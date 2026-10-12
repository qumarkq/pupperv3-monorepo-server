import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

class AppearancePolicyTests(unittest.TestCase):
    def setUp(self):
        package = Path(__file__).resolve().parents[1] / 'person_follower'
        self.assertTrue((package / 'appearance_follow_policy.py').exists(), 'Missing packaged colour-follow policy')
        from person_follower.appearance_follow_policy import AppearanceFollowPolicy
        from person_follower.single_person_lock import Box
        self.policy = AppearanceFollowPolicy()
        self.box = Box(320, 320, 220, 220)

    def lock(self):
        self.policy.select('red')
        self.assertTrue(self.policy.arm())
        for i in range(12):
            self.policy.observe([self.box], [0], i + 1, 0.0, i / 10)
        self.assertEqual(self.policy.lock.state, 'LOCKED')

    def test_selection_does_not_start_motion(self):
        self.policy.select('red')
        self.assertFalse(self.policy.active)
        self.assertEqual(self.policy.command(0), (0, 0))

    def test_lost_colour_stops_and_does_not_reacquire(self):
        self.lock()
        self.assertGreater(self.policy.command(1.1)[0], 0)
        self.policy.observe([self.box], [], 13, 0, 1.2)
        self.assertEqual(self.policy.command(1.2), (0, 0))
        self.policy.observe([self.box], [0], 14, 0, 1.3)
        self.assertEqual(self.policy.lock.state, 'LOST')

    def test_stale_frames_stop_motion(self):
        self.lock()
        self.assertEqual(self.policy.command(1.5), (0, 0))
        self.assertEqual(self.policy.lock.state, 'LOST')

    def test_multiple_colour_matches_stop_motion(self):
        self.lock()
        from person_follower.single_person_lock import Box
        self.policy.observe([self.box, Box(550, 300, 100, 200)], [0, 1], 13, 0, 1.2)
        self.assertEqual(self.policy.command(1.2), (0, 0))

    def test_red_shirt_uses_clean_pixels(self):
        from person_follower.shirt_color_selector import analyse_shirt, appearance_intent
        image = np.zeros((640, 640, 3), dtype=np.uint8)
        image[:, :, 2] = 255
        self.assertTrue(analyse_shirt(image, self.box, 'red')['match'])
        self.assertFalse(analyse_shirt(image, self.box, 'blue')['match'])
        self.assertEqual(appearance_intent('跟隨穿紅色上衣的人')['shirt_color'], 'red')

if __name__ == '__main__':
    unittest.main()
