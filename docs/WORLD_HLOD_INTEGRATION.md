# Nintendo DS outdoor BMD -> LibSaturn World HLOD

**Status:** adapter + real-ROM geometry regression; WLH1 creation requires a local checkout of LibSaturn and acceptance of its source-specific quality gates. **Not yet a playable outdoor Saturn scene.** No ROM/derived assets are committed.

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
  --name main_castle --cell-size 8 --lod-targets 160,64,24 \
  --hlod-quality aggressive \
  --out '/private/sm64ds-world'

python3 tools/sm64ds_convert.py \
  --rom '/private/Super Mario 64 DS (USA).nds' \
  --kind world-hlod \
  --libsaturn-source '/path/to/libsaturn' \
  --model 'data/stage/main_garden/main_garden_all.bmd' \
  --name main_garden --cell-size 8 --lod-targets 160,64,24 \
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

## Next acceptance gates (not claimed complete)

1. Run the real LibSaturn `build_package` on each private source; inspect failed quality gates, area coverage, sector count, delivered triangle counts, and byte budget. Do not accept a lower-quality LOD without image/metric review.
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
