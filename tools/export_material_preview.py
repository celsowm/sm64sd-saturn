#!/usr/bin/env python3
"""Export a local BMD source texture and its face bakes for visual debugging."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.textures import bake_face


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--model',required=True)
    p.add_argument('--material',type=int,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--size',type=int,default=16);p.add_argument('--limit',type=int,default=120)
    a=p.parse_args();model=convert_bmd(Filesystem.from_file(a.rom).read(a.model))
    if not 0<=a.material<len(model.material_textures):p.error('material outside model')
    tex=model.material_textures[a.material]
    if tex is None:p.error('material has no texture')
    a.out.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGBA',(tex.width,tex.height));image.putdata(tex.pixels)
    image.save(a.out/'source.png')
    indices=[i for i,m in enumerate(model.face_materials) if m==a.material][:a.limit]
    scale=3; pitch=a.size*scale+4; label=12; cols=8
    sheet=Image.new('RGB',(cols*pitch,((len(indices)+cols-1)//cols)*(pitch+label)),(40,40,40));draw=ImageDraw.Draw(sheet)
    for n,i in enumerate(indices):
        tile=bake_face(tex,model.face_uvs[i],a.size)
        pic=Image.new('RGBA',(a.size,a.size));pic.putdata(tile.rgba)
        x=(n%cols)*pitch;y=(n//cols)*(pitch+label)
        sheet.paste(pic.resize((a.size*scale,a.size*scale),Image.Resampling.NEAREST),(x,y),pic.resize((a.size*scale,a.size*scale),Image.Resampling.NEAREST))
        draw.text((x,y+pitch),str(i),fill='white')
    sheet.save(a.out/'faces.png')
    (a.out/'metadata.json').write_text(json.dumps({'model':a.model,'material':a.material,'width':tex.width,'height':tex.height,
        'repeat_s':tex.repeat_s,'repeat_t':tex.repeat_t,'flip_s':tex.flip_s,'flip_t':tex.flip_t,'face_ids':indices},indent=2)+'\n')

if __name__=='__main__':main()
