# Port status — 2026-11-10

## Verified local work

- The repository has a Python converter in `tools/sm64ds_convert.py` and ROM-free + optional local-ROM tests in `tests/test_converter.py`.
- Local user-supplied ASME Rev.00 input was identified and verified by SHA-256 in `docs/ROM_AUDIT.md`.
- Local importer resolved `ARCHIVE/arc0.narc:131`, parsed **16** bones, **131** rigid unique vertex anchors and **246** native quad/degenerate-quad face records.
- Four animation candidates were decoded: idle (120 frames), walk (30), run (30), jump (11), each with 16 joint tracks.
- **11/11 Python tests passed** with `SM64DS_ROM` supplied locally. Without the ROM, the suite ran **7 passed + 4 skipped**.
- The generated untextured C preview passed a **host C syntax-only check** against matching stub declarations. This is **not** a real LibSaturn link/ABI test.

## Not done

- No SH-2 toolchain compilation or link using installed LibSaturn.
- No emulator boot, screenshot, pixel parity, VDP1 rendering or native performance measurement.
- No source-texture, palette, per-face UV baking, weighted BMD matrices, KCL parity or gameplay logic.
- BCA playback frequency assumed 30 Hz as a configurable importer setting; the original game's state timings have not yet been cross-checked.
- No asset blobs are committed to the repository.

## Next blocking gates

1. Connect generated `sat_model_asset_t` + `sat_skeleton_asset_t` + `sat_skin_asset_t` + `sat_skeleton_clip_t` to a **real LibSaturn scene** and run native API validation.
2. Use source reference/harness for bone matrix comparison at fixed animation frames; correct any visual/pose divergence.
3. Implement VDP1 indexed texture baking with transparent index handling and predictable texture-memory ownership, then move to runtime character rendering.
4. Investigate KCL primitive tests and original player behavior after rendering is proven.

Source/measurements are development evidence only, not an assertion that Mario is yet playable on Saturn.
