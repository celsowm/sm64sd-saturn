# SM64DS to Saturn Port Plan (Technically Grounded)

## Core Philosophy
- **NOT using Tekken 3 as a fighting game base** — only as reference for SH-2/LibSaturn build patterns
- **Using LibSaturn's examples/mini-games** as the foundation (hello_world, basic_3d_texture, basic_3d_animation, dino_demo)
- The SM64DS core logic adapts to run under LibSaturn's example framework

## Architecture

```
SM64DS Core Logic (preserved C++ code)
        |
        v
Asset Pipeline (host tools): BMD→sat_model_asset_t, BCA→sat_animated_model_asset_t, KCL→sat_mesh_t+sat_mesh3_grid_t
        |
        v
LibSaturn Example Framework (adapted base: basic_3d_animation + dino_demo patterns)
        |
        v
Saturn Hardware (VDP1/VDP2, SH-2 Master+Slave, CD-ROM, SMPC, SCSP)
```

---

## Technical Mapping: SM64DS → LibSaturn

### 1. Model & Animation Pipeline

| SM64DS | LibSaturn | Conversion |
|---|---|---|
| `BMD_File` (model file) | `sat_model_asset_t` | Host tool: parse BMD → generate C arrays |
| `BCA_File` (bone animation) | `sat_model_animation_asset_t` (baked vertex poses) | Host tool: run skeletal skinning on host → bake per-frame vertex positions |
| `BTP_File` (texture pattern) | Part of `sat_model_texture_asset_t` | Convert texture sequences to indexed8 + palette |
| `BTA_File` (texture SRT) | Not directly supported; bake into vertex UVs or use material animation | Requires custom handling or bake into vertex colors |
| `BMA_File` (material animation) | `sat_anim_face_colors` / `sat_anim_vertex_gouraud` (baked flat/Gouraud) | Bake material animation into per-frame face/vertex colors |
| `ModelComponents` (parsed model data) | `sat_mesh_t` (runtime mutable vertices) + `sat_model_asset_t` (immutable source) | `sat_model_copy_to_mesh()` copies generated geometry to mesh |
| `dExtSimpleModel_c` | `sat_scene3d_instance_t` with static mesh | Direct mapping |
| `dExtAnmModel_c` + `dExtFrameCtrl_c` | `sat_anim_state_t` + `sat_anim_decode()` per frame | Direct mapping |
| `dExtBlendAnmModel_c` (crossfade) | Two `sat_anim_state_t` + manual lerp between pose buffers | Custom: decode both clips, lerp vertices |
| `dExtAnm2Model_c` (dual frame ctrl) | Two `sat_anim_state_t` for body/face or upper/lower | Custom: decode both, combine per-bone or per-vertex |

**Key Insight:** LibSaturn **does not do runtime skinning**. The host `tools/import_model.py` runs skeletal animation on the host and bakes per-frame vertex positions into `sat_model_animation_asset_t`. SM64DS BCA files must go through this same host pipeline.

**Tooling Needed:**
- `tools/bmd_to_saturn.py`: Parse BMD_File → emit `sat_model_asset_t` C arrays
- `tools/bca_to_saturn.py`: Parse BCA_File + BMD → run skinning → emit `sat_model_animation_asset_t`
- `tools/kcl_to_saturn.py`: Parse KCL → emit `sat_mesh_t` + build `sat_mesh3_grid_t`

### 2. Collision System

| SM64DS | LibSaturn | Notes |
|---|---|---|
| `dBgW_Kc` (KCL collider) | `sat_mesh_t` + `sat_mesh3_grid_t` | KCL positions/normals/tris → mesh; octree → grid |
| `dBgCh_SphCrr` (sphere sweep) | `sat_sphere_cast_mesh()` + `sat_sphere_cast_mesh_faces()` | Direct functional equivalent |
| `dBgCh` (query root) | Custom actor component using `sat_body3_t` | `sat_body3_step()` + `sat_body3_collide_mesh_grid()` |
| `dBgCh_Actr` (actor collision) | `sat_body3_collide_aabbs()` or `sat_body3_collide_mesh_grid()` | Actor-to-actor collision |
| `dBgCh_Lin` (line/ray cast) | `sat_raycast_mesh()` | Ray casting against mesh |
| `dBgCh_Gnd` (ground check) | `sat_sphere_mesh_contact()` or dedicated floor check | Part of body step |
| Push-out displacement (`disp`) | `sat_contact3_t` from `sat_sphere_cast_mesh()` | Accumulate contacts manually |

**Collision Mapping Code Pattern:**
```c
// SM64DS: dBgCh_SphCrr::SetObjAndSphere(pos, radius, actor) → DetectClsn()
// LibSaturn:
sat_sphere_t sphere = { .center = pos, .radius = radius };
sat_vec3_t disp = actor_velocity;
sat_sphere_mesh_hit_t hit;
uint8_t found;
sat_sphere_cast_mesh(&level_mesh, &sphere, &disp, &hit, &found);
if (found) {
    // hit.t = fraction of displacement (0..1)
    // hit.normal = surface normal
    // hit.point = impact point
    // Apply push-out based on hit
}
```

### 3. Actor Framework

| SM64DS | LibSaturn | Mapping |
|---|---|---|
| `dActor_c` (base actor) | Custom `Actor` struct with `sat_scene3d_instance_t` | Composition over inheritance |
| `dBgActor_c` (collision actor) | `Actor` + `sat_body3_t` + collision mesh ref | Embed physics body |
| `dActor_c` vtable (Init, Behave, Render) | Function pointers or C++ virtuals in custom struct | `void (*init)(Actor*)`, `void (*behave)(Actor*)`, `void (*render)(Actor*, sat_scene_t*)` |
| `daPly_c` (Mario) | `PlayerActor` : `Actor` with state machine | Port state machine logic |
| Overlay-based dynamic loading | `sat_load_files()` + `sat_exec_arg()` or manual code loading | CD-based overlay loading |

**Actor Struct Pattern:**
```c
typedef struct Actor {
    sat_scene3d_instance_t instance;
    sat_body3_t body;              // for collision/physics actors
    const sat_model_asset_t* model; // static model
    const sat_animated_model_asset_t* anim_asset; // animated model (optional)
    sat_anim_state_t anim_state;    // animation playback
    uint16_t state;                 // current state ID
    void (*behave)(struct Actor*);
    void (*render)(struct Actor*, sat_scene_t*);
    // ... SM64DS-specific fields (health, coins, etc.)
} Actor;
```

### 4. Player (Mario) - daPly_c

The `d_a_ply_methods.cpp` is 24,782 lines with a massive state machine. Key systems to port:

| SM64DS System | LibSaturn Approach |
|---|---|
| State machine (`data_ov002_02110244` + 80+ states) | Port state functions as `PlayerState` functions; state = function pointer |
| Animation scripts (`AnimScriptStep`, `SetAnim`) | `sat_anim_state_t` + `sat_anim_set_clip()` + `sat_anim_advance()` |
| Movement physics (gravity, ground check, wall kick) | `sat_body3_step()` + custom Mario physics on top |
| Collision queries (`dBgCh_SphCrr`) | `sat_sphere_cast_mesh_grid()` via `sat_body3_collide_mesh_grid()` |
| Camera interaction (`dCamera_c`) | LibSaturn `follow_camera3d.h` or `orbit_camera3d.h` |
| Particle system | Custom particle system using VDP1 sprites |
| Sound (`Sound::PlayBank0`, etc.) | `sat_audio_update()` + `sat_music_t` for BGM, PCM voices for SFX |
| Cap system (Mario/Luigi/Wario/Yoshi) | Multiple model assets + `sat_character_asset_t` or model swap |
| Star/coin collection | Actor collision callbacks + game state |
| Message/BMG text | `sat_ascii_font_draw_text_screen_indexed8()` + custom text system |

**Mario State Machine Pattern:**
```c
// Each SM64DS state becomes a function:
typedef int (*PlayerStateFn)(PlayerActor*, int beginFrame, int endFrame);

// State table (from data_ov002_02110244):
static PlayerStateFn s_playerStates[] = {
    State_Init,           // 0
    State_Idle,           // 1
    State_Walk,           // 2
    State_Jump,           // 3
    State_LongJump,       // 4
    State_WallKick,       // 5
    State_GroundPound,    // 6
    State_Dive,           // 7
    State_Swim,           // 8
    // ... 80+ states
};

// In PlayerActor::behave():
int result = s_playerStates[player->state](player, frameBegin, frameEnd);
if (result == STATE_TRANSITION) {
    player->state = player->nextState;
}
```

### 5. Filesystem & Overlays

| SM64DS | LibSaturn | Implementation |
|---|---|---|
| NitroFS (1936 entries) | ISO9660 + `sat_cdfs_volume_t` | Build ISO from asset catalog |
| Overlay 0 (ARM9 main) | Main ELF (always resident) | Link all non-overlay code into main ELF |
| Overlays 1-103 (actor code) | `sat_cart_overlay_t` in RAM cart OR dynamic CD loading | `sat_cart_overlay_load()` for cart, or `sat_load_files()` + jump for CD |
| `SharedFilePtr::LoadFile()` | `sat_load_files()` + LZ77 decode | Port `DecompressLZ16` to host |
| Handle 0x0000-0x7FFF → file | Asset catalog: handle → ISO path → `sat_load_item_t` | Generate `sat_load_item_t[]` from `handles.tsv` |

**Overlay Loading Strategy:**
```c
// For actors in overlays, two options:
// Option A: RAM Cartridge (if 1MB/4MB cart present)
sat_cart_overlay_t ovl;
sat_cart_overlay_init(&ovl, 0x02400000, 0x200000); // 2MB slot in cart
sat_cart_overlay_load(&ovl, &cd_volume, actorOverlayID, "OVERLAYS/ov0XX.bin", size, NULL, NULL);

// Option B: Dynamic CD load into WRAM-L (no cart)
sat_load_item_t item = { "OVERLAYS/ov0XX.bin", size, 0, size, wramL_overlay_slot };
sat_load_files(&cd_volume, &item, 1, 0, loading_progress, NULL);
// Jump to overlay entry point via function pointer
```

### 6. Audio

| SM64DS | LibSaturn | Implementation |
|---|---|---|
| SDAT (SSEQ + samples) | ADX music (streamed) + PCM voices (SFX) | Host tool: extract SDAT → convert sequences to ADX, samples to PCM |
| SSEQ (MIDI-like sequences) | Not directly supported; convert to ADX | Use `tools/convert_audio.py` pattern |
| Nitro SDK sound engine | `sat_music_t` for BGM, `sat_audio_update()` for mixing | 68K driver for timed SFX: `sat_sound_play(SAT_SOUND_PLAY_AT_TICK, ...)` |
| 44.1kHz/48kHz ADPCM | SCSP supports PCM8/PCM16 + IMA ADPCM | Convert samples to PCM16 or IMA ADPCM |

### 7. Input

| SM64DS | LibSaturn | Mapping |
|---|---|---|
| D-Pad | D-Pad | Direct |
| A/B/X/Y | A/B/C/X | A→A, B→B, X→C, Y→X |
| L/R | L/R | Direct |
| Start | Start | Direct |
| Touch screen | Analog stick (cursor) or D-Pad shortcuts | Map touch actions to button combos |
| Microphone | Not available | Remove or simulate |

### 8. Memory Layout (Critical)

**Saturn Memory Map (from LibSaturn `tools/memory_layout.py`):**
```
0x06000000 - 0x060003FF: Master vectors
0x06000400 - 0x060007FF: Slave vectors
0x06000800 - 0x06000FFF: Slave stack
0x06001000 - 0x06001FFF: Dual SH-2 control
0x06002000 - 0x06003FFF: Dual SH-2 control (cont.)
0x06004000 - 0x060FFFFF: Application (ELF loaded here)
0x06100000 - 0x061FFFFF: Work RAM High (1MB)
VDP1 VRAM: 0x25C00000 - 0x25C7FFFF (512KB)
VDP2 VRAM: 0x25E00000 - 0x25E7FFFF (512KB) + 0x25E80000 - 0x25EFFFFF (512KB)
CRAM: 0x25F00000 - 0x25F007FF (2KB)
Sound RAM: 0x25B00000 - 0x25B7FFFF (512KB)
```

**SM64DS Memory → Saturn:**
- ARM9 main (0x02000000-0x023FFFFF, 4MB) → Application + WRAM-H
- Overlay code (0x02000000 region) → Cart overlay or WRAM-L dynamic load
- NitroFS assets → CD-ROM (ISO9660)
- VRAM (256KB) → VDP1 VRAM (512KB) + VDP2 VRAM
- OAM (32KB) → VDP1 sprite system (dynamic allocation)

### 9. Rendering Pipeline

| SM64DS | LibSaturn |
|---|---|
| GX FIFO immediate mode | `sat_scene_t` + `sat_scene_submit_instance()` per frame |
| Display list (DMA to 0x4000400) | VDP1 command buffer built each frame, submitted once |
| OAM sprites (128 max) | VDP1 distorted sprites via `sat_scene_submit_quad()` |
| 2D BG layers (DISPCNT/BGxCNT) | VDP2 NBG0-3 via `sat_vdp2_layers.h` |
| 3D matrix stack (GX) | `sat_model_transform3d_matrix()` + `sat_camera3d_update()` |
| Polygon + texture | VDP1 distorted sprites with `SAT_SCENE3D_INDEXED_TEXTURED` |

**Frame Loop Pattern (from dino_demo):**
```c
while (1) {
    sat_wait_vblank();
    sat_vdp2_layers_commit();        // VDP2 registers
    sat_set_clear_color(SAT_COLOR_BLACK);
    sat_begin_frame();
    sat_pad_poll(&pad);

    // Update game logic (60 Hz)
    update_actors();
    update_camera();
    update_animation();

    // Submit scene
    sat_scene_begin(&scene, &camera, near_z, 320, 224, 64);
    for each actor:
        sat_scene_submit_instance(&scene, &actor->instance, slot, screen_scratch, world_scratch);
    sat_scene_flush(&scene);

    // HUD
    draw_hud();

    sat_end_frame();
}
```

---

## Revised Phases with Technical Detail

### Phase 0: Foundation (2-3 weeks)
1. **Build & run `basic_3d_animation` example** — verify toolchain, Mednafen/Ymir
2. **Extract SM64DS asset catalog:**
   ```sh
   cd sm64sd-saturn/.external/sm64ds-decomp
   python3 tools/asset_catalog.py generate ~/Downloads/"Super Mario 64 DS (USA).nds"
   ```
   Produces `build/assets/files.tsv`, `handles.tsv`, `NitroFileId.h`, `AssetHandle.h`
3. **Analyze catalog:** Identify BMD/BCA/BTP/KCL files for Mario + 1 test course
4. **Study `basic_3d_animation` + `dino_demo` code** — understand dual SH-2, anim pipeline, scene submission

### Phase 1: Asset Pipeline (3-4 weeks) — **Critical Path**
Build host tools to convert SM64DS assets → LibSaturn format:

1. **`tools/bmd_to_saturn.py`**: Parse BMD_File → emit `sat_model_asset_t` C/H
   - Extract vertices, faces, UVs, textures, materials
   - Quantize to 16.16 fixed-point (`sat_fx16_t`)
   - Generate face_texture_indices mapping

2. **`tools/bca_to_saturn.py`**: Parse BCA_File + BMD → run skinning → emit `sat_model_animation_asset_t`
   - Load BMD skeleton + BCA animation
   - Run CPU skinning on host (LibSaturn `sat_skin_*` not used at runtime)
   - Bake per-frame vertex positions (quantized int16 with bias/scale)
   - Generate `sat_anim_position_encoding_t` per clip

3. **`tools/kcl_to_saturn.py`**: Parse KCL → emit `sat_mesh_t` + build `sat_mesh3_grid_t` at runtime
   - Extract positions, normals, triangles
   - Build octree → uniform grid (`sat_mesh3_grid_init`)

4. **`tools/iso_builder.py`**: From `handles.tsv` + asset files → ISO9660 image
   - Map NitroFS paths → ISO paths
   - Generate `sat_load_item_t[]` for all assets
   - Build CUE/BIN via LibSaturn `scripts/gen_cue.py`

**Test:** Convert Mario BMD + BCA (walk, jump, idle) + 1 course KCL → verify in `basic_3d_animation` viewer

### Phase 2: MMIO Proxy & Core Types (2-3 weeks)
1. **Create `src-port/saturn/mmio.h`** with `Reg<T>` proxy (model after `port/ntr/mmio.h`)
   - Map DS register addresses (0x04000000, 0x04001000, etc.) to no-ops or host vars
   - Only implement side-effect registers needed for compilation (CP divider, timers)

2. **Type mapping header `src-port/saturn/types_map.h`:**
   ```c
   // SM64DS → LibSaturn
   typedef sat_fx16_t Fix12i;        // both 16.16
   typedef sat_fx32_t fx32;          // 16.16 or 32-bit
   typedef sat_vec3_t Vector3;       // same layout
   typedef sat_mat4_t Matrix4x3;     // row-major, translation in [3][7][11]
   #define SAT_FX16_ONE 0x10000      // matches Fix12i 1.0
   ```

3. **Compile core math files** (`DotVec3.c`, `CrossVec3.c`, `MulVec3Mat4x3.c`, `ApproachAngle.cpp`, `cstd*.c`) against LibSaturn toolchain with `#ifdef SM64DS_PLATFORM_SATURN` guards

### Phase 3: Collision System (3-4 weeks)
1. **Port `dBgW_Kc` → `LevelCollider`:**
   - Wrap `sat_mesh_t` + `sat_mesh3_grid_t`
   - `SetFile()` → `sat_mesh3_grid_init()` at load time
   - `DetectClsn()` → `sat_sphere_cast_mesh_grid()` / `sat_sphere_cast_mesh_faces()`

2. **Port `dBgCh_SphCrr` → `SphereCollider`:**
   - `SetObjAndSphere()` → set `sat_sphere_t`
   - `DetectClsn()` → call `LevelCollider::SphereCast()`
   - Three result slots (floor/wall/under) → three `sat_sphere_mesh_hit_t`

3. **Port `dBgCh_Actr` / `dBgCh_Lin` / `dBgCh_Gnd`** as needed for actors

4. **Integrate with `sat_body3_t`** for physics-based actors:
   - `sat_body3_step()` for gravity/drag
   - `sat_body3_collide_mesh_grid()` for world collision

### Phase 4: Actor Framework + First Display (3-4 weeks)
1. **Define `Actor` base struct** with `sat_scene3d_instance_t`, `sat_body3_t`, function pointers
2. **Port minimal actor types:** static prop, simple enemy, collectible
3. **Replace `basic_3d_animation` main loop** with actor update + scene submission
4. **Load Mario model + walk animation** → render on screen (orbit camera)
5. **Success criteria:** Mario model animates (walk cycle) on Saturn screen

### Phase 5: Mario Actor + Input (4-5 weeks)
1. **Port `daPly_c` state machine:**
   - Extract state functions from `d_a_ply_methods.cpp`
   - Map to `PlayerStateFn` function pointer table
   - Keep KuppaScript integration (script commands → state transitions)

2. **Implement movement physics:**
   - Gravity, ground check, slope handling
   - Wall kick, long jump, dive, ground pound
   - Use `sat_body3_step()` + custom Mario logic

3. **Input mapping:**
   ```c
   void map_nds_to_saturn(const sat_pad_state_t* pad, NDSInput* out) {
       out->dpad = (pad->held & SAT_PAD_UP) ? NDS_UP : 0 | ...;
       out->a = (pad->held & SAT_PAD_A) != 0;
       out->b = (pad->held & SAT_PAD_B) != 0;
       out->x = (pad->held & SAT_PAD_C) != 0;  // X→C
       out->y = (pad->held & SAT_PAD_X) != 0;  // Y→X
       out->l = (pad->held & SAT_PAD_L) != 0;
       out->r = (pad->held & SAT_PAD_R) != 0;
       out->start = (pad->held & SAT_PAD_START) != 0;
       // Touch → analog stick cursor or D-Pad combo
   }
   ```

4. **Camera:** Use `sat_follow_camera3d.h` (third-person follow) or port SM64DS `dCamera_c`

5. **Success criteria:** Mario walks, jumps, long-jumps on flat textured floor

### Phase 6: Course Prototype (4-6 weeks)
1. **Load full course KCL + geometry** (Bob-omb Battlefield or Castle Grounds)
2. **Place static actors:** platforms, blocks, coins, goombas
3. **Implement actor collision callbacks** (coin collection, enemy hit, block break)
4. **Camera collision** (follow camera with wall avoidance)
5. **Star/coin counter + HUD**
6. **Success criteria:** Playable course with Mario moving, collecting coins, basic enemies

### Phase 7: Systems Completion (4-6 weeks)
1. **Overlay loading:** Dynamic actor code loading from CD
2. **Audio:** SDAT→ADX/PCM conversion + `sat_music_t` + SFX
3. **Save system:** SM64DS NVRAM schema → `sat_save.h` backup RAM
4. **Message/BMG text:** Custom text renderer using `sat_ascii_font`
5. **Minigames:** Port ov004 minigame scenes
6. **Polish:** Performance optimization (VDP1 command budget), visual fidelity

---

## Required Tooling (Must Build First)

| Tool | Input | Output | Used By |
|---|---|---|---|
| `bmd_to_saturn.py` | BMD_File | `sat_model_asset_t` C/H | All models |
| `bca_to_saturn.py` | BCA_File + BMD | `sat_model_animation_asset_t` C/H | Animated models |
| `btp_to_saturn.py` | BTP_File | Texture sequence frames | Texture animation |
| `kcl_to_saturn.py` | KCL_File | `sat_mesh_t` + grid build code | Collision |
| `iso_builder.py` | `handles.tsv` + asset files | ISO9660 BIN/CUE | CD-ROM |
| `sdat_extract.py` | SDAT_File | ADX (BGM) + PCM16 (SFX) | Audio |

---

## Risk Register (Technical)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| BMD/BCA format not fully documented | High | High | SM64DS decomp has `dExtSimpleModel_c::LoadFile` + `func_020462d0` — reverse from there |
| BCA skinning weights don't match LibSaturn baking | Medium | High | Use SM64DS's own skinning code on host to bake poses; don't reimplement skinning |
| VDP1 command budget exceeded | High | High | Profile with `dino_demo` diagnostics; limit faces/frame; use `SAT_VDP1_FRAME_ON_SUBMIT` |
| Overlay loading from CD too slow | Medium | Medium | Pre-load common overlays; use RAM cart if available; async load next area |
| SDAT → ADX conversion loses fidelity | Medium | Medium | Prioritize PCM for SFX; ADX for BGM only; accept some fidelity loss |
| Mario state machine too large for SH-2 I-cache | Low | Medium | SH-2 has 4KB I-cache; 24K lines of C++ → ~100KB code; use `-Os`, profile |
| Dual SH-2 sync for animation | Medium | Medium | Follow `dino_demo` pattern: Slave decodes next pose while Master renders |

---

## Concrete Next Steps (Week 1)

1. **Run LibSaturn example:**
   ```sh
   cd ~/dev/lib-saturn
   make EXAMPLE=basic_3d_animation
   # Boot build/basic_3d_animation.cue in Mednafen
   ```

2. **Extract SM64DS assets:**
   ```sh
   cd ~/dev/sm64sd-saturn/.external/sm64ds-decomp
   python3 tools/asset_catalog.py generate ~/Downloads/"Super Mario 64 DS (USA).nds"
   # Examine build/assets/handles.tsv for Mario (handle 0xBF = 191?) and course BMDs
   ```

3. **Write `bmd_to_saturn.py` prototype** — parse one BMD (Mario or simple block) → emit `sat_model_asset_t`

4. **Test in `basic_3d_animation`** — replace `male_walk_asset` with converted Mario model

5. **Verify toolchain:** `sh2eb-elf-gcc --version` and CMake build works

This technically grounded plan replaces the vague "extract 500 functions" with specific, testable deliverables at each phase, based on actual code analysis of both SM64DS decomp and LibSaturn examples.