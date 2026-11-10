# SM64DS USA Rev.00 — local ROM audit (metadata only)

Date: 2026-11-10. Target: a locally supplied **Super Mario 64 DS USA** ROM. This document contains **only metadata and derived counts**. No Nintendo ROM content, extracted textures, models, animations, audio, or binary assets are committed.

## Identity and method

| Field | Observed |
|---|---|
| DS title | \`S.MARIO64DS\` |
| Game code | \`ASME\` |
| Maker | \`01\` |
| Revision | 0 |
| ROM file size | 16,777,216 bytes (16 MiB) |
| SHA-256 of local input | \`916056a27ffb07d1bae2ce0ca6f6464c1621c737dc96657a7b9eab4d3bccfc87\` |
| NitroFS FAT entries | 1,936 |
| Named NitroFS entries | 1,833 |
| Unnamed FAT entries | 103 (ARM9 overlays) |
| NitroFS directory count | 315 |
| ARM9 overlay table entries | 103 |
| ARM7 overlays | 0 |

The read-only inspection parsed DS header / FNT / FAT / overlay table; all 8 NARC container headers and their internal FNT/FAT; and **in memory** decompressed selected source files with the standard LZ77 type-0x10 algorithm after the game's \`LZ77\` prefix. The original bytes were not written to the repository or copied to any public location. This is a source-asset **metadata inspection**, not a validated complete runtime handle map, fully converted model, successful boot, or physics test.

Top-level named NitroFS breakdown: **450 BMD**, **492 BCA**, **241 KCL**, **105 BTP**, **8 NARC**, **535 BIN**, **1 SDAT**, plus one entry with no extension. These counts exclude files nested inside NARC containers.

## Important discovery: the actual gameplay Mario model is nested in a NARC

**Do not use \`data/player/b_mario_all.bmd\` as the assumed gameplay skeleton.** That top-level model has only **1 bone**. The principal 16-bone model is inside:

| Field | Result |
|---|---|
| Outer NitroFS file | \`ARCHIVE/arc0.narc\` |
| Outer NitroFS file ID | **105** |
| Archive entries | **198** |
| Internal NARC index | **131** |
| Internal full path | \`data/player/mario_model.bmd\` |
| Internal compressed size | **7,013 bytes** |
| Uncompressed size | **12,184 bytes** |
| Bone count | **16** |
| Display-list groups | **1** |
| Materials/textures | **1 / 1** |
| Weighted matrix count | **0** |

The same NARC contains Mario's separate heads (cap and no-cap), a star and coin model, and many player animations. In particular, \`data/player/mario_head_cap.bmd\` is index **129** and \`data/player/mario_head_nocap.bmd\` index **130**, both with 1 bone. The 16-bone gameplay body and separate head resources should be evaluated as a combined character presentation; the existence of these assets alone does not prove the final assembled transforms.

**Action:** add NARC parsing and local nested-asset resolution to Gate 1 **before** designing the Mario BMD converter, and use full logical identities \`archive_path + internal_index + internal_path\`. NitroFS file IDs and NARC indexes are distinct namespaces.

## First animation clips and matching skeleton

The following files are top-level NitroFS entries, not files inside the above NARC:

| Animation | NitroFS ID | Compressed bytes | Uncompressed bytes | Frames | Loop | Track entries |
|---|---:|---:|---:|---:|---|---:|
| \`data/player/su_wait.bca\` | 858 | 3,016 | 3,512 | 120 | yes | 16 |
| \`data/player/su_walk.bca\` | 859 | 1,700 | 2,048 | 30 | yes | 16 |
| \`data/player/su_run.bca\` | 857 | 1,733 | 2,080 | 30 | yes | 16 |
| \`data/player/su_jump.bca\` | 855 | 861 | 1,192 | 11 | no | 16 |

Track entry counts were derived from BCA track-table offsets and the recovered **0x24-byte per-bone track** structure. They align with the 16-bone model, making this a high-value import pair for an early golden test. **This does not yet prove that each clip is the game's selected animation for Mario in every gameplay state**, or that its time base matches Saturn's; verify against original actor resource selection and the upstream native PC-port oracle.

The model has zero weighted matrices in its BMD header. Test rigid per-joint attachment first; do not fabricate blend weights. LibSaturn's \`sat_skin_rigid_t\` records and \`sat_skeleton_clip_t\` can represent rigid hierarchy animation after a correct BMD/BCA conversion. Use its weighted-skin path only where the source actually requires it.

## Candidate test courses: measured source sizes

| Source stage | BMD file ID | BMD compressed / raw | KCL file ID | KCL compressed / raw | KCL prisms |
|---|---:|---:|---:|---:|---:|
| \`test_map_b\` | 1537 | 356 / 756 B | 1536 | 145 / 286 B | 3 |
| \`test_map\` | 1533 | 18,916 / 37,288 B | 1531 | 16,386 / 28,826 B | 801 |
| \`main_garden\` | 1474 | 22,675 / 33,412 B | 1472 | 18,219 / 28,192 B | 597 |
| \`bombhei_map\` | 1291 | 35,974 / 52,344 B | 1289 | 42,192 / 55,390 B | 930 |
| \`castle_1f\` | 1302 | 68,643 / 108,880 B | 1294 | 51,618 / 80,552 B | 1,463 |

KCL prisms are counts of 0x10-byte triangle/prism records between the recovered offsets at header +0x08 and +0x0c; this is **not** a count of final rendered triangles or VDP1 commands. The table does **not** include level textures, placement and CLPS/behavioral metadata, per-actor assets, or Saturn conversion overhead. On-disk LZ77 sizes are **not** a memory/VRAM budget.

Suggested steps:
1. **Importer smoke:** \`test_map_b\` for the first BMD + KCL read/decompress/bounds test, supplemented by original synthetic fixtures.
2. **Scenic vertical slice:** \`main_garden\` is a smaller content candidate than \`bombhei_map\` for early level loading and collision.
3. **Bob-omb Battlefield:** use \`bombhei_map\` for the recognizable stage after the renderer/collider are proven and source references confirm placement/scene behavior.

## Risks and required changes to PORT_PLAN.md

1. A parser that examines only top-level NitroFS entries **misses the real Mario model**. Implement **NARC/BTAF/BTNF/GMIF** parsing and nested paths first.
2. Nearly all selected BMD/BCA/KCL assets start with \`"LZ77" | 0x10 | 24-bit uncompressed size\`. Host conversion must decode them **before** interpreting BMD/BCA/KCL headers; the exceptions require explicit format detection. NARC containers themselves begin with \`NARC\`.
3. Work from BMD bone ordering and BCA track ordering; validate parent relationships and object/head attachment at nontrivial animation frames, not only the rest pose.
4. The KCL format is prism-based with its own normals, attributes, and octree. Do not naïvely reinterpret it as a triangle mesh with generic sphere response and declare gameplay parity.
5. **No claim yet** that the official upstream asset handle table (\`0x80A\` entries) has been recovered. The current inspection covers NitroFS and NARC directory indexes; the mapping from runtime game handles in ARM9 overlay 0 remains a dedicated verification task.
6. Remain on **stock Sega Saturn** for the acceptance baseline. Validate final code/pose/collision/texture/command memory from Saturn-generated assets before assigning a target frame rate.

## Acceptance checklist for next implementation

- [ ] Reproducible local ROM fingerprint + region/version check.
- [ ] A production-safe FNT/FAT and NARC reader with bounds and format tests.
- [ ] LZ77 decompressor with malformed/truncated/overrun test vectors.
- [ ] Import \`arc0.narc:131\` and inspect 16-bone parent chain.
- [ ] Match \`su_wait/su_walk/su_run/su_jump\`'s 16 tracks against Mario model hierarchy.
- [ ] Compare reference poses against upstream PC native smoke tests.
- [ ] Convert \`test_map_b\` geometry and KCL without touching proprietary assets in public CI.
- [ ] Record VRAM, WRAM and VDP1 command budget of the **converted** test content.
- [ ] Generate **handles.tsv** by validating overlay 0 separately; don't confuse handles with FNT file IDs.

**Disclosure note:** this is a traceable audit of a user-provided local ROM, not authorization to publish Nintendo assets or ship a playable game with their content.
