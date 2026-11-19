#!/usr/bin/env python3
"""Prepare a private, full-detail castle walking scene from a local ROM."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.cli import main as convert
from sm64ds_pipeline.kcl import decode_kcl
from sm64ds_pipeline.skybox import emit_skybox
from sm64ds_pipeline.textures import bake_face, index_bakes, index_bakes_lut4, BakedTexture
from sm64ds_pipeline.subdivide import split_large_faces
from sm64ds_pipeline.sdk_split import split_nearby
from sm64ds_pipeline.quad_merge import merge_coplanar_quads
from sm64ds_pipeline.adaptive_bake import adaptive_bakes, adaptive_lut4_bakes
from sm64ds_pipeline.support_planes import support_planes
from sm64ds_pipeline.level_objects import extract_castle_props


def fx(value):
    result = round(value * 65536)
    if not -2**31 <= result < 2**31:
        raise ValueError('fixed-point overflow')
    return result


def vec(value):
    return '{' + ','.join(str(fx(v)) for v in value) + '}'


def array(values, size=16):
    return '\n'.join(','.join(str(v) for v in values[i:i + size]) + ',' for i in range(0, len(values), size))


def hex_array(values, size=12):
    return '\n'.join(','.join(f'0x{v:04x}' for v in values[i:i + size]) + ',' for i in range(0, len(values), size))


def _build_castle_props(fs: Filesystem):
    """Extract Castle Grounds billboard trees and wooden signs as compact LUT4 assets."""
    trees, signs = extract_castle_props(fs)

    # Billboard tree: derive exact world quad extents from bomb_tree.bmd at 0.5x actor scale
    # and crop transparent horizontal/vertical margins to an 8-aligned VDP1 LUT4 sprite.
    tree_bmd = convert_bmd(fs.read('data/normal_obj/tree/bomb_tree.bmd'))
    tt = tree_bmd.material_textures[0]
    if tt is None:
        raise ValueError('bomb_tree.bmd is missing its texture')
    opaque_xs = [x for y in range(tt.height) for x in range(tt.width) if tt.pixels[y * tt.width + x][3] >= 128]
    opaque_ys = [y for y in range(tt.height) for x in range(tt.width) if tt.pixels[y * tt.width + x][3] >= 128]
    u0 = (min(opaque_xs) // 8) * 8
    u1 = min(tt.width, ((max(opaque_xs) + 8) // 8) * 8)
    w_crop = u1 - u0
    if w_crop % 8 != 0:
        u0 = max(0, u1 - ((w_crop // 8) * 8))
        w_crop = u1 - u0
    v0 = min(opaque_ys)
    v1 = max(opaque_ys) + 1
    h_crop = v1 - v0

    # Derive texel-to-world scale directly from face 0 of bomb_tree.bmd (actor scale = 0.5).
    tverts = [tuple(c * (1 << tree_bmd.scale_shift) * 0.5 / 4096.0 for c in (v.x, v.y, v.z))
              for v in tree_bmd.vertices]
    f0 = tree_bmd.faces[0]
    uv0 = tree_bmd.face_uvs[0]
    p_base, p_apex, p_right = tverts[f0[0]], tverts[f0[1]], tverts[f0[2]]
    dx_du = (p_right[0] - p_base[0]) / (uv0[2][0] - uv0[0][0])
    dy_dv = (p_apex[1] - p_base[1]) / (uv0[0][1] - uv0[1][1])
    u_center = uv0[0][0]
    v_bottom = uv0[0][1]
    tree_left = (u0 - u_center) * dx_du
    tree_right = (u1 - u_center) * dx_du
    tree_bottom = (v_bottom - v1) * dy_dv
    tree_top = (v_bottom - v0) * dy_dv

    crop_px = tuple(tt.pixels[y * tt.width + x] for y in range(v0, v1) for x in range(u0, u1))
    tree_texs, tree_luts, tree_lut_cnt, _ = index_bakes_lut4([BakedTexture(w_crop, h_crop, crop_px)], groups=[0])
    tree_bytes = tree_lut_cnt * 32 + len(tree_texs[0].pixels)

    # Wooden signpost: obj_tatefuda.bmd at 0.5x actor scale, quad-merged and LUT4-baked.
    sign_bmd = convert_bmd(fs.read('data/normal_obj/obj_tatefuda/obj_tatefuda.bmd'))
    sverts = [tuple(c * (1 << sign_bmd.scale_shift) * 0.5 / 4096.0 for c in (v.x, v.y, v.z))
              for v in sign_bmd.vertices]
    sfaces, suvs, smats, scols, _, _ = merge_coplanar_quads(
        sverts, sign_bmd.faces, sign_bmd.face_uvs, sign_bmd.face_materials, colors=sign_bmd.face_colors
    )
    ssrcs = [sign_bmd.material_textures[mat] for mat in smats]
    sareas = [_face_area(sverts, f) for f in sfaces]
    stexs, sluts, slut_cnt, sftexs, _ = adaptive_lut4_bakes(
        ssrcs, suvs, smats, colors=scols, byte_budget=2560, samples=2, face_areas=sareas, max_size=32
    )
    sign_bytes = slut_cnt * 32 + sum(len(t.pixels) for t in stexs)

    h_lines = [
        '#define CASTLE_PROPS_AVAILABLE 1',
        f'#define CASTLE_TREE_COUNT {len(trees)}u',
        f'#define CASTLE_TREE_LEFT {fx(tree_left)}',
        f'#define CASTLE_TREE_RIGHT {fx(tree_right)}',
        f'#define CASTLE_TREE_BOTTOM {fx(tree_bottom)}',
        f'#define CASTLE_TREE_TOP {fx(tree_top)}',
        'extern const sat_model_asset_t castle_tree_model;',
        'extern const sat_vec3_t castle_tree_positions[CASTLE_TREE_COUNT];',
        f'#define CASTLE_SIGN_COUNT {len(signs)}u',
        f'#define CASTLE_SIGN_VERTEX_COUNT {len(sverts)}u',
        f'#define CASTLE_SIGN_FACE_COUNT {len(sfaces)}u',
        f'#define CASTLE_SIGN_TEXTURE_COUNT {len(stexs)}u',
        'extern const sat_model_asset_t castle_sign_model;',
        'extern const sat_vec3_t castle_sign_positions[CASTLE_SIGN_COUNT];',
        'extern const int16_t castle_sign_yaw_deg[CASTLE_SIGN_COUNT];',
    ]

    t0 = tree_texs[0]
    c_lines = [
        'static const sat_vec3_t tree_vertices[4]={',
        f'{vec((tree_left, tree_top, 0.0))},{vec((tree_right, tree_top, 0.0))},',
        f'{vec((tree_right, tree_bottom, 0.0))},{vec((tree_left, tree_bottom, 0.0))}',
        '};',
        'static const uint16_t tree_faces[4]={0,1,2,3};',
        'static const uint16_t tree_face_textures[1]={0};',
        'static const uint8_t tree_pixels_0[]={', array(t0.pixels), '};',
        'static const sat_model_texture_asset_t tree_textures[1]={',
        f'{{.pixels=tree_pixels_0,.width={t0.width},.height={t0.height},'
        f'.palette_slot={t0.lut_slot},.flags=SAT_MODEL_TEXTURE_LUT4,.pixel_count={t0.width * t0.height}}},',
        '};',
        'static const uint16_t tree_luts[]={', hex_array(tree_luts), '};',
        'const sat_model_asset_t castle_tree_model={.vertices=tree_vertices,.vertex_count=4,'
        '.indices=tree_faces,.face_count=1,.face_texture_indices=tree_face_textures,'
        '.textures=tree_textures,.texture_count=1,.palettes_rgb555=0,.palette_count=0,'
        f'.palette_base=0,.luts_rgb555=tree_luts,.lut_count={tree_lut_cnt}}};',
        'const sat_vec3_t castle_tree_positions[CASTLE_TREE_COUNT]={',
        ',\n'.join(vec(t.position) for t in trees),
        '};',
        'static const sat_vec3_t sign_vertices[]={',
        ',\n'.join(vec(v) for v in sverts),
        '};',
        'static const uint16_t sign_faces[]={',
        array([i for f in sfaces for i in f]),
        '};',
    ]
    for i, t in enumerate(stexs):
        c_lines.extend([f'static const uint8_t sign_pixels_{i}[]={{', array(t.pixels), '};'])
    c_lines.append('static const sat_model_texture_asset_t sign_textures[]={')
    for i, t in enumerate(stexs):
        c_lines.append(
            f'{{.pixels=sign_pixels_{i},.width={t.width},.height={t.height},'
            f'.palette_slot={t.lut_slot},.flags=SAT_MODEL_TEXTURE_LUT4,.pixel_count={t.width * t.height}}},'
        )
    c_lines += [
        '};',
        'static const uint16_t sign_luts[]={', hex_array(sluts), '};',
        'static const uint16_t sign_face_textures[]={', array(sftexs), '};',
        f'const sat_model_asset_t castle_sign_model={{.vertices=sign_vertices,.vertex_count={len(sverts)},'
        f'.indices=sign_faces,.face_count={len(sfaces)},.face_texture_indices=sign_face_textures,'
        f'.textures=sign_textures,.texture_count={len(stexs)},.palettes_rgb555=0,.palette_count=0,'
        f'.palette_base=0,.luts_rgb555=sign_luts,.lut_count={slut_cnt}}};',
        'const sat_vec3_t castle_sign_positions[CASTLE_SIGN_COUNT]={',
        ',\n'.join(vec(s.position) for s in signs),
        '};',
        'const int16_t castle_sign_yaw_deg[CASTLE_SIGN_COUNT]={',
        array([s.yaw_deg for s in signs]),
        '};',
    ]
    return h_lines, c_lines, {
        'castle_tree_count': len(trees),
        'castle_sign_count': len(signs),
        'castle_tree_texture_bytes': tree_bytes,
        'castle_sign_texture_bytes': sign_bytes,
    }


def _face_area(vertices, face):
    p0, p1, p2 = vertices[face[0]], vertices[face[1]], vertices[face[2]]
    def tri_area(a, b, c):
        ex, ey, ez = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        fx_, fy_, fz_ = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        cx = ey * fz_ - ez * fy_
        cy = ez * fx_ - ex * fz_
        cz = ex * fy_ - ey * fx_
        return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
    area = tri_area(p0, p1, p2)
    if face[2] != face[3]:
        area += tri_area(p0, p2, vertices[face[3]])
    return area


def prepare(rom: Path, out: Path, tile_size=16, split_edge=0, sdk_split=0,
            sdk_path=None, split_radius=96, adaptive_faces=0, texture_budget=96 * 1024,
            texture_samples=1, refine_faces=(), refine_grid=0, refine_manifest=None,
            adaptive_priorities=None, stitch_sources=(), stitch_cross_sources=(),
            pack_split_quads=False, vertex_colors=False, merge_quads=False, lut4=False,
            max_edge=0.0, max_edge_radius=0.0, max_tile_size=48):
    fs = Filesystem.from_file(rom)
    m = convert_bmd(fs.read('data/stage/main_castle/main_castle_all.bmd'))
    refine_grids = {}
    refine_axes = {}
    if refine_manifest is not None:
        expected = json.loads(refine_manifest.read_text())
        if refine_faces:
            raise ValueError('choose a refinement manifest or explicit face IDs')
        refine_faces = []
        for entry in expected:
            i = entry['face']
            if not 0 <= i < len(m.faces) or list(m.faces[i]) != entry['vertices'] or list(m.face_provenance[i]) != entry['provenance']:
                raise ValueError(f'refinement face {i} does not match source model')
            refine_faces.append(i)
            if 'grid' in entry:
                refine_grids[i] = entry['grid']
            if 'axes' in entry:
                refine_axes[i] = entry['axes']
    out.mkdir(parents=True, exist_ok=True)
    # Face IDs survive material baking; retain the original source stream and
    # primitive type for matching diagnostic captures to the decoded model.
    (out / 'castle_face_provenance.json').write_text(json.dumps([
        {'face': i, 'group': group, 'display_list': display_list, 'material': material,
         'primitive': primitive, 'vertices': m.faces[i], 'uv': m.face_uvs[i]}
        for i, (group, display_list, material, primitive) in enumerate(m.face_provenance)
    ], indent=2) + '\n')
    prisms = decode_kcl(fs.read('data/stage/main_castle/main_castle.kcl'))
    vertices = [tuple(c * (1 << m.scale_shift) * 64 / 4096 for c in (v.x, v.y, v.z)) for v in m.vertices]
    faces, uvs, materials = m.faces, m.face_uvs, m.face_materials
    colors = m.face_colors if vertex_colors and m.face_colors else None
    origins = list(range(len(faces)))
    source_sets = [(i,) for i in range(len(faces))]

    if split_edge and sdk_split:
        raise ValueError('choose one subdivision strategy')
    if refine_faces and not sdk_split:
        raise ValueError('face refinement requires SDK splitting')
    if pack_split_quads and not sdk_split:
        raise ValueError('quad packing requires SDK splitting')

    merged_quad_count = 0
    if merge_quads:
        pre_count = len(faces)
        faces, uvs, materials, merged_cols, origins, source_sets = merge_coplanar_quads(
            vertices, faces, uvs, materials, colors=colors, origins=origins
        )
        if colors is not None:
            colors = merged_cols
        merged_quad_count = pre_count - len(faces)
        if refine_faces:
            raw_refine = set(refine_faces)
            new_refine = []
            new_grids = {}
            new_axes = {}
            for idx, srcs in enumerate(source_sets):
                hit = [s for s in srcs if s in raw_refine]
                if not hit:
                    continue
                new_refine.append(idx)
                grids = [refine_grids[s] for s in hit if s in refine_grids]
                if grids:
                    new_grids[idx] = min(grids)
                axes_set = set()
                for s in hit:
                    if s in refine_axes:
                        axes_set.update(refine_axes[s])
                if axes_set:
                    new_axes[idx] = ''.join(a for a in 'xyz' if a in axes_set)
            refine_faces = new_refine
            refine_grids = new_grids
            refine_axes = new_axes

    if sdk_split:
        if sdk_path is None:
            raise ValueError('SDK splitting requires --libsaturn-source')
        pre_origins = origins
        pre_source_sets = source_sets
        if colors is not None:
            vertices, faces, uvs, materials, split_origins, colors = split_nearby(
                vertices, faces, uvs, materials, sdk_path,
                center=(0, 256), radius=split_radius, cell_size=sdk_split,
                refine_faces=refine_faces, refine_cell_size=refine_grid,
                refine_grids=refine_grids, refine_axes=refine_axes,
                pack_quads=pack_split_quads, colors=colors,
                max_edge=max_edge, max_edge_radius=max_edge_radius,
            )
        else:
            vertices, faces, uvs, materials, split_origins = split_nearby(
                vertices, faces, uvs, materials, sdk_path,
                center=(0, 256), radius=split_radius, cell_size=sdk_split,
                refine_faces=refine_faces, refine_cell_size=refine_grid,
                refine_grids=refine_grids, refine_axes=refine_axes,
                pack_quads=pack_split_quads,
                max_edge=max_edge, max_edge_radius=max_edge_radius,
            )
        origins = [pre_origins[o] for o in split_origins]
        source_sets = [pre_source_sets[o] for o in split_origins]
        (out / 'castle_split_origins.json').write_text(json.dumps(origins) + '\n')
    elif split_edge:
        vertices, faces, uvs, materials, origins = split_large_faces(vertices, faces, uvs, materials, split_edge)
        source_sets = [(o,) for o in origins]
        (out / 'castle_split_origins.json').write_text(json.dumps(origins) + '\n')

    def bake_castle(size):
        bakes = []
        for idx, (material, uv) in enumerate(zip(materials, uvs)):
            tex = m.material_textures[material]
            col = colors[idx] if colors is not None else None
            bakes.append(
                bake_face(tex, uv, size, samples=texture_samples, colors=col)
                if tex else BakedTexture(size, size, ((180, 180, 180, 255),) * (size * size))
            )
        return index_bakes(bakes)

    high_faces = []
    luts = ()
    lut_count = 0
    palette = ()
    tile_size_hist = {}
    if lut4:
        sources = [m.material_textures[mat] for mat in materials]
        if any(tex is None for tex in sources):
            raise ValueError('LUT4 castle baking requires textured faces')
        priorities = json.loads(adaptive_priorities.read_text()) if adaptive_priorities else None
        if isinstance(priorities, dict):
            source_priorities = {int(face): weight for face, weight in priorities.items()}
            if any(face < 0 or face >= len(m.faces) for face in source_priorities):
                raise ValueError('adaptive priority references an unknown source face')
            priorities = [max(source_priorities.get(s, 1) for s in srcs) for srcs in source_sets]
        areas = [_face_area(vertices, f) for f in faces]
        textures, luts, lut_count, face_textures, sizes = adaptive_lut4_bakes(
            sources, uvs, materials, colors=colors,
            byte_budget=texture_budget, samples=texture_samples,
            priorities=priorities, face_areas=areas, max_size=max_tile_size,
        )
        tile_size_hist = {f'{w}x{h}': c for (w, h), c in sorted(Counter(sizes).items())}
        high_faces = [i for i, (w, h) in enumerate(sizes) if w > 8 or h > 8]
        pixels = lut_count * 32 + sum(len(t.pixels) for t in textures)
        max_budget = max(192 * 1024, texture_budget)
        if pixels > max_budget:
            raise ValueError('castle exceeds resident texture budget')
    elif adaptive_faces:
        sources = [m.material_textures[mat] for mat in materials]
        if any(tex is None for tex in sources):
            raise ValueError('adaptive castle baking requires textured faces')
        priorities = json.loads(adaptive_priorities.read_text()) if adaptive_priorities else None
        if isinstance(priorities, dict):
            # Source-face weights apply to every piece generated by subdivision.
            # Older priority files remain ordered by render face.
            source_priorities = {int(face): weight for face, weight in priorities.items()}
            if any(face < 0 or face >= len(m.faces) for face in source_priorities):
                raise ValueError('adaptive priority references an unknown source face')
            priorities = [max(source_priorities.get(s, 1) for s in srcs) for srcs in source_sets]
        textures, palette, face_textures, high_faces = adaptive_bakes(
            sources, uvs,
            high_face_limit=adaptive_faces, byte_budget=texture_budget, samples=texture_samples,
            priorities=priorities, stitch_faces=faces, stitch_origins=origins,
            stitch_sources=stitch_sources, stitch_cross_sources=stitch_cross_sources,
        )
        tile_size = 8
        pixels = sum(len(t.pixels) for t in textures)
        if pixels > 192 * 1024:
            raise ValueError('castle exceeds resident texture budget')
    else:
        if stitch_sources or stitch_cross_sources:
            raise ValueError('edge stitching requires adaptive bakes')
        textures, palette, face_textures = bake_castle(tile_size)
        # Correct repeat modes reveal more distinct terrain tiles. Bound their
        # residency so face textures cannot consume the actor's RAM/VRAM budget.
        if sum(len(t.pixels) for t in textures) > 192 * 1024 and tile_size > 8:
            tile_size = 8
            textures, palette, face_textures = bake_castle(tile_size)
        pixels = sum(len(t.pixels) for t in textures)
        if pixels > 192 * 1024:
            raise ValueError('castle exceeds resident texture budget')

    out.mkdir(parents=True, exist_ok=True)
    # The world-space castle transform is identity. Keep a compact candidate
    # list for support-plane tests, using the same fixed-point coordinates
    # emitted to the Saturn asset rather than approximate float comparisons.
    flat_faces = [i for i, face in enumerate(faces)
                  if len({fx(vertices[index][1]) for index in face}) == 1]
    planes = support_planes(vertices, faces)
    header = ['#pragma once', '#include <saturn/model3d.h>', '#include "sm64ds_play.h"',
              f'#define CASTLE_VERTEX_COUNT {len(vertices)}u', f'#define CASTLE_FACE_COUNT {len(faces)}u',
              '#define CASTLE_FACE_SOURCE_AVAILABLE 1',
              '#define CASTLE_FLAT_FACE_LIST_AVAILABLE 1',
              f'#define CASTLE_FLAT_FACE_COUNT {len(flat_faces)}u',
              '#define CASTLE_SUPPORT_PLANE_LIST_AVAILABLE 1',
              f'#define CASTLE_SUPPORT_PLANE_COUNT {len(planes)}u',
              f'#define CASTLE_TEXTURE_COUNT {len(textures)}u', 'extern const sat_model_asset_t castle_model;',
              'extern const sm64ds_collision_t castle_collision;',
              'extern const uint16_t castle_face_source[CASTLE_FACE_COUNT];',
              'extern const uint16_t castle_flat_faces[];',
              'extern const uint16_t castle_support_faces[];',
              'extern const sat_vec3_t castle_support_normals[];',
              'extern const uint8_t castle_double_sided[CASTLE_FACE_COUNT];',
              'extern const uint8_t castle_polygon_alpha[CASTLE_FACE_COUNT];']
    code = ['#include "castle_scene.h"', '/* Private ROM-derived data. Never commit. */',
            'static const sat_vec3_t vertices[]={', ',\n'.join(vec(v) for v in vertices), '};',
            'static const uint16_t faces[]={', array([i for face in faces for i in face]), '};',
            'const uint16_t castle_face_source[]={', array(origins), '};',
            'const uint16_t castle_flat_faces[]={', array(flat_faces or [0]), '};',
            'const uint16_t castle_support_faces[]={', array([f for f, _ in planes] or [0]), '};',
            'const sat_vec3_t castle_support_normals[]={',
            ',\n'.join('{' + ','.join(map(str, n)) + '}' for _, n in planes) if planes else '{0,0,0}', '};',
            'const uint8_t castle_double_sided[]={',
            array([int((m.material_flags[mat] & 0xc0) == 0xc0) for mat in materials]), '};',
            'const uint8_t castle_polygon_alpha[]={',
            array([(m.material_flags[mat] >> 16) & 31 for mat in materials]), '};']
    for i, t in enumerate(textures):
        code.extend([f'static const uint8_t pixels_{i}[]={{', array(t.pixels), '};'])
    code += ['static const sat_model_texture_asset_t textures[]={']
    if lut4:
        for i, t in enumerate(textures):
            code.append(
                f'{{.pixels=pixels_{i},.width={t.width},.height={t.height},'
                f'.palette_slot={t.lut_slot},.flags=SAT_MODEL_TEXTURE_LUT4,.pixel_count={t.width * t.height}}},'
            )
        code += ['};', 'static const uint16_t luts[]={', hex_array(luts), '};',
                 'static const uint16_t face_textures[]={', array(face_textures), '};',
                 'const sat_model_asset_t castle_model={.vertices=vertices,',
                 f'.vertex_count={len(vertices)},.indices=faces,.face_count={len(faces)},',
                 f'.face_texture_indices=face_textures,.textures=textures,.texture_count={len(textures)},',
                 f'.palettes_rgb555=0,.palette_count=0,.palette_base=0,.luts_rgb555=luts,.lut_count={lut_count}}};']
    else:
        for i, t in enumerate(textures):
            code.append(f'{{.pixels=pixels_{i},.width={t.width},.height={t.height},.pixel_count={len(t.pixels)}}},')
        code += ['};', 'static const uint16_t palette[]={', array(palette), '};',
                 'static const uint16_t face_textures[]={', array(face_textures), '};',
                 'const sat_model_asset_t castle_model={.vertices=vertices,',
                 f'.vertex_count={len(vertices)},.indices=faces,.face_count={len(faces)},',
                 f'.face_texture_indices=face_textures,.textures=textures,.texture_count={len(textures)},',
                 '.palettes_rgb555=palette,.palette_count=1,.palette_base=2};']
    code += ['static const sm64ds_prism_t prisms[]={']
    bounds = []
    for p in prisms:
        lo = tuple(min(v[i] for v in p.vertices) for i in range(3))
        hi = tuple(max(v[i] for v in p.vertices) for i in range(3))
        bounds.append((lo, hi))
        code.append('{' + ','.join((vec(p.vertices[0]), vec(p.normal), '{' + ','.join(vec(e) for e in p.edges) + '}', vec(lo), vec(hi), str(fx(p.extent)), str(p.attribute))) + '},')
    code += ['};']
    ox = math.floor((min(b[0][0] for b in bounds) - 4) / 32) * 32
    oz = math.floor((min(b[0][2] for b in bounds) - 4) / 32) * 32
    nx = math.ceil((max(b[1][0] for b in bounds) + 4 - ox) / 32)
    nz = math.ceil((max(b[1][2] for b in bounds) + 4 - oz) / 32)
    bins = [[] for _ in range(nx * nz)]
    for i, (lo, hi) in enumerate(bounds):
        for z in range(max(0, int((lo[2] - 4 - oz) // 32)), min(nz, int((hi[2] + 4 - oz) // 32) + 1)):
            for x in range(max(0, int((lo[0] - 4 - ox) // 32)), min(nx, int((hi[0] + 4 - ox) // 32) + 1)):
                bins[z * nx + x].append(i)
    offsets = [0]
    indices = []
    for b in bins:
        indices.extend(b)
        offsets.append(len(indices))
    code += ['static const uint32_t offsets[]={', array(offsets), '};',
             'static const uint16_t collision_indices[]={', array(indices), '};',
             'const sm64ds_collision_t castle_collision={.prisms=prisms,.offsets=offsets,.indices=collision_indices,',
             f'.count={len(prisms)},.nx={nx},.nz={nz},.origin_x={fx(ox)},.origin_z={fx(oz)}' + '};', '']
    props_report = {}
    if lut4:
        prop_h, prop_c, props_report = _build_castle_props(fs)
        header.extend(prop_h)
        code.extend(prop_c)
        code.append('')
    (out / 'castle_scene.h').write_text('\n'.join(header) + '\n')
    (out / 'castle_scene.c').write_text('\n'.join(code))

    if lut4:
        convert(['--rom', str(rom), '--out', str(out), '--tile-size', '24', '--lut4', '--adaptive-size'])
        convert(['--rom', str(rom), '--out', str(out), '--kind', 'skybox', '--model', 'data/vrbox/vr02.bmd',
                 '--name', 'skybox_preview', '--tile-size', '16', '--lut4', '--subdivide-sky'])
    else:
        convert(['--rom', str(rom), '--out', str(out), '--tile-size', '24'])
        convert(['--rom', str(rom), '--out', str(out), '--kind', 'skybox', '--model', 'data/vrbox/vr02.bmd',
                 '--name', 'skybox_preview'])

    # The gameplay head shares the body's bone-local convention. The
    # top-level b_mario_head_cap is a different, larger model/orientation.
    head = convert_bmd(fs.read('ARCHIVE/arc0.narc:129'))
    h, c, head_report = emit_skybox(head, 'mario_head', palette_base=4, tile_size=24,
                                    lut4=lut4, adaptive_size=lut4)
    # Reuse the plain rigid-model emitter, retaining head-local coordinates.
    # The runtime attaches it to bone 15 rather than following the camera.
    if head_report['scale_divisor'] != 1:
        raise ValueError('head attachment requires its original model scale')
    (out / 'mario_head.h').write_text(h)
    (out / 'mario_head.c').write_text(c)
    report = {'rom_sha256': fs.sha256, 'render_vertices': len(vertices), 'render_faces': len(faces),
              'render_quads': sum(1 for f in faces if f[2] != f[3]),
              'render_triangles': sum(1 for f in faces if f[2] == f[3]),
              'merged_quad_pairs': merged_quad_count,
              'vertex_colors': vertex_colors,
              'lut4': lut4,
              'castle_lut_count': lut_count,
              'castle_tile_sizes': tile_size_hist,
              'split_edge': split_edge, 'sdk_split_grid': sdk_split, 'split_radius': split_radius,
              'max_edge': max_edge, 'max_edge_radius': max_edge_radius,
              'refine_faces': list(refine_faces), 'refine_grid': refine_grid,
              'refine_grid_overrides': refine_grids,
              'refine_axes_overrides': refine_axes, 'pack_split_quads': pack_split_quads,
              'source_render_faces': len(m.faces),
              'flat_render_faces': len(flat_faces),
              'support_plane_faces': len(planes),
              'castle_tile_size': tile_size, 'actor_tile_size': 24,
              'castle_high_resolution_faces': len(high_faces),
              'castle_texture_samples': texture_samples,
              'stitched_source_faces': list(stitch_sources),
              'stitched_cross_source_pairs': [list(pair) for pair in stitch_cross_sources],
              'castle_high_resolution_face_ids': high_faces,
              'castle_texture_bytes': pixels, 'castle_texture_tiles': len(textures), 'kcl_prisms': len(prisms),
              'collision_grid': [nx, nz], 'collision_grid_references': len(indices),
              'world_units_per_bmd_unit': 64, 'world_units_per_ds_unit': 0.064,
              'head_attachment_bone': 15, 'head_texture_bytes': head_report['texture_pixels_bytes'],
              'head_model': 'ARCHIVE/arc0.narc:129',
              'render_lod': 'full detail with experimental face split' if split_edge or sdk_split else
                            'original full-detail mesh; no visual HLOD switching',
              'physics': 'prototype KCL locomotion; CLPS attributes retained but behaviors not implemented',
              **props_report}
    (out / 'castle_scene.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--out', type=Path, default=Path('private/castle'))
    p.add_argument('--tile-size', type=int, choices=(8, 16), default=16)
    p.add_argument('--split-edge', type=float, default=0, help='Experimental one-pass static face split threshold in world units')
    p.add_argument('--sdk-split-grid', type=float, default=0, help='Experimental LibSaturn XZ grid split size')
    p.add_argument('--split-radius', type=float, default=96, help='XZ radius around spawn for SDK split')
    p.add_argument('--max-edge', type=float, default=0, help='Subdivide oversized faces exceeding this edge length in world units')
    p.add_argument('--max-edge-radius', type=float, default=0, help='Optional XZ radius around spawn for --max-edge (0 = whole castle)')
    p.add_argument('--refine-face', type=int, action='append', default=[], help='Source face ID to split on the finer grid; repeatable')
    p.add_argument('--refine-manifest', type=Path, help='Validated source faces to refine')
    p.add_argument('--refine-grid', type=float, default=0, help='Fine grid size for selected source faces')
    p.add_argument('--pack-split-quads', action='store_true', help='Keep convex split pieces as native quads where possible')
    p.add_argument('--merge-quads', action='store_true', help='Merge coplanar UV/color-consistent triangle pairs into native VDP1 quads')
    p.add_argument('--vertex-colors', action='store_true', help='Modulate baked face textures with DS BMD vertex colors')
    p.add_argument('--lut4', action='store_true', help='Emit 4-bit VDP1 LUT4 textures with adaptive non-square sizes and per-group LUTs')
    p.add_argument('--max-tile-size', type=int, default=48, choices=(16, 24, 32, 48, 64), help='Maximum axis size for adaptive LUT4 castle tiles')
    p.add_argument('--libsaturn-source', type=Path, help='LibSaturn source checkout for SDK splitting')
    p.add_argument('--adaptive-faces', type=int, default=0, help='Maximum faces with 16x16 adaptive bakes')
    p.add_argument('--adaptive-priorities', type=Path, help='JSON source-face weights or a list of per-render-face weights')
    p.add_argument('--stitch-source', type=int, action='append', default=[], help='Experimentally stitch baked edges of this original source face')
    p.add_argument('--stitch-cross-source', type=int, nargs=2, action='append', default=[], metavar=('FACE_A', 'FACE_B'), help='Experimentally stitch shared edges between two source faces')
    p.add_argument('--texture-budget', type=int, default=96 * 1024, help='Adaptive castle pixel budget in bytes')
    p.add_argument('--texture-samples', type=int, choices=(1, 2, 4), default=1, help='Samples per axis for filtered castle bakes')
    a = p.parse_args()
    prepare(a.rom, a.out, a.tile_size, a.split_edge, a.sdk_split_grid,
            a.libsaturn_source, a.split_radius, a.adaptive_faces, a.texture_budget, a.texture_samples,
            a.refine_face, a.refine_grid, a.refine_manifest, a.adaptive_priorities, a.stitch_source, a.stitch_cross_source,
            a.pack_split_quads, a.vertex_colors, a.merge_quads, a.lut4, a.max_edge, a.max_edge_radius, a.max_tile_size)
