#!/usr/bin/env python3
"""Launch the server colour follower with an owned calibration gate and timeout.

Run in an already sourced ROS workspace. Does not activate walking itself.
"""
import argparse
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time


def homing_complete(text):
    motors = set(re.findall(r'Homed actuator ([0-9]+)', text))
    return len(motors) == 12 and 'Finished homing!' in text


def ros(*args, timeout=4):
    return subprocess.run(['ros2', *args], capture_output=True, text=True, timeout=timeout)


def stop_group(process):
    for sig, timeout in ((signal.SIGINT, 5), (signal.SIGTERM, 2), (signal.SIGKILL, 2)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        # The launch parent may have exited while children still own the group.
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-seconds', type=int, default=180)
    args = parser.parse_args()
    if not 30 <= args.max_seconds <= 600:
        parser.error('--max-seconds must be between 30 and 600')
    if not os.getenv('ROS_DISTRO'):
        parser.error('Source the ROS distribution and built workspace before running')
    for pattern in ('ros2_control_node', '/lib/camera_ros/camera_node',
                    '/lib/hailo/hailo_detection', '/lib/person_follower/person_follower_node',
                    'appearance_person_follower'):
        result = subprocess.run(['pgrep', '-f', pattern], capture_output=True)
        if result.returncode == 0:
            parser.error('An existing control/vision/follower process is running: ' + pattern)
        if result.returncode != 1:
            parser.error('Cannot check existing processes with pgrep')
    log = tempfile.NamedTemporaryFile(prefix='pupper-appearance-', suffix='.log', delete=False)
    process = subprocess.Popen(
        ['ros2', 'launch', 'neural_controller', 'launch.py', 'person_follow_mode:=appearance'],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupt)
    try:
        print('CALIBRATION: waiting for 12 unique actuator confirmations. Log: ' + log.name, flush=True)
        deadline = time.monotonic() + 120
        while not homing_complete(Path(log.name).read_text(errors='replace')):
            if process.poll() is not None:
                raise RuntimeError('ROS launch exited before homing completed; inspect ' + log.name)
            if time.monotonic() >= deadline:
                raise RuntimeError('12-motor homing was not confirmed within 120 seconds')
            time.sleep(0.5)
        deadline = time.monotonic() + 45
        while True:
            if process.poll() is not None:
                raise RuntimeError('ROS launch exited before appearance follower was ready')
            result = ros('param', 'set', '/appearance_person_follower', 'homing_verified', 'true')
            if result.returncode == 0 and 'Set parameter successful' in result.stdout:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Cannot release appearance calibration gate; inspect ' + log.name)
            time.sleep(0.5)
        print('HOMING VERIFIED: following remains inactive. Start the voice agent in another terminal.', flush=True)
        print('Complete shutdown in ' + str(args.max_seconds) + ' seconds; Ctrl+C stops earlier.', flush=True)
        deadline = time.monotonic() + args.max_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('ROS launch exited unexpectedly; inspect ' + log.name)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print('Stopping owned ROS stack.', flush=True)
    finally:
        try:
            commands = [
                ('service', 'call', '/appearance_follow/deactivate', 'std_srvs/srv/Trigger', '{}'),
                ('topic', 'pub', '--once', '/emergency_stop', 'std_msgs/msg/Empty', '{}'),
                ('service', 'call', '/controller_manager/switch_controller',
                 'controller_manager_msgs/srv/SwitchController',
                 '{activate_controllers: [], deactivate_controllers: [neural_controller], strictness: 1, activate_asap: true, timeout: {sec: 2, nanosec: 0}}'),
            ]
            for command in commands:
                try:
                    result = ros(*command)
                    if result.returncode != 0:
                        print('Shutdown request failed: ' + ' '.join(command[:3]), flush=True)
                except subprocess.TimeoutExpired:
                    print('Shutdown request timed out: ' + ' '.join(command[:3]), flush=True)
        finally:
            stop_group(process)
            log.close()
            print('Log saved: ' + log.name, flush=True)


if __name__ == '__main__':
    main()
