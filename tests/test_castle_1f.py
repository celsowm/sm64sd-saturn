import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from sm64ds_pipeline.bmd import convert_bmd
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.kcl import decode_kcl
from sm64ds_pipeline.level_objects import extract_castle_1f_objects
from sm64ds_pipeline.quad_merge import merge_coplanar_quads
from sm64ds_pipeline.subdivide import split_long_edges
from prepare_castle import _compact_rooms, _compute_room_adjacency, _compute_room_portals

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


if __name__ == "__main__":
    unittest.main()
