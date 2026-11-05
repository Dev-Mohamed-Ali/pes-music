"""AFS2 (.awb) audio banks."""
import struct
from dataclasses import dataclass

from ..errors import ModError


@dataclass
class Awb:
    ids: list
    entries: list
    align: int
    head_size: int


def read_awb(data):
    if data[:4] != b"AFS2":
        raise ModError("Unexpected music bank format.")
    count, align = struct.unpack("<II", data[8:16])
    align &= 0xFFFF
    ids = list(struct.unpack(f"<{count}H", data[16:16 + 2 * count]))
    head_size = 16 + 2 * count + 4 * (count + 1)
    offsets = struct.unpack(f"<{count + 1}I", data[16 + 2 * count:head_size])
    entries = [data[(offsets[i] + align - 1) // align * align:offsets[i + 1]] for i in range(count)]
    return Awb(ids, entries, align, head_size)


def write_awb(original, awb):
    """Rebuild a bank from `awb`, reusing the fixed header of `original`. Returns (bank, its header)."""
    pos, offsets, body = awb.head_size, [awb.head_size], bytearray()
    for entry in awb.entries:
        start = (pos + awb.align - 1) // awb.align * awb.align
        body += b"\0" * (start - pos) + entry
        pos = start + len(entry)
        offsets.append(pos)
    count = len(awb.ids)
    head = original[:16] + struct.pack(f"<{count}H", *awb.ids) + struct.pack(f"<{count + 1}I", *offsets)
    return head + bytes(body), head
