# SM64DS host converters: architecture, tests, validation

The public source tree contains a **local-ROM asset compiler** and a LibSaturn **native scene viewer**. No extracted Nintendo content is distributed. This pipeline now has separate parsers/emitters instead of a single 700-line Python module.

## Code ownership

`tools/sm64ds_convert.py` delegates only; all implementation lives in `tools/sm64ds_pipeline/`:

- `common.py`, `compression.py`: bounded binary / LZ10 / 20.12→16.16 and quaternion conversions.
- `filesystem.py`: DS FNT/FAT, NARC `BTAF`/`BTNF`/`GMIF` and nested identifiers.
- `bmd.py`: 0x40-byte bone headers, display groups/material references, transform-bone map, weighted matrix ranges and decoded material textures.
- `geometry.py`: DS FIFO command decode, primitive assembly, DS row-vector local matrices and UV preservation.
- `textures.py`: DS palette formats A3I5/2bpp/4bpp/8bpp/4×4/A5I3/RGB555; canonical VDP1 quad baking, transparent palette index 0, deterministic 256-color shared palette and deduplication.
- `bca.py`: 9 BCA channels per bone, keyframe/tail interpolation, circular 12-bit rotations, scales preserved.
- `skinning.py`: inverse-rest local anchors for up to 3 weighted influences, Q15 weights, quantization and rigid-first vertex layout.
- `emit.py`: generated LibSaturn model/skeleton/skin/clip descriptors and private C/H output.
- `runtime/sm64ds_pose.c`: interpolated BCA scales in 16.16; builds world matrices in parent-first order (T×R×S) for `sat_skin_update_mesh` without modifying the LibSaturn API.
- `src/viewer.c`: actual LibSaturn API wiring for model validation, texture uploads, animated mesh, canonical scene and orbit camera.

Each step consumes a source-data buffer or explicit IR; no hidden global asset state, runtime ROM parsing on Saturn, duplicated SDK, or implicit malloc in the Saturn program.

## Run with a private ROM

```bash
python3 tools/sm64ds_convert.py \
  --rom '/private/Super Mario 64 DS (USA).nds' \
  --model 'ARCHIVE/arc0.narc:131' \
  --out /private/derived/sm64ds \
  --name mario_preview --tile-size 16 --vram-texture-budget 262144

python3 -m unittest discover -s tests -v
SM64DS_ROM='/private/Super Mario 64 DS (USA).nds' \
  python3 -m unittest discover -s tests -v

# For a pure hierarchy/rigging diagnostic, without VDP1 textures:
python3 tools/sm64ds_convert.py --rom /private/game.nds \
  --out /private/derived/sm64ds --untextured
```

Output: `mario_preview.c`, `mario_preview.h`, `mario_preview.json` (game-derived, **private**). `--clip name=NitroFS/path.bca` may be repeated to override idle/walk/run/jump. Nominal animation rate defaults to 30 Hz; original gameplay timing is not yet oracle-verified.

## What has been measured

| Local USA Rev.00 source | Value |
|---|---:|
| Top-level BMD parsed | 440 / 450 |
| Unsupported top-level BMD | 10 high-scale `vrbox` skyboxes (`scaleShift=13`) |
| Mario skeletal joints | 16 |
| Mario source vertices | 131 rigid + 0 weighted |
| Mario VDP1 faces | 246 |
| Decoded Mario DS textures | 1 compressed 4×4 source texture |
| Deduplicated VDP1 indexed8 face tiles, size 16×16 | 208 |
| VDP1 face texture pixel bytes (excluding command/other VRAM) | 53,248 |
| BCA frames idle/walk/run/jump | 120 / 30 / 30 / 11 |
| ROM-free + optional local ROM tests | 17 total with ROM, pass |
| Generated C and scale-runtime C syntax | Host GCC `-std=c11 -Wall -Wextra -Werror` with API-shape stubs, pass |

The source RGBA colors are converted to a single RGB555 palette of up to 255 opaque colors plus transparent index 0. When source alpha is fractional, **alpha is thresholded at 128**. The exporter reports the VDP1 pixel budget but **not** frame buffer, scene commands, head, music or other VRAM costs. Numeric counts do not prove rendered fidelity.

## Weighted matrices and animated scales

Upstream `ModelComponents.cpp` has `numWeightedMatrices` and a four-pointer data block (`weights`, `joints`, `ranges`, `rest-bone matrices`). The converter handles matrix slots mapping to those entries and expands 2/3 source influences into per-joint inverse-rest local positions and exact Q15 byte weights, with reindexing of rigid vertices before blends to satisfy LibSaturn. **This was verified by synthetic weighted fixtures:** all 502 BMDs examined in this ROM have zero weighted matrices; there is no real game-weighted case to compare. LibSaturn supports at most three influences; inputs exceeding that explicitly fail.

BCA translation/rotation are emitted in existing `sat_skeleton_clip_t`. Scale is handled as an **independent synchronized array**, interpreted by `sm64ds_clip_sample_scale` and `sm64ds_pose_world_matrices`. It does not try to retrofit `sat_skeleton_pose_joint_t` with a nonexistent scale field. For the four Mario sample clips all per-frame scales are identity; a synthetic squashing clip exercises the non-unit path.

## Native viewer integration

`CMakeLists.txt` accepts `SM64DS_GENERATED_DIR=/private/derived/sm64ds`. It builds the viewer against an **installed LibSaturn SDK**, including `runtime/sm64ds_pose.c` and `src/viewer.c`. Viewer validates source assets, allocates actor-owned scratch buffers, samples pose/scale, recomputes matrices, calls `sat_skin_update_mesh`, and queues its textured mesh through `sat_scene_submit_instance`. Camera and clip switching are live.

**Validation still required:** running this code through a genuine SH-2 cross compiler, linking against the currently installed SDK, booting ISO in Ymir/Mednafen, visually comparing Mario against the upstream PC native port and measuring VDP1 command/VRAM/time budgets. The development container has no `sh2eb-elf-*` compiler, no installed LibSaturn prefix and no emulator. C syntax checked against *matching host declarations* does not prove native compatibility.

## Remaining fidelity boundaries

- Animated gameplay logic, input response and collisions/KCL/CLPS.
- Level effects/lighting, DS material SRT, transparent polygons, color blending and runtime BTP texture-sequence animation.
- Head/face attachment and exact Mario silhouette/pose parity; the one-source-texture body is not the complete character presentation.
- Quads are exported as VDP1 canonical UV-baked tiles with nearest-neighbor sampling: this differs from the DS hardware's perspective-correct rasterizer and needs screenshot comparisons.
- 10 `vrbox` BMDs with high scale shift need a separate static skybox/background importer rather than pretending they are character skins.
- Proven measured frame rate and Saturn execution. All present timings remain assumptions until tested.

Sources: [DS matched BMD](https://github.com/tangosdev/sm64ds-decomp/blob/main/include/BMD_File.h), [BCA interpolation](https://github.com/tangosdev/sm64ds-decomp/blob/main/src/func_0204547c.cpp), [LibSaturn Skin3D](https://github.com/celsowm/libsaturn/blob/main/include/saturn/skin3d.h), [model](https://github.com/celsowm/libsaturn/blob/main/include/saturn/model3d.h) and [package consumer](https://github.com/celsowm/libsaturn/blob/main/docs/PACKAGING.md).
