"""The rename window."""
import customtkinter as ctk

from .theme import CHALK, FLOODLIGHT, FLOODLIGHT_LIGHT, LINE, NIGHT, TURF, TURF_LIGHT, font


class RenameDialog(ctk.CTkToplevel):
    def __init__(self, parent, slot, on_save):
        super().__init__(parent)
        self.title("Rename track")
        self.geometry("420x230")
        self.resizable(False, False)
        self.configure(fg_color=NIGHT)
        self.transient(parent)
        self.on_save = on_save
        self.title_value = ctk.StringVar(value=slot.title)
        self.artist_value = ctk.StringVar(value=slot.artist)
        for label, value in (("Title", self.title_value), ("Artist", self.artist_value)):
            ctk.CTkLabel(self, text=label, font=font(13), text_color=LINE, anchor="w").pack(
                fill="x", padx=18, pady=(10, 0))
            ctk.CTkEntry(self, textvariable=value, font=font(14), fg_color=TURF, border_color=TURF_LIGHT,
                         text_color=CHALK).pack(fill="x", padx=18)
        ctk.CTkLabel(self, text="Long names are shortened to what the game can show.", font=font(12),
                     text_color=LINE, anchor="w").pack(fill="x", padx=18, pady=(8, 0))
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=12)
        ctk.CTkButton(actions, text="Save name", width=100, font=font(13, "bold"), fg_color=FLOODLIGHT,
                      text_color=NIGHT, hover_color=FLOODLIGHT_LIGHT, corner_radius=4, command=self.save).pack(side="left")
        ctk.CTkButton(actions, text="Cancel", width=80, font=font(13), fg_color="transparent", hover_color=TURF_LIGHT,
                      text_color=CHALK, corner_radius=4, command=self.destroy).pack(side="left", padx=6)
        self.after(50, self.grab_set)
        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<Return>", lambda _: self.save())

    def save(self):
        self.on_save(self.title_value.get(), self.artist_value.get())
        self.destroy()
