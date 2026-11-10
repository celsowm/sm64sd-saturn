# High-scale skybox BMD coverage — ASME Rev.00

Verified 2026-11-10 with a privately supplied USA Rev.00 ROM. This document contains no Nintendo asset bytes.

## Root cause

All ten files data/vrbox/vr02.bmd through vr11.bmd have valid, nonempty one-bone geometry and source scaleShift=13. The previous parser rejected everything above 12. Their original source coordinates reach approximately 58,982 game units, outside the signed 16.16 coordinate range of the Saturn runtime. Raising the parser threshold without changing the exporter would overflow its skin positions.

## Separate static converter

The module tools/sm64ds_pipeline/skybox.py validates a single identity root, no weighted matrices, and nonempty faces. It chooses the smallest power-of-two uniform scale divisor that keeps the source geometry inside --skybox-radius (default 128), preserving UVs and all relative proportions.

Source DS units = raw_vertex * 2**scaleShift / 4096
Saturn Q16 = round(raw_vertex * 2**(scaleShift+16) / (4096*divisor))

For all ten ASME skyboxes: scaleShift=13; divisor=512; Q16=raw_vertex*256 exactly; original extent 58,982 becomes 115.19921875 units with zero quantization error. The transformed geometry is a CAMERA-RELATIVE VISUAL BACKGROUND, not a world-space collision mesh.

The converter produces a static sat_model_asset_t with geometry, face-to-texture mappings, UV-baked indexed8 VDP1 textures and a shared RGB555 palette. No fake animation or skeleton is emitted.

## Usage (private local ROM)

    python3 tools/sm64ds_convert.py \
      --rom '/private/path/Super Mario 64 DS (USA).nds' \
      --kind skybox --model data/vrbox/vr02.bmd \
      --name vr02 --out /private/derived/vr02

    # Smaller texture tiles, optional
    python3 tools/sm64ds_convert.py \
      --rom '/private/path/Super Mario 64 DS (USA).nds' \
      --kind skybox --model data/vrbox/vr03.bmd \
      --tile-size 8 --skybox-radius 128 \
      --name vr03 --out /private/derived/vr03

The ROM-derived .c, .h, and .json output files must remain private and are NOT committed. The JSON report records coordinate scale, texture budget, face coverage and source counts.

## Saturn renderer contract

The instance world origin must follow camera.eye each frame; its cull_backfaces setting must be 0 because the camera is inside the shell; submit it in a background pass with correct painter ordering. The static emitter does not implement a running background scene and does not prove native rendering.

## Verified coverage

- 450 / 450 top-level NitroFS BMDs parsed with zero tolerated exceptions.
- 52 / 52 named NARC BMDs parsed, 502 / 502 BMDs total.
- 10 / 10 skyboxes exported as textured static C/H, each with nonempty tiles, zero untextured faces and less than 256 KiB of VDP1 texture pixel payload.
- All ten private C exports passed GCC C11 -Wall -Wextra -Werror -fsyntax-only against matching header stubs (not a real LibSaturn link).
- 22 / 22 Python tests passed with the private ROM; without it, 14 pass and 8 are skipped.

Remaining: SH-2 compile, installed LibSaturn package link, Ymir/Mednafen images, exact material alpha and background pass parity, and runtime performance.
