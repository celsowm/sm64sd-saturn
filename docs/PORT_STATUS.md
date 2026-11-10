# Port status — 2026-11-10 (modular converter / textured viewer)

## Completed and locally checked

- Parser responsibilities split into 10 small Python modules under `tools/sm64ds_pipeline/`; CLI remains a thin orchestrator.
- Nintendo DS source formats 1-7 (including critical compressed 4×4 format 5) decode to RGBA; per-face VDP1 indexed8 canonical textures share one RGB555 palette.
- DS GX FIFO interpreter accepts known matrix and material-state operations, retains UVs and matrix-joint identities; unknown commands fail explicitly.
- BMD weighted matrix parsing and up-to-three-influence inverse-rest anchors added, with synthetic tests. This USA ROM contains 0 weighted BMD matrices across 502 inspected models.
- Animated per-joint BCA scale channels are sampled and emitted separately; Saturn runtime helper computes dynamic T*R*S world matrices for `sat_skin_update_mesh`, without altering LibSaturn's pose ABI.
- `src/viewer.c` and root `CMakeLists.txt` wire generated private Mario C/H into the actual LibSaturn model, texture upload, skinning and canonical 3D scene API.
- **17/17 Python tests passed with local ASME Rev.00 ROM.** 440 / 450 top-level source BMDs parsed. Mario: 16 joints, 131 rigid vertices, 246 faces, 208 texture tiles, 53,248 texture-pixel bytes, 4 candidate BCA clips.
- Generated Mario C and scale runtime C passed host C11 syntax-only checks with equivalent LibSaturn declarations.

## Still pending

- **No native SH-2 link or emulator/hardware boot yet**. The dev environment lacks the toolchain and installed LibSaturn. Viewer is source integration, not demonstrated rendering.
- Texture UV and animation visual parity against the original DS and upstream PC oracle, head attachment and full material SRT/alpha/lighting correctness.
- Ten 1-bone skyboxes with `scaleShift=13` need separate static background handling.
- Scene collision / KCL/CLPS, Mario control/physics, real game loop and course content.
- Full sound and audio synchronization, calibrated rate/frame budget, memory pressure under level load and stress cases.

No copyrighted asset bytes were committed. Generated assets are local-only.
