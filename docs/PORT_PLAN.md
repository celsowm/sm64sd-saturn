# Super Mario 64 DS -> Sega Saturn: Evidence-Based Port Plan

> Status: revised engineering plan (2026-11-10). This document specifies the *next implementation*, not features already delivered. As of this revision, this repository contains documentation and gitignore only; there is no bootable game, converter, test harness or measured port performance here.
>
> Target: stock Sega Saturn, LibSaturn as an **installed dependency**, and the decompiled SM64DS sources as the behavioral reference. The first deliverable is an independently reproducible **playable vertical slice**, not a claimed complete game port.

## 1. Decision summary

1. **Port behavior, not Nintendo DS hardware.** Compile a deliberately small set of the recovered game logic for SH-2 when practical. Put graphics, file I/O, input, audio and timing behind explicit platform seams. Do not attempt to emulate the Nintendo DS via memory-mapped-register no-ops on Saturn.
2. **Use LibSaturn's actual skeletal runtime.** It *does* provide skeletal clips, hierarchical joints, crossfades, CPU skinning (up to three influences), bounded character assets, scene integration and Master/Slave execution. Previous versions of this plan incorrectly said otherwise.
3. **Retain the game's 20.12 math semantics at the game boundary.** The game's Fix12i is a signed 20.12 value; LibSaturn's sat_fx16_t is signed 16.16. They have the same storage width but **not the same numeric representation**. Do not typedef one as the other.
4. **Do not load ARM9/DS overlay binaries on SH-2.** Overlays are source-level port/build units, not binary compatible Saturn executables. Initially statically link only the functions needed for the slice. Investigate a relocatable SH-2 overlay loader only after size measurements prove it necessary.
5. **Reuse the PC port as an oracle, not as a Saturn runtime.** The upstream native PC port already has model, animation, collision, filesystem and actor smoke tests. Reuse its fixtures and expected outcomes to validate host converters and SH-2 adapters.
6. **Respect VDP1's constraints.** Saturn has no general Z-buffer, no arbitrary texture UV interpolation after near-plane clipping, and finite command/texture capacity. Design LOD, material conversion, transparency, VDP2 backgrounds and near clipping from day one.
7. **Stock hardware first.** No RAM expansion cartridge, mandatory analog controller, mandatory dual-SH-2 parallelism, or CD-streamed music is allowed to block the first playable slice.

### Explicit exclusions for the first playable release

Do not port all 100+ DS overlays, all player states, minigames, touch-screen menus, full castle progression, every character, arbitrary DS graphics FIFO behavior or complete SDAT playback before a measurable walking/jumping scene exists. They are later work, each gated by evidence.

## 2. Verified references and source-of-truth policy

| Subject | Ground truth | How we use it |
|---|---|---|
| SM64DS source and assets | [tangosdev/sm64ds-decomp](https://github.com/tangosdev/sm64ds-decomp) | Original behavior, data layouts, source-level functions; local ROM-derived assets |
| Native PC port | [port/README.md](https://github.com/tangosdev/sm64ds-decomp/blob/main/port/README.md) | Smoke model/anim/KCL/actor, platform seam pattern, output oracle |
| BMD parser | [port/ntr/bmd.cpp](https://github.com/tangosdev/sm64ds-decomp/blob/main/port/ntr/bmd.cpp) | Starting point, **not** trusted without correction and differential tests |
| Asset catalog | [tools/asset_catalog.py](https://github.com/tangosdev/sm64ds-decomp/blob/main/tools/asset_catalog.py) | Generate local files.tsv, handles.tsv and generated headers |
| LibSaturn skeleton | [skeleton3d.h](https://github.com/celsowm/libsaturn/blob/main/include/saturn/skeleton3d.h) | Joint hierarchy, pose sampling, crossfade, root motion |
| LibSaturn skinning | [skin3d.h](https://github.com/celsowm/libsaturn/blob/main/include/saturn/skin3d.h) | Runtime CPU skinning, mesh updates and parallel jobs |
| Character assets | [character3d.h](https://github.com/celsowm/libsaturn/blob/main/include/saturn/character3d.h) | SKA1 decode/load, clip load, materials, resource ownership |
| Animation validation | [SKELETAL_ANIMATION_3D.md](https://github.com/celsowm/libsaturn/blob/main/docs/SKELETAL_ANIMATION_3D.md) | Demonstrated supported features and limits |
| Scene and renderer | [CHARACTER_RENDERING_3D.md](https://github.com/celsowm/libsaturn/blob/main/docs/CHARACTER_RENDERING_3D.md) | Painter queue, LOD, clip fallback, transparency limits |
| Collision | [collide3d.h](https://github.com/celsowm/libsaturn/blob/main/include/saturn/collide3d.h) | Bounded mesh/AABB/sphere queries; **not** 1:1 DS KCL semantics |
| Native build | [PACKAGING.md](https://github.com/celsowm/libsaturn/blob/main/docs/PACKAGING.md) | Installed CMake SDK, toolchain and disc builder |
| Local source ROM audit | [ROM_AUDIT.md](ROM_AUDIT.md) | Verified ASME Rev.00 metadata, nested NARC Mario model and initial course costs |

**Dependency policy:** Record tested upstream and LibSaturn commit SHAs in a machine-readable manifest. Keep LibSaturn separate and installed, not copied into this repo. Keep the upstream decomp under ignored .external/ (or obtain it with a documented fetch script). No unaudited remote HEAD changes in a release build. Read current header signatures before implementation: names and layouts here are references, not proof that unimplemented adapters exist.

**Copyright / provenance:** No ROM, retail Nintendo textures/music/models, extracted binary assets or generated derivative asset bundles in public commits. A legitimately obtained local dump is supplied by the developer. Tests must also work on original self-authored fixtures so CI does not need proprietary material. Review upstream license and the distinction between original decomp source and Nintendo-owned game content before distributing anything.

### 2.1 Verified ROM-specific constraints (local ASME Rev.00)

A read-only audit of the user-supplied USA Rev.00 image has now been completed; see **[ROM_AUDIT.md](ROM_AUDIT.md)** for provenance, exact IDs, compressed/raw byte counts and test candidates. This verifies **1,936 FAT entries (1,833 named NitroFS files and 103 unnamed ARM9 overlays)**, plus nested assets inside eight NARC containers. It does **not** yet verify the 0x80A-entry game runtime-handle table.

**Asset pipeline dependency change:** the usable 16-bone gameplay Mario model is **NOT** the top-level one-bone `data/player/b_mario_all.bmd`. The matching 16-bone model is `ARCHIVE/arc0.narc` (NitroFS ID **105**), **NARC index 131**: `data/player/mario_model.bmd`. Animation candidates `su_wait`, `su_walk`, `su_run`, `su_jump` are top-level NitroFS files **858/859/857/855**, respectively, and contain **16 BCA bone tracks** each. Thus **NARC traversal + LZ77 unpacking are Gate 1 prerequisites**, not late-stage extras. Initial rigid-joint skinning is favored by that model's zero weighted-matrix count; runtime visual/behavioral verification is still required.

The smallest BMD/KCL test is `test_map_b` (NitroFS 1537/1536, 3 KCL prisms). `main_garden` is a lighter first scenic-level candidate (BMD/KCL 1474/1472; 597 prisms) than `bombhei_map` (1291/1289; 930 prisms). These are **source-data observations only**; do not infer SH-2 or VDP1 performance from compressed ROM sizes.

## 3. Proposed architecture

~~~text
Original SM64DS behavior + upstream PC-port oracle
                 |
        Pure gameplay adaptation
   (math, state, interactions, camera rules)
                 |
        Thin SATURN platform HAL
   (time, input, files, collision, rendering, sound)
                 |
          LibSaturn public APIs
                 |
    SH-2 / VDP1 / VDP2 / SCSP / CD block

Host-side asset build (separate process):
Local .nds -> verified catalog -> NitroFS/NARC/LZ77 resolver -> BMD/BCA/KCL/texture/SDAT parsers
           -> validated intermediate representation
           -> Saturn mesh/skin/clip/texture/collider packages
           -> disc assets + manifest with offsets, sizes and hashes
~~~

The asset pipeline is host-only and must not require a giant runtime format parser. Keep DS-native logic separate from Saturn-native presentation. Make each seam testable on a PC host, then through a Saturn emulator.

Suggested folders (create when implementation starts):

~~~text
CMakeLists.txt                    # separate consumer of installed LibSaturn
cmake/                           # toolchain configuration, version validation
docs/PORT_PLAN.md
docs/PORT_STATUS.md              # achieved gates, evidence and real measurements
docs/RESOURCE_LEDGER.md          # measured memory/VRAM/audio ownership
src/
  game/                           # selected original semantics / adapted logic
  platform/saturn/                # input, time, asset loading, presentation, audio
  runtime/                        # actor state, level session, camera, game loop
  main.cpp                        # entry point, no global dynamic initialization
include/sm64sat/
tools/
  catalog.py                      # validate upstream catalog, metadata
  bmd_import.py                   # source format -> canonical model IR
  bca_import.py                   # source animation -> joints and clips
  kcl_import.py                   # source collision -> collision IR
  build_assets.py                 # IR -> bounded Saturn wire assets
  test_fixtures/                 # original non-Nintendo synthetic cases
tests/host/
tests/fixtures/                   # deterministic expected metadata and pose results
disc/                             # only self-authored or local generated assets
.external/                        # ignored upstream checkout
~~~

Keep ports/adapters local to this repository. General-purpose enhancements to LibSaturn must come with an isolated test and upstream change, not a copy-pasted private renderer.

## 4. Fundamental numeric and ABI correctness

### 4.1 Point representation: **critical correction**

- Game **Fix12i** uses 20.12 fixed point (unity 0x1000), as documented in upstream include/types.h.
- LibSaturn **sat_fx16_t** uses 16.16 fixed point (unity 0x10000), as documented in include/saturn/core.h.
- Converting a world coordinate from game units to Saturn fixed-point requires a **checked scale and shift**, not a cast. For equal world-unit scales, a raw 20.12 -> 16.16 conversion is value * 16 (with signed int64 intermediate and overflow check). Returning to 20.12 requires an explicitly selected rounding policy, not a reinterpret cast.
- Distinguish local unit conversion from world-scale normalization; a large DS course coordinate may not fit in a 16.16 intermediate. Adopt a per-level origin and a documented scene scale **before** converting, with signed bounds checked in 64 bits.
- The game's Vector3 may be memory-layout-compatible in simple cases, but it is **not** a direct semantic substitute for sat_vec3_t. Do not cast whole arrays or reinterpret game objects.
- DS matrix conventions, bone record order, handedness, axis direction, texture orientation, angle units and the Saturn's row-major 4x4 layout must be normalized explicitly and verified with nontrivial transforms.

First host gate: golden tests for zero, negative fractions, unity, bounds, overflow, vector dot/cross, transforms, bone parenting, rotation and inverse transforms. Compare movement outputs in native DS 20.12 before converting for rendering.

### 4.2 C++/SH-2 integration

- Start with an installed LibSaturn CMake consumer using C and C++; compile one small C++ object and confirm the link, map, startup and static-constructor checks.
- Avoid dynamic global initializers, default hidden heap allocations, exceptions and RTTI dependencies unless the runtime is deliberately extended and verified.
- Do not mass-rewrite upstream src/ or blindly rebuild the 24k-line player state source. Select a **link-closed source slice**, preserve behavior, isolate DS-specific code behind interfaces and report unresolved symbols by module.
- Keep simulation state deterministic, with explicit object ownership and no runtime vtable pointers assumed to have ARM binary layout.
- Define the simulation tick rate from observed original-game behavior, **not** from the Saturn's display refresh; decouple presentation from simulation and audio.

## 5. Character model and animation pipeline

### 5.1 Canonical intermediate representation

Build a typed host IR for mesh topology, unique vertices, face materials, texture/palette references, UVs, hierarchy, bind transforms, clip samples, events and per-vertex influences. Track exact source IDs and conversion warnings. Produce predictable binary assets; compiled C arrays are acceptable only for tiny fixtures.

**BMD import:**
- Reuse upstream header structures and the existing PC-port parser as starting evidence.
- Decode display-list operations and matrix references; do **not** assume each material is a simple triangle list.
- Verify bone-ID versus record-position mapping. The upstream PC-port documentation explicitly notes a known issue involving nonsequential bone IDs in the host parser; fix/validate independently rather than cloning its bug.
- Rebuild topology with deliberate quad handling/triangulation, seam duplication as required by materials, and strict index bounds.
- Resolve both top-level NitroFS assets **and nested NARC assets** by fully-qualified identity (outer file ID/path, inner index/path). Decode `LZ77`-prefixed streams before reading their BMD/BCA/KCL structures.
- Convert DS palette/texture formats offline into a tested LibSaturn indexed texture path. Document unsupported blend modes and UV transforms; never silently equate DS and VDP1 material models.

**BCA import and animation:** LibSaturn already supports:
- **sat_skeleton_asset_t**, **sat_skeleton_clip_t**, **sat_skel_clip_player_t**;
- **sat_clip_sample()**, **sat_skeleton_evaluate()**, **sat_skeleton_world_matrices()**;
- **sat_skin_asset_t**, **sat_skin_update_mesh()**, **sat_skin_deform_range()**;
- **sat_pose_fade_t** / joint-level pose blending;
- character SKA1 asset decoding and per-clip loading.

Convert BCA hierarchy and sample channels **offline** into the native joint/clip representation. Prefer runtime joint sampling and CPU skinning over baking each vertex of every frame. For vertex attachment, map a one-joint DS anchor to a rigid record; preserve true 2/3-weight blends if they exist. Never invent influences from an incomplete model parser. Validate parent-first sorting, inverse-bind/anchor math, loop timing, animation speed, topology and actor-owned scratch lifetime. The library's skinning format permits at most three influences per vertex: any source exceeding that requires explicit tested reduction or a different path.

**Profiling choices (make a measured decision):**

| Mode | CPU | RAM/asset cost | Decision condition |
|---|---|---|---|
| Runtime rigid/weighted skin, Master | Per-update joints + skin | Compact shared clips | Default first implementation |
| Runtime skin, Slave job | Similar total work, possible overlap | Task buffers and synchronization | Enable after serial equivalence and benefit measurement |
| Offline baked vertex animation | Decode fixed vertex poses | Potentially large clip assets | Fallback for a few exceptional models, never blanket policy |
| Rigid part transforms | Joint matrices, little deform | Per-part draw overhead | Good when source topology is rigid and material count is low |

Use **sat_skin_requirements()**, **sat_scene_requirements()** and explicit resource budgets; validate load-time skin and mesh with **sat_skin_validate()** / **sat_skin_validate_mesh()**. Pose vertices are per actor; texture/topology/clip data is shared. Release only after jobs and VDP1 users finish.

**Animation acceptance gate:** reproduce at least rest, idle, walk and jump (or a documented smaller set if a source clip is unavailable). Compare local joint matrices and vertex positions against a PC reference at named frames. Detect mirrored bones, inverted parent chains, wrong animation rates, loop discontinuities and visible texture seams. Capture pixel checkpoints on Ymir/Mednafen.

### 5.2 Static level geometry

Do not submit a whole DS course as one monolithic model. Partition and LOD geometry into bounded chunks; keep textures resident where practical, cull chunks with conservative bounds, and reserve command capacity for Mario/HUD. Use VDP2 for compatible backdrops/large 2D planes; gameplay-height geometry and depth-interacting obstacles remain VDP1. Do not claim a generic Z-buffer or unrestricted per-pixel alpha.

## 6. KCL collision and Mario movement

SM64DS KCL collision is not equivalent to LibSaturn's sphere body solver. LibSaturn's **sat_sphere_cast_mesh()** handles convex quad faces/edges/vertices; the **sat_sphere_cast_mesh_faces()** variant explicitly omits edge/corner-only collisions and initial overlap. A DS KCL is a different representation and its game-specific traversal/contact response matters.

**Decision sequence:**
1. Extract KCL into a host-only triangle/collision IR with normals, type flags, bounds and spatial structure.
2. Run upstream **smoke_clsn** and instrument ground/wall/ray queries at selected positions, on slopes, corners, ledges and moving surfaces. Generate reference hit sets/contact normals.
3. Implement the narrowest compatibility adapter that reproduces those results. Reuse LibSaturn collision/grid primitives **only where semantic equivalence is demonstrated**. If triangular KCL semantics require a small dedicated static-triangle solver, keep it locally isolated; do not force every KCL triangle into an invalid/degenerated quad.
4. Separate broad phase from narrow phase. Precompute a static acceleration structure offline where possible and avoid per-query heap allocations.
5. Preserve original Mario motion/state rules on top of the collision adapter. **sat_body3_step()** is useful for prototypes and independent objects, not an automatic replacement for the game's physics.

**Acceptance fixtures:** idle grounded, walking over a seam, slope limits, wall approach and wall kick, jump apex/landing, ledge fall, ceiling hit, corners, high-velocity crossing, initial overlap and moving-platform handoff. Compare state/position/velocity/contact flags after deterministic input sequences; state an explicit tolerance in original game units.

## 7. Game state, actors, input and camera

### 7.1 Actor framework

Implement a tiny runtime actor registry for the slice only: player, static terrain, collectible and one simple hazard/enemy. Reuse original high-level actor logic where isolated and link-closed. Do not assume a C struct with function pointers reproduces the C++ recovered class ABI. Keep stable spawn IDs, bounded pools, deterministic update order, explicit init/destroy and ownership-free render submission after simulation.

### 7.2 Player state scope

Progressive state port:
1. Idle / turn / walk / run.
2. Jump / fall / land.
3. Long jump and wall kick.
4. Ground pound / dive.
5. Swim, character-specific powers and advanced interactions **after the level slice**.

Treat names/function mappings as candidates until verified against recovered code; avoid inventing state indices or promising every source state will compile untouched. Keep original game behavior as reference, with regression tests.

### 7.3 Saturn controls

Start with a digital pad mapping table, documented in-game. Movement is camera-relative where supported. Preserve held/pressed/released semantics, keep diagonals stable, reserve enough buttons for run/jump/crouch/camera, and provide an intentional replacement for touch-screen-only actions. Additional 3D analog support is optional and must not change digital determinism.

The previous sample's ternary/bitwise-OR D-pad expression was not valid mapping logic; write and test a proper independent bit accumulator. Avoid relying on unproven symbolic button names in pseudocode.

### 7.4 Camera

Reuse the LibSaturn follow/orbit camera as the first viewport, then port **dCamera_c** behavior selectively. Account for walls/ceilings, distance clamp, recentering, safe camera position, interpolation and near-plane failures. Camera collision is a separate correctness gate; don't make the prototype appear playable only from one fixed angle.

## 8. Loading, audio, saving and content

**ROM catalog and packaging**
- Generate **files.tsv** and **handles.tsv** from a local ROM using the upstream asset_catalog tool; validate game region and manifest fingerprint before converting.
- Convert/decompress assets on the host, preserve a reproducible manifest of logical name, source ID, byte count, converted format, hash and dependencies.
- Build Saturn ISO/BIN/CUE using the **installed LibSaturn CMake packaging functions** (see PACKAGING.md). Do not invent an entirely new ISO writer or mistake gen_cue.py alone for a filesystem builder.
- Initial slice: load a small bounded set of assets on area entry, then no mandatory per-frame CD reads.
- Later: investigate region streaming, cache ownership and measured seek cost. Only consider a SH-2 relocatable overlay format with relocation tables, writable state, symbol linkage and unload rules **if** a static linked build cannot meet RAM constraints. ARM9 overlay bytes can never be jumped into directly.

**Audio**
- The installed **music.h** supports PCM8, PCM16BE, IMA ADPCM and CRI ADX with caller-owned workspace and a disc-stream scheduler. Do not treat a Nintendo SSEQ sequence as an ADX file; synthesize/render sequences with correct soundbanks offline, then encode.
- Start with a few self-authored PCM SFX. Add converted BGM later, with scheduler, voice policy and ring-buffer sizing (the actual music header defines allowable frames and workspace). Test loop continuity, read pressure, underruns, effect latency and game-load transitions. Use real library **sat_music_open / play / update / close** contract; do not assume a nonexistent automatic global music mixer.
- SCSP sound RAM is a shared resource: reserve driver/SFX/music resident buffers and count them, not merely the total file sizes.

**Save/HUD**
- First vertical slice uses volatile progress with no save requirement.
- Later use LibSaturn backup RAM APIs with a versioned Saturn-native schema; never reinterpret the DS save layout as a ready-to-write Saturn blob.
- The first HUD shows life/coin/goal and debug toggles. BMG localization, more characters and touchscreen-style menus belong in later work.

## 9. Hardware and resource ledger

This is a **physical capacity overview**, not an allocation claim. LibSaturn linker/startup/VRAM ownership must be checked independently.

| Resource | Baseline capacity | Budget discipline |
|---|---:|---|
| WRAM High | 1 MiB (0x06000000..0x060FFFFF) | Code, globals, stacks and hot state; account for startup/vector reservations |
| WRAM Low | 1 MiB (0x00200000..0x002FFFFF) | Large cold data and buffers; profile bus/worker access |
| VDP1 VRAM | 512 KiB | Command lists, texture pixels, Gouraud tables, required double buffering |
| VDP2 VRAM | 512 KiB | BG/rotation tilemaps, tile pixels, coefficient data; bank/cycle-pattern limits apply |
| Color RAM | 4 KiB | Palette/color mode and ownership, not automatically all usable at once |
| SCSP Sound RAM | 512 KiB | Driver, voices, ring buffers and SFX |
| CD-ROM | Disc capacity is not live RAM | Load latency, seek costs and scheduler constraints |

**Correction to the prior plan:** the address region 0x25E80000..0x25EFFFFF must not be counted as a second independent 512 KiB of VDP2 storage. Also, the native main program is *not* free to fill all of WRAM High: vectors, runtime control, stacks and program image take space. See LibSaturn's **tools/memory_layout.py** and installed linker script.

Before attempting a course, record:
- Linker map: code/rodata/data/BSS, Master/Slave stacks, WRAM High/Low peaks.
- Asset residency: shared model/skin/clip bytes, per-actor vertex/pose/scratch, CD staging, collision grid.
- VDP1: texture residency, commands drawn/queued, face/LOD rejection, draw-end pacing.
- VDP2: allocation by bank, timing/cycle pattern, CRAM palette footprint.
- SCSP: voice allocations, music workspace, underruns.
- Timings **separately**: fixed ticks, new displayed images, VBlank, render preparation, skin, collision, command submission/draw completion, music update and CD reads.

No speculative FPS percentages. **30 displayed frames/s at 320x224** is an *initial stretch target*, not a result. A faithful playable 20-ish FPS slice with a measured 60 Hz update loop can be useful; preserve simulation/update determinism, measure actual cadence, and never call submissions/s "FPS". Test on stock-console configuration before any optional expansion. Parallel execution is an optimization with a testable speedup, not a phase-0 dependency.

## 10. Delivery plan with hard gates

### Gate 0 — reproducible boot and source baseline (first milestone)

**Build:** initialize a minimal separate CMake C/C++ project linking installed **LibSaturn::Saturn**, boot a self-authored scene on Mednafen and Ymir, read input, render a quad and print error diagnostics. Pin LibSaturn and upstream commits. Confirm no static constructor/heap/startup surprises.

**Evidence:** successful build commands, output file size, linker map, emulator boot record and screenshot. Do not call it done merely because an example in another repository builds.

### Gate 1 — numeric and format oracles

**Build:** local-only NitroFS **and NARC** parsing, game-specific LZ77 unpacking and validated manifest; native-to-fixed math adapter; independent host tests; model IR from `test_map_b` plus a *synthetic* geometry fixture in CI. Then resolve **`ARCHIVE/arc0.narc:131`** and inspect Mario's 16-bone hierarchy. Fix and prove bone record-ID mapping. Compare parsed materials/matrices/geometry to the upstream PC smoke-model path.

**Pass:** tested 20.12↔16.16 behavior, exact source asset identity, bounded parser, reproducible topology and diagnostic errors for unsupported commands.

### Gate 2 — Mario appears on Saturn

**Build:** render the actual Mario model at `arc0.narc:131` from local converted assets, and test its separate head attachment where applicable. Do **not** substitute `b_mario_all.bmd` without evidence. Prove indexed textures, palette ownership, face winding, near clipping, camera orbit and object-level culling. Keep an original test character as the CI fixture.

**Pass:** captured, correctly textured Mario from front/side/back; no reversed faces, out-of-bounds uploads or unaccounted VDP1 command rejections.

### Gate 3 — actual runtime skeletal animation

**Build:** import the verified **16-bone** Mario hierarchy + 16-track `su_wait`/`su_walk`/`su_run`/`su_jump` BCA candidates, export skeleton/rigid skin/native clips or SKA1, sample joints on Saturn, deform into actor-owned vertices and submit scene instance. First verify these are the gameplay-selected clips against original source resource bindings. Serial Master first; optionally compare a parallel Slave variant. Do not make per-frame baked vertices the default.

**Pass:** rest/walk/jump samples match golden source poses to stated tolerances; valid render and bounded pose memory; deterministic clip switching; independent actor instances.

### Gate 4 — Mario locomotion on a simple graybox

**Build:** adapter for KCL/terrain collision semantics, selected original player states, Saturn pad input and third-person follow camera. One platform route, one slope, one wall, one ceiling and one ledge; static collision data is enough.

**Pass:** reproducible movement traces with walking, running, jumping, landing, wall contact and ledge handling; camera never passes through the principal test obstruction; 60 Hz simulation remains consistent under dropped draws.

### Gate 5 — small playable course

**Build:** prefer the measured smaller **`main_garden`** as the initial scenic candidate, then compare to **`bombhei_map`** (Bob-omb Battlefield) using *converted* geometry/texture/VRAM/command costs before fixing the playable course. Stream or preload course chunks as required. Add a coin, one enemy/hazard, a collectible goal, health/goal HUD, restart and victory state. Exercise actor lifecycle and scene depth ordering.

**Pass:** full unattended input replay from spawn to goal on Ymir/Mednafen; no dead end; screenshots of several camera angles; complete memory and per-frame timing report.

### Gate 6 — production paths

**Build:** level-entry CD asset loader, resilient cache/resource ownership, SFX, background music using the real scheduler, eventual save and menus. Implement optional quality modes/LOD using measurements; ensure collision/world logic is unchanged by visual LOD.

**Pass:** multiple level reloads and failed-load recovery; no asset lifetime violation; no audio underruns in the reference scenario; correct backup RAM round-trip if save is enabled.

### Gate 7 — extended game coverage (only after Gate 5/6)

Add player states and characters, more actors, courses, scripts, inter-level transitions, UI and systems incrementally. Use a tracking matrix per dependency and regression suite. Keep minigames and touch-specific features separate. Any dynamic SH-2 overlay system requires a memory/streaming feasibility experiment **before** implementation.

### Stop/go rules

At the end of each gate, publish **PORT_STATUS.md**: source revision, commands run, tests passed/failed, screenshots/hashes, RAM and frame metrics, unresolved issues and exact next gate. If a required behavior fails, fix the seam before expanding actor or asset coverage. Avoid making a new generalized engine subsystem to work around a single unverified conversion error.

## 11. Test strategy

| Test layer | Must prove | Can run without ROM? |
|---|---|---|
| Converter unit tests | malformed input, endianness, index/capacity bounds, decode determinism | Yes: original synthetic fixtures |
| Numeric/ABI tests | fixed-point conversions, matrix and C/C++ boundaries | Yes |
| Source-oracle tests | BMD/BCA/actor/KCL parity with upstream native PC port | Developer local ROM only |
| LibSaturn host tests | skeleton validation, skin mesh, scene capacity and ownership | Yes |
| Emulator deterministic tests | boot, controls, state traces, image checkpoints, CD/resource lifecycle | Self-authored fixture yes; Mario-specific local only |
| Performance probes | master/slave work, draw completion, WRAM/VRAM occupancy, music underruns | Synthetic stress tests yes |

Host equivalence should compare structured pose/collision/game state, not only screenshots. Visual acceptance must inspect actual emulator frames; a matching command count is not visual proof. Maintain a stable seed, fixed input timeline, local asset hash and reference screenshots. If physical Saturn validation is not run, explicitly mark that evidence missing rather than implying a hardware result.

## 12. Prioritized first implementation tasks

1. Add CMake/installed-LibSaturn consumer project and bootable original fixture.
2. Add a README with setup, SH-2 toolchain, pinned dependency manifest and local ROM policy.
3. Add format/numeric host tests; establish the fixed-point boundary.
4. Generate one local asset catalog and verify a BMD against upstream PC-port output.
5. Build BMD IR + indexed materials and display the first converted model.
6. Build BCA hierarchy/clip/skin IR and drive LibSaturn runtime skinning.
7. Add KCL oracle and Mario's minimal locomotion; move to a reproducible level slice.
8. Measure memory and image pacing *before* widening scope.

**Definition of success:** a developer can clone the clean repository, build a stock-Saturn bootable fixture without Nintendo assets, optionally provide their own ROM locally, and reproduce a small playable Mario scene with documented correct motion, animation, collision, controlled resource ownership and measured presentation performance. The full game port is a roadmap after that proof, not an assumption.
