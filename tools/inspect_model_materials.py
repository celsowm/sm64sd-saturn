#!/usr/bin/env python3
"""Summarize ROM model material usage and source polygon attributes."""
import argparse
import json
from collections import Counter
from pathlib import Path
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.compression import lz77
from sm64ds_pipeline.common import field


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--model',required=True,help='NitroFS path or ARCHIVE/name.narc:index')
    a=p.parse_args()
    fs=Filesystem.from_file(a.rom);blob=fs.read(a.model)
    model=convert_bmd(blob);raw=lz77(blob)
    count,base=field(raw,0x24,'II');used=Counter(model.face_materials)
    texture_count,texture_base=field(raw,0x14,'II')
    rows=[]
    for i in range(count):
        at=base+i*0x30
        params,flags,diffuse,specular=field(raw,at+0x20,'IIII')
        texid=field(raw,at+4,'I')
        texflags=field(raw,texture_base+texid*0x14+0x10,'I') if texid<texture_count else 0
        combined=params|texflags
        rows.append({'material':i,'faces':used[i],
                     'textured':model.material_textures[i] is not None,
                     'texture_params':f'{params:08x}','texture_flags':f'{texflags:08x}',
                     'texture_generation':combined>>30,
                     'zero_transparent':bool(combined&0x20000000),
                     'zero_transparent_from_material':bool(params&0x20000000 and not texflags&0x20000000),
                     'flags':f'{flags:08x}','diffuse_ambient':f'{diffuse:08x}',
                     'specular_emission':f'{specular:08x}',
                     'render_back':bool(flags&0x40),'render_front':bool(flags&0x80),
                     'alpha':(flags>>16)&31,'hidden':bool(flags&0x80000000)})
    print(json.dumps({'model':a.model,'faces':len(model.faces),
                      'gx_polygon_attr_commands':model.gx_commands.get('29',0),
                      'gx_normal_commands':model.gx_commands.get('21',0),
                      'materials':rows},indent=2))

if __name__=='__main__':main()
