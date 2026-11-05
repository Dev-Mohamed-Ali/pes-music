import os
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

from pesmusic import installer
from pesmusic.errors import ModError
from pesmusic.formats import filelist
from pesmusic.formats.acb import commands
from pesmusic.formats.awb import Awb, read_awb, write_awb
from pesmusic.formats.utf import data_span, read_table, set_value, xor
from pesmusic.games import GAMES, Volume

SUFFIX_GAME = GAMES[1]


def table(rows):
    """Build a tiny @UTF table with columns Number (u32) and Blob (data)."""
    strings = b"<NULL>\0Number\0Blob\0"
    number_at, blob_at = strings.index(b"Number"), strings.index(b"Blob")
    columns = struct.pack(">BI", 0x54, number_at) + struct.pack(">BI", 0x5B, blob_at)
    rows_at = 24 + len(columns)
    data, packed = b"", b""
    for number, blob in rows:
        packed += struct.pack(">III", number, len(data), len(blob))
        data += blob
    strings_at = rows_at + len(packed)
    data_at = strings_at + len(strings)
    head = struct.pack(">IIIIHHI", rows_at, strings_at, data_at, 0, 2, 12, len(rows))
    body = head + columns + packed + strings + data
    return b"@UTF" + struct.pack(">I", len(body)) + body


class Tables(unittest.TestCase):
    def test_read(self):
        self.assertEqual(read_table(table([(7, b"abc")])), [{"Number": 7, "Blob": b"abc"}])

    def test_reads_encrypted_tables(self):
        self.assertEqual(read_table(xor(table([(7, b"abc")])))[0]["Number"], 7)

    def test_set_value_at_an_offset(self):
        buffer = bytearray(b"pad!" + table([(1, b""), (2, b"")]))
        set_value(buffer, 4, 1, "Number", 99)
        self.assertEqual(read_table(bytes(buffer[4:]))[1]["Number"], 99)

    def test_data_span(self):
        buffer = bytearray(b"pad!" + table([(1, b"xy"), (2, b"hello")]))
        start, size = data_span(buffer, 4, 1, "Blob")
        self.assertEqual(bytes(buffer[start:start + size]), b"hello")

    def test_unknown_data_is_refused(self):
        with self.assertRaises(ModError):
            read_table(b"not a table at all, just some bytes")

    def test_xor_reverses_itself(self):
        self.assertEqual(xor(xor(b"hello")), b"hello")


class Commands(unittest.TestCase):
    def test_walks_each_command(self):
        blob = bytes.fromhex("0057020032006d0101")
        self.assertEqual([(c, o) for c, o, _ in commands(blob)], [(0x57, 3), (0x6D, 8)])


class Banks(unittest.TestCase):
    def test_round_trip(self):
        header = b"AFS2\x02\x04\x02\x00" + struct.pack("<II", 2, 32)
        bank, _ = write_awb(header, Awb([0, 1], [b"a" * 40, b"b" * 7], 32, 16 + 4 + 12))
        awb = read_awb(bank)
        self.assertEqual((awb.ids, awb.entries), ([0, 1], [b"a" * 40, b"b" * 7]))


class FileList(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = folder.name
        self.path = os.path.join(folder.name, filelist.NAME)

    def test_round_trip(self):
        entries = [filelist.new_entry("a.cpk", 100, 10100), filelist.new_entry("b.cpk", 200, 10200)]
        filelist.write_list(self.path, 100, entries)
        self.assertEqual(os.path.getsize(self.path), filelist.FILE_SIZE)
        self.assertEqual(filelist.read_list(self.path), (100, entries))

    def test_unknown_files_are_refused(self):
        with open(self.path, "wb") as f:
            f.write(b"junk")
        with self.assertRaises(ModError):
            filelist.read_list(self.path)

    def test_bad_count_is_refused(self):
        with open(self.path, "wb") as f:
            f.write(struct.pack("<II", 100, 999).ljust(filelist.FILE_SIZE, b"\0"))
        with self.assertRaises(ModError):
            filelist.read_list(self.path)

    def test_load_version_is_the_lowest_in_the_list(self):
        entries = [filelist.new_entry("a.cpk", 300, 10500), filelist.new_entry("b.cpk", 100, 10200)]
        self.assertEqual(filelist.load_version(entries), 10200)

    def test_load_version_defaults_for_an_empty_list(self):
        self.assertEqual(filelist.load_version([]), filelist.DEFAULT_VERSION)

    def test_name_is_the_first_free_one(self):
        self.assertEqual(installer.pick_name(self.folder, [], SUFFIX_GAME), ("dt80_100E_win.cpk", 100))

    def test_name_steps_aside_for_listed_mods(self):
        entries = [filelist.new_entry("dt80_100E_win.cpk", 100, 10100)]
        self.assertEqual(installer.pick_name(self.folder, entries, SUFFIX_GAME), ("dt80_200E_win.cpk", 200))

    def test_name_steps_aside_for_unlisted_files(self):
        open(os.path.join(self.folder, "dt80_100E_win.cpk"), "wb").close()
        self.assertEqual(installer.pick_name(self.folder, [], SUFFIX_GAME)[1], 200)

    def test_a_name_is_found_when_every_hundred_is_taken(self):
        entries = [filelist.new_entry(f"dt80_{n}E_win.cpk", n, 10100) for n in range(100, 1000, 100)]
        self.assertEqual(installer.pick_name(self.folder, entries, SUFFIX_GAME)[1], 110)


class Recovery(unittest.TestCase):
    def test_tidy_restores_a_mod_left_as_prev(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("a.cpk.prev", "a.cpk.tmp", "other.tmp"):
                open(os.path.join(folder, name), "wb").close()
            installer.tidy(folder)
            self.assertEqual(sorted(os.listdir(folder)), ["a.cpk", "other.tmp"])


class Levels(unittest.TestCase):
    def test_lowest_level_is_about_the_stock_loudness(self):
        self.assertEqual(Volume(50, 30, 65).lowest_level, 24)

    def test_gain_at_full_level(self):
        self.assertAlmostEqual(Volume(50, 30, 65).gain_db(100), 12.7, places=1)

    def test_every_game_lists_a_unique_exe(self):
        self.assertEqual(len({g.exe for g in GAMES}), len(GAMES))


class FakeArchive:
    def __init__(self, _):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class Cancel(unittest.TestCase):
    def test_cancelled_install_stops_before_converting(self):
        cancel = threading.Event()
        cancel.set()
        slot = installer.Slot("c", "t", "a", 100, installer.NEW, "x.mp3", 0, 48000)
        with patch.object(installer, "Cpk", FakeArchive), patch.object(installer, "read_bank", lambda _: (None, None)):
            with self.assertRaises(ModError):
                installer.collect_tracks([slot], ".", None, lambda *_: None, cancel)
