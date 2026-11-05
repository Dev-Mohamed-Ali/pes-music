"""CRI @UTF tables, the row/column format inside CPK and ACB files."""
import struct

from ..errors import ModError

FORMATS = {0: ">B", 1: ">b", 2: ">H", 3: ">h", 4: ">I", 5: ">i", 6: ">Q", 7: ">q", 8: ">f", 9: ">d"}
SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 4, 9: 8, 0xA: 4, 0xB: 8}
STRING, DATA = 0xA, 0xB
PER_ROW, CONSTANT = 0x50, 0x30


def xor(data):
    key, out = 0x655F, bytearray(len(data))
    for i, byte in enumerate(data):
        out[i] = byte ^ (key & 255)
        key = (key * 0x4115) & 0xFFFFFFFF
    return bytes(out)


def plain(data):
    return data if data[:4] == b"@UTF" else xor(data)


def _layout(table):
    rows_at, strings_at, data_at, _, columns, row_size, rows = struct.unpack(">IIIIHHI", table[8:32])
    # the top half of rows_at holds a version in newer tables
    return (rows_at & 0xFFFF) + 8, strings_at + 8, data_at + 8, columns, row_size, rows


def _text(table, at):
    return table[at:table.index(0, at)].decode("utf8", "replace")


def _columns(table):
    """Yield (name, storage, kind, position of a constant value)."""
    _, strings_at, _, columns, _, _ = _layout(table)
    pos = 32
    for _ in range(columns):
        flags = table[pos]
        name = _text(table, strings_at + struct.unpack(">I", table[pos + 1:pos + 5])[0])
        pos += 5
        storage, kind = flags & 0xF0, flags & 0x0F
        yield name, storage, kind, pos
        if storage == CONSTANT:
            pos += SIZES[kind]


def read_table(data):
    table = plain(data)
    if table[:4] != b"@UTF":
        raise ModError("Unexpected file format in the game data.")
    rows_at, strings_at, data_at, _, row_size, rows = _layout(table)

    def value(kind, pos):
        if kind == STRING:
            return _text(table, strings_at + struct.unpack(">I", table[pos:pos + 4])[0])
        if kind == DATA:
            offset, size = struct.unpack(">II", table[pos:pos + 8])
            return table[data_at + offset:data_at + offset + size]
        return struct.unpack(FORMATS[kind], table[pos:pos + SIZES[kind]])[0]

    columns = list(_columns(table))
    result = []
    for index in range(rows):
        pos, row = rows_at + index * row_size, {}
        for name, storage, kind, const_at in columns:
            if storage == PER_ROW:
                row[name] = value(kind, pos)
                pos += SIZES[kind]
            else:
                row[name] = value(kind, const_at) if storage == CONSTANT else None
        result.append(row)
    return result


def _cell(table, row, name):
    rows_at, _, _, _, row_size, _ = _layout(table)
    offset = 0
    for column, storage, kind, _ in _columns(table):
        if storage != PER_ROW:
            continue
        if column == name:
            return rows_at + row * row_size + offset, kind
        offset += SIZES[kind]
    raise ModError(f"Column {name} not found in the game data.")


def set_value(buffer, base, row, name, value):
    """Overwrite one per-row number in the table held at buffer[base:]."""
    pos, kind = _cell(bytes(buffer[base:]), row, name)
    struct.pack_into(FORMATS[kind], buffer, base + pos, value)


def data_span(buffer, base, row, name):
    """Return (absolute offset, size) of one data cell in the table at buffer[base:]."""
    table = bytes(buffer[base:])
    pos, _ = _cell(table, row, name)
    offset, size = struct.unpack(">II", table[pos:pos + 8])
    return base + _layout(table)[2] + offset, size
