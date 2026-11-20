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


@dataclass(frozen=True)
class SpriteRgb555:
    width: int
    height: int
    pixels: tuple[int, ...]  # Saturn BGR555 with bit 15 set, or 0 for transparent


@dataclass(frozen=True)
class CloudAtlas4bpp:
    width: int
    height: int
    pixels: bytes  # 4bpp packed (2 pixels/byte, low nibble=left? No: Saturn high nibble=left)
    palette: tuple[int, ...]  # 16 Saturn BGR555 CRAM words (without bit 15)


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
    """Extract SM64DS volumetric clouds (256x128 4bpp, Saturn nibble order) + 16-color CRAM palette."""
    ncg = lz77_auto(fs.read(CLOUD_OBJ_NCG_PATH))
    pals = decode_ncl_palettes(fs.read(CLOUD_OBJ_NCL_PATH), direct=False)
    # 512 4bpp tiles laid out 32 tiles wide x 16 tiles high = 256x128
    width, height = 256, 128
    packed = bytearray((width * height) // 2)
    for y in range(height):
        ty = y >> 3
        sy = y & 7
        for x in range(0, width, 2):
            tx = x >> 3
            sx0 = x & 7
            tile_id = ty * 32 + tx
            c0 = _sample_ncg_4bpp(ncg, tile_id, sx0, sy)
            c1 = _sample_ncg_4bpp(ncg, tile_id, sx0 + 1, sy)
            # Saturn 4bpp order: high nibble = left pixel, low nibble = right pixel
            packed[(y * width + x) >> 1] = ((c0 & 0xF) << 4) | (c1 & 0xF)
    return CloudAtlas4bpp(width=width, height=height, pixels=bytes(packed), palette=pals[0])
