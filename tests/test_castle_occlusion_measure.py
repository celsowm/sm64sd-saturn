import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from measure_castle_occlusion import measure
from check_support_capture import compare


class OcclusionMeasureTest(unittest.TestCase):
    def test_counts_changed_actor_pixels_by_source_face(self):
        background = (96, 160, 240)
        # Face ID zero is encoded as RGB555 value 109.
        face = ((109 & 31) << 3, ((109 >> 5) & 31) << 3, 0)
        actor = Image.new('RGB', (3, 1))
        actor.putdata([background, face, (248, 0, 0)])
        scene = Image.new('RGB', (3, 1))
        scene.putdata([face, face, face])
        self.assertEqual(measure(actor, scene, [477], background),
                         {'actor_pixels': 2, 'overlap_by_source': {477: 1}})

    def test_rejects_mismatched_capture_sizes(self):
        with self.assertRaises(ValueError):
            measure(Image.new('RGB', (1, 1)), Image.new('RGB', (2, 1)), [], (0, 0, 0))

    def test_wall_loss_is_reported_even_outside_actor(self):
        background, wall = (96, 160, 240), (248, 0, 248)
        actor = Image.new('RGB', (2, 1))
        actor.putdata([(248, 0, 0), background])
        before = Image.new('RGB', (2, 1), wall)
        after = Image.new('RGB', (2, 1))
        after.putdata([wall, background])
        result = compare(actor, before, after, [477], 477, background, wall)
        self.assertEqual(result['wall_on_actor_before'], 1)
        self.assertEqual(result['wall_on_actor_lost'], 0)
        self.assertEqual(result['wall_pixels_lost'], 1)


if __name__ == '__main__':
    unittest.main()
