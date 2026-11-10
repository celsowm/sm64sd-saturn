# Super Mario 64 DS -> Sega Saturn (LibSaturn)

Experimental, source-level port to a **stock Sega Saturn**, referencing [sm64ds-decomp](https://github.com/tangosdev/sm64ds-decomp) and using public [LibSaturn](https://github.com/celsowm/libsaturn) APIs. The repository contains **tools, tests and a scene viewer**, not Nintendo game data.

## Implemented: modular host pipeline and first real viewer source

`tools/sm64ds_convert.py` is only a CLI. The implementation is separated under [`tools/sm64ds_pipeline/`](tools/sm64ds_pipeline):

| Module | Responsibility |
|---|---|
| `common.py` | strict binary spans; fixed-point and quaternion helpers |
| `filesystem.py` | NitroFS FNT/FAT and NARC archives |
| `compression.py` | bounds-checked Nintendo LZ10 |
| `bmd.py` | model hierarchy, material mapping, weighted-matrix metadata |
| `geometry.py` | Nintendo DS GX commands, local matrices, UVs and face winding |
| `textures.py` | formats 1-7 including 4×4 compressed, VDP1 face baking and palette quantization |
| `bca.py` | BCA rotations, translations and animated scale sampling |
| `skinning.py` | rigid and up-to-three-influence LibSaturn skin anchors |
| `emit.py` | LibSaturn C/H model, skin, skeleton and clip export |
| `skybox.py` | camera-relative static background conversion and coordinate normalization |
| `cli.py` | argument validation, input/output orchestration |
| `runtime/sm64ds_pose.c` | Saturn-side scale sampling and parent-first T·R·S world matrices |
| `runtime/sm64ds_background.c` | Camera-following textured skybox, palette isolation, bounded scene admission |
| `src/viewer.c` | Saturn scene integration, indexed textures, animated skin, orbit camera, optional skybox and telemetry |

**Status:** 26/26 tests pass with the locally supplied ASME USA Rev.00 ROM. **450/450** top-level BMDs and **52/52** nested NARC BMDs parse without exemptions; ten skyboxes also export textured static C/H files. The generated Mario model has 16 joints, 131 rigid vertices, 246 VDP1 faces and 208 deduplicated indexed8 texture tiles (~52 KiB pixel payload). **This is not an emulator or hardware boot result.**

## Build locally (ROM not distributed)

```sh
python3 -m unittest discover -s tests -v

SM64DS_ROM='/private/path/Super Mario 64 DS (USA).nds' \
  python3 -m unittest discover -s tests -v

python3 tools/sm64ds_convert.py \
  --rom '/private/path/Super Mario 64 DS (USA).nds' \
  --model 'ARCHIVE/arc0.narc:131' \
  --out /private/derived/sm64ds \
  --name mario_preview \
  --tile-size 16

cmake -S . -B build -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=/prefix/share/libsaturn/toolchains/sh2eb-elf.cmake \
  -DCMAKE_PREFIX_PATH=/prefix \
  -DSM64DS_GENERATED_DIR=/private/derived/sm64ds
cmake --build build
cmake --build build --target sm64ds_viewer_disc
```

The CMake viewer links the installed `LibSaturn::Saturn`; it does **not** download/clone the SDK. On the controller: **A** auto-orbit, **B** camera reset, **C** next animation, D-pad orbit, L/R zoom. The generated C/H and linked disc are private, user-owned derivative assets. No ROM content belongs in public Git.

### Background models / skyboxes

`data/vrbox/vr02.bmd` to `vr11.bmd` use `scaleShift=13`, resulting in
source coordinates reaching 58,982. Use **`--kind skybox`** to export them
as bounded static `sat_model_asset_t` background meshes (default normalized
radius 128, divisor 512 for the ten verified files). Never treat these
camera-relative models as world-scale collision meshes.

```sh
python3 tools/sm64ds_convert.py \
  --rom '/private/path/Super Mario 64 DS (USA).nds' \
  --kind skybox --model data/vrbox/vr02.bmd \
  --out /private/derived/vr02 --name vr02
```

To render a background alongside Mario, generate it into the **same**
private directory using `--name skybox_preview` (instead of `vr02`), then
configure CMake with `-DSM64DS_ENABLE_SKYBOX=ON`. The runtime places the
shell at the camera eye, draws it without backface culling in **pass 0**, and
puts Mario in **pass 1**. Palette bank **1** for the skybox avoids overwriting
Mario's palette bank 0. This is testable source integration; **no
emulator/hardware picture-equivalence is claimed.** See
[skybox audit](docs/SKYBOX_COVERAGE.md) and
[background renderer/build instructions](docs/BACKGROUND_RENDERING.md).

### World HLOD (castle exterior and garden)

A new `--kind world-hlod` converter bridges the real DS BMD material/UV topology to the LibSaturn `model_pipeline.world_hlod` simplifier and WLH1 packer. See [world HLOD integration](docs/WORLD_HLOD_INTEGRATION.md) for the command, verified real-ROM counts and remaining rendering/VRAM gates. Generated geometry and reports stay private. This is not yet a playable outdoor level.

See [converter technical details](docs/CONVERTER.md), [port plan](docs/PORT_PLAN.md), [ROM audit](docs/ROM_AUDIT.md), and [current status](docs/PORT_STATUS.md).

## Current boundaries

This is a **viewer source and measured host asset pipeline**, not a completed playable Mario game. Hardware/SH-2 build and emulator image inspection still need to be run in an environment with the installed toolchain and SDK. Exact DS polygon translucency, lighting, material texture transforms, character head attachment, KCL parity, actor behavior and gameplay remain separate work. Copyrighted assets never enter public CI or commits.
