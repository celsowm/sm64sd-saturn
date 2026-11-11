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
from .skybox import emit_skybox
from .world_hlod import build_world_hlod, materials_manifest

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom',type=Path,required=True,help='Local USA Rev0 .nds image')
    parser.add_argument('--model',default='ARCHIVE/arc0.narc:131',help='NitroFS path or NARC:index')
    parser.add_argument('--clip',action='append',default=[],help='name=NitroFS/path.bca (repeat)')
    parser.add_argument('--out',type=Path,required=True,help='Private generated-output directory')
    parser.add_argument('--name',default='mario_preview')
    parser.add_argument('--kind',choices=['character','skybox','world-hlod'],default='character',
                        help='Character: BMD+BCA; skybox: static backdrop; world-hlod: LibSaturn WLH1 sector meshes.')
    parser.add_argument('--skybox-radius',type=int,default=128,
                        help='Target maximum absolute coordinate of camera-local skybox')
    parser.add_argument('--rate-num',type=int,default=30,help='Explicit nominal clip-rate numerator')
    parser.add_argument('--rate-den',type=int,default=1,help='Clip-rate denominator')
    parser.add_argument('--untextured',action='store_true',help='Emit rig-only geometry')
    parser.add_argument('--tile-size',type=int,default=16,choices=[8,16,24,32,48,64],help='Baked VDP1 face texture width/height')
    parser.add_argument('--vram-texture-budget',type=int,default=262144,help='Max bytes for baked VDP1 pixels')
    parser.add_argument('--libsaturn-source',type=Path,default=None,
                        help='Local LibSaturn checkout (required for world-hlod; no download)')
    parser.add_argument('--cell-size',type=float,default=8.0,
                        help='World-HLOD cell size in source game units')
    parser.add_argument('--lod-targets',default='160,64,24',
                        help='Maximum triangles per HLOD level in each cell, descending')
    parser.add_argument('--hlod-quality',choices=['conservative','balanced','aggressive'],
                        default='aggressive',help='LibSaturn simplifier quality/geometry constraints')
    a=parser.parse_args(argv)
    fs=Filesystem.from_file(a.rom)
    model=convert_bmd(fs.read(a.model))
    if a.kind=='world-hlod':
        if a.clip: raise FormatError('--clip is invalid for static world HLOD')
        if a.libsaturn_source is None:
            raise FormatError('world-hlod requires --libsaturn-source /path/to/libsaturn')
        try:
            targets=tuple(int(x) for x in a.lod_targets.split(','))
        except ValueError as exc:
            raise FormatError('--lod-targets must be comma-separated positive integers') from exc
        archive,report=build_world_hlod(model,a.libsaturn_source,
            cell_size=a.cell_size,lod_targets=targets,quality=a.hlod_quality)
        report.update(rom_sha256=fs.sha256,model=a.model,asset_kind='world-hlod')
        a.out.mkdir(parents=True,exist_ok=True)
        (a.out/f'{a.name}.wlh').write_bytes(archive)
        (a.out/f'{a.name}.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        (a.out/f'{a.name}.materials.json').write_text(
            json.dumps(materials_manifest(model),indent=2)+'\n',encoding='utf8')
        print(json.dumps({k:v for k,v in report.items() if k!='cells'},indent=2))
        return
    if a.kind=='skybox':
        if a.clip:raise FormatError('--clip is invalid for a static skybox')
        header,source,report=emit_skybox(
            model,a.name,target_radius=a.skybox_radius,
            textured=not a.untextured,tile_size=a.tile_size,
            texture_budget=a.vram_texture_budget)
        report.update(rom_sha256=fs.sha256,model=a.model)
        a.out.mkdir(parents=True,exist_ok=True)
        (a.out/f'{a.name}.h').write_text(header,encoding='utf8')
        (a.out/f'{a.name}.c').write_text(source,encoding='utf8')
        (a.out/f'{a.name}.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
        print(json.dumps(report,indent=2))
        return
    # Normal Mario locomotion lives beside his body/head in arc0. The
    # top-level su_* clips are a different animation set.
    clips=a.clip or ['idle=ARCHIVE/arc0.narc:179','walk=ARCHIVE/arc0.narc:180',
                     'run=ARCHIVE/arc0.narc:145','jump=ARCHIVE/arc0.narc:120']
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

