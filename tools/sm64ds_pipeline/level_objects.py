"""SM64DS ARM9 level overlay decompression and static prop object extraction."""
from __future__ import annotations
from dataclasses import dataclass
import struct
from .common import FormatError
from .filesystem import Filesystem

DS_TO_SATURN_SCALE = 0.064
OBJ_ID_BOMB_TREE = 41
OBJ_ID_TATEFUDA = 76
CASTLE_GROUNDS_OVERLAY_ID = 9


@dataclass(frozen=True)
class LevelProp:
    object_id: int
    position: tuple[float, float, float]
    yaw_deg: int = 0
    param: int = 0


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


def extract_castle_props(fs: Filesystem) -> tuple[list[LevelProp], list[LevelProp]]:
    """Extract Castle Grounds exterior trees and wooden signs from overlay 9."""
    ram_addr, data = read_arm9_overlay(fs, CASTLE_GROUNDS_OVERLAY_ID)
    clps_off = data.find(b"CLPS")
    if clps_off < 0x10:
        raise FormatError("CLPS chunk not found in castle grounds overlay")

    # LevelOverlay header immediately precedes the first CLPS block; the pointer
    # 12 bytes before CLPS references the level's object-bank directory entry.
    area_ptr = struct.unpack_from("<I", data, clps_off - 0x0C)[0]
    area_off = _ptr_to_off(area_ptr, ram_addr, len(data))
    bank_ptr = struct.unpack_from("<I", data, area_off)[0]
    bank_off = _ptr_to_off(bank_ptr, ram_addr, len(data))
    list_count, list_ptr = struct.unpack_from("<II", data, bank_off)
    if not 1 <= list_count <= 32:
        raise FormatError(f"unexpected castle object list count: {list_count}")
    list_off = _ptr_to_off(list_ptr, ram_addr, len(data))

    trees: list[LevelProp] = []
    signs: list[LevelProp] = []
    for i in range(list_count):
        tag_type, obj_count, _pad, arr_ptr = struct.unpack_from("<BBHI", data, list_off + i * 8)
        arr_off = _ptr_to_off(arr_ptr, ram_addr, len(data))
        kind = tag_type & 0x1F
        if kind == 5:  # Simple object: 8 bytes (id_and_param:u16, x:i16, y:i16, z:i16)
            if arr_off + obj_count * 8 > len(data):
                raise FormatError("simple object array exceeds overlay bounds")
            for j in range(obj_count):
                idp, x, y, z = struct.unpack_from("<Hhhh", data, arr_off + j * 8)
                oid = idp & 0x1FF
                param = idp >> 9
                if oid == OBJ_ID_BOMB_TREE:
                    trees.append(LevelProp(
                        object_id=oid,
                        position=(x * DS_TO_SATURN_SCALE, y * DS_TO_SATURN_SCALE, z * DS_TO_SATURN_SCALE),
                        param=param,
                    ))
        elif kind == 0:  # Standard object: 16 bytes (id:u16, x/y/z:i16, rx/ry/rz:i16, param:u16)
            if arr_off + obj_count * 16 > len(data):
                raise FormatError("standard object array exceeds overlay bounds")
            for j in range(obj_count):
                oid, x, y, z, _rx, ry, _rz, param = struct.unpack_from("<HhhhhhhH", data, arr_off + j * 16)
                if oid == OBJ_ID_TATEFUDA:
                    yaw = round(ry * 360.0 / 65536.0) % 360
                    signs.append(LevelProp(
                        object_id=oid,
                        position=(x * DS_TO_SATURN_SCALE, y * DS_TO_SATURN_SCALE, z * DS_TO_SATURN_SCALE),
                        yaw_deg=yaw,
                        param=param,
                    ))
    return trees, signs
