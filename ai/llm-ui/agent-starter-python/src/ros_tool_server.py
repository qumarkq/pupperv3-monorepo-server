import base64
import random
from typing import Tuple, Optional, Any, Dict
import threading
import queue
from pupster import ANIMATION_NAMES
import rclpy
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
import logging
from controller_manager_msgs.srv import SwitchController, ListControllers
from std_srvs.srv import Trigger
from dataclasses import dataclass, field
from geometry_msgs.msg import Twist
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String
import asyncio
from abc import ABC, abstractmethod
import time
import gemini_interface
from PIL import Image
import io
import gemini_utils
import ros_image_utils
import os
from appearance_follow_client import AppearanceFollowClient

logger = logging.getLogger("ros_tool_server")
AVAILABLE_CONTROLLERS = {
    "neural_controller",
    "neural_controller_three_legged",
    "forward_kp_controller",
    "forward_position_controller",
    "forward_kd_controller",
}

# Single animation controller name
ANIMATION_CONTROLLER_NAME = "animation_controller_py"


@dataclass
class MoveCfg:
    vx_threshold: float = 0.4  # m/s
    vy_threshold: float = 0.4  # m/s
    wz_threshold: float = 30.0  # deg/s
    vx_max: float = 0.75  # m/s
    vy_max: float = 0.5  # m/s
    wz_max: float = 120.0  # deg/s


@dataclass
class DefaultCfg:
    move_cfg: MoveCfg = field(default_factory=MoveCfg)


DEFAULT_CFG = DefaultCfg()


class Command(ABC):
    """Base class for all robot commands"""

    def __init__(self, name: str):
        self.name = name
        self.timestamp = time.time()

    @abstractmethod
    async def execute(self, server: "RosToolServer") -> Tuple[bool, str]:
        """Execute the command and return success status and message"""
        pass


# TODO: The warnings will only show up on execution but the LLM won't see them and would benefit from seeing the warnings when queueing
class MoveCommand(Command):
    def __init__(self, vx: float, vy: float, wz: float, server: "RosToolServer"):
        super().__init__("move")
        self.vx = vx
        self.vy = vy
        self.wz = wz

        if abs(vx) > server.cfg.move_cfg.vx_max:
            raise ValueError(f"vx {vx} exceeds max limit of ±{server.cfg.move_cfg.vx_max}")
        if abs(vy) > server.cfg.move_cfg.vy_max:
            raise ValueError(f"vy {vy} exceeds max limit of ±{server.cfg.move_cfg.vy_max}")
        if abs(wz) > server.cfg.move_cfg.wz_max:
            raise ValueError(f"wz {wz} exceeds max limit of ±{server.cfg.move_cfg.wz_max}")

        # Check if all velocities are below their thresholds
        if (
            abs(vx) < server.cfg.move_cfg.vx_threshold
            and abs(vy) < server.cfg.move_cfg.vy_threshold
            and abs(wz) < server.cfg.move_cfg.wz_threshold
        ):
            raise ValueError("All velocities (vx, vy, wz) are below their movement thresholds, robot may not move")

    async def execute(self, server: "RosToolServer") -> Tuple[bool, str]:
        # Validate velocity constraints
        vx = self.vx
        vy = self.vy
        wz = self.wz

        # Create and publish Twist message
        twist = Twist()
        twist.linear.x = float(vx)
        twist.linear.y = float(vy)
        twist.angular.z = float(wz) / 57.2958  # Convert deg/s to rad/s

        server.twist_pub.publish(twist)

        message = f"Robot moving with velocities vx={vx}, vy={vy}, wz={wz}"
        server.node.get_logger().info(f"Executing MoveCommand - vx: {vx}, vy: {vy}, wz: {wz}")
        return True, message


class StopCommand(Command):
    def __init__(self):
        super().__init__("stop")

    async def execute(self, server: "RosToolServer") -> Tuple[bool, str]:
        twist = Twist()
        twist.linear.x = 0.0
        twist.linear.y = 0.0
        twist.angular.z = 0.0

        server.twist_pub.publish(twist)

        server.node.get_logger().info("Executed StopCommand")
        return True, "Robot stopped successfully"


class WaitCommand(Command):
    def __init__(self, duration: float):
        super().__init__("wait")
        self.duration = duration

    async def execute(self, server: "RosToolServer") -> Tuple[bool, str]:
        await asyncio.sleep(self.duration)
        server.node.get_logger().info(f"Executed WaitCommand for {self.duration} seconds")
        return True, f"Waited for {self.duration} seconds"


class MoveForTimeCommand(Command):
    def __init__(self, vx: float, vy: float, wz: float, duration: float, server: "RosToolServer"):
        super().__init__("move_for_time")

        self.move_cmd = MoveCommand(vx, vy, wz, server)
        self.wait_cmd = WaitCommand(duration)
        self.stop_cmd = StopCommand()

    # TODO: Make the queue processor accept "CompositeCommand" so this can be simpler
    async def execute(self, server: "RosToolServer") -> Tuple[bool, str]:
        # Execute move command
        success, message = await self.move_cmd.execute(server)
        if not success:
            return False, f"Move failed: {message}"

        # Wait for the specified duration
        success, message = await self.wait_cmd.execute(server)

        # Execute stop command
        success, message = await self.stop_cmd.execute(server)
        if not success:
            return False, f"Stop failed: {message}"

        return (
            True,
            f"Completed move_for_time: vx={self.move_cmd.vx}, vy={self.move_cmd.vy}, wz={self.move_cmd.wz} for {self.wait_cmd.duration}s",
        )


def list_controllers(server: "RosToolServer") -> Optional[Dict[str, str]]:
    list_req = ListControllers.Request()
    list_future = server.list_controllers_client.call_async(list_req)
    rclpy.spin_until_future_complete(server.node, list_future, timeout_sec=2.0)

    if list_future.done() and list_future.result():
        controllers = list_future.result().controller
        return controllers
    return None

def is_controller_active(server: "RosToolServer", controller_name: str) -> bool:
    """Check if a specific controller is currently active.

    Args:
        server: The RosToolServer instance
        controller_name: Name of the controller to check

    Returns:
        True if the controller is active, False otherwise
    """
    controllers = list_controllers(server)
    if controllers is not None:
        for controller in controllers:
            if controller.name == controller_name and controller.state == "active":
                return True
    return False


class ActivateWalkingCommand(Command):
    def __init__(self):
        super().__init__("activate_walking")

    async def execute(self, server: "RosToolServer") -> Tuple[bool, str]:
        controller_name = server.current_walking_controller

        # Activate the walking controller
        req = SwitchController.Request()
        req.activate_controllers = [controller_name]
        server.node.get_logger().info(f"Activating controller: {controller_name}")
        req.deactivate_controllers = list(AVAILABLE_CONTROLLERS - {controller_name})
        server.node.get_logger().info(f"Deactivating controllers: {list(AVAILABLE_CONTROLLERS - {controller_name})}")
        req.strictness = 1

        future = server.switch_controller_client.call_async(req)
        rclpy.spin_until_future_complete(server.node, future, timeout_sec=2.0)

        if future.done() and future.result().ok:
            server.node.get_logger().info("🤖 Walking mode ACTIVATED")
            return True, f"Walking mode activated successfully with {controller_name}"
        else:
            server.node.get_logger().error("❌ Failed to activate walking mode")
            return False, "Failed to activate walking mode - controller switch failed"


class DeactivateCommand(Command):
    def __init__(self):
        super().__init__("deactivate")

    async def execute(self, server: "RosToolServer") -> Tuple[bool, str]:
        req = SwitchController.Request()
        req.activate_controllers = []
        req.deactivate_controllers = list(AVAILABLE_CONTROLLERS)
        req.strictness = 1

        future = server.switch_controller_client.call_async(req)
        rclpy.spin_until_future_complete(server.node, future, timeout_sec=2.0)

        if future.done() and future.result().ok:
            server.node.get_logger().info("🤖 Robot DEACTIVATED")
            return True, "Robot deactivated successfully"
        else:
            server.node.get_logger().error("❌ Failed to deactivate robot")
            return False, "Failed to deactivate robot - controller switch failed"


# TODO: Make this block while the animation runs by using a service!
class AnimationCommand(Command):
    def __init__(self, animation_csv_name: str):
        super().__init__(f"animation_{animation_csv_name}")
        self.animation_csv_name = animation_csv_name

    async def execute(self, server: "RosToolServer") -> Tuple[bool, str]:
        try:
            # Publish the animation name to the animation_controller_py topic
            # The animation_controller_py will handle controller switching automatically
            topic_name = f"/{ANIMATION_CONTROLLER_NAME}/animation_select"
            if topic_name not in server.animation_publishers:
                # Create publisher if it doesn't exist
                server.animation_publishers[topic_name] = server.node.create_publisher(String, topic_name, 10)

            # Publish animation selection
            msg = String()
            msg.data = self.animation_csv_name
            server.animation_publishers[topic_name].publish(msg)

            server.node.get_logger().info(f"🎭 Animation '{self.animation_csv_name}' requested")
            return True, f"Animation '{self.animation_csv_name}' started successfully"

        except Exception as e:
            server.node.get_logger().error(f"❌ Failed to start animation '{self.animation_csv_name}': {e}")
            return False, f"Failed to start animation '{self.animation_csv_name}': {e}"


class RosToolServer():
    def __init__(self, cfg=DEFAULT_CFG):
        self.cfg = cfg
        rclpy.init()
        self.node = Node("ros_tool_server")
        self.switch_controller_client = self.node.create_client(
            SwitchController, "/controller_manager/switch_controller"
        )
        self.list_controllers_client = self.node.create_client(ListControllers, "/controller_manager/list_controllers")
        self.current_walking_controller = "neural_controller"  # default walking controller

        self.activate_person_following_client = self.node.create_client(Trigger, "activate_person_following")
        self.deactivate_person_following_client = self.node.create_client(Trigger, "deactivate_person_following")
        self.person_follow_mode = os.getenv("PUPSTER_PERSON_FOLLOW_MODE", "ordinary").strip().lower()
        if self.person_follow_mode not in {"ordinary", "appearance"}:
            raise ValueError("PUPSTER_PERSON_FOLLOW_MODE must be ordinary or appearance")
        self.appearance_clients = {}
        self._appearance_stop_unconfirmed = False
        self.appearance_follow = AppearanceFollowClient(
            self._call_appearance_service,
            lambda: is_controller_active(self, self.current_walking_controller),
            settle_delay=0.6, walking_timeout=8.0,
        )
        self.following_mode_status = "inactive"

        # Initialize command queue
        self.command_queue = asyncio.Queue()
        self.queue_running = False
        self.queue_task = None
        self.current_command_task = None

        # Publish LLM commands through cmd_vel_mux so teleop and e-stop keep
        # their higher-priority safety behavior.
        self.cmd_vel_topic = os.getenv("PUPSTER_CMD_VEL_TOPIC", "/llm_cmd_vel")
        if self.person_follow_mode == "appearance" and self.cmd_vel_topic != "/llm_cmd_vel":
            raise ValueError("Appearance mode requires PUPSTER_CMD_VEL_TOPIC=/llm_cmd_vel for confirmed-stop override")
        self.twist_pub = self.node.create_publisher(Twist, self.cmd_vel_topic, 10)
        self.node.get_logger().info(
            f"Publishing voice movement commands to {self.cmd_vel_topic}"
        )

        # Dictionary to hold animation publishers (created on demand)
        self.animation_publishers = {}

        # Image subscription node: keep only the most recent compressed image
        self.image_node = Node("ros_tool_server_images")
        self.latest_image_queue: "queue.Queue[CompressedImage]" = queue.Queue(maxsize=1)
        self.image_sub = self.image_node.create_subscription(
            CompressedImage,
            "/camera/image_raw/compressed",
            self._on_image,
            1,
        )

        if self.person_follow_mode == "appearance":
            self.appearance_stop_timer = self.image_node.create_timer(0.05, self._publish_appearance_stop)
            self.image_node.create_subscription(
                String, "/appearance_follow/status", self._on_appearance_status, 1,
            )

        self.gemini_annotated_image_publisher = self.node.create_publisher(
            CompressedImage, "/gemini/annotated_image", 10
        )

        # Start ROS executor in a background thread
        self.executor = SingleThreadedExecutor()
        # Only add the image node to this executor so control node remains
        # free to use spin_until_future_complete in service calls.
        self.executor.add_node(self.image_node)
        self._ros_thread = threading.Thread(target=self._spin_executor, name="ros-executor", daemon=True)
        self._ros_thread.start()

        self.start_queue_processor()

        self.node.get_logger().info("ROS Tool Server has been started.")

    async def get_camera_image(self, context: Any) -> Dict[str, Any]:
        from livekit.agents.llm import ImageContent

        self.node.get_logger().info("FUNCTION CALL: get_camera_image")

        latest_ros_compressed_img_msg = self.latest_image_queue.get_nowait()
        b64 = base64.b64encode(latest_ros_compressed_img_msg.data).decode("utf-8")
        ctx = context.session.current_agent.chat_ctx.copy()
        ctx.add_message(
            role="user",
            content=[ImageContent(image=f"data:image/jpeg;base64,{b64}")],
        )
        self.node.get_logger().info(f"Adding image to conversation, size: {len(b64)} bytes.....")
        await context.session.current_agent.update_chat_ctx(ctx)
        # log image number of bytes
        self.node.get_logger().info(f"Added image to conversation, size: {len(b64)} bytes")
        return True, "Image added to conversation"

    # TODO: LLM might want to start the queue processor explicitly so it can control when commands start executing.
    # For now, we can start it automatically when the server is created.
    # For instance, the LLM often takes several seconds to queue up commands and it's possible the behavior will be wrong if
    # the commands start executing before the LLM is done queueing them.
    def start_queue_processor(self):
        """Start the background task that processes commands from the queue"""
        if not self.queue_running:
            self.queue_running = True
            self.queue_task = asyncio.create_task(self._process_command_queue())
            self.node.get_logger().info("Command queue processor started")

    async def stop_queue_processor(self):
        """Stop the command queue processor"""
        self.queue_running = False
        if self.queue_task:
            await self.queue_task
            self.node.get_logger().info("Command queue processor stopped")

    def _spin_executor(self):
        """Spin the ROS executor in a dedicated thread."""
        try:
            self.executor.spin()
        except Exception as e:
            self.node.get_logger().error(f"ROS executor stopped with error: {e}")
            raise e

    def _on_image(self, msg: CompressedImage):
        """Keep only the latest image in a thread-safe single-slot queue."""
        try:
            # Drop previous image if present to keep only the latest
            if self.latest_image_queue.full():
                try:
                    self.latest_image_queue.get_nowait()
                except queue.Empty:
                    pass
            self.latest_image_queue.put_nowait(msg)
            # logging.info("Enqueued latest image")
        except Exception as e:
            self.node.get_logger().warning(f"Failed to enqueue latest image: {e}")

    async def _process_command_queue(self):
        """Background task that processes commands from the queue sequentially"""
        while self.queue_running:
            try:
                # Wait for a command with timeout to allow checking queue_running
                command = await asyncio.wait_for(self.command_queue.get(), timeout=0.1)
                self.node.get_logger().info(f"Executing command: {command.name}")

                # Create a cancellable task for the command execution
                self.current_command_task = asyncio.create_task(command.execute(self))

                try:
                    success, message = await self.current_command_task
                    if success:
                        self.node.get_logger().info(f"Command {command.name} succeeded: {message}")
                    else:
                        self.node.get_logger().error(f"Command {command.name} failed: {message}")

                ################## Handle cancellation ##################
                except asyncio.CancelledError:
                    self.node.get_logger().info(f"Command {command.name} was cancelled")
                    # Ensure robot is stopped after cancellation
                    stop_cmd = StopCommand()
                    await stop_cmd.execute(self)
                    self.node.get_logger().info("Robot stopped after command cancellation")

                ################### Handle other exceptions ###################
                except Exception as e:
                    self.node.get_logger().error(f"Error executing command {command.name}: {e}")
                finally:
                    self.current_command_task = None

            except asyncio.TimeoutError:
                # Timeout is expected, continue loop to check queue_running
                # Log every 10 seconds if the queue is empty
                if random.random() < 0.01:
                    self.node.get_logger().info("Command queue processor waiting for commands...")
                continue
            except Exception as e:
                self.node.get_logger().error(f"Unexpected error in command queue processor: {e}")

    async def add_command(self, command: Command) -> None:
        """Add a command to the queue"""
        if self.person_follow_mode == "appearance" and isinstance(
            command, (MoveCommand, MoveForTimeCommand, AnimationCommand, DeactivateCommand),
        ):
            stopped, message = await self.deactivate_person_following()
            if not stopped:
                raise RuntimeError("Cannot change motion while follow stop is unconfirmed: " + message)
        await self.command_queue.put(command)
        self.node.get_logger().info(f"Added command {command.name} to queue")

    async def queue_move_for_time(self, vx: float, vy: float, wz: float, duration: float) -> Tuple[bool, str]:
        """Queue a move_for_time operation as a single command"""
        self.node.get_logger().info(
            f"FUNCTION CALL: queue_move_for_time command: vx={vx}, vy={vy}, wz={wz}, duration={duration}"
        )
        start_time = time.time()

        # Ensure walking controller is active before moving
        await self.queue_activate_walking()

        try:
            move_for_time_cmd = MoveForTimeCommand(vx, vy, wz, duration, self)
        except ValueError as e:
            self.node.get_logger().warning(f"Invalid parameters for move_for_time: {e}")
            return False, str(e)
        await self.add_command(move_for_time_cmd)
        self.node.get_logger().info(f"FUNCTION CALL: queue_move_for_time command took: {time.time() - start_time:.2f}s")
        return True, f"Queued move_for_time: vx={vx}, vy={vy}, wz={wz} for {duration}s"

    async def queue_activate_walking(self):
        """Queue an activate walking command"""
        self.node.get_logger().info("FUNCTION CALL: queue_activate_walking")

        # Check if walking controller is active, if not queue activation and wait
        do_wait = False
        if not is_controller_active(self, self.current_walking_controller):
            self.node.get_logger().info(
                f"Walking controller {self.current_walking_controller} not active, will wait for activation to finish"
            )
            do_wait = True

        self.node.get_logger().info("Queueing activate walking command")
        await self.add_command(ActivateWalkingCommand())
        if do_wait:
            await self.add_command(WaitCommand(2.5))  # wait 2.5 seconds for controller to activate
        return True, "Activate walking command queued"

    async def queue_deactivate(self):
        """Queue a deactivate command"""
        self.node.get_logger().info("FUNCTION CALL: queue_deactivate")
        await self.add_command(DeactivateCommand())
        return True, "Deactivate command queued"

    async def queue_stop(self):
        """Queue a stop command"""
        self.node.get_logger().info("FUNCTION CALL: queue_stop")
        await self.deactivate_person_following()
        await self.add_command(StopCommand())
        return True, "Stop command queued"

    async def queue_wait(self, duration: float):
        """Queue a wait command"""
        self.node.get_logger().info(f"FUNCTION CALL: queue_wait with duration {duration}")
        await self.add_command(WaitCommand(duration))
        return True, f"Wait command for {duration} seconds queued"

    async def queue_animation(self, animation_name: str):
        """Queue an animation command"""
        self.node.get_logger().info(f"FUNCTION CALL: queue_animation with animation_name {animation_name}")
        try:
            animation_cmd = AnimationCommand(animation_name)
            await self.add_command(animation_cmd)
            return True, f"Animation '{animation_name}' queued"
        except ValueError as e:
            self.node.get_logger().warning(f"Invalid animation name: {e}")
            return False, str(e)

    async def _interrupt_and_stop(self) -> Tuple[bool, str]:
        """Interrupt current command and immediately stop the robot"""
        self.node.get_logger().info("_interrupt_and_stop: Interrupting current command and stopping robot")
        start_time = time.time()

        # Cancel the currently executing command if any
        if self.current_command_task and not self.current_command_task.done():
            self.node.get_logger().info(f"Cancelling current command task")
            self.current_command_task.cancel()
            # The cancellation handler in _process_command_queue will stop the robot

            # Wait a moment for the cancellation to complete
            try:
                await asyncio.wait_for(self.current_command_task, timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        else:
            # No command running, just stop the robot directly
            await self.deactivate_person_following()
            stop_cmd = StopCommand()
            await stop_cmd.execute(self)

        self.node.get_logger().info(
            f"RosToolServer: _interrupt_and_stop done. Took: {time.time() - start_time:0.3f} seconds"
        )
        return True, "Current command interrupted and robot stopped"

    async def clear_queue(self) -> Tuple[bool, str]:
        """Clear all pending commands from the queue"""
        self.node.get_logger().info("clear_queue")
        count = 0
        while not self.command_queue.empty():
            try:
                self.command_queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break

        self.node.get_logger().info(f"Cleared {count} commands from queue")
        return True, f"Cleared {count} pending commands from queue"

    async def immediate_stop(self) -> Tuple[bool, str]:
        """Immediate stop: interrupt current command, stop robot, and clear queue"""
        self.node.get_logger().warning("IMMEDIATE STOP initiated")
        start_time = time.time()

        stopped, stop_message = await self.deactivate_person_following()

        # Then clear the queue
        await self.clear_queue()

        # First interrupt and stop
        await self._interrupt_and_stop()

        if self.person_follow_mode == "appearance" and not stopped:
            return False, "Follow stop unconfirmed; holding zero velocity: " + stop_message
        self.node.get_logger().warning(f"IMMEDIATE STOP completed. Took: {time.time() - start_time:0.3f} seconds")
        return True, "Immediate stop completed: robot stopped and queue cleared"

    def _on_appearance_status(self, message):
        self.following_mode_status = "active" if " LOCKED:" in message.data else "inactive"

    def _publish_appearance_stop(self):
        # Runs on the image-node executor thread, independently of blocking ROS
        # service waits on the voice event loop. A single zero would expire.
        if self._appearance_stop_unconfirmed:
            self.twist_pub.publish(Twist())

    def _hold_appearance_stop(self):
        self._appearance_stop_unconfirmed = True
        self.twist_pub.publish(Twist())

    async def _call_appearance_service(self, action) -> Tuple[bool, str]:
        if action == "deactivate":
            self._hold_appearance_stop()
        name = "/appearance_follow/" + action
        if name not in self.appearance_clients:
            self.appearance_clients[name] = self.node.create_client(Trigger, name)
        client = self.appearance_clients[name]
        if not client.wait_for_service(timeout_sec=0.5):
            return False, "Missing service: " + name
        if action == "ready":
            publishers = self.node.get_publishers_info_by_topic("/person_following_cmd_vel")
            if len(publishers) != 1 or publishers[0].node_name != "appearance_person_follower":
                return False, "Expected exactly one appearance-follow velocity publisher"
        future = client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=3.0)
        if not future.done() or future.result() is None:
            future.cancel()
            return False, "Service timed out: " + name
        result = future.result()
        if action == "deactivate" and result.success:
            self._appearance_stop_unconfirmed = False
        return result.success, result.message

    async def _prepare_appearance_follow(self):
        await self.clear_queue()
        task = self.current_command_task
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=0.5)
            except asyncio.CancelledError:
                pass
        await StopCommand().execute(self)

    async def activate_appearance_following(self, shirt_color: str) -> Tuple[bool, str]:
        if self.person_follow_mode != "appearance":
            return False, "Start ROS with person_follow_mode:=appearance and set PUPSTER_PERSON_FOLLOW_MODE=appearance"
        # Preparation runs inside the acquisition transaction so STOP invalidates
        # even requests that are still cancelling an old movement command.
        success, message = await self.appearance_follow.follow(
            shirt_color, prepare=self._prepare_appearance_follow,
        )
        self.following_mode_status = "active" if success else "inactive"
        return success, message

    async def activate_person_following(self) -> Tuple[bool, str]:
        if self.person_follow_mode == "appearance":
            return False, "Appearance mode requires an explicit upper-shirt colour; use activate_appearance_following"
        self.node.get_logger().info("Activating person following...")
        fut = self.activate_person_following_client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self.node, fut, timeout_sec=3.0)
        if fut.done() and fut.result() is not None:
            if fut.result().success:
                self.following_mode_status = "active"
            return fut.result().success, fut.result().message
        return False, "Failed to call activate_person_following service"

    async def deactivate_person_following(self) -> Tuple[bool, str]:
        if self.person_follow_mode == "appearance":
            success, message = await self.appearance_follow.stop()
            if success:
                self.following_mode_status = "inactive"
            return success, message
        self.node.get_logger().info("Deactivating person following...")
        fut = self.deactivate_person_following_client.call_async(Trigger.Request())
        rclpy.spin_until_future_complete(self.node, fut, timeout_sec=3.0)
        if fut.done() and fut.result() is not None:
            if fut.result().success:
                self.following_mode_status = "inactive"
            return fut.result().success, fut.result().message
        return False, "Failed to call deactivate_person_following service"

    async def analyze_camera_image(self, prompt: str, context: Any) -> Tuple[bool, str]:
        self.node.get_logger().info(f"FUNCTION CALLED: analyze_camera_image(prompt={prompt})")

        # OpenCV is only needed for the optional camera-analysis tool. Keep it
        # lazy so voice-only console movement can start without cv2 installed.
        import fisheye_utils

        start_time = time.time()

        # Get image from queue
        image_msg = self.latest_image_queue.get_nowait()
        image = Image.open(io.BytesIO(image_msg.data)).convert("RGB")

        self.node.get_logger().info("loaded image")

        # Convert fisheye to equirectangular
        camera_params_path = os.path.join(os.path.dirname(__file__), "camera_params.yaml")
        equirect_image, equirect_width, equirect_height, h_fov_deg = fisheye_utils.fisheye_to_equirectangular(
            image, camera_params_path
        )

        self.node.get_logger().info("converted to equirectangular")

        # Analyze with Gemini
        text = gemini_interface.analyze_camera_image(prompt, equirect_image)
        self.node.get_logger().info(f"Gemini raw text: {text}")

        boxes = gemini_utils.parse_bounding_boxes(text)
        boxes_pixels = [gemini_utils.transform_to_pixels(box, 1400, 1050, 1000) for box in boxes]
        self.node.get_logger().info("parsed bounding boxes")

        # Convert bounding box centroids to elevation/heading coordinates
        objects_with_elevation_heading = fisheye_utils.convert_boxes_to_elevation_heading(
            boxes_pixels, equirect_width, equirect_height, h_fov_deg
        )

        self.node.get_logger().info("converted boxes to elevation/heading")

        # Log object positions
        for obj in objects_with_elevation_heading:
            self.node.get_logger().info(
                f"Object: {obj['label']}  - "
                f"Elevation: {obj['elevation_deg']:.2f}°, Heading: {obj['heading_deg']:.2f}°"
            )

        # Publish annotated image
        annotated_img = gemini_utils.draw_bounding_boxes(equirect_image, boxes)
        annotated_img_msg = ros_image_utils.pil_to_compressed_msg(annotated_img)
        self.gemini_annotated_image_publisher.publish(annotated_img_msg)

        self.node.get_logger().info("published annotated image")

        # Create response with elevation/heading information
        response_parts = [text]
        if objects_with_elevation_heading:
            response_parts.append("\n\nObject positions (elevation/heading):")
            for obj in objects_with_elevation_heading:
                response_parts.append(
                    f"- {obj['label']}: elevation={obj['elevation_deg']:.2f}°, heading={obj['heading_deg']:.2f}°"
                )

        response = "\n".join(response_parts)
        self.node.get_logger().info(f"Published annotated equirectangular image with {len(boxes)} bounding boxes")
        self.node.get_logger().info(f"analyze_camera_image response: {response}")
        self.node.get_logger().info(f"analyze_camera_image took: {time.time() - start_time:0.3f} seconds")
        return True, response

    async def check_mode(self) -> Tuple[bool, str]:
        if self.person_follow_mode == "appearance":
            locked, _ = await self._call_appearance_service("check")
            self.following_mode_status = "active" if locked else "inactive"
        controller_statuses = list_controllers(self)
        if controller_statuses is None:
            return False, "Controller status unavailable"
        animation_mode = any(c.name == "forward_position_controller" and c.state=="active" for c in controller_statuses)
        walking_mode = any(c.name == "neural_controller" and c.state=="active" for c in controller_statuses)
        following_mode = self.following_mode_status == "active"
        idle_mode = not (animation_mode or walking_mode or following_mode)
        result_str = f"Animation mode: {animation_mode}, Walking mode: {walking_mode}, Following mode: {following_mode}, Idle mode: {idle_mode}"
        self.node.get_logger().info(f"check_mode result: {result_str}")
        return True, result_str
