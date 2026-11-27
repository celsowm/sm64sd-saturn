"""SM64DS ARM9 level overlay decompression and static prop object extraction."""
from __future__ import annotations
from dataclasses import dataclass
import struct
from .common import FormatError
from .filesystem import Filesystem

DS_TO_SATURN_SCALE = 0.064
OBJ_ID_PAINTING = 42
OBJ_ID_TATEFUDA = 76
OBJ_ID_KINOPIO = 80
OBJ_ID_BOWSER_PAINTING = 275
CASTLE_GROUNDS_OVERLAY_ID = 9
CASTLE_1F_OVERLAY_ID = 10


@dataclass(frozen=True)
class LevelProp:
    object_id: int
    position: tuple[float, float, float]
    yaw_deg: int = 0
    param: int = 0


@dataclass(frozen=True)
class DoorPlacement:
    position: tuple[float, float, float]
    yaw_deg: int
    in_area: int
    out_area: int
    door_type: int
    is_level_exit: bool


@dataclass(frozen=True)
class PaintingPlacement:
    model_path: str
    position: tuple[float, float, float]
    yaw_deg: int
    width: float
    height: float
    room: int
    centered_y: bool = False
    # Picture-gate param word: bits 0-3 width, 4-7 height, 8-12 picture id,
    # 13-14 state row. State 0 is the proximity ripple mesh.
    param: int = 0
    state: int = 0


@dataclass(frozen=True)
class Castle1fObjects:
    doors: list[DoorPlacement]
    paintings: list[PaintingPlacement]
    toads: list[LevelProp]
    toad_rooms: list[int]


def blz_decompress(data: bytes) -> bytes:
    """Decompress Nintendo DS backwards LZ77 (BLZ) ARM9 overlay data."""
    if len(data) < 8:
        raise FormatError("truncated BLZ stream")
    inc_len = struct.unpack_from("<I", data, len(data) - 4)[0]
    hdr_and_top = struct.unpack_from("<I", data, len(data) - 8)[0]
    hdr_len = hdr_and_top >> 24
    top_off = hdr_and_top & 0xFFFFFF
    if hdr_len < 8 or top_off > len(data) or inc_len > 8 * 1024 * 1024:
        raise FormatError("invalid BLZ footer")
    out = bytearray(len(data) + inc_len)
    out[:len(data)] = data
    src = len(data) - hdr_len
    dst = len(out)
    stop = len(data) - top_off
    while src > stop:
        src -= 1
        flags = data[src]
        for _ in range(8):
            if src <= stop:
                break
            if flags & 0x80:
                if src < 2:
                    raise FormatError("truncated BLZ backreference")
                src -= 2
                val = (data[src + 1] << 8) | data[src]
                length = ((val >> 12) & 0xF) + 3
                disp = (val & 0xFFF) + 3
                if dst < length or dst - 1 + disp >= len(out):
                    raise FormatError("BLZ backreference out of range")
                for _ in range(length):
                    dst -= 1
                    out[dst] = out[dst + disp]
            else:
                if src < 1 or dst < 1:
                    raise FormatError("truncated BLZ literal")
                src -= 1
                dst -= 1
                out[dst] = data[src]
            flags = (flags << 1) & 0xFF
    return bytes(out)


def read_arm9_overlay(fs: Filesystem, overlay_id: int) -> tuple[int, bytes]:
    """Read and decompress an ARM9 overlay from the NDS ROM."""
    ov_off, ov_size = struct.unpack_from("<II", fs.blob, 0x50)
    if ov_size % 32 != 0 or ov_off + ov_size > len(fs.blob):
        raise FormatError("invalid ARM9 overlay table")
    count = ov_size // 32
    for i in range(count):
        ov_id, ram_addr, ram_size, _bss, _si0, _si1, fid, flags = struct.unpack_from(
            "<8I", fs.blob, ov_off + i * 32
        )
        if ov_id != overlay_id:
            continue
        raw = fs.read_id(fid)
        data = blz_decompress(raw) if (flags & 0x01000000) else raw
        if len(data) < ram_size:
            raise FormatError(f"overlay {overlay_id} shorter than declared RAM size")
        return ram_addr, data[:ram_size]
    raise FormatError(f"ARM9 overlay {overlay_id} not found")


def _ptr_to_off(ptr: int, ram_addr: int, size: int) -> int:
    off = ptr - ram_addr
    if not 0 <= off < size:
        raise FormatError(f"overlay pointer 0x{ptr:08x} outside overlay")
    return off


CASTLE_1F_PIC_GATE_OVERLAY_ID = 80
RIPPLE_WAVE_ROWS = 12
RIPPLE_WAVE_ROW_BYTES = 20


def castle_1f_wave_table(fs: Filesystem) -> tuple[tuple[int, int, int, int, int], ...]:
    """Read the picture-gate WaveParams table from overlay 80.

    Twelve rows of five 32-bit words: amplitude, phase step, wavelength,
    radius and duration. Rows 0-5 are the front wave and 6-11 the back wave;
    each half shares its phase step and duration. The table is found
    structurally (constant amplitude/wavelength, two phase/duration halves)
    rather than by a build-space address, so a ROM revision cannot silently
    point the wave at unrelated data.
    """
    _ram, data = read_arm9_overlay(fs, CASTLE_1F_PIC_GATE_OVERLAY_ID)
    table_bytes = RIPPLE_WAVE_ROWS * RIPPLE_WAVE_ROW_BYTES
    matches: list[tuple[tuple[int, int, int, int, int], ...]] = []
    for off in range(0, len(data) - table_bytes + 1, 4):
        rows = tuple(
            struct.unpack_from("<5i", data, off + r * RIPPLE_WAVE_ROW_BYTES)
            for r in range(RIPPLE_WAVE_ROWS)
        )
        if _plausible_wave_rows(rows):
            matches.append(rows)
    if len(matches) != 1:
        raise FormatError(f"expected one picture-gate wave table, found {len(matches)}")
    return matches[0]


def _plausible_wave_rows(rows) -> bool:
    if len({r[0] for r in rows}) != 1 or len({r[2] for r in rows}) != 1:
        return False
    if not (0 < rows[0][0] < 1 << 20 and 0 < rows[0][2] < 1 << 24):
        return False
    front, back = rows[:6], rows[6:]
    for half in (front, back):
        if len({r[1] for r in half}) != 1 or len({r[4] for r in half}) != 1:
            return False
        if not (0 < half[0][1] < 65536 and 0 < half[0][4] < 1000):
            return False
    if front[0][1] == back[0][1]:
        return False
    return all(0 < r[3] < 1 << 28 for r in rows)


# Painting param high-byte -> NitroFS model path for Castle 1F course paintings.
CASTLE_1F_PAINTING_MODELS = {
    0: "data/picture/for_bh.bmd",  # Bob-omb Battlefield (r1)
    1: "data/picture/for_bk.bmd",  # Whomp's Fortress (r5)
    2: "data/picture/for_ki.bmd",  # Jolly Roger Bay (r7)
    3: "data/picture/for_sm.bmd",  # Cool, Cool Mountain (r3)
}


def extract_castle_1f_objects(fs: Filesystem) -> Castle1fObjects:
    """Extract Peach's Castle 1F doors, course paintings, and Toads from overlay 10."""
    ram_addr, data = read_arm9_overlay(fs, CASTLE_1F_OVERLAY_ID)
    # Locate the LevelOverlay header via castle_1f BMD/KCL ov0 file IDs (0x0608, 0x0600).
    marker = struct.pack("<HH", 0x0608, 0x0600)
    hdr_off = data.find(marker)
    if hdr_off < 0x10:
        raise FormatError("castle_1f LevelOverlay header not found in overlay 10")
    base = hdr_off - 0x10
    global_bank_ptr = struct.unpack_from("<I", data, base + 0x0C)[0]
    area_ptr = struct.unpack_from("<I", data, base + 0x18)[0]
    area_cnt = data[base + 0x1C]
    if area_cnt != 8:
        raise FormatError(f"unexpected castle_1f area count: {area_cnt}")

    doors: list[DoorPlacement] = []
    gb_off = _ptr_to_off(global_bank_ptr, ram_addr, len(data))
    gb_count, gb_list_ptr = struct.unpack_from("<II", data, gb_off)
    gb_list_off = _ptr_to_off(gb_list_ptr, ram_addr, len(data))
    for i in range(gb_count):
        tag_type, obj_count, _pad, arr_ptr = struct.unpack_from("<BBHI", data, gb_list_off + i * 8)
        if (tag_type & 0x1F) != 9:  # Door/portal list (12 bytes each)
            continue
        arr_off = _ptr_to_off(arr_ptr, ram_addr, len(data))
        if arr_off + obj_count * 12 > len(data):
            raise FormatError("castle_1f door array exceeds overlay bounds")
        for j in range(obj_count):
            x, y, z, ry, p1, p2 = struct.unpack_from("<hhhhHH", data, arr_off + j * 12)
            in_area = (p1 >> 12) & 0xF
            out_area = (p1 >> 8) & 0xF
            yaw = round(ry * 360.0 / 65536.0) % 360
            pos = (x * DS_TO_SATURN_SCALE, y * DS_TO_SATURN_SCALE, z * DS_TO_SATURN_SCALE)
            # Door types 1 (front), 6 (basement), 7 (upstairs 2F), and courtyard exit (z < -300)
            # are level-boundary exits rather than open internal room archways.
            is_exit = (p2 in (1, 6, 7)) or (pos[2] < -300.0)
            doors.append(DoorPlacement(
                position=pos,
                yaw_deg=yaw,
                in_area=in_area,
                out_area=out_area,
                door_type=p2,
                is_level_exit=is_exit,
            ))

    paintings: list[PaintingPlacement] = []
    toads: list[LevelProp] = []
    toad_rooms: list[int] = []
    area_off = _ptr_to_off(area_ptr, ram_addr, len(data))
    for room in range(area_cnt):
        bank_ptr = struct.unpack_from("<I", data, area_off + room * 12)[0]
        if not (ram_addr <= bank_ptr < ram_addr + len(data)):
            continue
        bank_off = bank_ptr - ram_addr
        list_count, list_ptr = struct.unpack_from("<II", data, bank_off)
        if not 1 <= list_count <= 32:
            continue
        list_off = _ptr_to_off(list_ptr, ram_addr, len(data))
        for i in range(list_count):
            tag_type, obj_count, _pad, arr_ptr = struct.unpack_from("<BBHI", data, list_off + i * 8)
            if (tag_type & 0x1F) != 0:  # Standard objects (16 bytes each)
                continue
            arr_off = _ptr_to_off(arr_ptr, ram_addr, len(data))
            if arr_off + obj_count * 16 > len(data):
                raise FormatError("castle_1f standard object array exceeds overlay bounds")
            for j in range(obj_count):
                oid, x, y, z, _rx, ry, _rz, param = struct.unpack_from("<HhhhhhhH", data, arr_off + j * 16)
                pos = (x * DS_TO_SATURN_SCALE, y * DS_TO_SATURN_SCALE, z * DS_TO_SATURN_SCALE)
                yaw = round(ry * 360.0 / 65536.0) % 360
                if oid == OBJ_ID_PAINTING:
                    course_idx = (param >> 8) & 0xF
                    model_path = CASTLE_1F_PAINTING_MODELS.get(course_idx)
                    if model_path is not None:
                        w_units = (((param >> 4) & 0xF) + 1) * 100.0 * DS_TO_SATURN_SCALE
                        h_units = ((param & 0xF) + 1) * 100.0 * DS_TO_SATURN_SCALE
                        paintings.append(PaintingPlacement(
                            model_path=model_path,
                            position=pos,
                            yaw_deg=yaw,
                            width=w_units,
                            height=h_units,
                            room=room,
                            param=param,
                            state=(param >> 13) & 3,
                        ))
                elif oid == OBJ_ID_BOWSER_PAINTING:
                    paintings.append(PaintingPlacement(
                        model_path="data/special_obj/c1_peach/c1_peach.bmd",
                        position=pos,
                        yaw_deg=yaw,
                        width=37.5,
                        height=37.5,
                        room=room,
                        centered_y=True,
                        state=3,
                    ))
                elif oid == OBJ_ID_KINOPIO:
                    toads.append(LevelProp(
                        object_id=oid,
                        position=pos,
                        yaw_deg=yaw,
                        param=param,
                    ))
                    toad_rooms.append(room)

    return Castle1fObjects(doors=doors, paintings=paintings, toads=toads, toad_rooms=toad_rooms)


def extract_clps_masks(fs: Filesystem, overlay_id: int) -> tuple[int, int]:
    """Return (slippery, water) bitmasks of CLPS attribute indices (<32).

    SM64DS level overlays embed small 1-entry helper CLPS blocks for objects before
    the stage's main multi-entry CLPS table. Select the largest valid 8-byte-entry
    CLPS chunk in the overlay, then extract every index whose traction is 3
    (unclimbable/slippery) or whose word0 carries the water bit (0x20).
    """
    _ram_addr, data = read_arm9_overlay(fs, overlay_id)
    best_off = -1
    best_count = 0
    pos = 0
    while True:
        idx = data.find(b"CLPS", pos)
        if idx < 0:
            break
        pos = idx + 4
        if idx + 8 > len(data):
            continue
        entry_sz, count = struct.unpack_from("<HH", data, idx + 4)
        if entry_sz == 8 and count > best_count and idx + 8 + count * 8 <= len(data):
            best_off = idx + 8
            best_count = count
    if best_off < 0:
        raise FormatError(f"CLPS table not found in ARM9 overlay {overlay_id}")
    slippery = water = 0
    for i in range(min(best_count, 32)):
        lo = struct.unpack_from("<I", data, best_off + i * 8)[0]
        if ((lo >> 12) & 0x7) == 3:
            slippery |= 1 << i
        if lo & 0x20:
            water |= 1 << i
    return slippery, water


def extract_clps_slippery_mask(fs: Filesystem, overlay_id: int) -> int:
    """Bitmask of CLPS indices marked traction=3 (unclimbable/slippery)."""
    return extract_clps_masks(fs, overlay_id)[0]


def extract_clps_water_mask(fs: Filesystem, overlay_id: int) -> int:
    """Bitmask of CLPS indices whose word0 carries the water bit (0x20)."""
    return extract_clps_masks(fs, overlay_id)[1]
