#!/usr/bin/env python3
"""Build and replay control and wall routes with live animation and support ordering."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from check_castle_capture import check
from inspect_support_capture import inspect, symbols

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (('controls', 'castle_route.pad', 790), ('wall', 'castle_camera_wall.pad', 940))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bios', required=True, type=Path)
    p.add_argument('--generated-dir', type=Path, default=ROOT/'private/castle-support-auto')
    p.add_argument('--build-dir', type=Path, default=ROOT/'build/castle-support-routes')
    p.add_argument('--output-dir', type=Path, default=ROOT/'private/castle-support-auto/live-routes')
    p.add_argument('--probe', type=Path, default=ROOT.parent/'lib-saturn/harness/build-macos/probe')
    p.add_argument('--nm', type=Path, default=ROOT.parent/'saturn-tools/bin/sh2eb-elf-nm')
    p.add_argument('--ground-pose', action='store_true')
    p.add_argument('--sloped-support', action='store_true')
    p.add_argument('--screenshot-step', type=int, default=100,
                   help='emulated fields between screenshots; 0 disables intermediate images')
    args = p.parse_args()
    if args.screenshot_step < 0:
        p.error('--screenshot-step must be nonnegative')
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    def run(command):
        print('+', ' '.join(map(str, command)), flush=True)
        subprocess.run([str(x) for x in command], cwd=ROOT, check=True)

    run(['cmake', '-S', ROOT, '-B', args.build_dir, '-DCMAKE_BUILD_TYPE=Release',
         f'-DCMAKE_TOOLCHAIN_FILE={ROOT.parent}/lib-saturn/cmake/toolchains/sh2eb-elf.cmake',
         f'-DCMAKE_PREFIX_PATH={ROOT.parent}/saturn-prefix-gc',
         f'-DSM64DS_GENERATED_DIR={args.generated_dir.resolve()}',
         '-DSM64DS_BUILD_CASTLE=ON', '-DSM64DS_VISUAL_DIAGNOSTICS=ON',
         '-DSM64DS_DIAG_FIXED_CAMERA=OFF', '-DSM64DS_DIAG_ABSOLUTE_CAMERA=OFF',
         '-DSM64DS_DIAG_ORBIT_PLAYER=OFF', '-DSM64DS_DIAG_OVERRIDE_PLAYER_Y=OFF',
         '-DSM64DS_DIAG_LIVE_ANIMATION=ON',
         f'-DSM64DS_DIAG_GROUND_POSE={"ON" if args.ground_pose else "OFF"}',
         '-DSM64DS_DIAG_WALL_FIXTURE=OFF', '-DSM64DS_DIAG_WALL_PARTIAL=OFF',
         '-DSM64DS_DIAG_FACE_IDS=OFF', '-DSM64DS_DIAG_CASTLE_FACE_IDS=OFF',
         '-DSM64DS_DIAG_NO_CULL=OFF', '-DSM64DS_DIAG_SOLID=OFF',
         '-DSM64DS_DIAG_CASTLE_FALLBACK_COLOR=OFF', '-DSM64DS_DIAG_OBJECTS=15',
         '-DSM64DS_DIAG_SUPPORT_DEPTH=ON', '-DSM64DS_DIAG_SUPPORT_AUTO=ON',
         '-DSM64DS_DIAG_SUPPORT_GUARD=ON', '-DSM64DS_DIAG_GEOMETRIC_DEPTH=OFF',
         f'-DSM64DS_DIAG_SLOPED_SUPPORT={"ON" if args.sloped_support else "OFF"}',
         '-DSM64DS_DIAG_PAIR_DEPTH=OFF'])
    run(['cmake', '--build', args.build_dir, '--target', 'sm64ds_castle_disc', '--parallel', '4'])
    elf = out/'sm64ds_castle.elf'
    shutil.copy2(args.build_dir/'sm64ds_castle.elf', elf)
    syms = symbols(args.nm, elf)
    reports = {}
    for name, pad, frames in ROUTES:
        wram = out/f'{name}-wram.bin'
        misaligned = out/f'{name}-misaligned.txt'
        command = [args.probe, '--iso', args.build_dir/'disc/sm64ds_castle.cue',
                   '--bin', args.build_dir/'sm64ds_castle.app.bin', '--bios', args.bios,
                   '--boot-mode', 'injection', '--frames', frames,
                   '--pad-script', ROOT/'tests'/pad, '--out', out/f'{name}-probe.json',
                   '--dump-wram-high', wram, '--misaligned-report', misaligned]
        shots = set(range(args.screenshot_step, frames, args.screenshot_step)) if args.screenshot_step else set()
        shots.add(frames-1)
        for frame in sorted(shots):
            command += ['--screenshot', f'{frame}:{out}/{name}-{frame}.png']
        run(command)
        if not re.search(r'totals: master 0, slave 0\)', misaligned.read_text()):
            raise RuntimeError(f'{name}: misaligned access or unrecognized probe report')
        telemetry = check(elf, wram, args.nm, name)
        support = inspect(wram.read_bytes(), syms)
        if support['counters']['map_failed']:
            raise RuntimeError(f'{name}: support mapping failed')
        reports[name] = {'telemetry': telemetry, 'support': support}
        (out/'results.json').write_text(json.dumps(reports, indent=2)+'\n')
    print(out/'results.json')


if __name__ == '__main__':
    main()
