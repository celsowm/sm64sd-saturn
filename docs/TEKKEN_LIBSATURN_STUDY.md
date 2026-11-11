# Tekken 3's LibSaturn integration: lessons for Mario

Inspected the local `../tekken3-saturn` checkout at `9e09a32` on 2026-11-10.
No Tekken files, assets or adapted game code were copied or changed.

## Character pipeline

`src/saturn/characters.c` owns the bridge from game presentation state into
LibSaturn. The portable game computes the original pose; renderer-owned vertex
buffers receive skin deformation. Face IDs, material mappings, anchors and
two-sided flags retain their source identities.

`src/saturn/psx_skin_bridge.c` explicitly converts original Q12 matrices to
LibSaturn Q16 and conjugates rotations into the imported anchors' basis. It
validates all referenced parts and bounds before writing. Its PS1 Y/Z basis
change is specific to that importer and must not be applied to Nintendo DS
geometry. `tests/test_psx_skin_bridge.c` checks axis mapping and placement.

The canonical path uses `sat_skin_deform_range` / `sat_skin_update_mesh`.
`src/saturn/compiled_renderer.c` is an additional validated specialization,
with a complete reference path retained. It is not a replacement animation
system that Mario needs to duplicate.

## Textures and materials

`scripts/psx_character_textures.py` contains two paths:

- Default: 8×8 indexed patches. `T3_FIGHTER_TEXTURE_CAP` defaults to 0 in
  `CMakeLists.txt`.
- Optional fidelity experiment: dimensions follow the face's original UV
  span, with a cap; LUT4 preserves local color tables and transparent code 0.
  Corner samples include both endpoints. Source triangle/quad corner ordering
  is retained when constructing VDP1's A/B/C/D perimeter.

`docs/FIGHTER_FIDELITY.md` explicitly reports that native LUT4, lighting and
hand variants failed its performance acceptance rule and remain optional.
Their existence is not evidence they should replace Mario's textures without
a measured image/memory/cadence comparison. The endpoint sampler is PS1-specific;
DS fractional UV and material transforms require their own reference.

`characters.c` uploads through `sat_model_upload_textures`, builds materials,
then initializes `sat_scene3d_instance_binding_t` and compiled material programs.
Topology and texture residency remain immutable while skinning changes vertices.
Bindings avoid repeating static validation each frame. Original per-face
two-sided flags accompany screen-winding culling; blindly culling every source
material would lose geometry if the source expects two-sided drawing.

## Frame presentation and memory

`src/saturn/main.c` selects `SAT_VDP1_FRAME_ON_SUBMIT` after initialization.
`docs/VDP1_PRESENTATION.md` demonstrates why auto-swapping slow command lists
produces incomplete pictures. This is the same presentation issue observed
in Mario's initial Mednafen screenshot; the castle target now uses this mode.

Tekken explicitly separates mutable actor geometry, immutable bindings and
large cold data across High/Low WRAM. It uses the normal scene painter and
keeps HUD/END command reserve. Additional projected/native command paths are
conditional and must be understood with the selected build configuration.
Parallel geometry has explicit ownership, publication and cache synchronization.
Those optimizations are not prerequisites for repairing Mario's face.

## Verification standard worth adopting

`scripts/compare_saturn_presentation.py` compares the same committed tick,
stable state fields, BIOS/probe/cache settings and exact model-region pixels.
It rejects unhealthy captures and mismatched controls. Independent timings
are measured separately; a CPU submission counter alone is not visible FPS.
Source-specific rendering gaps are documented rather than hidden by metrics.

For Mario this means checking head/eyes and limbs at frozen idle, walk, run
and jump poses from multiple angles, comparing joint/vertex transforms to the
DS source, and inspecting Mednafen as well as Ymir. Passing collision tests or
seeing nonzero command counts does not establish character fidelity.

## Concrete Mario findings

1. The eye material's TEXIMAGE_PARAM supplies repeat/mirror flags and 2× S
   scaling. The old converter read texture flags alone and applied texture
   matrices only while the current matrix mode was texture. The corrected
   material bind and TEXGEN handling preserve this source state.
2. The normal gameplay clips reside in `arc0`: wait 179, walk 180, run 145,
   jump 120. The earlier default selected top-level `su_*` clips instead.
   Defaults now bind the normal set explicitly.
3. Body and gameplay head 129 remain separate source meshes; head attachment
   follows body bone 15. The alternative `b_mario_head_cap` has a different
   coordinate convention and was already removed from this attachment.
4. Per-face sizes/color tables, exact source projection and per-face visibility
   warrant separate experiments. Tekken's PS1 projection/ordering rules are not
   substitutes for DS rules. No claim of complete Mario pixel/pose parity is
   made by this study.

The repair set currently passes 42 ROM-enabled host tests and builds a native
Saturn disc. Character image review remains a separate acceptance gate.
