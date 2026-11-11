# Port status — 2026-11-10 (modular converter / textured viewer)

## Current: playable castle grounds prototype

The `sm64ds_castle` SH-2 target now builds a private bootable disc and supports
walking/running, jumping/landing, wall/ceiling collision, camera orbit, pause
and reset on the original exterior and independent KCL. The separate gameplay
head is attached to body bone 15. **42/42 ROM-enabled host tests pass.**

Ymir input replays and a full BIOS boot were captured. Direct Mednafen image
inspection exposed partial VDP1 lists under automatic field swaps; explicit
`SAT_VDP1_FRAME_ON_SUBMIT` fixed the missing Mario/HUD. A fresh Mednafen capture
shows the corrected gameplay head and complete scene. The current SDK was
rebuilt and installed before linking. Generated assets/captures remain ignored.

This is an exploration prototype with roughly 8 draws/second in the initial
full-detail Ymir routes. Original DS movement, CLPS behaviors, water/swimming,
doors, actors, audio, missions, image parity and hardware acceptance remain
open. High WRAM residency also needs reduction before expansion. See
[playable castle build, controls and evidence](PLAYABLE_CASTLE.md).

Earlier entries below describe prior milestones and their then-open gates.

## Completed and locally checked

- Parser responsibilities split into 10 small Python modules under `tools/sm64ds_pipeline/`; CLI remains a thin orchestrator.
- Nintendo DS source formats 1-7 (including critical compressed 4×4 format 5) decode to RGBA; per-face VDP1 indexed8 canonical textures share one RGB555 palette.
- DS GX FIFO interpreter accepts known matrix and material-state operations, retains UVs and matrix-joint identities; unknown commands fail explicitly.
- BMD weighted matrix parsing and up-to-three-influence inverse-rest anchors added, with synthetic tests. This USA ROM contains 0 weighted BMD matrices across 502 inspected models.
- Animated per-joint BCA scale channels are sampled and emitted separately; Saturn runtime helper computes dynamic T*R*S world matrices for `sat_skin_update_mesh`, without altering LibSaturn's pose ABI.
- `src/viewer.c` and root `CMakeLists.txt` wire generated private Mario C/H into the actual LibSaturn model, texture upload, skinning and canonical 3D scene API.
- **22/22 Python tests passed with local ASME Rev.00 ROM.** 450/450 top-level BMDs and 52/52 NARC BMDs parsed. Mario: 16 joints, 131 rigid vertices, 246 faces, 208 texture tiles, 53,248 texture-pixel bytes, 4 candidate BCA clips.
- Generated Mario C and scale runtime C passed host C11 syntax-only checks with equivalent LibSaturn declarations.

## Still pending

- **No native SH-2 link or emulator/hardware boot yet**. The dev environment lacks the toolchain and installed LibSaturn. Viewer is source integration, not demonstrated rendering.
- Texture UV and animation visual parity against the original DS and upstream PC oracle, head attachment and full material SRT/alpha/lighting correctness.
- Ten 1-bone high-scale skyboxes now export textured static C/H, but still need native renderer integration and screenshots.
- Scene collision / KCL/CLPS, Mario control/physics, real game loop and course content.
- Full sound and audio synchronization, calibrated rate/frame budget, memory pressure under level load and stress cases.

No copyrighted asset bytes were committed. Generated assets are local-only.

## 450/450 BMD gate closed (2026-11-10)

- The formerly rejected files data/vrbox/vr02.bmd through vr11.bmd use valid scaleShift=13, not malformed data.
- Dedicated camera-relative static conversion scales source extrema 58,982 to 115.1992 with uniform divisor 512, exactly representable in Saturn 16.16.
- All ten textures + face maps exported privately, without uncovered faces; ten C11 syntax checks passed against matching headers.
- **502/502** source BMD files now parse (450 NitroFS + 52 NARC); **22/22** local tests pass; no-ROM test run: 14 pass, 8 skip.

Pending: real SH-2/installed SDK link, emulator rendering/parity, material alpha and painter pass performance. See [SKYBOX_COVERAGE.md](SKYBOX_COVERAGE.md).

## Background scene integration (2026-11-10)

- `runtime/sm64ds_background.c/.h` implements camera-eye translation,
  static asset initialization and upload-once textures. It checks all face
  material mappings, capacity and overflow before scene submission.
- Skybox indexed8 palette defaults to **bank 1**; Mario is **bank 0**.
  LibSaturn model upload honors `asset->palette_base`.
- `src/viewer.c` supports optional `skybox_preview.c/.h` through CMake flag
  `SM64DS_ENABLE_SKYBOX=ON`, painter background pass 0/actor pass 1,
  a shared queue, trusted flush and live scene command statistics.
- **26/26 local tests passed** with the ASME image, including a host-compiled
  executable that tests camera-follow, palette guard, capacity admission and
  fixed-point overflow. Generated assets passed host C11 syntax checks.
- Example vr02 + Mario: **372 faces** and **67,328 texture pixel bytes**.
  These are host estimates; actual VDP1 command usage/SH-2 cycles are **not
  measured yet**.

Next acceptance: install SH-2 compiler/LibSaturn, build the private disc,
boot in Ymir, verify skybox image and pass ordering, compare against DS/PC
reference, and capture actual `g_sm64ds_viewer_stats` measurements.
See [BACKGROUND_RENDERING.md](BACKGROUND_RENDERING.md).

## Outdoor HLOD host packages (2026-11-10)

- Local ROM copied to ignored `private/sm64ds_usa.nds`; generated geometry,
  reports and material manifests remain under ignored `private/world-hlod/`.
- Fixed LibSaturn exact-duplicate welding and collapse remapping to retain
  source material ownership. Fixed clipping to avoid orphan vertices from
  rejected zero-area fragments, which falsely failed unsimplified garden
  geometry's surface-error gate.
- Castle passes aggressive quality gates with per-cell targets 512/384/256:
  eight cells, 207,836 bytes, total LOD face counts 1,951/1,881/1,459.
- Garden passes with targets 256/160/96: eight cells, 102,292 bytes, total
  LOD face counts 955/895/623. Both retain 100% partition source triangle and
  area coverage. Independent WLH1 binary read-back passed.
- **33/33 SM64 tests pass with the ROM**, plus **44/44 LibSaturn simplifier,
  quality and CLI tests** and **10/10 LibSaturn HLOD tests**, including the
  new material and orphan-vertex regressions. Quality thresholds were kept.

Next: post-simplification texture baking, bounded cell loading and scene
submission, then native build and emulator image/telemetry acceptance.
These host results do not establish runtime frame rate, image parity or
VRAM residency. See [HLOD measurements](WORLD_HLOD_INTEGRATION.md).
