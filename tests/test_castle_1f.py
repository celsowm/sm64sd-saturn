import math
import os
import re
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.kcl import decode_kcl
from sm64ds_pipeline.level_objects import (
    CASTLE_1F_OVERLAY_ID,
    CASTLE_GROUNDS_OVERLAY_ID,
    castle_1f_wave_table,
    extract_castle_1f_objects,
    extract_clps_masks,
    extract_clps_slippery_mask,
)
from sm64ds_pipeline.quad_merge import merge_coplanar_quads
from sm64ds_pipeline.subdivide import cut_faces_against_boxes, cut_faces_at_height, split_long_edges
from prepare_castle import (
    _compact_chunks,
    _compact_rooms,
    _compute_room_adjacency,
    _compute_room_portals,
    _kcl_water_surface,
    _merge_water_actors,
    _xz_near_polygon,
)

ROM = Path(os.environ["SM64DS_ROM"]) if "SM64DS_ROM" in os.environ else None


@unittest.skipUnless(ROM and ROM.is_file(), "set SM64DS_ROM to a local USA SM64DS ROM")
class Castle1fPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fs = Filesystem.from_file(ROM)
        cls.model = convert_bmd(cls.fs.read("data/stage/castle_1f/castle_1f_all.bmd"))

    def test_bmd_assigns_all_eight_rooms(self):
        self.assertEqual(len(self.model.bones), 8)
        self.assertEqual(len(self.model.face_rooms), len(self.model.faces))
        self.assertEqual(set(self.model.face_rooms), set(range(8)))
        # Main lobby (r0) is the largest room.
        counts = [self.model.face_rooms.count(r) for r in range(8)]
        self.assertEqual(max(counts), counts[0])
        self.assertGreater(counts[0], 800)

    def test_overlay_10_extracts_doors_paintings_and_toads(self):
        objs = extract_castle_1f_objects(self.fs)
        self.assertEqual(len(objs.doors), 15)
        self.assertEqual(sum(d.is_level_exit for d in objs.doors), 7)
        self.assertEqual(len(objs.paintings), 7)
        paths = {p.model_path for p in objs.paintings}
        self.assertEqual(
            paths,
            {
                "data/picture/for_bh.bmd",
                "data/picture/for_bk.bmd",
                "data/picture/for_ki.bmd",
                "data/picture/for_sm.bmd",
                "data/special_obj/c1_peach/c1_peach.bmd",
            },
        )
        self.assertEqual(len(objs.toads), 4)
        self.assertEqual(objs.toad_rooms[0], 0)

    def test_ripple_course_paintings_are_state0(self):
        objs = extract_castle_1f_objects(self.fs)
        ripples = [p for p in objs.paintings if p.state == 0]
        self.assertEqual(len(ripples), 4)
        # All four course paintings carry the same width nibble in param1.
        self.assertEqual({p.param & 0xF for p in ripples}, {5})
        for p in ripples:
            self.assertGreater(p.width, 0)
            self.assertGreater(p.height, 0)

    def test_wave_table_rows_have_front_and_back_halves(self):
        rows = castle_1f_wave_table(self.fs)
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(len(r) == 5 for r in rows))
        self.assertEqual({r[1] for r in rows[:6]}, {13107})
        self.assertEqual({r[1] for r in rows[6:]}, {4369})
        # Amplitude and wavelength are shared by both halves; the durations
        # differ (60 frames in front, 100 behind).
        self.assertEqual({r[0] for r in rows}, {rows[0][0]})
        self.assertEqual({r[2] for r in rows}, {rows[0][2]})
        for half in (rows[:6], rows[6:]):
            self.assertEqual(len({r[4] for r in half}), 1)
        self.assertEqual(rows[0][4], 60)
        self.assertEqual(rows[6][4], 100)
        for r in rows:
            amplitude, phase_step, wavelength, radius, duration = r
            self.assertGreater(amplitude, 0)
            self.assertGreater(wavelength, 0)
            self.assertGreater(radius, 0)
            self.assertGreater(duration, 0)

    def test_generated_ripple_arrays(self):
        hdr = (ROOT / "private/castle_1f/castle_scene.h").read_text()
        src = (ROOT / "private/castle_1f/castle_scene.c").read_text()
        self.assertIn("#define CASTLE_RIPPLE_COUNT 4u", hdr)
        self.assertIn("#define CASTLE_RIPPLE_GRID 8u", hdr)
        self.assertIn("#define CASTLE_RIPPLE_CELLS (CASTLE_RIPPLE_GRID*CASTLE_RIPPLE_GRID)", hdr)
        self.assertIn("#define CASTLE_RIPPLE_TILE_COUNT 256u", hdr)
        self.assertGreater(int(re.search(r"#define CASTLE_PAINTING_TEXTURE_COUNT (\d+)u", hdr).group(1)), 200)
        rows = re.search(r"const uint8_t castle_ripple_paintings\[CASTLE_RIPPLE_COUNT\]=\{(.*?)\};",
                         src, re.S).group(1)
        paints = [int(x) for x in re.findall(r"\d+", rows)]
        self.assertEqual(len(paints), 4)
        # Each ripple row owns a disjoint run of 64 tiles.
        tiles = [int(x) for x in re.findall(r"\d+", re.search(
            r"const uint16_t castle_ripple_tiles\[CASTLE_RIPPLE_TILE_COUNT\]=\{(.*?)\};", src, re.S).group(1))]
        self.assertEqual(len(tiles), 256)
        runs = [tiles[r * 64:(r + 1) * 64] for r in range(4)]
        for run in runs:
            self.assertEqual(len(run), 64)                # one tile per grid cell
            self.assertLessEqual(len(set(run)), 64)
        for a, b in ((0, 1), (1, 2), (2, 3)):
            self.assertFalse(set(runs[a]) & set(runs[b]))
        waves = [tuple(int(x) for x in re.findall(r"\d+", m)) for m in re.findall(
            r"\{(\d+,\d+,\d+,\d+,\d+)\}", re.search(
                r"const castle_ripple_wave_t castle_ripple_waves\[CASTLE_RIPPLE_COUNT\]=\{(.*?)\};", src, re.S).group(1))]
        self.assertEqual(len(waves), 4)
        for row in waves:
            self.assertEqual(len(row), 5)
            self.assertEqual(row[4], 60)                 # duration kept raw

    def test_generated_wave_rows_match_rom_table_scaled(self):
        src = (ROOT / "private/castle_1f/castle_scene.c").read_text()
        waves = [tuple(int(x) for x in re.findall(r"\d+", m)) for m in re.findall(
            r"\{(\d+,\d+,\d+,\d+,\d+)\}", re.search(
                r"const castle_ripple_wave_t castle_ripple_waves\[CASTLE_RIPPLE_COUNT\]=\{(.*?)\};", src, re.S).group(1))]
        rom_rows = castle_1f_wave_table(self.fs)
        rom = rom_rows[3]            # width step 6 selects row 3 (see _ripple_wave_row)
        self.assertEqual(len(set(waves)), 1)
        gen = waves[0]
        for field, rom_field in ((1, 1), (4, 4)):
            self.assertEqual(gen[field], rom[rom_field])
        for field in (0, 2, 3):
            # 4.12 DS lengths are converted with *1.024.
            self.assertAlmostEqual(gen[field] / 1.024, rom[field], delta=max(1, rom[field] * 0.02))

    def test_ripple_height_math(self):
        # Port of castle_ripple_height: the wavefront, the amplitude decay
        # and the falloff are all integer fixed-point maths on the generated
        # wave rows.
        src = (ROOT / "private/castle_1f/castle_scene.c").read_text()
        row = [tuple(int(x) for x in re.findall(r"\d+", m)) for m in re.findall(
            r"\{(\d+,\d+,\d+,\d+,\d+)\}", re.search(
                r"const castle_ripple_wave_t castle_ripple_waves\[CASTLE_RIPPLE_COUNT\]=\{(.*?)\};", src, re.S).group(1))][0]
        amp, phase_step, wavelength, radius, duration = row

        def height(dist, elapsed, phase=0):
            frames = 65535 // phase_step
            speed = wavelength // frames
            if dist > speed * elapsed:
                return 0
            amp_v = amp - (amp // duration) * elapsed
            fall = amp_v - (amp_v * dist) // radius
            if fall < 0:
                fall = 0
            return int(round(math.sin(2 * math.pi * phase / 65536.0) * fall))

        # A wave never begins with a zero timer.
        self.assertEqual(height(0, 0), 0)
        elapsed = 1
        speed = wavelength // (65535 // phase_step)
        # Beyond the wavefront the canvas is flat.
        self.assertEqual(height(speed * elapsed + 1, elapsed), 0)
        self.assertEqual(height(speed * elapsed + 1, 0), 0)
        # Halfway through the run the origin cell is displaced; at the end the
        # linear decay has reduced it.
        half = duration // 2
        h_half = height(0, half, phase=16384)
        h_end = height(0, duration, phase=16384)
        self.assertGreater(h_half, 0)
        self.assertLess(abs(h_end), abs(h_half))

    def test_room_compaction_and_portal_adjacency(self):
        m = self.model
        verts = [
            tuple(c * (1 << m.scale_shift) * 64.0 / 4096.0 for c in (v.x, v.y, v.z))
            for v in m.vertices
        ]
        faces, uvs, mats, cols, origins, src_sets = merge_coplanar_quads(
            verts, m.faces, m.face_uvs, m.face_materials,
            colors=m.face_colors, rooms=m.face_rooms,
        )
        frooms = [m.face_rooms[o] for o in origins]
        cverts, cfaces, _, _, _, _, crooms, _, meta = _compact_rooms(
            verts, faces, uvs, mats, origins, src_sets, frooms, cols, len(m.bones)
        )
        rfirst, rcount, rvfirst, rvcount, rmin, rmax = meta
        self.assertEqual(sum(rcount), len(cfaces))
        self.assertEqual(sum(rvcount), len(cverts))
        for r in range(8):
            self.assertGreater(rcount[r], 0)
            self.assertGreater(rvcount[r], 0)
            for fi in range(rfirst[r], rfirst[r] + rcount[r]):
                self.assertEqual(crooms[fi], r)
                for vi in cfaces[fi]:
                    self.assertGreaterEqual(vi, rvfirst[r])
                    self.assertLess(vi, rvfirst[r] + rvcount[r])
        objs = extract_castle_1f_objects(self.fs)
        portals = _compute_room_portals(cverts, cfaces, crooms, 8, objs.doors)
        self.assertEqual(len(portals), 8)
        self.assertEqual({rb for _, ra, rb in portals if ra == 0}, set(range(1, 8)))
        adj = _compute_room_adjacency(rmin, rmax, objs.doors, portals=portals)
        # Lobby r0 connects via portals to all 7 side rooms.
        self.assertEqual(adj[0], 0xFF)
        # Every side room connects back to r0 and itself.
        for r in range(1, 8):
            self.assertEqual(adj[r], 1 | (1 << r))

    def test_split_long_edges_bounds_edge_lengths_and_preserves_colors(self):
        verts = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 0.0, 20.0), (0.0, 0.0, 20.0)]
        faces = [(0, 1, 2, 3)]
        uvs = [((0.0, 0.0), (10.0, 0.0), (10.0, 2.0), (0.0, 2.0))]
        mats = [0]
        cols = [((255, 0, 0), (0, 255, 0), (0, 255, 0), (255, 0, 0))]
        sv, sf, su, sm, so, sc = split_long_edges(verts, faces, uvs, mats, 40.0, colors=cols)
        self.assertEqual(len(sf), 3)
        self.assertEqual(len(sc), 3)
        self.assertEqual(so, [0, 0, 0])
        for f in sf:
            pts = [sv[i] for i in f]
            for i in range(4):
                dx = pts[i][0] - pts[(i + 1) % 4][0]
                dy = pts[i][1] - pts[(i + 1) % 4][1]
                dz = pts[i][2] - pts[(i + 1) % 4][2]
                self.assertLessEqual((dx * dx + dy * dy + dz * dz) ** 0.5, 40.0 + 1e-6)

    def test_castle_1f_kcl_decodes_cleanly(self):
        prisms = decode_kcl(self.fs.read("data/stage/castle_1f/castle_1f.kcl"))
        self.assertEqual(len(prisms), 1462)

    def test_clps_slippery_masks_match_overlays(self):
        ext_mask = extract_clps_slippery_mask(self.fs, CASTLE_GROUNDS_OVERLAY_ID)
        c1f_mask = extract_clps_slippery_mask(self.fs, CASTLE_1F_OVERLAY_ID)
        # Outer green boundary hills (0x0d) and invisible walls (0x14) are traction=3.
        self.assertEqual(ext_mask, 0x00182488)
        self.assertTrue(ext_mask & (1 << 0x0D))
        # Castle 1F stair surfaces (0x05..0x08, 0x0b, 0x0f, 0x10) must NOT be slippery.
        self.assertEqual(c1f_mask, 0x00060400)
        for stair_attr in (0x05, 0x06, 0x07, 0x08, 0x0B, 0x0F, 0x10):
            self.assertFalse(c1f_mask & (1 << stair_attr))

    def test_compact_chunks_partitions_and_bounds_faces(self):
        verts = [
            (10.0, 0.0, 10.0), (50.0, 0.0, 10.0), (50.0, 5.0, 50.0), (10.0, 5.0, 50.0),
            (200.0, 10.0, 200.0), (240.0, 10.0, 200.0), (240.0, 20.0, 240.0), (200.0, 20.0, 240.0),
        ]
        faces = [(0, 1, 2, 3), (4, 5, 6, 7)]
        uvs = [((0.0, 0.0),) * 4, ((0.0, 0.0),) * 4]
        mats = [0, 1]
        origins = [0, 1]
        source_sets = [(0,), (1,)]
        cv, cf, _, _, _, _, fchunks, _, meta = _compact_chunks(
            verts, faces, uvs, mats, origins, source_sets, None, 128.0
        )
        cfirst, ccount, cvfirst, cvcount, cmin, cmax = meta
        self.assertEqual(len(cfirst), 2)
        self.assertEqual(sum(ccount), 2)
        self.assertEqual(len(set(fchunks)), 2)
        for c in range(2):
            for fi in range(cfirst[c], cfirst[c] + ccount[c]):
                for vi in cf[fi]:
                    self.assertTrue(cvfirst[c] <= vi < cvfirst[c] + cvcount[c])
                    for axis in range(3):
                        self.assertTrue(cmin[c][axis] <= cv[vi][axis] <= cmax[c][axis])

    def test_cut_faces_against_boxes_removes_buried_ground(self):
        # 100x100 grass quad at y=0 with a 20x20 raised hedge box at [40..60]x[40..60], y_top=20.
        verts = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 0.0, 100.0), (0.0, 0.0, 100.0)]
        faces = [(0, 1, 2, 3)]
        uvs = [((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0))]
        mats = [3]
        origins = [0]
        source_sets = [(0,)]
        cols = [((255, 255, 255),) * 4]
        v2, f2, u2, m2, o2, s2, c2 = cut_faces_against_boxes(
            verts, faces, uvs, mats, origins, source_sets,
            target_materials={3}, boxes=[(40.0, 60.0, 40.0, 60.0, 20.0)], colors=cols,
        )
        # Should split into 4 outside quads totaling 100*100 - 20*20 = 9600 sq units.
        self.assertEqual(len(f2), 4)
        self.assertEqual(len(c2), 4)
        area = 0.0
        for f in f2:
            pts = [v2[i] for i in (f[:3] if f[2] == f[3] else f)]
            cx = sum(p[0] for p in pts) / len(pts)
            cz = sum(p[2] for p in pts) / len(pts)
            # No surviving piece centroid may lie inside the subtracted box.
            self.assertFalse(40.0 < cx < 60.0 and 40.0 < cz < 60.0)
            xs = [p[0] for p in pts]
            zs = [p[2] for p in pts]
            area += (max(xs) - min(xs)) * (max(zs) - min(zs))
        self.assertAlmostEqual(area, 9600.0, places=3)


@unittest.skipUnless(ROM and ROM.is_file(), "set SM64DS_ROM to a local USA SM64DS ROM")
class CastleGroundsWaterTests(unittest.TestCase):
    def test_mc_water_actor_supplies_the_original_moat(self):
        # Castle Grounds has no water in its stage KCL: the original moat is the
        # MC_WATER actor (ov009), whose own KCL is a flat rectangle at y=-6.4.
        fs = Filesystem.from_file(ROM)
        prisms = decode_kcl(fs.read("data/stage/main_castle/main_castle.kcl"))
        _slippery, water_mask = extract_clps_masks(fs, CASTLE_GROUNDS_OVERLAY_ID)
        self.assertEqual(water_mask, 0)
        merged, merged_mask = _merge_water_actors(fs, "main_castle", prisms, water_mask)
        self.assertEqual(len(merged), len(prisms) + 2)
        bits = [b for b in range(32) if merged_mask >> b & 1]
        self.assertEqual(len(bits), 1)
        self.assertEqual({p.attribute for p in merged[len(prisms):]}, set(bits))
        y, triangles = _kcl_water_surface(merged, merged_mask)
        self.assertAlmostEqual(y, -6.4)
        self.assertEqual(len(triangles), 2)
        xs = [v[0] for t in triangles for v in t]
        zs = [v[2] for t in triangles for v in t]
        self.assertAlmostEqual(min(xs), -448.0)
        self.assertAlmostEqual(max(xs), 512.0)
        self.assertAlmostEqual(min(zs), -320.0)
        self.assertAlmostEqual(max(zs), 512.25, places=2)

    def test_stage_without_mc_water_is_unchanged(self):
        fs = Filesystem.from_file(ROM)
        prisms = decode_kcl(fs.read("data/stage/main_garden/main_garden.kcl"))
        _slippery, water_mask = extract_clps_masks(fs, 11)
        merged, merged_mask = _merge_water_actors(fs, "main_garden", prisms, water_mask)
        self.assertEqual(merged, prisms)
        self.assertEqual(merged_mask, water_mask)

    def test_mc_water_bta_scroll_is_diagonal_91_frames(self):
        # The MC_WATER BTA (ov009 daObjMcWater_c) has 91 frames, scale 4096,
        # rotation 0, and translates S and T together at 46/91 per frame.
        from sm64ds_pipeline.bta import load_bta
        from prepare_castle import MC_WATER_OVERLAY_ID, MC_WATER_BTA_OFFSET
        fs = Filesystem.from_file(ROM)
        anim = load_bta(fs, MC_WATER_OVERLAY_ID, MC_WATER_BTA_OFFSET)
        self.assertEqual(len(anim.frames), 91)
        scale_s, scale_t, rotation = anim.frames[0][:3]
        self.assertEqual(scale_s, 4096)
        self.assertEqual(scale_t, 4096)
        self.assertEqual(rotation, 0)
        # transS == transT every frame (diagonal), stepping by 46.
        for f in anim.frames:
            self.assertEqual(f[3], f[4])
        self.assertEqual(anim.frames[0][3], 0)
        self.assertEqual(anim.frames[1][3], 46)
        self.assertEqual(anim.frames[-1][3], 4096)

    def test_emit_water_texture_bakes_phase_ring(self):
        # The generated castle exports the 32x32 LUT4 texture and a 16-entry
        # phase ring whose frames carry the diagonal BTA scroll.
        from prepare_castle import _emit_water_texture
        fs = Filesystem.from_file(ROM)
        header, _code, info = _emit_water_texture(fs)
        self.assertTrue(any("CASTLE_WATER_TEXTURE_AVAILABLE 1" in l for l in header))
        self.assertTrue(any("CASTLE_WATER_TEX_WIDTH 32u" in l for l in header))
        self.assertTrue(any("CASTLE_WATER_TEX_HEIGHT 32u" in l for l in header))
        self.assertEqual(info["texture_size"], [32, 32])
        self.assertEqual(info["phases"], 16)
        self.assertEqual(info["bta_frames"], 91)
        self.assertEqual(info["bta_step"], [46, 46])


class WaterLayerTests(unittest.TestCase):
    def test_cut_faces_at_height_splits_only_listed_faces(self):
        # A wall from y=0 to y=20 cut at the water (y=8), and a second wall left whole.
        verts = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 20.0, 0.0), (0.0, 20.0, 0.0),
                 (0.0, 0.0, 5.0), (10.0, 0.0, 5.0), (10.0, 20.0, 5.0), (0.0, 20.0, 5.0)]
        faces = [(0, 1, 2, 3), (4, 5, 6, 7)]
        uvs = [((0.0, 0.0), (4.0, 0.0), (4.0, 20.0), (0.0, 20.0))] * 2
        cols = [((31, 31, 31), (31, 31, 31), (11, 11, 11), (11, 11, 11))] * 2
        v2, f2, u2, m2, o2, s2, c2 = cut_faces_at_height(
            verts, faces, uvs, [1, 1], [0, 1], [(0,), (1,)], 8.0, {0}, colors=cols,
        )
        self.assertEqual(len(f2), 3)
        self.assertEqual(o2, [0, 0, 1])
        self.assertEqual(f2[2], (4, 5, 6, 7))
        below, above = ([v2[i][1] for i in f] for f in f2[:2])
        self.assertLessEqual(max(below), 8.0)
        self.assertGreaterEqual(min(above), 8.0)
        # UVs and colors follow the cut: v = y here, and the color is 3/5 of the way down.
        for f, uv, col in zip(f2[:2], u2[:2], c2[:2]):
            for i, (u, v), c in zip(f, uv, col):
                self.assertAlmostEqual(v, v2[i][1])
                if v2[i][1] == 8.0:
                    self.assertEqual(c, (23, 23, 23))

    def test_compact_chunks_keeps_layers_apart(self):
        # Seabed and water over it in the same XZ cell land in different chunks.
        verts = [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0), (40.0, 0.0, 40.0), (0.0, 0.0, 40.0),
                 (0.0, 8.0, 0.0), (40.0, 8.0, 0.0), (40.0, 8.0, 40.0), (0.0, 8.0, 40.0)]
        faces = [(0, 1, 2, 3), (4, 5, 6, 7)]
        uvs = [((0.0, 0.0),) * 4] * 2
        args = (verts, faces, uvs, [0, 1], [0, 1], [(0,), (1,)], None, 128.0)
        self.assertEqual(len(_compact_chunks(*args)[-1][0]), 1)
        self.assertEqual(len(_compact_chunks(*args, layers=[0, 1])[-1][0]), 2)

    def test_xz_near_polygon(self):
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        self.assertTrue(_xz_near_polygon(5.0, 5.0, square, 2.0))
        self.assertTrue(_xz_near_polygon(11.5, 5.0, square, 2.0))
        self.assertFalse(_xz_near_polygon(13.0, 5.0, square, 2.0))
        self.assertTrue(_xz_near_polygon(5.0, 5.0, square[::-1], 0.0))


if __name__ == "__main__":
    unittest.main()
