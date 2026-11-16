@echo off
title Unitree Go2 Inspector - Custom Factory
wsl.exe -d Ubuntu-24.04 -- bash -lc "source \"$HOME/inspection_venv/bin/activate\"; source /opt/ros/jazzy/setup.bash; source \"$HOME/ros2_ws/install/setup.bash\"; ros2 run inspector_world stop_all.sh"
wsl.exe -d Ubuntu-24.04 -- bash -lc "source \"$HOME/inspection_venv/bin/activate\"; source /opt/ros/jazzy/setup.bash; source \"$HOME/ros2_ws/install/setup.bash\"; ros2 run inspector_world start_factory_profile.sh \"$HOME/factory_scene\""
echo.
echo Custom factory simulation stopped. Press any key to close.
pause >nul
