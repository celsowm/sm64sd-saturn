"""Cylindrical sky panorama for a VDP2 bitmap layer.

The camera-relative vrbox mesh is ray cast from its origin into a
`width` x `height` 256-colour bitmap. Column u looks along azimuth
theta = -2*pi*u/width (world direction (sin theta, ., cos theta)), so the
column grows with screen x for LibSaturn's look_at (right = forward x up).
Row v looks at tan(elevation) = (horizon - v - 0.5) / focal with
focal = width / (2*pi), i.e. one bitmap pixel per screen pixel at zoom
focal_screen / focal. Rows outside [band_first, band_first + band_rows)
repeat the band's edge rows on the Saturn, so only the band is stored,
SLZ1-compressed (LibSaturn tools/satlz.py, decoded by sat_lz_decode).
"""
from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path

from .bmd import Model
from .common import FormatError
from .textures import _wrap


def _load_satlz(prefix: Path | None):
    candidates = []
    if prefix is not None:
        candidates.append(prefix / 'share/libsaturn/tools/satlz.py')
    env = os.environ.get('LIBSATURN_PREFIX')
    if env:
        candidates.append(Path(env) / 'share/libsaturn/tools/satlz.py')
    dev = Path(__file__).resolve().parents[3]
    candidates.append(dev / 'saturn-prefix/share/libsaturn/tools/satlz.py')
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location('satlz', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FormatError('sky panorama needs LibSaturn tools/satlz.py (set LIBSATURN_PREFIX)')


def bake_panorama(model: Model, width: int, height: int, horizon: float,
                  samples: int = 2):
    """RGB rows (lists of (r, g, b) 0..255) of the full width x height panorama."""
    try:
        import numpy as np
    except ImportError as exc:
        raise FormatError('sky panorama baking needs numpy') from exc
    focal = width / (2.0 * math.pi)
    verts = np.array([(v.x, v.y, v.z) for v in model.vertices], float)
    sub = (np.arange(samples) + 0.5) / samples
    us = (np.arange(width)[:, None] + sub[None, :]).reshape(-1)
    vs = (np.arange(height)[:, None] + sub[None, :]).reshape(-1)
    theta = -2.0 * math.pi * us / width
    tan_el = (horizon - vs) / focal
    rays = np.empty((len(vs), len(us), 3))
    rays[:, :, 0] = np.sin(theta)[None, :]
    rays[:, :, 1] = tan_el[:, None]
    rays[:, :, 2] = np.cos(theta)[None, :]
    rays = rays.reshape(-1, 3)
    nearest = np.full(len(rays), np.inf)
    colour = np.zeros((len(rays), 3))
    for face, uv, material in zip(model.faces, model.face_uvs, model.face_materials):
        tex = model.material_textures[material] if material < len(model.material_textures) else None
        if tex is None:
            continue
        texels = np.array([p[:3] for p in tex.pixels], float)
        for tri in ((0, 1, 2), (0, 2, 3)):
            a, b, c = (verts[face[i]] for i in tri)
            if np.allclose(b, c) or np.allclose(a, b) or np.allclose(a, c):
                continue
            ua, ub, uc = (np.array(uv[i], float) for i in tri)
            e1, e2 = b - a, c - a
            p = np.cross(rays, e2)
            det = p @ e1
            valid = np.abs(det) > 1e-9
            inv = np.where(valid, 1.0 / np.where(valid, det, 1.0), 0.0)
            origin = -a
            s = (p @ origin) * inv
            q = np.cross(origin, e1)
            t = (rays @ q) * inv
            dist = (q @ e2) * inv
            hit = valid & (s >= 0) & (t >= 0) & (s + t <= 1) & (dist > 0) & (dist < nearest)
            if not hit.any():
                continue
            idx = np.nonzero(hit)[0]
            nearest[idx] = dist[idx]
            tu = ua[0] + s[idx] * (ub[0] - ua[0]) + t[idx] * (uc[0] - ua[0])
            tv = ua[1] + s[idx] * (ub[1] - ua[1]) + t[idx] * (uc[1] - ua[1])
            px = np.array([_wrap(int(x), tex.width, tex.repeat_s, tex.flip_s) for x in np.floor(tu)])
            py = np.array([_wrap(int(y), tex.height, tex.repeat_t, tex.flip_t) for y in np.floor(tv)])
            colour[idx] = texels[py * tex.width + px]
    if not np.isfinite(nearest).all():
        raise FormatError('sky panorama: some directions miss the skybox mesh')
    colour = colour.reshape(height, samples, width, samples, 3).mean(axis=(1, 3))
    return np.clip(np.rint(colour), 0, 255).astype('uint8')


def emit_sky_panorama(model: Model, name: str, *, width: int = 512, height: int = 512,
                      horizon: int = 256, tan_top: float = 1.10, tan_bottom: float = -1.0,
                      libsaturn_prefix: Path | None = None) -> tuple[str, str, dict]:
    if (width, height) not in ((512, 256), (512, 512), (1024, 256), (1024, 512)):
        raise FormatError('VDP2 bitmap must be 512x256, 512x512, 1024x256 or 1024x512')
    try:
        from PIL import Image
    except ImportError as exc:
        raise FormatError('sky panorama needs Pillow') from exc
    satlz = _load_satlz(libsaturn_prefix)
    focal = width / (2.0 * math.pi)
    first = max(0, int(math.floor(horizon - tan_top * focal)))
    last = min(height, int(math.ceil(horizon - tan_bottom * focal)))
    rgb = bake_panorama(model, width, height, horizon)[first:last]
    image = Image.fromarray(rgb, 'RGB').quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                                                 dither=Image.Dither.NONE)
    indices = image.tobytes()
    palette = image.getpalette()[:256 * 3]
    palette += [0] * (256 * 3 - len(palette))
    rgb555 = [(palette[i] >> 3) | ((palette[i + 1] >> 3) << 5) | ((palette[i + 2] >> 3) << 10)
              for i in range(0, 256 * 3, 3)]
    packed = satlz.compress(indices)
    prefix = name.upper()
    header = '\n'.join([
        '#pragma once', '#include <stdint.h>',
        f'#define {prefix}_WIDTH {width}u',
        f'#define {prefix}_HEIGHT {height}u',
        f'#define {prefix}_HORIZON_ROW {horizon}u',
        f'#define {prefix}_BAND_FIRST {first}u',
        f'#define {prefix}_BAND_ROWS {last - first}u',
        f'/* Bitmap pixels per radian of azimuth (width / 2pi), 16.16. */',
        f'#define {prefix}_FOCAL_FX16 {round(focal * 65536)}',
        f'#define {prefix}_LZ_BYTES {len(packed)}u',
        f'extern const uint8_t {name}_lz[{prefix}_LZ_BYTES];',
        f'extern const uint16_t {name}_palette[256];', ''])
    code = [f'#include "{name}.h"', '',
            '/* Private, ROM-derived generated data.  Never commit this file. */', '',
            f'const uint8_t {name}_lz[{prefix}_LZ_BYTES] __attribute__((aligned(4))) = {{']
    code.extend('    ' + ', '.join(f'0x{b:02x}' for b in packed[i:i + 16]) + ','
                for i in range(0, len(packed), 16))
    code.extend(['};', '', f'const uint16_t {name}_palette[256] = {{'])
    code.extend('    ' + ', '.join(f'0x{x:04x}' for x in rgb555[i:i + 12]) + ','
                for i in range(0, 256, 12))
    code.extend(['};', ''])
    report = {'output': name, 'kind': 'vdp2-cylindrical-sky', 'width': width, 'height': height,
              'horizon_row': horizon, 'band_first': first, 'band_rows': last - first,
              'band_bytes': len(indices), 'lz_bytes': len(packed),
              'focal_px_per_radian': focal}
    return header, '\n'.join(code), report
