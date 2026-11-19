#!/usr/bin/env python3
"""Build a labeled contact sheet from DS and Saturn castle screenshots.

DSperate frame PNGs stack the DS top and bottom displays vertically. This tool
uses only the top display, then letterboxes both images into the same viewport
so gameplay camera framing can be reviewed side by side.

Example:
  python3 tools/compare_castle_captures.py \
    --pair spawn private/ds-mario-move.png private/castle-capture/final-reset.png \
    --output private/castle-comparison.png
"""

import argparse
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_view(path: Path, width: int, height: int) -> Image.Image:
    image = Image.open(path).convert("RGB")
    if image.height == image.width * 3 // 2:
        image = image.crop((0, 0, image.width, image.height // 2))
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), (18, 22, 30))
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    return canvas


def region_view(image: Image.Image, region: tuple[int, int, int, int], width: int, height: int) -> Image.Image:
    x, y, w, h = region
    crop = image.crop((x, y, x + w, y + h))
    return crop.resize((width, height), Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pair", nargs=3, action="append", metavar=("LABEL", "DS_PNG", "SATURN_PNG"),
        required=True, help="one DS and Saturn capture; repeat for more pairs",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=320, help="normalized viewport width")
    parser.add_argument("--height", type=int, default=224, help="normalized viewport height")
    args = parser.parse_args()

    label_h, gutter = 36, 8
    regions = [
        ("full view", None),
        ("Mario framing", (116, 72, 88, 120)),
        ("castle and ground", (0, 0, args.width, 122)),
    ]
    sheet = Image.new(
        "RGB",
        (2 * args.width + 3 * gutter, len(args.pair) * len(regions) * (args.height + label_h + gutter) + gutter),
        (34, 39, 48),
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    row = 0
    for label, ds_path, saturn_path in args.pair:
        ds_image = load_view(Path(ds_path), args.width, args.height)
        saturn_image = load_view(Path(saturn_path), args.width, args.height)
        for region_name, region in regions:
            y = gutter + row * (args.height + label_h + gutter)
            ds_x = gutter
            saturn_x = 2 * gutter + args.width
            ds_label = textwrap.fill(f"{label} · {region_name} · DS", width=39)
            saturn_label = textwrap.fill(f"{label} · {region_name} · Saturn", width=39)
            draw.multiline_text((ds_x, y + 2), ds_label, fill="white", font=font, spacing=1)
            draw.multiline_text((saturn_x, y + 2), saturn_label, fill="white", font=font, spacing=1)
            view_y = y + label_h
            ds_view = ds_image if region is None else region_view(ds_image, region, args.width, args.height)
            saturn_view = saturn_image if region is None else region_view(saturn_image, region, args.width, args.height)
            sheet.paste(ds_view, (ds_x, view_y))
            sheet.paste(saturn_view, (saturn_x, view_y))
            row += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
