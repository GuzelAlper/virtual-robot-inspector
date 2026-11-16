"""Go2 в сцене инспекции: старт → коридор с препятствием → цех со станцией приборов.

    ros2 launch inspector_world inspection_world.launch.py
    ros2 launch inspector_world inspection_world.launch.py rviz:=true lidar:=true

Использует запуск робота из пакета unitree_go2_sim (khaledgabr77/unitree_go2_ros2),
подменяя только мир и стартовую позу, и добавляет gt_localizer (TF world → map для Nav2).
"""
import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (AppendEnvironmentVariable, DeclareLaunchArgument, IncludeLaunchDescription,
                            SetEnvironmentVariable)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory("inspector_world")
    go2_launch = os.path.join(get_package_share_directory("unitree_go2_sim"), "launch", "unitree_go2_launch.py")
    default_world = os.path.join(pkg, "worlds", "inspection_hall.sdf")
    with open(os.path.join(pkg, "config", "route.yaml"), encoding="utf-8") as f:
        start = yaml.safe_load(f)["start"]

    args = [
        DeclareLaunchArgument("world", default_value=default_world,
                              description="Gazebo SDF world file"),
        DeclareLaunchArgument("spawn_x", default_value=str(start["x"])),
        DeclareLaunchArgument("spawn_y", default_value=str(start["y"])),
        DeclareLaunchArgument("spawn_yaw", default_value=str(start["yaw"])),
        DeclareLaunchArgument("rviz", default_value="false", description="Открыть RViz"),
        DeclareLaunchArgument("lidar", default_value="false",
                              description="Лидар Velodyne: Nav2 видит новые препятствия (тяжелее для ПК)"),
        DeclareLaunchArgument("d455", default_value="false", description="Камера глубины RealSense D455 (тяжёлая)"),
        DeclareLaunchArgument("camera_view", default_value="true", description="Окно с камерой робота (/rgb_image)"),
        DeclareLaunchArgument("software_render", default_value="false",
                              description="Рендер на CPU (LIBGL_ALWAYS_SOFTWARE=1): если камера робота даёт чёрный кадр"),
    ]
    disable = lambda name: PythonExpression(["'false' if '", LaunchConfiguration(name), "' == 'true' else 'true'"])

    go2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(go2_launch),
        launch_arguments={
            "world": LaunchConfiguration("world"),
            "world_init_x": LaunchConfiguration("spawn_x"),
            "world_init_y": LaunchConfiguration("spawn_y"),
            "world_init_heading": LaunchConfiguration("spawn_yaw"),
            "rviz": LaunchConfiguration("rviz"),
            "disable_camera": "false",                 # фронтальная камера /rgb_image — для чтения приборов
            "disable_velodyne_lidar": disable("lidar"),
            "disable_d455": disable("d455"),
            "disable_lidar_l1": "true",                # в пакете помечен как недоработанный
        }.items(),
    )
    return LaunchDescription([
        AppendEnvironmentVariable("GZ_SIM_RESOURCE_PATH", os.path.join(pkg, "models")),
        *args,
        SetEnvironmentVariable("LIBGL_ALWAYS_SOFTWARE", "1", condition=IfCondition(LaunchConfiguration("software_render"))),
        SetEnvironmentVariable("GALLIUM_DRIVER", "llvmpipe", condition=IfCondition(LaunchConfiguration("software_render"))),
        go2,
        Node(package="inspector_world", executable="gt_localizer.py", name="gt_localizer", output="screen",
             parameters=[{"use_sim_time": True}]),
        Node(package="rqt_image_view", executable="rqt_image_view", name="camera_view", arguments=["/rgb_image"],
             condition=IfCondition(LaunchConfiguration("camera_view"))),
    ])
