#!/usr/bin/env python3
"""Check real Ymir High WRAM telemetry using symbols from the matching ELF."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

FIELDS='magic frames ticks jumps landings wall_hits resets x y z velocity_y camera_x camera_y camera_z target_x target_y target_z grounded clip commands skipped faces paused culled clipped fallback sky_clip_candidates castle_clip_candidates body_clip_candidates head_clip_candidates texture_arena_initial texture_arena_remaining texture_estimate health max_health dead coins star_bits boss_hp boss_state boss_held boss_x boss_y boss_z requested_yaw actual_camera_yaw camera_clearance mario_facing camera_fov_y'.split()


def check(elf, wram, nm, scenario):
    symbols={}
    for line in subprocess.check_output([str(nm),'-n',str(elf)],text=True).splitlines():
        words=line.split()
        if len(words)==3:
            symbols[words[2].lstrip('_')]=int(words[0],16)
    data=wram.read_bytes()
    if len(data)!=1024*1024: raise ValueError('expected a complete High WRAM dump')
    offset=symbols['g_sm64ds_castle_stats']-0x06000000
    # The header must have been extended in lockstep with the C struct; a
    # stale field list silently shifts every later value.
    assert len(FIELDS)==len(set(FIELDS)), 'duplicate telemetry field'
    assert len(FIELDS)==49, "telemetry field count is %d, expected 49" % len(FIELDS)
    # SH-2 is big-endian and the struct is uint32_t/int32_t only.
    report=dict(zip(FIELDS,struct.unpack_from(f'>{len(FIELDS)}I',data,offset)))
    for name in ('x','y','z','velocity_y','camera_x','camera_y','camera_z',
                 'target_x','target_y','target_z','mario_facing','camera_fov_y',
                 'camera_clearance','boss_x','boss_y','boss_z'):
        v=report[name]
        report[name]=v-2**32 if v>=2**31 else v   # signed 16.16 in the raw view
        report[name+'_units']=report[name]/65536
    panic=struct.unpack_from('>I',data,symbols['g_sat_last_panic']-0x06000000)[0]
    assert report['magic']==0x43415331 and report['frames']>0, 'no completed castle frame'
    assert panic!=0x50414e43, 'runtime panic recorded'
    assert report['skipped']==0, 'scene dropped faces'
    assert report['commands']>0 and report['ticks']>0, 'render/simulation did not advance'
    if scenario=='controls':
        assert report['jumps']>=1 and report['landings']>=2, 'jump/landing route failed'
        assert report['resets']>=2 and report['grounded']==1, 'reset did not return to ground'
        assert report['x']==0 and report['z']==256*65536, 'reset missed spawn'
        assert report['paused']==0, 'resume failed'
    if scenario=='wall':
        assert report['wall_hits']>0 and report['grounded']==1, 'wall contact route failed'
    # Add a second, script-friendly view without losing the raw 16.16 values.
    for name in ('x','y','z','velocity_y','camera_x','camera_y','camera_z',
                 'target_x','target_y','target_z','mario_facing','camera_fov_y',
                 'camera_clearance'):
        report[name+'_units']=report[name]/65536
    report.update(scenario=scenario,panic=False)
    # Endianness guard: SH-2 words are big-endian, so reading with '<' would
    # swap every field (magic 0x53414350 read as 0x50434153) and give
    # nonsense positions instead of failing loudly.
    assert report['magic']==0x43415331, 'telemetry read with the wrong endianness'
    return report


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,default=root/'build/castle/sm64ds_castle.elf')
    p.add_argument('--wram',type=Path,required=True)
    p.add_argument('--nm',type=Path,default=root.parent/'saturn-tools/bin/sh2eb-elf-nm')
    p.add_argument('--scenario',choices=('boot','controls','wall'),default='boot')
    a=p.parse_args()
    print(json.dumps(check(a.elf,a.wram,a.nm,a.scenario),indent=2))
