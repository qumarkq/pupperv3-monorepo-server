"""Offline behavior tests: no ROS, microphones or motors."""
import asyncio
import importlib.util
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / 'src'

class FollowClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        path = SRC / 'appearance_follow_client.py'
        self.assertTrue(path.exists(), 'Missing appearance-follow integration')
        spec = importlib.util.spec_from_file_location('appearance_follow_client', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.Client = module.AppearanceFollowClient
        self.calls = []
        self.ready = True
        self.locked = True
        self.walking = True

    async def call(self, name):
        self.calls.append(name)
        if name == 'ready':
            return self.ready, 'camera ready'
        if name == 'check':
            return self.locked, 'LOCKED' if self.locked else 'ACQUIRING'
        return True, name

    def client(self, timeout=0.05):
        return self.Client(self.call, lambda: self.walking, lock_timeout=timeout, poll_interval=0.001)

    async def test_success_requires_selected_colour_and_confirmed_lock(self):
        ok, _ = await self.client().follow('red')
        self.assertTrue(ok)
        self.assertEqual(self.calls, ['deactivate', 'ready', 'select_red', 'activate', 'check'])

    async def test_invalid_colour_never_arms(self):
        ok, _ = await self.client().follow('pink; shell')
        self.assertFalse(ok)
        self.assertEqual(self.calls, ['deactivate'])

    async def test_inactive_controller_never_arms(self):
        self.walking = False
        ok, _ = await self.client().follow('red')
        self.assertFalse(ok)
        self.assertNotIn('activate', self.calls)

    async def test_stale_camera_never_arms(self):
        self.ready = False
        ok, _ = await self.client().follow('red')
        self.assertFalse(ok)
        self.assertNotIn('activate', self.calls)

    async def test_lock_timeout_deactivates(self):
        self.locked = False
        ok, _ = await self.client(timeout=0.003).follow('red')
        self.assertFalse(ok)
        self.assertEqual(self.calls[-1], 'deactivate')

    async def test_service_failure_deactivates(self):
        async def fail(name):
            if name == 'activate':
                self.calls.append(name)
                return False, 'rejected'
            return await self.call(name)
        client = self.Client(fail, lambda: True)
        ok, _ = await client.follow('blue')
        self.assertFalse(ok)
        self.assertEqual(self.calls[-1], 'deactivate')

    async def test_stop_cancels_pending_acquisition(self):
        self.locked = False
        client = self.client()
        task = asyncio.create_task(client.follow('red'))
        while 'check' not in self.calls:
            await asyncio.sleep(0)
        stop = asyncio.create_task(client.stop())
        result, stopped = await asyncio.gather(task, stop)
        self.assertFalse(result[0])
        self.assertTrue(stopped[0])
        self.assertEqual(self.calls[-1], 'deactivate')
        self.assertEqual(self.calls.count('activate'), 1)

    async def test_queued_walking_can_finish_before_preparation(self):
        self.walking = False
        async def prepare():
            self.assertTrue(self.walking, 'Must not clear queued walking activation early')
        client = self.Client(self.call, lambda: self.walking, walking_timeout=0.05, poll_interval=0.001)
        task = asyncio.create_task(client.follow('red', prepare=prepare))
        await asyncio.sleep(0.003)
        self.walking = True
        ok, _ = await task
        self.assertTrue(ok)

    async def test_stop_during_preparation_cannot_arm_later(self):
        entered = asyncio.Event()
        release = asyncio.Event()
        async def prepare():
            entered.set()
            await release.wait()
        client = self.client()
        task = asyncio.create_task(client.follow('red', prepare=prepare))
        await entered.wait()
        stop = asyncio.create_task(client.stop())
        await asyncio.sleep(0)
        release.set()
        result, stopped = await asyncio.gather(task, stop)
        self.assertFalse(result[0])
        self.assertTrue(stopped[0])
        self.assertNotIn('activate', self.calls)

    async def test_task_cancellation_deactivates(self):
        self.locked = False
        client = self.client()
        task = asyncio.create_task(client.follow('red'))
        while 'check' not in self.calls:
            await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.calls[-1], 'deactivate')

if __name__ == '__main__':
    unittest.main()
