"""Level object ID -> actor ID -> actor name.

sObjToActorIdTable (decomp ov002:0x0210cbf4) is a u16 array in this ROM's
overlay 2. It is found by content: object 42 is PICTURE_GATE (307) and object
80 is KINOPIO (185). Actor names come from the decomp's actor_debug_names.tsv.
"""
from __future__ import annotations
from pathlib import Path
import struct
from .common import FormatError
from .filesystem import Filesystem
from .level_objects import read_arm9_overlay

ACTOR_COUNT = 391
ACTOR_PICTURE_GATE = 307
ACTOR_KINOPIO = 185
DEFAULT_NAMES = Path(__file__).resolve().parents[2] / '.external/sm64ds-decomp/symbols/actor_debug_names.tsv'


def obj_to_actor_table(fs: Filesystem) -> list[int]:
    _ram, d = read_arm9_overlay(fs, 2)
    for o in range(0, len(d) - 164, 2):
        if struct.unpack_from('<H', d, o + 84)[0] == ACTOR_PICTURE_GATE and \
           struct.unpack_from('<H', d, o + 160)[0] == ACTOR_KINOPIO:
            n = 0
            while o + 2 * n + 2 <= len(d) and struct.unpack_from('<H', d, o + 2 * n)[0] < ACTOR_COUNT:
                n += 1
            return list(struct.unpack_from(f'<{n}H', d, o))
    raise FormatError('sObjToActorIdTable not found in overlay 2')


def actor_names(path: Path = DEFAULT_NAMES) -> dict[int, str]:
    out = {}
    for line in path.read_text().splitlines():
        parts = line.split('\t')
        if len(parts) >= 2:
            out[int(parts[0])] = parts[1]
    return out
