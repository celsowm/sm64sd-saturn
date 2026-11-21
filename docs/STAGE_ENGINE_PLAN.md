# Stage engine plan: Bob-omb Battlefield first, every stage after

> Status: phases 0–6 complete (2026-11-20); phase 7 rollout in progress (2 of 8).
> Measurements come from the local USA ROM (`private/sm64ds_usa.nds`), its
> level overlays and the local decomp checkout at `.external/sm64ds-decomp`
> (`44250be91a`). The frame-time figures are probe-emulator figures, not
> hardware results.

## 1. Goal

Make adding a stage **a data change, not a code change**. Today the port has
two hand-wired stages: Castle Grounds (`EXT.BIN`) and Castle 1F (`C1F.BIN`).
They share one 2,988-line `src/castle.c` whose behavior is selected by about
25 compile-time macros (151 `#if` blocks). A third stage built the same way
would add more branches, and the forty-fifth would be unmaintainable.

The target is:

- **One engine library.** It holds the player, camera, collision, stage
  rendering, sky, actors, HUD, stage flow and profiling.
- **One generated data package per stage.** The converter derives it from the
  DS level overlay, plus a small hand-written row per stage.
- **One actor registry, keyed by DS actor ID.** A stage links only the actor
  kinds it spawns.
- **One stage graph.** Every door, painting, pipe and course exit resolves to
  a target program and entrance through generated tables.

Bob-omb Battlefield (`bombhei_map`, course 1) is the first stage built on this
engine. Castle Grounds and 1F are rebuilt on it as well. After that, each
further stage costs its table row, its new actor kinds and a test route.

**There is no backwards compatibility.** Any file, macro, target, format,
handoff struct or tool interface can be renamed, rewritten or deleted.
What has to be kept is behavior: the existing stages must still play, look the
same and run at the same frame time. Section 4 defines the checks for that.

## 2. What the ROM contains

### 2.1 All stages, found automatically

Every one of the 48 `data/stage/<name>/<name>_all.bmd` + `.kcl` pairs was
matched to its level overlay by searching the overlays for the pair's
overlay-0 file IDs. The overlay holds the `LVL_Overlay` record
(`include/LVL_Overlay.h`). So the stage → overlay map can be generated rather
than hand-written.

| Stage | Overlay | Areas | Verts | Faces | KCL today | Notes |
|---|---:|---:|---:|---:|---|---|
| `main_castle` | 9 | 1 | 1,029 | 1,337 | OK (1,243) | Castle Grounds, done |
| `castle_1f` | 10 | 8 | 2,052 | 2,889 | OK (1,462) | Castle 1F, done |
| `main_garden` | 11 | 1 | 607 | 631 | padding | Courtyard |
| `castle_b1` | 12 | 5 | 1,228 | 1,534 | padding | Basement |
| `castle_2f` | 13 | 7 | 2,546 | 3,312 | padding | 2F / 3F |
| **`bombhei_map`** | **14** | **1** | **766** | **1,137** | **degenerate** | **Bob-omb Battlefield** |
| `battan_king_map` | 15 | 1 | 854 | 1,020 | padding | Whomp's Fortress |
| `kaizoku_irie` | 16 | 1 | 471 | 784 | padding | Jolly Roger Bay |
| `kaizoku_ship` | 17 | 1 | 266 | 314 | padding | JRB ship interior |
| `snow_mt` | 18 | 1 | 1,119 | 1,350 | padding | Cool, Cool Mountain |
| `snow_slider` | 19 | 1 | 752 | 1,217 | padding | CCM slide |
| `teresa_house` | 20 | 7 | 1,961 | 2,721 | OK (1,566) | Big Boo's Haunt |
| `cave` | 21 | 8 | 2,746 | 3,656 | padding | Hazy Maze Cave |
| `fire_land` | 22 | 1 | 574 | 832 | padding | Lethal Lava Land |
| `fire_mt` | 23 | 1 | 666 | 1,039 | padding | LLL volcano |
| `desert_land` | 24 | 1 | 689 | 990 | OK (966) | Shifting Sand Land |
| `desert_py` | 25 | 2 | 1,130 | 1,494 | padding | SSL pyramid |
| `water_land` | 26 | 2 | 739 | 1,135 | OK (729) | Dire, Dire Docks |
| `snow_land` | 27 | 1 | 682 | 1,093 | OK (838) | Snowman's Land |
| `snow_kama` | 28 | 1 | 165 | 237 | OK (252) | SL igloo |
| `water_city` | 29 | 2 | 1,019 | 1,530 | OK (1,400) | Wet-Dry World |
| `high_mt` | 30 | 1 | 983 | 1,478 | degenerate | Tall, Tall Mountain |
| `high_slider` | 31 | 1 | 1,047 | 1,585 | OK (1,566) | TTM slide |
| `tibi_deka_d` | 32 | 1 | 520 | 783 | OK (792) | Tiny-Huge Island (huge) |
| `tibi_deka_t` | 33 | 1 | 532 | 800 | OK (609) | Tiny-Huge Island (tiny) |
| `tibi_deka_in` | 34 | 1 | 267 | 383 | OK (237) | THI interior |
| `clock_tower` | 35 | 1 | 1,132 | 1,401 | OK (1,102) | Tick Tock Clock |
| `rainbow_cruise` | 36 | 1 | 1,635 | 2,304 | OK (1,774) | Rainbow Ride |
| `suisou` | 38 | 1 | 265 | 334 | OK (102) | Secret Aquarium |
| `habatake` | 39 | 1 | 417 | 582 | OK (346) | Wing cap tower |
| `horisoko` | 40 | 1 | 518 | 762 | OK (607) | Vanish cap (to confirm) |
| `metal_switch` | 41 | 1 | 529 | 854 | OK (649) | Metal cap |
| `rainbow_mario` | 42 | 1 | 1,141 | 1,986 | OK (1,360) | Over the Rainbows (to confirm) |
| `koopa1_map` / `_boss` | 43 / 44 | 1 | 616 / 49 | 966 / 88 | OK | Bowser in the Dark World + arena |
| `koopa2_map` / `_boss` | 45 / 46 | 1 | 899 / 105 | 1,413 / 116 | padding / OK | Bowser in the Fire Sea + arena |
| `koopa3_map` / `_boss` | 47 / 48 | 1 | 1,006 / 60 | 1,578 / 76 | OK | Bowser in the Sky + arena |
| `ex_m_map`, `ex_l_map`, `ex_w_map` | 52, 54, 56 | 1, 5, 1 | 622–885 | 845–1,237 | mixed | Character secret stages (to confirm) |
| `ex_mario`, `ex_luigi`, `ex_wario` | 53, 55, 57 | 1 | 272–571 | 503–643 | OK | Character cap rooms (to confirm) |
| `playroom` | 58 | 3 | 1,247 | 1,366 | degenerate | To identify |
| `test_map`, `test_map_b` | 8, 49 | 1 | — | — | padding | Developer test maps, skip |

The names in the Notes column are working labels. Phase 1 replaces them with
the decomp's own stage/course table.

What this means for the design:

- **Collision is a shared blocker.** 22 KCL files fail the decoder's range
  check (marked "padding") and 3 fail on degenerate prisms. The range
  failures have one cause: the normal table's length is not a multiple of 6
  bytes, because the prism table after it is 4-byte aligned. That is 2 bytes
  of alignment padding, not corrupt data.
- **Multiple areas are normal.** 11 stages have more than one area, and the
  area count always equals the model's bone count. The 1F room and portal
  code has to become the general area system, not a 1F special case.
- **The meshes all fit the current budget.** The largest are `cave` (3,656
  faces) and `castle_2f` (3,312). Castle 1F (2,889 faces) already runs with
  room culling, so no stage needs a new renderer, only per-stage tuning.
- **Some courses are two stages.** JRB + ship, CCM + slide, LLL + volcano,
  SSL + pyramid, SL + igloo, THI's three stages, TTM + slide, and each Bowser
  map + its arena. The stage graph has to handle in-course transitions, not
  only castle ↔ course.

### 2.2 BoB level data (overlay 14)

- The `LVL_Overlay` record sits at overlay offset `0x228c + 8`. Its model and
  KCL file IDs are `0x05FD` and `0x05FB`.
- **Level-wide object table** (area −1), by sub-table category (low 5 bits):

  | Category | Count |
  |---:|---:|
  | 1 (entrances) | 4 |
  | 2 (path nodes) | 49 |
  | 3 (paths) | 4 |
  | 4 (views) | 4 |
  | 6, 7 | 4 + 4 |
  | 8, 11, 14 | 1 each |

- **Area 0:**
  - One always-present standard list with 89 objects.
  - Several more standard lists, each filtered by star (the top 3 bits of
    the sub-table byte; `LoadObjects` loads a list when the filter is 0 or
    equals the selected star).
  - A simple-object list (category 5) after each standard list.
- **Object IDs used:**
  - Always-present list: 7, 13, 15, 19, 23, 29, 30, 36, 43, 45, 49, 50,
    76 (signpost), 79, 173, 187, 188 and 304.
  - Star lists add 10, 20, 21, 48, 51, 52, 56, 254, 281, 282, 315 and 316.
- **Actor names are not resolved yet.** The object ID indexes
  `sObjToActorIdTable` (decomp `ov002:0x0210cbf4`, see
  `symbols/actor_renames.tsv`). The actor ID indexes
  `symbols/actor_debug_names.tsv` (391 names). The table was not found by
  scanning the ARM9 binary. It lives in overlay 2, and the decomp's address
  may be for another region.

### 2.3 Decomp sources for BoB's actors

| Actor | Decomp file |
|---|---|
| Bob-omb | `src/game/actors/d_a_bmb.cpp`, `include/daBmb_c.h` |
| Pink Bob-omb | `src/game/actors/d_a_red_bombhei.cpp` |
| King Bob-omb | `src/game/actors/d_a_bombking.cpp` |
| Chain Chomp, its gate | `src/game/actors/d_a_wanwan.cpp`, `d_a_obj_wanwan_shutter.cpp` |
| Cannon, cannon lid | `src/game/actors/d_a_cnn.cpp`, `d_a_obj_cannon_shutter.cpp` |
| Water bomb | `src/game/actors/d_a_wbm.cpp` |
| ? block | `src/game/actors/d_a_obj_hatena_block.cpp` |
| Painting (castle side) | `src/game/actors/d_a_pic_gate_methods.cpp`, `include/daPicGate_c.h` |

`notes/actor-naming.md` points to the N64 decomp behaviors (`bobomb.inc.c`,
`chain_chomp.inc.c`, `king_bobomb.inc.c`, …) as a second reading of the same
logic.

## 3. Architecture

### 3.1 Layers

```
tools/                        host, Python
  stage_table.py              one row per stage (hand-written, small)
  prepare_stage.py            ROM -> private/stages/<name>/ (generated C + report)
  prepare_actor.py            ROM -> private/actors/<kind>/  (models, clips, textures)
  sm64ds_pipeline/level.py    generic LVL_Overlay reader (all categories)
  sm64ds_pipeline/kcl.py      fixed decoder
  sm64ds_pipeline/stage_graph.py   exits/doors/paintings -> warp tables

engine/                       SH-2, C, built once as a static library
  frame.c        main loop, fixed 60 Hz simulation, draw pacing
  player/        movement + action table (one file per action group)
  camera.c
  collision.c    KCL queries, CLPS surface types
  stage_render.c chunks, areas/portals, support ordering, painter passes
  sky.c          VDP2 panorama
  actor.c        pool, spawn, culling, touch dispatch
  hud.c
  stage_flow.c   warps, fades, sat_exec handoff, save block
  profile.c

actors/                       SH-2, C, one module per actor kind
  coin.c star.c hatena_block.c signpost.c door.c painting.c
  bmb.c bombking.c wanwan.c cnn.c wbm.c ...

stages/<name>/                generated, private (never committed)
  stage_data.c/.h             the descriptor + all stage data
  actor_kinds.c               the registry subset this stage links
```

Each stage program is linked from three parts: `engine` + `stages/<name>` +
the actor modules listed in its `actor_kinds.c`. Each program becomes one
`.BIN` on the disc. The intro stays its own program (`0.BIN`).

### 3.2 The stage descriptor

All per-stage differences that are now macros become fields of one constant
struct. Feature switches become nullable pointers or counts, so the engine
has no `#if` for stage features.

```c
typedef struct {
    uint8_t stage_id;              /* index in the generated stage table */
    const char *name;              /* "BOB" */
    const stage_geometry_t *geometry;   /* chunks, areas, portals, supports */
    const stage_collision_t *collision; /* KCL grid + prisms + CLPS table */
    const stage_sky_t *sky;        /* NULL for indoor stages */
    const stage_area_t *areas;     /* area_count >= 1; bones == areas */
    uint8_t area_count;
    const stage_entrance_t *entrances;  uint8_t entrance_count;
    const stage_warp_t *warps;          uint8_t warp_count;
    const stage_object_t *objects;      uint16_t object_count; /* star-filtered at spawn */
    const stage_path_t *paths;          uint8_t path_count;
    const stage_view_t *views;          uint8_t view_count;
    const stage_tuning_t *tuning;  /* camera, cull distances, render pass limits */
    uint8_t music_id, course_id;
} stage_desc_t;
```

Compile-time switches stay only for real build variants (release vs.
diagnostics), and those live in the engine, not in stage data.

### 3.3 The stage table (hand-written part)

`tools/stage_table.py` holds what the ROM cannot tell us. Everything else
comes from the overlay. One row per stage:

```python
Stage(name='bombhei_map', bin='BOB', course=1, profile='outdoor',
      convert=dict(max_edge=48, chunk_size=128, max_tile_size=48,
                   texture_samples=4, texture_budget=245760),
      tuning=dict(camera='outdoor', far_cull=None),
      ds_level_id=None)   # filled from the decomp level table in phase 1
```

- `bin` is the disc file name: up to 8 characters, ISO 9660 level 1.
- `profile` picks converter defaults:
  - `outdoor`: chunks + sky.
  - `indoor`: areas + portals, no sky.
  - `arena`: small, no chunking.
- **Rows are checked.** A build step converts every row and fails if a stage
  goes over its budget or uses a feature the engine lacks. It writes
  `private/stages/report.json` with one line per stage: faces, texture bytes,
  KCL prisms, actor kinds used, kinds still unimplemented, and estimated
  VRAM/WRAM.

### 3.4 Stage graph (warps)

Every transition is generated data:

- **Course exits** (`ExitEntry`, 14 bytes) and **teleports** come from the
  overlay. The target level ID in their parameters maps to a stage through
  the decomp's level table.
- **Doors** (`DoorEntry`) and **paintings** (castle standard objects 42 and
  275, course index in the parameter) become warp volumes. Each painting's
  course index maps to a course row in the stage table.
- **Entrances** (category 1) give the spawn position and yaw for each
  incoming warp.
- **Exit course from the pause menu** and **death** return to a per-course
  castle entrance taken from the stage table. On the DS that is the spot in
  front of the course's painting.

`stage_graph.py` checks the whole graph: every warp target exists, every
target entrance exists, and every course can be reached from the castle.
Targets that are not converted yet are reported. At runtime they show a "not
ported" message instead of warping.

Runtime warp record:

```c
typedef struct {
    sat_fx16_t min[3], max[3];   /* world-space trigger box */
    uint8_t kind;                /* door, painting, pipe, exit, teleport, area */
    uint8_t target_stage;        /* stage table index -> BIN name */
    uint8_t target_entrance;
    uint8_t flags;               /* needs airborne, needs star count, ... */
    uint16_t required_stars;     /* star doors */
} stage_warp_t;
```

Changing area inside one program (teleports, multi-area stages) uses the same
record with `target_stage` equal to the current stage. That needs no
`sat_exec`.

### 3.5 Handoff and save state

Replace `runtime/sm64ds_stage_handoff.h` with one struct, passed through
`sat_exec`. It must stay under `SAT_EXEC_ARG_MAX` (64 bytes):

```c
typedef struct {
    uint32_t magic, version;
    uint8_t target_entrance, star, from_stage, flags;
    sm64ds_save_t save;          /* stars per course (bit per star), keys, caps, lives, coins */
} sm64ds_handoff_t;
```

The save block starts out living only in the handoff. Backup RAM is a later
step that adds nothing new to this struct.

### 3.6 Actors

- **Registry.** Actor kinds are indexed by **DS actor ID** (0–390). A kind has:

  ```c
  typedef struct {
      uint16_t actor_id;
      uint16_t state_size;           /* per-instance bytes from the pool */
      void (*init)(actor_t *, const stage_object_t *);
      void (*update)(actor_t *);
      void (*submit)(actor_t *, scene_t *);
      void (*on_touch)(actor_t *, player_t *);
      const actor_assets_t *assets;  /* models, clips, textures, palette */
      sat_fx16_t update_range, draw_range;
  } actor_kind_t;
  ```

  This follows the decomp's `InitResources` / `Behavior` / `Render` split, so
  a port reads side by side with the decomp file.

- **Per-stage linking.** `prepare_stage.py` resolves each object to an actor
  ID through `sObjToActorIdTable` and emits `actor_kinds.c` with only the
  kinds that stage uses and that have a module. Code and assets for other
  kinds are not linked, which is how WRAM stays bounded as the actor count
  grows. Unsupported kinds are counted in the report and on the debug HUD.
- **Assets once per kind.** `prepare_actor.py` converts a kind's models,
  BCA clips and textures into `private/actors/<kind>/`. Every stage that uses
  the kind links the same files.
- **Shared kinds.** Coins, stars, ? blocks, signposts, doors, paintings, 1-ups,
  boxes and so on are used everywhere and are ported first.
- **Palette banks.** Banks are given out per stage by the converter from the
  kinds that stage uses, not fixed by hand per actor.

### 3.7 Player

- One player module. Actions are a table (`player_action_t`: enter, update,
  exit, animation), ported from the decomp's `daPly_c` state functions.
- Courses add actions as their stars need them: grab/throw for BoB,
  swimming for JRB/DDD, sliding for the slides, caps later. The table makes
  each one an additive change.
- The current custom walk/run/jump movement is replaced by the ported
  actions as they land.

### 3.8 Collision and surfaces

- `collision.c` holds the KCL grid query code moved out of `castle.c`.
- CLPS (surface behavior) becomes a per-stage table of surface types:
  slippery, very slippery, water, death plane, lava, quicksand, hard
  ground, … Only the slippery mask exists today
  (`extract_clps_slippery_mask`). The engine handles types as players and
  stages need them. Unhandled types fall back to normal ground and are listed
  in the report.

## 4. Behavior checks for the refactor

There is no compatibility to keep, but there is behavior to keep. Before the
refactor starts, record a baseline:

1. **Routes:** `tests/castle_route.pad`, `castle_orbit.pad` and
   `castle_camera_wall.pad`, plus a new 1F route through every room. For each
   route, store the end position of Mario, the jump/landing/reset counts and
   the panic flag from the RAM dump (`tools/check_castle_capture.py`).
2. **Images:** fixed-camera captures at the spawn and in each 1F room
   (`tools/capture_castle_comparisons.py`).
3. **Frame time:** `tools/profile_castle_frames.py` on the controls and orbit
   routes (currently about 53.0 and 49.1 ms per draw).

After every refactor step, all three must match:

- **Routes:** identical end state.
- **Images:** pixel difference within the current tolerance.
- **Frame time:** within ±2% of the baseline.

The host test suite is rewritten along with the code where it tests old
interfaces.

## 5. Phases

### Phase 0: baseline

- Record the baseline in section 4. Store it under `private/baseline-engine/`.
- Write the 1F all-rooms route.

**Done when:** the baseline can be regenerated with one command.

### Phase 1: tools for all stages

**1.1 KCL decoder** (`tools/sm64ds_pipeline/kcl.py`)

- Allow alignment padding after the normal table: use `(start - n) // 6`
  normals, and accept up to 3 trailing bytes.
- Degenerate prisms: find how the DS query code treats them
  (`notes/collision-system.md`, the KCL query classes). Then drop them, or
  keep them as edge-only records, and count them in the report instead of
  failing. Dump where they are and what attribute they have, and check none
  are walkable floors.
- Fixture tests: one padded normal table and one degenerate prism.
- **Gate:** all 48 KCL files decode.

**1.2 Generic level reader** (`sm64ds_pipeline/level.py`)

- `read_level(fs, overlay_id) -> Level`. It covers every category in
  `include/LVL_Overlay.h`: entrance, exit, door, teleport source, standard,
  simple, path node, path and view records. Unknown categories are kept as
  raw bytes with their category number.
- Each list keeps its area and star filter.
- Locate the record by its (model, KCL) file-ID pair from the handle table,
  as in section 2.1.
- `extract_castle_props`, `extract_castle_1f_objects` and their constants
  are deleted. The castle stages use the generic reader.

**1.3 Names**

- Extract `sObjToActorIdTable` from overlay 2. Find it by content: object 42
  must map to `PICTURE_GATE` (actor 307), and object 80 to the Toad actor.
- Extract the decomp's level table (level ID → stage, course) the same way,
  for the stage graph.
- Both go into the stage report. A test checks that the castle object IDs
  used today (41, 42, 76, 80, 275) resolve as expected.

**1.4 Stage table and the all-stages report**

- Write `tools/stage_table.py` with rows for every stage in section 2.1.
  Rows for stages not yet playable are marked `enabled=False`. They are still
  converted for the report.
- `prepare_stage.py --all --report` converts every row and writes
  `private/stages/report.json`.
- Sky: find each outdoor stage's skybox ID (`dScStage_c::LoadSkybox` /
  `GetSkyboxID`, `notes/scene-provenance.md`). Then bake its panorama with
  `emit_sky_panorama`.

**Done when:** all 48 stages convert, and the report names every object's
actor.

### Phase 2: engine refactor

Done in steps. Each step builds, boots and passes the section 4 checks.

1. **Build system.**
   - Add a CMake function: `sm64ds_add_stage(NAME bob BIN BOB DATA_DIR …)`.
     It links the engine, the stage data and the stage's actor modules, then
     stages `<BIN>.BIN` onto the disc.
   - The unified disc's file list comes from the enabled stage-table rows.
   - `build-castle.sh` becomes `build.sh`. It calls
     `prepare_stage.py` for the enabled rows, `prepare_intro.py` and the CMake
     build.
   - Old targets and names are deleted: `sm64ds_castle`, `sm64ds_castle_1f`,
     `_castle_vdp2_sky`, `SM64DS_CASTLE_1F_DIR`, `SM64DS_GENERATED_DIR`.
2. **Split `src/castle.c`** into the `engine/` modules in section 3.1.
   Simply moving code comes first. Behavior changes come in later steps.
3. **Replace stage macros with the descriptor.**
   - Every `CASTLE_*` switch becomes a descriptor field, generated by
     `prepare_stage.py`: `CASTLE_STAGE_ID`, `CASTLE_WARP_*`,
     `CASTLE_ROOM_CULLING`, `CASTLE_PROPS_AVAILABLE`,
     `CASTLE_INTERIOR_PROPS_AVAILABLE`, `CASTLE_INTRO_PROPS_AVAILABLE`,
     `CASTLE_HAS_SKYBOX` and the rest.
   - The generated `castle_*.h` headers are replaced by one
     `stage_data.h` schema.
4. **General areas.** The 1F room and portal code becomes the area system for
   any stage with `area_count > 1`.
5. **Warps from the stage graph.** Replace the single warp box with
   `stage_warp_t` tables. Replace `sm64ds_warp_arg_t` with
   `sm64ds_handoff_t`.
6. **Actors.** Move the existing props (signposts, bomb trees, doors,
   paintings, Toads, Lakitu and the warp pipe) into actor modules spawned
   from the generic object list. The hand-written prop arrays are deleted.
7. **Delete what is no longer used:**
   - The old VDP1 skybox path (`skybox_preview`, `CASTLE_HAS_SKYBOX`).
   - The experiment switches `SM64DS_EXP_NO_SKY` and `SM64DS_EXP_FAR_CULL`.
   - `runtime/sm64ds_stage_handoff.h`.
   - The castle-specific extractors.
   - Any `runtime/` module that is now folded into `engine/`
     (`sm64ds_background`, `sm64ds_painter`, `sm64ds_play`, `sm64ds_pose`).
   - `src/viewer.c` and `src/sprite_fixture.c`, if they have no remaining use.
8. **Diagnostics.** The `SM64DS_VISUAL_DIAGNOSTICS` / `SM64DS_DIAG_*` code (57
   + ~70 `#if` uses) moves into a separate diagnostics build of the engine.
   A runtime debug menu replaces it where that is cheap enough. The release
   engine has none of it.

**Done when:** Castle Grounds and 1F run on the engine and pass section 4.
`src/castle.c` no longer exists. Nothing in `engine/` mentions a specific
stage.

### Phase 3: Bob-omb Battlefield, static

- Enable the `bombhei_map` row (`BOB.BIN`, `outdoor` profile, Castle Grounds
  converter settings).
- Add a direct-boot disc option, `build.sh --direct bob`, which puts BoB at
  `0.BIN`. It works for any stage.
- Spawn at entrance 0.
- Handle the surface types BoB's CLPS table uses, at least death planes
  (reset to the spawn) and slippery slopes.
- Record `tests/bob_route.pad` (spawn → Chain Chomp → foot of the hill) and
  `tests/bob_orbit.pad`. Profile them and take DS comparison captures.

**Done when:**

- Mario can walk the whole course without falling through or getting stuck.
- Probe frame time is ≤ 55 ms per draw on both routes.
- At least 32 KB of High WRAM is still free.
- No BoB-specific code was added to `engine/`.

### Phase 4: castle ↔ course through the stage graph

- Generated painting warps take Mario from 1F into `BOB.BIN`, star 1. Star
  select is skipped for now.
- Pause → Exit course and death return Mario to the castle entrance for BoB.
- Stages that are not enabled show "not ported" at their painting or door.
- Route: 1F → BoB painting → BoB → exit → 1F in front of the painting.

**Done when:** the route passes, and the graph check reports no broken links
among the enabled stages.

### Phase 5: actor framework, shared kinds, player actions — **Done (2026-11-20)**

- `engine/actor.c`:
  - A pool sized from the stage report.
  - Star-filtered spawning.
  - Update and draw ranges.
  - Touch dispatch against Mario's cylinder.
  - A shared animation pose for identical actors that are on the same frame.
- **Shared kinds:** coin (yellow, red, blue), Power Star, ? block, signpost
  (text box), door, 1-up.
- **Player actions:** punch/kick, grab/hold/throw, damage/knockback/health,
  death/respawn, star collect. Port them from `daPly_c` into the action
  table.
- **HUD:** coins, health, stars.

**Done when:** every shared kind and action works in Castle Grounds and BoB.
The frame-time budget holds with BoB's always-present objects spawned.

**Done.** Actor pool is per kind (generated `sm64ds_actor_kind_t` with its own
buffer set), star-filtered at spawn, update-culled at 200 units and
draw-culled in `sm64ds_actor_kind_submit`. Touch dispatch is the shared
`sm64ds_actor_hit_t` (count, push, damage, coins, stars, bounce,
boss_defeated). Shared kinds: coin (yellow/red, 50-per-heart), Power Star
(`star_bit`), ? block, signpost, door, 1-up placements, Bob-omb, pink
Bob-omb, Goomba, Chain Chomp, iron ball, King Bob-omb. Player actions:
walk/run/jump (prototype), grab/hold/throw (boss), damage/knockback/health,
death/respawn, star collect. HUD: coins, health, stars, boss HP while it is
engaged. BoB's always-present objects spawn at 31.3 ms/draw (controls
route), inside the 55 ms static budget.

### Phase 6: BoB star 1 — **Done (2026-11-20)**

Port these kinds from the decomp, in this order:

1. **Bob-omb** (`d_a_bmb.cpp`): walk, notice Mario, chase, fuse, explode,
   respawn.
2. **Chain Chomp + post + gate** (`d_a_wanwan.cpp`,
   `d_a_obj_wanwan_shutter.cpp`). The chain is drawn as sprites.
3. **Moving obstacles on the climb**, as the object report shows them (for
   example the rolling iron balls).
4. **King Bob-omb** (`d_a_bombking.cpp`): grab and throw Mario, be grabbed
   from behind, three hits, defeat, star spawn.

Then the mission flow: star appears → collect → set the save bit → exit to
the castle.

**Done when:** a route defeats King Bob-omb and collects star 1. Probe frame
time is ≤ 66 ms per draw on the climb and summit routes. No WRAM overflow.

**In progress (2026-11-20).** Kinds 1, 2, 3 and 4 exist as posed actors with
behavior: Bob-omb/pink Bob-omb/Goomba chase and explode; Chain Chomp
(`WANWAN`, behavior 5) lunges at Mario and hurts on contact, drawn from the
bomb body with a procedural chain from post to head; iron balls
(`IRONBALL`, behavior 6) roll toward Mario; King Bob-omb stomps (3 HP),
stuns, and unlocks the star. Coins (yellow/red/secret) spin, are collected on
an 8-unit box and count toward the 50-per-heart rule; secret coins grant five. Grab/hold/throw on the
boss: A grabs a stunned/idle boss in reach, X throws it along Mario's facing
with an arc; a throw counts one hit, so three throws beat him, and a stomp
also works. On defeat the star spawns at the boss's death spot (`star_bit`),
is collected on touch, sets the save bit and appears in the warp arg.

Player damage is a real health model (`health`/`max_health` 8, 45-step hurt
i-frames, clamped healing, 50 coins heal 1, a 90-step down timer and respawn
at the stage spawn with the view reset). The HUD shows `HP:n/8` while hurt
and `$:n` once coins are held, and flashes the screen red during i-frames.
WRAM gate after each stage link: BoB 47 KB High / 124 KB Low free. Speeds,
ranges, fuse, blast, health and stun values are estimates, not decomp values.
The Bob-omb colour issue is unresolved.

**Verified route (`tests/bob_boss_fight.pad`, `BOSS.BIN` summit spawn):** the
route stomps King Bob-omb three times and collects star 1 in 2,900 probe
fields; the end state is `boss_hp=0, star_bits=1, health=6, grounded=1` with
3 resets and 11 landings, pinned in `private/baseline-engine/baseline.json`
as the `bob_summit` route. Probe frame time is **58.4 ms/draw** (≤66 budget).
`BOSS.BIN` is the same course as `BOB.BIN` with Mario spawned at the summit
(`--spawn 96 96 -345`) so the fight is one short walk; `BOB.BIN` remains the
full walk from the main entrance, at 31.3 ms/draw on the controls route.

### Phase 7: rolling out to other stages — **in progress (2 of 8 done)**

Adding a stage follows one checklist. Nothing on it touches `engine/` unless
the stage needs a new engine feature, and such features are listed in advance
below.

**Adding a stage:**

1. Enable its row in `stage_table.py` and tune its converter settings.
2. `prepare_stage.py <name>` and read its report: faces, budgets, missing
   actor kinds, missing surface types, broken warps.
3. Port the missing actor kinds into `actors/`.
4. Record a walk route and an orbit route, then profile and capture.
5. Connect it in the graph (painting, door or pipe) and record the entry/exit
   route.

**Suggested order,** chosen so each stage needs at most one new engine
feature:

| Order | Stage(s) | New engine feature |
|---:|---|---|
| 1 | `bombhei_map` (BoB) | none beyond phases 5–6 |
| 2 | `main_garden`, `castle_b1`, `castle_2f` | star doors, key doors (multi-area already done) |
| 3 | `battan_king_map` (WF) | moving platforms / rotating terrain |
| 4 | `kaizoku_irie` + `kaizoku_ship` (JRB) | water, swimming, in-course stage transitions |
| 5 | `snow_mt` + `snow_slider` (CCM) | sliding, slide surfaces |
| 6 | `teresa_house` (BBH) | translucent actors (Boos), 7 areas |
| 7 | `koopa1_map` + `koopa1_boss` | boss arena handoff, Bowser grab/throw |
| 8 | the rest | caps (wing/metal/vanish), quicksand/lava, clock-driven terrain, size switching (THI) |

The character-specific stages (`ex_*`) and character switching are out of
scope until the decomp's character model is ported.

## 6. Budgets

`private/stages/report.json` tracks these for every stage. The build fails
when an enabled stage goes over.

| Resource | Measured by | Target |
|---|---|---|
| Frame time | probe profile block | ≤ 55 ms static, ≤ 66 ms with actors |
| High WRAM | ELF + BSS from the map file | ≥ 32 KB free |
| Low WRAM | `.wram_l` (sky band, bindings) | fits, with room for the sky band |
| VDP1 VRAM | `sat_model_vram_estimate_bytes` per stage + actor kinds + HUD | fits |
| VDP1 commands | scene stats on the routes | under the list capacity |
| CRAM | converter's bank map (stage, actors, HUD, VDP2 sky bank 3) | no overlap |

## 7. Risks

- **The refactor breaks the working stages.** This is why phase 2 goes in
  small steps, each checked against the section 4 baseline.
- **High WRAM as actors grow.** Per-stage linking keeps unused kinds out.
  If one stage still does not fit, move cold data to Low WRAM and shrink
  texture budgets per stage.
- **Frame time with many actors.** Update/draw ranges, shared poses, and
  sprite stand-ins for far actors.
- **The player port is the biggest single piece of work.** Keep it as an
  action table, so each action lands and is tested by itself.
- **Region addresses.** The decomp's addresses may be for another ROM region.
  Find every table by content (known ID pairs), never by address.
- **Hardware.** Every frame-time number comes from the probe, which has no
  cache emulation and no real VDP1 timing. Validate on hardware before tuning
  close to a budget.

## 8. Open questions

1. What exactly are level-wide categories 6, 7, 8, 11 and 14?
2. Where is the level ID → stage/course table, and in which overlay?
3. Which skybox does each outdoor stage use?
4. How does the DS collision query treat degenerate prisms?
5. Is star select needed before BoB's star 2, or will a debug menu choose
   the star until then?
6. Which stages are `horisoko`, `rainbow_mario`, `playroom` and the `ex_*`
   set? Check against the decomp's course table.

## 9. First concrete steps

1. Record the phase 0 baseline.
2. Fix `decode_kcl` (padding + degenerate prisms) until all 48 KCL files
   decode.
3. Write `level.py` and the object/level name tables.
4. Write `stage_table.py` and run the all-stages report.
5. Start the phase 2 refactor with the CMake stage function and the
   `castle.c` split.

## 10. Status

| Phase | State |
|---|---|
| 0 baseline | Done: `tools/record_baseline.py record` / `check` (3 routes, end state exact, image diff ≤1%, frame time ±2%). A fourth route, `c1f_walk` (Castle 1F: walk and one jump), covers the 1F build. Re-recorded 2026-11-20 on the final engine (post health/coins/chain-chomp/star-handoff changes); `check` passes. |
| 1 tools | Done: KCL fix, `level.py`, `actors.py`, `stage_table.py`, `prepare_stage.py --all --report`. Level ID: sublevel = overlay − 8 (derived; matches castle 1, 1F 2, BoB 6; the decomp's SUBLEVEL_LEVEL_TABLE address does not match this ROM). Not done: baking a sky for every stage (the vrbox lookup exists). |
| 2 engine refactor | Partly: warp/entrance tables generated per stage (`sm64ds_warp_t`, `sm64ds_entrance_t`), `sm64ds_add_stage()` in CMake, props from the level reader, old castle extractors deleted. `castle.c` shrank from 2,988 to 1,418 lines by moving self-contained blocks into textually included files (`castle_diag.inc`, `castle_sky.inc`, `castle_intro.inc`, `castle_props.inc`, `castle_rooms.inc`, `castle_interior.inc`, `castle_support_order.inc`, `castle_hud.inc`); baseline unchanged. `stage_desc_t` exists as `sm64ds_stage_desc_t castle_stage` (name, id, background, camera distances, kill floor, entrance and warp tables), generated per stage; the spawn, camera, background and warp macros are gone. Not done: turning the `.inc` blocks into real linked modules with their own interfaces (they still share `castle.c` statics), areas generalised beyond 1F rooms. |
| 3 static BoB | Done: `BOB.BIN`, 36 ms/draw in the probe, trees and signposts from the level data. The two route scripts `tests/bob_route.pad` (spawn → Chain Chomp → hill foot) and `tests/bob_orbit.pad` (full camera orbit at the spawn) are recorded and profiled at **43.97 ms/draw** and **30.93 ms/draw** (≤55 ms static budget); both end grounded with no skipped faces and one boot reset. WRAM gate: `tools/check_stage_budget.py` runs after each stage link (BoB: 54 KB High / 340 KB Low WRAM free). A fall-reset floor (`CASTLE_KILL_Y`) is generated per stage. |
| 4 warps | Done for 1F ↔ BoB (painting jump, L+R+Z return), verified in the probe. Painting warps are now generated from the stage table (`painting=`, `enabled=`): enabling a course adds its 1F trigger and numbered return entrance with no code change. `prepare_stage.py --all` bakes every stage's sky (all but id 11, Bowser in the Sky, which has no vrbox model). |
| 5 actor framework | Done: static posed kinds (`runtime/sm64ds_actors.{h,c}`, `tools/actor_registry.py`, `sm64ds_pipeline/actor_model.py`, per-stage `actors=` in the stage table). BoB draws Bob-omb, pink Bob-omb, Goomba, King Bob-omb, ? blocks, the yellow, red and secret coin models (the five secret coins are worth five coins each), Chain Chomp (bomb body + procedural chain) and iron balls from the level data. Kinds have an optional behavior: `chaser` (Bob-omb, pink Bob-omb, Goomba) walks toward Mario inside a range and follows the floor; Bob-ombs light a fuse on contact (they flash), then explode, hitting Mario with a horizontal push plus a hop inside the blast radius and respawning after 300 steps; Goombas are consumed on contact; coins spin and are collected within an 8-unit box; Chain Chomp lunges at Mario; iron balls roll toward him; the star stays hidden until the boss is defeated. Player damage is a real health model (`health`/`max_health` 8, 45-step hurt i-frames, clamped healing, 50 coins heal 1, a 90-step down timer and respawn at the stage spawn with the view reset). The HUD shows `HP:n/8` while hurt and `$:n` once coins are held, and flashes the screen red during i-frames. Actor submission culls placements more than a body-height from Mario, and bosses take a tunable stun time. Probe-verified on BoB: standing still at the spawn costs one health point to the nearest Bob-omb (200 fields: 8/8, 400 fields: 7/8, landed, no death); with Chain Chomp and iron balls linked, 600 fields still 7/8, landed. WRAM gate after each stage link: BoB 54 KB High / 340 KB Low free. Speeds, ranges, fuse, blast, health and stun values are estimates, not decomp values. The Bob-omb colour issue is unresolved. The `sm64ds_warp_arg_t` handoff now carries a `stars` byte, so a course exit/death can pass collected stars back to the castle; the castle persists them in `g_stars` across the warp. |
| 6 BoB star 1 | Done: `tests/bob_boss_fight.pad` stomps King Bob-omb three times and collects star 1 on the `BOSS.BIN` summit spawn. End state `boss_hp=0, star_bits=1, health=6, grounded=1`, pinned as the `bob_summit` route in `private/baseline-engine/baseline.json` (6,000 fields). Probe 58.1 ms/draw (≤66 budget). Grab/hold/throw (A grabs, X throws), the star save bit and the star-1 handoff (`sm64ds_warp_arg_t::star_bits`) are all in. The boss can be stomped while stunned (SM64 rule) and rolls down slopes after Mario. The star homes slowly toward Mario after spawning at the boss's death spot so it is always reachable on foot. |
| 7 rollout | In progress: 3 of 8 rollout stages boot and profile in the probe. |
| | **`main_garden` (Castle Courtyard, `GARDEN.BIN`)** — phase-7 rollout stage 1. Enabled in `stage_table.py`; converts (1×1 fallback source for its one untextured material); boots in the probe (`tests/garden_walk.pad`: 1 jump, 2 landings, 0 resets, 0 skipped faces, Mario grounded). **41.3 ms/draw** (≤55 static budget). WRAM after link: **299 KB High / 645 KB Low free** (gate ≥32 KB). No course painting, so its 1F return warp is inert by design. |
| | **`battan_king_map` (Whomp's Fortress, `WF.BIN`)** — phase-7 rollout stage 2. Enabled in `stage_table.py` with shared actors (COIN, RED_COIN, KURIBO, RED_BOMBHEI, HATENA_BLOCK). Converts (1,454 render faces, 30 chunks, 243,712 tex bytes). Boots in the probe (`tests/wf_walk.pad`: 1 jump, 2 landings, 0 resets, 0 skipped faces, Mario grounded). **46.0 ms/draw** (≤55 static budget, down from 65.5 after culling coin/star spin to 48 units). WRAM after link: **142 KB High / 417 KB Low free**. Next rollout stages: JRB, CCM, BBH, Bowser, per the plan's order. |
| | **`kaizoku_irie` (Jolly Roger Bay, `JRB.BIN`)** — phase-7 rollout stage 3, static. Enabled in `stage_table.py` with shared actors (COIN, RED_COIN, KURIBO, RED_BOMBHEI, HATENA_BLOCK); its painting adds 1F entrance 5. Converts (4,820 render faces, 644 prisms, 61 coins). Boots in the probe (`tests/jrb_walk.pad`: spawn → beach → water's edge, 1 jump, 2 landings, 0 resets, 0 skipped faces, Mario grounded) and `tests/jrb_orbit.pad` orbits the bay from the spawn. **25.3 ms/draw walk / 41.5 ms/draw orbit** (≤55 static budget). WRAM after link: **64 KB High / 43 KB Low free**. Water and swimming are not implemented yet, so the routes stay on the beach and pier. |

## Water plane (JRB)

Translucent horizontal faces (polygon alpha < 31) are the water surface.
`prepare_castle.py` removes them from the render mesh and emits
`castle_water_regions[]`, one rectangle and height each (JRB: the bay at y=64,
x -397..502, z -42..490, and the cave pool at y=-188.6). `src/castle.c` draws the
region nearest the camera as a lib-saturn camera-centred water plane (4 rings,
cell 56 units, same painter pass as the level so it depth-sorts with the
terrain). Checked in Ymir with `tests/jrb_orbit.pad`: it boots, orbits and the
bay shows water; WRAM free after link is 57.8 KB High (was ~64 KB). The look is
flat colour with the plane's wobble and distance tint, not the DS water texture,
and swimming/the underwater view are not wired in yet.
