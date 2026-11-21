#!/usr/bin/env python3
"""Convert DS stages and write the all-stages report.

    prepare_stage.py --rom ROM --all --report private/stages/report.json
    prepare_stage.py --rom ROM --stage bombhei_map --report out.json
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sm64ds_pipeline.actors import actor_names, obj_to_actor_table
from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.kcl import decode_kcl
from sm64ds_pipeline.level import read_level
from sm64ds_pipeline.sky_panorama import emit_sky_panorama
from stage_table import BY_NAME, STAGES

# Object-list categories whose first field is an object ID.
OBJECT_CATEGORIES = (0, 1, 5)


def stage_report(fs, stage, obj_actor, names):
    base = f'data/stage/{stage.name}'
    out = {'stage': stage.name, 'bin': stage.bin, 'title': stage.title,
           'profile': stage.profile, 'enabled': stage.enabled}
    model = convert_bmd(fs.read(f'{base}/{stage.name}_all.bmd'))
    out['vertices'], out['faces'] = len(model.vertices), len(model.faces)
    out['bones'] = len(model.bones)
    stats = {}
    out['kcl_prisms'] = len(decode_kcl(fs.read_id(fs.by_name[f'{base}/{stage.name}.kcl']),
                                       stats=stats))
    out['kcl_degenerate'] = len(stats['degenerate'])
    lv = read_level(fs, stage.name)
    out['overlay'], out['areas'], out['sublevel'] = lv.overlay_id, lv.area_count, lv.sublevel
    out['skybox_id'] = lv.skybox_id
    if lv.skybox_id:
        # Sky table: id k -> data/vrbox/vr(k+1).bmd; bake it to prove it converts.
        path = f'data/vrbox/vr{lv.skybox_id + 1:02d}.bmd'
        if path in fs.by_name:
            _h, _c, sky = emit_sky_panorama(convert_bmd(fs.read(path)), 'sky_panorama')
            out['sky'] = {'model': path, 'report': sky}
        else:
            out['sky'] = {'model': None, 'note': f'{path} not in ROM; sky id unmapped'}
    actors = Counter()
    unknown = Counter()
    for lists in [lv.level_lists] + lv.area_lists:
        for lst in lists:
            if lst.category not in OBJECT_CATEGORIES:
                continue
            for rec in lst.records:
                oid = rec[0] & (0x1FF if lst.category == 5 else 0xFFFF)
                if oid < len(obj_actor):
                    actors[names.get(obj_actor[oid], f'actor{obj_actor[oid]}')] += 1
                else:
                    unknown[oid] += 1
    out['actors'] = dict(sorted(actors.items()))
    out['unknown_objects'] = dict(sorted(unknown.items()))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--stage', action='append', default=[])
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--report', type=Path)
    args = ap.parse_args(argv)
    if not args.all and not args.stage:
        ap.error('give --all or --stage')
    fs = Filesystem.from_file(args.rom)
    obj_actor, names = obj_to_actor_table(fs), actor_names()
    wanted = STAGES if args.all else [BY_NAME[n] for n in args.stage]
    rows = []
    for st in wanted:
        row = stage_report(fs, st, obj_actor, names)
        rows.append(row)
        print(f"{st.name:16} ov{row['overlay']:<3} areas={row['areas']} faces={row['faces']:<5} "
              f"prisms={row['kcl_prisms']:<5} actors={len(row['actors'])}")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(rows, indent=1) + '\n')


if __name__ == '__main__':
    main()
