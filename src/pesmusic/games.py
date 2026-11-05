"""What differs between the supported games."""
import math
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Volume:
    """Menu music is cue % x category %. The mod moves the category to a louder row the game already has."""

    cue: int
    category: int
    louder_category: int
    category_row: int = 2
    louder_row: int = 1

    @property
    def lowest_level(self):
        return math.ceil(self.cue * self.category / self.louder_category)

    def gain_db(self, level):
        stock = self.cue * self.category
        return max(20 * math.log10(level * self.louder_category / stock), 0.0)


@dataclass(frozen=True)
class Game:
    name: str
    exe: str
    acf: str
    edition: int
    suffix: str
    title_limit: tuple
    artist_limit: tuple
    volume: Volume | None


# name limits are (bytes, bytes once XML-escaped); only PES 2017 is known to crash past its limit,
# the others use the longest names Konami shipped
GAMES = (
    Game("PES 2016", "PES2016.exe", "PES2016.acf", 16, "win", (47, 47), (41, 41), None),
    Game("PES 2017", "PES2017.exe", "PES2017.acf", 17, "win", (25, 29), (38, 40), Volume(50, 30, 65)),
    Game("PES 2019", "PES2019.exe", "PES2019.acf", 19, "x64", (28, 28), (30, 30), Volume(60, 30, 65)),
    Game("PES 2020", "PES2020.exe", "PES2020.acf", 20, "x64", (22, 22), (36, 36), Volume(60, 33, 73)),
    Game("PES 2021", "PES2021.exe", "PES2021.acf", 21, "x64", (35, 35), (20, 20), Volume(60, 33, 73)),
)


def game_in(folder):
    return next((g for g in GAMES if os.path.exists(os.path.join(folder, g.exe))), None)


def _steam_libraries():
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam = winreg.QueryValueEx(key, "SteamPath")[0]
        with open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), encoding="utf-8") as f:
            paths = [line.split('"')[3].replace("\\\\", "\\") for line in f if '"path"' in line]
        return [os.path.join(p, "steamapps", "common") for p in [steam, *paths]]
    except (OSError, IndexError):
        return []


def find_installs(extra=()):
    """Return {game name: folder} for installs found in common places and `extra` folders."""
    roots = [f"{drive}:\\Games" for drive in "CDEFG"] + _steam_libraries()
    folders = list(extra)
    for root in roots:
        if os.path.isdir(root):
            folders += [os.path.join(root, name) for name in sorted(os.listdir(root))]
    found = {}
    for folder in folders:
        game = game_in(folder) if os.path.isdir(folder) else None
        if game:
            found.setdefault(game.name, folder)
    return dict(sorted(found.items()))
