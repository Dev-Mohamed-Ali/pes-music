"""The main window."""
import copy
import os
import queue
import threading
import traceback
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .. import __version__, converter, installer, playlist, settings
from ..errors import ModError
from ..games import find_installs, game_in
from ..installer import ACTIVE, NEW, NOT_INSTALLED, ORIGINAL, REPAIR, Slot
from .dialogs import RenameDialog
from .rows import SlotRow
from .theme import CARD, CHALK, FLOODLIGHT, FLOODLIGHT_LIGHT, LINE, MUTED_ON_LIGHT, NIGHT, TURF, TURF_LIGHT, font

NO_LEVEL_TEXT = "This game's menu level can't be changed."


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=NIGHT)
        self.title(f"PES Music {__version__}")
        self.geometry("960x820")
        self.minsize(860, 640)
        self.after(250, self.set_icon)
        self.config_data = settings.load()
        self.installs = find_installs(self.config_data.get("folders", []))
        self.folder = self.config_data.get("folder")
        if self.folder not in self.installs.values():
            self.folder = next(iter(self.installs.values()), None)
        self.state_info = None
        self.slots, self.baseline, self.stock, self.rows = [], [], [], []
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.close_after = False
        self.build_window()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.poll)
        self.check_tools()
        self.load_game()

    def set_icon(self):
        path = converter.resource(os.path.join("assets", "icon.ico"))
        if path:
            self.iconbitmap(path)

    def plain_button(self, parent, text, command, width=110):
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=32, corner_radius=4,
                             font=font(13), fg_color=TURF, hover_color=TURF_LIGHT, text_color=CHALK)

    def build_window(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.build_header()
        self.notice = ctk.CTkFrame(self, fg_color=TURF_LIGHT, corner_radius=4)
        self.notice.grid_columnconfigure(0, weight=1)
        self.notice_text = ctk.CTkLabel(self.notice, text="", font=font(13), text_color=CHALK, anchor="w", justify="left")
        self.notice_text.grid(row=0, column=0, sticky="ew", padx=10, pady=6)
        self.notice_button = ctk.CTkButton(self.notice, text="", width=120, height=28, corner_radius=4,
                                           font=font(13, "bold"), fg_color=FLOODLIGHT, hover_color=FLOODLIGHT_LIGHT,
                                           text_color=NIGHT)
        self.sheet = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=TURF_LIGHT,
                                            scrollbar_button_hover_color=LINE)
        self.sheet.grid(row=2, column=0, sticky="nsew", padx=(22, 12), pady=(10, 0))
        self.build_footer()

    def build_header(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 0))
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text="PES Music", font=font(30, "bold"), text_color=CHALK).grid(row=0, column=0, sticky="w")
        self.game_menu = ctk.CTkOptionMenu(head, values=list(self.installs) or ["No game found"], command=self.pick_install,
                                           width=130, height=30, corner_radius=4, font=font(14, "bold"),
                                           dropdown_font=font(13), fg_color=TURF, button_color=TURF_LIGHT,
                                           button_hover_color=LINE, text_color=CHALK, dropdown_fg_color=TURF,
                                           dropdown_text_color=CHALK, dropdown_hover_color=TURF_LIGHT)
        self.game_menu.grid(row=0, column=1, sticky="w", padx=14)
        self.status = ctk.CTkLabel(head, text="Checking the game", font=font(15, "bold"), text_color=LINE, anchor="e")
        self.status.grid(row=0, column=2, sticky="e")
        self.path_label = ctk.CTkLabel(head, text="", font=font(13), text_color=LINE, anchor="w")
        self.path_label.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.change_game = ctk.CTkButton(head, text="Add a game folder", width=130, height=24, corner_radius=4,
                                         font=font(12), fg_color="transparent", hover_color=TURF, text_color=CHALK,
                                         command=self.pick_folder)
        self.change_game.grid(row=1, column=2, sticky="e")

    def build_footer(self):
        adds = ctk.CTkFrame(self, fg_color="transparent")
        adds.grid(row=3, column=0, sticky="ew", padx=22, pady=(8, 0))
        self.add_tracks_button = self.plain_button(adds, "Add tracks", self.add_tracks)
        self.add_tracks_button.pack(side="left")
        self.add_folder_button = self.plain_button(adds, "Add a folder", self.add_folder)
        self.add_folder_button.pack(side="left", padx=6)
        ctk.CTkLabel(adds, text="New tracks fill the slots still playing original songs.", font=font(12),
                     text_color=LINE).pack(side="left", padx=8)

        level = ctk.CTkFrame(self, fg_color="transparent")
        level.grid(row=4, column=0, sticky="ew", padx=22, pady=(12, 0))
        level.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(level, text="Music level", font=font(14, "bold"), text_color=CHALK).grid(row=0, column=0, padx=(0, 12))
        self.slider = ctk.CTkSlider(level, from_=23, to=100, number_of_steps=77, command=self.on_level, fg_color=TURF,
                                    progress_color=FLOODLIGHT, button_color=CHALK, button_hover_color=FLOODLIGHT_LIGHT)
        self.slider.grid(row=0, column=1, sticky="ew")
        self.level_label = ctk.CTkLabel(level, text="", font=font(12), text_color=LINE, width=270, anchor="e")
        self.level_label.grid(row=0, column=2, padx=(12, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=5, column=0, sticky="ew", padx=22, pady=(10, 16))
        actions.grid_columnconfigure(1, weight=1)
        self.install_button = ctk.CTkButton(actions, text="Install mod", width=170, height=40, corner_radius=4,
                                            font=font(15, "bold"), fg_color=FLOODLIGHT, hover_color=FLOODLIGHT_LIGHT,
                                            text_color=NIGHT, text_color_disabled=MUTED_ON_LIGHT, command=self.start_install)
        self.install_button.grid(row=0, column=0, rowspan=2)
        self.message = ctk.CTkLabel(actions, text="", font=font(13), text_color=LINE, anchor="w")
        self.message.grid(row=0, column=1, sticky="ew", padx=14)
        self.progress = ctk.CTkProgressBar(actions, height=6, corner_radius=2, fg_color=TURF, progress_color=FLOODLIGHT)
        self.progress.set(0)
        self.remove_button = ctk.CTkButton(actions, text="Remove mod", width=110, height=32, corner_radius=4, font=font(13),
                                           fg_color="transparent", border_width=1, border_color=CARD,
                                           hover_color="#3A2B2A", text_color=CHALK, command=self.start_remove)
        self.remove_button.grid(row=0, column=2, rowspan=2)

    @property
    def game(self):
        return self.state_info.game if self.state_info else None

    def is_stock(self, index):
        return self.slots[index].key() == self.stock[index].key()

    def pending(self, index):
        return self.slots[index].key() != self.baseline[index].key()

    def has_changes(self):
        info = self.state_info
        if not info or not self.slots:
            return False
        if info.status != ACTIVE:
            return True
        level_changed = self.game.volume is not None and self.level() != info.level
        return level_changed or [s.key() for s in self.slots] != [s.key() for s in self.baseline]

    def level(self):
        return round(self.slider.get())

    def show_level(self, level):
        volume = self.game.volume
        self.level_label.configure(text=f"{level}%, {volume.gain_db(level):.1f} dB louder than the original game")

    def on_level(self, value):
        self.show_level(round(value))
        self.refresh_buttons()

    def rebuild_rows(self):
        if len(self.rows) == len(self.slots):
            return
        for row in self.rows:
            row.destroy()
        self.rows = [SlotRow(self, self.sheet, i) for i in range(len(self.slots))]

    def refresh(self):
        self.rebuild_rows()
        for i, row in enumerate(self.rows):
            row.show(self.slots[i], self.pending(i), self.is_stock(i))
        self.refresh_buttons()

    def refresh_buttons(self):
        ready = bool(self.state_info) and not self.busy
        if self.busy:
            self.install_button.configure(text="Cancel", state="normal", command=self.request_cancel)
        else:
            active = self.state_info and self.state_info.status == ACTIVE
            self.install_button.configure(text="Install changes" if active else "Install mod",
                                          state="normal" if ready and self.has_changes() else "disabled",
                                          command=self.start_install)
        self.remove_button.configure(state="normal" if ready and self.state_info.mod_file else "disabled")
        self.change_game.configure(state="disabled" if self.busy else "normal")
        self.game_menu.configure(state="disabled" if self.busy else "normal")
        for widget in (self.add_tracks_button, self.add_folder_button):
            widget.configure(state="normal" if ready else "disabled")
        self.slider.configure(state="normal" if ready and self.game.volume else "disabled")
        for i, row in enumerate(self.rows):
            row.enable(ready)
            if ready and i < len(self.slots):
                row.buttons["reset"].configure(state="disabled" if self.is_stock(i) else "normal")

    def show_message(self, text, tone=LINE):
        self.message.configure(text=text, text_color=tone)

    def show_notice(self, text="", action=None, command=None):
        if not text:
            self.notice.grid_forget()
            return
        self.notice_text.configure(text=text)
        if action:
            self.notice_button.configure(text=action, command=command)
            self.notice_button.grid(row=0, column=1, padx=8, pady=6)
        else:
            self.notice_button.grid_forget()
        self.notice.grid(row=1, column=0, sticky="ew", padx=22, pady=(10, 0))

    def apply_state(self, info):
        self.state_info = info
        self.slots, self.baseline = copy.deepcopy(info.slots), copy.deepcopy(info.slots)
        self.path_label.configure(text=info.folder)
        self.game_menu.set(info.game.name)
        label = {ACTIVE: "Mod installed", NOT_INSTALLED: "Mod not installed", REPAIR: "Mod needs repair"}[info.status]
        if info.status == ACTIVE and info.level:
            label += f" at {info.level}%"
        tone = {ACTIVE: FLOODLIGHT, NOT_INSTALLED: LINE, REPAIR: CARD}[info.status]
        self.status.configure(text=label, text_color=tone)

        volume = info.game.volume
        if volume:
            self.slider.configure(from_=volume.lowest_level, number_of_steps=100 - volume.lowest_level)
            level = info.level or 100
            self.slider.set(level)
            self.show_level(level)
        else:
            self.level_label.configure(text=NO_LEVEL_TEXT)

        if info.status == REPAIR:
            self.show_notice(info.problem, "Repair mod", self.start_repair)
        elif info.conflicts:
            names = ", ".join(info.conflicts)
            self.show_notice(f"{names} also changes menu music. One mod will override the other.")
        elif converter.ffmpeg_ready():
            self.show_notice()
        self.refresh()

    def poll(self):
        while not self.events.empty():
            kind, payload = self.events.get()
            if kind == "stock":
                self.stock = payload
            elif kind == "state":
                self.apply_state(payload)
            elif kind == "progress":
                self.progress.set(payload[0])
                self.show_message(payload[1])
            elif kind == "message":
                self.show_message(*payload)
            elif kind == "songs":
                self.place_songs(*payload)
            elif kind == "done":
                self.finish()
            elif kind == "call":
                payload()
        self.after(80, self.poll)

    def finish(self):
        self.busy = False
        self.progress.grid_forget()
        self.refresh_buttons()
        if self.close_after:
            self.destroy()

    def run(self, work):
        self.busy = True
        self.cancel.clear()
        self.refresh_buttons()

        def task():
            try:
                work()
            except ModError as error:
                self.events.put(("message", (str(error), CARD)))
            except Exception:
                settings.log.error(traceback.format_exc())
                self.events.put(("message", (f"Something went wrong. Details are in {settings.LOG_FILE}", CARD)))
            self.events.put(("done", None))

        threading.Thread(target=task, daemon=True).start()

    def request_cancel(self):
        self.cancel.set()
        self.show_message("Cancelling")

    def load_game(self):
        folder = self.folder
        if not folder:
            self.load_failed()
            return
        self.path_label.configure(text=folder)
        self.show_message("Checking the game")

        def work():
            try:
                info = installer.read_state(folder)
            except ModError:
                self.events.put(("call", self.load_failed))
                raise
            self.events.put(("stock", installer.stock_slots(folder)))
            self.events.put(("state", info))
            self.events.put(("message", ("", LINE)))
            self.config_data["folder"] = folder
            settings.save(self.config_data)

        self.run(work)

    def load_failed(self):
        self.state_info = None
        self.slots, self.baseline, self.stock = [], [], []
        self.status.configure(text="Choose your game folder", text_color=FLOODLIGHT)
        self.level_label.configure(text="")
        self.refresh()

    def check_tools(self):
        if not converter.ffmpeg_ready():
            self.show_notice("FFmpeg is needed to convert songs. It is free and installs in about a minute.",
                             "Install FFmpeg", self.start_ffmpeg)

    def start_ffmpeg(self):
        def work():
            self.events.put(("message", ("Installing FFmpeg", LINE)))
            converter.install_ffmpeg()
            self.events.put(("call", self.show_notice))
            self.events.put(("message", ("FFmpeg installed.", CHALK)))

        self.run(work)

    def pick_install(self, name):
        if name in self.installs:
            self.folder = self.installs[name]
            self.load_game()

    def pick_folder(self):
        chosen = filedialog.askdirectory(title="Choose a PES game folder", initialdir=self.folder or None)
        if not chosen:
            return
        folder = os.path.normpath(chosen)
        game = game_in(folder)
        if not game:
            self.show_message("That folder has no supported PES game. Choose the folder with the game's .exe.", CARD)
            return
        self.installs[game.name] = folder
        self.installs = dict(sorted(self.installs.items()))
        self.game_menu.configure(values=list(self.installs))
        self.config_data["folders"] = sorted({*self.config_data.get("folders", []), folder})
        self.folder = folder
        self.load_game()

    def choose_files(self, multiple=True):
        types = [("Audio", " ".join("*" + e for e in converter.AUDIO_EXTENSIONS)), ("All files", "*.*")]
        start = self.config_data.get("music")
        if multiple:
            return filedialog.askopenfilenames(title="Choose tracks", initialdir=start, filetypes=types)
        path = filedialog.askopenfilename(title="Choose a track", initialdir=start, filetypes=types)
        return [path] if path else []

    def add_tracks(self):
        self.check_songs(self.choose_files(), None)

    def add_folder(self):
        folder = filedialog.askdirectory(title="Choose a folder of songs", initialdir=self.config_data.get("music"))
        if not folder:
            return
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(converter.AUDIO_EXTENSIONS))
        if not names:
            self.show_message("That folder has no audio files.", CARD)
            return
        self.check_songs([os.path.join(folder, n) for n in names], None)

    def replace(self, index):
        self.check_songs(self.choose_files(multiple=False), index)

    def check_songs(self, paths, index):
        paths = [os.path.normpath(p) for p in paths]
        if not paths:
            return
        self.config_data["music"] = os.path.dirname(paths[0])

        def work():
            good, bad = [], []
            for number, path in enumerate(paths, 1):
                if self.cancel.is_set():
                    break
                self.events.put(("message", (f"Checking track {number} of {len(paths)}", LINE)))
                try:
                    good.append((path, converter.probe(path)))
                except ModError as error:
                    bad.append(str(error))
            self.events.put(("songs", (good, bad, index)))

        self.run(work)

    def place_songs(self, good, bad, index):
        if not self.slots:
            return
        known = {s.source for s in self.slots if s.kind == NEW}
        placed = skipped = 0
        for path, seconds in good:
            if path in known:
                continue
            target = index if index is not None else next(
                (i for i, s in enumerate(self.slots) if s.kind == ORIGINAL), None)
            if target is None:
                skipped += 1
                continue
            artist, title = playlist.names_from_file(path, self.game)
            slot = self.slots[target]
            self.slots[target] = Slot(slot.cue, title, artist, seconds, NEW, path,
                                      playlist.highlight_start(seconds), slot.rate)
            placed += 1
        self.refresh()
        notes = []
        if placed:
            notes.append(f"Added {placed} track{'s' if placed != 1 else ''}.")
        if skipped:
            notes.append(f"{skipped} left out: no original slots remain. Use Replace on a slot.")
        if bad:
            notes.append(bad[0] if len(bad) == 1 else f"{len(bad)} files could not be used. First: {bad[0]}")
        self.show_message(" ".join(notes), CARD if bad or skipped else CHALK)

    def move(self, index, step):
        other = index + step
        if 0 <= other < len(self.slots):
            first, second = self.slots[index], self.slots[other]
            first.cue, second.cue = second.cue, first.cue
            self.slots[index], self.slots[other] = second, first
            # converted songs take their slot's rate; existing audio keeps its own
            for position in (index, other):
                if self.slots[position].kind == NEW:
                    self.slots[position].rate = self.stock[position].rate
            self.refresh()

    def rename(self, index):
        slot = self.slots[index]

        def save(title, artist):
            title = playlist.fit(playlist.clean_name(title), self.game.title_limit)
            artist = playlist.fit(playlist.clean_name(artist), self.game.artist_limit)
            if not title:
                self.show_message("A track needs a title.", CARD)
                return
            slot.title, slot.artist = title, artist or "Unknown"
            self.refresh()

        RenameDialog(self, slot, save)

    def reset(self, index):
        self.slots[index] = copy.deepcopy(self.stock[index])
        self.refresh()

    def start_install(self):
        folder, slots = self.folder, copy.deepcopy(self.slots)
        level = self.level() if self.game.volume else None
        if any(s.kind == NEW for s in slots) and not converter.ffmpeg_ready():
            self.show_message("FFmpeg is needed first.", CARD)
            return
        self.progress.grid(row=1, column=1, sticky="ew", padx=14)
        self.progress.set(0)

        def work():
            installer.install(folder, slots, level, lambda value, text: self.events.put(("progress", (value, text))),
                              self.cancel)
            self.events.put(("state", installer.read_state(folder)))
            self.events.put(("message", (f"Installed. Start {self.game.name} to hear it.", CHALK)))

        self.run(work)

    def start_remove(self):
        if not messagebox.askyesno("Remove mod", "Remove the mod and go back to the game's own menu music?"):
            return
        folder = self.folder

        def work():
            installer.remove(folder)
            self.events.put(("state", installer.read_state(folder)))
            self.events.put(("message", ("Mod removed.", CHALK)))

        self.run(work)

    def start_repair(self):
        folder = self.folder

        def work():
            installer.repair(folder)
            self.events.put(("state", installer.read_state(folder)))
            self.events.put(("message", ("Repair finished.", CHALK)))

        self.run(work)

    def on_close(self):
        if not self.busy:
            self.destroy()
        elif messagebox.askyesno("Job running", "Stop the current job and close?"):
            self.cancel.set()
            self.close_after = True


def main():
    settings.setup_logging()
    ctk.set_appearance_mode("dark")
    App().mainloop()
