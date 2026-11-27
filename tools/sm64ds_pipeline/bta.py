"""BTA texture-SRT animation files (dExtAnmTexSRT_c).

A BTA animates the texture-SRT of the materials a BMD names. The runtime
(the decomp's ``func_020469e8`` in ``dExtAnmTexSRT_c::Update``) reads one
0x18-byte entry per animated material and, for each of five slots, copies
either a fixed table word (``flag == 1``) or ``table[index + frame]`` into the
material's texture matrix. The material state layout is the one
ModelComponents builds at 0x02044b30:

    slot 0  texScaleS   (fx32)      slot 1  texScaleT   (fx32)
    slot 2  texRotation (u16, 4096 per turn)
    slot 3  texTransS   (fx32)      slot 4  texTransT   (fx32)

The castle-grounds water (``MC_WATER`` in overlay 9) is the reference user:
``d_a_obj_mc_water.cpp`` calls ``Prepare(bmd, data_ov009_02112bc4)`` once,
then ``SetFile(file, 0, 0x1000, 0)`` and advances one frame per tick, so the
32x32 repeat water texture scrolls diagonally forever. Its BTA has 91 frames,
one entry with ``flag = (1,1,1,0,0)`` and ``index = (0,0,0,0,0)``: scale and
rotation are the fixed words 4096/4096/0, while transS/transT step through
``tableC[frame]`` (0,46,91,...,4096) and ``tableA[frame]`` (1,1,1,...,91).
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

from .common import FormatError
from .filesystem import Filesystem
from .level_objects import read_arm9_overlay

# The five animated material-state slots, in table order (A, A, B, C, C).
_TABLES = ("a", "a", "b", "c", "c")


@dataclass(frozen=True)
class TexSrtAnim:
    """One decoded BTA: per-frame texture-SRT for a single material.

    ``frames`` entries are ``(scale_s, scale_t, rotation, trans_s, trans_t)``
    in the file's own units (fx32 scale/translation, 4096-per-turn rotation).
    """

    frames: tuple[tuple[int, int, int, int, int], ...]


def parse_bta(blob: bytes, base: int, offset: int) -> TexSrtAnim:
    """Decode the BTA at ``offset`` in ``blob``.

    ``base`` is the overlay's load address: table and entry pointers inside the
    file are absolute addresses in that space and are rebased to file offsets.
    """
    if not 0 <= offset <= len(blob) - 0x18:
        raise FormatError("BTA offset outside overlay")
    num_frames = struct.unpack_from("<H", blob, offset)[0]
    table_a, table_b, table_c = struct.unpack_from("<III", blob, offset + 4)
    count, _pad, entries = struct.unpack_from("<HHI", blob, offset + 0x10)
    if not 1 <= num_frames <= 4096:
        raise FormatError("implausible BTA frame count")
    if not 1 <= count <= 64:
        raise FormatError("implausible BTA entry count")

    def to_off(address: int) -> int:
        off = address - base
        if not 0 <= off < len(blob):
            raise FormatError("BTA pointer outside overlay")
        return off

    def table(address: int, width: int) -> list[int]:
        fmt, size = ("<i", 4) if width == 4 else ("<H", 2)
        at = to_off(address)
        need = (num_frames + 1) * size
        if at + need > len(blob):
            raise FormatError("BTA table outside overlay")
        return [struct.unpack_from(fmt, blob, at + i * size)[0]
                for i in range(num_frames + 1)]

    a = table(table_a, 4)
    b = table(table_b, 2)
    c = table(table_c, 4)
    tables = {"a": a, "b": b, "c": c}
    entries_at = to_off(entries)
    if entries_at + count * 0x18 > len(blob):
        raise FormatError("BTA entries outside overlay")

    frames = []
    for frame in range(num_frames):
        slots = [0, 0, 0, 0, 0]
        for i in range(count):
            at = entries_at + i * 0x18
            _id, _p2, _p4, _p6 = struct.unpack_from("<4H", blob, at)
            for slot in range(5):
                flag = struct.unpack_from("<H", blob, at + 8 + 4 * slot)[0]
                idx = struct.unpack_from("<H", blob, at + 10 + 4 * slot)[0]
                word = tables[_TABLES[slot]][idx]
                if flag != 1:
                    word = tables[_TABLES[slot]][idx + frame]
                slots[slot] = word
        frames.append(tuple(slots))
    return TexSrtAnim(tuple(frames))


def load_bta(fs: Filesystem, overlay_id: int, offset: int) -> TexSrtAnim:
    """Read and decode the BTA at ``offset`` bytes into an ARM9 overlay.

    ``offset`` is relative to the decompressed overlay image, not a link-time
    address: the decomp's ``data_ov009_02112bc4`` is a build-space symbol and
    the retail overlay is a different build with a different base.
    """
    base, data = read_arm9_overlay(fs, overlay_id)
    return parse_bta(data, base, offset)