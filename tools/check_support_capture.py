#!/usr/bin/env python3
"""Check matched actor, baseline and candidate face-ID captures.

The actor-only image supplies the silhouette. Face-ID overlap is a useful
regression measure but is not a general physical visibility oracle. A solid
diagnostic wall can additionally be checked for lost pixels, including when
the wall only partly covers the actor.
"""
import argparse
import json
from pathlib import Path

from PIL import Image
from measure_castle_occlusion import measure


def compare(actor, baseline, candidate, origins, source, background, wall):
    if actor.size != baseline.size or actor.size != candidate.size:
        raise ValueError('all capture dimensions must match')
    before = measure(actor, baseline, origins, background)
    after = measure(actor, candidate, origins, background)
    result = {'actor_pixels': before['actor_pixels'],
              'source': source,
              'source_overlap_before': before['overlap_by_source'].get(source, 0),
              'source_overlap_after': after['overlap_by_source'].get(source, 0)}
    if wall is not None:
        a = actor.convert('RGB').tobytes()
        b = baseline.convert('RGB').tobytes()
        c = candidate.convert('RGB').tobytes()
        before_wall = after_wall = lost_wall = lost_on_actor = 0
        for i in range(0, len(a), 3):
            ap, bp, cp = tuple(a[i:i+3]), tuple(b[i:i+3]), tuple(c[i:i+3])
            if ap == background:
                continue
            previous, current = bp == wall, cp == wall
            before_wall += previous
            after_wall += current
            lost_on_actor += previous and not current
        # Check the entire fixture as well as its intersection with Mario.
        for i in range(0, len(b), 3):
            lost_wall += tuple(b[i:i+3]) == wall and tuple(c[i:i+3]) != wall
        result.update(wall_on_actor_before=before_wall, wall_on_actor_after=after_wall,
                      wall_pixels_lost=lost_wall, wall_on_actor_lost=lost_on_actor)
    return result


def rgb(value):
    try:
        result = tuple(int(v) for v in value.split(','))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('expected R,G,B') from exc
    if len(result) != 3 or any(v < 0 or v > 255 for v in result):
        raise argparse.ArgumentTypeError('expected R,G,B in 0..255')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--origins', type=Path, required=True)
    parser.add_argument('--source', type=int, required=True)
    parser.add_argument('--background', type=rgb, default=(96, 160, 240))
    parser.add_argument('--wall', type=rgb, help='Exact RGB of the solid wall fixture')
    parser.add_argument('--min-wall-on-actor', type=int, default=0)
    parser.add_argument('--max-source-overlap', type=int, required=True)
    args = parser.parse_args()
    if args.min_wall_on_actor < 0 or args.max_source_overlap < 0:
        parser.error('pixel thresholds must be nonnegative')
    if args.min_wall_on_actor and args.wall is None:
        parser.error('--min-wall-on-actor requires --wall')
    origins = json.loads(args.origins.read_text())
    with Image.open(args.actor) as actor, Image.open(args.baseline) as baseline, Image.open(args.candidate) as candidate:
        result = compare(actor, baseline, candidate, origins, args.source, args.background, args.wall)
    failures = []
    if not result['actor_pixels']:
        failures.append('actor silhouette is empty')
    if result['source_overlap_after'] > args.max_source_overlap:
        failures.append('source overlap exceeds limit')
    if args.wall is not None:
        if result['wall_on_actor_before'] < args.min_wall_on_actor:
            failures.append('baseline wall does not cover enough actor pixels')
        if result['wall_pixels_lost']:
            failures.append('candidate lost baseline wall pixels')
    result['failures'] = failures
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
