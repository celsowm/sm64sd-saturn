import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from stage_table import BY_NAME, STAGES


class StageTableTests(unittest.TestCase):
    def test_all_stages_unique_and_bins_fit_iso9660(self):
        self.assertEqual(len(STAGES), 48)
        self.assertEqual(len({s.bin for s in STAGES}), 48)
        self.assertTrue(all(len(s.bin) <= 8 and s.bin.isalnum() for s in STAGES))

    def test_playable_today(self):
        self.assertEqual({s.name for s in STAGES if s.enabled},
                         {'main_castle', 'castle_1f', 'bombhei_map', 'main_garden',
                          'battan_king_map', 'kaizoku_irie'})
        self.assertEqual(BY_NAME['bombhei_map'].bin, 'BOB')
        self.assertEqual(BY_NAME['main_garden'].bin, 'GARDEN')
        self.assertEqual(BY_NAME['battan_king_map'].bin, 'WF')
        self.assertEqual(BY_NAME['kaizoku_irie'].bin, 'JRB')


class PaintingEntranceTests(unittest.TestCase):
    def test_enabled_course_returns_to_numbered_1f_entrance(self):
        from stage_table import castle_1f_entrance
        # BoB is the first enabled painting course -> entrance 3.
        self.assertEqual(castle_1f_entrance('bombhei_map'), 3)
        # WF is the second -> entrance 4.
        self.assertEqual(castle_1f_entrance('battan_king_map'), 4)
        # JRB is the third -> entrance 5.
        self.assertEqual(castle_1f_entrance('kaizoku_irie'), 5)
        with self.assertRaises(ValueError):
            castle_1f_entrance('snow_mt')           # not enabled yet


class ActorRegistryTests(unittest.TestCase):
    def test_bob_kinds_cover_the_mission(self):
        from actor_registry import ACTORS
        for kind in ('BOMBHEI', 'RED_BOMBHEI', 'KURIBO', 'BOMBKING', 'STAR1',
                     'HATENA_BLOCK', 'COIN', 'RED_COIN', 'SECRET_COIN',
                     'WANWAN', 'IRONBALL'):
            self.assertIn(kind, ACTORS)

    def test_star_bit_and_boss_unlock(self):
        from actor_registry import ACTORS
        star = ACTORS['STAR1']
        self.assertEqual(star.star_bit, 1)
        self.assertEqual(star.unlock_by, 'BOMBKING')
        self.assertEqual(star.behavior, 3)
        boss = ACTORS['BOMBKING']
        self.assertEqual(boss.behavior, 2)
        self.assertEqual(boss.hp, 3)
        self.assertGreater(boss.top, 0.0)
        self.assertGreater(boss.stun_steps, 0)
        secret = ACTORS['SECRET_COIN']
        self.assertEqual(secret.behavior, 4)
        self.assertEqual(secret.coin_value, 5)
