#!/usr/bin/env python3
"""Run castle pad routes in the probe and report the per-stage frame profile.

Reads g_sm64ds_castle_profile (FRT ticks per main-loop stage, summed over
completed draws) from a High WRAM dump, and summarizes --profile-pc samples
by ELF symbol. Emulator measurements, not a physical-hardware frame rate.
"""
import argparse
from collections import Counter
import bisect
import json
from pathlib import Path
import struct
import subprocess

STAGES = 'vblank sim skin camera begin sky castle props actor support flush hud end'.split()
HEADER = 'magic frequency_hz frames sim_steps max_sim_steps vdp1_draw_waits vdp1_draw_timeouts vdp1_late_swaps'.split()
ROUTES = {'controls': ('castle_route.pad', 790), 'orbit': ('castle_orbit.pad', 720),
          'bob_climb': ('bob_climb.pad', 950), 'bob_summit': ('bob_boss_fight.pad', 510),
          'bob_route': ('bob_route.pad', 840), 'bob_orbit': ('bob_orbit.pad', 720),
          'garden_walk': ('garden_walk.pad', 260), 'wf_walk': ('wf_walk.pad', 260),
          'jrb_walk': ('jrb_walk.pad', 260), 'jrb_orbit': ('jrb_orbit.pad', 720)}
ROOT = Path(__file__).resolve().parents[1]


def symbols(nm, elf):
    data, text = {}, []
    for line in subprocess.check_output([str(nm), '-n', '-S', str(elf)], text=True).splitlines():
        w = line.split()
        if len(w) == 3:
            data[w[2].lstrip('_')] = int(w[0], 16)
        elif len(w) == 4:
            data[w[3].lstrip('_')] = int(w[0], 16)
            if w[2].lower() == 't' and int(w[1], 16):
                text.append((int(w[0], 16), int(w[0], 16) + int(w[1], 16), w[3]))
    text.sort()
    return data, text


def read_profile(wram, address):
    count = len(HEADER) + 2 * len(STAGES)
    words = struct.unpack_from(f'>{count}I', wram, address - 0x06000000)
    head = dict(zip(HEADER, words))
    if head['magic'] != 0x50524f46 or not head['frames']:
        raise ValueError('no profiled castle frame in WRAM dump')
    sums = words[len(HEADER):len(HEADER) + len(STAGES)]
    maxes = words[len(HEADER) + len(STAGES):]
    return head, dict(zip(STAGES, sums)), dict(zip(STAGES, maxes))


def summarize(head, sums, maxes):
    hz, frames = head['frequency_hz'], head['frames']
    ms = lambda ticks: 1000.0 * ticks / hz
    total = sum(sums.values())
    stages = {name: {'avg_ms': round(ms(sums[name]) / frames, 2),
                     'max_ms': round(ms(maxes[name]), 2),
                     'share': round(sums[name] / total, 3) if total else 0.0}
              for name in STAGES}
    cpu = sum(sums[n] for n in STAGES if n not in ('vblank', 'end'))
    # Fields are 60 Hz NTSC; the route's boot/load fields precede the loop.
    return {'frames': frames,
            'fields_per_frame': round(ms(total) / frames * 60 / 1000, 2),
            'avg_frame_ms': round(ms(total) / frames, 2),
            'avg_cpu_work_ms': round(ms(cpu) / frames, 2),
            'avg_vdp1_wait_ms': stages['end']['avg_ms'],
            'avg_vblank_wait_ms': stages['vblank']['avg_ms'],
            'sim_steps_per_frame': round(head['sim_steps'] / frames, 2),
            'max_sim_steps': head['max_sim_steps'],
            'vdp1': {k: head[k] for k in ('vdp1_draw_waits', 'vdp1_draw_timeouts', 'vdp1_late_swaps')},
            'stages': stages}


def hot_symbols(samples, text, limit, skip):
    """One PC sample per field; `skip` drops boot and asset-loading fields."""
    starts = [row[0] for row in text]
    counts, total = Counter(), 0
    for line in samples.read_text().splitlines()[skip:]:
        try:
            pc = int(line.strip(), 16)
        except ValueError:
            continue
        total += 1
        i = bisect.bisect_right(starts, pc) - 1
        counts[text[i][2] if i >= 0 and pc < text[i][1] else f'?{pc:08x}'] += 1
    return [{'symbol': s, 'samples': n, 'share': round(n / total, 3)} for s, n in counts.most_common(limit)]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-dir', type=Path, default=ROOT / 'build/castle')
    p.add_argument('--out', type=Path, default=ROOT / 'private/frame-profile/baseline')
    p.add_argument('--routes', nargs='+', choices=sorted(ROUTES), default=sorted(ROUTES))
    p.add_argument('--probe', type=Path, default=ROOT.parent / 'lib-saturn/harness/build-macos/probe')
    p.add_argument('--bios', type=Path, default=ROOT.parent / 'lib-saturn/bios/firmware/mpr-17933.bin')
    p.add_argument('--nm', type=Path, default=ROOT.parent / 'saturn-tools/bin/sh2eb-elf-nm')
    p.add_argument('--target', default='sm64ds_castle', help='CMake target, e.g. sm64ds_bob')
    p.add_argument('--route-target', action='append', default=[],
                   help='Override the CMake target for a route (repeatable, NAME=TARGET)')
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--skip-fields', type=int, default=120, help='boot/load fields left out of hot symbols')
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    report = {}
    for name in a.routes:
        pad, fields = ROUTES[name]
        wram, pcs = a.out / f'{name}-wram.bin', a.out / f'{name}-pc.txt'
        target = a.target
        for override in a.route_target:
            key, _, value = override.partition('=')
            if key == name:
                target = value
        elf = a.build_dir / f'{target}.elf'
        cue = a.build_dir / f'disc/{target}.cue'
        if not cue.exists():
            cue = a.build_dir / f'disc/{target}_direct.cue'
        data, text = symbols(a.nm, elf)
        subprocess.run([str(x) for x in [
            a.probe, '--iso', cue,
            '--bin', a.build_dir / f'{target}.app.bin', '--bios', a.bios,
            '--boot-mode', 'injection', '--frames', fields,
            '--pad-script', ROOT / 'tests' / pad, '--out', a.out / f'{name}-probe.json',
            '--dump-wram-high', wram, '--profile-pc', pcs,
            '--screenshot', f'{fields - 1}:{a.out}/{name}-final.png']],
            check=True, capture_output=True)
        head, sums, maxes = read_profile(wram.read_bytes(), data['g_sm64ds_castle_profile'])
        report[name] = summarize(head, sums, maxes)
        report[name]['hot_symbols'] = hot_symbols(pcs, text, a.limit, a.skip_fields)
    (a.out / 'profile.json').write_text(json.dumps(report, indent=2) + '\n')
    for name, r in report.items():
        print(f"{name}: {r['frames']} draws, {r['avg_frame_ms']} ms/draw ({r['fields_per_frame']} fields), "
              f"CPU work {r['avg_cpu_work_ms']} ms, VDP1 wait {r['avg_vdp1_wait_ms']} ms, "
              f"{r['sim_steps_per_frame']} sim steps/draw")
        for stage, v in r['stages'].items():
            print(f"  {stage:8} {v['avg_ms']:7.2f} ms  {100 * v['share']:5.1f}%  max {v['max_ms']}")
        for h in r['hot_symbols'][:10]:
            print(f"  {100 * h['share']:5.1f}%  {h['symbol']}")
    print(f'full report: {a.out / "profile.json"}')


if __name__ == '__main__':
    main()
