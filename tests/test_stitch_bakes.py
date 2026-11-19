import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from sm64ds_pipeline.stitch_bakes import stitch_bakes
from sm64ds_pipeline.textures import BakedTexture
from inspect_stitch_edges import overlap


class StitchBakesTest(unittest.TestCase):
    def test_cross_source_stitches_only_selected_shared_edges(self):
        red, blue = (200, 0, 0, 255), (0, 0, 200, 255)
        bakes = [BakedTexture(8, 8, (color,)*64) for color in (red, blue, blue)]
        faces = [(0, 1, 2, 2), (1, 0, 3, 3), (3, 0, 4, 4)]
        result = stitch_bakes(faces, [7, 8, 8], bakes, set(), [(7, 8)])
        self.assertEqual(result[0].rgba[:8], tuple(reversed(result[1].rgba[:8])))
        self.assertEqual(result[2], bakes[2])
        self.assertEqual(result[0].rgba[4*8+4], red)

    def test_shared_edge_and_interior(self):
        red, blue = (200, 0, 0, 255), (0, 0, 200, 255)
        bakes = [BakedTexture(8, 8, (red,)*64), BakedTexture(8, 8, (blue,)*64)]
        # A->B of one triangle is B->A of the other.
        result = stitch_bakes([(0, 1, 2, 2), (1, 0, 3, 3)], [7, 7], bakes, {7})
        self.assertEqual(result[0].rgba[:8], tuple(reversed(result[1].rgba[:8])))
        self.assertEqual(result[0].rgba[4*8+4], red)
        self.assertEqual(result[1].rgba[4*8+4], blue)
        self.assertEqual(bakes[0].rgba[0], red)

    def test_different_source_and_alpha_untouched(self):
        a = BakedTexture(8, 8, ((1, 2, 3, 255),)*64)
        b = BakedTexture(8, 8, ((4, 5, 6, 0),)*64)
        faces = [(0, 1, 2, 2), (1, 0, 3, 3)]
        self.assertEqual(stitch_bakes(faces, [7, 7], [a, b], {7}), [a, b])
        self.assertEqual(stitch_bakes(faces, [7, 8], [a, b], {7, 8}), [a, b])

    def test_mixed_resolutions(self):
        red, blue = (200, 0, 0, 255), (0, 0, 200, 255)
        a = BakedTexture(8, 8, (red,)*64)
        b = BakedTexture(16, 16, (blue,)*256)
        result = stitch_bakes([(0, 1, 2, 2), (1, 0, 3, 3)], [7, 7], [a, b], {7})
        self.assertEqual(result[0].rgba[0], result[1].rgba[15])
        self.assertEqual(result[0].rgba[0], result[1].rgba[14])
        self.assertEqual(result[0].rgba[4*8+4], red)

    def test_partial_edge_diagnostic(self):
        long_edge = (0, 1, 2, (0, 0, 0), (4, 0, 0))
        partial = (1, 3, 1, (2, 0, 0), (0, 0, 0))
        match = overlap(long_edge, partial, 0.001)
        self.assertAlmostEqual(match['overlap_units'], 2)
        self.assertFalse(match['exact_vertex_pair'])
        displaced = (2, 4, 5, (0, 0.1, 0), (2, 0.1, 0))
        self.assertIsNone(overlap(long_edge, displaced, 0.001))



if __name__ == '__main__':
    unittest.main()
