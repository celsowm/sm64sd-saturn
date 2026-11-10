# Camera-relative skyboxes (BMD) on LibSaturn VDP1

**Status: implementation and host tests; no SH-2 link/emulator screenshot yet.**
No Nintendo ROM, textures or extracted assets are checked into this repository.

## Source pipeline and normalization

`tools/sm64ds_pipeline/skybox.py` converts a one-bone static BMD into an
immutable `sat_model_asset_t`. The ten ASME Rev.00 `data/vrbox/vr02.bmd`
through `vr11.bmd` files use `scaleShift=13`, with original coordinates up
to ~58,982 world units: these cannot be used directly with signed 16.16
Saturn coordinates. A uniform power-of-two divisor (**512** for these ten)
places them inside a camera-relative shell (~115.2 units maximum), without
measurable quantization error on the tested ROM. UVs become VDP1-compatible
indexed8 face textures. These are visual backgrounds, **not collision meshes**.

## Runtime behavior

The independent `runtime/sm64ds_background.h/.c`:

- Validates face/texture mapping and caller-owned buffer capacities before
  uploading geometry/textures **once at startup**.
- Requires indexed8 palette bank **1..7** for the skybox. Mario uses bank
  **0**. This prevents the actual palette overwrite present in the previous
  exporter. The SDK's `sat_model_upload_textures` honors
  `asset->palette_base + texture.palette_slot`.
- Rebuilds **only the world translation** to match `camera.eye` each frame.
  The camera orientation stays in the scene view/projection matrix.
- Disables backface culling (viewed from **inside** the shell); does not apply
  world collider semantics or whole-instance AABB culling.
- Rejects scene capacity exhaustion and 16.16 translation overflow **before**
  touching the background world matrix or attempting submission.

LibSaturn's source painter key is `(255 - pass) << 24 | depth`, so **pass 0
paints before pass 1**. We submit background in **pass 0**, Mario in **pass
1**, and flush the one scene-wide face queue. This intentional *artistic*
ordering is appropriate for a distant backdrop; it does not claim a
Z-buffer, transparent polygon parity or perfect screen-space clipping.

The viewer allocates its scene face capacity from the two generated asset
constants and preflights a **192 KiB combined texture policy budget**. This is
not a measurement of actual VDP1 VRAM availability: the SDK allocator is the
final authority. `sat_scene_flush_trusted` is used because both sets of
materials and textures stay resident and immutable throughout every frame;
the SDK still enforces command reservation and rollback semantics.

## Build with private ROM-derived assets

```sh
ROM='/private/path/Super Mario 64 DS (USA).nds'
PRIVATE=/private/derived/sm64ds
python3 tools/sm64ds_convert.py --rom "$ROM" \
    --model 'ARCHIVE/arc0.narc:131' --name mario_preview --out "$PRIVATE"
python3 tools/sm64ds_convert.py --rom "$ROM" \
    --kind skybox --model data/vrbox/vr02.bmd \
    --name skybox_preview --out "$PRIVATE"

cmake -S . -B build -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=/prefix/share/libsaturn/toolchains/sh2eb-elf.cmake \
  -DCMAKE_PREFIX_PATH=/prefix \
  -DSM64DS_GENERATED_DIR="$PRIVATE" \
  -DSM64DS_ENABLE_SKYBOX=ON
cmake --build build
cmake --build build --target sm64ds_viewer_disc
```

`SM64DS_ENABLE_SKYBOX` defaults to OFF. Set ON to require private
`skybox_preview.c/.h`; change `--model` to test other vrbox assets.
Generated assets and the final disc remain local.

## Verified host numbers and telemetry

Local ASME Rev.00 conversion with `vr02`:

| | Mario | Skybox vr02 |
|---|---:|---:|
| Source/compiled vertices | 131 | 84 |
| VDP1 faces (potential commands) | 246 | 126 |
| Deduplicated texture tiles | 208 | 55 |
| Indexed8 texture pixel bytes | 53,248 | 14,080 |

Combined **67,328 bytes of pixels** and **372 potential faces**.
Other skyboxes have different counts. These are **host source measurements**,
NOT actual VDP1 command usage or frame time.

The global `g_sm64ds_viewer_stats` (magic `0x534b5931`, SKY1) records
**actual scene frame stats** after a successful flush: submitted faces,
world commands, command capacity/use, skipped/culled/clipped/fallback faces.
When LibSaturn profiling is enabled, `profile_ticks_available=1` and
projection, painter and emission ticks are also reported. When unavailable
they must not be interpreted as measured zero.

`python3 -m unittest discover -s tests -v` runs the ROM-free host mock C
test for camera following, palette protection and atomic admission. With
`SM64DS_ROM=/private/...nds` it also tests the ten converted backgrounds,
palette separation, policy budgets and generated C11 syntax.

## Remaining acceptance

Compile/link with installed `sh2eb-elf-gcc` and LibSaturn. Boot the
generated disc in Ymir, inspect inside-facing skybox and camera rotation,
compare source screenshots to the DS/PC-port oracle, record command and
profiling metrics in multiple camera angles. No such SH-2/emulator
measurement was possible in the current environment. Translucency,
material SRT/scrolling and pixel-perfect Nintendo DS equivalence remain
unverified.
