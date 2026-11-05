"""Full install, reinstall and removal on temporary copies of every installed game.

Needs the games, so it isn't part of the unit tests. Run from the project folder:
    set PYTHONPATH=src
    python tests\\game_scenarios.py <any song file> [game name ...]
"""
import copy
import os
import shutil
import sys
import tempfile
import threading
import traceback

from pesmusic import converter, games, installer, playlist
from pesmusic.formats import filelist
from pesmusic.formats.cpk import Cpk

results = []


def check(name, passed, detail=""):
    results.append(bool(passed))
    print(f"  {'PASS' if passed else 'FAIL'} {name} {detail}")


def copy_game(source, target, keep_mod=False):
    game = games.game_in(source)
    download = os.path.join(target, "download")
    os.makedirs(os.path.join(target, "Data"))
    os.makedirs(download)
    shutil.copy(os.path.join(source, installer.SOURCE), os.path.join(target, "Data"))
    open(os.path.join(target, game.exe), "wb").close()
    list_path = os.path.join(source, "download", filelist.NAME)
    if os.path.exists(list_path) and not keep_mod and game.edition != 17:
        shutil.copy(list_path, download)
    if keep_mod:
        for name in os.listdir(os.path.join(source, "download")):
            shutil.copy(os.path.join(source, "download", name), download)
    return game


def play_through(folder, game, song):
    quiet, go = (lambda *_: None), threading.Event()
    download = os.path.join(folder, "download")
    list_path = os.path.join(download, filelist.NAME)
    original_list = open(list_path, "rb").read() if os.path.exists(list_path) else None

    state = installer.read_state(folder)
    check("reads the stock game", state.status == installer.NOT_INSTALLED, f"{len(state.slots)} slots")
    slots = copy.deepcopy(state.slots)
    seconds = converter.probe(song)
    artist, title = playlist.names_from_file(song, game)
    odd = next((i for i, s in enumerate(slots) if s.rate != 48000), None)
    changed = [0] + ([odd] if odd else [])
    for i in changed:
        slots[i] = installer.Slot(slots[i].cue, title, artist, seconds, installer.NEW, song,
                                  playlist.highlight_start(seconds), slots[i].rate)
    level = 80 if game.volume else None
    installer.install(folder, slots, level, quiet, go)

    state = installer.read_state(folder)
    check("installs", state.status == installer.ACTIVE, state.mod_file)
    check("new slots read back", all(state.slots[i].title == title for i in changed))
    check("other slots stay original",
          all(s.kind == installer.ORIGINAL for i, s in enumerate(state.slots) if i not in changed))
    check("level", state.level == level, state.level)
    with Cpk(os.path.join(download, state.mod_file)) as mod:
        check("partial archive", len(mod.rows) == (4 if game.volume else 3), sorted(mod.names()))
    newest = filelist.read_list(list_path)[1][-1]
    check("list entry", filelist.entry_name(newest) == state.mod_file, filelist.entry_version(newest))

    slots = copy.deepcopy(state.slots)
    slots[1].cue, slots[2].cue = slots[2].cue, slots[1].cue
    slots[1], slots[2] = slots[2], slots[1]
    installer.install(folder, slots, game.volume.lowest_level if game.volume else None, quiet, go)
    after = installer.read_state(folder)
    check("swapped slots survive a reinstall", after.slots[1].title == state.slots[2].title)

    installer.remove(folder)
    now = open(list_path, "rb").read() if os.path.exists(list_path) else None
    check("removal restores the list exactly", now == original_list)
    leftovers = [n for n in os.listdir(download) if n in (state.mod_file, installer.NOTE, filelist.NAME + ".bak")]
    check("removal leaves no mod files", not leftovers, leftovers)


def upgrade_old_install(source, song):
    """An install made by the old PES 2017 app is a full archive with its own note."""
    root = tempfile.mkdtemp(prefix="pesmusic")
    try:
        folder = os.path.join(root, "game")
        game = copy_game(source, folder, keep_mod=True)
        before = installer.read_state(folder)
        check("sees the old install", before.status == installer.ACTIVE, f"{before.mod_file} at {before.level}%")
        installer.install(folder, before.slots, before.level, lambda *_: None, threading.Event())
        after = installer.read_state(folder)
        check("keeps every song and name", [s.key() for s in after.slots] == [s.key() for s in before.slots])
        check("same level", after.level == before.level)
        check("old note replaced", not os.path.exists(os.path.join(folder, "download", installer.OLD_NOTE)))
        with Cpk(os.path.join(folder, "download", after.mod_file)) as mod:
            check("now a partial archive", len(mod.rows) == 4, game.name)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    song, only = sys.argv[1], sys.argv[2:]
    installer.game_running = lambda _: False
    for name, source in games.find_installs().items():
        if only and name not in only:
            continue
        print(name)
        root = tempfile.mkdtemp(prefix="pesmusic")
        try:
            folder = os.path.join(root, "game")
            play_through(folder, copy_game(source, folder), song)
            if games.game_in(source).edition == 17 and installer.read_note(os.path.join(source, "download")):
                upgrade_old_install(source, song)
        except Exception:
            check("no crash", False, traceback.format_exc()[-300:])
        finally:
            shutil.rmtree(root, ignore_errors=True)
    print("ALL PASS" if all(results) else "SOME FAILED", len(results))


if __name__ == "__main__":
    main()
