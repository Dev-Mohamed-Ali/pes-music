"""CRI CPK archives."""
import struct

from ..errors import ModError
from .utf import plain, read_table, set_value, xor


class Cpk:
    def __init__(self, path):
        self.file = open(path, "rb")
        try:
            head = self.file.read(16)
            if head[:4] != b"CPK ":
                raise ModError(f"Not a game archive: {path}")
            self.head_size = struct.unpack("<Q", head[8:16])[0]
            self.head = self.file.read(self.head_size)
            self.info = read_table(self.head)[0]
            self.toc_at = self.info["TocOffset"]
            self.file.seek(self.toc_at)
            toc = self.file.read(16)
            if toc[:4] != b"TOC ":
                raise ModError(f"Archive has no readable file list: {path}")
            self.toc_size = struct.unpack("<Q", toc[8:16])[0]
            self.toc = self.file.read(self.toc_size)
            self.rows = read_table(self.toc)
        except Exception:
            self.file.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.file.close()

    def names(self):
        return {row["FileName"] for row in self.rows}

    def read(self, name):
        for row in self.rows:
            if row["FileName"] == name:
                self.file.seek(self.toc_at + row["FileOffset"])
                return self.file.read(row["FileSize"])
        raise ModError(f"{name} not found in the game data.")

    def write_partial(self, files, path):
        """Write a new archive holding only `files` ({name: bytes}), keeping this archive's folders."""
        head, toc = bytearray(plain(self.head)), bytearray(plain(self.toc))
        rows_at = (struct.unpack(">I", toc[8:12])[0] & 0xFFFF) + 8
        row_size = struct.unpack(">H", toc[26:28])[0]
        keep = [i for i, row in enumerate(self.rows) if row["FileName"] in files]
        if len(keep) != len(files):
            raise ModError("A music file is missing from the game data.")

        kept = b"".join(bytes(toc[rows_at + i * row_size:rows_at + (i + 1) * row_size]) for i in keep)
        toc[rows_at:rows_at + len(self.rows) * row_size] = kept.ljust(len(self.rows) * row_size, b"\0")
        struct.pack_into(">I", toc, 28, len(keep))

        content_at, align = self.info["ContentOffset"], self.info["Align"]
        self.file.seek(0)
        prefix = bytearray(self.file.read(content_at))
        total = 0
        with open(path, "wb") as out:
            out.write(b"\0" * content_at)
            pos = content_at
            for slot, i in enumerate(keep):
                data = files[self.rows[i]["FileName"]]
                start = (pos + align - 1) // align * align
                out.write(b"\0" * (start - pos))
                out.write(data)
                pos = start + len(data)
                total += len(data)
                set_value(toc, 0, slot, "FileOffset", start - self.toc_at)
                set_value(toc, 0, slot, "FileSize", len(data))
                set_value(toc, 0, slot, "ExtractSize", len(data))
            set_value(head, 0, 0, "ContentSize", (pos - content_at + align - 1) // align * align)
            # Konami's archives store twice the data size in these two fields
            set_value(head, 0, 0, "EnabledPackedSize", 2 * total)
            set_value(head, 0, 0, "EnabledDataSize", 2 * total)
            set_value(head, 0, 0, "Files", len(keep))
            prefix[16:16 + self.head_size] = xor(bytes(head)) if self.head[:4] != b"@UTF" else bytes(head)
            at = self.toc_at + 16
            prefix[at:at + self.toc_size] = xor(bytes(toc)) if self.toc[:4] != b"@UTF" else bytes(toc)
            out.seek(0)
            out.write(prefix)
