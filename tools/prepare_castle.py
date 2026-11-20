#!/usr/bin/env python3
"""Prepare a private, full-detail castle walking scene from a local ROM."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.bca import Animation
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.cli import main as convert
from sm64ds_pipeline.emit import emit_model
from sm64ds_pipeline.kcl import decode_kcl
from sm64ds_pipeline.sdat import SdatArchive, resample_wave_s8
from sm64ds_pipeline.skybox import emit_skybox
from sm64ds_pipeline.sky_panorama import emit_sky_panorama
from sm64ds_pipeline.textures import bake_face, index_bakes, index_bakes_lut4, BakedTexture
from sm64ds_pipeline.subdivide import cut_faces_against_boxes, split_large_faces, split_long_edges
from sm64ds_pipeline.sdk_split import split_nearby
from sm64ds_pipeline.quad_merge import merge_coplanar_quads
from sm64ds_pipeline.adaptive_bake import adaptive_bakes, adaptive_lut4_bakes
from sm64ds_pipeline.support_planes import support_planes
from sm64ds_pipeline.skinning import rest_world, mv
from sm64ds_pipeline.level_objects import (
    CASTLE_1F_OVERLAY_ID,
    CASTLE_GROUNDS_OVERLAY_ID,
    extract_castle_1f_objects,
    extract_castle_props,
    extract_clps_slippery_mask,
)


def fx(value):
    result = round(value * 65536)
    if not -2**31 <= result < 2**31:
        raise ValueError('fixed-point overflow')
    return result


def vec(value):
    return '{' + ','.join(str(fx(v)) for v in value) + '}'


def aabb_literal(lo, hi):
    """Emit a sat_aabb3_t covering [fx(lo), fx(hi)] with >=0 half-extents."""
    fl = [fx(v) for v in lo]
    fh = [fx(v) for v in hi]
    center = [(a + b) // 2 for a, b in zip(fl, fh)]
    half = [max(0, (b - a + 1) // 2 + 1) for a, b in zip(fl, fh)]
    return '{{' + ','.join(map(str, center)) + '},{' + ','.join(map(str, half)) + '}}'


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


def _build_castle_1f_props(fs: Filesystem):
    """Extract Castle 1F course paintings, exit doors, and Toads as compact LUT4 assets."""
    objs = extract_castle_1f_objects(fs)

    # 1. Course paintings (each is 1 quad + 1 crisp 64x64 LUT4 texture).
    unique_paths = []
    path_to_idx = {}
    painting_bakes = []
    for p in objs.paintings:
        if p.model_path not in path_to_idx:
            path_to_idx[p.model_path] = len(unique_paths)
            unique_paths.append(p.model_path)
            pbmd = convert_bmd(fs.read(p.model_path))
            ptex = pbmd.material_textures[0]
            if ptex is None:
                raise ValueError(f'{p.model_path} is missing its texture')
            uv = ((0.0, 0.0), (float(ptex.width), 0.0),
                  (float(ptex.width), float(ptex.height)), (0.0, float(ptex.height)))
            painting_bakes.append(bake_face(ptex, uv, 64, samples=2))
    ptexs, pluts, plut_cnt, _ = index_bakes_lut4(
        painting_bakes, groups=list(range(len(painting_bakes)))
    )
    painting_bytes = plut_cnt * 32 + sum(len(t.pixels) for t in ptexs)

    # Precompute world-space quad corners (TL, TR, BR, BL) facing +normal into the room.
    painting_quads = []
    for p in objs.paintings:
        rad = math.radians(p.yaw_deg)
        nx, nz = math.sin(rad), math.cos(rad)
        rx, rz = math.cos(rad), -math.sin(rad)
        hw = p.width * 0.5
        if p.centered_y:
            y_bot = p.position[1] - p.height * 0.5
            y_top = p.position[1] + p.height * 0.5
        else:
            y_bot = p.position[1]
            y_top = p.position[1] + p.height
        cx = p.position[0] + nx * 0.6
        cz = p.position[2] + nz * 0.6
        tl = (cx - rx * hw, y_top, cz - rz * hw)
        tr = (cx + rx * hw, y_top, cz + rz * hw)
        br = (cx + rx * hw, y_bot, cz + rz * hw)
        bl = (cx - rx * hw, y_bot, cz - rz * hw)
        painting_quads.append((tl, tr, br, bl, path_to_idx[p.model_path], p.room))

    # 2. Level-exit 3D doors (obj_door1.bmd at 0.5x actor scale).
    exit_doors = [d for d in objs.doors if d.is_level_exit]
    door_bmd = convert_bmd(fs.read('data/normal_obj/door/obj_door1.bmd'))
    dverts = [tuple(c * (1 << door_bmd.scale_shift) * 0.5 / 4096.0 for c in (v.x, v.y, v.z))
              for v in door_bmd.vertices]
    dfaces, duvs, dmats, dcols, _, _ = merge_coplanar_quads(
        dverts, door_bmd.faces, door_bmd.face_uvs, door_bmd.face_materials, colors=door_bmd.face_colors
    )
    dsrcs = [door_bmd.material_textures[mat] for mat in dmats]
    dareas = [_face_area(dverts, f) for f in dfaces]
    dtexs, dluts, dlut_cnt, dftexs, _ = adaptive_lut4_bakes(
        dsrcs, duvs, dmats, colors=dcols, byte_budget=4096, samples=2, face_areas=dareas, max_size=32
    )
    door_bytes = dlut_cnt * 32 + sum(len(t.pixels) for t in dtexs)

    # 3. Toad NPCs (kinopio.bmd baked in rest-world pose at 0.5x actor scale).
    toad_bmd = convert_bmd(fs.read('data/enemy/kinopio/kinopio.bmd'))
    toad_rw = rest_world(toad_bmd)
    tverts = []
    for v in toad_bmd.vertices:
        pt = tuple(c * (1 << toad_bmd.scale_shift) / 4096.0 for c in (v.x, v.y, v.z))
        if v.joint < len(toad_bmd.bones):
            lin, tr = toad_rw[v.joint]
            pt = tuple(a + b for a, b in zip(mv(lin, pt), tr))
        tverts.append(tuple(c * 0.5 for c in pt))
    tfaces, tuvs, tmats, tcols, _, _ = merge_coplanar_quads(
        tverts, toad_bmd.faces, toad_bmd.face_uvs, toad_bmd.face_materials, colors=toad_bmd.face_colors
    )
    tsrcs = [toad_bmd.material_textures[mat] for mat in tmats]
    tareas = [_face_area(tverts, f) for f in tfaces]
    ttexs, tluts, tlut_cnt, tftexs, _ = adaptive_lut4_bakes(
        tsrcs, tuvs, tmats, colors=tcols, byte_budget=10240, samples=2, face_areas=tareas, max_size=24
    )
    toad_bytes = tlut_cnt * 32 + sum(len(t.pixels) for t in ttexs)

    h_lines = [
        '#define CASTLE_INTERIOR_PROPS_AVAILABLE 1',
        f'#define CASTLE_PAINTING_COUNT {len(painting_quads)}u',
        f'#define CASTLE_PAINTING_TEXTURE_COUNT {len(ptexs)}u',
        'extern const sat_model_asset_t castle_painting_model;',
        'extern const sat_quad3_t castle_painting_quads[CASTLE_PAINTING_COUNT];',
        'extern const uint8_t castle_painting_tex_indices[CASTLE_PAINTING_COUNT];',
        'extern const uint8_t castle_painting_rooms[CASTLE_PAINTING_COUNT];',
        f'#define CASTLE_DOOR_COUNT {len(exit_doors)}u',
        f'#define CASTLE_DOOR_VERTEX_COUNT {len(dverts)}u',
        f'#define CASTLE_DOOR_FACE_COUNT {len(dfaces)}u',
        f'#define CASTLE_DOOR_TEXTURE_COUNT {len(dtexs)}u',
        'extern const sat_model_asset_t castle_door_model;',
        'extern const sat_vec3_t castle_door_positions[CASTLE_DOOR_COUNT];',
        'extern const int16_t castle_door_yaw_deg[CASTLE_DOOR_COUNT];',
        'extern const uint8_t castle_door_rooms[CASTLE_DOOR_COUNT];',
        f'#define CASTLE_TOAD_COUNT {len(objs.toads)}u',
        f'#define CASTLE_TOAD_VERTEX_COUNT {len(tverts)}u',
        f'#define CASTLE_TOAD_FACE_COUNT {len(tfaces)}u',
        f'#define CASTLE_TOAD_TEXTURE_COUNT {len(ttexs)}u',
        'extern const sat_model_asset_t castle_toad_model;',
        'extern const sat_vec3_t castle_toad_positions[CASTLE_TOAD_COUNT];',
        'extern const int16_t castle_toad_yaw_deg[CASTLE_TOAD_COUNT];',
        'extern const uint8_t castle_toad_rooms[CASTLE_TOAD_COUNT];',
    ]

    c_lines = [
        'static const sat_vec3_t painting_dummy_verts[4]={{0,0,0},{65536,0,0},{65536,65536,0},{0,65536,0}};',
        'static const uint16_t painting_dummy_faces[4]={0,1,2,3};',
        'static const uint16_t painting_dummy_ftex[1]={0};',
    ]
    for i, t in enumerate(ptexs):
        c_lines.extend([f'static const uint8_t painting_pixels_{i}[]={{', array(t.pixels), '};'])
    c_lines.append('static const sat_model_texture_asset_t painting_textures[]={')
    for i, t in enumerate(ptexs):
        c_lines.append(
            f'{{.pixels=painting_pixels_{i},.width={t.width},.height={t.height},'
            f'.palette_slot={t.lut_slot},.flags=SAT_MODEL_TEXTURE_LUT4,.pixel_count={t.width * t.height}}},'
        )
    c_lines += [
        '};',
        'static const uint16_t painting_luts[]={', hex_array(pluts), '};',
        'const sat_model_asset_t castle_painting_model={.vertices=painting_dummy_verts,.vertex_count=4,'
        '.indices=painting_dummy_faces,.face_count=1,.face_texture_indices=painting_dummy_ftex,'
        f'.textures=painting_textures,.texture_count={len(ptexs)},.palettes_rgb555=0,.palette_count=0,'
        f'.palette_base=0,.luts_rgb555=painting_luts,.lut_count={plut_cnt}}};',
        'const sat_quad3_t castle_painting_quads[CASTLE_PAINTING_COUNT]={',
    ]
    for tl, tr, br, bl, _, _ in painting_quads:
        c_lines.append(f'{{.v={{{vec(tl)},{vec(tr)},{vec(br)},{vec(bl)}}}}},')
    c_lines += [
        '};',
        'const uint8_t castle_painting_tex_indices[CASTLE_PAINTING_COUNT]={',
        array([q[4] for q in painting_quads]), '};',
        'const uint8_t castle_painting_rooms[CASTLE_PAINTING_COUNT]={',
        array([q[5] for q in painting_quads]), '};',
        'static const sat_vec3_t door_vertices[]={',
        ',\n'.join(vec(v) for v in dverts),
        '};',
        'static const uint16_t door_faces[]={',
        array([i for f in dfaces for i in f]),
        '};',
    ]
    for i, t in enumerate(dtexs):
        c_lines.extend([f'static const uint8_t door_pixels_{i}[]={{', array(t.pixels), '};'])
    c_lines.append('static const sat_model_texture_asset_t door_textures[]={')
    for i, t in enumerate(dtexs):
        c_lines.append(
            f'{{.pixels=door_pixels_{i},.width={t.width},.height={t.height},'
            f'.palette_slot={t.lut_slot},.flags=SAT_MODEL_TEXTURE_LUT4,.pixel_count={t.width * t.height}}},'
        )
    c_lines += [
        '};',
        'static const uint16_t door_luts[]={', hex_array(dluts), '};',
        'static const uint16_t door_face_textures[]={', array(dftexs), '};',
        f'const sat_model_asset_t castle_door_model={{.vertices=door_vertices,.vertex_count={len(dverts)},'
        f'.indices=door_faces,.face_count={len(dfaces)},.face_texture_indices=door_face_textures,'
        f'.textures=door_textures,.texture_count={len(dtexs)},.palettes_rgb555=0,.palette_count=0,'
        f'.palette_base=0,.luts_rgb555=door_luts,.lut_count={dlut_cnt}}};',
        'const sat_vec3_t castle_door_positions[CASTLE_DOOR_COUNT]={',
        ',\n'.join(vec(d.position) for d in exit_doors),
        '};',
        'const int16_t castle_door_yaw_deg[CASTLE_DOOR_COUNT]={',
        array([d.yaw_deg for d in exit_doors]), '};',
        'const uint8_t castle_door_rooms[CASTLE_DOOR_COUNT]={',
        array([d.in_area for d in exit_doors]), '};',
        'static const sat_vec3_t toad_vertices[]={',
        ',\n'.join(vec(v) for v in tverts),
        '};',
        'static const uint16_t toad_faces[]={',
        array([i for f in tfaces for i in f]),
        '};',
    ]
    for i, t in enumerate(ttexs):
        c_lines.extend([f'static const uint8_t toad_pixels_{i}[]={{', array(t.pixels), '};'])
    c_lines.append('static const sat_model_texture_asset_t toad_textures[]={')
    for i, t in enumerate(ttexs):
        c_lines.append(
            f'{{.pixels=toad_pixels_{i},.width={t.width},.height={t.height},'
            f'.palette_slot={t.lut_slot},.flags=SAT_MODEL_TEXTURE_LUT4,.pixel_count={t.width * t.height}}},'
        )
    c_lines += [
        '};',
        'static const uint16_t toad_luts[]={', hex_array(tluts), '};',
        'static const uint16_t toad_face_textures[]={', array(tftexs), '};',
        f'const sat_model_asset_t castle_toad_model={{.vertices=toad_vertices,.vertex_count={len(tverts)},'
        f'.indices=toad_faces,.face_count={len(tfaces)},.face_texture_indices=toad_face_textures,'
        f'.textures=toad_textures,.texture_count={len(ttexs)},.palettes_rgb555=0,.palette_count=0,'
        f'.palette_base=0,.luts_rgb555=toad_luts,.lut_count={tlut_cnt}}};',
        'const sat_vec3_t castle_toad_positions[CASTLE_TOAD_COUNT]={',
        ',\n'.join(vec(t.position) for t in objs.toads),
        '};',
        'const int16_t castle_toad_yaw_deg[CASTLE_TOAD_COUNT]={',
        array([t.yaw_deg for t in objs.toads]), '};',
        'const uint8_t castle_toad_rooms[CASTLE_TOAD_COUNT]={',
        array(objs.toad_rooms), '};',
    ]
    return h_lines, c_lines, objs, {
        'castle_painting_count': len(painting_quads),
        'castle_painting_texture_bytes': painting_bytes,
        'castle_door_count': len(exit_doors),
        'castle_door_texture_bytes': door_bytes,
        'castle_toad_count': len(objs.toads),
        'castle_toad_texture_bytes': toad_bytes,
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


def _compact_rooms(vertices, faces, uvs, materials, origins, source_sets, face_rooms, colors, room_count):
    """Order faces and vertices into contiguous per-room slices for fast O(1) room culling."""
    order = sorted(range(len(faces)), key=lambda i: (face_rooms[i], i))
    new_vertices = []
    new_faces = []
    new_uvs = []
    new_materials = []
    new_origins = []
    new_source_sets = []
    new_face_rooms = []
    new_colors = [] if colors is not None else None
    room_first = [0] * room_count
    room_count_arr = [0] * room_count
    room_vfirst = [0] * room_count
    room_vcount = [0] * room_count
    room_min = [(0.0, 0.0, 0.0)] * room_count
    room_max = [(0.0, 0.0, 0.0)] * room_count

    by_room = [[] for _ in range(room_count)]
    for idx in order:
        r = face_rooms[idx]
        if not 0 <= r < room_count:
            raise ValueError(f'room index {r} out of range 0..{room_count - 1}')
        by_room[r].append(idx)

    for r in range(room_count):
        room_first[r] = len(new_faces)
        room_vfirst[r] = len(new_vertices)
        vmap = {}
        r_pts = []
        for idx in by_room[r]:
            f = faces[idx]
            remapped = []
            for vi in f:
                if vi not in vmap:
                    vmap[vi] = len(new_vertices)
                    pt = vertices[vi]
                    new_vertices.append(pt)
                    r_pts.append(pt)
                remapped.append(vmap[vi])
            new_faces.append(tuple(remapped))
            new_uvs.append(uvs[idx])
            new_materials.append(materials[idx])
            new_origins.append(origins[idx])
            new_source_sets.append(source_sets[idx])
            new_face_rooms.append(r)
            if new_colors is not None:
                new_colors.append(colors[idx])
        room_count_arr[r] = len(new_faces) - room_first[r]
        room_vcount[r] = len(new_vertices) - room_vfirst[r]
        if r_pts:
            room_min[r] = tuple(min(p[k] for p in r_pts) for k in range(3))
            room_max[r] = tuple(max(p[k] for p in r_pts) for k in range(3))

    return (
        new_vertices, new_faces, new_uvs, new_materials, new_origins, new_source_sets,
        new_face_rooms, new_colors,
        (room_first, room_count_arr, room_vfirst, room_vcount, room_min, room_max),
    )


def _compact_chunks(vertices, faces, uvs, materials, origins, source_sets, colors, cell_size):
    """Partition world faces into non-empty XZ spatial grid chunks for 6-plane frustum culling."""
    if cell_size <= 0:
        raise ValueError('chunk_size must be positive')
    cells = {}
    face_chunks = []
    for f in faces:
        pts = [vertices[i] for i in (f[:3] if f[2] == f[3] else f)]
        cx = sum(p[0] for p in pts) / len(pts)
        cz = sum(p[2] for p in pts) / len(pts)
        key = (math.floor(cx / cell_size), math.floor(cz / cell_size))
        cid = cells.get(key)
        if cid is None:
            cid = len(cells)
            cells[key] = cid
        face_chunks.append(cid)
    if len(cells) > 255:
        raise ValueError(f'chunk count {len(cells)} exceeds uint8_t runtime index limit')
    return _compact_rooms(
        vertices, faces, uvs, materials, origins, source_sets, face_chunks, colors, len(cells)
    )


def _compute_room_portals(vertices, faces, face_rooms, n_rooms, doors=()):
    """Compute exact doorway portals (center_pos, room_a, room_b) from internal doors."""
    room_pts = [set() for _ in range(n_rooms)]
    for face, r in zip(faces, face_rooms):
        for vi in face:
            room_pts[r].add(vertices[vi])
    portals = []
    for d in doors:
        if d.is_level_exit:
            continue
        p = d.position
        dists = []
        for r in range(n_rooms):
            if not room_pts[r]:
                continue
            md = min(math.dist(p, q) for q in room_pts[r])
            dists.append((md, r))
        dists.sort()
        if len(dists) >= 2:
            ra, rb = dists[0][1], dists[1][1]
            if ra > rb:
                ra, rb = rb, ra
            center = (p[0], p[1] + 8.0, p[2])
            portals.append((center, ra, rb))
    return portals


def _compute_room_adjacency(room_min, room_max, doors=(), portals=()):
    """Compute per-room adjacency bitmask from actual internal doorway portals."""
    n = len(room_min)
    adj = [1 << r for r in range(n)]
    if portals:
        for _, a, b in portals:
            adj[a] |= 1 << b
            adj[b] |= 1 << a
        return adj
    pad = 4.0
    for d in doors:
        if d.is_level_exit:
            continue
        linked = set()
        if 0 <= d.in_area < n:
            linked.add(d.in_area)
        if 0 <= d.out_area < n:
            linked.add(d.out_area)
        for r in range(n):
            if all(room_min[r][k] - pad <= d.position[k] <= room_max[r][k] + pad for k in range(3)):
                linked.add(r)
        for a in linked:
            for b in linked:
                adj[a] |= 1 << b
    return adj


def prepare(rom: Path, out: Path, tile_size=16, split_edge=0, sdk_split=0,
            sdk_path=None, split_radius=96, adaptive_faces=0, texture_budget=96 * 1024,
            texture_samples=1, refine_faces=(), refine_grid=0, refine_manifest=None,
            adaptive_priorities=None, stitch_sources=(), stitch_cross_sources=(),
            pack_split_quads=False, vertex_colors=False, merge_quads=False, lut4=False,
            max_edge=0.0, max_edge_radius=0.0, max_tile_size=48, stage='main_castle',
            chunk_size=0.0, warp_target='', with_intro_props=False):
    if stage not in ('main_castle', 'castle_1f'):
        raise ValueError(f'unsupported stage: {stage}')
    is_interior = (stage == 'castle_1f')
    fs = Filesystem.from_file(rom)
    bmd_path = f'data/stage/{stage}/{stage}_all.bmd'
    kcl_path = f'data/stage/{stage}/{stage}.kcl'
    m = convert_bmd(fs.read(bmd_path))
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
    prisms = decode_kcl(fs.read(kcl_path))
    vertices = [tuple(c * (1 << m.scale_shift) * 64 / 4096 for c in (v.x, v.y, v.z)) for v in m.vertices]
    faces, uvs, materials = m.faces, m.face_uvs, m.face_materials
    face_rooms = list(m.face_rooms) if m.face_rooms else [0] * len(faces)
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
        pre_rooms = face_rooms
        faces, uvs, materials, merged_cols, origins, source_sets = merge_coplanar_quads(
            vertices, faces, uvs, materials, colors=colors, origins=origins,
            rooms=pre_rooms if is_interior else None,
        )
        face_rooms = [pre_rooms[o] for o in origins]
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

    if not is_interior and max_edge > 0:
        # Subtract raised hedge box footprints (mat 8, 19 tops) from underlying
        # continuous grass ground (mat 3) so buried grass cannot sort over hedge
        # walls under Saturn's average-depth painter sort.
        hedge_boxes = []
        seen_boxes = set()
        for f, mat in zip(faces, materials):
            if mat not in (8, 19):
                continue
            pts = [vertices[vi] for vi in (f[:3] if f[2] == f[3] else f)]
            ys = [p[1] for p in pts]
            if max(ys) - min(ys) > 0.1:
                continue
            xs = [p[0] for p in pts]
            zs = [p[2] for p in pts]
            box = (min(xs), max(xs), min(zs), max(zs), max(ys))
            key = tuple(round(v, 2) for v in box)
            if key not in seen_boxes and box[1] - box[0] > 1.0 and box[3] - box[2] > 1.0:
                seen_boxes.add(key)
                hedge_boxes.append(box)
        if hedge_boxes:
            pre_len = len(faces)
            vertices, faces, uvs, materials, origins, source_sets, colors = cut_faces_against_boxes(
                vertices, faces, uvs, materials, origins, source_sets,
                target_materials={3}, boxes=hedge_boxes, colors=colors,
            )
            face_rooms = [0] * len(faces)

    split_center = (-64, 16) if is_interior else (0, 256)
    if sdk_split:
        if sdk_path is None:
            raise ValueError('SDK splitting requires --libsaturn-source')
        pre_origins = origins
        pre_source_sets = source_sets
        pre_rooms = face_rooms
        if colors is not None:
            vertices, faces, uvs, materials, split_origins, colors = split_nearby(
                vertices, faces, uvs, materials, sdk_path,
                center=split_center, radius=split_radius, cell_size=sdk_split,
                refine_faces=refine_faces, refine_cell_size=refine_grid,
                refine_grids=refine_grids, refine_axes=refine_axes,
                pack_quads=pack_split_quads, colors=colors,
                max_edge=max_edge, max_edge_radius=max_edge_radius,
            )
        else:
            vertices, faces, uvs, materials, split_origins = split_nearby(
                vertices, faces, uvs, materials, sdk_path,
                center=split_center, radius=split_radius, cell_size=sdk_split,
                refine_faces=refine_faces, refine_cell_size=refine_grid,
                refine_grids=refine_grids, refine_axes=refine_axes,
                pack_quads=pack_split_quads,
                max_edge=max_edge, max_edge_radius=max_edge_radius,
            )
        origins = [pre_origins[o] for o in split_origins]
        source_sets = [pre_source_sets[o] for o in split_origins]
        face_rooms = [pre_rooms[o] for o in split_origins]
        (out / 'castle_split_origins.json').write_text(json.dumps(origins) + '\n')
    elif split_edge:
        pre_rooms = face_rooms
        vertices, faces, uvs, materials, origins = split_large_faces(vertices, faces, uvs, materials, split_edge)
        source_sets = [(o,) for o in origins]
        face_rooms = [pre_rooms[o] for o in origins]
        (out / 'castle_split_origins.json').write_text(json.dumps(origins) + '\n')
    elif max_edge > 0:
        pre_origins = origins
        pre_source_sets = source_sets
        pre_rooms = face_rooms
        if is_interior:
            sub_kw = {'high_y': 60.0, 'high_max_edge': max_edge * 2.0}
        else:
            # Fine bilinear quads everywhere Mario can walk (including west hedge maze);
            # keep distant outer mountains, upper spires, and deep moat walls compact.
            sub_kw = {
                'play_box': (-455.0, 360.0, -20.0, 90.0, -240.0, 430.0),
                'outside_max_edge': 160.0,
                'material_max_edges': {9: 24.0, 18: 24.0},
            }
        if colors is not None:
            vertices, faces, uvs, materials, split_origins, colors = split_long_edges(
                vertices, faces, uvs, materials, max_edge, colors=colors, **sub_kw
            )
        else:
            vertices, faces, uvs, materials, split_origins = split_long_edges(
                vertices, faces, uvs, materials, max_edge, **sub_kw
            )
        origins = [pre_origins[o] for o in split_origins]
        source_sets = [pre_source_sets[o] for o in split_origins]
        face_rooms = [pre_rooms[o] for o in split_origins]
        (out / 'castle_split_origins.json').write_text(json.dumps(origins) + '\n')

    room_meta = None
    chunk_meta = None
    face_chunks = None
    if is_interior and len(m.bones) > 1:
        (vertices, faces, uvs, materials, origins, source_sets,
         face_rooms, colors, room_meta) = _compact_rooms(
            vertices, faces, uvs, materials, origins, source_sets, face_rooms, colors, len(m.bones)
        )
    elif not is_interior and chunk_size > 0:
        (vertices, faces, uvs, materials, origins, source_sets,
         face_chunks, colors, chunk_meta) = _compact_chunks(
            vertices, faces, uvs, materials, origins, source_sets, colors, chunk_size
        )

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
    header = ['#pragma once', '#include <saturn/model3d.h>', '#include <saturn/collide3d.h>', '#include "sm64ds_play.h"']
    if is_interior:
        header += [
            '#define CASTLE_STAGE_ID 1u',
            '#define CASTLE_STAGE_NAME "C1F"',
            '#define CASTLE_HAS_SKYBOX 0',
            f'#define CASTLE_SPAWN_X {fx(-64.0)}',
            f'#define CASTLE_SPAWN_Y {fx(0.0)}',
            f'#define CASTLE_SPAWN_Z {fx(64.0)}',
            f'#define CASTLE_SPAWN_FLOOR_CEILING {fx(24.0)}',
            '#define CASTLE_SPAWN_YAW 0',
            '#define CASTLE_SPAWN_FACING 180',
            f'#define CASTLE_RETURN_SPAWN_X {fx(-64.0)}',
            f'#define CASTLE_RETURN_SPAWN_Z {fx(64.0)}',
            f'#define CASTLE_RETURN_FLOOR_CEILING {fx(24.0)}',
            '#define CASTLE_RETURN_YAW 0',
            '#define CASTLE_RETURN_FACING 180',
            '#define CASTLE_DEFAULT_CAM_DIST 52',
            '#define CASTLE_CLOSE_CAM_DIST 32',
            '#define CASTLE_BG_R 3',
            '#define CASTLE_BG_G 4',
            '#define CASTLE_BG_B 7',
            '#define CASTLE_WARP_AVAILABLE 1',
            f'#define CASTLE_WARP_TARGET_BIN "{warp_target or "0.BIN"}"',
            '#define CASTLE_WARP_TARGET_ENTRANCE 1u',
            f'#define CASTLE_WARP_MIN_X {fx(-78.0)}',
            f'#define CASTLE_WARP_MAX_X {fx(-50.0)}',
            f'#define CASTLE_WARP_MIN_Y {fx(-4.0)}',
            f'#define CASTLE_WARP_MAX_Y {fx(18.0)}',
            f'#define CASTLE_WARP_MIN_Z {fx(124.0)}',
            f'#define CASTLE_WARP_MAX_Z {fx(144.0)}',
        ]
    else:
        header += [
            '#define CASTLE_STAGE_ID 0u',
            '#define CASTLE_STAGE_NAME "EXT"',
            '#define CASTLE_HAS_SKYBOX 1',
            f'#define CASTLE_SPAWN_X {fx(0.0)}',
            f'#define CASTLE_SPAWN_Y {fx(100.0)}',
            f'#define CASTLE_SPAWN_Z {fx(256.0)}',
            f'#define CASTLE_SPAWN_FLOOR_CEILING {fx(512.0)}',
            '#define CASTLE_SPAWN_YAW 0',
            '#define CASTLE_SPAWN_FACING 180',
            f'#define CASTLE_RETURN_SPAWN_X {fx(0.0)}',
            f'#define CASTLE_RETURN_SPAWN_Z {fx(-18.0)}',
            f'#define CASTLE_RETURN_FLOOR_CEILING {fx(80.0)}',
            '#define CASTLE_RETURN_YAW 180',
            '#define CASTLE_RETURN_FACING 0',
            '#define CASTLE_DEFAULT_CAM_DIST 65',
            '#define CASTLE_CLOSE_CAM_DIST 35',
            '#define CASTLE_BG_R 12',
            '#define CASTLE_BG_G 20',
            '#define CASTLE_BG_B 30',
            '#define CASTLE_WARP_AVAILABLE 1',
            f'#define CASTLE_WARP_TARGET_BIN "{warp_target or "C1F.BIN"}"',
            '#define CASTLE_WARP_TARGET_ENTRANCE 0u',
            f'#define CASTLE_WARP_MIN_X {fx(-16.0)}',
            f'#define CASTLE_WARP_MAX_X {fx(16.0)}',
            f'#define CASTLE_WARP_MIN_Y {fx(44.0)}',
            f'#define CASTLE_WARP_MAX_Y {fx(66.0)}',
            f'#define CASTLE_WARP_MIN_Z {fx(-74.0)}',
            f'#define CASTLE_WARP_MAX_Z {fx(-58.0)}',
        ]
    header += [f'#define CASTLE_VERTEX_COUNT {len(vertices)}u', f'#define CASTLE_FACE_COUNT {len(faces)}u',
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
    slippery_mask = extract_clps_slippery_mask(
        fs, CASTLE_1F_OVERLAY_ID if is_interior else CASTLE_GROUNDS_OVERLAY_ID
    )
    code += ['static const uint32_t offsets[]={', array(offsets), '};',
             'static const uint16_t collision_indices[]={', array(indices), '};',
             'const sm64ds_collision_t castle_collision={.prisms=prisms,.offsets=offsets,.indices=collision_indices,',
             f'.count={len(prisms)},.nx={nx},.nz={nz},.origin_x={fx(ox)},.origin_z={fx(oz)},'
             f'.slippery_attrs=0x{slippery_mask:08x}u' + '};', '']
    props_report = {}
    c1f_objs = None
    if lut4:
        if is_interior:
            prop_h, prop_c, c1f_objs, props_report = _build_castle_1f_props(fs)
        else:
            prop_h, prop_c, props_report = _build_castle_props(fs)
        header.extend(prop_h)
        code.extend(prop_c)
        code.append('')
    if room_meta is not None:
        room_first, room_count_arr, room_vfirst, room_vcount, room_min, room_max = room_meta
        room_portals = _compute_room_portals(
            vertices, faces, face_rooms, len(room_first), c1f_objs.doors if c1f_objs else ()
        )
        room_adj = _compute_room_adjacency(
            room_min, room_max, c1f_objs.doors if c1f_objs else (), portals=room_portals
        )
        support_rooms = [face_rooms[f] for f, _ in planes] or [0]
        # Floor decal faces in room 0 (e.g. the iconic Sun Carpet floating 1 unit
        # above the sunken checkered pit floor) need a slight painter-depth bias so
        # underlying larger floor strips never sort over them.
        floor_decals = []
        for fi, (face, mat) in enumerate(zip(faces, materials)):
            if face_rooms[fi] != 0:
                continue
            tex = m.material_textures[mat]
            if tex is None or not any(px[3] == 0 for px in tex.pixels):
                continue
            ys = [vertices[vi][1] for vi in face]
            if max(ys) - min(ys) <= 0.05 and max(ys) < -0.5:
                floor_decals.append(fi)
        header += [
            '#define CASTLE_ROOM_CULLING 1',
            f'#define CASTLE_ROOM_COUNT {len(room_first)}u',
            f'#define CASTLE_FLOOR_DECAL_COUNT {len(floor_decals)}u',
            f'#define CASTLE_PORTAL_COUNT {len(room_portals)}u',
            'extern const uint16_t castle_room_first[CASTLE_ROOM_COUNT];',
            'extern const uint16_t castle_room_count[CASTLE_ROOM_COUNT];',
            'extern const uint16_t castle_room_vfirst[CASTLE_ROOM_COUNT];',
            'extern const uint16_t castle_room_vcount[CASTLE_ROOM_COUNT];',
            'extern const sat_vec3_t castle_room_min[CASTLE_ROOM_COUNT];',
            'extern const sat_vec3_t castle_room_max[CASTLE_ROOM_COUNT];',
            'extern const sat_aabb3_t castle_room_bounds[CASTLE_ROOM_COUNT];',
            'extern const uint8_t castle_room_adj[CASTLE_ROOM_COUNT];',
            'extern const uint8_t castle_support_rooms[];',
            'extern const uint16_t castle_floor_decals[];',
            'extern const sat_vec3_t castle_portal_pos[];',
            'extern const uint8_t castle_portal_room_a[];',
            'extern const uint8_t castle_portal_room_b[];',
        ]
        code += [
            'const uint16_t castle_room_first[CASTLE_ROOM_COUNT]={', array(room_first), '};',
            'const uint16_t castle_room_count[CASTLE_ROOM_COUNT]={', array(room_count_arr), '};',
            'const uint16_t castle_room_vfirst[CASTLE_ROOM_COUNT]={', array(room_vfirst), '};',
            'const uint16_t castle_room_vcount[CASTLE_ROOM_COUNT]={', array(room_vcount), '};',
            'const sat_vec3_t castle_room_min[CASTLE_ROOM_COUNT]={',
            ',\n'.join(vec(v) for v in room_min), '};',
            'const sat_vec3_t castle_room_max[CASTLE_ROOM_COUNT]={',
            ',\n'.join(vec(v) for v in room_max), '};',
            'const sat_aabb3_t castle_room_bounds[CASTLE_ROOM_COUNT]={',
            ',\n'.join(aabb_literal(lo, hi) for lo, hi in zip(room_min, room_max)), '};',
            'const uint8_t castle_room_adj[CASTLE_ROOM_COUNT]={', array(room_adj), '};',
            'const uint8_t castle_support_rooms[]={', array(support_rooms), '};',
            'const uint16_t castle_floor_decals[]={', array(floor_decals or [0]), '};',
            'const sat_vec3_t castle_portal_pos[]={',
            ',\n'.join(vec(pos) for pos, _, _ in room_portals) if room_portals else '{0,0,0}', '};',
            'const uint8_t castle_portal_room_a[]={',
            array([ra for _, ra, _ in room_portals] or [0]), '};',
            'const uint8_t castle_portal_room_b[]={',
            array([rb for _, _, rb in room_portals] or [0]), '};',
            '',
        ]
        props_report['castle_room_counts'] = room_count_arr
        props_report['castle_room_vcounts'] = room_vcount
        props_report['castle_room_adj'] = room_adj
        props_report['castle_portal_count'] = len(room_portals)
    elif chunk_meta is not None:
        chunk_first, chunk_count_arr, chunk_vfirst, chunk_vcount, chunk_min, chunk_max = chunk_meta
        support_chunks = [face_chunks[f] for f, _ in planes] or [0]
        header += [
            '#define CASTLE_CHUNK_CULLING 1',
            f'#define CASTLE_CHUNK_COUNT {len(chunk_first)}u',
            'extern const uint16_t castle_chunk_first[CASTLE_CHUNK_COUNT];',
            'extern const uint16_t castle_chunk_count[CASTLE_CHUNK_COUNT];',
            'extern const uint16_t castle_chunk_vfirst[CASTLE_CHUNK_COUNT];',
            'extern const uint16_t castle_chunk_vcount[CASTLE_CHUNK_COUNT];',
            'extern const sat_aabb3_t castle_chunk_bounds[CASTLE_CHUNK_COUNT];',
            'extern const uint8_t castle_support_chunks[];',
        ]
        code += [
            'const uint16_t castle_chunk_first[CASTLE_CHUNK_COUNT]={', array(chunk_first), '};',
            'const uint16_t castle_chunk_count[CASTLE_CHUNK_COUNT]={', array(chunk_count_arr), '};',
            'const uint16_t castle_chunk_vfirst[CASTLE_CHUNK_COUNT]={', array(chunk_vfirst), '};',
            'const uint16_t castle_chunk_vcount[CASTLE_CHUNK_COUNT]={', array(chunk_vcount), '};',
            'const sat_aabb3_t castle_chunk_bounds[CASTLE_CHUNK_COUNT]={',
            ',\n'.join(aabb_literal(lo, hi) for lo, hi in zip(chunk_min, chunk_max)), '};',
            'const uint8_t castle_support_chunks[]={', array(support_chunks), '};',
            '',
        ]
        props_report['castle_chunk_count'] = len(chunk_first)
        props_report['castle_chunk_max_faces'] = max(chunk_count_arr) if chunk_count_arr else 0
        props_report['castle_chunk_size'] = chunk_size
    props_report['clps_slippery_mask'] = f'0x{slippery_mask:08x}'
    if with_intro_props and not is_interior:
        header += ['#define CASTLE_INTRO_PROPS_AVAILABLE 1']
    (out / 'castle_scene.h').write_text('\n'.join(header) + '\n')
    (out / 'castle_scene.c').write_text('\n'.join(code))

    if lut4:
        convert(['--rom', str(rom), '--out', str(out), '--tile-size', '24', '--lut4', '--adaptive-size'])
        if not is_interior:
            convert(['--rom', str(rom), '--out', str(out), '--kind', 'skybox', '--model', 'data/vrbox/vr02.bmd',
                     '--name', 'skybox_preview', '--tile-size', '16', '--lut4', '--subdivide-sky'])
    else:
        convert(['--rom', str(rom), '--out', str(out), '--tile-size', '24'])
        if not is_interior:
            convert(['--rom', str(rom), '--out', str(out), '--kind', 'skybox', '--model', 'data/vrbox/vr02.bmd',
                     '--name', 'skybox_preview'])
    if not is_interior:
        # VDP2 sky for the default build; skybox_preview stays for diagnostics.
        sh, sc, sky_report = emit_sky_panorama(convert_bmd(fs.read('data/vrbox/vr02.bmd')), 'sky_panorama')
        (out / 'sky_panorama.h').write_text(sh)
        (out / 'sky_panorama.c').write_text(sc)
        (out / 'sky_panorama.json').write_text(json.dumps(sky_report, indent=2) + '\n')

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

    if with_intro_props and not is_interior:
        lakitu = convert_bmd(fs.read('data/enemy/c_jugem/c_jugem.bmd'))
        lakitu_wait = Animation(fs.read('data/enemy/c_jugem/c_jugem_wait.bca'), len(lakitu.bones))
        lh, lc, lakitu_stats = emit_model(
            lakitu, [('wait', lakitu_wait)], 'lakitu_actor',
            textured=True, tile_size=8, texture_budget=16 * 1024, lut4=lut4, adaptive_size=False,
        )
        (out / 'lakitu_actor.h').write_text(lh)
        (out / 'lakitu_actor.c').write_text(lc)

        pipe_m = convert_bmd(fs.read('data/normal_obj/obj_dokan/obj_dokan.bmd'))
        ph, pc, pipe_stats = emit_skybox(
            pipe_m, 'warp_pipe', palette_base=5, tile_size=16, lut4=lut4, adaptive_size=lut4,
        )
        (out / 'warp_pipe.h').write_text(ph)
        (out / 'warp_pipe.c').write_text(pc)

        sdat = SdatArchive(fs.read('data/sound_data.sdat'))
        swar_open = sdat.decode_swar_waves(35)
        sfx_rate = 12000
        whoosh_pcm = resample_wave_s8(swar_open[0], sfx_rate)
        pipe_pcm = resample_wave_s8(swar_open[3], sfx_rate)
        if len(whoosh_pcm) & 1:
            whoosh_pcm += b'\x00'
        if len(pipe_pcm) & 1:
            pipe_pcm += b'\x00'
        def _s8_rows(raw):
            rows = []
            for idx in range(0, len(raw), 16):
                vals = [b - 256 if b >= 128 else b for b in raw[idx:idx + 16]]
                rows.append('    ' + ', '.join(f'{v:4d}' for v in vals) + ',')
            return '\n'.join(rows)
        (out / 'castle_intro_sfx.h').write_text('\n'.join([
            '#pragma once',
            '#include <stdint.h>',
            f'#define CASTLE_INTRO_SFX_RATE {sfx_rate}u',
            f'#define CASTLE_INTRO_WHOOSH_SAMPLES {len(whoosh_pcm)}u',
            f'#define CASTLE_INTRO_PIPE_SAMPLES {len(pipe_pcm)}u',
            'extern const int8_t castle_intro_whoosh_pcm[CASTLE_INTRO_WHOOSH_SAMPLES];',
            'extern const int8_t castle_intro_pipe_pcm[CASTLE_INTRO_PIPE_SAMPLES];',
            '',
        ]))
        (out / 'castle_intro_sfx.c').write_text('\n'.join([
            '#include "castle_intro_sfx.h"',
            '/* Locally generated from a user-provided ROM; not for public distribution. */',
            'const int8_t castle_intro_whoosh_pcm[CASTLE_INTRO_WHOOSH_SAMPLES] = {',
            _s8_rows(whoosh_pcm),
            '};',
            'const int8_t castle_intro_pipe_pcm[CASTLE_INTRO_PIPE_SAMPLES] = {',
            _s8_rows(pipe_pcm),
            '};',
            '',
        ]))
        props_report['intro_props'] = {
            'lakitu_tex_bytes': lakitu_stats['texture_pixels_bytes'],
            'pipe_tex_bytes': pipe_stats['texture_pixels_bytes'],
            'pipe_scale_divisor': pipe_stats['scale_divisor'],
            'sfx_bytes': len(whoosh_pcm) + len(pipe_pcm),
        }
    report = {'rom_sha256': fs.sha256, 'stage': stage, 'render_vertices': len(vertices), 'render_faces': len(faces),
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
    p.add_argument('--stage', choices=('main_castle', 'castle_1f'), default='main_castle', help='Castle stage to export')
    p.add_argument('--chunk-size', type=float, default=0, help='Partition exterior world into XZ spatial chunks of this size for frustum culling')
    p.add_argument('--warp-target', default='', help='Override target binary name for stage warp (e.g. EXT.BIN)')
    p.add_argument('--with-intro-props', action='store_true', help='Also emit Lakitu, green warp pipe, and opening SFX for Act III cutscene')
    a = p.parse_args()
    prepare(a.rom, a.out, a.tile_size, a.split_edge, a.sdk_split_grid,
            a.libsaturn_source, a.split_radius, a.adaptive_faces, a.texture_budget, a.texture_samples,
            a.refine_face, a.refine_grid, a.refine_manifest, a.adaptive_priorities, a.stitch_source, a.stitch_cross_source,
            a.pack_split_quads, a.vertex_colors, a.merge_quads, a.lut4, a.max_edge, a.max_edge_radius, a.max_tile_size,
            a.stage, a.chunk_size, a.warp_target, a.with_intro_props)
