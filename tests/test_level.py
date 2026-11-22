"""Generic level reader against the local ROM (skipped when absent)."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from sm64ds_pipeline.filesystem import Filesystem
from sm64ds_pipeline.level import read_level, asset_handles
from sm64ds_pipeline.level_objects import extract_castle_1f_objects


@unittest.skipUnless(os.getenv('SM64DS_ROM'), 'local ROM absent')
class LevelReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fs = Filesystem.from_file(Path(os.environ['SM64DS_ROM']))

    def test_handles_match_known_ids(self):
        h = asset_handles(self.fs)
        self.assertEqual(h['data/stage/castle_1f/castle_1f.kcl'], 0x600)
        self.assertEqual(h['data/stage/bombhei_map/bombhei_map_all.bmd'], 0x5FD)
        self.assertEqual(h['data/stage/bombhei_map/bombhei_map.kcl'], 0x5FB)

    def test_stage_overlays(self):
        for stage, ov, areas in (('main_castle', 9, 1), ('castle_1f', 10, 8),
                                 ('bombhei_map', 14, 1), ('cave', 21, 8)):
            lv = read_level(self.fs, stage)
            self.assertEqual((lv.overlay_id, lv.area_count), (ov, areas))

    def test_sublevel_ids(self):
        for stage, sub in (('main_castle', 1), ('castle_1f', 2), ('bombhei_map', 6)):
            self.assertEqual(read_level(self.fs, stage).sublevel, sub)

    def test_castle_1f_matches_old_extractor(self):
        old = extract_castle_1f_objects(self.fs)
        lv = read_level(self.fs, 'castle_1f')
        doors = [r for l in lv.lists(9) for r in l.records]
        self.assertEqual(len(doors), len(old.doors))
        toads = [r for a in range(lv.area_count) for l in lv.lists(0, a)
                 for r in l.records if r[0] == 80]
        self.assertEqual(len(toads), len(old.toads))

    def test_bob_omb_battlefield_lists(self):
        lv = read_level(self.fs, 'bombhei_map')
        self.assertEqual(sum(l.count for l in lv.lists(1)), 4)    # entrances
        self.assertEqual(sum(l.count for l in lv.lists(2)), 49)   # path nodes
        std = lv.lists(0, 0)
        self.assertIn(89, [l.count for l in std if l.star == 0])



@unittest.skipUnless(os.getenv('SM64DS_ROM') and Path(
    __import__('sm64ds_pipeline.actors', fromlist=['x']).DEFAULT_NAMES).exists(),
    'local ROM or decomp names absent')
class ActorTableTests(unittest.TestCase):
    def test_castle_object_ids_resolve(self):
        from sm64ds_pipeline.actors import obj_to_actor_table, actor_names
        fs = Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        t, names = obj_to_actor_table(fs), actor_names()
        for obj, name in ((41, 'TREE'), (42, 'PICTURE_GATE'), (76, 'TATEFUDA'),
                          (80, 'KINOPIO'), (275, 'C1_PEACH')):
            self.assertEqual(names[t[obj]], name)



@unittest.skipUnless(os.getenv('SM64DS_ROM') and Path(
    __import__('sm64ds_pipeline.actors', fromlist=['x']).DEFAULT_NAMES).exists(),
    'local ROM or decomp names absent')
class ActorBakeTests(unittest.TestCase):
    def test_bob_actor_placements_and_bake(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        from actor_registry import ACTORS
        from sm64ds_pipeline.actor_model import bake_actor
        from sm64ds_pipeline.level import actor_placements
        fs = Filesystem.from_file(Path(os.environ['SM64DS_ROM']))
        wanted = {name: (spec.source or name, spec.only_star) for name, spec in ACTORS.items()}
        placed = actor_placements(fs, 'bombhei_map', wanted)
        self.assertEqual(len(placed['BOMBHEI']), 11)
        self.assertEqual(len(placed['BOMBKING']), 1)
        spec = ACTORS['BOMBHEI']
        src, rep = bake_actor(fs, 'bombhei', spec.bmd, placed['BOMBHEI'], scale=spec.scale)
        self.assertEqual(rep['count'], 11)
        self.assertIn('actor_kind_bombhei', src)


if __name__ == '__main__':
    unittest.main()
