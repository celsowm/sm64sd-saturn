"""NitroFS and NARC asset namespaces."""
from __future__ import annotations
import hashlib
from pathlib import Path
from .common import FormatError,field,region
from .compression import lz77

def fnt_names(fnt: bytes) -> dict[int, str]:
    """Nintendo FNT directory walker, shared by ROM and NARC."""
    if len(fnt) < 8:
        raise FormatError("missing FNT root directory")
    directory_count = field(fnt, 6, 'H')
    if not 1 <= directory_count <= 4096 or 8 * directory_count > len(fnt):
        raise FormatError("invalid FNT directory count")
    dirs = {}
    for i in range(directory_count):
        dirs[0xF000 + i] = field(fnt, i * 8, 'IHH')
    result: dict[int, str] = {}
    active: set[int] = set()

    def walk(directory: int, prefix: str):
        if directory not in dirs or directory in active:
            raise FormatError("unknown or cyclic FNT directory")
        active.add(directory)
        pos, file_id, _parent = dirs[directory]
        if pos >= len(fnt):
            raise FormatError("FNT directory offset outside table")
        for _ in range(len(fnt)):
            if pos >= len(fnt):
                raise FormatError("unterminated FNT directory")
            n = fnt[pos]
            pos += 1
            if n == 0:
                active.remove(directory)
                return
            size = n & 0x7f
            if size == 0:
                raise FormatError("empty FNT name")
            name = region(fnt, pos, size).decode('latin1')
            pos += size
            if n & 0x80:
                child = field(fnt, pos, 'H')
                pos += 2
                walk(child, prefix + name + '/')
            else:
                if file_id in result:
                    raise FormatError("duplicate FNT file ID")
                result[file_id] = prefix + name
                file_id += 1
        raise FormatError("unterminated FNT directory")

    walk(0xF000, '')
    return result


class Filesystem:
    def __init__(self, blob: bytes):
        if len(blob) < 0x60 or blob[12:16] != b'ASME' or blob[30] != 0:
            raise FormatError("only USA ASME revision 0 has been verified")
        fnt_off, fnt_len, fat_off, fat_len = field(blob, 0x40, 'IIII')
        if fat_len % 8:
            raise FormatError("invalid FAT length")
        self.blob = blob
        self.names = fnt_names(region(blob, fnt_off, fnt_len))
        self.by_name = {p: i for i, p in self.names.items()}
        if len(self.by_name) != len(self.names):
            raise FormatError("duplicate NitroFS path")
        self.fat = [field(blob, fat_off + 8 * i, 'II') for i in range(fat_len // 8)]
        for start, end in self.fat:
            if start > end or end > len(blob):
                raise FormatError("invalid FAT file bounds")
        self.sha256 = hashlib.sha256(blob).hexdigest()

    @classmethod
    def from_file(cls, path: Path):
        return cls(path.read_bytes())

    def read_id(self, file_id: int) -> bytes:
        if file_id < 0 or file_id >= len(self.fat):
            raise FormatError(f"NitroFS ID out of range: {file_id}")
        a, b = self.fat[file_id]
        return self.blob[a:b]

    def read(self, selector: str) -> bytes:
        """'NitroFS/path' or 'ARCHIVE/arc0.narc:131' or ':nested/path'."""
        outer, colon, inner = selector.partition(':')
        if outer not in self.by_name:
            raise FormatError(f"NitroFS path not found: {outer}")
        data = self.read_id(self.by_name[outer])
        if colon:
            archive = Narc(data)
            data = archive.read(int(inner) if inner.isdecimal() else inner)
        return lz77(data)


class Narc:
    def __init__(self, blob: bytes):
        if len(blob) < 16 or blob[:4] != b'NARC' or field(blob, 8, 'I') != len(blob):
            raise FormatError("invalid NARC header")
        self.blob = blob
        blocks = {}
        pos = field(blob, 12, 'H')  # NARC header length (0x10)
        count = field(blob, 14, 'H')
        if pos < 16 or not 2 <= count <= 8:
            raise FormatError("invalid NARC block count/header")
        for _ in range(count):
            tag = region(blob, pos, 4)
            size = field(blob, pos + 4, 'I')
            if size < 8 or tag in blocks:
                raise FormatError("invalid NARC block")
            blocks[tag] = (pos, size)
            region(blob, pos, size)
            pos += size
        if pos != len(blob) or not all(k in blocks for k in (b'BTAF', b'BTNF', b'GMIF')):
            raise FormatError("missing NARC section or trailing data")
        fat_off, fat_size = blocks[b'BTAF']
        self.count = field(blob, fat_off + 8, 'I')
        if self.count > 65535 or fat_size < 12 + self.count * 8:
            raise FormatError("invalid NARC FAT")
        self.items = [field(blob, fat_off + 12 + 8 * i, 'II') for i in range(self.count)]
        fnt_off, fnt_size = blocks[b'BTNF']
        self.names = fnt_names(region(blob, fnt_off + 8, fnt_size - 8))
        self.name_ids = {p: i for i, p in self.names.items()}
        dat_off, dat_size = blocks[b'GMIF']
        self.data = region(blob, dat_off + 8, dat_size - 8)
        for a, b in self.items:
            if a > b or b > len(self.data):
                raise FormatError("invalid NARC internal FAT")

    def read(self, entry: int | str) -> bytes:
        if isinstance(entry, str):
            if entry not in self.name_ids:
                raise FormatError(f"NARC path not found: {entry}")
            entry = self.name_ids[entry]
        if not 0 <= entry < self.count:
            raise FormatError("NARC ID outside FAT")
        a, b = self.items[entry]
        return self.data[a:b]


