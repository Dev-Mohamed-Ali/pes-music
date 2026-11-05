"""One line of the team sheet."""
import customtkinter as ctk

from ..installer import INSTALLED, NEW, ORIGINAL
from .theme import CHALK, FLOODLIGHT, LINE, TURF, TURF_LIGHT, clock, font

STATE_TEXT = {ORIGINAL: "Original", INSTALLED: "Installed", NEW: "New"}


class SlotRow:
    def __init__(self, app, parent, index):
        self.app = app
        self.index = index
        self.frame = ctk.CTkFrame(parent, fg_color=TURF, corner_radius=4, height=52)
        self.frame.pack(fill="x", pady=(0, 3))
        self.frame.grid_columnconfigure(1, weight=1)
        self.number = ctk.CTkLabel(self.frame, text=str(index + 1), width=48, font=font(24, "bold"), text_color=LINE)
        self.number.grid(row=0, column=0, rowspan=2, padx=(6, 4))
        self.title = ctk.CTkLabel(self.frame, text="", anchor="w", font=font(15, "bold"), text_color=CHALK, height=20)
        self.title.grid(row=0, column=1, sticky="ew", pady=(6, 0))
        self.artist = ctk.CTkLabel(self.frame, text="", anchor="w", font=font(12), text_color=LINE, height=18)
        self.artist.grid(row=1, column=1, sticky="ew", pady=(0, 6))
        self.length = ctk.CTkLabel(self.frame, text="", width=44, font=font(13), text_color=LINE)
        self.length.grid(row=0, column=2, rowspan=2)
        self.state = ctk.CTkLabel(self.frame, text="", width=70, font=font(12), text_color=LINE)
        self.state.grid(row=0, column=3, rowspan=2)

        tools = ctk.CTkFrame(self.frame, fg_color="transparent")
        tools.grid(row=0, column=4, rowspan=2, padx=(0, 6))
        self.buttons = {}
        for name, text, width, command in (
            ("up", "▲", 28, lambda: app.move(index, -1)),
            ("down", "▼", 28, lambda: app.move(index, 1)),
            ("replace", "Replace", 66, lambda: app.replace(index)),
            ("rename", "Rename", 62, lambda: app.rename(index)),
            ("reset", "Reset", 52, lambda: app.reset(index)),
        ):
            button = ctk.CTkButton(tools, text=text, width=width, height=26, corner_radius=4, font=font(12),
                                   fg_color="transparent", hover_color=TURF_LIGHT, text_color=CHALK, command=command)
            button.pack(side="left", padx=1)
            self.buttons[name] = button

    def show(self, slot, pending, is_stock):
        tone = FLOODLIGHT if pending else CHALK if slot.kind == INSTALLED else LINE
        self.title.configure(text=slot.title)
        self.artist.configure(text=slot.artist)
        self.length.configure(text=clock(slot.seconds))
        self.state.configure(text=STATE_TEXT[slot.kind], text_color=tone)
        self.number.configure(text_color=tone)
        self.buttons["reset"].configure(state="disabled" if is_stock else "normal")

    def enable(self, enabled):
        for name, button in self.buttons.items():
            if name != "reset" or not enabled:
                button.configure(state="normal" if enabled else "disabled")

    def destroy(self):
        self.frame.destroy()
