#!/bin/bash

# Source ROS2 environment
source /opt/ros/jazzy/setup.bash

# Set vol to 100%
amixer sset 'Master' 100%

# Set SW volume to 150%
wpctl set-volume @DEFAULT_SINK@ 1.0

# Source local workspace
source /home/pi/pupperv3-monorepo/ros2_ws/install/local_setup.bash

# Run the agent with the dependencies installed by `uv sync`.
export ROS_LOCALHOST_ONLY=1
exec .venv/bin/python -u src/agent.py console
