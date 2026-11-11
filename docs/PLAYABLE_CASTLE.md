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
sibling `lib-saturn`, `saturn-prefix-gc` and `saturn-tools/bin` directories.
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
