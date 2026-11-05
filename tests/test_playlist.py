import unittest

from pesmusic import playlist
from pesmusic.games import GAMES

PES_2017 = next(g for g in GAMES if g.edition == 17)
XML = """<Playlist wepes="17">
<CueList Num="2">
<Label CueName="A" Id="1" Title="One &amp; Two" Artist="X" Offset="5" RemainTimeForFadeoutStart="1"/>
<Label CueName="B" Id="2" Title="Two" Artist="Y" Offset="6" RemainTimeForFadeoutStart="1"/>
<Label CueName="C" Id="3" Title="Three" Artist="Z" Offset="7" RemainTimeForFadeoutStart="1"/>
</CueList>
<DefaultPlayList Num="1"><List ListName="Menu" NumContents="2"><Label Id="2"/><Label Id="1"/></List></DefaultPlayList>
</Playlist>"""


class Names(unittest.TestCase):
    def test_fit_caps_bytes_and_escaped_bytes(self):
        self.assertLessEqual(len(playlist.fit("x" * 90, (25, 29)).encode()), 25)
        self.assertLessEqual(len(playlist.esc(playlist.fit("a&" * 20, (25, 29))).encode()), 29)

    def test_fit_keeps_multibyte_characters_whole(self):
        playlist.fit("رقم" * 20, (25, 29)).encode().decode()

    def test_clean_name_strips_latin_accents_and_control_characters(self):
        self.assertEqual(playlist.clean_name("Sān\x07-Z"), "San-Z")

    def test_clean_name_leaves_other_scripts_alone(self):
        self.assertEqual(playlist.clean_name("골든 ガンダム رقم 1"), "골든 ガンダム رقم 1")

    def test_names_from_file(self):
        self.assertEqual(playlist.names_from_file(r"C:\m\Some Artist - Some Title.mp3", PES_2017),
                         ("Some Artist", "Some Title"))

    def test_names_fall_back_when_nothing_is_left(self):
        self.assertEqual(playlist.names_from_file("&&& - ,,,.mp3", PES_2017), ("Unknown", "Track"))

    def test_no_separator(self):
        self.assertEqual(playlist.names_from_file("song.mp3", PES_2017), ("Unknown", "song"))


class Highlights(unittest.TestCase):
    def test_short_song_stays_inside_the_track(self):
        self.assertLess(playlist.highlight_start(30), 30000)

    def test_long_song_is_capped(self):
        self.assertEqual(playlist.highlight_start(300), 60000)


class PlaylistFile(unittest.TestCase):
    def test_menu_cues_come_from_the_menu_list_in_order(self):
        self.assertEqual(playlist.menu_cues(XML), ["B", "A"])

    def test_read_names_unescapes(self):
        self.assertEqual(playlist.read_names(XML)["A"], ("One & Two", "X", 5))

    def test_edition(self):
        self.assertEqual(playlist.edition(XML), 17)

    def test_write_names_escapes_and_keeps_other_attributes(self):
        class Slot:
            cue, title, artist, offset = "B", 'A "B" & C', "Me", 9

        written = playlist.write_names(XML, [Slot])
        self.assertIn('Title="A &quot;B&quot; &amp; C" Artist="Me" Offset="9" RemainTimeForFadeoutStart="1"', written)
        self.assertIn('Title="Three"', written)
