"""Camera-relative static skybox exporter (no fabricated skin/animation).

Nintendo DS vrbox BMDs use scaleShift=13, producing scene radii larger than
sat_fx16_t can store directly.  This module preserves the raw shape and UVs,
but normalizes a skybox uniformly into a bounded camera-local shell, which
must follow the camera position in the Saturn renderer.  This is *not* a
world-space collider or gameplay mesh.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import re
from .bmd import Model
from .common import FormatError
from .emit import _actor_tile_size, _rgb_group
from .quad_merge import merge_coplanar_quads
from .textures import bake_face,index_bakes,index_bakes_lut4

@dataclass(frozen=True)
class SkyboxGeometry:
    vertices_fx16:tuple[tuple[int,int,int],...]
    source_max_units:float
    target_max_units:float
    scale_divisor:int
    max_quant_error:float


def _round_div(n:int,d:int)->int:
    if d<=0:raise ValueError('denominator must be positive')
    return (n+d//2)//d if n>=0 else -((-n+d//2)//d)


def normalize_skybox(model:Model, target_radius:int=128)->SkyboxGeometry:
    """Uniform power-of-two normalization; exact on ASME vrbox shift-13 meshes.

    Coordinates are derived from DS raw 4.12 positions with scaleShift
    applied, divided by the same factor for *every* vertex and axis.  The
    output is Saturn signed 16.16, without overflowing intermediate floats.
    """
    if not 16<=target_radius<=1024:
        raise FormatError('skybox target radius must be 16..1024')
    if len(model.bones)!=1 or model.weighted_count or not model.vertices or not model.faces:
        raise FormatError('static skybox needs one rigid root and nonempty geometry')
    bone=model.bones[0]
    if (bone.idx,bone.parent,bone.trans,bone.scale,bone.angles)!=(0,-1,(0,0,0),(4096,4096,4096),(0,0,0)):
        raise FormatError('skybox has animated/rest transform: do not erase it')
    if any(v.joint!=0 for v in model.vertices):
        raise FormatError('skybox contains matrix slots outside the root')
    max_raw=max(abs(x) for v in model.vertices for x in (v.x,v.y,v.z))
    if max_raw==0:raise FormatError('degenerate skybox')
    raw_mul=1<<model.scale_shift
    source_max=max_raw*raw_mul/4096
    divisor=1
    while max_raw*raw_mul>target_radius*4096*divisor:
        divisor*=2
    num=raw_mul*65536
    den=4096*divisor
    values=[];q_err=0.
    for v in model.vertices:
        raw=(v.x,v.y,v.z)
        fx=tuple(_round_div(x*num,den) for x in raw)
        if any(abs(x)>=2**31 for x in fx):raise FormatError('normalized skybox overflows sat_fx16_t')
        q_err=max(q_err,*(abs(actual/65536 - source*raw_mul/(4096*divisor)) for source,actual in zip(raw,fx)))
        values.append(fx)
    return SkyboxGeometry(tuple(values),source_max,source_max/divisor,divisor,q_err)


def _format_bytes(values:bytes)->list[str]:
    return ['    '+', '.join(f'0x{byte:02x}' for byte in values[i:i+16])+',' for i in range(0,len(values),16)]


def _subdivide_sky(verts_fx, faces, uvs, materials, max_edge: float = 54.0):
    """Merge skybox quads and subdivide oversized sky panels to avoid near-clip fallback."""
    verts = [tuple(c / 65536.0 for c in v) for v in verts_fx]
    faces, uvs, materials, _, _, _ = merge_coplanar_quads(
        verts, faces, uvs, materials, min_dot=0.995, max_plane_dist=0.5
    )
    intern = {tuple(round(c, 6) for c in v): i for i, v in enumerate(verts)}

    def add_pt(p):
        key = tuple(round(c, 6) for c in p)
        if key not in intern:
            intern[key] = len(verts)
            verts.append(p)
        return intern[key]

    def mid3(a, b):
        return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)

    def mid2(a, b):
        return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)

    def dist(a, b):
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

    queue = list(zip(faces, uvs, materials))
    out_f = []
    out_u = []
    out_m = []
    for f, uv, mat in queue:
        work = [(f, uv)]
        for _ in range(1):
            nxt = []
            for cf, cuv in work:
                if cf[2] == cf[3]:
                    p0, p1, p2 = verts[cf[0]], verts[cf[1]], verts[cf[2]]
                    if max(dist(p0, p1), dist(p1, p2), dist(p2, p0)) <= max_edge:
                        nxt.append((cf, cuv))
                        continue
                    m01 = add_pt(mid3(p0, p1))
                    m12 = add_pt(mid3(p1, p2))
                    m20 = add_pt(mid3(p2, p0))
                    u01, u12, u20 = mid2(cuv[0], cuv[1]), mid2(cuv[1], cuv[2]), mid2(cuv[2], cuv[0])
                    nxt.append(((cf[0], m01, m20, m20), (cuv[0], u01, u20, u20)))
                    nxt.append(((m01, cf[1], m12, m12), (u01, cuv[1], u12, u12)))
                    nxt.append(((m20, m12, cf[2], cf[2]), (u20, u12, cuv[2], cuv[2])))
                    nxt.append(((m01, m12, m20, m20), (u01, u12, u20, u20)))
                else:
                    p0, p1, p2, p3 = verts[cf[0]], verts[cf[1]], verts[cf[2]], verts[cf[3]]
                    eu = max(dist(p0, p1), dist(p3, p2))
                    ev = max(dist(p0, p3), dist(p1, p2))
                    if max(eu, ev) <= max_edge:
                        nxt.append((cf, cuv))
                        continue
                    if eu > max_edge and ev > max_edge:
                        m01 = add_pt(mid3(p0, p1))
                        m12 = add_pt(mid3(p1, p2))
                        m23 = add_pt(mid3(p2, p3))
                        m30 = add_pt(mid3(p3, p0))
                        mc = add_pt(mid3(mid3(p0, p1), mid3(p3, p2)))
                        u01 = mid2(cuv[0], cuv[1])
                        u12 = mid2(cuv[1], cuv[2])
                        u23 = mid2(cuv[2], cuv[3])
                        u30 = mid2(cuv[3], cuv[0])
                        uc = mid2(u01, u23)
                        nxt.append(((cf[0], m01, mc, m30), (cuv[0], u01, uc, u30)))
                        nxt.append(((m01, cf[1], m12, mc), (u01, cuv[1], u12, uc)))
                        nxt.append(((mc, m12, cf[2], m23), (uc, u12, cuv[2], u23)))
                        nxt.append(((m30, mc, m23, cf[3]), (u30, uc, u23, cuv[3])))
                    elif eu >= ev:
                        m01 = add_pt(mid3(p0, p1))
                        m23 = add_pt(mid3(p2, p3))
                        u01 = mid2(cuv[0], cuv[1])
                        u23 = mid2(cuv[2], cuv[3])
                        nxt.append(((cf[0], m01, m23, cf[3]), (cuv[0], u01, u23, cuv[3])))
                        nxt.append(((m01, cf[1], cf[2], m23), (u01, cuv[1], cuv[2], u23)))
                    else:
                        m12 = add_pt(mid3(p1, p2))
                        m30 = add_pt(mid3(p3, p0))
                        u12 = mid2(cuv[1], cuv[2])
                        u30 = mid2(cuv[3], cuv[0])
                        nxt.append(((cf[0], cf[1], m12, m30), (cuv[0], cuv[1], u12, u30)))
                        nxt.append(((m30, m12, cf[2], cf[3]), (u30, u12, cuv[2], cuv[3])))
            work = nxt
        for cf, cuv in work:
            out_f.append(cf)
            out_u.append(cuv)
            out_m.append(mat)
    out_verts_fx = tuple(tuple(round(c * 65536.0) for c in v) for v in verts)
    return out_verts_fx, out_f, out_u, out_m


def emit_skybox(model:Model, name:str, *, target_radius:int=128, textured:bool=True,
                tile_size:int=16, texture_budget:int=262144, palette_base:int=1,
                lut4:bool=False, adaptive_size:bool=False, subdivide_sky:bool=False)->tuple[str,str,dict]:
    """Emit a plain static sat_model_asset_t plus its model-space metadata.

    The Saturn caller must set world translation to the *current camera eye*,
    draw from inside (no backface culling), and keep skybox faces in the
    background pass; this exporter does not claim to implement a sky renderer.
    """
    if not re.fullmatch('[a-z][a-z0-9_]*',name):raise FormatError('invalid C symbol prefix')
    if not lut4 and not 1 <= palette_base <= 7:
        raise FormatError('skybox palette bank must be in 1..7 (bank 0 reserved for Mario)')
    geo=normalize_skybox(model,target_radius)
    verts_fx=geo.vertices_fx16
    faces=model.faces
    uvs=model.face_uvs
    mats=model.face_materials
    if subdivide_sky:
        verts_fx,faces,uvs,mats=_subdivide_sky(verts_fx,faces,uvs,mats)
    textures=[];palette=();luts=();lut_count=0;face_tex=[65535]*len(faces)
    if textured:
        bakes=[];locations=[];groups=[]
        for idx,(material,uv) in enumerate(zip(mats,uvs)):
            if material>=len(model.material_textures):
                raise FormatError('skybox face references an invalid material')
            tex=model.material_textures[material]
            if tex is not None:
                if adaptive_size:
                    w,h=_actor_tile_size(tex,uv,tile_size)
                    b=bake_face(tex,uv,w,height=h)
                else:
                    b=bake_face(tex,uv,tile_size,samples=2 if subdivide_sky else 1)
                bakes.append(b);locations.append(idx);groups.append(_rgb_group(material,b))
        if bakes:
            if lut4:
                textures,luts,lut_count,idxs=index_bakes_lut4(bakes,groups=groups)
            else:
                textures,palette,idxs=index_bakes(bakes)
            for i,texid in zip(locations,idxs):face_tex[i]=texid
    vram=lut_count*32+sum((len(tex.pixels)+7)&~7 for tex in textures)
    if vram>texture_budget:raise FormatError(f'skybox textures require {vram} bytes > {texture_budget} budget')
    prefix=name.upper()
    header='\n'.join(['#pragma once','#include <saturn/model3d.h>',
        f'#define {prefix}_VERTEX_COUNT {len(verts_fx)}u',
        f'#define {prefix}_FACE_COUNT {len(faces)}u',
        f'#define {prefix}_TEXTURE_COUNT {len(textures)}u',
        f'#define {prefix}_SCALE_DIVISOR {geo.scale_divisor}u',
        f'extern const sat_model_asset_t {name}_model;', ''])
    code=[f'#include "{name}.h"','','/* Private, ROM-derived generated data.  Never commit this file. */','',
          f'static const sat_vec3_t {name}_vertices[{len(verts_fx)}] = {{']
    code.extend('    {'+', '.join(str(int(x)) for x in xyz)+'},' for xyz in verts_fx)
    code.extend(['};','',f'static const uint16_t {name}_indices[{len(faces)*4}] = {{'])
    code.extend('    '+', '.join(str(x) for x in face)+',' for face in faces)
    code.extend(['};',''])
    if textures:
        for i,tex in enumerate(textures):
            code.append(f'static const uint8_t {name}_pixels_{i}[{len(tex.pixels)}] = {{')
            code.extend(_format_bytes(tex.pixels));code.extend(['};'])
        code.extend(['',f'static const sat_model_texture_asset_t {name}_textures[{len(textures)}] = {{'])
        if lut4:
            for i,t in enumerate(textures):
                code.append(f'    {{.pixels={name}_pixels_{i}, .width={t.width}, .height={t.height},'
                            f' .palette_slot={t.lut_slot}, .flags=SAT_MODEL_TEXTURE_LUT4, .pixel_count={t.width*t.height}}},')
            code.extend(['};',f'static const uint16_t {name}_luts[{len(luts)}] = {{'])
            code.extend('    '+', '.join(f'0x{x:04x}' for x in luts[i:i+12])+',' for i in range(0,len(luts),12))
            code.extend(['};',''])
        else:
            for i,t in enumerate(textures):
                code.append(f'    {{.pixels={name}_pixels_{i}, .width={t.width}, .height={t.height},'
                            f' .palette_slot=0, .flags=0, .pixel_count={t.width*t.height}}},')
            code.extend(['};',f'static const uint16_t {name}_palette[256] = {{'])
            code.extend('    '+', '.join(f'0x{x:04x}' for x in palette[i:i+12])+',' for i in range(0,256,12))
            code.extend(['};',''])
    code.append(f'static const uint16_t {name}_face_textures[{len(face_tex)}] = {{')
    code.extend('    '+', '.join('SAT_MESH_TEXTURE_NONE' if k==65535 else str(k)
                           for k in face_tex[i:i+12])+',' for i in range(0,len(face_tex),12))
    code.extend(['};',f'const sat_model_asset_t {name}_model = {{',
                 f'    .vertices={name}_vertices, .vertex_count={len(verts_fx)},',
                 f'    .indices={name}_indices, .face_count={len(faces)},',
                 f'    .face_texture_indices={name}_face_textures,',
                 f'    .textures={name}_textures, .texture_count={len(textures)},' if textures else
                     '    .textures=0, .texture_count=0,',
                 (f'    .palettes_rgb555=0, .palette_count=0, .palette_base=0, .luts_rgb555={name}_luts, .lut_count={lut_count},'
                  if lut4 else f'    .palettes_rgb555={name}_palette, .palette_count=1, .palette_base={palette_base},') if textures else
                     '    .palettes_rgb555=0, .palette_count=0,',
                 '};',''])
    report={
        'output':name,'kind':'camera-relative-static-skybox','palette_base':0 if lut4 else palette_base,
        'lut4':lut4,'lut_count':lut_count,
        'source_scale_shift':model.scale_shift,
        'scale_divisor':geo.scale_divisor,
        'source_max_abs_coordinate':geo.source_max_units,
        'converted_max_abs_coordinate':geo.target_max_units,
        'max_scale_quant_error':geo.max_quant_error,
        'source_vertices':len(verts_fx),'native_quad_commands':len(faces),
        'source_materials':model.material_count,'source_textures':model.texture_count,
        'texture_tiles':len(textures),'texture_pixels_bytes':lut_count*32+sum(len(t.pixels) for t in textures),
        'estimated_vdp1_texture_bytes':vram,'faces_without_texture':face_tex.count(65535),
        'requirements':['position shell at camera.eye every frame',
                        'cull_backfaces=0 (view from inside)',
                        'submit pass 0, actors pass 1',
                        'reserve RGB555 palette bank 0 for Mario',
                        'no collision or world-scale gameplay semantics'],
        'notes':['This is a normalized static background, not original DS world coordinates',
                 'ROM-derived C/H must remain private',
                 'No Saturn emulator or hardware visual parity claim']}
    return header,'\n'.join(code),report
