#!/usr/bin/env python3
"""Resolve a diagnostic RGB555 face-ID capture to source face metadata."""
import argparse
import json
from collections import Counter
from pathlib import Path
from PIL import Image


def face_id(rgb, count):
    r,g,b=(v >> 3 for v in rgb[:3])
    encoded=r|(g<<5)|(b<<10)
    # 109 is odd and thus invertible modulo 2^15.
    index=(encoded*pow(109,-1,1<<15))%(1<<15)-1
    return index if 0<=index<count else None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture',type=Path)
    p.add_argument('provenance',type=Path)
    p.add_argument('--point',action='append',default=[],metavar='X,Y')
    p.add_argument('--region',metavar='X,Y,WIDTH,HEIGHT')
    p.add_argument('--reference',type=Path,help='Matching textured capture for pixel filtering')
    p.add_argument('--min-rgb',type=int,default=0,help='Only count reference pixels with all channels at least this value')
    p.add_argument('--reference-rgb',metavar='R,G,B',help='Only count pixels near this reference color')
    p.add_argument('--rgb-tolerance',type=int,default=8,help='Per-channel tolerance for --reference-rgb')
    p.add_argument('--origins',type=Path,help='Optional split-face to source-face JSON array')
    a=p.parse_args()
    faces=json.loads(a.provenance.read_text());im=Image.open(a.capture).convert('RGB')
    origins=json.loads(a.origins.read_text()) if a.origins else None
    count=len(origins) if origins is not None else len(faces)
    ref=Image.open(a.reference).convert('RGB') if a.reference else None
    if ref and ref.size!=im.size:p.error('reference and ID capture dimensions must match')
    if not 0<=a.min_rgb<=255:p.error('--min-rgb must be 0..255')
    if a.reference_rgb:
        try: target=tuple(map(int,a.reference_rgb.split(',')))
        except ValueError:p.error('--reference-rgb must be R,G,B')
        if len(target)!=3 or any(not 0<=v<=255 for v in target):p.error('--reference-rgb must be R,G,B in 0..255')
        if ref is None:p.error('--reference-rgb requires --reference')
    else: target=None
    if not 0<=a.rgb_tolerance<=255:p.error('--rgb-tolerance must be 0..255')
    def selected(x,y):
        if ref is None:return True
        pixel=ref.getpixel((x,y))
        return min(pixel)>=a.min_rgb and (target is None or all(abs(c-t)<=a.rgb_tolerance for c,t in zip(pixel,target)))
    def describe(i):
        return {'render_face':i,'source':faces[origins[i] if origins is not None else i]}
    if not a.point and not a.region:p.error('provide --point and/or --region')
    for point in a.point:
        x,y=map(int,point.split(','));rgb=im.getpixel((x,y));idx=face_id(rgb,count)
        print(json.dumps({'x':x,'y':y,'rgb':rgb,'face':None if idx is None else describe(idx)}))
    if a.region:
        x,y,w,h=map(int,a.region.split(','))
        if w<=0 or h<=0 or x<0 or y<0 or x+w>im.width or y+h>im.height:
            p.error('region must fit within the image')
        counts=Counter(face_id(im.getpixel((px,py)),count) for py in range(y,y+h) for px in range(x,x+w)
                       if selected(px,py))
        print(json.dumps([{'face':describe(i),'pixels':n} for i,n in counts.most_common() if i is not None],indent=2))

if __name__=='__main__': main()
