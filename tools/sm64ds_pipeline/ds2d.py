"""Nintendo DS 2D asset (NCG/NSC/NCL & 3D font) decoders for Sega Saturn VDP1/VDP2."""
from __future__ import annotations

import struct
from dataclasses import dataclass

from .common import FormatError
from .compression import lz77_auto
from .filesystem import Filesystem
from .textures import decode_texture, rgba_to_rgb555


FONT_CHARS = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "[]?!~,\"\"·abcdefghijklmnopqrstuvwxyz"
    "-.\':;& /"
)
FONT_INDEX = {ch: idx for idx, ch in enumerate(FONT_CHARS)}

FONT16_PATH = "ARCHIVE/c2d.narc:data/2D_cad/USA/d_2d_mario_3Dfont_16_16_US_PAL_ncg.bin"
FONT8_PATH = "ARCHIVE/c2d.narc:data/2D_cad/USA/d_2d_mario_3Dfont_US_PAL_ncg.bin"
CMN_PAL_PATH = "data/2D_cad/d_2d_cmn_icon_ncl.bin"
CLOUD_OBJ_NCG_PATH = "data/2D_cad/d_2d_op_obj_cl_ncg.bin"
CLOUD_OBJ_NCL_PATH = "data/2D_cad/d_2d_op_obj_cl_ncl.bin"
PEACH_LETTER_BMD_PATH = "data/normal_obj/opening/USA/peach_letter_US.bmd"
# Real boot/title logo art (used by the title screen and IPL splash).
NINTENDO_LOGO_NSC_PATH = "data/2D_cad/d_2d_nintendo_logo_nsc.bin"
MARIO64DS_IPL_NCG_PATH = "data/2D_cad/d_2d_MARIO64DS_IPL_download_ncg.bin"
MARIO64DS_IPL_NCL_PATH = "data/2D_cad/d_2d_MARIO64DS_IPL_download_ncl.bin"


@dataclass(frozen=True)
class SpriteRgb555:
    width: int
    height: int
    pixels: tuple[int, ...]  # Saturn BGR555 with bit 15 set, or 0 for transparent


@dataclass(frozen=True)
class CloudAtlas4bpp:
    width: int
    height: int
    pixels: bytes  # 4bpp packed, Saturn order: high nibble = left pixel
    palette: tuple[int, ...]  # 16 Saturn BGR555 CRAM words (without bit 15)
    # One (x, y, w, h) box per cloud, in source order (top-left first): big,
    # top-right, mid-right, bottom-left. Each box holds only that cloud.
    rects: tuple[tuple[int, int, int, int], ...] = ()


def ds_bgr555_to_saturn(val: int, *, direct: bool = True) -> int:
    """Convert Nintendo DS 15-bit BGR555 to Saturn BGR555 (bit 15 set for VDP1 direct)."""
    raw = val & 0x7FFF
    return (0x8000 | raw) if direct else raw


def decode_ncl_palettes(blob: bytes, *, direct: bool = False) -> list[tuple[int, ...]]:
    """Decode DS NCL palette data into a list of 16-entry Saturn BGR555 palettes."""
    data = lz77_auto(blob)
    if len(data) < 32 or (len(data) % 32) != 0:
        raise FormatError(f"invalid NCL length: {len(data)}")
    palettes: list[tuple[int, ...]] = []
    for p in range(len(data) // 32):
        entries = tuple(
            ds_bgr555_to_saturn(struct.unpack_from("<H", data, p * 32 + i * 2)[0], direct=direct)
            for i in range(16)
        )
        palettes.append(entries)
    return palettes


def _sample_ncg_4bpp(ncg: bytes, tile_id: int, x: int, y: int) -> int:
    off = tile_id * 32 + y * 4 + (x >> 1)
    if off >= len(ncg):
        return 0
    b = ncg[off]
    return ((b >> 4) & 0xF) if (x & 1) else (b & 0xF)


def _make_green_font_palette(gold_pal: tuple[int, ...]) -> tuple[int, ...]:
    """Derive a crisp Mario-Green 3D beveled font palette from the ROM's gold palette."""
    out = [0]
    for i in range(1, 16):
        c = gold_pal[i] & 0x7FFF
        r = c & 31
        g = (c >> 5) & 31
        b = (c >> 10) & 31
        # Map yellow/gold luminance to vibrant Mario green (keep dark outlines black)
        if r <= 2 and g <= 2 and b <= 2:
            out.append(0x8000)
        else:
            ng = min(31, max(g, r))
            nr = min(31, (r * 3) // 10)
            nb = min(31, (b * 5) // 10)
            out.append(0x8000 | (nb << 10) | (ng << 5) | nr)
    return tuple(out)


def _make_white_font_palette(gold_pal: tuple[int, ...]) -> tuple[int, ...]:
    """Derive a clean white-with-black-outline 3D beveled palette from the ROM's gold palette."""
    out = [0]
    for i in range(1, 16):
        c = gold_pal[i] & 0x7FFF
        r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
        if r <= 2 and g <= 2 and b <= 2:
            out.append(0x8000)
        else:
            lum = max(r, g, b)
            nr = min(31, max(18, lum))
            ng = min(31, max(18, lum))
            nb = min(31, max(20, lum))
            out.append(0x8000 | (nb << 10) | (ng << 5) | nr)
    return tuple(out)


def render_mario3d_banner(
    fs: Filesystem,
    lines: list[tuple[str, list[str] | str]],
    *,
    char_advance: int = 15,
    line_height: int = 18,
    pad_x: int = 4,
    pad_y: int = 2,
) -> SpriteRgb555:
    """Render multi-line text using SM64DS's authentic 16x16 3D beveled font to Saturn RGB555.

    Color codes in palette specs: 'R' (red), 'B' (blue), 'Y' (gold/yellow), 'G' (green),
    'O' (orange), 'W' (white). Width is padded to a multiple of 8 for Saturn VDP1.
    """
    ncg = lz77_auto(fs.read(FONT16_PATH))
    pals = decode_ncl_palettes(fs.read(CMN_PAL_PATH), direct=True)
    pal_map = {
        "Y": pals[1],
        "R": pals[4],
        "B": pals[5],
        "O": pals[8],
        "G": _make_green_font_palette(pals[1]),
        "W": _make_white_font_palette(pals[1]),
    }

    max_cols = max((len(text) for text, _ in lines), default=1)
    raw_w = max_cols * char_advance + (16 - char_advance) + pad_x * 2
    width = (raw_w + 7) & ~7
    height = len(lines) * line_height + pad_y * 2
    buf = [0] * (width * height)

    for li, (text, color_spec) in enumerate(lines):
        line_px_w = len(text) * char_advance + (16 - char_advance) if text else 0
        x0 = (width - line_px_w) // 2
        y0 = pad_y + li * line_height
        ci_seq = list(color_spec) if isinstance(color_spec, str) else list(color_spec)
        color_cursor = 0
        for ch_idx, ch in enumerate(text):
            if ch == " ":
                continue
            glyph = FONT_INDEX.get(ch)
            if glyph is None:
                continue
            code = ci_seq[color_cursor % len(ci_seq)] if ci_seq else "Y"
            color_cursor += 1
            pal = pal_map.get(code, pal_map["Y"])
            gr, gc = glyph // 16, glyph % 16
            gx = x0 + ch_idx * char_advance
            for py in range(16):
                dy = y0 + py
                if not (0 <= dy < height):
                    continue
                tile_row = gr * 2 + (py >> 3)
                sub_y = py & 7
                for px in range(16):
                    dx = gx + px
                    if not (0 <= dx < width):
                        continue
                    tile_col = gc * 2 + (px >> 3)
                    sub_x = px & 7
                    cidx = _sample_ncg_4bpp(ncg, tile_row * 32 + tile_col, sub_x, sub_y)
                    if cidx != 0:
                        buf[dy * width + dx] = pal[cidx]
    return SpriteRgb555(width=width, height=height, pixels=tuple(buf))


def render_peach_letter_card(
    fs: Filesystem,
    lines: list[str],
    *,
    width: int = 160,
    height: int = 168,
) -> SpriteRgb555:
    """Compose Peach's parchment letter card from ROM parchment + signature + SM64DS 8x16 font."""
    if (width % 8) != 0:
        raise FormatError("VDP1 sprite width must be a multiple of 8")
    bmd_data = fs.read(PEACH_LETTER_BMD_PATH)
    _scale, _nb, _bo, _ndl, _dlo, nt, to, _np, po, _nm, _mo = struct.unpack_from(
        "<IIIIIIIIIII", bmd_data, 0
    )
    if nt < 2:
        raise FormatError("peach_letter_US.bmd missing expected textures")
    sig_tex = decode_texture(bmd_data, to + 0 * 20, po + 0 * 16)
    paper_tex = decode_texture(bmd_data, to + 1 * 20, po + 1 * 16)
    font8 = lz77_auto(fs.read(FONT8_PATH))

    # Build mirrored parchment background (peach_letter_2 is the right half, mirrored across X)
    rgba_buf: list[tuple[int, int, int, int]] = [(248, 238, 232, 255)] * (width * height)
    for y in range(height):
        sy = min(paper_tex.height - 1, (y * paper_tex.height) // height)
        for x in range(width):
            # Mirror horizontally around center so ornate scrollwork frames both sides
            u = abs((x * 2 + 1) - width) / float(width)
            sx = min(paper_tex.width - 1, int(u * paper_tex.width))
            r, g, b, a = paper_tex.pixels[sy * paper_tex.width + sx]
            # Warm cream tint and subtle parchment border frame
            if x < 2 or x >= width - 2 or y < 2 or y >= height - 2:
                rgba_buf[y * width + x] = (176, 136, 152, 255)
            elif x < 4 or x >= width - 4 or y < 4 or y >= height - 4:
                rgba_buf[y * width + x] = (232, 206, 214, 255)
            else:
                rgba_buf[y * width + x] = (
                    min(255, r + 8),
                    min(255, g + 4),
                    min(255, b + 4),
                    255,
                )

    # Render readable SM64DS 8x16 dialogue font lines in deep warm plum ink
    ink_dark = (58, 28, 48, 255)
    ink_mid = (112, 68, 96, 255)
    ink_shadow = (218, 198, 208, 255)
    y_cursor = 16
    for line in lines:
        if not line:
            y_cursor += 6
            continue
        char_w = 7
        line_w = len(line) * char_w
        x0 = max(8, (width - line_w) // 2)
        for idx, ch in enumerate(line):
            if ch == " ":
                continue
            glyph = FONT_INDEX.get(ch)
            if glyph is None:
                continue
            gr, gc = glyph // 32, glyph % 32
            gx = x0 + idx * char_w
            for py in range(16):
                dy = y_cursor + py
                if not (0 <= dy < height):
                    continue
                tile_id = (gr * 2 + (py >> 3)) * 32 + gc
                sub_y = py & 7
                for px in range(8):
                    dx = gx + px
                    if not (0 <= dx < width):
                        continue
                    cidx = _sample_ncg_4bpp(font8, tile_id, px, sub_y)
                    if cidx != 0:
                        # Subtle 1px drop shadow for legibility at 320x224
                        if dx + 1 < width and dy + 1 < height:
                            rgba_buf[(dy + 1) * width + (dx + 1)] = ink_shadow
                        rgba_buf[dy * width + dx] = ink_dark if cidx >= 2 else ink_mid
        y_cursor += 15

    # Composite Peach's authentic pink handwritten signature at bottom-right
    sig_x0 = width - sig_tex.width - 12
    sig_y0 = height - sig_tex.height - 6
    for sy in range(sig_tex.height):
        dy = sig_y0 + sy
        if not (0 <= dy < height):
            continue
        for sx in range(sig_tex.width):
            dx = sig_x0 + sx
            if not (0 <= dx < width):
                continue
            sr, sg, sb, sa = sig_tex.pixels[sy * sig_tex.width + sx]
            if sa >= 96:
                br, bg, bb, _ = rgba_buf[dy * width + dx]
                alpha = sa / 255.0
                rgba_buf[dy * width + dx] = (
                    int(sr * alpha + br * (1.0 - alpha)),
                    int(sg * alpha + bg * (1.0 - alpha)),
                    int(sb * alpha + bb * (1.0 - alpha)),
                    255,
                )

    sat_pixels = tuple(0x8000 | (rgba_to_rgb555(px) & 0x7FFF) for px in rgba_buf)
    return SpriteRgb555(width=width, height=height, pixels=sat_pixels)


def extract_cloud_atlas(fs: Filesystem) -> CloudAtlas4bpp:
    """Extract the SM64DS title clouds as a 4bpp atlas (Saturn nibble order)
    plus their 16-color CRAM palette, one separate box per cloud.

    The source is 512 OBJ tiles (32 x 16, 256x128) that the game assembles
    with OAM in code, so the raw grid is not a picture: the bottom-left
    cloud's last 16 rows sit in a strip at x 176..255, rows 112..127, next
    to a solid 32x16 sky block at x 144..175, and the big cloud's box
    overlaps the mid-right cloud. Copying rectangles straight out of the raw
    grid therefore cut clouds and dragged in pieces of their neighbours.
    Here the strip is put back under its cloud, the sky block dropped, and
    every cloud copied by its own pixel mask into its own box.
    """
    ncg = lz77_auto(fs.read(CLOUD_OBJ_NCG_PATH))
    pals = decode_ncl_palettes(fs.read(CLOUD_OBJ_NCL_PATH), direct=False)
    src_w, src_h = 256, 128
    joined_h = src_h + 16
    grid = [[0] * src_w for _ in range(joined_h)]
    for y in range(src_h):
        for x in range(src_w):
            grid[y][x] = _sample_ncg_4bpp(ncg, (y >> 3) * 32 + (x >> 3), x & 7, y & 7)
    for y in range(112, 128):
        for x in range(144, 256):
            if x >= 176:
                grid[y + 16][x - 152] = grid[y][x]
            grid[y][x] = 0

    # 8-connected clouds, ordered by their top-left corner.
    seen = [[False] * src_w for _ in range(joined_h)]
    clouds = []
    for y0 in range(joined_h):
        for x0 in range(src_w):
            if not grid[y0][x0] or seen[y0][x0]:
                continue
            seen[y0][x0] = True
            stack, pts = [(x0, y0)], []
            while stack:
                x, y = stack.pop()
                pts.append((x, y))
                for ny in (y - 1, y, y + 1):
                    for nx in (x - 1, x, x + 1):
                        if 0 <= nx < src_w and 0 <= ny < joined_h and grid[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
            clouds.append(pts)
    clouds = [c for c in clouds if len(c) >= 256]   # drop stray specks
    if len(clouds) != 4:
        raise FormatError(f"expected 4 title clouds, found {len(clouds)}")
    boxes = []
    for pts in clouds:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        boxes.append((min(ys), min(xs), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, pts))
    boxes.sort(key=lambda b: (b[0], b[1]))

    # First-fit shelf packing into a 256-wide atlas, tallest first, 2px apart.
    width = 256
    place = {}
    shelves = []   # [y, height, next x]
    for i in sorted(range(4), key=lambda i: -boxes[i][3]):
        _, _, w, h, _ = boxes[i]
        shelf = next((sh for sh in shelves if sh[1] >= h and sh[2] + w <= width), None)
        if shelf is None:
            shelf = [shelves[-1][0] + shelves[-1][1] + 2 if shelves else 0, h, 0]
            shelves.append(shelf)
        place[i] = (shelf[2], shelf[0])
        shelf[2] += w + 2
    height = (shelves[-1][0] + shelves[-1][1] + 7) & ~7
    out = [[0] * width for _ in range(height)]
    rects = []
    for i, (top, left, w, h, pts) in enumerate(boxes):
        px, py = place[i]
        for x, y in pts:
            out[py + y - top][px + x - left] = grid[y][x]
        rects.append((px, py, w, h))
    packed = bytearray((width * height) // 2)
    for y in range(height):
        for x in range(0, width, 2):
            packed[(y * width + x) >> 1] = ((out[y][x] & 0xF) << 4) | (out[y][x + 1] & 0xF)
    return CloudAtlas4bpp(width=width, height=height, pixels=bytes(packed),
                          palette=pals[0], rects=tuple(rects))


def decode_ncl_palette16(blob: bytes, *, direct: bool = True) -> tuple[int, ...]:
    """Decode a single 16-entry DS NCL palette (32 bytes) to Saturn BGR555."""
    data = lz77_auto(blob)
    if len(data) < 32:
        raise FormatError(f"invalid NCL16 length: {len(data)}")
    return tuple(
        ds_bgr555_to_saturn(struct.unpack_from("<H", data, i * 2)[0], direct=direct)
        for i in range(16)
    )


def _sample_ncg_8bpp(ncg: bytes, tile_id: int, x: int, y: int) -> int:
    off = tile_id * 64 + y * 8 + x
    return ncg[off] if off < len(ncg) else 0


def decode_8bpp_tile_sprite(
    ncg: bytes,
    palette: tuple[int, ...],
    *,
    tiles_x: int,
    tiles_y: int,
    transparent: set[int] | None = None,
    direct: bool = True,
) -> SpriteRgb555:
    """Render a DS 8bpp tile grid (8x8 tiles) into an RGB555 sprite.

    ``palette`` must hold 256 entries. ``transparent`` lists the palette
    indices to leave as 0 (default: just index 0).
    """
    if len(palette) < 256:
        raise FormatError(f"8bpp sprite needs a 256-color palette, got {len(palette)}")
    if transparent is None:
        transparent = {0}
    width, height = tiles_x * 8, tiles_y * 8
    buf = [0] * (width * height)
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            tile_id = ty * tiles_x + tx
            for py in range(8):
                y = ty * 8 + py
                for px in range(8):
                    x = tx * 8 + px
                    ci = _sample_ncg_8bpp(ncg, tile_id, px, py)
                    if ci in transparent or ci >= len(palette):
                        continue
                    raw = palette[ci]
                    if direct:
                        buf[y * width + x] = 0x8000 | (raw & 0x7FFF)
                    else:
                        buf[y * width + x] = raw & 0x7FFF
    return SpriteRgb555(width=width, height=height, pixels=tuple(buf))


def extract_nintendo_logo(fs: Filesystem) -> SpriteRgb555:
    """Decode the real Nintendo boot logo (8bpp 128x16 NSC, red oval + wordmark).

    The NSC is 8bpp, 128 wide x 16 tall. Index 0xF1 is the background
    (transparent), 0x4C the red oval, and 77..255 the red-to-white gradient
    that forms the "Nintendo" wordmark.
    """
    nsc = lz77_auto(fs.read(NINTENDO_LOGO_NSC_PATH))
    width, height = 128, 16
    if len(nsc) < width * height:
        raise FormatError(f"Nintendo logo too small: {len(nsc)}")
    pal = [0] * 256
    pal[76] = 0x7C1F  # red oval (RGB555 r=31, g=0, b=0)
    for i in range(77, 256):
        v = i - 77
        r = 31
        g = min(31, v * 31 // 178)
        b = min(31, v * 31 // 178)
        pal[i] = (r & 31) | ((g & 31) << 5) | ((b & 31) << 10)
    buf = [0] * (width * height)
    for y in range(height):
        for x in range(width):
            v = nsc[y * width + x]
            if v == 0xF1 or v == 0x00 or v >= len(pal):
                continue
            c = pal[v]
            if c:
                buf[y * width + x] = 0x8000 | (c & 0x7FFF)
    return SpriteRgb555(width=width, height=height, pixels=tuple(buf))


def extract_mario64ds_ipl_logo(fs: Filesystem) -> SpriteRgb555:
    """Decode the real MARIO 64 DS IPL logo (8bpp 64x16 NCG + 16-color NCL)."""
    ncg = lz77_auto(fs.read(MARIO64DS_IPL_NCG_PATH))
    ncl16 = decode_ncl_palette16(fs.read(MARIO64DS_IPL_NCL_PATH), direct=False)
    pal = [0] * 256
    for i, c in enumerate(ncl16):
        pal[i] = c
    # The IPL art is 8bpp 8x8 tiles, 8 wide x 2 tall = 64x16.
    return decode_8bpp_tile_sprite(ncg, tuple(pal), tiles_x=8, tiles_y=2, direct=True)
