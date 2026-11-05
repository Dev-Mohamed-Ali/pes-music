"""Colours and type: a team sheet under floodlights."""
import customtkinter as ctk

NIGHT, TURF, TURF_LIGHT = "#12302B", "#1A3F38", "#245248"
CHALK, LINE = "#EEF2E6", "#9DB5A9"
FLOODLIGHT, FLOODLIGHT_LIGHT, CARD = "#F2C14E", "#FFD97A", "#E2685F"
MUTED_ON_LIGHT = "#5F7A70"
FONT = "Bahnschrift"


def font(size, weight="normal"):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


def clock(seconds):
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"
