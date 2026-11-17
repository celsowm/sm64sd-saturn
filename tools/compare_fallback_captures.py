#!/usr/bin/env python3
"""Measure highlighted flat-fallback coverage in matching RGB captures."""
import argparse
import json
from pathlib import Path
from PIL import Image


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images',nargs='+',type=Path)
    parser.add_argument('--region',default='0,0,320,224',help='X,Y,WIDTH,HEIGHT')
    parser.add_argument('--color',default='255,0,255',help='R,G,B')
    parser.add_argument('--tolerance',type=int,default=8)
    args=parser.parse_args()
    try:
        x,y,w,h=map(int,args.region.split(','));color=tuple(map(int,args.color.split(',')))
    except ValueError:parser.error('invalid region or color')
    if len(color)!=3 or any(not 0<=v<=255 for v in color) or not 0<=args.tolerance<=255:
        parser.error('color and tolerance must be in 0..255')
    result=[]
    for path in args.images:
        im=Image.open(path).convert('RGB')
        if x<0 or y<0 or w<=0 or h<=0 or x+w>im.width or y+h>im.height:
            parser.error(f'region does not fit {path}')
        pixels=im.load()
        count=sum(all(abs(c-t)<=args.tolerance for c,t in zip(pixels[px,py],color))
                  for py in range(y,y+h) for px in range(x,x+w))
        result.append({'image':str(path),'pixels':count,'region_pixels':w*h,'fraction':count/(w*h)})
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
