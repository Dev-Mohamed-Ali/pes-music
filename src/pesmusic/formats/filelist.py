"""download\\DpFileList.bin, the list of extra archives the game loads."""
import os
import struct

from ..errors import ModError

NAME = "DpFileList.bin"
FILE_SIZE, MAX_ENTRIES, ENTRY_SIZE = 3080, 64, 48
DEFAULT_VERSION = 10100


def read_list(path):
    """Return (first header value, entries). Refuses a file it can't fully understand."""
    if not os.path.exists(path):
        return 100, []
    with open(path, "rb") as f:
        data = f.read()
    count = struct.unpack("<I", data[4:8])[0] if len(data) == FILE_SIZE else MAX_ENTRIES + 1
    if count > MAX_ENTRIES:
        raise ModError(f"{NAME} has an unknown format, so it was left alone.")
    entries = [data[8 + i * ENTRY_SIZE:8 + (i + 1) * ENTRY_SIZE] for i in range(count)]
    return struct.unpack("<I", data[:4])[0], entries


def write_list(path, first, entries):
    temp = path + ".tmp"
    with open(temp, "wb") as f:
        f.write((struct.pack("<II", first, len(entries)) + b"".join(entries)).ljust(FILE_SIZE, b"\0"))
    os.replace(temp, path)


def entry_name(entry):
    return entry[8:40].split(b"\0")[0].decode("ascii", "replace")


def entry_number(entry):
    return struct.unpack("<I", entry[:4])[0]


def entry_version(entry):
    return struct.unpack("<I", entry[4:8])[0]


def load_version(entries):
    """The game skips entries newer than its data, so match the lowest version it already loads."""
    return min((entry_version(e) for e in entries), default=DEFAULT_VERSION)


def new_entry(name, number, version):
    return struct.pack("<II", number, version) + name.encode().ljust(32, b"\0") + struct.pack("<II", 0, 1)
