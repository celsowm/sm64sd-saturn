#!/usr/bin/env python3
"""Find coincident and partially overlapping edges of two generated sources.

This is a geometry diagnostic, not a texture-coverage or visibility proof.
Coordinates come from the private generated castle C file in 16.16 units.
"""
import argparse
import json
import math
from pathlib import Path
import re


def array(text, declaration):
    try:
        return text.split(declaration, 1)[1].split('};', 1)[0]
    except IndexError as exc:
        raise ValueError(f'missing {declaration}') from exc


def edges(scene, origins, source):
    vertices = [tuple(int(v) / 65536 for v in xyz) for xyz in re.findall(
        r'\{(-?\d+),(-?\d+),(-?\d+)\}', array(scene, 'static const sat_vec3_t vertices[]={'))]
    values = [int(v) for v in re.findall(r'\d+', array(scene, 'static const uint16_t faces[]={'))]
    if len(values) != len(origins)*4:
        raise ValueError('origin count does not match generated faces')
    result = []
    for face, origin in enumerate(origins):
        if origin != source:
            continue
        indices = values[face*4:face*4+4]
        sides = ((0, 1), (1, 2), (2, 0)) if indices[2] == indices[3] else ((0, 1), (1, 2), (2, 3), (3, 0))
        for a, b in sides:
            if indices[a] != indices[b]:
                result.append((face, indices[a], indices[b], vertices[indices[a]], vertices[indices[b]]))
    return result


def overlap(a, b, tolerance):
    p, q = a[3], a[4]
    u = tuple(q[i]-p[i] for i in range(3))
    length2 = sum(v*v for v in u)
    if not length2:
        return None
    parameters = []
    for point in b[3:5]:
        d = tuple(point[i]-p[i] for i in range(3))
        t = sum(d[i]*u[i] for i in range(3))/length2
        error = math.sqrt(sum((d[i]-t*u[i])**2 for i in range(3)))
        if error > tolerance:
            return None
        parameters.append(t)
    lo, hi = max(0.0, min(parameters)), min(1.0, max(parameters))
    if (hi-lo)*math.sqrt(length2) <= tolerance:
        return None
    return {'faces': [a[0], b[0]], 'vertices': [[a[1], a[2]], [b[1], b[2]]],
            'overlap_units': (hi-lo)*math.sqrt(length2),
            'exact_vertex_pair': {a[1], a[2]} == {b[1], b[2]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--origins', type=Path, required=True)
    parser.add_argument('--sources', type=int, nargs=2, required=True)
    parser.add_argument('--tolerance', type=float, default=1/128)
    args = parser.parse_args()
    if args.tolerance <= 0 or args.sources[0] == args.sources[1]:
        parser.error('use a positive tolerance and two different source faces')
    scene = args.scene.read_text()
    origins = json.loads(args.origins.read_text())
    first, second = (edges(scene, origins, source) for source in args.sources)
    matches = [match for a in first for b in second if (match := overlap(a, b, args.tolerance))]
    print(json.dumps({'sources': args.sources, 'edge_counts': [len(first), len(second)],
                      'exact': sum(m['exact_vertex_pair'] for m in matches),
                      'partial': sum(not m['exact_vertex_pair'] for m in matches),
                      'matches': matches}, indent=2))


if __name__ == '__main__':
    main()
