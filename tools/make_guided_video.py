#!/usr/bin/env python3
"""Render a guided, uncut playthrough video: title screen to King Bob-omb's star.

One deterministic probe run boots the intro on the unified castle disc and
follows a pad script (tests/guided_route.pad) through the whole chain:

    intro -> Castle Grounds -> Castle 1F -> Bob-omb Battlefield painting ->
    the mountain climb -> King Bob-omb -> Power Star

Nothing is skipped: the intro, the Lakitu fly-in, every stage load and the
whole climb are in the video. The script refuses to write the video unless
the final High WRAM telemetry shows the boss defeated and star 1 collected.

The route file is a normal probe pad script. Lines starting with `#@` are
chapter captions drawn over the video:

    #@ 400 Title screen: press START
    #@end 9000                     (last field to record)

Usage:
    tools/make_guided_video.py                    # private/guided/*.mp4
    tools/make_guided_video.py --fps 30 --scale 3 --out my.mp4
    tools/make_guided_video.py --verify-only      # run, check the win, no video
"""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from check_castle_capture import check  # noqa: E402

AUDIO_RATE = 44100   # probe --dump-audio: signed 16-bit little-endian stereo
FIELD_HZ = 60.0


def read_route(path):
    """Return (pad_text, chapters[(field, text)], end_field)."""
    chapters, end, pad = [], None, []
    for line in path.read_text().splitlines():
        m = re.match(r'#@end\s+(\d+)\s*$', line)
        if m:
            end = int(m.group(1))
            continue
        m = re.match(r'#@\s+(\d+)\s+(.+?)\s*$', line)
        if m:
            chapters.append((int(m.group(1)), m.group(2)))
            continue
        pad.append(line)
    if end is None:
        raise SystemExit(f'{path}: missing "#@end <field>" line')
    chapters.sort()
    return '\n'.join(pad) + '\n', chapters, end


def run_probe(a, work, pad_text, end):
    work.mkdir(parents=True, exist_ok=True)
    frames = work / 'frames'
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    (work / 'route.pad').write_text(pad_text)
    step = max(1, round(FIELD_HZ / a.fps))
    shots = [f'{f}:frames/{f:06d}.png' for f in range(0, end, step)] if not a.verify_only else []
    cmd = [a.probe, '--iso', a.build_dir / 'disc/sm64ds_castle.cue',
           '--bin', a.build_dir / 'sm64ds_intro.app.bin', '--bios', a.bios,
           '--boot-mode', 'injection', '--frames', end,
           '--pad-script', 'route.pad', '--out', 'probe.json',
           '--dump-wram-high', 'wram.bin']
    if not a.verify_only:
        cmd += ['--dump-audio', 'audio.raw']
    for s in shots:
        cmd += ['--screenshot', s]
    print(f'probe: {end} fields, {len(shots)} frames ...', flush=True)
    subprocess.run([str(x) for x in cmd], cwd=work, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return step


def verify(a, work):
    elf = a.build_dir / 'sm64ds_bob.elf'
    rep = check(elf, work / 'wram.bin', a.nm, 'summit')   # asserts boss_hp==0 and star 1
    print(f"verified: boss_hp={rep['boss_hp']} star_bits={rep['star_bits']} "
          f"health={rep['health']}/{rep['max_health']} at ({rep['x_units']:.0f},"
          f"{rep['y_units']:.0f},{rep['z_units']:.0f})")
    return rep


def caption_for(chapters, field):
    text = ''
    for start, t in chapters:
        if start <= field:
            text = t
    return text


def compose(a, work, chapters, end, step):
    from PIL import Image, ImageDraw, ImageFont
    out_w, out_h = 320 * a.scale, 224 * a.scale
    bar = 22 * a.scale // 2
    font = ImageFont.load_default(size=7 * a.scale)
    audio = work / 'audio.raw'
    a.out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ['ffmpeg', '-loglevel', 'error', '-y',
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{out_w}x{out_h}',
           '-framerate', str(a.fps), '-i', '-']
    if audio.exists():
        cmd += ['-f', 's16le', '-ar', str(AUDIO_RATE), '-ac', '2', '-i', str(audio)]
    cmd += ['-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p']
    if audio.exists():
        cmd += ['-c:a', 'aac', '-b:a', '160k', '-shortest']
    cmd += [str(a.out)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    last = None
    for f in range(0, end, step):
        png = work / 'frames' / f'{f:06d}.png'
        if png.exists():
            last = Image.open(png).convert('RGB').resize((out_w, out_h), Image.NEAREST)
        if last is None:
            continue
        im = last.copy()
        text = caption_for(chapters, f)
        if text:
            d = ImageDraw.Draw(im, 'RGBA')
            d.rectangle((0, out_h - bar, out_w, out_h), fill=(0, 0, 0, 170))
            d.text((out_w // 2, out_h - bar // 2), text, font=font, fill=(255, 255, 255),
                   anchor='mm')
        enc.stdin.write(im.tobytes())
    enc.stdin.close()
    if enc.wait():
        raise SystemExit('ffmpeg failed')
    print(f'wrote {a.out}')


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--route', type=Path, default=ROOT / 'tests/guided_route.pad')
    p.add_argument('--build-dir', type=Path, default=ROOT / 'build/castle')
    p.add_argument('--work', type=Path, default=ROOT / 'private/guided/work')
    p.add_argument('--out', type=Path, default=ROOT / 'private/guided/sm64ds_bob_omb_guided.mp4')
    p.add_argument('--probe', type=Path, default=ROOT.parent / 'lib-saturn/harness/build-macos/probe')
    p.add_argument('--bios', type=Path, default=ROOT.parent / 'lib-saturn/bios/firmware/mpr-17933.bin')
    p.add_argument('--nm', type=Path, default=ROOT.parent / 'saturn-tools/bin/sh2eb-elf-nm')
    p.add_argument('--fps', type=int, default=30, choices=(15, 20, 30, 60))
    p.add_argument('--scale', type=int, default=3, help='integer upscale of the 320x224 frames')
    p.add_argument('--verify-only', action='store_true',
                   help='run the route and check the boss defeat; write no video')
    a = p.parse_args()
    for need in (a.probe, a.bios, a.route, a.build_dir / 'disc/sm64ds_castle.cue',
                 a.build_dir / 'sm64ds_intro.app.bin', a.build_dir / 'sm64ds_bob.elf'):
        if not Path(need).exists():
            raise SystemExit(f'missing {need} (run ./build-castle.sh first)')
    if not shutil.which('ffmpeg') and not a.verify_only:
        raise SystemExit('ffmpeg is not on PATH')
    pad_text, chapters, end = read_route(a.route)
    step = run_probe(a, a.work, pad_text, end)
    verify(a, a.work)
    if a.verify_only:
        return 0
    compose(a, a.work, chapters, end, step)
    return 0


if __name__ == '__main__':
    sys.exit(main())
