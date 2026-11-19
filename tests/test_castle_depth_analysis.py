import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from analyze_castle_depth import depth_at


class CastleDepthAnalysisTest(unittest.TestCase):
    def test_perspective_depth_uses_reciprocal_interpolation(self):
        points = [(0, 0, 10), (10, 0, 20), (0, 10, 20), (0, 10, 20)]
        self.assertAlmostEqual(depth_at(points, 5, 0), 1 / (0.5/10 + 0.5/20))

    def test_rejects_outside_and_behind_camera(self):
        points = [(0, 0, 10), (10, 0, 10), (0, 10, 10), (0, 10, 10)]
        self.assertIsNone(depth_at(points, 20, 20))
        self.assertIsNone(depth_at([(x, y, -w) for x, y, w in points], 1, 1))


if __name__ == '__main__':
    unittest.main()
