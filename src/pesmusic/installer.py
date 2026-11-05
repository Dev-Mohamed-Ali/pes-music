"""Read, install, remove and repair the mod in a game folder."""
import copy
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass, field

from . import converter, playlist
from .errors import ModError
from .formats import filelist
from .formats.acb import Bank, bank_matches_audio, rebuild
from .formats.awb import read_awb
from .formats.cpk import Cpk
from .formats.utf import read_table, set_value
from .games import game_in

SOURCE = os.path.join("Data", "dt40_all.cpk")
NOTE = "PESMusic.json"
OLD_NOTE = "PES2017Music.json"
ACB, AWB, PLAYLIST = "BGM_P2P.acb", "BGM_P2P.awb", "Playlist.xml"
MENU_CATEGORY = "DefVol_Menu_Music"
BAD_ARCHIVE = (ModError, OSError, struct.error, ValueError, KeyError)

ORIGINAL, INSTALLED, NEW = "original", "installed", "new"
NOT_INSTALLED, ACTIVE, REPAIR = "not_installed", "installed", "repair"


@dataclass
class Slot:
    cue: str
    title: str
    artist: str
    seconds: float
    kind: str
    source: str
    offset: int
    rate: int

    def key(self):
        return self.kind, self.source, self.title, self.artist


@dataclass
class State:
    folder: str
    game: object
    status: str
    slots: list
    level: int = None
    mod_file: str = None
    problem: str = ""
    conflicts: list = field(default_factory=list)


def game_running(game):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {game.exe}"], capture_output=True, text=True,
                         **converter.HIDDEN).stdout
    return game.exe.lower() in out.lower()


def require_closed(game):
    if game_running(game):
        raise ModError(f"{game.name} is running. Close it and try again.")


def open_game(folder):
    game = game_in(folder)
    if not game or not os.path.exists(os.path.join(folder, SOURCE)):
        raise ModError("This is not a supported PES folder. Choose the folder that has the game's .exe.")
    with Cpk(os.path.join(folder, SOURCE)) as source:
        if playlist.edition(source.read(PLAYLIST).decode("utf-8")) != game.edition:
            raise ModError(f"This {game.name} version is not supported.")
    return game


def read_note(download):
    for name in (NOTE, OLD_NOTE):
        try:
            with open(os.path.join(download, name), encoding="utf-8") as f:
                note = json.load(f)
            if isinstance(note, dict):
                return note
        except (OSError, ValueError):
            continue
    return {}


def file_md5(path):
    digest = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            digest.update(chunk)
    return digest.hexdigest()


def is_healthy(download, mod_file):
    path = os.path.join(download, mod_file)
    try:
        with Cpk(path) as mod:
            if not bank_matches_audio(mod.read(ACB), mod.read(AWB)):
                return False
    except BAD_ARCHIVE:
        return False
    expected = read_note(download).get("md5")
    return not expected or file_md5(path) == expected


def louder_config(acf0, game):
    config = read_table(acf0)[0]
    index = {r["Name"]: r["Index"] for r in read_table(config["CategoryNameTable"])}[MENU_CATEGORY]
    categories = config["CategoryTable"]
    volume = game.volume
    command = read_table(config["CommandTable"])[volume.louder_row]["Command"]
    if read_table(categories)[index]["CommandIndex"] != volume.category_row or \
            command != bytes.fromhex(f"00570200{volume.louder_category:02x}"):
        raise ModError("Unexpected audio settings in the game data.")
    acf = bytearray(acf0)
    set_value(acf, acf0.find(categories), index, "CommandIndex", volume.louder_row)
    return bytes(acf)


def has_louder_config(acf, game):
    config = read_table(acf)[0]
    index = {r["Name"]: r["Index"] for r in read_table(config["CategoryNameTable"])}[MENU_CATEGORY]
    return read_table(config["CategoryTable"])[index]["CommandIndex"] == game.volume.louder_row


def find_mod(download, game):
    """Return the mod's file name: from our note, or by its volume patch for installs with no note."""
    noted = read_note(download).get("file")
    if noted or not game.volume or not os.path.isdir(download):
        return noted
    for name in sorted(os.listdir(download)):
        if name.lower().endswith(".cpk"):
            try:
                with Cpk(os.path.join(download, name)) as cpk:
                    if AWB in cpk.names() and has_louder_config(cpk.read(game.acf), game):
                        return name
            except BAD_ARCHIVE:
                continue
    return None


def other_archives(download, entries, mod_file):
    for entry in entries:
        name = filelist.entry_name(entry)
        path = os.path.join(download, name)
        if name != mod_file and os.path.exists(path):
            yield name, path


def find_conflicts(download, entries, mod_file):
    conflicts = []
    for name, path in other_archives(download, entries, mod_file):
        try:
            with Cpk(path) as cpk:
                if {ACB, AWB, PLAYLIST} & cpk.names():
                    conflicts.append(name)
        except BAD_ARCHIVE:
            continue
    return conflicts


def base_config(folder, game, entries, mod_file):
    """The audio settings the game really uses: a DLC copy can replace the one in dt40."""
    download = os.path.join(folder, "download")
    for _, path in reversed(list(other_archives(download, entries, mod_file))):
        try:
            with Cpk(path) as cpk:
                if game.acf in cpk.names():
                    return cpk.read(game.acf)
        except BAD_ARCHIVE:
            continue
    with Cpk(os.path.join(folder, SOURCE)) as source:
        return source.read(game.acf)


def read_bank(cpk):
    return Bank(cpk.read(ACB)), read_awb(cpk.read(AWB))


def stock_slots(folder):
    with Cpk(os.path.join(folder, SOURCE)) as source:
        xml = source.read(PLAYLIST).decode("utf-8")
        bank, awb = read_bank(source)
    names = playlist.read_names(xml)
    slots = []
    for cue in playlist.menu_cues(xml):
        track = bank.read_track(cue, awb)
        title, artist, offset = names[cue]
        slots.append(Slot(cue, title, artist, track.seconds, ORIGINAL, cue, offset, track.rate))
    return slots


def read_state(folder):
    game = open_game(folder)
    download = os.path.join(folder, "download")
    stock = stock_slots(folder)
    _, entries = filelist.read_list(os.path.join(download, filelist.NAME))
    mod_file = find_mod(download, game)
    state = State(folder, game, NOT_INSTALLED, stock, mod_file=mod_file)
    state.conflicts = find_conflicts(download, entries, mod_file)
    if not mod_file:
        return state

    if not os.path.exists(os.path.join(download, mod_file)):
        state.status, state.problem = REPAIR, "The mod file is missing from the download folder."
        return state
    if not is_healthy(download, mod_file):
        state.status, state.problem = REPAIR, "The installed mod file is damaged."
        return state

    with Cpk(os.path.join(folder, SOURCE)) as source:
        base_bank, base_awb = read_bank(source)
    with Cpk(os.path.join(download, mod_file)) as mod:
        bank, awb = read_bank(mod)
        names = playlist.read_names(mod.read(PLAYLIST).decode("utf-8"))
    state.slots = []
    for slot in stock:
        track = bank.read_track(slot.cue, awb)
        kind = ORIGINAL if track.data == base_bank.read_track(slot.cue, base_awb).data else INSTALLED
        title, artist, offset = names[slot.cue]
        state.slots.append(Slot(slot.cue, title, artist, track.seconds, kind, slot.cue, offset, track.rate))
    state.level = bank.level([s.cue for s in stock]) if game.volume else None
    state.status = ACTIVE
    if not any(filelist.entry_name(e) == mod_file for e in entries):
        state.status, state.problem = REPAIR, "The mod is in the folder, but the game is not set to load it."
    return state


def collect_tracks(slots, folder, mod_path, progress, cancel):
    """Return {cue: Track} for every slot not playing its own original audio."""
    with Cpk(os.path.join(folder, SOURCE)) as source:
        base_bank, base_awb = read_bank(source)
    mod_bank = mod_awb = None
    if mod_path and any(s.kind == INSTALLED for s in slots):
        with Cpk(mod_path) as mod:
            mod_bank, mod_awb = read_bank(mod)

    tracks = {}
    fresh = [s for s in slots if s.kind == NEW]
    with tempfile.TemporaryDirectory(prefix="pesmusic") as work:
        for slot in slots:
            if cancel.is_set():
                raise ModError("Install cancelled. Nothing changed.")
            if slot.kind == NEW:
                number = fresh.index(slot) + 1
                progress(number / (len(fresh) + 1), f"Converting {slot.title} ({number} of {len(fresh)})")
                tracks[slot.cue] = converter.convert(slot.source, work, number, slot.rate)
                slot.seconds = tracks[slot.cue].seconds
                slot.offset = playlist.highlight_start(slot.seconds)
            elif slot.kind == INSTALLED:
                tracks[slot.cue] = mod_bank.read_track(slot.source, mod_awb)
            elif slot.source != slot.cue:
                tracks[slot.cue] = base_bank.read_track(slot.source, base_awb)
    return tracks


def build(folder, game, slots, level, entries, mod_file, out_path, mod_path, progress, cancel):
    slots = copy.deepcopy(slots)
    tracks = collect_tracks(slots, folder, mod_path, progress, cancel)
    for slot in slots:
        if slot.offset >= slot.seconds * 1000:
            slot.offset = playlist.highlight_start(slot.seconds)
    progress(0.9, "Building the mod")
    with Cpk(os.path.join(folder, SOURCE)) as source:
        cues = [s.cue for s in slots]
        acb, awb = rebuild(source.read(ACB), source.read(AWB), tracks, cues, level)
        xml = playlist.write_names(source.read(PLAYLIST).decode("utf-8"), slots)
        files = {ACB: acb, AWB: awb, PLAYLIST: xml.encode("utf-8")}
        if game.volume:
            files[game.acf] = louder_config(base_config(folder, game, entries, mod_file), game)
        source.write_partial(files, out_path)
    with Cpk(out_path) as built:
        if not bank_matches_audio(built.read(ACB), built.read(AWB)):
            raise ModError("The built mod failed its check. Nothing changed.")


def tidy(download):
    """Finish or undo whatever an interrupted install left behind."""
    if not os.path.isdir(download):
        return
    for name in os.listdir(download):
        path = os.path.join(download, name)
        if name.endswith(".prev"):
            target = path[:-len(".prev")]
            if os.path.exists(target):
                os.remove(path)
            else:
                os.replace(path, target)
        elif name.endswith(".cpk.tmp") or name in (filelist.NAME + ".tmp", NOTE + ".tmp"):
            os.remove(path)


def write_note(download, mod_file):
    data = {"app": "PES Music", "version": 2, "file": mod_file, "md5": file_md5(os.path.join(download, mod_file))}
    temp = os.path.join(download, NOTE + ".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(temp, os.path.join(download, NOTE))
    old = os.path.join(download, OLD_NOTE)
    if os.path.exists(old):
        os.remove(old)


def pick_name(download, entries, game):
    """Take the first dt80 number no other mod uses."""
    taken = {filelist.entry_name(e).lower() for e in entries}
    numbers = {filelist.entry_number(e) for e in entries}
    for number in [*range(100, 1000, 100), *range(110, 1000, 10)]:
        name = f"dt80_{number}E_{game.suffix}.cpk"
        if name.lower() not in taken and number not in numbers and not os.path.exists(os.path.join(download, name)):
            return name, number
    raise ModError("No free mod name left in the download folder.")


def number_of(mod_file, download, entries, game):
    digits = re.search(r"dt80_(\d+)E", mod_file)
    return int(digits[1]) if digits else pick_name(download, entries, game)[1]


def add_to_list(list_path, first, entries, mod_file, number):
    if len(entries) >= filelist.MAX_ENTRIES:
        raise ModError(f"{filelist.NAME} is full, so the game cannot load another mod.")
    entry = filelist.new_entry(mod_file, number, filelist.load_version(entries))
    filelist.write_list(list_path, first, entries + [entry])


def install(folder, slots, level, progress, cancel):
    game = open_game(folder)
    require_closed(game)
    download = os.path.join(folder, "download")
    os.makedirs(download, exist_ok=True)
    tidy(download)
    state = read_state(folder)
    list_path = os.path.join(download, filelist.NAME)
    first, entries = filelist.read_list(list_path)

    size = os.path.getsize(os.path.join(folder, SOURCE))
    if shutil.disk_usage(download).free < 2 * size:
        raise ModError(f"Not enough free disk space. Free up {2 * size // 2**20} MB and try again.")

    mod_file = state.mod_file or pick_name(download, entries, game)[0]
    registered = any(filelist.entry_name(e) == mod_file for e in entries)
    if not registered and len(entries) >= filelist.MAX_ENTRIES:
        raise ModError(f"{filelist.NAME} is full, so the game cannot load another mod.")

    path = os.path.join(download, mod_file)
    temp, previous = path + ".tmp", path + ".prev"
    try:
        current = path if os.path.exists(path) and is_healthy(download, mod_file) else None
        build(folder, game, slots, level if game.volume else None, entries, mod_file, temp, current, progress, cancel)
        if cancel.is_set():
            raise ModError("Install cancelled. Nothing changed.")
        require_closed(game)
        progress(0.97, "Installing")
        if os.path.exists(list_path):
            shutil.copy2(list_path, list_path + ".bak")
        if os.path.exists(path):
            os.replace(path, previous)
        try:
            os.replace(temp, path)
            if not registered:
                add_to_list(list_path, first, entries, mod_file, number_of(mod_file, download, entries, game))
            write_note(download, mod_file)
        except OSError:
            if os.path.exists(previous):
                os.replace(previous, path)
            raise
        if os.path.exists(previous):
            os.remove(previous)
    finally:
        if os.path.exists(temp):
            os.remove(temp)
    progress(1, "Installed")


def _drop_from_list(download, mod_file):
    list_path = os.path.join(download, filelist.NAME)
    first, entries = filelist.read_list(list_path)
    kept = [e for e in entries if filelist.entry_name(e) != mod_file]
    if kept:
        if len(kept) != len(entries):
            shutil.copy2(list_path, list_path + ".bak")
            filelist.write_list(list_path, first, kept)
        return
    for path in (list_path, list_path + ".bak"):
        if os.path.exists(path):
            os.remove(path)


def remove(folder):
    game = open_game(folder)
    require_closed(game)
    download = os.path.join(folder, "download")
    tidy(download)
    mod_file = find_mod(download, game)
    if not mod_file:
        return False
    _drop_from_list(download, mod_file)
    for name in (mod_file, NOTE, OLD_NOTE):
        path = os.path.join(download, name)
        if os.path.exists(path):
            os.remove(path)
    return True


def repair(folder):
    """Make the list match reality: load a good mod, or clear out a broken one."""
    game = open_game(folder)
    require_closed(game)
    download = os.path.join(folder, "download")
    tidy(download)
    mod_file = find_mod(download, game)
    if not mod_file:
        return
    path = os.path.join(download, mod_file)
    if not (os.path.exists(path) and is_healthy(download, mod_file)):
        remove(folder)
        return
    list_path = os.path.join(download, filelist.NAME)
    first, entries = filelist.read_list(list_path)
    if not any(filelist.entry_name(e) == mod_file for e in entries):
        if os.path.exists(list_path):
            shutil.copy2(list_path, list_path + ".bak")
        add_to_list(list_path, first, entries, mod_file, number_of(mod_file, download, entries, game))
    write_note(download, mod_file)
