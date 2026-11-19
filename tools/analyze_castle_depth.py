#!/usr/bin/env python3
"""Compare projected body and castle triangle depths at captured pixels.

Inputs are matched body-only face-ID and castle face-ID captures with WRAM
dumps and their exact ELFs. This is a diagnostic approximation: it uses
triangle interpolation at integer pixel positions, whereas VDP1 rasterizes
distorted quads with hardware-specific coverage. It does not cover the head,
near-clipped polygons, or pixels outside the projected triangles.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import struct
import subprocess

from PIL import Image
from inspect_face_capture import face_id

WRAM_BASE = 0x06000000


def symbol_table(nm, elf):
    result = subprocess.run([str(nm), '-S', '-n', str(elf)], check=True,
                            text=True, capture_output=True)
    symbols = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 4:
            try:
                address, size = int(parts[0], 16), int(parts[1], 16)
            except ValueError:
                continue
            symbols[parts[3]] = (address - WRAM_BASE, size)
    return symbols


def projected_face(data, symbols, index_symbol, projected_symbol, face):
    index_start, index_size = symbols[index_symbol]
    projected_start, projected_size = symbols[projected_symbol]
    if index_start < 0 or projected_start < 0 or (face + 1) * 8 > index_size:
        raise ValueError('face index outside WRAM symbol')
    indices = struct.unpack_from('>4H', data, index_start + face * 8)
    if any((index + 1) * 8 > projected_size for index in indices):
        raise ValueError('vertex index outside projected symbol')
    return [struct.unpack_from('>hhi', data, projected_start + 8 * i) for i in indices]


def depth_at(points, x, y, tolerance=0.03):
    """Perspective-correct depth, or None when outside the projected face."""
    for i, j, k in ((0, 1, 2), (0, 2, 3)):
        (x0, y0, w0), (x1, y1, w1), (x2, y2, w2) = (points[n] for n in (i, j, k))
        denominator = (y1-y2)*(x0-x2) + (x2-x1)*(y0-y2)
        if not denominator or min(w0, w1, w2) <= 0:
            continue
        u = ((y1-y2)*(x-x2) + (x2-x1)*(y-y2))/denominator
        v = ((y2-y0)*(x-x2) + (x0-x2)*(y-y2))/denominator
        t = 1-u-v
        if min(u, v, t) >= -tolerance:
            inverse_depth = u/w0 + v/w1 + t/w2
            if inverse_depth > 0:
                return 1/inverse_depth
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('actor-image', 'actor-wram', 'actor-elf', 'castle-image',
                 'castle-wram', 'castle-elf', 'origins'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--nm', type=Path, required=True)
    parser.add_argument('--source', type=int, required=True)
    args = parser.parse_args()
    actor_symbols = symbol_table(args.nm, args.actor_elf)
    castle_symbols = symbol_table(args.nm, args.castle_elf)
    actor_data, castle_data = args.actor_wram.read_bytes(), args.castle_wram.read_bytes()
    origins = json.loads(args.origins.read_text())
    actor_count = actor_symbols['_indices'][1] // 8
    with Image.open(args.actor_image) as image:
        actor = image.convert('RGB')
    with Image.open(args.castle_image) as image:
        castle = image.convert('RGB')
    if actor.size != castle.size:
        parser.error('capture dimensions must match')
    counts = Counter()
    pairs = defaultdict(list)
    actor_faces, castle_faces = {}, {}
    for y in range(actor.height):
        for x in range(actor.width):
            castle_id = face_id(castle.getpixel((x, y)), len(origins))
            if castle_id is None or origins[castle_id] != args.source:
                continue
            actor_id = face_id(actor.getpixel((x, y)), actor_count)
            if actor_id is None:
                continue
            if actor_id not in actor_faces:
                actor_faces[actor_id] = projected_face(actor_data, actor_symbols, '_indices', '_projected', actor_id)
            if castle_id not in castle_faces:
                castle_faces[castle_id] = projected_face(castle_data, castle_symbols, '_ci', '_cp', castle_id)
            sx, sy = x - actor.width // 2, y - actor.height // 2
            actor_depth = depth_at(actor_faces[actor_id], sx, sy)
            castle_depth = depth_at(castle_faces[castle_id], sx, sy)
            if actor_depth is None or castle_depth is None:
                counts['outside_projected_triangles'] += 1
                continue
            delta = (castle_depth - actor_depth) / 65536
            counts['ground_behind' if delta > 0 else 'ground_in_front_or_equal'] += 1
            pairs[(castle_id, actor_id)].append(delta)
    crossing = [{'castle_face': c, 'actor_face': a,
                 'min_delta': round(min(values), 4), 'max_delta': round(max(values), 4)}
                for (c, a), values in sorted(pairs.items()) if min(values) < 0 < max(values)]
    print(json.dumps({'source': args.source, 'counts': counts, 'crossing_pairs': crossing,
                      'note': 'Approximate body-only projected-triangle comparison; not a pixel-perfect oracle.'}, indent=2))


if __name__ == '__main__':
    main()
