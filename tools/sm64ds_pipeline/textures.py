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

@dataclass(frozen=True)
class Lut4Texture:
    width: int
    height: int
    lut_slot: int
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


def decode_texture(data: bytes, tex_record: int, pal_record: int, *, material_flags: int=0) -> SourceTexture:
    tdata, tsize = field(data, tex_record + 4, 'II')
    # The game ORs TEXIMAGE_PARAM from the material and texture record.
    # Transparency, wrapping, size and format must all use the same state.
    flags = field(data, tex_record + 0x10, 'I') | material_flags
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


def bake_face(tex: SourceTexture, uv: tuple[tuple[float,float],...], size: int=16, *,
              height: int | None=None, samples: int=1,
              colors: tuple[tuple[float,float,float],...] | None=None) -> BakedTexture:
    """Bake a canonical VDP1 quad: A top-left, B top-right, C bottom-right, D bottom-left."""
    width = size
    h = size if height is None else height
    if len(uv) != 4 or not 8 <= width <= 128 or (width & 7) or not 4 <= h <= 128 or samples not in (1,2,4):
        raise FormatError('VDP1 face bake needs 4 UVs and VDP1-legal dimensions (width multiple of 8)')
    if colors is not None and len(colors) != 4:
        raise FormatError('VDP1 face bake needs 4 corner colors')
    modulate = colors is not None and any(c[0] < 30.99 or c[1] < 30.99 or c[2] < 30.99 for c in colors)
    u0,v0 = uv[0]; u1,v1 = uv[1]; u2,v2 = uv[2]; u3,v3 = uv[3]
    tw, th = tex.width, tex.height
    rep_s, rep_t, flip_s, flip_t = tex.repeat_s, tex.repeat_t, tex.flip_s, tex.flip_t
    tpix = tex.pixels
    if modulate:
        c0, c1, c2, c3 = colors
    rgba=[]
    inv_samples = 1.0 / samples
    inv_w = 1.0 / width
    inv_h = 1.0 / h
    ss = samples * samples
    half_ss = ss // 2
    for y in range(h):
        for x in range(width):
            ar = ag = ab = 0
            alpha = 0
            for sy in range(samples):
                t = (y + (sy + 0.5) * inv_samples) * inv_h
                omt = 1.0 - t
                for sx in range(samples):
                    s = (x + (sx + 0.5) * inv_samples) * inv_w
                    oms = 1.0 - s
                    w00 = oms * omt
                    w10 = s * omt
                    w11 = s * t
                    w01 = oms * t
                    u = w00*u0 + w10*u1 + w11*u2 + w01*u3
                    v = w00*v0 + w10*v1 + w11*v2 + w01*v3
                    px = _wrap(int(u // 1), tw, rep_s, flip_s)
                    py = _wrap(int(v // 1), th, rep_t, flip_t)
                    color = tpix[py * tw + px]
                    ca = color[3]
                    alpha += ca
                    if ca:
                        if modulate:
                            cr = w00*c0[0] + w10*c1[0] + w11*c2[0] + w01*c3[0]
                            cg = w00*c0[1] + w10*c1[1] + w11*c2[1] + w01*c3[1]
                            cb = w00*c0[2] + w10*c1[2] + w11*c2[2] + w01*c3[2]
                            cr = 0.0 if cr < 0.0 else (31.0 if cr > 31.0 else cr)
                            cg = 0.0 if cg < 0.0 else (31.0 if cg > 31.0 else cg)
                            cb = 0.0 if cb < 0.0 else (31.0 if cb > 31.0 else cb)
                            r = int((color[0] * cr + 15.5) / 31.0)
                            g = int((color[1] * cg + 15.5) / 31.0)
                            b = int((color[2] * cb + 15.5) / 31.0)
                            ar += r * ca; ag += g * ca; ab += b * ca
                        else:
                            ar += color[0] * ca; ag += color[1] * ca; ab += color[2] * ca
            if alpha:
                half_a = alpha // 2
                rgba.append(((ar + half_a) // alpha, (ag + half_a) // alpha,
                             (ab + half_a) // alpha, (alpha + half_ss) // ss))
            else:
                rgba.append((0, 0, 0, (alpha + half_ss) // ss))
    return BakedTexture(width, h, tuple(rgba))


def index_bakes(bakes: list[BakedTexture], *, reference_bakes: list[BakedTexture] | None=None) -> tuple[list[IndexedTexture], tuple[int,...], list[int]]:
    """One shared 256-color RGB555 palette. Index 0 is transparent.

    Frequency-based deterministic palette + nearest 5-bit color mapping. No
    hidden dependence on Pillow or a proprietary color table.
    """
    counts: Counter[int] = Counter()
    # Optionally choose the palette from a fixed reference set. Mixed-size
    # face bakes otherwise give larger tiles disproportionate palette weight.
    for tile in bakes if reference_bakes is None else reference_bakes:
        for p in tile.rgba:
            if p[3] >= 128:
                counts[rgba_to_rgb555(p)] += 1
    selected = [v for v,_ in sorted(counts.items(),key=lambda x:(-x[1],x[0]))[:255]]
    # An all-transparent reference cannot represent opaque output pixels.
    if not selected and any(p[3]>=128 for tile in bakes for p in tile.rgba):
        raise FormatError('transparent reference palette cannot represent opaque bakes')
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


def _median_cut_rgb555(counts: dict[int, int], max_colors: int = 15) -> list[int]:
    """Deterministic weighted median-cut quantizer over RGB555 values."""
    if not counts:
        return []
    if len(counts) <= max_colors:
        return sorted(counts.keys())
    items = [((c & 31, (c >> 5) & 31, (c >> 10) & 31), w) for c, w in sorted(counts.items())]

    def box_stats(bucket):
        lo = [31, 31, 31]
        hi = [0, 0, 0]
        total = 0
        for rgb, w in bucket:
            total += w
            for k in range(3):
                if rgb[k] < lo[k]:
                    lo[k] = rgb[k]
                if rgb[k] > hi[k]:
                    hi[k] = rgb[k]
        # Perceptual channel weights (G > R > B) for split priority.
        spans = ((hi[0] - lo[0]) * 3, (hi[1] - lo[1]) * 4, (hi[2] - lo[2]) * 2)
        best_axis = max(range(3), key=lambda k: (spans[k], -k))
        return spans[best_axis] * total, best_axis, bucket

    boxes = [box_stats(items)]
    while len(boxes) < max_colors:
        best_idx = max(range(len(boxes)), key=lambda i: (boxes[i][0], len(boxes[i][2])))
        score, axis, bucket = boxes[best_idx]
        if score == 0 or len(bucket) < 2:
            break
        bucket.sort(key=lambda item: (item[0][axis], item[0]))
        half = sum(w for _, w in bucket) / 2.0
        acc = 0
        split = 1
        for i, (_, w) in enumerate(bucket):
            acc += w
            if acc >= half and i > 0:
                split = i
                break
        if split <= 0 or split >= len(bucket):
            split = len(bucket) // 2
        boxes[best_idx] = box_stats(bucket[:split])
        boxes.append(box_stats(bucket[split:]))

    selected = set()
    for _, _, bucket in boxes:
        total = sum(w for _, w in bucket)
        r = sum(rgb[0] * w for rgb, w in bucket)
        g = sum(rgb[1] * w for rgb, w in bucket)
        b = sum(rgb[2] * w for rgb, w in bucket)
        c = ((r + total // 2) // total) | (((g + total // 2) // total) << 5) | (((b + total // 2) // total) << 10)
        selected.add(c)
    # If two centroids collided, refill with highest-error remaining source colors.
    while len(selected) < max_colors and len(selected) < len(counts):
        sel_rgb = [(c & 31, (c >> 5) & 31, (c >> 10) & 31) for c in selected]
        worst_c = None
        worst_err = -1
        for c, w in counts.items():
            if c in selected:
                continue
            r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
            d = min((r - sr) ** 2 + (g - sg) ** 2 + (b - sb) ** 2 for sr, sg, sb in sel_rgb)
            err = d * w
            if err > worst_err:
                worst_err = err
                worst_c = c
        if worst_c is None:
            break
        selected.add(worst_c)
    return sorted(selected)


def index_bakes_lut4(bakes: list[BakedTexture], *, groups: list | None = None) -> tuple[list[Lut4Texture], tuple[int, ...], int, list[int]]:
    """Quantize baked tiles into VDP1 LUT4 (4-bit) textures with per-group 16-color LUTs.

    Index 0 is transparent (0x0000). Entries 1..15 carry the VDP1 RGB bit (0x8000)
    so LUT4 sprites mix cleanly with indexed8 HUD/palette sprites.
    """
    if groups is None:
        groups = [0] * len(bakes)
    if len(groups) != len(bakes):
        raise FormatError('LUT4 group count must match bake count')
    group_order = sorted(set(groups))
    group_to_slot = {g: slot for slot, g in enumerate(group_order)}
    group_counts: list[Counter[int]] = [Counter() for _ in group_order]
    for tile, g in zip(bakes, groups):
        cnt = group_counts[group_to_slot[g]]
        for p in tile.rgba:
            if p[3] >= 128:
                cnt[rgba_to_rgb555(p)] += 1

    luts: list[int] = []
    lut_selected: list[list[int]] = []
    lut_maps: list[dict[int, int]] = []
    for cnt in group_counts:
        selected = _median_cut_rgb555(cnt, 15)
        lut_selected.append(selected)
        luts.append(0x0000)
        luts.extend(0x8000 | c for c in selected)
        luts.extend([0x0000] * (15 - len(selected)))
        lut_maps.append({c: i + 1 for i, c in enumerate(selected)})

    def nearest_in(slot: int, color: int) -> int:
        mp = lut_maps[slot]
        if color in mp:
            return mp[color]
        selected = lut_selected[slot]
        if not selected:
            return 0
        r, g, b = color & 31, (color >> 5) & 31, (color >> 10) & 31
        best = min(
            range(len(selected)),
            key=lambda i: (
                ((r - (selected[i] & 31)) ** 2) * 3
                + ((g - ((selected[i] >> 5) & 31)) ** 2) * 4
                + ((b - ((selected[i] >> 10) & 31)) ** 2) * 2,
                i,
            ),
        )
        mp[color] = best + 1
        return best + 1

    out: list[Lut4Texture] = []
    faces: list[int] = []
    intern: dict[tuple[int, int, int, bytes], int] = {}
    for tile, g in zip(bakes, groups):
        slot = group_to_slot[g]
        nibbles = [0 if p[3] < 128 else nearest_in(slot, rgba_to_rgb555(p)) for p in tile.rgba]
        if len(nibbles) & 1:
            raise FormatError('LUT4 texture texel count must be even')
        packed = bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))
        key = (tile.width, tile.height, slot, packed)
        if key not in intern:
            intern[key] = len(out)
            out.append(Lut4Texture(tile.width, tile.height, slot, packed))
        faces.append(intern[key])
    return out, tuple(luts), len(group_order), faces
