"""Exercise real ROS-tool methods with an in-memory transport (ROS unavailable)."""
import ast
import asyncio
from pathlib import Path
import sys
import types
import threading
import time
import unittest

SRC = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(SRC))


def tool_class():
    tree = ast.parse((SRC / 'ros_tool_server.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RosToolServer')
    wanted = {'activate_appearance_following', 'deactivate_person_following', 'activate_person_following', '_call_appearance_service', 'immediate_stop', '_hold_appearance_stop', '_publish_appearance_stop', '_on_appearance_status', 'check_mode'}
    methods = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in wanted]
    namespace = {'Twist': lambda: types.SimpleNamespace(linear=types.SimpleNamespace(x=0.0), angular=types.SimpleNamespace(z=0.0)), 'Tuple': tuple, 'Trigger': types.SimpleNamespace(Request=lambda: object()),
                 'is_controller_active': lambda server, name: True,
                 'asyncio': asyncio, 'time': __import__('time')}
    namespace['rclpy'] = types.SimpleNamespace(spin_until_future_complete=lambda *a, **kw: None)
    module = ast.Module(body=[ast.ClassDef(name='Tool', bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), '<real ROS tool methods>', 'exec'), namespace)
    return namespace['Tool']


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_appearance_stop_invalidates_pending_client(self):
        tool = tool_class()()
        self.assertTrue(hasattr(tool, 'activate_appearance_following'), 'Missing voice ROS integration')
        tool.following_mode_status = 'active'
        async def stop():
            return True, 'inactive'
        tool.appearance_follow = types.SimpleNamespace(stop=stop)
        tool.person_follow_mode = 'appearance'
        ok, _ = await tool.deactivate_person_following()
        self.assertTrue(ok)
        self.assertEqual(tool.following_mode_status, 'inactive')

    async def test_ordinary_follow_refuses_appearance_mode(self):
        tool = tool_class()()
        tool.person_follow_mode = 'appearance'
        ok, message = await tool.activate_person_following()
        self.assertFalse(ok)
        self.assertIn('colour', message)

    async def test_immediate_stop_reports_unconfirmed_follow_stop(self):
        tool = tool_class()()
        tool.person_follow_mode = 'appearance'
        async def stop():
            return False, 'service timed out'
        async def nothing():
            return True, 'done'
        tool.deactivate_person_following = stop
        tool.clear_queue = nothing
        tool._interrupt_and_stop = nothing
        tool.node = types.SimpleNamespace(get_logger=lambda: types.SimpleNamespace(warning=lambda *a: None))
        ok, _ = await tool.immediate_stop()
        self.assertFalse(ok)

    async def test_unconfirmed_stop_keeps_zero_until_confirmation(self):
        tool = tool_class()()
        outputs = []
        tool.twist_pub = types.SimpleNamespace(publish=outputs.append)
        stop_executor = threading.Event()
        def executor():
            while not stop_executor.wait(0.05):
                tool._publish_appearance_stop()
        thread = threading.Thread(target=executor)
        tool._hold_appearance_stop()
        thread.start()
        try:
            # Simulate the voice thread blocked on a ROS service response.
            time.sleep(0.12)
            self.assertGreaterEqual(len(outputs), 3)
            self.assertTrue(all(msg.linear.x == 0 and msg.angular.z == 0 for msg in outputs))
            tool._appearance_stop_unconfirmed = False
            count = len(outputs)
            time.sleep(0.1)
            self.assertEqual(len(outputs), count)
        finally:
            stop_executor.set()
            thread.join()

    async def test_target_loss_updates_voice_follow_status(self):
        tool = tool_class()()
        tool._on_appearance_status(types.SimpleNamespace(data='APPEARANCE_FOLLOW shirt=red LOCKED: session target locked'))
        self.assertEqual(tool.following_mode_status, 'active')
        tool._on_appearance_status(types.SimpleNamespace(data='APPEARANCE_FOLLOW shirt=red LOST: target missing'))
        self.assertEqual(tool.following_mode_status, 'inactive')

    async def test_colour_request_refuses_ordinary_mode(self):
        tool = tool_class()()
        self.assertTrue(hasattr(tool, 'activate_appearance_following'), 'Missing voice ROS integration')
        tool.person_follow_mode = 'ordinary'
        ok, _ = await tool.activate_appearance_following('red')
        self.assertFalse(ok)

if __name__ == '__main__':
    unittest.main()
