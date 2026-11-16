@echo off
title Unitree Go2 Inspector
wsl.exe -d Ubuntu-24.04 -- bash -lc "source \"$HOME/inspection_venv/bin/activate\"; source /opt/ros/jazzy/setup.bash; source \"$HOME/ros2_ws/install/setup.bash\"; ros2 run inspector_world stop_all.sh"
wsl.exe -d Ubuntu-24.04 -- bash -lc "source \"$HOME/inspection_venv/bin/activate\"; source /opt/ros/jazzy/setup.bash; source \"$HOME/ros2_ws/install/setup.bash\"; ros2 launch inspector_world inspection_mission.launch.py software_render:=false camera_view:=true ai:=true ai_view:=true"
echo.
echo Simulation stopped. Press any key to close.
pause >nul
