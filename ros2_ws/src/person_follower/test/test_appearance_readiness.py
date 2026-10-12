"""Run real readiness and arming methods without a ROS daemon."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

PATH = Path(__file__).resolve().parents[1] / 'person_follower' / 'appearance_person_follower.py'


def methods():
    tree = ast.parse(PATH.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    body = [n for n in cls.body if isinstance(n, ast.FunctionDef)
            and n.name in {'controller_ready', 'ready', 'arm', 'joint_feedback', 'controller_result'}]
    namespace = {'COLORS': ('red',), 'time': SimpleNamespace(monotonic=lambda: 10.0), 'math': __import__('math')}
    node = ast.Module(body=[ast.ClassDef(name='Follower', bases=[], keywords=[], body=body, decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(node), str(PATH), 'exec'), namespace)
    return namespace['Follower']


class ReadinessTests(unittest.TestCase):
    def node(self):
        n = methods()()
        n.get_parameter = lambda name: SimpleNamespace(value=True)
        n.geometry_ok = True
        n.last_image_received = 9.95
        n.frame_age = 0.01
        n.wait_reason = 'waiting'
        n.controller_active = False
        n.controller_received = 9.95
        n.joints_received = 9.95
        return n

    def test_unverified_homing_cannot_report_robot_ready(self):
        n = self.node()
        n.controller_active = True
        n.get_parameter = lambda name: SimpleNamespace(value=False)
        self.assertFalse(n.ready(None, SimpleNamespace()).success)

    def test_camera_alone_cannot_report_robot_ready(self):
        result = self.node().ready(None, SimpleNamespace())
        self.assertFalse(result.success)

    def test_stale_joint_feedback_cannot_report_ready(self):
        n = self.node()
        n.controller_active = True
        n.joints_received = 8.0
        result = n.ready(None, SimpleNamespace())
        self.assertFalse(result.success)

    def test_fresh_controller_feedback_and_camera_report_ready(self):
        n = self.node()
        n.controller_active = True
        result = n.ready(None, SimpleNamespace())
        self.assertTrue(result.success)

    def test_arm_refuses_inactive_controller_even_if_colour_selected(self):
        n = self.node()
        n.policy = SimpleNamespace(active=False, color='red')
        result = n.arm(None, SimpleNamespace())
        self.assertFalse(result.success)

if __name__ == '__main__':
    unittest.main()
