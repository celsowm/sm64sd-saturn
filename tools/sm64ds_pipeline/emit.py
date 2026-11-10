"""C emitters for LibSaturn model/skin/clip structures and VDP1 baked textures.

No Nintendo input bytes are committed: consumers must generate private
mario.c/h from a ROM they provide locally. Full rigging keeps skeleton, skin,
clips, scales, textures and material allocation as distinct runtime objects.
"""
from __future__ import annotations
import re
from .common import FormatError,checked_fx,quaternion
from .bmd import Model
from .bca import Animation
from .textures import bake_face,index_bakes
from .skinning import build_layout


def vec(x):
    return '{' + ', '.join(str(int(v)) for v in x) + '}'


def c_array_bytes(values,width=16):
    return '\n'.join('    '+', '.join('0x%02x'%v for v in values[i:i+width])+','
                     for i in range(0,len(values),width))


def emit_model(model:Model,animations:list[tuple[str,Animation]],name:str,
               rate_num:int=30,rate_den:int=1, *, textured:bool=True,
               tile_size:int=16,texture_budget:int=256*1024):
    if not re.fullmatch(r'[a-z][a-z0-9_]*',name):
        raise FormatError('output symbol prefix must be a C identifier')
    if not 1<=rate_num<=32767 or not 1<=rate_den<=65535:
        raise FormatError('clip rates out of LibSaturn bounds')
    if not animations or len({k for k,_ in animations})!=len(animations):
        raise FormatError('at least one unique animation is required')
    for label,clip in animations:
        if not re.fullmatch(r'[a-z][a-z0-9_]*',label):raise FormatError('bad clip name')
        if clip.joints!=len(model.bones):raise FormatError(f'{label} joint count mismatch')
    skin=build_layout(model)
    if len(skin.rigid)+len(skin.blend)>65535:
        raise FormatError('LibSaturn vertex count exceeds uint16')
    if len(model.faces)>65535:raise FormatError('face count exceeds LibSaturn limit')
    header=['#pragma once','#include <saturn/model3d.h>',
            '#include <saturn/skeleton3d.h>','#include <saturn/skin3d.h>',
            '#include "sm64ds_pose.h"',
            f'#define {name.upper()}_VERTEX_COUNT {len(model.vertices)}u',
            f'#define {name.upper()}_FACE_COUNT {len(model.faces)}u',
            f'#define {name.upper()}_JOINT_COUNT {len(model.bones)}u',
            f'#define {name.upper()}_CLIP_COUNT {len(animations)}u',
            f'extern const sat_model_asset_t {name}_model;',
            f'extern const sat_skeleton_asset_t {name}_skeleton;',
            f'extern const sat_skin_asset_t {name}_skin;',
            f'extern const sat_skeleton_clip_t {name}_clips[{len(animations)}];',
            f'extern const sm64ds_scale_clip_t {name}_scale_clips[{len(animations)}];','']
    lines=[f'#include "{name}.h"','',
           '/* Locally generated from a user-provided ROM; not for public distribution. */','']
    lines.append(f'static const sat_skeleton_joint_t {name}_joints[{len(model.bones)}] = {{')
    for bone in model.bones:
        par='SAT_TRANSFORM3D_ROOT' if bone.parent<0 else str(bone.parent)
        lines.append(f'    {{.parent={par}, .rest_translation={vec(checked_fx(t) for t in bone.trans)}, '
                     f'.rest_rotation={vec(quaternion(bone.angles))}, .rest_scale={vec(checked_fx(s) for s in bone.scale)}}},')
    lines += ['};',f'const sat_skeleton_asset_t {name}_skeleton = '
              f'{{.joints={name}_joints, .joint_count={len(model.bones)}}};','']

    # The static model.vertices are source-space placeholders. Render by
    # applying the character's sampled joint matrices into an actor-owned mesh.
    lines.append(f'static const sat_vec3_t {name}_source_vertices[{len(model.vertices)}] = {{')
    for i in skin.order:
        v=model.vertices[i]
        lines.append(f'    {vec(checked_fx(x*(1<<model.scale_shift)) for x in (v.x,v.y,v.z))},')
    lines += ['};','']
    if skin.rigid:
        lines.append(f'static const sat_skin_rigid_t {name}_rigid[{len(skin.rigid)}] = {{')
        lines += [f'    {{{vec(v.pos)}, {v.joint}, 0}},' for v in skin.rigid]
        lines += ['};','']
    if skin.blend:
        lines.append(f'static const sat_skin_blend_t {name}_blended[{len(skin.blend)}] = {{')
        for b in skin.blend:
            lines.append(f'    {{{vec(b.joints)}, {b.count}, {vec(b.weights)}, '
                         f'{{{", ".join(vec(p) for p in b.positions)}}}}},')
        lines += ['};','']
    lines += [f'const sat_skin_asset_t {name}_skin = {{',
              f'    .rigid={name}_rigid,' if skin.rigid else '    .rigid=0,',
              f'    .blend={name}_blended,' if skin.blend else '    .blend=0,',
              f'    .rigid_count={len(skin.rigid)}, .blend_count={len(skin.blend)},',
              f'    .joint_count={len(model.bones)}, .pos_shift={skin.pos_shift},',
              f'    .max_joint={max((v.joint for v in skin.rigid),default=0) if not skin.blend else max([v.joint for v in skin.rigid]+[x for b in skin.blend for x in b.joints[:b.count]])}',
              '};','']
    lines.append(f'static const uint16_t {name}_faces[{len(skin.indices)*4}] = {{')
    lines.extend('    '+', '.join(map(str,face))+',' for face in skin.indices)
    lines += ['};','']

    textures=[];palette=();indices=[65535]*len(model.faces)
    if textured:
        bakes=[];which=[]
        for i,(mat,uv) in enumerate(zip(model.face_materials,model.face_uvs)):
            source=model.material_textures[mat]
            if source is None:continue
            bakes.append(bake_face(source,uv,tile_size));which.append(i)
        if bakes:
            textures,palette,local_index=index_bakes(bakes)
            for i,j in zip(which,local_index):indices[i]=j
        tex_bytes=sum(len(t.pixels)+(7 & -(len(t.pixels))) for t in textures)
        if tex_bytes>texture_budget:
            raise FormatError(f'baked VDP1 textures use {tex_bytes} bytes, budget is {texture_budget}; use --tile-size 8')
        if len(textures)>65535:raise FormatError('too many VDP1 texture tiles')
    if textures:
        for i,tex in enumerate(textures):
            lines += [f'static const uint8_t {name}_texture_{i}[{len(tex.pixels)}] = {{',
                      c_array_bytes(tex.pixels),'};']
        lines += ['',f'static const sat_model_texture_asset_t {name}_texture_descriptors[{len(textures)}] = {{']
        lines += [f'    {{.pixels={name}_texture_{i}, .width={t.width}, .height={t.height}, '
                  f'.palette_slot=0, .flags=0, .pixel_count={t.width*t.height}}},'
                  for i,t in enumerate(textures)]
        lines += ['};',f'static const uint16_t {name}_palette[256] = {{']
        lines += [c_array_bytes(palette,12).replace('0x','0x')]
        # c_array_bytes is 8-bit; RGB555 entries need full 16-bit emit instead.
        lines[-1]='\n'.join('    '+', '.join('0x%04x'%v for v in palette[i:i+12])+','
                           for i in range(0,256,12))
        lines += ['};','']
    lines += [f'static const uint16_t {name}_face_textures[{len(indices)}] = {{']
    lines.extend('    '+', '.join('SAT_MESH_TEXTURE_NONE' if n==65535 else str(n)
                               for n in indices[i:i+12])+',' for i in range(0,len(indices),12))
    lines += ['};',f'const sat_model_asset_t {name}_model = {{',
              f'    .vertices={name}_source_vertices, .vertex_count={len(model.vertices)},',
              f'    .indices={name}_faces, .face_count={len(model.faces)},',
              f'    .face_texture_indices={name}_face_textures,',
              f'    .textures={name}_texture_descriptors, .texture_count={len(textures)},' if textures else
              '    .textures=0, .texture_count=0,',
              f'    .palettes_rgb555={name}_palette, .palette_count=1, .palette_base=0,' if textures else
              '    .palettes_rgb555=0, .palette_count=0,',
              '};','']
    header.insert(9,f'#define {name.upper()}_TEXTURE_COUNT {len(textures)}u')
    clip_stats=[];scale_entries=[]
    for label,clip in animations:
        pose=[];scales=[];non_unit=False;last_q=[None]*clip.joints
        for frame in range(clip.frames):
            for joint,(translation,rotation,scale) in enumerate(clip.sample(frame)):
                q=quaternion(rotation)
                if last_q[joint] and sum(x*y for x,y in zip(q,last_q[joint]))<0:
                    q=tuple(-x for x in q)
                last_q[joint]=q
                pose.append((vec(checked_fx(v) for v in translation),vec(q)))
                scale_fx=tuple(checked_fx(v) for v in scale)
                scales.append(scale_fx)
                if scale_fx!=(65536,65536,65536):non_unit=True
        lines += [f'static const sat_skeleton_pose_joint_t {name}_{label}_poses[{len(pose)}] = {{']
        lines.extend(f'    {{{t}, {q}}},' for t,q in pose)
        lines += ['};','']
        if non_unit:
            lines += [f'static const sat_vec3_t {name}_{label}_scales[{len(scales)}] = {{']
            lines.extend(f'    {vec(s)},' for s in scales)
            lines += ['};','']
        scale_entries.append((label,non_unit))
        clip_stats.append({'name':label,'frames':clip.frames,'joint_tracks':clip.joints,
                           'loop':clip.loop,'animated_scales':non_unit})
    lines += [f'const sat_skeleton_clip_t {name}_clips[{len(animations)}] = {{']
    for label,clip in animations:
        lines.append(f'    {{.frames={name}_{label}_poses, .frame_count={clip.frames}, '
                     f'.joint_count={clip.joints}, .rate_num={rate_num}, .rate_den={rate_den}, '
                     f'.flags={"SAT_CLIP_FLAG_LOOP" if clip.loop else "0"}}},')
    lines += ['};','',f'const sm64ds_scale_clip_t {name}_scale_clips[{len(animations)}] = {{']
    for label,sc in scale_entries:
        lines.append(f'    {{.frames={name}_{label}_scales, '
                     f'.frame_count={dict((k,v) for k,v in animations)[label].frames}, .joint_count={len(model.bones)}}},'
                     if sc else f'    {{.frames=0, .frame_count=0, .joint_count={len(model.bones)}}},')
    lines += ['};','']
    report={'output':name,'geometry_mode':'VDP1 indexed8 textured' if textured else 'untextured',
            'pose_rate_assumption':f'{rate_num}/{rate_den} Hz; verify with original game',
            'skeleton_joints':len(model.bones),'rigid_vertices':len(skin.rigid),
            'blended_vertices':len(skin.blend),'native_quad_commands':len(model.faces),
            'source_materials':model.material_count,'source_textures':model.texture_count,
            'weighted_source_matrices':model.weighted_count,'gx_commands':model.gx_commands,
            'clip_stats':clip_stats,'texture_tiles':len(textures),
            'texture_pixels_bytes':sum(len(t.pixels) for t in textures),
            'source_color_count':len({v for v in palette if v}),
            'max_skin_anchor_quant_error':skin.quant_error,
            'estimated_clip_bytes':sum(a.frames*a.joints*20 for _,a in animations),
            'notes':['ROM-derived C/H files must remain private','renderer has not been boot-tested on an SH-2',
                     'BMD material colors, polygon alpha and lighting not proven visually equivalent',
                     'scale clips use runtime/sm64ds_pose.c to compute scaled joint-world matrices']}
    return '\n'.join(header)+'\n','\n'.join(lines)+'\n',report
