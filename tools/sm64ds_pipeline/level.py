"""Generic SM64DS level reader: stage files -> overlay -> every object list.

Layout from the decomp's include/LVL_Overlay.h. The overlay record is found
by searching the stage's overlay for its (model, KCL) NitroFS file-ID pair.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import struct
from .common import FormatError
from .filesystem import Filesystem
from .level_objects import blz_decompress, read_arm9_overlay

# Category index -> (name, record size or 0 when the layout is not decoded).
# Order is the sObjectLoaders table at ov002:0x0210cbb8.
CATEGORIES = {
    0: ('standard', 16), 1: ('entrance', 16), 2: ('path_node', 0),
    3: ('path', 0), 4: ('view', 0), 5: ('simple', 8),
    6: ('teleport_source', 8), 7: ('teleport_dest', 0), 8: ('fog', 0),
    9: ('door', 12), 10: ('exit', 14), 11: ('minimap_tile', 0),
    12: ('minimap_scale', 0), 13: ('unused13', 0), 14: ('star_camera', 0),
}
OVERLAY_TABLE_FIRST_STAGE_OVERLAY = 8


@dataclass
class ObjList:
    category: int
    star: int          # 0 = always, 1..7 = only for that star
    count: int
    records: list      # tuples (decoded) or bytes (raw, size unknown)
    raw_offset: int    # overlay offset of the entries array

    @property
    def name(self) -> str:
        return CATEGORIES.get(self.category, (f'category{self.category}', 0))[0]


@dataclass
class Level:
    overlay_id: int
    stage: str
    model_file_id: int
    kcl_file_id: int
    area_count: int
    minimap_ids: list
    skybox_id: int                           # 0 = none; 1..10 index the sky table
    level_lists: list                        # area -1
    area_lists: list = field(default_factory=list)   # [area] -> list[ObjList]

    @property
    def sublevel(self) -> int:
        """DS sublevel (level) id: level overlays are overlay 8 + sublevel."""
        return self.overlay_id - OVERLAY_TABLE_FIRST_STAGE_OVERLAY

    def lists(self, category: int, area: int | None = None):
        src = self.level_lists if area is None else self.area_lists[area]
        return [l for l in src if l.category == category]


def asset_handles(fs: Filesystem) -> dict[str, int]:
    """Path -> overlay-0 asset handle, from the pointer table in overlay 0.

    Level records name their model and KCL by handle, not by NitroFS ID. The
    table is the one run of pointers to path strings; index = handle.
    """
    ov_off, _ = struct.unpack_from('<II', fs.blob, 0x50)
    _id, ram, _size, _bss, _a, _b, fid, flags = struct.unpack_from('<8I', fs.blob, ov_off)
    raw = fs.read_id(fid)
    d = blz_decompress(raw) if flags & 0x01000000 else raw

    def is_path(o):
        v = struct.unpack_from('<I', d, o)[0] - ram
        return 0 < v < len(d) - 4 and d[v - 1] == 0 and d[v:v + 5] == b'data/' or \
            0 < v < len(d) - 4 and d[v - 1] == 0 and d[v] != 0

    anchor = d.find(struct.pack('<I', ram + d.find(b'data/stage/castle_1f/castle_1f.kcl\0')))
    if anchor < 0:
        raise FormatError('asset handle table not found')
    start = anchor
    while start >= 4 and is_path(start - 4):
        start -= 4
    end = anchor
    while end + 8 <= len(d) and is_path(end + 4):
        end += 4
    # castle_1f.kcl is handle 0x600; the table index must agree.
    if (anchor - start) // 4 != 0x600:
        raise FormatError('asset handle table misaligned')
    out = {}
    for i in range((end - start) // 4 + 1):
        o = struct.unpack_from('<I', d, start + 4 * i)[0] - ram
        out[d[o:d.index(b'\0', o)].decode('latin1')] = i
    return out


def stage_overlay(fs: Filesystem, stage: str) -> int:
    """Find the level overlay whose record names this stage's model and KCL."""
    marker = _marker(fs, stage)
    ov_off, ov_size = struct.unpack_from('<II', fs.blob, 0x50)
    for i in range(ov_size // 32):
        ov_id = struct.unpack_from('<I', fs.blob, ov_off + i * 32)[0]
        if ov_id < OVERLAY_TABLE_FIRST_STAGE_OVERLAY:
            continue
        try:
            _, data = read_arm9_overlay(fs, ov_id)
        except FormatError:
            continue
        if data.find(marker) >= 8:
            return ov_id
    raise FormatError(f'no level overlay for stage {stage}')


def _marker(fs: Filesystem, stage: str) -> bytes:
    h = asset_handles(fs)
    return struct.pack('<HH', h[f'data/stage/{stage}/{stage}_all.bmd'],
                       h[f'data/stage/{stage}/{stage}.kcl'])


def _off(ptr: int, ram: int, size: int) -> int:
    o = ptr - ram
    if not 0 <= o < size:
        raise FormatError(f'pointer 0x{ptr:08x} outside overlay')
    return o


def _obj_table(data: bytes, ram: int, ptr: int) -> list[ObjList]:
    if not (ram <= ptr < ram + len(data)):
        return []
    off = ptr - ram
    count, = struct.unpack_from('<H', data, off)
    arr = _off(struct.unpack_from('<I', data, off + 4)[0], ram, len(data))
    out = []
    for i in range(count):
        tag, n, _p, eptr = struct.unpack_from('<BBHI', data, arr + 8 * i)
        cat, star = tag & 0x1F, tag >> 5
        size = CATEGORIES.get(cat, ('', 0))[1]
        eoff = _off(eptr, ram, len(data)) if eptr else 0
        recs = []
        if size and eoff:
            if eoff + n * size > len(data):
                raise FormatError(f'category {cat} array exceeds overlay')
            fmt = {0: '<HhhhhhhH', 1: '<HhhhhhhH', 5: '<Hhhh', 6: '<hhhH',
                   9: '<hhhhHH', 10: '<hhhhh4B'}[cat]
            recs = list(struct.iter_unpack(fmt, data[eoff:eoff + n * size]))
        out.append(ObjList(cat, star, n, recs, eoff))
    return out


def read_level(fs: Filesystem, stage: str) -> Level:
    ov = stage_overlay(fs, stage)
    ram, data = read_arm9_overlay(fs, ov)
    marker = _marker(fs, stage)
    model, kcl = struct.unpack('<HH', marker)
    rec = data.find(marker) - 8
    objtab, = struct.unpack_from('<I', data, rec + 4)
    areas_ptr, = struct.unpack_from('<I', data, rec + 0x10)
    n_areas = data[rec + 0x14]
    sky = (struct.unpack_from('<I', data, rec + 0x18)[0] >> 4) & 0x1F
    lv = Level(ov, stage, model, kcl, n_areas, [], sky, _obj_table(data, ram, objtab))
    if n_areas:
        a = _off(areas_ptr, ram, len(data))
        for i in range(n_areas):
            tab, _bta = struct.unpack_from('<II', data, a + 12 * i)
            lv.minimap_ids.append(struct.unpack_from('<b', data, a + 12 * i + 8)[0])
            lv.area_lists.append(_obj_table(data, ram, tab))
    return lv


OBJ_TREE, OBJ_TATEFUDA = 41, 76


def level_props(fs: Filesystem, stage: str, star: int = 1):
    """(trees, signs) placements, DS units scaled to Saturn units.

    Lists filtered to another star are skipped, as LoadObjects does.
    """
    from .level_objects import DS_TO_SATURN_SCALE as k, LevelProp
    lv = read_level(fs, stage)
    trees, signs = [], []
    for lists in [lv.level_lists] + lv.area_lists:
        for lst in lists:
            if lst.star not in (0, star):
                continue
            if lst.category == 5:
                for idp, x, y, z in lst.records:
                    if idp & 0x1FF == OBJ_TREE:
                        trees.append(LevelProp(OBJ_TREE, (x * k, y * k, z * k), 0, idp >> 9))
            elif lst.category == 0:
                for oid, x, y, z, _rx, ry, _rz, param in lst.records:
                    if oid == OBJ_TATEFUDA:
                        signs.append(LevelProp(OBJ_TATEFUDA, (x * k, y * k, z * k),
                                               round(ry * 360 / 65536) % 360, param))
    return trees, signs


def actor_placements(fs: Filesystem, stage: str, wanted, star: int = 1):
    """{key: [(x, y, z, yaw_deg)]} in Saturn units. `wanted` maps a key to
    (actor name, exact star filter or 0 for the usual star 0 + selected star);
    a plain iterable of names means (name, 0)."""
    from .actors import actor_names, obj_to_actor_table
    from .level_objects import DS_TO_SATURN_SCALE as k
    table, names = obj_to_actor_table(fs), actor_names()
    lv = read_level(fs, stage)
    spec = wanted if isinstance(wanted, dict) else {w: (w, 0) for w in wanted}
    out = {w: [] for w in spec}
    for lists in [lv.level_lists] + lv.area_lists:
        for lst in lists:
            if lst.star not in (0, star) or lst.category not in (0, 5):
                continue
            for rec in lst.records:
                if lst.category == 5:
                    oid, (x, y, z), yaw = rec[0] & 0x1FF, rec[1:4], 0
                else:
                    oid, (x, y, z), yaw = rec[0], rec[1:4], round(rec[5] * 360 / 65536) % 360
                name = names.get(table[oid]) if oid < len(table) else None
                for key, (actor, only) in spec.items():
                    if name == actor and (not only or lst.star == only):
                        out[key].append((x * k, y * k, z * k, yaw))
    return out
