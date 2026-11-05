"""Playlist.xml and the names shown in the game."""
import html
import os
import re
import unicodedata
from xml.sax.saxutils import escape

from .errors import ModError

LABEL = re.compile(r'<Label CueName="(\w+)" Id="(\d+)" Title="([^"]*)" Artist="([^"]*)" Offset="(\d+)"')
MENU_LIST = re.compile(r'<List ListName="Menu".*?</List>', re.S)
HIGHLIGHT_START_MS = 60000
NAME_FIXES = {"K_DA": "K/DA"}


def esc(text):
    return escape(text, {'"': "&quot;"})


def fit(text, limit):
    while len(text.encode()) > limit[0] or len(esc(text).encode()) > limit[1]:
        text = text[:-1]
    return text.rstrip(" ,&(-")


def clean_name(text):
    for bad, good in NAME_FIXES.items():
        text = text.replace(bad, good)
    text = re.sub(r"\s*\(from the [^)]*\)", "", text, flags=re.I)
    text = text.replace("[", "(").replace("]", ")").replace(", &", " &")

    def without_accent(char):
        # Latin letters only: decomposing Hangul or kana would corrupt them
        base = unicodedata.normalize("NFD", char)[0]
        return base if base.isascii() else char

    return "".join(c for c in map(without_accent, text) if c.isprintable()).strip()


def names_from_file(path, game):
    stem = os.path.splitext(os.path.basename(path))[0]
    artist, title = stem.split(" - ", 1) if " - " in stem else ("Unknown", stem)
    return (fit(clean_name(artist), game.artist_limit) or "Unknown",
            fit(clean_name(title), game.title_limit) or "Track")


def highlight_start(seconds):
    return min(HIGHLIGHT_START_MS, int(seconds * 1000) // 3)


def read_names(xml):
    """Return {cue: (title, artist, highlight start)}."""
    return {cue: (html.unescape(title), html.unescape(artist), int(offset))
            for cue, _, title, artist, offset in LABEL.findall(xml)}


def menu_cues(xml):
    """The cues in the menu rotation, in order. The game's cue list can hold others."""
    menu = MENU_LIST.search(xml)
    if not menu:
        raise ModError("The game's playlist has no menu list.")
    by_id = {song_id: cue for cue, song_id, *_ in LABEL.findall(xml)}
    return [by_id[song_id] for song_id in re.findall(r'<Label Id="(\d+)"/>', menu[0])]


def edition(xml):
    found = re.search(r'wepes="(\d+)"', xml)
    return int(found[1]) if found else None


def write_names(xml, slots):
    for slot in slots:
        pattern = rf'(<Label CueName="{slot.cue}" Id="\d+") Title="[^"]*" Artist="[^"]*" Offset="\d+"'
        attributes = f' Title="{esc(slot.title)}" Artist="{esc(slot.artist)}" Offset="{slot.offset}"'
        xml, hits = re.subn(pattern, lambda match: match[1] + attributes, xml)
        if hits != 1:
            raise ModError(f"Playlist entry {slot.cue} not found.")
    return xml
