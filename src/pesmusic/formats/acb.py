"""ACB cue sheets: which audio each cue plays, how loud, and for how long."""
import hashlib
import struct
from dataclasses import dataclass

from ..errors import ModError
from .awb import read_awb, write_awb
from .utf import data_span, read_table, set_value

SEQUENCE_CUE = 3
PLAY_EVENT, SYNTH_TARGET, WAVE_ITEM = 0x7D0, 2, 1
VOLUME = 0x57
NONE = 65535


@dataclass
class Track:
    data: bytes
    samples: int
    rate: int

    @property
    def seconds(self):
        return self.samples / self.rate


def commands(blob):
    """Yield (code, offset of the value, value bytes) for each command in a blob."""
    pos = 0
    while pos + 3 <= len(blob):
        code, size = struct.unpack(">HB", blob[pos:pos + 3])
        yield code, pos + 3, blob[pos + 3:pos + 3 + size]
        pos += 3 + size


class Bank:
    def __init__(self, acb):
        self.raw = acb
        self.root = read_table(acb)[0]
        self.cues = self._table("CueTable")
        self.waves = self._table("WaveformTable")
        self.sequences = self._table("SequenceTable")
        self.tracks = self._table("TrackTable")
        self.synths = self._table("SynthTable")
        self.events = self._table("TrackEventTable") or self._table("CommandTable")
        self.sequence_commands_name = "SeqCommandTable" if self.root.get("SeqCommandTable") else "CommandTable"
        self.sequence_commands = self._table(self.sequence_commands_name)
        self.cue_index = {row["CueName"]: row["CueIndex"] for row in self._table("CueNameTable")}

    def _table(self, name):
        blob = self.root.get(name)
        return read_table(blob) if blob else []

    def wave_row(self, cue):
        """Follow cue, sequence, track, play event and synth to the cue's one audio row."""
        found = self._waves(self.cues[self.cue_index[cue]])
        if len(found) != 1:
            raise ModError(f"Unexpected audio layout for {cue}.")
        return found[0]

    def _waves(self, cue):
        if cue["ReferenceType"] != SEQUENCE_CUE:
            return []
        sequence = self.sequences[cue["ReferenceIndex"]]
        indexes = struct.unpack(f">{len(sequence['TrackIndex']) // 2}H", sequence["TrackIndex"])
        waves = []
        for track in indexes[:sequence["NumTracks"]]:
            event = self.tracks[track]["EventIndex"]
            if event in (None, NONE):
                continue
            for code, _, value in commands(self.events[event]["Command"]):
                if code == PLAY_EVENT and struct.unpack(">H", value[:2])[0] == SYNTH_TARGET:
                    items = self.synths[struct.unpack(">H", value[2:4])[0]]["ReferenceItems"]
                    pairs = struct.unpack(f">{len(items) // 2}H", items)
                    waves += [pairs[i + 1] for i in range(0, len(pairs), 2) if pairs[i] == WAVE_ITEM]
        return waves

    def stream_id(self, wave_row):
        wave = self.waves[wave_row]
        return wave["StreamAwbId"] if wave.get("StreamAwbId") is not None else wave["Id"]

    def read_track(self, cue, awb):
        row = self.wave_row(cue)
        wave = self.waves[row]
        data = awb.entries[awb.ids.index(self.stream_id(row))]
        return Track(data, wave["NumSamples"], wave["SamplingRate"])

    def volume_rows(self, cues):
        """Rows of the sequence command table that hold a volume for these cues."""
        rows = {self.sequences[self.cues[self.cue_index[c]]["ReferenceIndex"]]["CommandIndex"] for c in cues}
        return sorted(r for r in rows if r != NONE and self._volume(r) is not None)

    def _volume(self, row):
        for code, _, value in commands(self.sequence_commands[row]["Command"]):
            if code == VOLUME:
                return struct.unpack(">H", value)[0]
        return None

    def level(self, cues):
        rows = self.volume_rows(cues)
        return self._volume(rows[0]) if rows else None


def rebuild(acb0, awb0, tracks, cues, level):
    """Swap `tracks` ({cue: Track}) into a bank. Set `level` on `cues` unless it is None."""
    bank = Bank(acb0)
    awb = read_awb(awb0)
    acb = bytearray(acb0)
    cue_at, wave_at = acb0.find(bank.root["CueTable"]), acb0.find(bank.root["WaveformTable"])
    for cue, track in tracks.items():
        row = bank.wave_row(cue)
        awb.entries[awb.ids.index(bank.stream_id(row))] = track.data
        set_value(acb, wave_at, row, "NumSamples", track.samples)
        set_value(acb, cue_at, bank.cue_index[cue], "Length", track.samples * 1000 // track.rate)
        if bank.waves[row]["SamplingRate"] != track.rate:
            set_value(acb, wave_at, row, "SamplingRate", track.rate)
    new_awb, head = write_awb(awb0, awb)

    # the .acb keeps a copy of the AWB header and its MD5
    old_head = awb0[:awb.head_size]
    if acb0.count(old_head) != 1:
        raise ModError("Unexpected music bank layout.")
    at = acb.find(old_head)
    acb[at:at + awb.head_size] = head
    old_md5 = hashlib.md5(awb0).digest()
    if old_md5 not in acb0:
        raise ModError("Unexpected music bank hash.")
    acb = bytearray(bytes(acb).replace(old_md5, hashlib.md5(new_awb).digest()))

    if level is not None:
        base = acb0.find(bank.root[bank.sequence_commands_name])
        for row in bank.volume_rows(cues):
            start, size = data_span(acb, base, row, "Command")
            for code, offset, _ in commands(bytes(acb[start:start + size])):
                if code == VOLUME:
                    struct.pack_into(">H", acb, start + offset, level)
    return bytes(acb), new_awb


def bank_matches_audio(acb, awb):
    return hashlib.md5(awb).digest() in acb
