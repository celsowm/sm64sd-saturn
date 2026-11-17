#!/usr/bin/env python3
"""Count diagnostic face-ID pixels across comparable isolated captures."""
import argparse
import json
from pathlib import Path
from PIL import Image
from inspect_face_capture import face_id


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--face-count',type=int,required=True)
    p.add_argument('--region',default='0,20,320,185',help='X,Y,WIDTH,HEIGHT')
    p.add_argument('captures',nargs='+',type=Path)
    a=p.parse_args()
    if a.face_count<=0:p.error('face count must be positive')
    try:x,y,w,h=map(int,a.region.split(','))
    except ValueError:p.error('region must be X,Y,WIDTH,HEIGHT')
    counts=[0]*a.face_count
    for path in a.captures:
        im=Image.open(path).convert('RGB')
        if x<0 or y<0 or w<=0 or h<=0 or x+w>im.width or y+h>im.height:p.error(f'region outside {path}')
        pixels=im.load()
        for py in range(y,y+h):
            for px in range(x,x+w):
                color=pixels[px,py]
                if color in ((0,0,0),(255,255,255)):continue
                face=face_id(color,a.face_count)
                if face is not None:counts[face]+=1
    print(json.dumps(counts))


if __name__=='__main__':main()
