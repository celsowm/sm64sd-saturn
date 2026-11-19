#!/usr/bin/env python3
"""Convert a DSperate headless frame dump to a pair of PNG screens."""

import argparse
from pathlib import Path

from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("output", type=Path, help="PNG with top and bottom screens stacked")
    parser.add_argument("--frame", type=int, default=0, help="zero-based frame within the dump")
    args = parser.parse_args()
    frame_bytes = 256 * 192 * 2 * 4
    if args.frame < 0:
        parser.error("--frame must be nonnegative")
    with args.dump.open("rb") as source:
        source.seek(args.frame * frame_bytes)
        pixels = source.read(frame_bytes)
    if len(pixels) != frame_bytes:
        parser.error("frame is missing or incomplete")
    Image.frombytes("RGBA", (256, 384), pixels, "raw", "BGRA").convert("RGB").save(args.output)


if __name__ == "__main__":
    main()
