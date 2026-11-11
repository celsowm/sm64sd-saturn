#!/usr/bin/env python3
"""Prepare a private, full-detail castle walking scene from a local ROM."""
import argparse
import json
import math
from pathlib import Path
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.cli import main as convert
from sm64ds_pipeline.kcl import decode_kcl
from sm64ds_pipeline.skybox import emit_skybox
from sm64ds_pipeline.textures import bake_face, index_bakes, BakedTexture


def fx(value):
    result=round(value*65536)
    if not -2**31<=result<2**31: raise ValueError('fixed-point overflow')
    return result
def vec(value): return '{'+','.join(str(fx(v)) for v in value)+'}'
def array(values, size=16):
    return '\n'.join(','.join(str(v) for v in values[i:i+size])+',' for i in range(0,len(values),size))


def prepare(rom: Path, out: Path, tile_size=16):
    fs=Filesystem.from_file(rom)
    m=convert_bmd(fs.read('data/stage/main_castle/main_castle_all.bmd'))
    prisms=decode_kcl(fs.read('data/stage/main_castle/main_castle.kcl'))
    def bake_castle(size):
        bakes=[]
        for material, uv in zip(m.face_materials,m.face_uvs):
            tex=m.material_textures[material]
            bakes.append(bake_face(tex,uv,size) if tex else BakedTexture(size,size,((180,180,180,255),)*(size*size)))
        return index_bakes(bakes)
    textures,palette,face_textures=bake_castle(tile_size)
    # Correct repeat modes reveal more distinct terrain tiles. Bound their
    # residency so face textures cannot consume the actor's RAM/VRAM budget.
    if sum(len(t.pixels) for t in textures)>192*1024 and tile_size>8:
        tile_size=8
        textures,palette,face_textures=bake_castle(tile_size)
    pixels=sum(len(t.pixels) for t in textures)
    if pixels>192*1024: raise ValueError('castle exceeds resident texture budget')
    vertices=[tuple(c*(1<<m.scale_shift)*64/4096 for c in (v.x,v.y,v.z)) for v in m.vertices]
    out.mkdir(parents=True,exist_ok=True)
    header=['#pragma once','#include <saturn/model3d.h>','#include "sm64ds_play.h"',
            f'#define CASTLE_VERTEX_COUNT {len(vertices)}u',f'#define CASTLE_FACE_COUNT {len(m.faces)}u',
            f'#define CASTLE_TEXTURE_COUNT {len(textures)}u','extern const sat_model_asset_t castle_model;',
            'extern const sm64ds_collision_t castle_collision;']
    code=['#include "castle_scene.h"','/* Private ROM-derived data. Never commit. */',
          'static const sat_vec3_t vertices[]={',',\n'.join(vec(v) for v in vertices),'};',
          'static const uint16_t faces[]={',array([i for face in m.faces for i in face]),'};']
    for i,t in enumerate(textures): code.extend([f'static const uint8_t pixels_{i}[]={{',array(t.pixels),'};'])
    code+=['static const sat_model_texture_asset_t textures[]={']
    for i,t in enumerate(textures): code.append(f'{{.pixels=pixels_{i},.width={t.width},.height={t.height},.pixel_count={len(t.pixels)}}},')
    code+=['};','static const uint16_t palette[]={',array(palette),'};',
           'static const uint16_t face_textures[]={',array(face_textures),'};',
           'const sat_model_asset_t castle_model={.vertices=vertices,',
           f'.vertex_count={len(vertices)},.indices=faces,.face_count={len(m.faces)},',
           f'.face_texture_indices=face_textures,.textures=textures,.texture_count={len(textures)},',
           '.palettes_rgb555=palette,.palette_count=1,.palette_base=2};']
    code+=['static const sm64ds_prism_t prisms[]={']
    bounds=[]
    for p in prisms:
        lo=tuple(min(v[i] for v in p.vertices) for i in range(3))
        hi=tuple(max(v[i] for v in p.vertices) for i in range(3))
        bounds.append((lo,hi))
        code.append('{'+','.join((vec(p.vertices[0]),vec(p.normal),'{'+','.join(vec(e) for e in p.edges)+'}',vec(lo),vec(hi),str(fx(p.extent)),str(p.attribute)))+'},')
    code+=['};']
    ox=math.floor((min(b[0][0] for b in bounds)-4)/32)*32
    oz=math.floor((min(b[0][2] for b in bounds)-4)/32)*32
    nx=math.ceil((max(b[1][0] for b in bounds)+4-ox)/32)
    nz=math.ceil((max(b[1][2] for b in bounds)+4-oz)/32)
    bins=[[] for _ in range(nx*nz)]
    for i,(lo,hi) in enumerate(bounds):
        for z in range(max(0,int((lo[2]-4-oz)//32)),min(nz,int((hi[2]+4-oz)//32)+1)):
            for x in range(max(0,int((lo[0]-4-ox)//32)),min(nx,int((hi[0]+4-ox)//32)+1)):
                bins[z*nx+x].append(i)
    offsets=[0]; indices=[]
    for b in bins: indices.extend(b);offsets.append(len(indices))
    code+=['static const uint32_t offsets[]={',array(offsets),'};',
           'static const uint16_t collision_indices[]={',array(indices),'};',
           'const sm64ds_collision_t castle_collision={.prisms=prisms,.offsets=offsets,.indices=collision_indices,',
           f'.count={len(prisms)},.nx={nx},.nz={nz},.origin_x={fx(ox)},.origin_z={fx(oz)}'+'};','']
    (out/'castle_scene.h').write_text('\n'.join(header)+'\n')
    (out/'castle_scene.c').write_text('\n'.join(code))
    convert(['--rom',str(rom),'--out',str(out),'--tile-size','24'])
    convert(['--rom',str(rom),'--out',str(out),'--kind','skybox','--model','data/vrbox/vr02.bmd','--name','skybox_preview'])
    # The gameplay head shares the body's bone-local convention. The
    # top-level b_mario_head_cap is a different, larger model/orientation.
    head=convert_bmd(fs.read('ARCHIVE/arc0.narc:129'))
    h,c,head_report=emit_skybox(head,'mario_head',palette_base=4,tile_size=24)
    # Reuse the plain rigid-model emitter, retaining head-local coordinates.
    # The runtime attaches it to bone 15 rather than following the camera.
    if head_report['scale_divisor']!=1:
        raise ValueError('head attachment requires its original model scale')
    (out/'mario_head.h').write_text(h)
    (out/'mario_head.c').write_text(c)
    report={'rom_sha256':fs.sha256,'render_vertices':len(vertices),'render_faces':len(m.faces),
            'castle_tile_size':tile_size,'actor_tile_size':24,
            'castle_texture_bytes':pixels,'castle_texture_tiles':len(textures),'kcl_prisms':len(prisms),
            'collision_grid':[nx,nz],'collision_grid_references':len(indices),
            'world_units_per_bmd_unit':64,'world_units_per_ds_unit':0.064,
            'head_attachment_bone':15,'head_texture_bytes':head_report['texture_pixels_bytes'],
            'head_model':'ARCHIVE/arc0.narc:129',
            'render_lod':'original full-detail mesh; no visual HLOD switching',
            'physics':'prototype KCL locomotion; CLPS attributes retained but behaviors not implemented'}
    (out/'castle_scene.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('private/castle'))
    p.add_argument('--tile-size',type=int,choices=(8,16),default=16)
    a=p.parse_args();prepare(a.rom,a.out,a.tile_size)
