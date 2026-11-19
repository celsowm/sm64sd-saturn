#!/usr/bin/env python3
"""Read Mario and dCamera_c pose from a DSperate main-RAM dump.

Example:
  python3 tools/inspect_ds_castle_state.py --ram private/ds-camera.bin --scale 0.064
"""
import argparse
import json
from pathlib import Path
import struct

RAM_BASE = 0x02000000
RAM_SIZE = 4 * 1024 * 1024
ACTOR_ID_CAMERA = 0x014C
ACTOR_ID_MARIO = 0x00BF
CAMERA_SIZE = 0x1A8


def inspect(data: bytes, scale: float,
            anchor: tuple[float, float, float] | None = None) -> dict:
    if len(data) < RAM_SIZE:
        raise ValueError(f"RAM dump must contain at least {RAM_SIZE} main-RAM bytes")

    def word(addr: int) -> int:
        off = addr - RAM_BASE
        if off < 0 or off + 4 > RAM_SIZE:
            raise ValueError(f"address outside main RAM: 0x{addr:08x}")
        return struct.unpack_from("<I", data, off)[0]

    def s16(addr: int) -> int:
        return struct.unpack_from("<h", data, addr - RAM_BASE)[0]

    def vector(addr: int) -> tuple[int, int, int]:
        return struct.unpack_from("<3i", data, addr - RAM_BASE)

    actors: dict[int, list[int]] = {ACTOR_ID_CAMERA: [], ACTOR_ID_MARIO: []}
    for off in range(0, RAM_SIZE - CAMERA_SIZE, 4):
        actor_id = struct.unpack_from("<H", data, off + 0x0C)[0]
        if actor_id not in actors:
            continue
        vtable = struct.unpack_from("<I", data, off)[0]
        if RAM_BASE <= vtable < RAM_BASE + RAM_SIZE:
            actors[actor_id].append(RAM_BASE + off)

    players = actors[ACTOR_ID_MARIO]
    if not players:
        raise ValueError("no Mario actor (ID 0xbf) found")
    cameras = actors[ACTOR_ID_CAMERA]
    matches = [(c, p) for c in cameras for p in players if word(c + 0x110) == p]
    if len(matches) != 1:
        raise ValueError(f"expected one camera targeting Mario; found {len(matches)}")
    camera, player = matches[0]

    player_raw = vector(player + 0x5C)
    look_raw = vector(camera + 0x80)
    eye_raw = vector(camera + 0x8C)
    target_raw = vector(camera + 0x98)
    player_units = tuple(v / 4096 for v in player_raw)
    look_units = tuple(v / 4096 for v in look_raw)
    eye_units = tuple(v / 4096 for v in eye_raw)
    target_units = tuple(v / 4096 for v in target_raw)
    offset = (tuple(anchor[i] - player_units[i] * scale for i in range(3))
              if anchor is not None else (0.0, 0.0, 0.0))

    def map_point(p: tuple[float, float, float]) -> tuple[float, float, float]:
        return tuple(p[i] * scale + offset[i] for i in range(3))

    angle_y = s16(player + 0x8E)
    camera_yaw = s16(camera + 0x17C)
    camera_pitch = s16(camera + 0x17E)
    fov_half = s16(camera + 0x17A)
    angle_degrees = lambda a: a * 360 / 65536
    return {
        "ram": {"camera": f"0x{camera:08x}", "mario": f"0x{player:08x}"},
        "mario": {
            "position_raw_fix12": player_raw,
            "position_ds_units": player_units,
            "facing_raw_angle": angle_y,
            "facing_degrees": angle_degrees(angle_y),
            "position_saturn_units": map_point(player_units),
        },
        "camera": {
            "look_at_raw_fix12": look_raw,
            "eye_raw_fix12": eye_raw,
            "target_player_raw_fix12": target_raw,
            "look_at_ds_units": look_units,
            "eye_ds_units": eye_units,
            "target_player_ds_units": target_units,
            "look_at_saturn_units": map_point(look_units),
            "eye_saturn_units": map_point(eye_units),
            "target_player_saturn_units": map_point(target_units),
            "yaw_raw_angle": camera_yaw,
            "yaw_degrees": angle_degrees(camera_yaw),
            "pitch_raw_angle": camera_pitch,
            "pitch_degrees": angle_degrees(camera_pitch),
            "fov_half_raw_angle": fov_half,
            "fov_y_degrees": 2 * angle_degrees(fov_half),
            "target_player": f"0x{word(camera + 0x110):08x}",
        },
        "mapping": {"scale": scale, "offset_saturn_units": offset},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ram", required=True, type=Path)
    parser.add_argument("--scale", type=float, default=0.064)
    parser.add_argument("--saturn-anchor", default=None,
                        help="optional Saturn x,y,z to align the captured Mario position")
    args = parser.parse_args()
    anchor = None if args.saturn_anchor is None else tuple(float(v) for v in args.saturn_anchor.split(","))
    if anchor is not None and len(anchor) != 3:
        parser.error("--saturn-anchor must be x,y,z")
    print(json.dumps(inspect(args.ram.read_bytes(), args.scale, anchor), indent=2))
