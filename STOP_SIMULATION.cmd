@echo off
title Unitree Go2 Inspector - Stop
wsl.exe -d Ubuntu-24.04 -- bash -lc "source /opt/ros/jazzy/setup.bash; source \"$HOME/ros2_ws/install/setup.bash\"; ros2 run inspector_world stop_all.sh"
echo.
echo All ROS 2 and Gazebo processes were stopped.
pause
