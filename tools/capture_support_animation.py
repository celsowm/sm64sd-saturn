#!/usr/bin/env python3
"""Capture matched frozen animation poses for support-occlusion analysis.

The actor-only, baseline and candidate images use identical camera and pose
settings. Face overlap is an observation: foreground scenery can legitimately
cover the actor. Generated images and ROM-derived assets stay in private/.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image
from measure_castle_occlusion import measure
from check_castle_capture import check
from check_support_capture import compare
from inspect_face_capture import face_id

ROOT = Path(__file__).resolve().parents[1]
POSES = ((0, 0), (0, 45), (1, 0), (1, 15), (2, 0), (2, 15), (3, 0), (3, 6))
MATCHED_STATE = ('x', 'y', 'z', 'camera_x', 'camera_y', 'camera_z',
                 'target_x', 'target_y', 'target_z', 'mario_facing',
                 'camera_fov_y', 'clip', 'grounded')


def check_matched_state(reference, candidate, name):
    differences = [key for key in MATCHED_STATE if reference[key] != candidate[key]]
    if differences:
        raise RuntimeError(f'{name}: capture state differs: {", ".join(differences)}')


def command(args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def outside_changes(actor, base, candidate, origins):
    """Classify changes outside the actor mask by original face IDs."""
    counts = Counter()
    aa, bb, cc = (image.convert('RGB').tobytes() for image in (actor, base, candidate))
    for offset in range(0, len(aa), 3):
        a, b, c = (tuple(data[offset:offset+3]) for data in (aa, bb, cc))
        if a != (96, 160, 240) or b == c:
            continue
        bi, ci = face_id(b, len(origins)), face_id(c, len(origins))
        bs = origins[bi] if bi is not None else None
        cs = origins[ci] if ci is not None else None
        counts[f'{bs}->{cs}'] += 1
    return dict(sorted(counts.items()))


def textured_changes(actor, base, candidate):
    aa, bb, cc = (image.convert('RGB').tobytes() for image in (actor, base, candidate))
    count = greatest = 0
    for offset in range(0, len(aa), 3):
        if aa[offset:offset+3] != bytes((96, 160, 240)):
            continue
        b, c = bb[offset:offset+3], cc[offset:offset+3]
        if b != c:
            count += 1
            greatest = max(greatest, *(abs(x-y) for x, y in zip(b, c)))
    return {'outside_actor_pixels': count, 'max_channel_delta': greatest}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generated-dir', type=Path, default=ROOT/'private/castle-support-auto')
    p.add_argument('--build-dir', type=Path, default=ROOT/'build/castle-animation')
    p.add_argument('--output-dir', type=Path, default=ROOT/'private/castle-support-auto/animation')
    p.add_argument('--bios', type=Path, required=True)
    p.add_argument('--probe', type=Path, default=ROOT.parent/'lib-saturn/harness/build-macos/probe')
    p.add_argument('--nm', type=Path, default=ROOT.parent/'saturn-tools/bin/sh2eb-elf-nm')
    p.add_argument('--frames', type=int, default=400)
    p.add_argument('--ground-pose', action='store_true', help='test the grounded-pose adjustment')
    p.add_argument('--textured', action='store_true', help='measure textured differences instead of face IDs')
    p.add_argument('--depth-inputs', action='store_true',
                   help='also capture body-only and castle-only face IDs for depth analysis')
    p.add_argument('--sloped-support', action='store_true')
    p.add_argument('--source', type=int, default=477,
                   help='source face to report in progress output (default: 477)')
    p.add_argument('--wall-partial', action='store_true',
                   help='include the narrow foreground wall fixture')
    p.add_argument('--min-wall-on-actor', type=int, default=1,
                   help='minimum baseline wall coverage when using --wall-partial')
    p.add_argument('--player-y', type=int, help='override player height for a raised pose')
    p.add_argument('--x', type=float, default=-76.8)
    p.add_argument('--z', type=float, default=399.491875)
    p.add_argument('--target-y', type=float, default=26.57)
    p.add_argument('--camera-y', type=float, default=37.94)
    p.add_argument('--angles', type=int, nargs='+', default=[0, 180])
    p.add_argument('--poses', nargs='+', metavar='CLIP:FRAME',
                   help='restrict the matrix to selected frozen poses')
    args = p.parse_args()
    if args.min_wall_on_actor < 0:
        p.error('--min-wall-on-actor must be nonnegative')
    if args.wall_partial and args.textured:
        p.error('--wall-partial requires face-ID captures')
    try:
        poses = [tuple(map(int, pose.split(':'))) for pose in args.poses] if args.poses else POSES
        if any(len(pose) != 2 for pose in poses):
            raise ValueError
    except ValueError:
        p.error('--poses entries must be CLIP:FRAME')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    origins = json.loads((args.generated_dir/'castle_split_origins.json').read_text())
    common = ['cmake', '-S', ROOT, '-B', args.build_dir,
              '-DCMAKE_BUILD_TYPE=Release',
              f'-DCMAKE_TOOLCHAIN_FILE={ROOT.parent}/lib-saturn/cmake/toolchains/sh2eb-elf.cmake',
              f'-DCMAKE_PREFIX_PATH={ROOT.parent}/saturn-prefix',
              f'-DSM64DS_GENERATED_DIR={args.generated_dir.resolve()}',
              '-DSM64DS_BUILD_CASTLE=ON', '-DSM64DS_VISUAL_DIAGNOSTICS=ON',
              '-DSM64DS_DIAG_FIXED_CAMERA=ON', '-DSM64DS_DIAG_ABSOLUTE_CAMERA=ON',
              '-DSM64DS_DIAG_ORBIT_PLAYER=OFF', '-DSM64DS_DIAG_LIVE_ANIMATION=OFF',
              f'-DSM64DS_DIAG_GROUND_POSE={"ON" if args.ground_pose else "OFF"}',
              f'-DSM64DS_DIAG_OVERRIDE_PLAYER_Y={"ON" if args.player_y is not None else "OFF"}',
              f'-DSM64DS_DIAG_PLAYER_Y={args.player_y if args.player_y is not None else 0}',
              f'-DSM64DS_DIAG_WALL_FIXTURE={"ON" if args.wall_partial else "OFF"}',
              f'-DSM64DS_DIAG_WALL_PARTIAL={"ON" if args.wall_partial else "OFF"}', '-DSM64DS_DIAG_DS_ASPECT=ON',
              '-DSM64DS_DIAG_SHOW_UI=OFF', '-DSM64DS_DIAG_NO_CULL=OFF',
              '-DSM64DS_DIAG_SOLID=OFF', '-DSM64DS_DIAG_FACE_IDS=OFF',
              f'-DSM64DS_DIAG_CASTLE_FACE_IDS={"OFF" if args.textured else "ON"}',
              '-DSM64DS_DIAG_CASTLE_FALLBACK_COLOR=OFF',
              '-DSM64DS_DIAG_GEOMETRIC_DEPTH=OFF', '-DSM64DS_DIAG_PAIR_DEPTH=OFF',
              '-DSM64DS_DIAG_SUPPORT_GUARD=ON', '-DSM64DS_DIAG_FAR_DEPTH_FIRST=0',
              f'-DSM64DS_DIAG_SLOPED_SUPPORT={"ON" if args.sloped_support else "OFF"}',
              '-DSM64DS_DIAG_FACING=180', '-DSM64DS_DIAG_FLOOR_CEILING=80',
              '-DSM64DS_DIAG_FOV_Y=46', f'-DSM64DS_DIAG_X={args.x}',
              f'-DSM64DS_DIAG_Z={args.z}']
    results = []
    for angle in args.angles:
        radians = math.radians(angle)
        eye = (args.x+53*math.sin(radians), args.camera_y, args.z+53*math.cos(radians))
        camera = [f'-DSM64DS_DIAG_{key}={value}' for key, value in zip(
            ('CAMERA_X', 'CAMERA_Y', 'CAMERA_Z', 'TARGET_X', 'TARGET_Y', 'TARGET_Z'),
            (*eye, args.x, args.target_y, args.z))]
        for clip, frame in poses:
            stem = f'a{angle}-c{clip}-f{frame}'
            captures = {}
            reference = None
            for mode, mask, enabled in (('actor', 12, False), ('base', 15, False), ('auto', 15, True)):
                name = f'{stem}-{mode}'
                flags = [f'-DSM64DS_DIAG_CLIP={clip}', f'-DSM64DS_DIAG_FRAME={frame}',
                         f'-DSM64DS_DIAG_OBJECTS={mask}',
                         f'-DSM64DS_DIAG_FAR_DEPTH_COUNT={len(origins) if enabled else 0}',
                         f'-DSM64DS_DIAG_SUPPORT_DEPTH={"ON" if enabled else "OFF"}',
                         f'-DSM64DS_DIAG_SUPPORT_AUTO={"ON" if enabled else "OFF"}']
                command(common+camera+flags)
                command(['cmake', '--build', args.build_dir, '--target', 'sm64ds_castle_disc', '--parallel', '4'])
                command([args.probe, '--iso', args.build_dir/'disc/sm64ds_castle.cue',
                         '--bin', args.build_dir/'sm64ds_castle.app.bin', '--bios', args.bios,
                         '--boot-mode', 'injection', '--frames', args.frames,
                         '--screenshot', f'{args.frames-1}:{out/name}.png',
                         '--dump-wram-high', out/f'{name}-wram.bin',
                         '--misaligned-report', out/f'{name}-misaligned.json'])
                report = check(args.build_dir/'sm64ds_castle.elf', out/f'{name}-wram.bin', args.nm, 'boot')
                if reference is None:
                    reference = report
                else:
                    check_matched_state(reference, report, name)
                if report['skipped']:
                    raise RuntimeError(f'{name}: skipped commands')
                misaligned = (out/f'{name}-misaligned.json').read_text()
                if not re.search(r'totals: master 0, slave 0\)', misaligned):
                    raise RuntimeError(f'{name}: misaligned access or unrecognized probe report')
                (out/f'{name}-telemetry.json').write_text(json.dumps(report, indent=2)+'\n')
                if enabled:
                    shutil.copy2(args.build_dir/'sm64ds_castle.elf', out/f'{name}.elf')
                captures[mode] = out/f'{name}.png'
            if args.depth_inputs:
                for mode, mask, body_ids, castle_ids in (('body-depth', 4, 'ON', 'OFF'),
                                                          ('castle-depth', 2, 'OFF', 'ON')):
                    name = f'{stem}-{mode}'
                    flags = [f'-DSM64DS_DIAG_CLIP={clip}', f'-DSM64DS_DIAG_FRAME={frame}',
                             f'-DSM64DS_DIAG_OBJECTS={mask}', '-DSM64DS_DIAG_FAR_DEPTH_COUNT=0',
                             '-DSM64DS_DIAG_SUPPORT_DEPTH=OFF', '-DSM64DS_DIAG_SUPPORT_AUTO=OFF',
                             f'-DSM64DS_DIAG_FACE_IDS={body_ids}',
                             f'-DSM64DS_DIAG_CASTLE_FACE_IDS={castle_ids}']
                    command(common+camera+flags)
                    command(['cmake', '--build', args.build_dir, '--target', 'sm64ds_castle_disc', '--parallel', '4'])
                    command([args.probe, '--iso', args.build_dir/'disc/sm64ds_castle.cue',
                             '--bin', args.build_dir/'sm64ds_castle.app.bin', '--bios', args.bios,
                             '--boot-mode', 'injection', '--frames', args.frames,
                             '--screenshot', f'{args.frames-1}:{out/name}.png',
                             '--dump-wram-high', out/f'{name}-wram.bin',
                             '--misaligned-report', out/f'{name}-misaligned.json'])
                    report = check(args.build_dir/'sm64ds_castle.elf', out/f'{name}-wram.bin', args.nm, 'boot')
                    check_matched_state(reference, report, name)
                    if report['skipped'] or not re.search(r'totals: master 0, slave 0\)',
                                                           (out/f'{name}-misaligned.json').read_text()):
                        raise RuntimeError(f'{name}: skipped commands or misaligned access')
                    (out/f'{name}-telemetry.json').write_text(json.dumps(report, indent=2)+'\n')
                    shutil.copy2(args.build_dir/'sm64ds_castle.elf', out/f'{name}.elf')
            with Image.open(captures['actor']) as actor, Image.open(captures['base']) as base, Image.open(captures['auto']) as auto:
                if args.textured:
                    entry = {'angle': angle, 'clip': clip, 'frame': frame,
                             'textured_changes': textured_changes(actor, base, auto)}
                else:
                    before = measure(actor, base, origins, (96, 160, 240))
                    after = measure(actor, auto, origins, (96, 160, 240))
                    outside = outside_changes(actor, base, auto, origins)
                    entry = {'angle': angle, 'clip': clip, 'frame': frame, 'baseline': before,
                             'candidate': after, 'outside_actor_changes': outside}
                    if args.wall_partial:
                        entry['wall'] = compare(actor, base, auto, origins, 477,
                                                (96, 160, 240), (248, 0, 248))
                        if (entry['wall']['wall_on_actor_before'] < args.min_wall_on_actor or
                                entry['wall']['wall_pixels_lost']):
                            raise RuntimeError(f'{stem}: foreground wall coverage failed: {entry["wall"]}')
            results.append(entry)
            (out/'results.json').write_text(json.dumps(results, indent=2)+'\n')
            if args.textured:
                print(stem, entry['textured_changes'], flush=True)
            else:
                print(stem, f'source {args.source}:', before['overlap_by_source'].get(args.source, 0), '->',
                      after['overlap_by_source'].get(args.source, 0), flush=True)


if __name__ == '__main__':
    main()
