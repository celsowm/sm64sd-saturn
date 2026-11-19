#!/usr/bin/env python3
"""Inspect support-order diagnostics and geometry in a matching High WRAM dump.

Use the ELF from the exact capture build. A dump can be taken mid-frame, so
queue contents and counters are a snapshot, not a complete frame history.
"""
import argparse
import json
import math
from pathlib import Path
import struct
import subprocess

BASE = 0x06000000
SIZE = 1024 * 1024
ONE = 65536


def symbols(nm, elf):
    result = {}
    for line in subprocess.check_output([str(nm), '-S', str(elf)], text=True).splitlines():
        words = line.split()
        if len(words) == 4:
            try:
                address, size = int(words[0], 16), int(words[1], 16)
            except ValueError:
                continue
            result[words[3].lstrip('_')] = (address, size)
    return result


def inspect(data, syms, face=None, queue=None, origins=None):
    if len(data) != SIZE:
        raise ValueError('expected a complete 1 MiB High WRAM dump')

    def offset(name, index=0, width=1):
        if name not in syms:
            raise ValueError(f'{name} is absent; use the matching diagnostic ELF')
        address, size = syms[name]
        if index < 0 or index+width > size:
            raise ValueError(f'{name}: requested range exceeds symbol size')
        off = address-BASE+index
        if off < 0 or off+width > len(data):
            raise ValueError(f'{name} is not entirely in captured High WRAM')
        return off

    def minimum_y(name):
        size = syms[name][1]
        if not size or size % 12:
            raise ValueError(f'{name} is not a vec3 array')
        start = offset(name, 0, size)
        values = [struct.unpack_from('>i', data, start+12*i+4)[0]
                  for i in range(size//12)]
        index = min(range(len(values)), key=values.__getitem__)
        return {'vertex': index, 'y': values[index]/ONE}

    diag = offset('g_sm64ds_support_diag', 0, 192)
    count = struct.unpack_from('>I', data, diag)[0]
    mapped, expected = struct.unpack_from('>2I', data, diag+164)
    counters = struct.unpack_from('>5I', data, diag+172)
    lowest = {name: minimum_y(name) for name in ('world_vertices', 'hw')}
    result = {'actor_lowest': lowest, 'blocked_records': count,
              'mapped': mapped, 'expected': expected,
              'counters': dict(zip(('calls', 'potential', 'map_failed', 'changes', 'blocked'), counters))}
    result['blockers'] = []
    for i in range(min(count, 8)):
        face_index, blocker_queue, *coordinates = struct.unpack_from('>HH8h', data, diag+4+20*i)
        result['blockers'].append({'face': face_index, 'other_queue': blocker_queue,
                                   'x': coordinates[:4], 'y': coordinates[4:]})
    if syms['g_sm64ds_support_diag'][1] >= 212 and counters[-1]:
        face_index, blocker_queue, *coordinates = struct.unpack_from('>HH8h', data, diag+192)
        result['last_group_blocker'] = {'face': face_index, 'other_queue': blocker_queue,
                                        'x': coordinates[:4], 'y': coordinates[4:]}
    if syms['g_sm64ds_support_diag'][1] == 208:
        calls, total, maximum, last = struct.unpack_from('>4I', data, diag+192)
        result['profile'] = {'calls': calls, 'ticks_sum_mod_2_32': total,
                             'ticks_max': maximum, 'ticks_last': last}
    if face is not None:
        face_queue = struct.unpack_from('>H', data, offset('diagnostic_support_face_queue', 2*face, 2))[0]
        indices = struct.unpack_from('>4H', data, offset('ci', 8*face, 8))
        vertices = []
        for index in indices:
            xyz = struct.unpack_from('>3i', data, offset('cw', 12*index, 12))
            projected = struct.unpack_from('>hhi', data, offset('cp', 8*index, 8))
            vertices.append({'index': index, 'world': [v/ONE for v in xyz],
                             'projected': {'x': projected[0], 'y': projected[1],
                                           'depth': projected[2]/ONE}})
        face_info = {'face': face, 'queue': None if face_queue == 0xffff else face_queue,
                     'vertices': vertices}
        p0, p1, p2 = (v['world'] for v in vertices[:3])
        a = [p1[i]-p0[i] for i in range(3)]
        b = [p2[i]-p0[i] for i in range(3)]
        normal = [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
        length = math.sqrt(sum(n*n for n in normal))
        if length:
            normal = [n/length*(1 if normal[1] >= 0 else -1) for n in normal]
            distances = []
            for name in ('world_vertices', 'hw'):
                start = offset(name, 0, syms[name][1])
                for i in range(syms[name][1]//12):
                    point = struct.unpack_from('>3i', data, start+12*i)
                    position = [v/ONE for v in point]
                    distance = sum(normal[j]*(position[j]-p0[j]) for j in range(3))
                    distances.append((distance, name, i, position))
            camera = struct.unpack_from('>3i', data, offset('g_sm64ds_castle_stats', 44, 12))
            minimum, group, index, point = min(distances)
            def edge_xz(a, b, p):
                return (b[0]-a[0])*(p[2]-a[2])-(b[2]-a[2])*(p[0]-a[0])
            area = edge_xz(p0, p1, p2)
            def inside_triangle_xz(point):
                e = [edge_xz(p0, p1, point), edge_xz(p1, p2, point), edge_xz(p2, p0, point)]
                return bool(area) and (all(v >= 0 for v in e) or all(v <= 0 for v in e))
            face_info['plane'] = {'upward_normal': normal,
                                  'actor_min_signed_distance': minimum,
                                  'actor_min_vertex': {'group': group, 'index': index,
                                                       'world': point,
                                                       'within_triangle_xz': inside_triangle_xz(point)},
                                  'actor_vertices_below_within_triangle_xz': sum(
                                      d < 0 and inside_triangle_xz(v) for d, _, _, v in distances),
                                  'camera_signed_distance': sum(normal[j]*(camera[j]/ONE-p0[j]) for j in range(3))}
        if face_queue != 0xffff:
            face_info['key'] = struct.unpack_from('>I', data, offset('keys', 4*face_queue, 4))[0]
        result['face'] = face_info
    if queue is not None:
        mapped_face = struct.unpack_from('>i', data, offset('diagnostic_support_cache', 4*queue, 4))[0]
        mapped_face = mapped_face if mapped_face >= 0 else None
        queue_info = {'queue': queue, 'face': mapped_face}
        if mapped_face is not None and origins is not None:
            if mapped_face >= len(origins):
                raise ValueError('queue mapping exceeds the supplied origin list')
            queue_info['source_face'] = origins[mapped_face]
        result['queue'] = queue_info
    return result


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True, type=Path)
    parser.add_argument('--wram', required=True, type=Path)
    parser.add_argument('--nm', type=Path, default=root.parent/'saturn-tools/bin/sh2eb-elf-nm')
    parser.add_argument('--face', type=int, help='optional generated render-face index')
    parser.add_argument('--queue', type=int, help='optional queued face to map to a render face')
    parser.add_argument('--origins', type=Path, help='optional generated castle_split_origins.json')
    args = parser.parse_args()
    try:
        origins = json.loads(args.origins.read_text()) if args.origins else None
        print(json.dumps(inspect(args.wram.read_bytes(), symbols(args.nm, args.elf),
                                 args.face, args.queue, origins), indent=2))
    except (OSError, ValueError, KeyError, struct.error, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
