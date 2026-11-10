"""BMD texture decoding (DS formats 1..7) and VDP1 per-face UV baking.

The source DS 4x4 tiles are unpacked before sampling. VDP1 has no generic UV
interpolator: every emitted face gets a baked canonical texture; identical
rectangles are interned. All assets remain local and are never checked in.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from .common import field, region, FormatError

RGBA = tuple[int, int, int, int]

@dataclass(frozen=True)
class SourceTexture:
    width: int
    height: int
    pixels: tuple[RGBA, ...]
    repeat_s: bool = False
    repeat_t: bool = False
    flip_s: bool = False
    flip_t: bool = False

@dataclass(frozen=True)
class BakedTexture:
    width: int
    height: int
    rgba: tuple[RGBA, ...]

@dataclass(frozen=True)
class IndexedTexture:
    width: int
    height: int
    pixels: bytes


def rgb555_to_rgba(c: int, alpha: int = 255) -> RGBA:
    return (((c & 31) * 255 + 15) // 31,
            (((c >> 5) & 31) * 255 + 15) // 31,
            (((c >> 10) & 31) * 255 + 15) // 31, alpha)


def rgba_to_rgb555(rgba: RGBA) -> int:
    r, g, b, _ = rgba
    return ((r * 31 + 127) // 255) | (((g * 31 + 127) // 255) << 5) | (((b * 31 + 127) // 255) << 10)


def blend555(a: int, b: int, wa: int, wb: int) -> int:
    # Matches upstream texture.cpp integer channel interpolation in eighths.
    return ((a & 31) * wa + (b & 31) * wb) // 8 | \
           (((((a >> 5) & 31) * wa + ((b >> 5) & 31) * wb) // 8) << 5) | \
           (((((a >> 10) & 31) * wa + ((b >> 10) & 31) * wb) // 8) << 10)


def decode_texture(data: bytes, tex_record: int, pal_record: int) -> SourceTexture:
    tdata, tsize = field(data, tex_record + 4, 'II')
    flags = field(data, tex_record + 0x10, 'I')
    pdata, psize = field(data, pal_record + 4, 'II')
    fmt = (flags >> 26) & 7
    width, height = 8 << ((flags >> 20) & 7), 8 << ((flags >> 23) & 7)
    if width * height > 262144 or fmt not in range(1, 8):
        raise FormatError(f'unsupported source texture size/format {width}x{height} format {fmt}')
    pixels = region(data, tdata, tsize)
    palette = region(data, pdata, psize)
    n = width * height
    def p(idx: int) -> int:
        offset = 2 * idx
        # Matches Nitro's out-of-range palette lookup on real castle assets:
        # a BMD may contain unused 4x4 palette references beyond its table.
        return field(palette, offset, 'H') if offset + 2 <= len(palette) else 0
    def color(idx: int, alpha: int = 255) -> RGBA:
        return rgb555_to_rgba(p(idx), alpha)
    out: list[RGBA] = []
    transparent = bool(flags & (1 << 29))
    if fmt in (1, 2, 3, 4, 6, 7):
        sizes = {1:n, 2:(n+3)//4, 3:(n+1)//2, 4:n, 6:n, 7:n*2}
        if len(pixels) < sizes[fmt]:
            raise FormatError(f'truncated DS texture format {fmt}')
        for i in range(n):
            if fmt == 1:
                v = pixels[i]; out.append(color(v & 31, (v >> 5) * 255 // 7))
            elif fmt == 2:
                idx = (pixels[i // 4] >> ((i % 4) * 2)) & 3
                out.append(color(idx, 0 if transparent and idx == 0 else 255))
            elif fmt == 3:
                idx = (pixels[i // 2] >> ((i & 1) * 4)) & 15
                out.append(color(idx, 0 if transparent and idx == 0 else 255))
            elif fmt == 4:
                idx = pixels[i]
                out.append(color(idx, 0 if transparent and idx == 0 else 255))
            elif fmt == 6:
                v = pixels[i]; out.append(color(v & 7, (v >> 3) * 255 // 31))
            else:
                v = pixels[2 * i] | pixels[2 * i + 1] << 8
                out.append(rgb555_to_rgba(v, 255 if v & 0x8000 else 0))
    elif fmt == 5:
        # Each 4x4 block uses four bytes of 2-bit indices plus a uint16 palette
        # descriptor stored immediately after all tile pixels in this BMD.
        need = n // 4
        tile_table = region(data, tdata + tsize, need // 2)
        if len(pixels) < need:
            raise FormatError('truncated DS 4x4 block pixels')
        out = [(0,0,0,0)] * n
        for by in range(height // 4):
            for bx in range(width // 4):
                block = by * (width // 4) + bx
                texels = int.from_bytes(pixels[4*block:4*block+4], 'little')
                info = field(tile_table, block * 2, 'H')
                base = (info & 0x3fff) * 2
                mode = info >> 14
                c0, c1 = p(base), p(base+1)
                if mode == 0:
                    colors = (color(base), color(base+1), color(base+2), (0,0,0,0))
                elif mode == 1:
                    colors = (color(base), color(base+1), rgb555_to_rgba(blend555(c0,c1,4,4)), (0,0,0,0))
                elif mode == 2:
                    colors = (color(base), color(base+1), color(base+2), color(base+3))
                else:
                    colors = (color(base), color(base+1), rgb555_to_rgba(blend555(c0,c1,5,3)),
                              rgb555_to_rgba(blend555(c0,c1,3,5)))
                for dy in range(4):
                    for dx in range(4):
                        idx = (texels >> (2 * (dy*4+dx))) & 3
                        out[(by*4+dy) * width + bx*4+dx] = colors[idx]
    return SourceTexture(width,height,tuple(out),bool(flags & 0x10000),bool(flags & 0x20000),
                         bool(flags & 0x40000),bool(flags & 0x80000))


def _wrap(v: int, n: int, repeat: bool, flip: bool) -> int:
    if not repeat:
        return max(0,min(n-1,v))
    cell = v // n
    out = v % n
    return n - 1 - out if flip and (cell & 1) else out


def bake_face(tex: SourceTexture, uv: tuple[tuple[float,float],...], size: int=16) -> BakedTexture:
    """Bake a canonical VDP1 quad: A top-left, B top-right, C bottom-right, D bottom-left."""
    if len(uv) != 4 or not 8 <= size <= 128 or size & 7:
        raise FormatError('VDP1 face bake needs 4 UVs and a width multiple of eight')
    rgba=[]
    for y in range(size):
        t = (y + .5) / size
        for x in range(size):
            s = (x + .5) / size
            u = ((1-s)*(1-t)*uv[0][0] + s*(1-t)*uv[1][0] + s*t*uv[2][0] + (1-s)*t*uv[3][0])
            v = ((1-s)*(1-t)*uv[0][1] + s*(1-t)*uv[1][1] + s*t*uv[2][1] + (1-s)*t*uv[3][1])
            px = _wrap(int(u//1),tex.width,tex.repeat_s,tex.flip_s)
            py = _wrap(int(v//1),tex.height,tex.repeat_t,tex.flip_t)
            rgba.append(tex.pixels[py*tex.width+px])
    return BakedTexture(size,size,tuple(rgba))


def index_bakes(bakes: list[BakedTexture]) -> tuple[list[IndexedTexture], tuple[int,...], list[int]]:
    """One shared 256-color RGB555 palette. Index 0 is transparent.

    Frequency-based deterministic palette + nearest 5-bit color mapping. No
    hidden dependence on Pillow or a proprietary color table.
    """
    counts: Counter[int] = Counter()
    for tile in bakes:
        for p in tile.rgba:
            if p[3] >= 128:
                counts[rgba_to_rgb555(p)] += 1
    selected = [v for v,_ in sorted(counts.items(),key=lambda x:(-x[1],x[0]))[:255]]
    selected.sort()
    palette = [0] + selected + [0] * (255-len(selected))
    mapping = {color:i+1 for i,color in enumerate(selected)}
    def nearest(color: int) -> int:
        if color in mapping:
            return mapping[color]
        r,g,b=color&31,(color>>5)&31,(color>>10)&31
        best=min(range(len(selected)),key=lambda i:((r-(selected[i]&31))**2 +
                  (g-((selected[i]>>5)&31))**2 + (b-((selected[i]>>10)&31))**2,i))
        mapping[color]=best+1
        return best+1
    out=[]; faces=[]; intern={}
    for tile in bakes:
        raw=bytes(0 if p[3]<128 else nearest(rgba_to_rgb555(p)) for p in tile.rgba)
        key=(tile.width,tile.height,raw)
        if key not in intern:
            intern[key]=len(out)
            out.append(IndexedTexture(tile.width,tile.height,raw))
        faces.append(intern[key])
    return out, tuple(palette), faces
