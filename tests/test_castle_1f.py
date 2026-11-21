import os
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
    extract_castle_1f_objects,
    extract_clps_slippery_mask,
)
from sm64ds_pipeline.quad_merge import merge_coplanar_quads
from sm64ds_pipeline.subdivide import cut_faces_against_boxes, cut_faces_at_height, split_long_edges
from prepare_castle import (
    _compact_chunks,
    _compact_rooms,
    _compute_room_adjacency,
    _compute_room_portals,
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
