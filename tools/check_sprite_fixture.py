#!/usr/bin/env python3
"""Measure triangle fixture UV error against affine screen-space interpolation."""
import argparse
import json
import math
from pathlib import Path
import sys
from PIL import Image


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture',type=Path)
    a=p.parse_args()
    im=Image.open(a.capture).convert('RGB')
    if im.size!=(320,224):p.error('expected a native 320x224 capture')
    pixels=im.load();total=exact=within_one=0;max_error=0
    worst=[]
    # Exclude polygon edges and texel boundaries, where VDP1 coverage and
    # 32x32 finite texture sampling necessarily differ from an ideal surface.
    for y in range(37,187):
        for x in range(45,227):
            u=8*(x-40)/192;v=8*(y-32)/160
            if u+v>=7.75 or min(u%1,v%1,1-u%1,1-v%1)<.2:continue
            expected=(math.floor(u),math.floor(v))
            rgb=pixels[x,y]
            actual=(round(rgb[0]/32),round(rgb[1]/32))
            error=max(abs(actual[i]-expected[i]) for i in range(2))
            total+=1;exact+=error==0;within_one+=error<=1;max_error=max(max_error,error)
            if error>1 and len(worst)<12:worst.append({'x':x,'y':y,'rgb':rgb,'expected':expected,'actual':actual})
    print(json.dumps({'samples':total,'exact':exact,'within_one':within_one,
                      'max_channel_error_in_source_texels':max_error,'examples':worst},indent=2))
    if total==0 or within_one!=total:sys.exit(1)


if __name__=='__main__':main()
