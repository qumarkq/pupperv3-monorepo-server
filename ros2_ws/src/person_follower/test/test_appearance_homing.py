import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[4] / 'robot' / 'utils' / 'run_appearance_follow_safe.py'

class HomingTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PATH.exists(), 'Missing integrated calibration gate runner')
        spec = importlib.util.spec_from_file_location('safe_runner', PATH)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_all_twelve_and_completion_marker_required(self):
        text = '\n'.join('Homed actuator ' + str(i) for i in range(12))
        self.assertFalse(self.module.homing_complete(text))
        self.assertTrue(self.module.homing_complete(text + '\nFinished homing!'))

    def test_duplicate_confirmation_cannot_replace_missing_motor(self):
        text = '\n'.join('Homed actuator ' + str(i) for i in range(11))
        text += '\nHomed actuator 1\nFinished homing!'
        self.assertFalse(self.module.homing_complete(text))

if __name__ == '__main__':
    unittest.main()
