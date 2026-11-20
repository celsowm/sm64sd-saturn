# Castle grounds walking prototype

`sm64ds_castle` supports camera-relative walking/running, jumping, landing,
wall/ceiling collision, camera rotation, pause and reset on the original
exterior. Original player states, CLPS surface behaviors, swimming, doors,
actors, sound and missions remain open.

## Build and play

```sh
./build-castle.sh                     # private/sm64ds_usa.nds
./play-castle.sh                      # Mednafen + local BIOS
```

The build script accepts an alternate ROM as its first argument. Defaults use
sibling `lib-saturn`, `saturn-prefix` and `saturn-tools/bin` directories.
Override `LIBSATURN_SOURCE`, `LIBSATURN_PREFIX`, `LIBSATURN_TOOLCHAIN_ROOT` and
`LIBSATURN_BIOS` as needed. No dependencies are downloaded.

The private disc is `build/castle/disc/sm64ds_castle.cue` with its sibling `.bin`.
Generated assets stay in ignored `private/castle/`. Mednafen can configure
controller 1 with Alt+Shift+1.

| Saturn control | Action |
| --- | --- |
| D-pad | Move relative to camera |
| A | Jump |
| Hold B | Run |
| L / R | Rotate camera |
| X | Toggle closer camera |
| C | Reset to lawn/bridge spawn |
| Start | Pause / resume |

## Implementation

The original full-detail exterior has 1,029 vertices and 1,337 faces. Visual
HLOD switching remains an optimization. Collision uses the independent original
KCL: 1,243 prisms, a 36×36 XZ grid and 15,531 nearby-face references. KCL positions
are at 1/64 DS unit and normals at 1/1024; its dummy prism directory overlaps
the final 16 bytes of the normal table.

World scale is 64 Saturn units per BMD unit and 0.064 per DS gameplay unit.
Median reconstructed KCL corner-to-BMD-vertex distance is below 0.04 Saturn
unit. KCL attributes are retained; CLPS behavior is not interpreted yet.

Simulation runs at 60 Hz from elapsed time with four movement substeps, floor
and step queries, wall sliding, ceiling response and void reset. Catch-up is
capped at 250 ms per draw. Camera line tests shorten its offset against KCL.
Original idle/walk/run/jump BCA clips drive the body. The separate gameplay
capped head (`ARCHIVE/arc0.narc:129`) attaches to body bone 15, following
upstream `daPly_c::Render`. The top-level `b_mario_head_cap` uses a different
size/orientation and must not be substituted for this attachment.

Palette banks are body 0, sky 1, castle 2, HUD 3, head 4. Resident pixel payloads
are castle 158,720 bytes, body 53,248, head 41,728 and sky 14,080, plus font.
The initial build uses about 641 KB initialized data and 344 KB BSS. High WRAM
is tight; reduce residency before adding more actors.

## Presentation and verification

Following the Tekken integration study, eye material SRT/mirroring and the
normal Mario gameplay clip bindings were corrected. Actor patches now use 24
texels per side; the terrain exporter falls back to 8 when corrected repeat
modes exceed its 192 KiB pixel budget. Castle bindings live in Low WRAM.
These supersede the initial pixel/memory measurements above. The updated ELF
contains 692,152 initialized bytes. A new close front capture (`mario-front.png`)
shows both blue eyes, with no panic or skipped faces. Full limb/polygon parity
against the DS source is still open. See [the integration study](TEKKEN_LIBSATURN_STUDY.md).

The scene explicitly uses `SAT_VDP1_FRAME_ON_SUBMIT`. Automatic field swaps
exposed partially drawn pictures in Mednafen: castle/sky appeared but Mario
and HUD commands late in the list were missing. The completed list must finish
before its framebuffer is presented. Ymir's synchronous captures alone did
not expose this problem.

The fix was visually verified in a fresh Mednafen session: Mario is upright,
the lawn and castle are present, and both HUD lines appear. The installed SDK
was rebuilt from the current local LibSaturn checkout before the final link.

The SH-2 executable and native disc build without static constructors.
**42/42 ROM-enabled tests pass**, including sanitized native C movement tests,
malformed KCL checks and real KCL/render alignment.

The initial 790-field Ymir controls route demonstrated jumping, landing, camera
rotation, pause/resume and reset: one jump, three landings, two resets, zero
skipped faces and no panic. A separate 650-field forward route recorded 1,422
wall responses and stopped at the closed castle doorway. Both reported zero
misaligned memory accesses. Full BIOS disc boot was also captured. These
initial counts precede the frame-presentation fix.

The final build was replayed after both presentation and gameplay-head fixes:
96 completed draws across 790 fields, 706 simulation ticks, one jump, three
landings and two resets. It ended grounded at the original spawn, unpaused,
with 820 commands in the sampled frame, zero skipped faces and no panic.
`final-acceptance.json` records the symbol-checked RAM results, and
`final-reset.png` records the final scene.

The full-detail scene drew roughly 8 frames/second on those routes. Geometry,
fill rate and texture quality need optimization. Bakes are low-resolution;
source lighting/translucency parity is incomplete. No physical Saturn test is
claimed. Captures, logs, RAM and JSON stay in `private/castle-capture/`.

`tests/castle_route.pad` is the controls timeline. Transitions last multiple
fields so polling between slow draws can see them. Validate matching ELF/RAM:

```sh
python3 tools/check_castle_capture.py \
  --wram private/castle-capture/final-controls-wram.bin --scenario controls
```

Upstream `tangosdev/sm64ds-decomp` reports 11,389/11,389 matched functions,
99.9% linked and 96.2% PC-ported at fetched revision `3b57210e6d`. It is the
reference for subsequent original movement and surface-behavior integration.

## Near-camera surface repair

Textured materials now supply an opaque average texture color to LibSaturn's
near-plane fallback. Previously these materials left `rgb555` at zero, so
textured faces that could not be drawn whole had no fallback and disappeared.
Castle, body, head and sky materials now provide this color. Transparent index
zero is excluded from the average; fully transparent tiles retain no fallback.
Clipped surfaces use flat color until textured clipping is available.

Validation: 42/42 ROM-enabled host tests and native castle disc build pass.
The host fixture checks average color, transparent texels and material binding.
This repair has not yet received a new emulator image comparison. Mario pose,
source material colors/lighting, two-sided material handling and painter
occlusion remain separate visual fidelity limitations.

## Current visual repair build

`build-castle.sh` uses LibSaturn's host plane splitter on a 64-unit grid
near the spawn (48-unit XZ radius), with finer grids on validated foreground
faces, including selected entrance walls split along height. The generated
scene has 1,665 faces and 1,530 castle texture tiles; original KCL remains
unchanged. This localized
split improves the front-camera case where large ground triangles covered
Mario's feet. The rest of the level remains unsplit and may still exhibit
painter ordering artifacts. Partial-alpha castle materials use a 50% VDP1
mesh approximation; exact DS alpha blending is not available on this path.
HUD labels now have opaque backing for legibility.

The 790-field Ymir controls route and 650-field wall route passed with this
split and no sampled skipped faces or panic. The split build produced 72
completed draws on the controls route, compared with 79 for the current
unsplit build in a separate replay; these are route measurements, not a
physical-hardware frame-rate claim. Fixed-camera and route captures are under
`private/visual-repair-baseline/`. Further source pose, texture, clipping and
camera coverage work remains open; see [the repair plan](VISUAL_REPAIR_PLAN.md).

Castle 8×8 face tiles now use a 4×4 sample grid per output texel, averaging
colors with alpha weighting before palette quantization. The source castle
walls contain repeating brick textures; point sampling produced strong
checker artifacts when those repeats collapsed into tiny face tiles. The
filtered `castle-filtered.png` fixed-camera capture shows a smoother wall than
`castle-source-order.png`; it remains low resolution and is not DS parity.
Texture pixel residency is 82,816 bytes across 1,294 castle tiles. The current
790-field Ymir route completed 72 draws with one jump, three landings, two
resets, zero sampled skipped faces and no panic.

## Frame-time baseline

`g_sm64ds_castle_profile` sums FRT ticks per main-loop stage over every
completed draw. `end` is `sat_end_frame`, which waits for the VDP1 to finish
the previous list, so it separates VDP1-bound from CPU-bound frames.
`tools/profile_castle_frames.py` replays `tests/castle_route.pad` (controls)
and `tests/castle_orbit.pad` (spawn camera orbit) in the probe, reads the
block from the High WRAM dump and ranks `--profile-pc` samples by symbol
after the boot/load fields. The wall route now warps into the 1F interior,
a different program, so it is not used here.

Probe baseline (injection boot, no SH-2 cache emulation, immediate division;
not a hardware measurement):

| Stage | controls ms/draw | orbit ms/draw |
| --- | ---: | ---: |
| VBlank wait | 13.1 | 11.9 |
| Simulation (6.6–6.7 steps) | 5.2 | 4.5 |
| Skin | 2.8 | 2.8 |
| Camera | 1.6 | 1.7 |
| Sky submit | 8.4 | 9.1 |
| Castle chunk submit | 29.2 | 23.9 |
| Props | 0.8 | 1.3 |
| Shadow/body/head submit | 4.7 | 5.0 |
| Support ordering | 6.1 | 5.7 |
| Scene flush | 50.1 | 43.3 |
| HUD | 1.1 | 1.1 |
| VDP1 wait (`end`) | 0.02 | 0.02 |
| **Total** | **123.1 (7.4 fields)** | **110.2 (6.6 fields)** |

The scene is CPU-bound on the Master SH-2: the VDP1 always finishes before
the next submit (zero draw waits). Flush plus castle and sky submission are
~75% of a draw; `project`, `submit_instance`, `instance_bounds_visible` and
64-bit division helpers lead the PC samples. Simulation catch-up is ~5 ms,
not the main cost. The trailing VBlank wait costs a further ~12 ms per draw.
Results are in `private/frame-profile/baseline/`.

### Phase 1 progress

The flush cost is dominated by fallback faces, not by the ~900 projected-safe
ones: with fallback emission disabled as an experiment, the flush fell from
48.9 to 8.6 ms (controls) and 43.2 to 8.3 ms (orbit). About 200–270 faces per
draw take the fallback, mostly textured faces with a corner past the 2× screen
sprite bound; they render as screen-clipped solid polygons (the flat green
ground near the camera).

| Change | controls ms/draw | orbit ms/draw |
| --- | ---: | ---: |
| LibSaturn HEAD, before changes | 118.6 | 110.3 |
| Textured fallback shares the sprite's depth test and projection | 110.7 | 100.3 |
| No VBlank wait at the top of the castle loop | 94.4 | 89.6 |

- LibSaturn `draw_textured_quad_or_solid` (indexed.cpp) replaces the
  textured attempt plus `sat_draw_polygon_quad3` in the flush. When every
  corner clears the near plane the near clip returns the quad unchanged, so
  the fallback screen-clips the sprite's own projection: same output, one
  depth test and one projection instead of two.
- The castle loop no longer calls `sat_wait_vblank` before each frame. In
  `SAT_VDP1_FRAME_ON_SUBMIT` mode `sat_end_frame` already waits for the
  previous swap. Late swaps rise (about 20 to 45 per route) because a list
  submitted just before a VBlank is shown one field later; draw waits and
  timeouts stay zero.

Remaining fallback emission is still ~26–29 ms per draw. Subdividing large
near-camera textured faces would remove both that cost and the untextured
ground, and is the larger remaining lever beside Slave SH-2 preparation of
the castle chunks (24–29 ms).
