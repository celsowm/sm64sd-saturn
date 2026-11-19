import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from inspect_support_capture import BASE, SIZE, inspect
from capture_support_animation import MATCHED_STATE, check_matched_state


class SupportCaptureTest(unittest.TestCase):
    def test_capture_state_must_match(self):
        state = dict.fromkeys(MATCHED_STATE, 0)
        check_matched_state(state, dict(state), 'candidate')
        changed = dict(state, camera_y=1)
        with self.assertRaisesRegex(RuntimeError, 'candidate: capture state differs: camera_y'):
            check_matched_state(state, changed, 'candidate')

    def setUp(self):
        self.data = bytearray(SIZE)
        self.syms = {}
        cursor = 0
        for name, size in (('g_sm64ds_support_diag', 192), ('world_vertices', 24),
                           ('hw', 12), ('diagnostic_support_face_queue', 4),
                           ('ci', 16), ('cw', 24), ('cp', 16), ('keys', 12),
                           ('diagnostic_support_cache', 12), ('g_sm64ds_castle_stats', 56)):
            self.syms[name] = (BASE+cursor, size)
            cursor += size
        def put(name, offset, fmt, *values):
            struct.pack_into(fmt, self.data, self.syms[name][0]-BASE+offset, *values)
        put('g_sm64ds_support_diag', 164, '>7I', 3, 3, 5, 4, 0, 2, 1)
        put('world_vertices', 0, '>6i', 0, 2*65536, 0, 0, -65536, 0)
        put('hw', 0, '>3i', 0, 3*65536, 0)
        put('diagnostic_support_face_queue', 2, '>H', 2)
        put('ci', 8, '>4H', 0, 1, 1, 1)
        put('cw', 0, '>6i', 0, 65536, 0, 0, 65536, 65536)
        put('cp', 0, '>hhihhi', 1, 2, 65536, 3, 4, 2*65536)
        put('keys', 8, '>I', 0xfe000123)
        put('diagnostic_support_cache', 8, '>i', 1)

    def test_decodes_geometry_and_diagnostics(self):
        result = inspect(self.data, self.syms, 1)
        self.assertEqual(result['actor_lowest']['world_vertices'], {'vertex': 1, 'y': -1})
        self.assertEqual(result['counters']['changes'], 2)
        self.assertEqual(result['face']['queue'], 2)
        self.assertEqual(result['face']['key'], 0xfe000123)
        self.assertEqual(result['face']['vertices'][1]['projected']['depth'], 2)
        self.assertNotIn('queue', result)
        self.assertEqual(inspect(self.data, self.syms, 1, 2, [9, 17])['queue']['source_face'], 17)

    def test_rejects_out_of_range_face(self):
        with self.assertRaises(ValueError):
            inspect(self.data, self.syms, 2)


if __name__ == '__main__':
    unittest.main()
