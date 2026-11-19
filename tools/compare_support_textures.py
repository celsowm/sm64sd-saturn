#!/usr/bin/env python3
"""Measure image differences outside a matched actor-only capture."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops
from capture_support_animation import textured_changes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--actor', type=Path)
    p.add_argument('--baseline', type=Path)
    p.add_argument('--candidate', type=Path)
    p.add_argument('--baseline-dir', type=Path, help='matrix capture directory')
    p.add_argument('--candidate-dir', type=Path, help='matching matrix capture directory')
    args = p.parse_args()
    if args.baseline_dir or args.candidate_dir:
        if not args.baseline_dir or not args.candidate_dir or any((args.actor, args.baseline, args.candidate)):
            p.error('use both matrix directories or all three individual images')
        actors = sorted(args.baseline_dir.glob('*-actor.png'))
        if not actors:
            p.error('no actor captures in baseline directory')
        if {path.name for path in actors} != {path.name for path in args.candidate_dir.glob('*-actor.png')}:
            p.error('matrix directories must contain the same actor capture names')
        results = {}
        for path in actors:
            name = path.name.removesuffix('-actor.png')
            with Image.open(path) as actor, Image.open(args.candidate_dir/path.name) as other_actor, \
                 Image.open(args.baseline_dir/(name+'-base.png')) as baseline, \
                 Image.open(args.candidate_dir/(name+'-base.png')) as candidate:
                if any(image.size != actor.size for image in (other_actor, baseline, candidate)):
                    p.error(f'{name}: capture dimensions must match')
                if ImageChops.difference(actor.convert('RGB'), other_actor.convert('RGB')).getbbox():
                    p.error(f'{name}: actor captures differ; states may not match')
                results[name] = textured_changes(actor, baseline, candidate)
        print(json.dumps(results, indent=2))
        return
    if not all((args.actor, args.baseline, args.candidate)):
        p.error('use both matrix directories or all three individual images')
    with Image.open(args.actor) as actor, Image.open(args.baseline) as baseline, Image.open(args.candidate) as candidate:
        if actor.size != baseline.size or actor.size != candidate.size:
            p.error('capture dimensions must match')
        print(json.dumps(textured_changes(actor, baseline, candidate), indent=2))


if __name__ == '__main__':
    main()
