# Nintendo DS outdoor BMD -> LibSaturn World HLOD

**Status:** adapter, real-ROM geometry regression, and quality-gated castle/garden WLH1 packages measured locally. Requires LibSaturn's material-ownership and orphan-fragment fixes described below. **Not yet a playable outdoor Saturn scene.** No ROM/derived assets are committed.

## Responsibility split

| Stage | Owner | Invariant |
| --- | --- | --- |
| Nintendo NitroFS/BMD decode | `tools/sm64ds_pipeline/{filesystem,bmd,geometry,textures}.py` | Preserves source 4.12 positions, bone assignment, face corner UVs, material IDs |
| Rigid outdoor-scene adapter | `tools/sm64ds_pipeline/world_hlod.py` | Converts each VDP1 quad to two winding-preserving triangles; splits UV/material seams; reports zero-area triangles |
| Spatial partition / QEM / LOD validation | `LibSaturn/tools/model_pipeline/world_hlod.py` | Shared `SourceModel`, source-based per-cell simplification, HLOD metrics, WLH1 packaging; no copied simplifier |
| Per-sector visibility, fade, budget | `LibSaturn::sat_world_lod3d_plan` + `sat_world_lod3d_fade_apply` | Runtime 16.16 camera-relative AABBs and independent face/command estimates |
| Actual VDP1/VDP2 rendering | Existing `LibSaturn::sat_scene_t` painter | No second renderer; textured materials need separate UV baking and residency |
| Collisions | Original `.kcl` / independent physics | Render LOD never changes gameplay collision |

## Convert with your local ROM

```sh
python3 tools/sm64ds_convert.py \
  --rom '/private/Super Mario 64 DS (USA).nds' \
  --kind world-hlod \
  --libsaturn-source '/path/to/libsaturn' \
  --model 'data/stage/main_castle/main_castle_all.bmd' \
  --name main_castle --cell-size 8 --lod-targets 512,384,256 \
  --hlod-quality aggressive \
  --out '/private/sm64ds-world'

python3 tools/sm64ds_convert.py \
  --rom '/private/Super Mario 64 DS (USA).nds' \
  --kind world-hlod \
  --libsaturn-source '/path/to/libsaturn' \
  --model 'data/stage/main_garden/main_garden_all.bmd' \
  --name main_garden --cell-size 8 --lod-targets 256,160,96 \
  --hlod-quality aggressive \
  --out '/private/sm64ds-world'
```

Generated files are **private**: `main_castle.wlh`, `main_castle.json`, `main_castle.materials.json` (and garden equivalents). These outputs must be ignored by Git. The `.wlh` stores geometry, UV and material IDs, **not texture pixel data**; `.materials.json` records references/texture hashes, not copied Nintendo textures. The converter raises on LibSaturn quality or budget failures, rather than silently emitting degraded assets.

## Measured ROM decode (ASME USA Rev. 00)

| Metric | Exterior castle | Garden |
| --- | ---: | ---: |
| BMD faces | 1,337 | 631 |
| Triangles after quad triangulation | 1,370 | 663 |
| Source zero-area triangles | 0 | 2 (BMD faces 237, 240) |
| Non-degenerate triangles handed to LibSaturn | **1,370** | **661** |
| Vertices after splitting UV/material corners | 2,087 | 1,068 |
| Materials | 24 | 20 |
| Unique source RGBA textures | 24 | 19 |
| World X bounds | -8 to +8 | -4.9199 to +4.6987 |

These are static *source conversion* counts; not delivered HLOD sector totals or Saturn command timings. The two zero-area garden triangles have no surface area and are explicitly audited. The BMDs have one identity root and no weighted matrices; this is why they are eligible for this static path.

## Measured WLH1 packages (2026-11-10)

Measured against LibSaturn `5fe2b0b3` plus local fixes in
`tools/model_pipeline/{simplification,world_hlod}.py`:

- Exact-duplicate welding preserves source material ownership. Collapse
  remapping only selects vertex copies compatible with every affected face's
  material, including in aggressive mode.
- Partitioning only allocates vertices for non-degenerate clipped triangles.
  Rejected fragments previously left orphan vertices that inflated cell bounds
  and produced surface-error failures even with no simplification.

Both fixes have synthetic regressions in LibSaturn. All quality thresholds
remain unchanged. The original `160,64,24` targets still fail real surface-error
gates; the explicit per-scene targets above pass and are starting points for
runtime evaluation, not proven Saturn budgets.

| Metric | Exterior castle | Garden |
| --- | ---: | ---: |
| Cells, size 8 | 8 | 8 |
| Per-cell LOD targets | 512 / 384 / 256 | 256 / 160 / 96 |
| Partitioned source triangle fragments | 1,951 | 955 |
| Delivered triangles, summed across cells, LOD0 / LOD1 / LOD2 | 1,951 / 1,881 / 1,459 | 955 / 895 / 623 |
| WLH1 bytes, all three levels | 207,836 | 102,292 |
| Geometry payload bytes, LOD0 / LOD1 / LOD2 | 76,228 / 73,788 / 56,992 | 38,520 / 36,500 / 26,444 |
| Source triangle and area coverage | 100% | 100% |
| Minimum fixed-camera silhouette IoU, LOD2 | 0.9575 | 0.9393 |

Clipping increases triangle counts before simplification; totals across all
cells are not per-frame draw counts. Source coverage describes partitioning,
not exact preservation of every simplified surface. Every cell/level passed
the requested quality and triangle-budget gates. Independent binary read-back
verified package lengths, offsets, indices and source checksums. Local outputs
and full reports are under ignored `private/world-hlod/`.

These are host geometry and silhouette measurements. Texture appearance,
Saturn framebuffer parity, runtime RAM/VRAM residency and navigation remain
unverified. WLH1 excludes texels, and source texture byte estimates are not
post-bake VDP1 residency measurements.

## Next acceptance gates (not claimed complete)

1. Review textured images of the generated packages and tune protected regions/LOD targets for actual camera routes. Host package creation, coverage, byte accounting and quality gates have passed as recorded above; textured image review remains open.
2. Convert **post-partition/post-simplification** face UVs/material IDs into VDP1-compatible indexed textures and palette banks; do not reuse source per-face baked tiles after changing topology. Resolve CD and VRAM residency without preloading every texture/LOD.
3. Decode WLH1 cells into fixed work RAM scratch and construct `sat_world_lod3d_object_t` / `sat_world_lod3d_level_t` entries; respect scene/HUD reserve and fixed-point camera origin rebasing.
4. Integrate terrain/sky in VDP2 where visually valid. Only apply indexed VDP1-to-VDP2 fade with valid priorities; the Mario actor and castle facade must share physically correct painter ordering.
5. Preserve `.kcl` for movement/collision, validate BMD/KCL scale and origin, run SH-2 build and Ymir navigation routes across the entire exterior with matched screenshots and `sat_scene_stats` telemetry. Record CPU/division cost, true commands, VDP1 fill risk, actual palette/texture residency and VBlank cadence.

### Tests

```sh
python3 -m unittest discover -s tests -v
SM64DS_ROM='/private/Super Mario 64 DS (USA).nds' python3 -m unittest discover -s tests -v
```

Tests use no commercial asset bytes by default. The ROM-gated test checks actual castle and garden winding, materials, UV seam split and zero-area bookkeeping. Actual HLOD simplification requires LibSaturn's Python toolchain and is not exercised by the adapter-only test suite.
