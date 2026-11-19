# Headless DS reference emulator

The local ARM64 macOS build is `build/dsperate/src/frontend/headless/dsperate-headless`,
from [DSperate](https://github.com/tzubertowski/TreeFrogUI_DSperate) revision
`39806498dfdd1cc07541b3f45deaf79d7d0ac7b2`, checked out in `private/dsperate`.
This is an interpreter build with the software renderer, not melonDS. Its
FreeBIOS and generated firmware permit direct ROM boot; their timing is not the
original BIOS timing. Independent emulator or hardware verification remains
necessary for visual conclusions. The local checkout has macOS fixes for
software AES selection, Mach-O embedded font sections and network byte order;
the build also links `libresolv`. JIT and NEON are disabled.

For example, capture frame 299 (frame numbers start at zero):

```sh
build/dsperate/src/frontend/headless/dsperate-headless private/sm64ds_usa.nds \
  --direct --frames 300 --dump-frames private/ds-frame.raw \
  --dump-from 299 --dump-count 1
python3 tools/ds_frame_to_png.py private/ds-frame.raw private/ds-frame.png
```

Each dumped frame consists of two 256×192 BGRA screens, top first. The converter
requires Pillow and supports `--frame N` for a multi-frame dump. The local clone
also accepts frame-based `--script FILE` inputs (`F buttons MASK 0 0 DURATION`,
`F touch X Y DURATION`, and `F poke32 ADDRESS VALUE`) and `--dump-save FILE`,
which writes the cartridge SRAM image at exit. Replay files from
`private/dsperate/tools/mkdsin.py`, `--trace FILE --max N`, `--dump-gpu-frame`,
frame hashes, save states, and `--peek32 ADDRESS` for guest ARM9 memory reads
are also available. See its
`src/frontend/headless/main.cpp` for the remaining options; this version does
not implement a useful `--help` and does not provide a GDB server.

`private/ds-mario-unlocked.sav` is a valid 8 KiB save image with Mario unlocked.
`private/ds-mario-playable.state` boots into the castle grounds as Mario, and
`private/ds-mario-spawn.state` is a settled back-facing view after a short
forward input. The Saturn clone exposes a symbol-stable `g_sm64ds_castle_stats`
block in High WRAM. `tools/check_castle_capture.py` decodes player position,
Mario facing, camera eye and target, FOV, camera yaw, frame counters and renderer
statistics from Ymir's High WRAM dump. Position and angle fields are also
emitted in human units alongside raw 16.16 values, so scripts can consume the
comparison state without manual debugger inspection.

For visual matching, `SM64DS_DIAG_FIXED_CAMERA=ON` fixes Mario at
`SM64DS_DIAG_X/Z` and his facing with `SM64DS_DIAG_FACING`; `SM64DS_DIAG_YAW`
and `SM64DS_DIAG_CAMERA_DISTANCE` configure the orbit camera. To reproduce a
measured camera pose directly, enable `SM64DS_DIAG_ABSOLUTE_CAMERA` and set
`SM64DS_DIAG_CAMERA_X/Y/Z` plus `SM64DS_DIAG_TARGET_X/Y/Z` in Saturn world
units. Absolute mode bypasses camera collision so coordinates remain exact.
Diagnostic captures default to the DS top screen's 4:3 aspect ratio and hide
the Saturn controls; set `SM64DS_DIAG_DS_ASPECT=OFF` or
`SM64DS_DIAG_SHOW_UI=ON` to change that. `SM64DS_DIAG_FRAME` fixes the
animation frame. Reconfigure the build directory when changing these CMake
cache values.

For a moving-camera diagnostic, enable `SM64DS_DIAG_ORBIT_PLAYER` together
with `SM64DS_DIAG_FIXED_CAMERA`, disable `SM64DS_DIAG_ABSOLUTE_CAMERA`, and
use L/R input. The player is reset to the chosen position each frame while the
normal collision-aware camera responds to input. `SM64DS_DIAG_YAW` sets the
initial yaw in this mode.

Build repeatable side-by-side sheets with
`tools/compare_castle_captures.py --pair LABEL DS.png SATURN.png --output
OUT.png`; repeat `--pair` for additional views. It uses the DS top display and
normalizes both views to one viewport size, with full-view, Mario, and
castle/ground rows for each pair.

`tools/inspect_ds_castle_state.py` locates the live Mario and camera actors in
the DS RAM dumps and reports their positions, orientation, and FOV. The three
captures `private/castle-comparison-fixed/ds-{rear,side,front}-ram.bin` come
from the same settled spawn save state. Mario stays at `(-1200, 254,
6242.0605)` DS units with facing 180° while the camera turns. `0.064` Saturn
units per DS unit maps that to `(-76.8, 16.256, 399.492)` in this clone. The
mapping has no additional translation; aligning to the old Saturn spawn would
put Mario on the wrong patch of ground.

Run `python3 tools/capture_castle_comparisons.py --bios PATH_TO_SATURN_BIOS`
to rebuild and capture three diagnostic views. The tool re-reads each DS RAM
dump with `inspect_ds_castle_state.py`, maps positions and camera eye/target
using the 0.064 scale with no translation, and configures the clone with the
same Mario facing, half-scale imported BMD model, matching 4:3 projection, and
46° FOV. It captures each Saturn frame and High WRAM, verifies the state using
the matching ELF, then writes
`private/castle-comparison-fixed/direct/comparisons.png` plus per-view
telemetry and mapping JSON. The side-by-side sheet uses the DS top screen and
includes full views, Mario crops, and ground/castle crops; the DS touch map is
excluded. Rear and side poses are visible. A flat foreground patch covers most
of Mario in the matched front capture. See the [visual repair plan](VISUAL_REPAIR_PLAN.md)
for the depth and clipping evidence and the next comparisons. These files and
ROM-derived outputs stay under `private/`.
