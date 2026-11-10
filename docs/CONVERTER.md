# Experimental SM64DS model/animation converter (Gate 1 -> early Gate 3)

`tools/sm64ds_convert.py` reads a **locally provided ASME Rev.00 `.nds`** and exports a flat-color **rigging diagnostic** in the **current LibSaturn C API**: `sat_model_asset_t` (geometry with untextured quads), `sat_skin_asset_t` (rigid per-bone vertex anchors), `sat_skeleton_asset_t` (16-joint hierarchy), and `sat_skeleton_clip_t[]` (per-frame joint translation + Q15 quaternion). No third-party pip modules are required. The ROM and derived assets stay local.

## Run

```bash
python3 tools/sm64ds_convert.py \
  --rom '/private/path/Super Mario 64 DS (USA).nds' \
  --model 'ARCHIVE/arc0.narc:131' \
  --out /private/path/derived/sm64ds \
  --name mario_preview

python3 -m unittest discover -s tests -v
SM64DS_ROM='/private/path/Super Mario 64 DS (USA).nds' \
  python3 -m unittest discover -s tests -v
```

By default `idle=su_wait`, `walk=su_walk`, `run=su_run`, and `jump=su_jump` are read from the NitroFS root. Override with repeated `--clip name=data/.../clip.bca`. The presumed sampling rate is `30/1`, configurable with `--rate-num` and `--rate-den`. **The original game's playback rate has not been proven here.**

Generated files: `mario_preview.h`, `mario_preview.c`, `mario_preview.json`. They contain game-derived data and **must never be committed publicly**. `.gitignore` protects conventional derived output directories but you are responsible for your own `--out` path.

## What is implemented

- ASME Rev.00 header/version, FNT/FAT validation, named NitroFS lookup and nested NARC (`BTAF`/`BTNF`/`GMIF`) lookup.
- Strict Nintendo LZ10 decompression for the `LZ77`-wrapped SM64DS payloads; rejects truncated streams, output overruns and bad references.
- BMD bone hierarchy and local model-space vertex decoding from supported packed GX FIFO commands (`BEGIN_VTXS`, `MTX_RESTORE`, `VTX_16/10/XY/XZ/YZ/DIFF`, strips and quads), with distinct matrix slot -> joint mapping.
- BCA channels with keyframe interpolation and special tail frames, shortest-arc 12-bit angle wrap, translation in 20.12 and conversion to 16.16, Euler XYZ to normalized Q15 quaternion, plus per-joint frame-sign continuity.
- C emitted in the current LibSaturn public struct layouts. Validation rejects weighted matrices, dynamic scaling, unknown GX opcodes, unsupported bone order and capacity violations rather than silently producing inaccurate poses.
- CI-friendly tests independent of ROM and optional ASME integration tests using `SM64DS_ROM`.

## Crucial limitations

**This is NOT yet a bootable Mario game or a textured-model converter.** Geometry is an untextured diagnostic: face->texture entries are `SAT_MESH_TEXTURE_NONE`. This avoids falsely claiming VDP1 texture/UV equivalence. The BMD source may contain `TEXCOORD` changes, but per-face texture baking and palette/alpha transforms are not implemented yet. A runtime must allocate an actor-owned mutable mesh, copy the model topology, sample/evaluate the skeleton, get joint world matrices, then call `sat_skin_update_mesh()` before submitting to `sat_scene_submit_instance()`. The generated `model.vertices` are joint-local placeholders, **not** a posed bind-model to render as-is.

The generated clips store explicit per-frame `sat_skeleton_pose_joint_t` records (20 bytes per joint per frame), not a compressed SKA1 archive. For Mario this is a useful initial correctness fixture. Convert to the LibSaturn `SKA1`/streaming character format only once the raster/texture path is proven and RAM has been measured. No material/skin weighting >1 joint, normal lighting, BTP/BTA, KCL, CLPS, physics, player/game logic, head attachment or VDP1 pixel-perfectness is claimed.

## Acceptance measured locally on ASME Rev.00

| Measure | Current conversion |
|---|---:|
| BMD NARC `ARCHIVE/arc0.narc:131` joints | 16 |
| GX rigid source vertices | 131 |
| Native face/quad records | 246 |
| Weighted BMD matrices | 0 |
| BCA idle/walk/run/jump frames | 120 / 30 / 30 / 11 |
| Four clips' uncompressed pose payload | 61,120 bytes |
| Estimated geometry+pose arrays (excluding C pointers/metadata) | ~66,200 bytes |

This is **ROM metadata and a host emitter measurement**, not a Saturn SH-2 timing or VRAM measurement. Re-run with a pinned LibSaturn build and use `sat_model_validate()`, `sat_skin_validate()`, `sat_skeleton_validate()` and `sat_clip_validate()` before accepting generated assets. Host C syntax checking with equivalent stub declarations is useful but **does not** replace SH-2 linking or emulator test.

References: [ROM_AUDIT.md](ROM_AUDIT.md), [PORT_PLAN.md](PORT_PLAN.md), [upstream BCA sampler](https://github.com/tangosdev/sm64ds-decomp/blob/main/src/func_0204547c.cpp), [upstream BMD formats](https://github.com/tangosdev/sm64ds-decomp/blob/main/include/BMD_File.h), [LibSaturn skin3d.h](https://github.com/celsowm/libsaturn/blob/main/include/saturn/skin3d.h).