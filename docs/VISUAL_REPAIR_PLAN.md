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

## Priorities from the matched DS and Saturn captures

The rear, side and front pairs in
`private/castle-comparison-fixed/direct/comparisons.png` share the same Mario
position and facing, camera eye and target, and approximately 46° vertical
FOV. They are three directions from one position. The Saturn captures used
`private/castle-refined`, an older 1,467-face export. The normal build uses
the expanded refinement manifest and a separate texture allocation. The
current sheet also displays the DS image at 256×192 inside a larger cell and
the Saturn image at 320×224. Use the sheet to identify visible defects, and
measure silhouettes and landmarks on a common 4:3 image grid.

| View | Visible differences |
| --- | --- |
| Front | A flat yellow-green patch covers almost all of Mario. The DS reference shows his full body and ground shadow. |
| Rear | Mario is visible. The path becomes broad flat shapes, the castle doorway loses its dark opening and brick definition, and there are bright dithered patches on the lawn. The reference also shows trees and a sign. |
| Side | Mario is visible. The path has a hard flat color boundary, the background has angular blue and white patches, and the reference tree and Mario's ground shadow are absent. |

**Front-view diagnosis.** Straight rays from the captured front camera to
Mario's centerline at foot height and at offsets of 1, 3, 6, 9, 12, 15 and
18 world units hit no exported castle triangle before reaching their sample
points. The foot ray reaches path face 589 (source face 477) just past Mario's
feet, where the render surface is at Y=16.25 and Mario's feet are at Y=16.256.
That face's corners span camera depths of roughly −7.7 to 96.5 units, crossing
the near plane at depth 1. Mario's foot depth is 56.6 units, while the face's
four-corner average is 35.0 because the near triangle corner is counted
twice. LibSaturn sorts by the average and can draw a clipped face as flat
color. A shallow sort key can therefore make the renderer draw the path over
Mario even where the actual surface lies behind him. The same large triangles from source faces 477,
478 and 503 are present in the normal build's generated mesh. These are
candidates for the exact covering face. The centerline samples do not cover
the whole silhouette, and the current captures do not record the face that
actually wrote the affected pixels.

| Priority | Work | Acceptance |
| --- | --- | --- |
| 0 | Capture the normal build's generated assets at the same three poses. Normalize both active images to one 4:3 grid before making crops. Save the generated scene report and matching ELF/SDK identifiers alongside telemetry. Add a second fixed position on the approach after the first three views reproduce. | Camera and Mario state still match. Compare projected landmarks and actor silhouette on the common grid. Keep the prior images for the before/after record. |
| 1 | At the matched front camera, capture body/head in isolation, castle face IDs, and magenta fallback. Resolve the covering pixels to a source face, then capture its projected depth range and emission order. If the path triangles are confirmed, use targeted subdivision with interpolated UVs first. If the overlap survives, inspect the clipped-piece sort key before changing the SDK. | Front view shows Mario down to his feet. Real walls still occlude him on the wall route. Rear and side views retain coverage, and the approach shows no new cracks or flicker. |
| 2 | Improve the path and castle entrance. Measure visible fallback pixels with the magenta pass. Once fallback is reduced, separate doorway visibility from brick sampling by inspecting face IDs and UV bakes. Use the existing adaptive baker to spend remaining memory on visible path and wall faces. | The path retains continuous texture through camera turns, and the doorway reads clearly from the rear view. Before/after captures isolate the effect of each change. Record command counts, live VDP1 memory and completed draws on the controls and wall routes. |
| 3 | Capture sky only in the side view and check whether the angular patches come from shell coverage or flat fallback. Compare a dedicated background layer if the shell remains costly. Confirm whether the lawn dither comes from the existing VDP1 mesh approximation before changing material settings. | The side horizon stays continuous through the orbit and lawn overlays have no bright checker patches in the matched views. Record any remaining approximation and its memory cost. |
| 4 | Add a small ground contact shadow that follows the collision floor, with a height check for jumps. Audit separately loaded scene props to account for the trees and sign visible in the DS captures. Compare Mario's head and body in isolation once projection is normalized and the front obstruction is gone. | Ground contact reads from all three views. The shadow respects terrain and walls. Any remaining pose or silhouette difference can be tied to an isolated capture. |

The matched captures record 246, 359 and 94 castle clip candidates for rear,
side and front respectively. These are queue counts, not the number of visible
fallback pixels. All three sampled frames have zero skips or panic and
28,640 bytes free in the texture arena for the older export. Use new telemetry
for the normal build when choosing memory and command budgets.

The current generated assets were subsequently captured at the same three
poses in `private/castle-comparison-fixed/current/`. The front obstruction
persists. The fallback highlight makes the covering path magenta, and the
face-ID image resolves pixel (155,145) to render face 699, source face 477.
An attempted 16-unit split of that source face changed the generated face
count and failed the adaptive baker's priority-array length check. The
manifest was restored and the normal castle build regenerated successfully.
The priorities must be regenerated or mapped to the new split faces before
that candidate can be captured and evaluated.

An isolated candidate maps the existing priorities by source face, retaining
the original ordering for every unchanged source and assigning face 477's
uniform priority to its 55 new pieces. The manifest and mapped priorities are
saved in `private/castle-split-candidate/`. The 16-unit split raises the scene
from 1,665 to 1,719 render faces. At 128 high-resolution faces it exceeds the
texture arena; the candidate uses 64. Matched captures are in
`private/castle-comparison-fixed/split-candidate/`. In the front image Mario's
body and feet are visible where the previous path patch covered them. Rear,
side and front captures report respectively 930, 594 and 299 commands, zero
skips, and 7,520 bytes of texture arena remaining; each reports zero misaligned
accesses. These static views support the sort-order diagnosis but do not yet
establish the wall-occlusion or moving-camera acceptance criteria. The split
and reduced texture allocation have therefore not been promoted to the normal
build. Capture configuration now explicitly disables face-ID and fallback
diagnostics so cached CMake settings cannot contaminate comparison images.

The candidate was also built without visual diagnostics and replayed on the
790-field controls route and a 940-field wall/orbit route. The controls run
completed 63 draws, one jump, three landings and two resets; the wall run
completed 80 draws and recorded 978 wall responses. Both ended grounded,
with zero sampled skips, no panic, 7,520 texture bytes free, and zero reported
misaligned accesses. Screenshots, matching ELFs and telemetry are under
`private/castle-split-candidate/routes/`. The orbit screenshots show Mario
near the door, but some views also expose the previously observed camera and
wall clipping; they do not prove that a wall between the camera and Mario
occludes him correctly. A normal-geometry wall replay also passed (82 draws,
1,002 wall responses, 2,592 bytes free). Its camera yaw differs at the same
field because render cadence affects input polling, so these route screenshots
are not matched-pose visual comparisons. A controlled occlusion pose and an
approach orbit remain necessary before promoting the candidate.

Four static 90-degree orbit samples at the matched spawn are saved under
`private/castle-split-candidate/poses/`; all completed with zero sampled
skips, with 949, 387, 306 and 456 commands. These are separate viewpoints,
not a continuous moving-camera test. A proposed fixed doorway occlusion pose
puts a source triangle between the camera and Mario, but that triangle is
single-sided and the camera sees its back. Mario remains visible in both the
baseline and candidate captures, so this pose is not a valid test of
front-facing wall occlusion. Reversing the pose failed to find a walkable
floor at the chosen point. The controlled wall acceptance criterion remains
open. The comparison script also resets its floor ceiling explicitly so an
earlier diagnostic build cannot silently change the matched player height.

The new `SM64DS_DIAG_ORBIT_PLAYER` mode holds Mario at the matched position
while normal L/R input moves the collision-aware camera. A 760-field replay
with the candidate completed 55 draws, ended with zero sampled skips or panic,
and reported zero misaligned accesses. The sampled field 600 shows Mario partly
covered again. A fixed capture using the recorded camera pose, with an
actor-only comparison and castle face IDs, attributes 136 overlapping actor
pixels to candidate render faces 718, 719 and 720, all pieces of source face
477. Thus the 16-unit subdivision improves the original front view but does
not resolve the painter-order defect through the orbit. Captures, matching
ELFs and telemetry are in `private/castle-split-candidate/poses/`; the replay
is `private/castle-split-candidate/orbit.pad`. The candidate remains
experimental. Investigate the clipped-piece depth sort or a finer targeted
split with a measured texture and command budget before promotion.

An 8-unit split of source face 477 creates 161 pieces and increases the scene
to 1,825 faces. At 64 high-resolution faces it fails the VDP1 arena preflight;
at 32 it boots with 3,488 bytes free. At the fixed field-600 pose, comparing
the actor-only mask against face-ID renders attributes 92 actor pixels to
source 477, down from 136 with the 16-unit split, but the obstruction remains.
That comparison uses the same actor and camera pose, and its face-ID pass
recorded 499 commands and no sampled skips. Candidate assets and inputs are
in `private/castle-fine-candidate/`; the matching capture and ELF are named
`orbit-600-fine-face-ids` under the poses directory. Neither finer split nor
the loss of texture quality is justified for the normal build on this evidence.

The installed LibSaturn scene implementation constructs the painter key from
the four original projected corner depths when a face is queued, including
faces that will later use clipped fallback. It does not recompute that key from
the clipped visible piece. This is a plausible contributor, but the current
evidence does not establish whether clipping or painter ordering of otherwise
visible triangles accounts for every overlapping pixel. Avoid applying a
global actor depth bias: it could draw Mario through walls. Instrument the
identified pieces' clip status and queued depths against the actor before
choosing a sort change.

For the recorded field-600 pose, source-477 pieces 718, 719 and 720 have
camera-space corner depths of respectively 52.5–64.3, 44.0–64.3 and
44.0–64.3 units. All corners are beyond the one-unit near plane. Their
four-corner mean depths are 57.6, 52.0 and 53.3, while Mario's centerline
spans roughly 61.7 at his feet to 56.6 at height 12. These pieces can
therefore sort in front of Mario despite covering ground behind his silhouette;
the duplicate fourth corner of each triangle also affects the mean. This
sample is a face-level painter-order problem, not a near-plane clipping
problem. Correcting clipped-piece keys alone would not fix it. A repair needs
to handle intersecting screen-space depth ranges without overriding genuine
wall occlusion.

The overlap measurement can be repeated with
`python3 tools/measure_castle_occlusion.py ACTOR_ONLY.png FACE_IDS.png ORIGINS.json`.
The images must use the same camera and actor pose. The tool ignores unchanged
actor pixels, which can otherwise be mistaken for encoded face IDs. A changed
pixel assigned to a castle face is still only an overlap: foreground geometry
may legitimately hide Mario, and an actor pixel with exactly the same colour
as the face-ID pixel is not counted. For the recorded orbit pose it reports
136 source-477 overlaps for the 16-unit candidate and 92 for the 8-unit
candidate. These numbers are diagnostics, not an occlusion correctness gate.

The SDK's runtime plane splitter accepts solid materials only; it rejects
textured faces because it cannot preserve their texture coordinates. Thus
splitting a textured ground face at Mario's moving bounds requires new
textured rendering support, or an offline split fine enough to support a
provably correct local ordering. Neither has yet been demonstrated within the
VDP1 memory budget. Do not enable an unconditional player or ground sort bias
as a substitute: it cannot distinguish foreground from background.

For the recorded orbit pose, an additional body-only face-ID capture and its
projected-vertex WRAM dump are saved as `orbit-600-actor-ids` alongside the
castle face-ID capture. `tools/analyze_castle_depth.py` compares the two
using perspective-correct depth interpolated from the projected triangles.
It classifies 76 source-477/body pixels as ground behind the body, one as
ground in front, and leaves 59 outside its projected-triangle approximation.
The apparent front/behind crossing in one face pair is within 0.06 world
units and must not be treated as proof of a real intersection: pixel coverage,
integer projection and distorted-sprite rasterization can move the result.
The tool does not inspect the head or near-clipped polygons. This provides
stronger evidence of the bad order, but is not a complete visibility oracle.

An opt-in depth-key experiment (`SM64DS_DIAG_FAR_DEPTH_FIRST` and
`SM64DS_DIAG_FAR_DEPTH_COUNT`, diagnostics only) replaces the ordinary mean
depth of selected queued castle faces with their farthest corner depth. With
the 16-unit candidate and render faces 718–720, the fixed field-600 capture
reduces measured source-477 overlaps from 136 to zero; the face-ID capture
uses 393 commands with no sampled skips. The corresponding textured capture
is `orbit-600-far-depth-textured.png`. This is a controlled experiment, not a
general solution: those IDs belong only to this asset build, and farthest
corner depth is not a visibility proof.

Four fixed orbit samples at 0, 90, 180, and 270 degrees changed source-477
overlap counts from respectively 4 to 1, 112 to 0, 65 to 0, and 0 to 0.
The face-ID images also changed 36, 132, 244, and 109 pixels outside the
actor silhouette, respectively; in these samples both the old and new IDs
map to source 477. Those changes show the experiment reorders ground pieces
against each other as well as Mario. They do not establish that other camera
poses preserve walls, foreground ground, or texture seams. Captures are under
`private/castle-split-candidate/poses/orbit-test-*`. Leave the count at zero
in normal and matched-reference builds until a geometry-based rule and its
occlusion regressions are demonstrated.

A second opt-in experiment (`SM64DS_DIAG_GEOMETRIC_DEPTH`) gates a depth-key
adjustment on projected triangle comparisons. The fixed-point comparator in
`runtime/sm64ds_painter.c` clips the screen-space triangle intersection and
checks perspective-correct depth at its vertices. It returns ambiguous for
crossing or nearly coincident depth planes. Its host tests include thin
triangles, where clipping roundoff can otherwise produce the wrong answer.
The comparison is geometric only: VDP1 coverage, near-clipped geometry,
textured-quad interpolation, and effects on third faces still need treatment.

At the recorded orbit pose this conservative experiment leaves all 136
source-477 overlap pixels unchanged. It considers all actor triangles,
including backfaces, and rejects the selected ground pieces if any comparison
is ambiguous or in front; this is too conservative to repair the case. The
capture and telemetry are `orbit-600-geometric-depth-face-ids`. This result
supports investigating visible-face constraints or further subdivision; it
does not justify enabling the rule. The geometry experiment is off by default.

The per-body-face experiment initially reduced the recorded overlap from 136
to 33, but an independent body-face-ID comparison found 32 pixels that had
matched the isolated body before the change and no longer matched. Expanding
its self-order guard to cover shared and adjacent VDP1 vertices rejected the
changes in this pose. It is therefore not a viable repair as currently built.

A separate opt-in support-plane experiment (`SM64DS_DIAG_SUPPORT_DEPTH`) uses
the fact that a horizontal ground plane cannot lie strictly between a camera
above it and actor vertices on or above it. For the 55 split pieces of source 477,
with the experimental scenery guard enabled, the orbit-600 source-477 count
falls from 136 to 23. A body-only face-ID comparison found 89 newly matching
pixels and no previously matching pixels lost in that pose. The guard uses
conservative projected bounds and ignores selected coplanar pieces; it is not
a proof that all scenery ordering or texture seams are preserved. Four fixed
orbit samples changed source-477 overlaps 4→4, 112→29, 65→6, and 0→0. The
first two changed 119 and 26 pixels outside the actor mask, respectively; in
the face-ID captures both old and new IDs map to source 477. The remaining two
had no outside-mask changes. These captures are `orbit-test-*-support`.

In the 400-field orbit-600 face-ID probe, the support experiment completed 24
rendered frames versus 29 in the baseline, with no sampled skips in either.
Those counts are a diagnostic workload comparison, not a general frame-rate
measurement. This prototype still selects asset-specific face IDs, has not
validated wall or jump occlusion, and cannot yet be enabled as the normal
renderer. Its bucket separation is also heuristic rather than derived from
the SDK sort's actual buckets.

The current automatic diagnostic replaces that heuristic with the SDK's
bucket calculation, including pass-group shares and stable submission order.
It preserves the original bucket extrema and checks whether changing a ground
key would reverse the draw order of another queued scene face. The helper's
bucket results were compared with LibSaturn over 1,000 generated queues. A
two-pixel-padded triangle separation test avoids treating disjoint triangles
as blockers merely because their bounding rectangles overlap; near-clipped
faces remain conservative blockers. The guard ignores coplanar pieces with
the same original source face, so their shared texture edges can still change.

`prepare_castle.py` now emits the private `castle_face_source` array so the
automatic diagnostic can find support faces without hard-coded render IDs.
The independently regenerated candidate is `private/castle-support-auto`.
In the orbit-600 capture, the automatic version maps 324 of 324 queued castle
faces and reduces source-477 overlap from 136 pixels to zero. Across fixed
orbits 0, 90, 180 and 270 degrees, the respective counts are 4→4, 112→0,
65→0 and 0→0. The 90- and 180-degree face-ID captures change two and 174
pixels outside the actor mask; both IDs map to source 477. In the corresponding
180-degree textured captures, 47 outside-mask pixels differ, each by at most
8 RGB channel levels. These are not a comprehensive texture-seam audit.

The corrected moving-camera orbit ran 760 fields, with 60 completed draws,
no sampled skips, and no misaligned accesses. Diagnostic counters recorded
148 support-key changes and no mapping failures. A 790-field controls replay
and a 940-field wall-contact replay also passed their endpoint checks; these
checks do not inspect every rendered frame. A controlled front-facing castle
wall view retained all 406 measured wall pixels covering Mario. A separate
narrow solid wall fixture at the failing orbit pose retained all 568 wall
pixels covering Mario while source-477 overlap fell from 11 pixels to zero;
the correction was active in that fixture. The latter can be checked using
`tools/check_support_capture.py` with `--wall 248,0,248` and an appropriate
`--min-wall-on-actor`. A fixed raised-player view was unchanged in this sample.
The raised and wall poses are controlled rendering tests, not full gameplay
coverage.

In the fixed 400-field release probe, the original and automatic captures
completed 40 and 36 draws respectively. The automatic implementation is still
diagnostic-only: it needs broader moving/jumping and wall coverage, performance
work, and an explicit decision about seams before it can replace normal
rendering. The support rule depends on the bucket behavior of the installed
LibSaturn implementation; the host SDK comparison should be rerun when that
implementation changes.

The generated candidate now includes a fixed-point flat-face index: 274 of
1,719 render faces need consideration by the support-plane scan. The runtime
still verifies the transformed vertices are flat, and older generated assets
fall back to scanning the configured range. The orbit-600 source-477 overlap
remains zero after this change. In the same 400-field release probe the
automatic version still completed 36 draws, so this change does not establish
a measurable improvement to that overall frame rate.

With diagnostic pose freezing disabled, the 790-field controls replay and
940-field wall replay passed their endpoint checks, with 56 and 73 completed
draws respectively, no sampled command skips, and no misaligned accesses.
The controls replay registered one jump and three landings. Support diagnostics
recorded no mapping failures in either replay; the wall replay recorded 25 key
changes and 24 guard blocks, while the controls replay recorded no key changes.
These are endpoint and counter checks, not a frame-by-frame visual validation
of animation, jumping, or occlusion.

The reproducible animation matrix is `tools/capture_support_animation.py`.
It renders actor-only, uncorrected and corrected views of idle, walk, run and
jump poses from two camera angles, saves matching ELF/WRAM diagnostics, and
reports face-ID overlap and outside-actor changes. `--player-y 22 --poses
3:0 3:6` samples raised jump poses; frozen jump poses at ground level are not
a substitute for airborne gameplay. `--textured` measures visible texture
differences instead of decoding face IDs. The matrix samples poses; it is not
exhaustive frame-by-frame gameplay coverage.

The former four-pixel angle-0 overlap was caused by a conservative blocker:
a face crossing the near plane lay far outside the actor. The guarded test now
projects the SDK's near-clipped pieces before deciding whether that face can
overlap. In matched idle captures, source-477 overlap changes from 4 to 0 at
angle 0 and from 65 to 0 at angle 180. The narrow wall fixture still retains
all 568 wall pixels. For the sampled walking and grounded jump poses, some
animated vertices sit approximately 0.3 units below the collision floor; the
whole-plane rule deliberately refuses to reorder those cases. The experimental
`SM64DS_DIAG_GROUND_POSE` lifts a grounded pose only when its body dips below
the idle floor and preserves positive foot lift and airborne animation. With
that option, the 16 sampled angle/pose combinations show zero source-477
overlap. Raised frozen jump samples at both angles also show zero. This pose
adjustment is diagnostic-only pending slope and gameplay validation.

The face-ID captures still show changes outside the actor (for example 141 at
angle 0 and 174 at angle 180 in idle); the IDs on both sides of those changes
map to source 477. A triangle-versus-actor-bounds filter did not reduce these
changes and was removed. The seam problem remains open.
In corresponding textured idle captures, 37 and 47 pixels outside the actor
change at angles 0 and 180 respectively, with a maximum channel difference of
8 on the 0–255 capture scale.
The optional `--stitch-source 477` bake experiment averages corresponding
opaque texels on exactly shared triangle edges before palette indexing. In
the two textured idle captures it reduces those changing pixels from 37 to 9
and from 47 to 5, respectively, without increasing the generated texture
budget. Relative to the unstitched baseline, 997 and 1,519 ground pixels
change in those views, with maximum channel difference 8. This is a quality
tradeoff, not complete seam removal; the generated candidate and edge stitch
remain experimental. The stitched candidate retained all 568 wall-fixture
pixels and passed the live controls and wall endpoint replays.
Moving all fragments of a source face together, with their relative bucket
order preserved, was rejected by the scenery guard in the angle-0 and
angle-180 captures. Expanding the group to coplanar faces propagated it to
another overlapping scenery face; the angle-0 correction still did not apply.
The grouping experiment was removed rather than weakening the guard. Its
captures are retained privately for further investigation.
Two guard shortcuts were removed after timed comparisons showed slightly
higher costs in both sampled views. In a fixed idle pose, omitting the
near-plane cache reduced the per-call FRT measurement from about 6,794 to
6,733 ticks at angle 0 and from 2,001 to 1,990 ticks at angle 180; this does
not establish a whole-frame improvement. In the same poses, scanning all
1,719 faces instead of the 274-face flat list took about 7,231 and 2,455
ticks per correction call, versus 6,733 and 1,990 with the list. These are
single fixed-view measurements, not a general frame-rate guarantee. The fixed 400-field release capture
still completed 36 draws. One-PC-per-field profiling is available via
`tools/profile_symbol_samples.py`, but its samples include startup and are not
cycle counts. `tools/inspect_support_capture.py` reports support counters,
actor minimum heights, and optional render-face geometry from an exact matching
ELF and WRAM dump. Both inspect a snapshot that can be taken mid-frame.

`tools/capture_support_routes.py --ground-pose` builds a live-animation
candidate and replays the controls and wall routes with periodic screenshots,
checks their endpoint telemetry and misaligned-access reports, and writes the
support counters. With the grounded-pose experiment enabled, the latest
controls and wall replays completed 58 and 76 draws, recorded no mapping
failures or sampled skipped commands, and passed their endpoint checks. The
wall replay recorded 29 support-key changes and 24 guard blocks. Periodic
screenshots are useful inspection points, not proof of every intervening frame
or of behavior on sloped ground.

The sloped-support experiment generates conservative planar walkable-face
candidates and tests the camera and every actor vertex against each candidate
plane. Grounded pose lift uses the KCL floor normal, with a bounded adjustment.
At x=80, z=160, the source-493 slope covered 165 idle and 83 walking actor
pixels at angle 180; both fall to zero in the matched captures, with no
outside-actor pixel changes. Two matching angle-0 views also remain unchanged.
The original guard blocked this correction on a face entirely outside the
framebuffer. Limiting its overlap region to the framebuffer plus a two-pixel
margin allowed the correction while preserving the ordering check on visible
geometry. These four snapshots do not establish safety for all slopes.

The live controls and wall endpoint checks also pass with sloped support enabled,
without sampled command skips, misaligned accesses, or mapping failures. They
completed 53 and 68 draws, compared with 58 and 76 for the earlier flat-only
ground-pose runs; the runs are not a controlled frame benchmark, but the
reduction and the slope capture's roughly 36,000 FRT ticks per support call
make performance an open issue. The slope candidate list contains 1,016 faces.
The sloped path and stitched assets remain experimental and are not enabled in
the normal build.

One-PC-per-field samples of the fixed slope view pointed to repeated actor
vertex tests. A per-call, collision-safe cache now stores the exact minimum
actor projection for each encountered plane normal. In the same fixed angle-180
idle capture, the support call fell from about 36,009 to 16,869 FRT ticks;
the source-493 correction and outside-actor pixel comparison were unchanged
in both slope poses at angles 0 and 180. Controls and wall replays completed
55 and 70 draws, versus 53 and 68 before the cache, with no mapping failures
or sampled command skips. These are specific diagnostic workloads, not a
general frame-rate result. The partial foreground wall fixture at angle 126
retained all 566 wall pixels on the actor while source-477 overlap fell from
11 to zero. `capture_support_animation.py --wall-partial` reproduces that
fixture; the camera height and target height must match the recorded view.
All 16 flat-ground pose results, including outside-actor face-ID changes, were
identical before and after caching.

An expanded slope sweep found unresolved near-plane cases. At angle 135 the
unsplit source-493 triangle crosses the near plane and remains in front of the
actor; at angle 270 the same issue also occurs. A private experiment refines
source 493 on a 32-unit grid, adding 20 render faces and 1,280 texture bytes
before stitching. In the 270-degree running sample, refinement reduces the
baseline source-493 overlap to 22 pixels and the guarded correction removes
those 22. At 135 degrees, same-source fragments can be reordered after an
explicit coplanarity check, but source 494 is an adjacent plane with a
different normal and remains a legitimate guard blocker. The refined running
sample still has 69 source-493 pixels over the actor. Do not treat this as a
complete slope fix or ignore the source-494 blocker without proving the
relative ordering safe.

The refined candidate initially changed 66–179 textured pixels outside the
actor in four sampled slope views. Stitching source-493 shared edges as well
as source 477 reduces that to 2–8 pixels, with maximum channel difference 8;
this does not eliminate the seam. The narrow foreground fixture retained all
566 actor-covering wall pixels with this candidate. Raised jump samples at
angles 0 and 180 had unchanged baseline and corrected overlaps. The bake
priority remapping used for the refined mesh is reproducible with
`tools/remap_face_priorities.py`; changed fragment groups receive their source
face's mean priority, while unchanged groups keep their fragment priorities.

Finer subdivision was compared at the same slope position. A 16-unit grid for
both sources 493 and 494 removed source-493 overlap in the 135-degree samples,
but altered 48–80 outside-actor textured pixels in two poses, with channel
differences up to 16. A mixed candidate (16 units for source 493, 32 for 494)
is less disruptive in the sampled views: at 135 degrees the idle pose has seven
source-493 pixels remaining and nine outside-actor textured changes (maximum
channel difference 8), while the running pose removes 12 source-494 pixels
with no outside-actor textured changes. At 270 degrees the sampled idle and
running poses have no remaining source-493 overlap. A 24-unit grid for source
494 left 24 source-494 pixels in the 135-degree running pose, so it was not
selected over the mixed candidate. These are comparative samples, not proof
that all differences correspond to harmless seams.

The mixed candidate has 1,763 render faces and uses 109,248 castle texture
bytes; its live route telemetry reports 4,704 bytes remaining in the texture
arena. Controls and wall routes passed endpoint checks with 54 and 69 draws,
no sampled skipped commands and no mapping failures. The controlled partial
wall again retained all 566 actor-covering pixels. The normal build remains
unchanged while the remaining slope overlaps, broader regressions, and seam quality
remain open. The animation capture helper accepts `--source` to report the
relevant source-face count while testing slopes.
In the 135-degree grounded jump sample the mixed candidate retains 32
source-493 and eight source-494 overlap pixels. The actor's lowest signed
distance to source 494's plane is approximately -0.211 units, so the current
whole-actor plane proof cannot classify that neighboring slope as safely
behind the actor. A less conservative fix needs to account for the finite
face and the actor geometry, not merely assume all adjacent slopes are safe.
In the completed four-pose matrix for angles 135, 180, 225 and 270, the
remaining source-493/source-494 counts at angle 135 were 7/0, 6/2, 0/0 and
32/8; all eight source-specific counts at each of the other three angles were
zero. Other scene faces can still cover the actor, and these fixed poses do
not replace an all-camera gameplay regression.

A refinement that tested only queued actor polygons whose projected bounds
could overlap a support face produced the same results in eight slope captures
and increased the fixed 135-degree idle support cost from about 15,178 to
16,148 FRT ticks. It was removed; a restored grounded-jump capture matches the
previous result. `inspect_support_capture.py --face` now also reports the
lowest actor vertex and whether its XZ position lies in the face's first
triangle. For the source-494 blocker in that grounded-jump sample, the lowest
vertex is outside that footprint and no actor vertex below the plane lies
inside it. This is diagnostic evidence only: an actor polygon can cross the
footprint between vertices, and perspective visibility needs a screen-space
intersection proof rather than a vertex-only footprint check.
The host collision sampler now supports `--point x z ceiling`. At the lowest
actor vertex of the grounded-jump sample (81.2475, 36.5913, 160.9355), the
actual KCL floor query returns height 36.3766 on the source-493-side normal.
Thus that vertex is approximately 0.215 units above the collision floor even
though it lies below source 494's infinite plane. A blanket slope-specific
lift of 1/3 unit removed the eight source-494 overlap pixels but left 19
source-493 pixels; a 2/3-unit lift still left four source-493 pixels. The
fixed lifts were removed because they alter the grounded pose and can create a
gap without resolving the ordering problem. The 1/3-unit idle test shifted
the silhouette centroid upward by approximately 1.08 pixels in the fixed
135-degree view.

The blocked source-493/source-494 fragments in that view share a boundary:
their ideal projected triangle interiors are disjoint, but the padded VDP1
raster guard treats their edges as potentially overlapping. An experiment
that ignored the padding when the ideal triangles were disjoint removed the
source-493 overlap in all four 135-degree poses, but left eight source-494
pixels in the grounded-jump pose. It also exposed 100 source-494 face-ID pixels
outside the actor and changed 31–32 textured pixels in two views (maximum
channel difference 8). The foreground-wall fixture passed, but that does not
establish safety for all shared edges. The relaxed guard was removed; the
captures remain private for investigating a coverage-aware edge treatment.
An additional bake experiment stitched the exactly shared edges across source
faces 493 and 494 before repeating the relaxed-guard captures. The two sampled
views still changed 31 and 32 outside-actor textured pixels, respectively;
the option and relaxed guard were therefore removed. The mixed-resolution
subdivision also creates partial shared edges that exact vertex-pair matching
does not cover, so this result does not rule out a more complete edge bake.
`tools/inspect_stitch_edges.py` compares generated edge segments in world
space. At a 1/128-unit tolerance it finds two exactly matching edge pairs and
six partially overlapping pairs between sources 493 and 494 in the mixed
mesh; the blocked faces 809 and 834 are among the partial pairs. This is a
topology observation, not a proof of VDP1 raster or texture equivalence.
An interval-based stitch experiment also joined the partially overlapping
segments. With the relaxed diagnostic guard, it reduced outside-actor changes
from 31/32 to 30/31 pixels in the two sample poses. Relative to the prior
exact-cross-source experiment, its idle baseline changed 63 outside-actor
pixels by at most eight channel levels. Relative to the mixed candidate, the
full experimental bake (which also enabled same-source stitching for 494)
changed 2,734 outside-actor baseline pixels, with maximum channel difference
112. Those comparisons do not isolate the contribution of source-494
stitching from cross-source stitching. The tiny seam improvement did not
justify retaining the added pipeline option; the experiment and relaxed guard
were removed.
An isolated follow-up joined only cross-source segments while leaving source
494's internal edges untouched. It changed 67 outside-actor baseline pixels by
at most eight channel levels and retained the same one-pixel-per-view seam
improvement. Thus the much larger prior baseline difference came primarily
from adding source-494 internal stitching; the isolated result still did not
justify keeping the cross-source option.
`tools/inspect_seam_pixels.py` now reports a channel-difference histogram in
addition to face-ID pairs, so isolated edge effects and large palette or
fallback changes can be distinguished without one-off image scripts.

An aligned 24-unit grid for both slope sources left 179–245 source-493
overlap pixels in the four 135-degree poses and was rejected. An aligned
20-unit grid gave 135-degree source-493/source-494 counts of 2/0, 0/0, 0/0,
0/0; at 180 degrees all were zero, at 225 degrees 3/0 and 4/0 remained in
idle and walk, and at 270 degrees 6/0 and 1/0 remained in idle and walk.
The other sampled poses at 225 and 270 were zero. In the two sampled
135-degree textured views, the correction changed one outside-actor pixel by
eight channel levels. Controls and wall routes passed endpoint checks with
54 and 69 draws, no sampled skips or mapping failures; the partial wall kept
all 566 actor-covering pixels. The runtime texture arena reported 4,192 bytes
remaining.

This 20-unit mesh is not automatically a visual improvement: in the matched
135-degree idle baseline it differs from the mixed mesh at 11,952 outside-actor
pixels, including large color differences. Face-ID comparison attributes
6,106 of those pixels to source 494 in both images and 5,369 to source 493
in both; the remainder includes different visible source pairs. Different
subdivision and clipping can change the terrain appearance, so a matched
reference is needed before accepting it. `inspect_seam_pixels.py` can now take
`--candidate-origins` to compare captures from differently subdivided meshes
and reports both generated-face and source-face pairs.

A DS input replay reached a second slope position (Saturn coordinates
60.5975, 40.2078, 147.3930), with camera eye (30.0348, 69.7494, 176.2321)
and target (63.8593, 50.5342, 144.3152). `capture_castle_comparisons.py`
now accepts named views and can match DS height and enable the experimental
support correction. At this position, both the mixed and 20-unit meshes hide
most of Mario behind a large flat terrain triangle while the DS image shows
him fully. The 20-unit capture with the guarded sloped-support correction is
pixel-identical to its uncorrected capture. The telemetry records 446 castle
clipping candidates and 506 total fallback faces in this view. This new view
therefore rejects promotion of the candidate and points to the clipping/
fallback and support classification paths for further investigation; it does
not isolate which of those causes the obstruction. Comparisons use a real
Saturn BIOS in injection mode, with static Saturn pose and DS camera/FOV
rounded to the diagnostic settings; they are not a matched animation frame.

Face-ID inspection identifies the large foreground triangle as source 511.
With the unadjusted idle pose, four actor vertices lie below that triangle's
plane, the lowest by 0.360 units; the guarded plane test correctly refuses
to reorder it. Enabling the experimental ground-pose adjustment lifts the
actor 0.390 units, leaving its lowest point 0.013 units above the plane, and
the support correction restores Mario in this view. The large flat area is
confirmed as the castle texture fallback by the magenta diagnostic. A 32-unit
subdivision of source 511 in addition to the 20-unit slope candidate restores
visible texture in that area in the same fixed view. The candidate used 483
commands, no skips, and left 3,040 bytes in the texture arena; its support
pass sampled 32,571 ticks. This is one static view, not evidence that the
subdivision and pose adjustment pass animation, wall, seam or performance
gates. Other fallback areas and the DS-to-Saturn scene differences remain.
In a subsequent 12-pose face-ID screen (angles 135, 225 and 270; idle,
two walk frames and one jump frame, with ground-pose adjustment), the
corrected captures had no source-493 or source-494 pixels on the actor.
However, the two 135-degree walk frames changed 192 and 191 pixels outside
the actor, mostly source-493 against itself and 14 source-493/source-494
pixels each. This is a material seam/order regression in the diagnostic
and prevents promotion; the remaining ten sampled views had no recorded
outside-actor face-ID changes. These counts are not textured-color deltas.
Matched textured captures reduce the two 135-degree walk differences to 16
and 15 outside-actor pixels, each changing by eight channel levels. In the
first frame, five belong to source 493 on both sides and eleven to the
493/494 boundary. Removing the guard's same-source coplanar exemption in a
temporary diagnostic reduced the outside-actor face-ID changes to 14 per
frame, but left three and four source-493 pixels covering the actor. That
tradeoff was rejected and the guard restored. A separate partial-wall idle
fixture preserved all 723 wall pixels on the actor and reduced source-477
overlap from seven pixels to zero; this is a single fixed view, not a moving
wall-route or performance validation.

The diagnostic support pass now skips unmapped faces and faces whose current
depth is already at least the maximum actor depth before computing their
plane and screen bounds. Such faces could not receive a key change. With the
511 candidate, all twelve corrected face-ID images and result records in the
135/225/270 animation screen matched byte-for-byte, as did the partial-wall
result and the matched DS-view Saturn screenshot. Sampled support-call times
fell from 32,571 to 25,191 ticks in the DS view, from 8,014 to 6,846 in the
135-degree walk view, and from 5,007 to 4,070 in the wall fixture. These are
fixed diagnostic measurements; the cost is still substantial and these do not
establish production frame rate or broader visual correctness.

The support-plane test now first evaluates the actor's world-space bounding
box. Its minimum dot product is a conservative lower bound on every vertex;
only an inconclusive bound falls back to the exact cached vertex scan. In the
matched DS slope screenshot this retained identical pixels and reduced the
sampled support call from 25,191 to 19,493 ticks; the fixed partial-wall
result was identical and fell from 4,070 to 3,533 ticks. Live control and
wall replays completed 56 and 73 draws, with no sampled command skips or
mapping failures and 3,040 texture-arena bytes remaining. These do not prove
visual correctness throughout either route or establish a frame-rate target.
All twelve corrected face-ID images and result records from the 135/225/270
animation screen matched the pre-bounds captures byte-for-byte.
The same live input replays without the bound reached the same endpoints;
they completed 55 and 72 draws, compared with 56 and 72 in the matching
bounded run. Some same-field screenshots differ because frame cadence and
simulation ticks differ, so this comparison is not a matched-state visual
regression test.

An exact shared-edge stitch between sources 493 and 494 on the 20-unit mesh
with source 511 refined reduced the 135-degree walk-frame textured seam from
16/15 to 8/7 outside-actor pixels, each at most one RGB555 channel step. The
unmodified-order baseline also changed 60 outside-actor terrain pixels in
each sampled view, by at most one channel step. The DS-position screenshot
also changed, so this is a texture-quality tradeoff, not a finished seam fix.
The explicit experimental `--stitch-cross-source FACE_A FACE_B` option can
reproduce the bake without also stitching the second source's internal edges;
its generated scene was byte-identical to the private trial. It remains off
by default and still needs broader views and wall/route checks.
In the twelve textured captures at angles 135, 225 and 270, cross-stitching
changed 60 baseline pixels at angle 135 and none at 225 or 270; the maximum
channel change was eight. The only correction-induced textured changes were
the 8/7 pixels in the two 135-degree walk frames. The cross-stitched build
also completed the control and wall endpoint checks at 56 and 72 draws with
no sampled skips or mapping failures. Twelve of fifteen corresponding route
screenshots were byte-identical to the unstitched build; this comparison does
not prove all intermediate simulation states match. `compare_support_textures.py`
can compare matching capture directories and rejects differing actor-only
images before measuring outside-actor terrain differences.
The eight remaining pixels in the first walk frame correspond to five at
an exact shared edge between generated source-493 fragments 805/813 and
three at the 493/494 boundary. A temporary two-texel-wide blend across all
source-493 shared edges eliminated both sampled walk-frame differences, but
changed 5,570/5,555 other baseline pixels, each by at most one channel step.
Restricting the wider blend to the single 805/813 edge left three pixels in
both frames and changed 538/539 baseline pixels. Both experiments were
removed; neither establishes an acceptable texture tradeoff or a general
solution for the remaining boundary pixels.
An additional 20-view face-ID screen at angles 0, 45, 90, 180 and 315
found 12 source-494 pixels overlapping the actor in each of the first three
angle-0 poses. The two covering generated faces are 833 and 834. In the idle
snapshot, the lowest actor vertex is 0.665 units below their infinite plane
but outside both triangles in XZ; no actor vertex is below either triangle
within its XZ footprint. This explains why the conservative infinite-plane
test cannot establish the needed order, but is not a proof that every one of
the 12 pixels is erroneous. Angle 180 also has substantial source-266 overlap
which may be legitimate foreground; it requires separate geometric or DS
reference validation. Other face-ID changes in this screen likewise require
textured and visibility checks before judging them as defects.
Matched body-only and castle-only captures provide a projected-triangle depth
check for those two overlaps. For source 494 at angle 0, eight of the twelve
sampled body pixels place the terrain in front, and four fall outside the
diagnostic's triangle coverage. For source 266 at angle 180, 506 body pixels
place the terrain in front and 219 fall outside that coverage. This body-only
calculation approximates VDP1 quad rasterization, excludes the head, and is
not a pixel-perfect visibility oracle; neither result proves every overlapping
pixel is correct. `capture_support_animation.py --depth-inputs` produces the
matched face-ID captures and verifies recorded camera and actor state across
capture variants; `analyze_castle_depth.py` performs the depth comparison.
Precomputed painter buckets, a near-plane cache and a 256-slot normal cache
were separately screened in these views; their costs or memory did not
justify retaining them, so those experiments were removed.

The Tekken Saturn project demonstrates bypassing its painter for a Force floor
only after establishing that floor is always behind all relevant geometry
(`docs/TEKKEN_FORCE_PLAN.md`, floor direct-to-VDP1 experiment). That invariant
does not hold for this castle's slopes and walls, so its technique is a useful
performance experiment only for separately proven background surfaces, not a
general occlusion fix. Its matched image and complete-frame performance gates
are applicable here.

## Playable build after the desktop screenshot

The default exporter refines 20 additional source faces on the approach, bridge,
entrance, and wall. It keeps convex split pieces as VDP1 quads using
LibSaturn's splitter. Texture weights now use stable source face IDs.
The 111,360-byte castle texture cap is based on the previous playable build,
including room in VDP1 VRAM for the rest of the scene and HUD.

| Check | Previous disc | Rebuilt disc |
| --- | ---: | ---: |
| Castle render faces | 1,665 | 1,636 |
| Castle texture pixel bytes | 111,360 | 111,232 |
| Free texture arena on both routes | 2,592 B | 2,720 B |
| Draws completed, controls route | 66 | 66 |
| Draws completed, wall route | 87 | 86 |
| Visible flat fallback pixels, fixed approach | 19,817 | 3,416 |
| Visible flat fallback pixels, fixed entrance | 10,973 | 8,775 |

The two fixed views replay the sampled approach and entrance camera and
player coordinates in Ymir. They use an idle pose shared by both builds.
They approximate the area shown in the desktop screenshot. Both routes
passed their endpoint checks with zero sampled dropped faces and zero
reported misaligned accesses. The geometry audit found no degenerate
pieces, and the 68 ROM-enabled host tests passed. The rebuilt disc loaded
in Mednafen.

The approach captures show more brick detail and a more continuous path.
The entrance still shows stretched texture, and the partial-alpha materials
still use the mesh approximation. The support ordering experiment produced
an identical image in the sampled entrance pose and remains disabled in
the playable build. Private captures and logs are under
`private/castle-play-repair/`.
