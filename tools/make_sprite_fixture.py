#!/usr/bin/env python3
"""Generate a synthetic VDP1 triangle texture through the normal UV baker."""
import argparse
from pathlib import Path
from sm64ds_pipeline.textures import SourceTexture, bake_face, index_bakes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    # Distinct horizontal/vertical color channels make flipped or stretched
    # corners measurable. Source colors are independent of any ROM.
    source=SourceTexture(8,8,tuple((x*32,y*32,0,255) for y in range(8) for x in range(8)))
    baked=bake_face(source,((0,0),(8,0),(0,8),(0,8)),32)
    tiles,palette,_=index_bakes([baked])
    def values(data):return ','.join(str(x) for x in data)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text('#pragma once\n#include <stdint.h>\n'
        'static const uint8_t fixture_pixels[1024]={' + values(tiles[0].pixels) + '};\n'
        'static const uint16_t fixture_palette[256]={' + values(palette) + '};\n')


if __name__=='__main__':main()
