#!/usr/bin/env python3
"""Inspect source BMD faces, materials and world-scaled vertex positions."""
import argparse
import json
from pathlib import Path
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.filesystem import Filesystem


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--face',type=int,action='append',required=True)
    p.add_argument('--world-scale',type=float,default=1)
    a=p.parse_args();m=convert_bmd(Filesystem.from_file(a.rom).read(a.model))
    result=[]
    for i in a.face:
        if not 0<=i<len(m.faces):p.error(f'face {i} outside model')
        vertices=[m.vertices[v] for v in m.faces[i]]
        points=[[c*(1<<m.scale_shift)*a.world_scale/4096 for c in (v.x,v.y,v.z)] for v in vertices]
        result.append({'face':i,'indices':m.faces[i], 'provenance':m.face_provenance[i],
                       'points':points,'uv':m.face_uvs[i],
                       'bounds':[[min(v[j] for v in points),max(v[j] for v in points)] for j in range(3)]})
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
