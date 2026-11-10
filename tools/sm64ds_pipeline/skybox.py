"""Camera-relative static skybox exporter (no fabricated skin/animation).

Nintendo DS vrbox BMDs use scaleShift=13, producing scene radii larger than
sat_fx16_t can store directly.  This module preserves the raw shape and UVs,
but normalizes a skybox uniformly into a bounded camera-local shell, which
must follow the camera position in the Saturn renderer.  This is *not* a
world-space collider or gameplay mesh.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from .bmd import Model
from .common import FormatError
from .textures import bake_face,index_bakes

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


def emit_skybox(model:Model, name:str, *, target_radius:int=128, textured:bool=True,
                tile_size:int=16, texture_budget:int=262144, palette_base:int=1)->tuple[str,str,dict]:
    """Emit a plain static sat_model_asset_t plus its model-space metadata.

    The Saturn caller must set world translation to the *current camera eye*,
    draw from inside (no backface culling), and keep skybox faces in the
    background pass; this exporter does not claim to implement a sky renderer.
    """
    if not re.fullmatch('[a-z][a-z0-9_]*',name):raise FormatError('invalid C symbol prefix')
    if not 1 <= palette_base <= 7:
        raise FormatError('skybox palette bank must be in 1..7 (bank 0 reserved for Mario)')
    geo=normalize_skybox(model,target_radius)
    textures=[];palette=();face_tex=[65535]*len(model.faces)
    if textured:
        bakes=[];locations=[]
        for idx,(material,uv) in enumerate(zip(model.face_materials,model.face_uvs)):
            if material>=len(model.material_textures):
                raise FormatError('skybox face references an invalid material')
            tex=model.material_textures[material]
            if tex is not None:
                bakes.append(bake_face(tex,uv,tile_size));locations.append(idx)
        if bakes:
            textures,palette,idxs=index_bakes(bakes)
            for i,texid in zip(locations,idxs):face_tex[i]=texid
    vram=sum((len(tex.pixels)+7)&~7 for tex in textures)
    if vram>texture_budget:raise FormatError(f'skybox textures require {vram} bytes > {texture_budget} budget')
    prefix=name.upper()
    header='\n'.join(['#pragma once','#include <saturn/model3d.h>',
        f'#define {prefix}_VERTEX_COUNT {len(model.vertices)}u',
        f'#define {prefix}_FACE_COUNT {len(model.faces)}u',
        f'#define {prefix}_TEXTURE_COUNT {len(textures)}u',
        f'#define {prefix}_SCALE_DIVISOR {geo.scale_divisor}u',
        f'extern const sat_model_asset_t {name}_model;', ''])
    code=[f'#include "{name}.h"','','/* Private, ROM-derived generated data.  Never commit this file. */','',
          f'static const sat_vec3_t {name}_vertices[{len(geo.vertices_fx16)}] = {{']
    code.extend('    {'+', '.join(str(int(x)) for x in xyz)+'},' for xyz in geo.vertices_fx16)
    code.extend(['};','',f'static const uint16_t {name}_indices[{len(model.faces)*4}] = {{'])
    code.extend('    '+', '.join(str(x) for x in face)+',' for face in model.faces)
    code.extend(['};',''])
    if textures:
        for i,tex in enumerate(textures):
            code.append(f'static const uint8_t {name}_pixels_{i}[{len(tex.pixels)}] = {{')
            code.extend(_format_bytes(tex.pixels));code.extend(['};'])
        code.extend(['',f'static const sat_model_texture_asset_t {name}_textures[{len(textures)}] = {{'])
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
                 f'    .vertices={name}_vertices, .vertex_count={len(model.vertices)},',
                 f'    .indices={name}_indices, .face_count={len(model.faces)},',
                 f'    .face_texture_indices={name}_face_textures,',
                 f'    .textures={name}_textures, .texture_count={len(textures)},' if textures else
                     '    .textures=0, .texture_count=0,',
                 f'    .palettes_rgb555={name}_palette, .palette_count=1, .palette_base={palette_base},' if textures else
                     '    .palettes_rgb555=0, .palette_count=0,',
                 '};',''])
    report={
        'output':name,'kind':'camera-relative-static-skybox','palette_base':palette_base,
        'source_scale_shift':model.scale_shift,
        'scale_divisor':geo.scale_divisor,
        'source_max_abs_coordinate':geo.source_max_units,
        'converted_max_abs_coordinate':geo.target_max_units,
        'max_scale_quant_error':geo.max_quant_error,
        'source_vertices':len(model.vertices),'native_quad_commands':len(model.faces),
        'source_materials':model.material_count,'source_textures':model.texture_count,
        'texture_tiles':len(textures),'texture_pixels_bytes':sum(len(t.pixels) for t in textures),
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
