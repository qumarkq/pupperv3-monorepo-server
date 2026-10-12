"""Bounded colour-follow transaction; ROS transport is supplied by the caller."""
import asyncio
import time

COLORS = ('red', 'orange', 'yellow', 'green', 'blue', 'purple', 'black', 'white', 'gray')


class AppearanceFollowClient:
    def __init__(self, call, walking_active, *, lock_timeout=8.0, poll_interval=0.1, settle_delay=0.0, walking_timeout=0.0):
        self.call = call
        self.walking_active = walking_active
        self.lock_timeout = lock_timeout
        self.poll_interval = poll_interval
        self.settle_delay = settle_delay
        self.walking_timeout = walking_timeout
        self._generation = 0
        self._transaction = asyncio.Lock()

    async def stop(self):
        # Invalidate a pending acquisition before waiting for its cleanup.
        self._generation += 1
        async with self._transaction:
            return await self.call('deactivate')

    async def follow(self, color, *, prepare=None):
        self._generation += 1
        generation = self._generation
        async with self._transaction:
            confirmed = False
            needs_cleanup = False
            try:
                ok, message = await self.call('deactivate')
                if not ok:
                    return False, 'Cannot confirm previous follow stopped: ' + message
                if color not in COLORS:
                    return False, 'Specify one supported upper-shirt colour: ' + ', '.join(COLORS)
                # Give a queued ActivateWalkingCommand time to finish before
                # preparation clears pending movement. STOP invalidates this wait.
                walking_deadline = time.monotonic() + self.walking_timeout
                while not self.walking_active():
                    if generation != self._generation:
                        return False, 'Following cancelled by a newer request'
                    if time.monotonic() >= walking_deadline:
                        return False, 'Walking controller is not active; prepare walking mode first'
                    await asyncio.sleep(self.poll_interval)
                if prepare is not None:
                    await prepare()
                if self.settle_delay:
                    await asyncio.sleep(self.settle_delay)
                if generation != self._generation:
                    return False, 'Following cancelled by a newer request'
                needs_cleanup = True
                for action in ('ready', 'select_' + color, 'activate'):
                    if generation != self._generation:
                        return False, 'Following cancelled by a newer request'
                    if action == 'activate' and not self.walking_active():
                        return False, 'Walking controller became inactive'
                    ok, message = await self.call(action)
                    if not ok:
                        return False, action + ' rejected: ' + message
                deadline = time.monotonic() + self.lock_timeout
                while generation == self._generation and time.monotonic() < deadline:
                    ok, message = await self.call('check')
                    if generation != self._generation:
                        break
                    if not self.walking_active():
                        return False, 'Walking controller became inactive'
                    if ok:
                        confirmed = True
                        return True, 'Target locked: ' + color + ' upper shirt; following active'
                    if message.startswith('LOST'):
                        return False, message
                    await asyncio.sleep(self.poll_interval)
                return False, 'Target acquisition cancelled or timed out; following stopped'
            finally:
                # Includes cancellation, service rejection and failed lock acquisition.
                if needs_cleanup and not confirmed:
                    await self.call('deactivate')
