#!/usr/bin/env python3
"""Count face-ID pixels overlapping a matched actor-only capture.

Overlap is an observation, not proof of incorrect occlusion: foreground
geometry can legitimately hide the actor. Both captures must use the same
camera, actor pose, viewport, and render timing.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from PIL import Image
from inspect_face_capture import face_id


def measure(actor, scene, origins, background, by_render_face=False):
    if actor.size != scene.size:
        raise ValueError('capture dimensions must match')
    counts = Counter()
    actor_pixels = 0
    actor_bytes = actor.convert('RGB').tobytes()
    scene_bytes = scene.convert('RGB').tobytes()
    for offset in range(0, len(actor_bytes), 3):
        actor_pixel = tuple(actor_bytes[offset:offset + 3])
        scene_pixel = tuple(scene_bytes[offset:offset + 3])
        if actor_pixel == background:
            continue
        actor_pixels += 1
        # A visible actor pixel can happen to decode as a castle face ID.
        if actor_pixel == scene_pixel:
            continue
        index = face_id(scene_pixel, len(origins))
        if index is not None:
            counts[index if by_render_face else origins[index]] += 1
    return {'actor_pixels': actor_pixels,
            ('overlap_by_render_face' if by_render_face else 'overlap_by_source'):
                dict(sorted(counts.items()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('actor', type=Path, help='Actor-only capture')
    parser.add_argument('scene', type=Path, help='Matching face-ID capture')
    parser.add_argument('origins', type=Path, help='Render-to-source face JSON array')
    parser.add_argument('--background', default='96,160,240', help='Actor-only background RGB')
    parser.add_argument('--by-render-face', action='store_true', help='count generated face IDs instead of source IDs')
    args = parser.parse_args()
    try:
        background = tuple(int(value) for value in args.background.split(','))
        if len(background) != 3 or any(value < 0 or value > 255 for value in background):
            raise ValueError('background must be R,G,B in 0..255')
        origins = json.loads(args.origins.read_text())
        if not isinstance(origins, list) or any(not isinstance(i, int) or i < 0 for i in origins):
            raise ValueError('origins must be an array of nonnegative face IDs')
        with Image.open(args.actor) as actor, Image.open(args.scene) as scene:
            result = measure(actor, scene, origins, background, args.by_render_face)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
