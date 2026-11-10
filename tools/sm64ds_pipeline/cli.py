"""CLI orchestration; format parsers remain independent."""
from __future__ import annotations
import argparse
from pathlib import Path
import json
from .common import FormatError
from .filesystem import Filesystem
from .bmd import convert_bmd
from .bca import Animation
from .emit import emit_model

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True,help='Local USA Rev0 .nds image')
    parser.add_argument('--model',default='ARCHIVE/arc0.narc:131',help='NitroFS path or NARC:index')
    parser.add_argument('--clip',action='append',default=[],help='name=NitroFS/path.bca (repeat)')
    parser.add_argument('--out',type=Path,required=True,help='Private generated-output directory')
    parser.add_argument('--name',default='mario_preview')
    parser.add_argument('--rate-num',type=int,default=30,help='Explicit nominal clip-rate numerator')
    parser.add_argument('--rate-den',type=int,default=1,help='Clip-rate denominator')
    parser.add_argument('--untextured',action='store_true',help='Emit rig-only geometry')
    parser.add_argument('--tile-size',type=int,default=16,choices=[8,16,24,32,48,64],help='Baked VDP1 face texture width/height')
    parser.add_argument('--vram-texture-budget',type=int,default=262144,help='Max bytes for baked VDP1 pixels')
    a=parser.parse_args(argv)
    fs=Filesystem.from_file(a.rom)
    model=convert_bmd(fs.read(a.model))
    clips=a.clip or ['idle=data/player/su_wait.bca','walk=data/player/su_walk.bca',
                     'run=data/player/su_run.bca','jump=data/player/su_jump.bca']
    named=[]
    for item in clips:
        key,sep,path=item.partition('=')
        if not sep:
            parser.error('clip must be name=nitrofs/path')
        named.append((key,Animation(fs.read(path),len(model.bones))))
    header,source,report=emit_model(model,named,a.name,a.rate_num,a.rate_den,
        textured=not a.untextured,tile_size=a.tile_size,texture_budget=a.vram_texture_budget)
    report.update(rom_sha256=fs.sha256, model=a.model, source_clips={x.split("=",1)[0]:x.split("=",1)[1] for x in clips})
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/f'{a.name}.h').write_text(header,encoding='utf8')
    (a.out/f'{a.name}.c').write_text(source,encoding='utf8')
    (a.out/f'{a.name}.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(report,indent=2))


