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
| `cli.py` | argument validation, input/output orchestration |
| `runtime/sm64ds_pose.c` | Saturn-side scale sampling and parent-first T·R·S world matrices |
| `src/viewer.c` | Saturn scene integration, indexed textures, animated skin, orbit camera and clip switching |

**Status:** 17 host tests pass with the locally supplied ASME USA Rev.00 ROM, and 440/450 top-level BMDs parse (10 skybox models require a separate static high-scale path). The generated Mario model has 16 joints, 131 rigid vertices, 246 VDP1 faces and 208 deduplicated indexed8 texture tiles (~52 KiB pixel payload). **This is not an emulator or hardware boot result.**

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

See [converter technical details](docs/CONVERTER.md), [port plan](docs/PORT_PLAN.md), [ROM audit](docs/ROM_AUDIT.md), and [current status](docs/PORT_STATUS.md).

## Current boundaries

This is a **viewer source and measured host asset pipeline**, not a completed playable Mario game. Hardware/SH-2 build and emulator image inspection still need to be run in an environment with the installed toolchain and SDK. Exact DS polygon translucency, lighting, material texture transforms, character head attachment, KCL parity, actor behavior and gameplay remain separate work. Copyrighted assets never enter public CI or commits.
