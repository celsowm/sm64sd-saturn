# Castle and Mario visual repair plan

Prepared 2026-11-17. This is an implementation plan, not a claim that the
visual defects have been repaired. Scope: the existing castle prototype,
Mario body/head, terrain, clipping, visibility, texture quality and HUD.
Gameplay expansion and performance redesign follow correctness.

## Evidence and baseline

The current Mednafen desktop capture is retained privately at
`private/visual-repair-baseline/desktop.png`. It shows Mario facing the
camera on the path, diagonal red bands across his blue torso, ambiguous
limb overlaps, white patches on the lawn, a large flat foreground surface,
and strongly distorted castle texture detail. It cannot establish animation
correctness, collision correctness or which white patches are actual holes.
Do not classify every white pixel as missing geometry without a face-ID view.
The top instruction text loses contrast against the castle.

Inspected source baselines:

- Port HEAD: `102ae95057c69687cc321f7ac3a2b9690ac1c038`, plus current uncommitted
  near-clip fallback changes.
- Local LibSaturn HEAD: `c5a33e2627c85fb75268ce93576838069a33886b`.
- Local decomp HEAD: `44250be91a2113d1555c50b082f2c50f645336a7`.
- Built castle ELF SHA256:
  `633a3bb47382edbed2a742c1db4a623255c4ae7092583499f9a2f07356cfe7d1`.

These checkout IDs do not prove that an installed SDK archive matches its
source. Record the installed archive hash and build settings before comparison.
The baseline has 42 passing ROM-enabled host tests and a successful native
disc build; neither is visual acceptance.

Current generated reports, rather than older documentation, give:

| Asset | Current measurement |
| --- | --- |
| Castle | 1,029 vertices, 1,337 faces, 1,210 tiles at 8x8, 77,440 pixel bytes |
| Mario body | 16 joints, 131 rigid vertices, zero blended vertices, 246 faces |
| Body textures | 210 tiles at 24x24, 120,960 pixel bytes |
| Gameplay head | arc0 entry 129, attached to body bone 15, 95,040 pixel bytes |
| Collision | 1,243 prisms; independent of visual geometry |

Keep the ROM and all derived captures, oracle dumps and generated data private.

## Findings: established gaps and unresolved causes

| Symptom | Source evidence | What remains to prove |
| --- | --- | --- |
| Near-camera holes / flat foreground | LibSaturn `draw_textured_quad` refuses a texture when any original corner crosses the near plane or projection bounds. The new fallback supplies a flat average color. | Which visible patches take that fallback; whether culling and ordering also expose gaps. |
| White/gray surfaces | `prepare_castle.py` replaces every material without a texture with `(180,180,180,255)` tiles. `Model` carries no diffuse/ambient, polygon alpha or lighting state. | Which white patches are intended decoration, gray substitution, transparent pixels or uncovered background. |
| Missing back faces | `castle.c` enables culling globally for castle, body and head. The converter discards GX polygon state and exports no per-face side mask. SDK supports `double_sided_faces`. | Actual front/back/hidden flags for affected source materials and stream overrides. |
| Mario red diagonal bands | Triangles become degenerate quads; UVs are bilinearly baked across a square. Renderer uses four-corner average depth, including the repeated triangle corner. | Whether the band originates in UV mapping, wrong sprite corner convention, pose transforms, or occlusion. No single cause is established. |
| Castle texture distortion | Every castle face gets the same bake size; budget overflow reduces the entire castle from 16 to 8 texels per side. Source normals/colors are ignored. | Relative contribution of sampling, UV corner order, palette reduction and depth order. |
| Incorrect overlaps | SDK painter key uses average camera depth; no Z buffer. Castle, head and body share a pass. | Reproducible face pairs and depth spans that sort incorrectly. |
| Strange character shape | Skeleton path uses quaternion conversion, scale streams, rigid skin anchors and a separate head attachment. | Matrix/vertex parity at fixed clip frames, head transform and stable foot placement. |

Primary local references: `geometry.py`, `bmd.py`, `textures.py`, `skinning.py`,
`emit.py`, `prepare_castle.py`, `runtime/sm64ds_pose.c`, `src/castle.c`;
SDK `src/graphics/3d/scene/faces.cpp`,
`src/graphics/3d/rendering/indexed.cpp`, `include/saturn/scene3d_faces.h`;
decomp `src/engine/model/ModelComponents.cpp` and `port/ntr/gx.cpp`.
The decomp material bind writes polygon attributes, diffuse/ambient,
specular/emission and texture parameters; the port retains only part of this.
Its PC GX renderer also ignores POLYGON_ATTR, so it is not an independent
visibility oracle. Verify raw file layout against engine structs and actual
bytes; do not copy offsets from runtime material structures blindly.

## Ordered implementation and acceptance gates

### 1. Reproduce and expose the failing faces

Add a deterministic diagnostic mode to the existing target: fixed camera,
frozen clip/frame, actor-only/world-only/head-only, untextured face-ID colors,
wireframe overlay where practical, and toggles for culling and texture use.
Do not change production rendering defaults during these experiments.
Preserve face provenance from stream/group/material/primitive/corner through
skin remapping and texture deduplication. Log source face IDs in host reports,
not text over the gameplay screen.

Capture native emulator framebuffer images at fixed simulation ticks. Save
camera, player position, clip/frame, BIOS/config hashes, ELF/SDK hashes and
telemetry beside each image. Avoid wall-clock screenshots as regression goldens.
Cover front/side/back and near camera, both zoom distances, spawn, bridge,
castle door, wall proximity and camera rotation. Freeze at least idle, walk,
run and jump poses. Separate a geometry failure from a texture failure by
rendering the same frozen state with unique solid face colors.

Gate: every visible defect has a reproducible capture and affected face or
material IDs. Zero skipped faces is supporting telemetry, never the sole gate.

### 2. Prove topology, sprite mapping and character transforms

Create asymmetric synthetic fixtures: numbered/color-coded quad corners,
triangle with distinct UV corners, multi-face triangle and quad strips, UV
seams, mirrored textures, and a small articulated model. Compare all four GX
primitive types to an independent triangulation, including winding and area.
Retain original primitive type in IR rather than reconstructing it from
repeated indices later.

Test the actual VDP1 distorted-sprite corner/interpolation convention in the
emulator. Verify that a collapsed quad's bake maps to the intended triangle;
if it does not, change the triangle representation/bake together. Render
Mario's source atlas and per-face tiles privately for inspection before
increasing texture sizes.

Compare source bone-local anchors, parent transforms, joint-world matrices
and skinned positions at exact integer clip frames against the engine math.
Then test fractional frames, loop boundaries and jump end clamping. Use the
independent source Euler matrix as an oracle, rather than a second invocation
of the port quaternion helper. Mario currently has zero blended vertices:
prioritize rigid slots, matrix conventions and attachment over weighted-skin
changes. Verify bone 15 and head scale/orientation in isolation.

Check whether grounding Mario by each pose's animated minimum Y causes
unwanted vertical bobbing; retain a stable root/foot policy unless original
animation behavior requires otherwise.

Gate: exact topology/UV associations; matrix and vertex errors within measured
fixed-point/anchor quantization bounds; no unexplained torso bands in an
isolated solid or textured actor at the frozen poses. Establish tolerances
from numerical precision and image sampling, not an arbitrary large epsilon.

### 3. Preserve material and visibility semantics

Extend IR and emitters with source material identity, diffuse/ambient,
polygon visibility/alpha, per-corner colors/normals and relevant GX overrides.
Keep UV/color/normal seams distinct even where positions are shared.
Implement untextured material colors instead of generic gray textures.
Resolve hidden, front-only, back-only and two-sided materials explicitly;
normalize winding where needed and export SDK per-face side masks.
Honor state at the source-defined primitive boundary.

Treat alpha-test/cutout, opaque and blended materials separately. Preserve
transparent palette index zero. Specify an approximation for partial alpha
supported by stock VDP1; validate it against a source reference. Never make
all faces two-sided or opaque as a final workaround. Start with source
unlit colors, then add measured lighting/shading, checking SDK Gouraud format
support before assuming indexed8 textures can use it.

Gate: front/back orbit reveals intended surfaces only; hidden geometry stays
hidden; cutout edges remain intact; no unexplained gray material substitutions.
Synthetic visibility tests supplement the source image comparison.

### 4. Repair clipping and painter occlusion together

Keep the new flat-color fallback as a bounded emergency path and count it
separately from rejected/skipped faces. Instrument near crossings, excessive
projection spans, culling, fallback and depth spans. Test camera endpoints
inside or next to walls; camera collision alone cannot fix large floor faces.

First subdivide oversized static faces offline with interpolated source UVs,
materials and colors, constrained by projected error and resident budgets.
Use the existing SDK tiled rendering path where its API and texture ownership
fit; measure before adopting it. VDP1 cannot gain general arbitrary UV clipping
by clipping geometry alone. If smaller pieces still leave unacceptable flat
patches, evaluate a bounded clipped-texture strategy in the SDK with explicit
scratch/VRAM lifetime and command caps. Keep fallback for pathological views.

Use diagnostic overlap pairs to evaluate triangle centroid depth versus the
current duplicated-corner average. Correct depth keys for true primitives
where evidence supports it. Split large world faces whose depth intervals
straddle the actor. For persistent static ordering cycles, consider local
spatial partitioning with bounded splitting. Do not force Mario to a later
pass: that would draw him through walls. Keep sky behind geometry and HUD last.

Gate: ground and walls remain covered through a camera sweep; the path does
not cover Mario's feet incorrectly; walls correctly occlude Mario; limbs/head
sort correctly in the pose matrix. No capacity overflow at worst viewpoints.

### 5. Recover texture detail within stock memory

Replace uniform per-face sizes with bounded adaptive bake resolution based
on UV span, expected screen coverage and error. Prioritize Mario face/body,
castle entrance and walking surfaces. Deduplicate after material modulation
and wrapping. Preserve source texture sampling and mirrored repeat behavior.
Quantize only after establishing correct full-color reference bakes.

Compare direct shared-source/tiled textures with face bakes for repeating
terrain; do not assume either wins. Report palette error and per-material
texture cost. Remove the global 16-to-8 downgrade in favor of a deterministic
allocation policy that fails clearly if mandatory quality cannot fit.

Budget code/data/BSS/stacks in High and Low WRAM, VDP1 commands and scratch,
textures/font/Gouraud tables and safety reserve. Measure live allocations,
not only pixel totals. HLOD is deferred until full-detail geometry is correct.

Gate: identifiable castle detail, continuous path/grass, readable Mario eyes,
no red torso artifacts, bounded palette error and all stock memory limits met.
Compare equal-resolution native framebuffer captures, not desktop scaling.

### 6. Presentation and full regression acceptance

Give HUD text a compact opaque backing or suitable contrast treatment. Keep
completed-frame presentation and test slow frames in Mednafen as well as Ymir.
Re-run `tests/castle_route.pad`, wall/camera routes, reset and pause, and the
existing host suite. Preserve collision geometry and movement traces while
changing visual tessellation.

Archive before/after images for each failing view, diagnostic results,
resource peaks and displayed-frame timings. Add synthetic tests at each
repaired seam and private source-oracle checks where appropriate; do not use
image hashes across different emulators as a pixel-parity requirement.
Inspect complete sequences for flicker, texture swimming and popping that
still frames cannot prove. Physical Saturn verification remains a separate
explicitly outstanding gate unless actually performed.

Gate: all recorded defects closed with evidence, no new visibility/pose
regressions, no panic/skipped/capacity errors, correct frame completion and
reported performance. Refresh stale status/counts in the documentation only
from matching generated assets and captures.

## Delivery units and decision rules

Implement as reviewable changes in this order: diagnostic harness; topology
and pose corrections demonstrated by that harness; material/side semantics;
clipping and depth repair; adaptive textures; HUD and acceptance records.
A stage may prove that a suspected cause needs no code change; record that
result instead of rewriting a working subsystem. Keep converter/runtime
schema changes together and regenerate all affected assets reproducibly.
SDK changes need their own focused fixtures, rebuild/install evidence and a
relink of this port. Do not silently change the sibling SDK during asset fixes.

Completion means convincing visual evidence for the entire capture matrix,
not a successful build or an improved spawn screenshot. No full DS pixel
parity or performance target is promised before measurement. Residual hardware
approximations must be identified per material/view and explicitly assessed.

## Diagnostic build progress

`SM64DS_VISUAL_DIAGNOSTICS=ON` freezes the chosen clip and frame and permits
object isolation (`SM64DS_DIAG_OBJECTS`: sky 1, castle 2, body 4, head 8),
disabling culling (`SM64DS_DIAG_NO_CULL`) and replacing texture materials
with deterministic colors (`SM64DS_DIAG_SOLID`). These options belong in a
separate build directory; regular builds retain the gameplay defaults.

A Ymir run of clip 0 frame 0 at the existing front-view route produces
`private/visual-repair-baseline/actor-isolated.png`, `actor-no-cull.png`
and `actor-solid.png`, with the respective probe JSON files. The first two
show the diagonal red artifact even when castle/sky are excluded and when
culling is disabled. This localizes the symptom to the character rendering
path; it does not distinguish texture mapping, pose or painter order. Solid
colors are currently keyed by texture, not by individual face. Full face-ID
capture, source oracle comparison and the remaining visual fixes are open.

For example, configure a separate castle build with the normal toolchain and
asset settings plus `-DSM64DS_VISUAL_DIAGNOSTICS=ON -DSM64DS_DIAG_OBJECTS=12`
for body and head. The frozen frame is selected by `SM64DS_DIAG_CLIP` and
`SM64DS_DIAG_FRAME`; values outside the exported clip are rejected at startup.

The diagnostic option `SM64DS_DIAG_FACE_IDS=ON` assigns a unique RGB555
color to each Mario body face. For face ID `i`, the low 15 bits are
`((i + 1) * 109) & 0x7fff`; decode captured RGB channels back to five bits.
The private `mario_preview_face_provenance.json` maps the ID to its source
stream, primitive, original vertices and UVs. In the front view, comparing
red pixels of the textured actor with the isolated body ID capture points to
face 113 as one prominent contributor. It is a triangle-strip face using
joint 7, with source UVs around (24.06,52.75), (22.94,51.44), (22.88,51.44).
The image correspondence is diagnostic evidence, not proof that its UVs or
projection are wrong; actor head isolation and raster coverage can affect the
comparison. A source-pose and texture oracle is still needed.

## Matrix-slot correction

The source renderer loads each display-list part's byte table into GX matrix
slots, mapping each byte through `transformBoneMap`; `0xff` preserves the
previous slot. The converter previously interpreted each GX restore operand
as a direct index into `transformBoneMap`, ignoring the part table. Mario's
14-entry table is a permutation, so numerous vertices followed the wrong bones.
The converter now applies the part table, rejects unloaded slots, and retains
slot contents on `0xff`. A synthetic three-bone regression checks reordered
slots and retention. The local ROM's isolated frozen actor capture at
`private/visual-repair-baseline/actor-matrix-fixed.png` uses the same route
and pose as `actor-isolated.png`; the diagonal bands and detached limbs are
visibly improved. Both screenshots are Ymir captures, not full DS parity.
The 43 ROM-enabled tests pass and the standard disc rebuild succeeds. Further
source traversal/state edge cases, other poses, castle appearance, clipping,
textures and performance remain open.

## Castle material-side audit

The current castle ROM has textures for every one of its 1,337 faces; the
previous generic-gray explanation does not apply to this scene. Materials 5
and 22 enable both polygon sides (35 and 13 faces respectively); the exporter
now preserves their side mask and the runtime passes it to LibSaturn. The
remaining castle materials are front-facing according to their initial flags;
this model has no GX POLYGON_ATTR writes in its streams. The two partially
translucent material alphas still need a correct approximation.

The matched `castle-sided.png` Ymir capture shows an oversized green surface
covering Mario, supporting investigation of world/actor depth ordering and
large-face subdivision. Its reported zero fallback count was invalid: the
LibSaturn scene wrapper did not expose its face queue's counters at that time.
See the later telemetry correction before interpreting older captures.

## Static subdivision experiment

`prepare_castle.py --split-edge N` optionally performs one four-way split on
faces whose maximum edge exceeds N world units. It interpolates vertex and UV
coordinates together, keeps material and side assignment, leaves collision
unchanged, and writes child-to-source indices privately. Synthetic triangle
and quad tests check area and UV continuity. Normal builds do not enable it.

At threshold 128, the castle grew to 1,943 faces and 1,816 texture tiles.
Although the disc linked, Ymir hit a capacity panic during font initialization,
so this configuration is not acceptable. Moving the larger scene queue to Low
WRAM solved the link constraint but did not solve VDP1 texture allocation.
At threshold 192 the build and capture succeeded, but the green surface still
covered Mario in the matched front view. The hypothesis that a generic
one-pass split alone would resolve this view is therefore unproven. Identify
the responsible face and reduce texture residency/slot pressure before
repeating targeted subdivision. Captures and reports are in
`private/visual-repair-baseline/castle-split-{128,192}*` and generated test
assets are in `private/castle-split/`. The standard disc remains unsplit.

## LibSaturn splitter and reusable inspection tools

A new opt-in `--sdk-split-grid` path calls LibSaturn's
`model_pipeline.intersections.split_by_plane` on static triangles, preserving
UVs and source-face IDs. `--split-radius` bounds the experiment around spawn;
`--libsaturn-source` selects the existing checkout. This reuses the SDK
implementation rather than copying its plane-clipping algorithm. The SDK's
HLOD/QEM adapter remains available for future whole-scene reduction; its WLH1
output still needs post-simplification texture baking and runtime residency.

A 64-unit grid within 48 units of spawn produces 1,428 faces and 1,301 castle
tiles. It builds and the Ymir capture `castle-sdk-split.png` runs with zero
sampled skipped faces; the reported fallback count was invalid. Mario's lower body is more visible, but white
slivers appear in the ground. The input replay was time-driven and the camera
angle differs slightly, so this is not a controlled visual acceptance or a
production change. Fix split-edge coverage and compare fixed camera state;
then measure all routes and full texture/command limits before enabling it.

`tools/inspect_face_capture.py` decodes diagnostic RGB555 screenshots and
looks up source face provenance; `tools/inspect_model_materials.py` reports
source material flags and usage. Both replace one-off inspection snippets.
The face-ID screenshot identifies faces 680, 685, 686 and 721 near the spawn
foreground, which supports targeted experiments without splitting every face.

## Fixed-camera split comparison

`SM64DS_DIAG_FIXED_CAMERA=ON` resets the player to spawn each frame and fixes
camera yaw/zoom through `SM64DS_DIAG_YAW` and `SM64DS_DIAG_CLOSE_CAMERA`.
It is available only in visual diagnostic builds; movement is intentionally
disabled there. `fixed-unsplit.png` and `fixed-split.png` use the same camera,
idle pose, scene configuration and Ymir field. The split shows Mario's feet,
where the unsplit ground covers them, but introduces a white sliver on the
left hillside. The split is still disabled in production.

`tools/audit_castle_split.py` reuses the SDK adapter to compare each source
face's area against its generated pieces and report degenerates. For the
64-unit / 48-unit-radius experiment it reports no zero-area pieces and the
largest relative area difference is under 1.4e-10. This checks geometry in
3D, not VDP1 edge coverage or texture transparency; those remain likely
areas to inspect. The corresponding private JSON is `sdk-split-audit.json`.

## Source alpha and white overlay

A matched face-ID capture traced 284 white pixels in the hillside region to
split face 873, originating from source face 800, material 20. That material
has polygon alpha 12/31. The prior white sliver is therefore an opaque
rendering of a partially transparent source polygon, rather than evidence
of missing split geometry. Castle materials with alpha 12 or 15 now use
VDP1 mesh coverage (roughly half coverage), while alpha 31 remains opaque.
This is an approximation: indexed VDP1 pixels cannot generally alpha-blend
with a previously drawn VDP1 pixel, the two source alpha values are not
reproduced exactly, and near-plane fallback remains a solid color. The same
fixed split capture (`fixed-split-alpha.png`) shows a dithered overlay instead
of a solid white stripe. The split remains experimental.

The face inspection tool accepts a matching textured `--reference`, an RGB
threshold and a child `--origins` map to reproduce the face-800 diagnosis.
The local Tekken port confirms use of SDK per-face side masks and explicitly
selected material modes; its PS1-specific blending does not establish DS
alpha semantics. No LibSaturn defect was established by this experiment.

## Local split promoted for spawn

The 64-unit SDK grid split around spawn is now enabled by `build-castle.sh`.
This supersedes earlier statements that the split is disabled. A fixed-camera
comparison showed Mario's feet, and the 790-field controls and 650-field wall
Ymir replays passed with zero sampled skips/panics and zero misaligned accesses.
The controls route recorded 72 completed draws vs 79 in a separate unsplit
replay. Input is polled per completed draw, so these are not exact frame-by-frame
performance comparisons. The local split does not solve ordering elsewhere;
complete camera and texture acceptance remains open. Black HUD backings improve
contrast in light scenes. Experimental builds can still select other settings.

## Adaptive texture bake experiment

`prepare_castle.py --adaptive-faces 48 --texture-budget 98304` evaluates
8x8 versus 16x16 source samples and assigns larger bakes to the faces with the
largest color error. The allocator rechecks actual indexed, deduplicated pixel
bytes against the budget and has a synthetic detail/budget regression. It is
opt-in; the normal build still uses 8x8 castle tiles.

The split-castle experiment chose 48 faces and used 91,200 pixel bytes in
1,302 textures, up from 83,264 bytes in 1,301 textures. Both the front and
castle-facing fixed Ymir captures booted. The matched castle-facing images
`castle-8-control.png` and `castle-adaptive.png` show little obvious detail
improvement and a visible palette shift. The current scoring ignores projected
screen importance, and palette quantization weights the larger tiles more
heavily. Do not enable this policy until priority and palette error improve
across representative camera views and the resource/route gates pass.

## Source draw traversal

The converter now traverses each bone record's material/display-list bindings
in the order used by `ModelComponents::Render`, preserving repeated bindings
and skipping materials whose source hidden bit is set. Previously it sorted
by display-group number, deduplicated repeated bindings and fabricated a draw
for unreferenced groups. Castle's source order begins with groups 8, 0, 2, 9;
its old conversion began 0, 1, 2, 3. Retaining traversal also makes preserved
GX matrix slots follow the actual source sequence. A synthetic test covers
order, repeats, hidden bindings and invalid references; all 48 ROM-enabled
tests pass, including the full BMD parse audit. A fixed-camera Ymir capture
`castle-source-order.png` boots and appears comparable to the earlier view;
this alone does not prove painter parity. Face numbering changes when source
traversal changes: use the provenance file generated alongside each capture,
not earlier face IDs with new assets.

## Filtered castle texture bakes

The 8x8 point-sampled brick bakes amplified source repeats into high-contrast
checker noise. `bake_face` now supports 2x2 or 4x4 subtexel sampling using
alpha-weighted RGB, and `build-castle.sh` uses 4x4 for the castle. A synthetic
fixture checks averaging and prevents RGB from transparent pixels bleeding
into opaque color. `tools/export_material_preview.py` renders private source
textures and face-bake contact sheets for inspection.

The fixed-camera `castle-filtered.png` shows reduced wall noise compared with
`castle-source-order.png`. The current build uses 82,816 castle pixel bytes
and 1,294 tiles, with no runtime filtering cost. The 790-field Ymir controls
replay completed 72 draws, one jump, three landings, two resets, no sampled
skipped faces or panic and zero misaligned accesses. This does not restore
fine brick detail, prove all cutout materials, or close other visual gates.

## Pose conversion and ground offset

`tools/audit_pose_conversion.py` compares parent-first source Euler transforms
with quantized quaternion transforms at every integer frame of the four
exported Mario clips. The largest rigid vertex difference is about 0.00144
model units. This floating-point host comparison excludes blended vertices and
does not measure SH-2 fixed-point arithmetic, fractional frames or head
attachment. The ROM-derived report is kept privately as
`pose-conversion-audit.json`.

The same audit shows that the source body's lowest vertex varies by about
1.03 units over walk and 4.24 units over run. Previously the game offset the
whole actor by the current pose's lowest vertex every frame, cancelling this
foot lift and moving the head with it. The actor now keeps the initial idle
pose's ground offset throughout animation and jumping. The source poses can
still put a foot slightly below the ideal floor; sequence-level visual review
and source gameplay comparison are needed to assess this approximation.

The rebuilt disc passed the 790-field Ymir controls route: 72 completed draws,
one jump, three landings, two resets, no sampled skips or panic, and no
misaligned accesses. All 50 ROM-enabled host tests passed. These checks do
not establish pose or collision parity on hardware.

The material audit tool also reports texture-generation modes and normal
command counts. The castle's used materials are textured and use explicit UVs
or UV matrix generation; generic gray substitution does not explain its
current surfaces. Source cutout, lighting and visibility still need visual
validation.

## Clipping telemetry correction

LibSaturn's `sat_scene_stats` previously read wrapper counters that were reset
but never populated from the face queue. Its reported culled, clipped and
fallback values were therefore always zero. The SDK now exposes live queue
counters, retains them after flush, and resets them on the next begin; a host
scene API fixture covers those transitions. The rebuilt SDK archive used for
these captures has SHA-256
`1018bd76718ef25874cc64c17e48a7586af6627bd030f4ad3082cca4baaed45b`.

In the 790-field controls replay, the last sampled frame reports 804 culled
faces and 325 clipping candidates: 51 sky, 274 castle, zero body and zero
head. A separate sample at field 300 reports 407 candidates: 51 sky and 356
castle. The SDK's `fallback_faces` counts entries sent to the slow path, not
confirmed visible flat-color polygons: a candidate can still draw textured or
be fully offscreen. Candidate counts thus identify where to investigate, not
how many visible defects occurred. Zero skipped faces and no panic were
observed at these samples; both replays had zero misaligned accesses, and the
full controls route completed its jump, landing and reset checks. The capture
checker reads per-object candidates from the matching current ELF and WRAM.

## Foreground clipping refinement

The diagnostic option `SM64DS_DIAG_CASTLE_FALLBACK_COLOR=ON` makes the
castle's flat-color fallback magenta without changing its textured sprites.
Matched fixed-camera captures at spawn revealed a large visible fallback in
the foreground. Comparing the highlight with a face-ID capture identified
source ground faces 169, 170 and 175 as the main contributors. Diagnostic
solid-color geometry can change coverage at edges, so this correspondence is
evidence for targeting the split, not exact per-face pixel accounting.

`split_nearby` can now use a finer grid for selected source faces while
retaining the original split elsewhere. The normal build uses a 32-unit grid
for those three faces and the previous 64-unit grid within 48 units of spawn
for the rest. `tools/castle_refine_faces.json` validates each selected face's
vertices and provenance before conversion, so changed source traversal fails
clearly instead of refining unrelated geometry. In the matched spawn view,
`tools/compare_fallback_captures.py` measured 19,095 highlighted pixels in
the previous build and 460 after targeted refinement, within the 320x185
region below the HUD. A wider 32-unit split gave 444 pixels but increased the
castle to 1,808 faces and dropped the controls replay to 60 completed draws.

The targeted build has 1,467 castle faces and 85,312 texture pixel bytes,
compared with 1,428 faces and 82,816 bytes previously. The SDK geometry audit
found no degenerate pieces and a maximum relative source-area difference below
1.4e-10. The 790-field controls replay completed 72 draws, one jump, three
landings and two resets; the 650-field wall replay completed 60 draws and
recorded wall contact. Both had no sampled skipped faces or panic and zero
misaligned accesses. The ROM-enabled host suite passed all 50 tests, including
a refinement UV/provenance fixture. Capture matching applies only to this
camera and pose; remaining clipping, other viewpoints, frame-time variance and
physical-hardware behavior are still open.

## Spawn camera orbit refinement

Fixed-camera highlight captures at yaw 90, 180 and 270 degrees revealed large
flat fallback regions missed by the castle-facing view. Face-ID captures
identified additional ground and path faces; the validated refinement
manifest now lists ten source faces. Most use a 32-unit grid, with 16-unit
overrides for source faces 177 and 212 where the close camera still crossed
large pieces. Each manifest entry is checked against source vertices and
provenance, and the SDK splitter retains per-face UVs and material IDs.

In the 320x185 region below the HUD, matching normal-zoom captures at yaw
0, 90, 180 and 270 show 471, 609, 0 and 678 magenta pixels respectively.
Before the expanded refinement, the last three views showed 12,206, 14,422
and 13,039 pixels. The close yaw-180 view fell from 15,829 to 1,239. These
are highlight-color measurements at spawn, not complete scene coverage or
proof that remaining pixels are all visible defects. The source-area audit
reports no degenerate pieces and maximum relative area error below 1.3e-10.

The current castle has 1,577 faces and 92,288 texture pixel bytes. The
790-field controls replay completed 68 draws, one jump, three landings and two
resets; the 650-field wall replay completed 55 draws with wall contact. Both
sampled frames had no skipped faces or panic, and both probes reported zero
misaligned accesses. The preceding smaller split produced 72 and 60 draws on
those routes; cadence affects input polling, so the measurements do not prove
a precise performance delta. All 50 ROM-enabled host tests pass. Other camera
positions and angles, cutout coverage, moving sequences, and hardware remain
unverified.

## Filtered adaptive bake and live texture arena

The optional adaptive baker now uses the same filtered samples as the regular
build and chooses its palette from the low-resolution reference bakes. This
prevents higher-resolution tiles from changing the palette weighting. It can
also accept per-face importance counts from isolated face-ID captures using
`tools/capture_face_priorities.py`; these counts apply only to the matching
generated geometry and capture views. They are an experimental heuristic,
not a whole-level screen-coverage estimate.

An 80-face castle-focused experiment used 107,584 castle pixel bytes and
booted with 6,368 bytes of VDP1 texture arena remaining. A 128-face version
at 116,928 bytes exhausted the arena during font allocation. The old check
only compared model estimates to a fixed 440 KiB threshold, omitting the font
and the actual arena capacity. The runtime now checks the live free arena
against aligned model estimates, all 96 8x8 font glyphs, and a 2 KiB reserve
before uploading assets. It records initial free bytes, estimated usage, and
remaining bytes after uploads in capture telemetry.

The regular build uses 338,752 estimated bytes of its 360,416-byte initial
arena and measured 21,664 bytes remaining after upload. Its 790-field controls
route passed with 68 completed draws, no sampled skipped faces or panic, and
zero misaligned accesses; all 50 ROM-enabled host tests passed. The compact
adaptive capture shows no global palette shift, but wall-detail improvement
is not yet convincing enough to justify the smaller reserve and unverified
other views. It remains opt-in and is not in the normal build.

## Material texture flags and pose samples

The source engine ORs each material's TEXIMAGE_PARAM with its texture record
before binding it. The converter previously combined wrapping bits only;
it could miss palette-index-zero transparency or other texture state supplied
by the material. Decoding and the cache now use the combined flags, including
the effective texture generation mode. A synthetic 2-bit indexed texture test
checks that material-provided index-zero transparency and mirrored wrapping
are preserved. `tools/inspect_model_materials.py` reports both raw flag
words and the effective zero-transparency state.

For the current ROM's castle, body, head and sky, no material supplies the
index-zero transparency bit independently of its texture record. Generated C
assets for all four are byte-identical to the preceding build, so this fix
does not claim to change the current castle image. The rebuilt controls route
passed, with 68 draws, no sampled skips or panic, and zero misaligned accesses;
all 51 ROM-enabled host tests pass.

Isolated Ymir captures at idle frame 0; walk and run frames 7 and 15; and jump
frames 6 and 12 show connected limbs and head in those samples. They are not
an original-game reference, a complete animation sequence, or proof of
correct depth ordering. The SDK has multiple optimized depth-key paths;
triangle centroid sorting needs a matched overlap test and consistent
coverage of those paths before changing the renderer.

## Distorted-sprite triangle fixture

`SM64DS_BUILD_SPRITE_FIXTURE=ON` adds a ROM-free-data Saturn target. Its
texture is generated by `tools/make_sprite_fixture.py` through the actual
`bake_face` pipeline from an asymmetric 8x8 color grid, then displayed as a
distorted sprite with the last two vertices collapsed. The reusable
`tools/check_sprite_fixture.py` compares interior framebuffer samples with an
independent affine triangle reference, excluding edges and texel boundaries.

The 320x224 Ymir capture at field 159 matched the expected texel at 5,319 of
5,332 sampled pixels; all samples were within one source texel in either
channel. This confirms the mapping for this axis-aligned, screen-space
triangle in Ymir, within the finite bake/raster sampling tolerance. It does
not prove perspective-correct mapping, all triangle orientations, other
emulators, or physical VDP1 behavior. A host fixture now checks the output
corner order and unique UV associations for triangles, quads, triangle
strips and quad strips. All 52 ROM-enabled host tests pass.

## Castle entrance clipping

Fixed-camera diagnostics now accept player X/Z and a floor-search ceiling.
The ceiling matters at the doorway: the previous 512-unit search chose a
roof above the walkable surface, so those initial captures were discarded.
Using a 100-unit ceiling selects the same approximately 50-unit floor as the
wall route. In matched doorway captures, the flat-fallback highlight exposed
large entrance walls and floor faces. Selected faces can now be split on the
Y axis as well as X/Z, preserving source UVs and materials.

The validated refinement manifest includes 14 additional entrance faces. In
the 320x185 region below the HUD, highlighted pixels fell from 5,541 to 52
at X=0/Z=0 facing the entrance, from 35,022 to 2,976 at X=0/Z=-63 facing the
door, and from 29,670 to 5,304 at the same point facing back. These are fixed
Ymir screenshots, not full route coverage. The source-area audit found no
degenerate pieces and a maximum relative area error below 3.6e-10; the host
fixture checks UV interpolation on a vertical wall.

The current castle has 1,665 faces and 97,920 texture pixel bytes; the live
texture arena has 16,032 bytes free after upload. The controls replay passed
with 65 completed draws, one jump, three landings and two resets. The wall
replay passed with 54 draws and wall contact. Both sampled frames had no skips
or panic, and both probes reported zero misaligned accesses. All 52 ROM-enabled
host tests pass. The reverse door view also exposes a separate camera issue:
collision can move the camera to roughly two units from its target, clipping
Mario and the adjacent surfaces. Further camera and moving-view work remains.
