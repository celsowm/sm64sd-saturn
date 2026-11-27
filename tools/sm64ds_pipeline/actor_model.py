"""Bake one DS actor model into a generated C file (a `sm64ds_actor_kind_t`).

The model is posed at its rest skeleton, quad-merged and LUT4-baked, then
every placement of that actor kind in a stage shares it. One file per kind:
`actor_<name>.c`, exporting `actor_kind_<name>`.
"""
from __future__ import annotations
import math
from .adaptive_bake import adaptive_lut4_bakes
from .bmd import convert_bmd
from .quad_merge import merge_coplanar_quads
from .skinning import mv, rest_world


def _fx(v):
    r = round(v * 65536)
    if not -2**31 <= r < 2**31:
        raise ValueError('fixed-point overflow')
    return r


def _vec(v):
    return '{' + ','.join(str(_fx(c)) for c in v) + '}'


def _rows(values, size=16):
    return '\n'.join(','.join(str(v) for v in values[i:i + size]) + ',' for i in range(0, len(values), size))


def _hex_rows(values, size=12):
    return '\n'.join(','.join(f'0x{v:04x}' for v in values[i:i + size]) + ',' for i in range(0, len(values), size))


def _area(vs, f):
    def tri(a, b, c):
        e = [b[i] - a[i] for i in range(3)]
        g = [c[i] - a[i] for i in range(3)]
        x, y, z = e[1]*g[2]-e[2]*g[1], e[2]*g[0]-e[0]*g[2], e[0]*g[1]-e[1]*g[0]
        return 0.5 * math.sqrt(x*x + y*y + z*z)
    a = tri(vs[f[0]], vs[f[1]], vs[f[2]])
    if f[2] != f[3]:
        a += tri(vs[f[0]], vs[f[2]], vs[f[3]])
    return a


def bake_actor(fs, name, bmd_path, placements, *, scale=0.5, byte_budget=6144, max_size=24,
               max_depth=280, one_sided=True, behavior=0, speed=0.0, range_=0.0, radius=0.0, fuse_steps=0, blast=0.0, hp=0, top=0.0, stun_steps=0, unlock_by='', coin_value=0, star_bit=0):
    """Return (C source, report). `placements` = [(x, y, z, yaw_deg)] in Saturn units."""
    bmd = convert_bmd(fs.read(bmd_path))
    rw = rest_world(bmd)
    verts = []
    # Billboard bones (BMD bone flag): the DS turns their geometry to face the
    # camera. Keep each such vertex's bone pivot and its offset in the bone's
    # XY plane; the runtime rebuilds the vertex from the camera axes.
    billboard = []   # (vertex index, pivot xyz, offset xy)
    for vi, v in enumerate(bmd.vertices):
        p = tuple(c * (1 << bmd.scale_shift) / 4096.0 for c in (v.x, v.y, v.z))
        if v.joint < len(bmd.bones):
            lin, tr = rw[v.joint]
            if bmd.bones[v.joint].billboard:
                sx = math.sqrt(sum(lin[r][0] ** 2 for r in range(3)))
                sy = math.sqrt(sum(lin[r][1] ** 2 for r in range(3)))
                billboard.append((vi, tuple(c * scale for c in tr),
                                  (p[0] * sx * scale, p[1] * sy * scale)))
            p = tuple(a + b for a, b in zip(mv(lin, p), tr))
        verts.append(tuple(c * scale for c in p))
    if behavior in (5, 6):
        # Sprite kinds: a camera-facing quad from the model's XZ footprint.
        xs = [v[0] for v in verts]; ys = [v[1] for v in verts]
        x0, x1 = min(xs) - 2.0, max(xs) + 2.0
        y0, y1 = min(ys), max(ys) + 24.0 * scale
        verts = [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)]
        faces = [(0, 1, 2, 3)]
        uvs = [[(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]]
        mats = [0]
        cols = [[(255, 255, 255, 255)] * 4]
        srcs = [bmd.material_textures[0]]
        texs, luts, lut_count, ftex, _ = adaptive_lut4_bakes(
            srcs, uvs, mats, colors=cols, byte_budget=byte_budget, samples=2,
            face_areas=[_area(verts, f) for f in faces], max_size=max_size)
        billboard = []   # the sprite quad replaces the model's vertices
    else:
        faces, uvs, mats, cols, _, _ = merge_coplanar_quads(
            verts, bmd.faces, bmd.face_uvs, bmd.face_materials, colors=bmd.face_colors)
        srcs = [bmd.material_textures[m] for m in mats]
        texs, luts, lut_count, ftex, _ = adaptive_lut4_bakes(
            srcs, uvs, mats, colors=cols, byte_budget=byte_budget, samples=2,
            face_areas=[_area(verts, f) for f in faces], max_size=max_size)
    n, V, F, T = len(placements), len(verts), len(faces), len(texs)
    unlock_decl = f'extern sm64ds_actor_kind_t actor_kind_{unlock_by.lower()};' if unlock_by else ''
    unlock_init = f'.unlock=&actor_kind_{unlock_by.lower()}.defeated,' if unlock_by else ''
    star_init = f'.star_bit={star_bit},' if star_bit else ''
    c = [f'/* Generated actor kind {name} from {bmd_path}. Private ROM data. */',
         '#include "sm64ds_actors.h"', unlock_decl,
         f'static const sat_vec3_t {name}_vertices[]={{', ',\n'.join(_vec(v) for v in verts), '};',
         f'static const uint16_t {name}_faces[]={{', _rows([i for f in faces for i in f]), '};']
    for i, t in enumerate(texs):
        c += [f'static const uint8_t {name}_pixels_{i}[]={{', _rows(t.pixels), '};']
    c += [f'static const sat_model_texture_asset_t {name}_textures[]={{']
    c += [f'{{.pixels={name}_pixels_{i},.width={t.width},.height={t.height},.palette_slot={t.lut_slot},'
          f'.flags=SAT_MODEL_TEXTURE_LUT4,.pixel_count={t.width * t.height}}},' for i, t in enumerate(texs)]
    c += ['};', f'static const uint16_t {name}_luts[]={{', _hex_rows(luts), '};',
          f'static const uint16_t {name}_face_textures[]={{', _rows(ftex), '};',
          f'static const sat_model_asset_t {name}_model={{.vertices={name}_vertices,.vertex_count={V},'
          f'.indices={name}_faces,.face_count={F},.face_texture_indices={name}_face_textures,'
          f'.textures={name}_textures,.texture_count={T},.palettes_rgb555=0,.palette_count=0,'
          f'.palette_base=0,.luts_rgb555={name}_luts,.lut_count={lut_count}}};']
    if billboard:
        c += [f'static const uint16_t {name}_bb_index[]={{', _rows([b[0] for b in billboard]), '};',
              f'static const sat_vec3_t {name}_bb_pivot[]={{', ',\n'.join(_vec(b[1]) for b in billboard), '};',
              f'static const int32_t {name}_bb_offset[]={{',
              _rows([_fx(o) for b in billboard for o in b[2]]), '};']
        bb_init = (f'.bb_count={len(billboard)},.bb_index={name}_bb_index,'
                   f'.bb_pivot={name}_bb_pivot,.bb_offset={name}_bb_offset,')
    else:
        bb_init = ''
    c += [f'static const sat_vec3_t {name}_positions[]={{', ',\n'.join(_vec(p[:3]) for p in placements), '};',
          f'static const int16_t {name}_yaw[]={{', _rows([p[3] for p in placements]), '};',
          f'static sat_vec3_t {name}_v[{V}],{name}_w[{V}];',
          f'static uint16_t {name}_idx[{F * 4}],{name}_fm[{F}];',
          f'static sat_vdp1_texture_t {name}_tex[{T}];',
          f'static sat_scene3d_material_t {name}_mat[{T}];',
          f'static sat_projected_vertex_t {name}_proj[{V}];',
          f'static sat_scene3d_material_program_t {name}_prog[{T}];',
          f'static sat_mat4_t {name}_worlds[{n}];',
          f'static sat_vec3_t {name}_pos[{n}];static int16_t {name}_yawv[{n}];',
          f'static uint8_t {name}_st[{n}];static uint16_t {name}_tm[{n}];',
          f'static int32_t {name}_vx[{n}],{name}_vy[{n}],{name}_vz[{n}];',
          f'sm64ds_actor_kind_t actor_kind_{name}={{',
          f'.name="{name}",.model=&{name}_model,.positions={name}_positions,.yaw_deg={name}_yaw,.count={n},',
          f'.one_sided={int(one_sided)},.max_depth={max_depth},',
          f'.v={name}_v,.w={name}_w,.idx={name}_idx,.fm={name}_fm,.tex={name}_tex,.mat={name}_mat,',
          f'.proj={name}_proj,.prog={name}_prog,.worlds={name}_worlds,.vcap={V},.fcap={F},.tcap={T},',
          f'.behavior={behavior},.speed={_fx(speed)},.range={_fx(range_)},.radius={_fx(radius)},.fuse_steps={fuse_steps},.blast={_fx(blast)},.hp={hp},.top={_fx(top)},.stun_steps={stun_steps},.coin_value={coin_value},{star_init}{unlock_init}{bb_init}',
          f'.pos={name}_pos,.yaw_live={name}_yawv,.st={name}_st,.tm={name}_tm,'
          f'.vx={name}_vx,.vy={name}_vy,.vz={name}_vz}};', '']
    return '\n'.join(c), {'kind': name, 'bmd': bmd_path, 'count': n, 'vertices': V, 'faces': F,
                          'textures': T, 'billboard_vertices': len(billboard), 'texture_bytes': lut_count * 32 + sum(len(t.pixels) for t in texs)}
