#!/usr/bin/env python3
"""Generate ROM-derived Sega Saturn assets and CRI ADX audio for the SM64DS intro."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sm64ds_pipeline.bca import Animation
from tools.sm64ds_pipeline.bmd import Model, convert_bmd
from tools.sm64ds_pipeline.ds2d import (
    extract_cloud_atlas,
    render_mario3d_banner,
    render_peach_letter_card,
)
from tools.sm64ds_pipeline.emit import emit_model
from tools.sm64ds_pipeline.filesystem import Filesystem
from tools.sm64ds_pipeline.sdat import (
    SdatArchive,
    encode_adx_payload,
    render_sseq_pcm_s16be,
    resample_wave_s8,
)


def _fmt_u16_array(values, per_line: int = 12) -> str:
    rows = []
    for i in range(0, len(values), per_line):
        rows.append("    " + ", ".join(f"0x{v & 0xFFFF:04X}u" for v in values[i : i + per_line]) + ",")
    return "\n".join(rows)


def _fmt_u8_array(data: bytes, per_line: int = 16) -> str:
    rows = []
    for i in range(0, len(data), per_line):
        rows.append("    " + ", ".join(f"0x{b:02X}u" for b in data[i : i + per_line]) + ",")
    return "\n".join(rows)


def _fmt_s8_array(data: bytes, per_line: int = 16) -> str:
    rows = []
    for i in range(0, len(data), per_line):
        chunk = [b - 256 if b >= 128 else b for b in data[i : i + per_line]]
        rows.append("    " + ", ".join(f"{v:4d}" for v in chunk) + ",")
    return "\n".join(rows)


def _project_star_uvs(model: Model) -> Model:
    """Assign spherical UVs to env-mapped Power Star faces so star_body04 shades cleanly."""
    if not model.vertices or not model.material_textures:
        return model
    tex0 = model.material_textures[0]
    tw = float(tex0.width if tex0 else 32)
    th = float(tex0.height if tex0 else 32)
    new_uvs = []
    for fi, face in enumerate(model.faces):
        mat = model.face_materials[fi]
        if mat == 0 and tex0 is not None:
            fuv = []
            for vi in face:
                v = model.vertices[vi]
                r = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) or 1.0
                u = (0.5 + 0.42 * (v.x / r)) * (tw - 1.0)
                vv = (0.5 - 0.42 * (v.y / r)) * (th - 1.0)
                fuv.append((u, vv))
            new_uvs.append(tuple(fuv))
        else:
            new_uvs.append(model.face_uvs[fi])
    return Model(
        scale_shift=model.scale_shift,
        bones=model.bones,
        weighted=model.weighted,
        vertices=model.vertices,
        faces=model.faces,
        face_uvs=new_uvs,
        face_materials=model.face_materials,
        face_colors=model.face_colors,
        material_textures=model.material_textures,
        material_count=model.material_count,
        texture_count=model.texture_count,
        weighted_count=model.weighted_count,
        gx_commands=model.gx_commands,
        material_flags=model.material_flags,
        face_rooms=model.face_rooms,
        face_provenance=model.face_provenance,
    )


def _quantize_sprites_indexed8(
    sprites: list[tuple[str, object]]
) -> tuple[list[int], dict[str, bytes]]:
    """Pack multiple RGB555 sprites into one shared 256-color CRAM palette (0=transparent)."""
    color_counts: dict[int, int] = {}
    for _sym, spr in sprites:
        for v in spr.pixels:
            if v & 0x8000:
                raw = v & 0x7FFF
                color_counts[raw] = color_counts.get(raw, 0) + 1
    # Keep top 255 colors; if <= 255 colors, completely lossless!
    ordered = [c for c, _ in sorted(color_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:255]]
    palette = [0] + ordered + [0] * (255 - len(ordered))
    exact = {c: idx + 1 for idx, c in enumerate(ordered)}
    rgb_cache = [(c & 31, (c >> 5) & 31, (c >> 10) & 31) for c in ordered]
    nearest_cache: dict[int, int] = {}

    def map_color(raw: int) -> int:
        if raw in exact:
            return exact[raw]
        if raw in nearest_cache:
            return nearest_cache[raw]
        r, g, b = raw & 31, (raw >> 5) & 31, (raw >> 10) & 31
        best_i = 1
        best_d = 1 << 30
        for idx, (pr, pg, pb) in enumerate(rgb_cache):
            d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if d < best_d:
                best_d = d
                best_i = idx + 1
        nearest_cache[raw] = best_i
        return best_i

    indexed: dict[str, bytes] = {}
    for sym, spr in sprites:
        indexed[sym] = bytes(map_color(v & 0x7FFF) if (v & 0x8000) else 0 for v in spr.pixels)
    return palette, indexed


def _emit_2d_assets(fs: Filesystem, out: Path) -> dict:
    title_spr = render_mario3d_banner(
        fs,
        [("SUPER MARIO", "BGYRGYRGYR"), ("64 DS", "RBYRG")],
        char_advance=15,
        line_height=18,
    )
    nint_spr = render_mario3d_banner(
        fs,
        [("NINTENDO", "RRRRRRRR")],
        char_advance=15,
        line_height=18,
    )
    start_spr = render_mario3d_banner(
        fs,
        [("PRESS START", "YYYYYYYYYY")],
        char_advance=14,
        line_height=18,
    )
    letter_spr = render_peach_letter_card(
        fs,
        [
            "Dear Mario:",
            "Please come to",
            "the castle. I've",
            "baked a cake",
            "for you.",
            "Yours truly--",
            "Princess Toadstool,",
        ],
        width=160,
        height=168,
    )
    clouds = extract_cloud_atlas(fs)

    sprites = [
        ("intro_banner_title", title_spr),
        ("intro_banner_nintendo", nint_spr),
        ("intro_banner_start", start_spr),
        ("intro_peach_letter_card", letter_spr),
    ]
    shared_palette, indexed_pixels = _quantize_sprites_indexed8(sprites)

    h_lines = [
        "#pragma once",
        "#include <stdint.h>",
        "",
        "extern const uint16_t intro_2d_palette[256u];",
        "",
    ]
    c_lines = [
        '#include "intro_2d.h"',
        "",
        "/* Locally generated from a user-provided ROM; not for public distribution. */",
        "",
        "const uint16_t intro_2d_palette[256u] = {",
        _fmt_u16_array(shared_palette, 12),
        "};",
        "",
    ]

    for sym, spr in sprites:
        macro = sym.upper()
        px = indexed_pixels[sym]
        h_lines.append(f"#define {macro}_W {spr.width}u")
        h_lines.append(f"#define {macro}_H {spr.height}u")
        h_lines.append(f"extern const uint8_t {sym}_pixels[{len(px)}u];")
        c_lines.append(f"const uint8_t {sym}_pixels[{len(px)}u] = {{")
        c_lines.append(_fmt_u8_array(px))
        c_lines.append("};")
        c_lines.append("")

    h_lines += [
        f"#define INTRO_CLOUD_ATLAS_W {clouds.width}u",
        f"#define INTRO_CLOUD_ATLAS_H {clouds.height}u",
        f"extern const uint8_t intro_cloud_atlas_4bpp[{len(clouds.pixels)}u];",
        "extern const uint16_t intro_cloud_palette[16u];",
        "",
    ]
    c_lines += [
        f"const uint8_t intro_cloud_atlas_4bpp[{len(clouds.pixels)}u] = {{",
        _fmt_u8_array(clouds.pixels),
        "};",
        "",
        "const uint16_t intro_cloud_palette[16u] = {",
        _fmt_u16_array(clouds.palette, 8),
        "};",
        "",
    ]

    (out / "intro_2d.h").write_text("\n".join(h_lines), encoding="ascii")
    (out / "intro_2d.c").write_text("\n".join(c_lines), encoding="ascii")
    return {
        "sprites": {sym: (spr.width, spr.height, len(indexed_pixels[sym])) for sym, spr in sprites},
        "shared_palette_colors": sum(1 for c in shared_palette[1:] if c != 0),
        "cloud_atlas_bytes": len(clouds.pixels),
    }


def _emit_audio_assets(fs: Filesystem, out: Path) -> dict:
    sdat = SdatArchive(fs.read("data/sound_data.sdat"))
    disc_audio = out / "disc_audio" / "AUDIO"
    disc_audio.mkdir(parents=True, exist_ok=True)

    tracks = [
        ("TITLE", "NCS_BGM_TITLE", "TITLE.ADX", 22050, 2, 22.0),
        ("PEACH", "NCS_BGM_PEACH", "PEACH.ADX", 22050, 2, 10.0),
        ("OPENING", "NCS_BGM_OPENING", "OPENING.ADX", 22050, 1, 14.0),
    ]

    meta_lines = [
        "#pragma once",
        "#include <saturn/audio.h>",
        "",
        "/* Locally generated CRI ADX metadata from a user-provided ROM. */",
        "",
    ]
    track_stats = {}
    for macro, seq_name, filename, rate, ch, max_s in tracks:
        pcm, _frames = render_sseq_pcm_s16be(
            sdat, seq_name, sample_rate=rate, channels=ch, max_seconds=max_s
        )
        adx = encode_adx_payload(pcm, sample_rate=rate, channels=ch)
        (disc_audio / filename).write_bytes(adx.payload)
        meta_lines += [
            f'#define SM64DS_AUDIO_{macro}_DISC_PATH "AUDIO/{filename}"',
            f"#define SM64DS_AUDIO_{macro}_SAMPLE_RATE {adx.sample_rate}u",
            f"#define SM64DS_AUDIO_{macro}_CHANNELS {adx.channels}u",
            f"#define SM64DS_AUDIO_{macro}_SAMPLE_COUNT {adx.sample_count}u",
            f"#define SM64DS_AUDIO_{macro}_BYTES {len(adx.payload)}u",
            f"#define SM64DS_AUDIO_{macro}_FORMAT SAT_AUDIO_ADX_ADPCM",
            "",
        ]
        track_stats[macro] = {
            "file": f"AUDIO/{filename}",
            "sample_rate": adx.sample_rate,
            "channels": adx.channels,
            "sample_count": adx.sample_count,
            "bytes": len(adx.payload),
        }

    (out / "intro_audio_meta.h").write_text("\n".join(meta_lines), encoding="ascii")

    # Resident SCSP PCM8 SFX/voice clips for 0.BIN
    swar_nint = sdat.decode_swar_waves(0)
    swar_peach = sdat.decode_swar_waves(1)
    swar_title = sdat.decode_swar_waves(9)
    swar_mario = sdat.decode_swar_waves(37)

    sfx_rate = 16000
    sfx_specs = [
        ("intro_sfx_nintendo", resample_wave_s8(swar_nint[0], sfx_rate), sfx_rate),
        ("intro_sfx_mario_hello", resample_wave_s8(swar_mario[0], 11025), 11025),
        ("intro_sfx_start", resample_wave_s8(swar_title[3], sfx_rate), sfx_rate),
        ("intro_sfx_star", resample_wave_s8(swar_title[0], sfx_rate), sfx_rate),
        ("intro_sfx_peach_0", resample_wave_s8(swar_peach[0], sfx_rate), sfx_rate),
        ("intro_sfx_peach_1", resample_wave_s8(swar_peach[1], sfx_rate), sfx_rate),
        ("intro_sfx_peach_2", resample_wave_s8(swar_peach[2], sfx_rate), sfx_rate),
        ("intro_sfx_peach_3", resample_wave_s8(swar_peach[3], sfx_rate), sfx_rate),
        ("intro_sfx_peach_4", resample_wave_s8(swar_peach[4], sfx_rate), sfx_rate),
        ("intro_sfx_peach_5", resample_wave_s8(swar_peach[5], sfx_rate), sfx_rate),
    ]

    sh_lines = [
        "#pragma once",
        "#include <stdint.h>",
        '#include "intro_audio_meta.h"',
        "",
        "typedef struct sm64ds_sfx_clip {",
        "    const int8_t* samples;",
        "    uint32_t sample_count;",
        "    uint32_t sample_rate;",
        "} sm64ds_sfx_clip_t;",
        "",
        f"#define INTRO_PEACH_VOICE_COUNT 6u",
        "extern const sm64ds_sfx_clip_t intro_sfx_nintendo;",
        "extern const sm64ds_sfx_clip_t intro_sfx_mario_hello;",
        "extern const sm64ds_sfx_clip_t intro_sfx_start;",
        "extern const sm64ds_sfx_clip_t intro_sfx_star;",
        "extern const sm64ds_sfx_clip_t intro_sfx_peach[INTRO_PEACH_VOICE_COUNT];",
        "",
    ]
    sc_lines = [
        '#include "intro_audio.h"',
        "",
        "/* Locally generated SCSP PCM8 SFX/voice clips from a user-provided ROM. */",
        "",
    ]
    total_sfx_bytes = 0
    for sym, pcm8, rate in sfx_specs:
        # Pad length to even byte count for SCSP DMA alignment
        if len(pcm8) & 1:
            pcm8 += b"\x00"
        total_sfx_bytes += len(pcm8)
        sc_lines.append(f"static const int8_t {sym}_pcm[{len(pcm8)}u] = {{")
        sc_lines.append(_fmt_s8_array(pcm8))
        sc_lines.append("};")
        sc_lines.append("")
        if not sym.startswith("intro_sfx_peach_"):
            sc_lines.append(
                f"const sm64ds_sfx_clip_t {sym} = {{{sym}_pcm, {len(pcm8)}u, {rate}u}};"
            )
            sc_lines.append("")

    sc_lines.append("const sm64ds_sfx_clip_t intro_sfx_peach[INTRO_PEACH_VOICE_COUNT] = {")
    for i in range(6):
        sym, pcm8, rate = sfx_specs[4 + i]
        n = len(pcm8) + (len(pcm8) & 1)
        sc_lines.append(f"    {{{sym}_pcm, {n}u, {rate}u}},")
    sc_lines.append("};")
    sc_lines.append("")

    (out / "intro_audio.h").write_text("\n".join(sh_lines), encoding="ascii")
    (out / "intro_audio.c").write_text("\n".join(sc_lines), encoding="ascii")
    return {"adx_tracks": track_stats, "resident_sfx_bytes": total_sfx_bytes}


def prepare_intro(rom: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    fs = Filesystem.from_file(rom)

    # 1. 3D Mario Face Demo (29 rigid bones + idle wait loop)
    mario_face = convert_bmd(fs.read("data/DSMT/face_demo_mario.bmd"))
    mario_wait = Animation(fs.read("data/DSMT/face_demo_wait_mario.bca"), len(mario_face.bones))
    h, c, mf_stats = emit_model(
        mario_face,
        [("wait", mario_wait)],
        "mario_face",
        textured=True,
        tile_size=16,
        texture_budget=96 * 1024,
        lut4=True,
        adaptive_size=True,
    )
    (out / "mario_face.h").write_text(h, encoding="ascii")
    (out / "mario_face.c").write_text(c, encoding="ascii")

    # 2. 3D Power Star (spherical UV projection for golden metallic sheen + opening flight)
    star_model = _project_star_uvs(convert_bmd(fs.read("data/DSMT/face_demo_mariostar.bmd")))
    star_anim = Animation(fs.read("data/DSMT/opening_star_short.bca"), len(star_model.bones))
    h, c, star_stats = emit_model(
        star_model,
        [("short", star_anim)],
        "intro_star",
        textured=True,
        tile_size=16,
        texture_budget=24 * 1024,
        lut4=True,
        adaptive_size=True,
    )
    (out / "intro_star.h").write_text(h, encoding="ascii")
    (out / "intro_star.c").write_text(c, encoding="ascii")

    # 3. 3D Princess Peach (21 rigid bones + peach_op_wait loop)
    peach_model = convert_bmd(fs.read("data/enemy/peach/peach_low.bmd"))
    peach_anim = Animation(fs.read("data/enemy/peach/peach_op_wait.bca"), len(peach_model.bones))
    h, c, peach_stats = emit_model(
        peach_model,
        [("wait", peach_anim)],
        "peach_actor",
        textured=True,
        tile_size=16,
        texture_budget=64 * 1024,
        lut4=True,
        adaptive_size=True,
    )
    (out / "peach_actor.h").write_text(h, encoding="ascii")
    (out / "peach_actor.c").write_text(c, encoding="ascii")

    # 4. 2D Banners, Peach Letter Card & VDP2 Cloud Atlas
    d2_stats = _emit_2d_assets(fs, out)

    # 5. SDAT Audio -> CRI ADX CD streams + Resident SCSP PCM8 SFX/Voices
    audio_stats = _emit_audio_assets(fs, out)

    summary = {
        "rom_sha256": fs.sha256,
        "mario_face": {
            "verts": len(mario_face.vertices),
            "faces": len(mario_face.faces),
            "bones": len(mario_face.bones),
            "tex_bytes": mf_stats["texture_pixels_bytes"],
        },
        "intro_star": {
            "verts": len(star_model.vertices),
            "faces": len(star_model.faces),
            "tex_bytes": star_stats["texture_pixels_bytes"],
        },
        "peach_actor": {
            "verts": len(peach_model.vertices),
            "faces": len(peach_model.faces),
            "bones": len(peach_model.bones),
            "tex_bytes": peach_stats["texture_pixels_bytes"],
        },
        "assets_2d": d2_stats,
        "audio": audio_stats,
    }
    (out / "intro_manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    summary = prepare_intro(args.rom, args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
