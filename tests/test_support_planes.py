import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from sm64ds_pipeline.support_planes import support_planes


class SupportPlanesTest(unittest.TestCase):
    def test_upward_slope_and_rejections(self):
        vertices = [(0, 0, 0), (1, 1, 0), (0, 0, 1), (1, 1, 1),
                    (0, 2, 0), (0, 3, 1), (1, 3, 1)]
        faces = [(0, 1, 2, 2), (0, 2, 1, 1), (0, 4, 5, 5), (0, 1, 2, 6)]
        result = support_planes(vertices, faces)
        self.assertEqual([item[0] for item in result], [0, 1])
        self.assertGreater(result[0][1][1], 0)
        self.assertEqual(result[0][1], result[1][1])


if __name__ == '__main__':
    unittest.main()
