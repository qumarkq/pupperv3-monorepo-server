#!/usr/bin/env python3
"""Separate appearance-follow ROS adapter. Inactive on startup; no default target.

Uses exactly the observer's synchronized clean projection, never raw-box mixing.
The full isolated launch is the only supported execution topology.
"""
import argparse
import math
import signal
import subprocess
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from geometry_msgs.msg import Twist
from std_msgs.msg import String
from std_srvs.srv import Trigger
from sensor_msgs.msg import JointState
from controller_manager_msgs.srv import ListControllers

from .appearance_color_observer import AppearanceObserver, create_projector
from .appearance_follow_policy import AppearanceFollowPolicy
from .shirt_color_selector import COLORS


class AppearancePersonFollower(AppearanceObserver):
    def __init__(self, projector, preview=True, preview_port=8766):
        self.policy = AppearanceFollowPolicy()
        super().__init__(projector, "red", preview, preview_port,
                         mode="APPEARANCE_FOLLOW", node_name="appearance_person_follower")
        self.lock = self.policy.lock
        self.declare_parameter("homing_verified", False)
        self.controller_active = False
        self.controller_received = self.joints_received = None
        self.controller_future = None
        self.controller_client = self.create_client(ListControllers, "/controller_manager/list_controllers")
        self.create_subscription(JointState, "/joint_states", self.joint_feedback, 1)
        self.create_timer(0.5, self.poll_controller)
        self.velocity_pub = self.create_publisher(Twist, "/person_following_cmd_vel", 1)
        self.create_service(Trigger, "/appearance_follow/activate", self.arm)
        self.create_service(Trigger, "/appearance_follow/deactivate", self.stop)
        # Keep the old emergency/manual STOP useful, but expose NO old arm alias.
        self.create_service(Trigger, "/deactivate_person_following", self.stop)
        self.create_service(Trigger, "/appearance_follow/check", self.check)
        self.create_service(Trigger, "/appearance_follow/ready", self.ready)
        for color in COLORS:
            self.create_service(Trigger, "/appearance_follow/select_" + color,
                                lambda request, response, color=color: self.select(color, response))
        self.zero()
        self.get_logger().info("APPEARANCE FOLLOW: inactive; preview READ ONLY; no ordinary-follower fallback")

    @property
    def active(self):
        return self.policy.active

    def zero(self):
        self.policy.x = self.policy.yaw = 0.0
        self.velocity_pub.publish(Twist())

    def select(self, color, response):
        self.policy.select(color)
        self.zero()
        # Clear all pre-request frames. Selecting a colour only stops/selects;
        # activation is a SEPARATE, explicitly confirmed command.
        AppearanceObserver.change_color(self, String(data=color))
        self.policy.lock.reset()
        response.success, response.message = True, f"SELECTED {color}; inactive; explicit arm required"
        return response

    def arm(self, request, response):
        if not self.controller_ready():
            response.success, response.message = False, "Verified homing, active neural_controller and fresh 12-joint feedback required"
            return response
        if self.policy.active or self.policy.color not in COLORS:
            response.success, response.message = False, "Stop and select an explicit shirt colour first"
            return response
        # The arm begins a new capture session, not the already displayed frame.
        AppearanceObserver.change_color(self, String(data=self.policy.color))
        response.success = self.policy.arm()
        self.zero()
        response.message = "ACQUIRING: unique matching shirt near centre; waits for stable LOCKED"
        return response

    def stop(self, request, response):
        self.policy.stop()
        self.zero()
        for buffer in self.buffers.values():
            buffer.clear()
        response.success, response.message = True, "Following inactive; target selection cleared"
        return response

    def change_color(self, message):
        # Defence in depth: even an accidental internal preview command cannot
        # retarget a moving session or arm movement.
        return self.select(message.data, type("Response", (), {})())

    def reject_frame(self, reason):
        self.geometry_ok = False
        self.policy.reject(reason)
        self.wait_reason, self.evidence = reason, []
        self.last_image = self.last_image_received = None
        self.people = self.matches = 0
        self.zero()

    def update_lock(self, boxes, candidates, stamp, camera_age, now):
        index = self.policy.observe(boxes, candidates, stamp, camera_age, now)
        if self.lock.state != "LOCKED":
            self.zero()
        return index

    def joint_feedback(self, message):
        if (len(set(message.name)) >= 12 and len(message.position) == len(message.name)
                and all(math.isfinite(value) for value in message.position)):
            self.joints_received = time.monotonic()
        else:
            self.joints_received = None

    def poll_controller(self):
        if self.controller_future is not None and not self.controller_future.done():
            if time.monotonic() - self.controller_requested > 1.5:
                self.controller_future.cancel()
                self.controller_active = False
            else:
                return
        if self.controller_client.service_is_ready():
            self.controller_requested = time.monotonic()
            self.controller_future = self.controller_client.call_async(ListControllers.Request())
            self.controller_future.add_done_callback(self.controller_result)
        else:
            self.controller_active = False

    def controller_result(self, future):
        if future.cancelled() or future.exception() is not None:
            self.controller_active = False
            return
        result = future.result()
        self.controller_active = result is not None and any(
            item.name == "neural_controller" and item.state == "active"
            for item in result.controller
        )
        self.controller_received = time.monotonic()

    def controller_ready(self):
        now = time.monotonic()
        return (self.get_parameter("homing_verified").value is True
                and self.controller_active and self.controller_received is not None
                and now - self.controller_received <= 1.5
                and self.joints_received is not None and now - self.joints_received <= 0.5)

    def ready(self, request, response):
        if not self.controller_ready():
            response.success, response.message = False, "Waiting for verified homing, active controller and fresh 12-joint feedback"
            return response
        now = time.monotonic()
        gap = None if self.last_image_received is None else now - self.last_image_received
        age = None if gap is None or self.frame_age is None else self.frame_age + gap
        response.success = (self.controller_ready() and self.geometry_ok and gap is not None and gap <= 0.30
                            and age is not None and -0.05 <= age <= 0.30)
        response.message = "APPEARANCE_FOLLOW synchronized geometry ready" if response.success else self.wait_reason
        return response

    def check(self, request, response):
        self.policy.command(time.monotonic())
        if self.lock.state != "LOCKED":
            self.zero()
        response.success = self.active and self.lock.state == "LOCKED"
        response.message = self.lock.state + ": " + self.lock.reason
        return response

    def tick(self):
        if self.policy.active and not self.controller_ready():
            self.policy.stop()
            self.zero()
        super().tick()
        x, yaw = self.policy.command(time.monotonic())
        command = Twist()
        command.linear.x, command.angular.z = x, yaw
        self.velocity_pub.publish(command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--preview-port", type=int, default=8766)
    args, ros_args = parser.parse_known_args()
    if not 1 <= args.preview_port <= 65535:
        parser.error("Invalid preview port")
    # Hailo is a sibling process in the same launch; wait for its real parameters,
    # never guess a default FOV or bypass the synchronized-image checks.
    deadline = time.monotonic() + 45
    while True:
        try:
            projector = create_projector()
            break
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Hailo not ready; no following started: {exc}") from exc
            print(f"Waiting for Hailo projection: {exc}", flush=True)
            time.sleep(0.5)
    rclpy.init(args=ros_args)
    node = None
    try:
        node = AppearancePersonFollower(projector, preview_port=args.preview_port)
        def interrupt(signum, frame):
            raise KeyboardInterrupt
        for name in ("SIGTERM", "SIGHUP"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), interrupt)
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.policy.stop()
            if rclpy.ok():
                node.zero()
            if node.web_preview is not None:
                node.web_preview.close()
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
