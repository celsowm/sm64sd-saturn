#!/usr/bin/env python3
"""Locate textured changes outside an actor and identify their face-ID pairs."""
import argparse
from collections import Counter
import json
from pathlib import Path

from PIL import Image
from inspect_face_capture import face_id


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('actor', 'baseline', 'candidate', 'baseline-ids', 'candidate-ids', 'origins'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--candidate-origins', type=Path,
                   help='source mapping for candidate when its mesh differs from baseline')
    p.add_argument('--limit', type=int, default=30)
    a = p.parse_args()
    origins = json.loads(a.origins.read_text())
    candidate_origins = json.loads(a.candidate_origins.read_text()) if a.candidate_origins else origins
    paths = (a.actor, a.baseline, a.candidate, a.baseline_ids, a.candidate_ids)
    images = [Image.open(path).convert('RGB') for path in paths]
    if any(image.size != images[0].size for image in images):
        p.error('capture dimensions must match')
    buffers = [image.tobytes() for image in images]
    width, height = images[0].size
    pairs, source_pairs, examples, deltas = Counter(), Counter(), [], Counter()
    for y in range(height):
        for x in range(width):
            offset = 3*(y*width+x)
            actor, before, after, before_id, after_id = (
                tuple(data[offset:offset+3]) for data in buffers)
            if actor != (96, 160, 240) or before == after:
                continue
            left, right = face_id(before_id, len(origins)), face_id(after_id, len(candidate_origins))
            pairs[f'{left}->{right}'] += 1
            left_source = origins[left] if left is not None else None
            right_source = candidate_origins[right] if right is not None else None
            source_pairs[f'{left_source}->{right_source}'] += 1
            deltas[max(abs(before[i]-after[i]) for i in range(3))] += 1
            if len(examples) < a.limit:
                examples.append({'x': x, 'y': y, 'before_rgb': before, 'after_rgb': after,
                                 'before_face': left, 'after_face': right,
                                 'before_source': left_source, 'after_source': right_source})
    print(json.dumps({'changed_pixels': sum(pairs.values()), 'face_pairs': dict(pairs),
                      'source_pairs': dict(source_pairs),
                      'channel_delta_histogram': dict(sorted(deltas.items())),
                      'examples': examples}, indent=2))


if __name__ == '__main__':
    main()
