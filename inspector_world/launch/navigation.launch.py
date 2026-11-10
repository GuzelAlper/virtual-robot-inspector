"""Nav2 для Go2: карта сцены + планировщик + контроллер + поведенческие узлы.

    ros2 launch inspector_world navigation.launch.py

Запускать после inspection_world.launch.py, когда Go2 встал (контроллеры ходьбы активны).
Только нужные узлы Nav2 (без AMCL, docking, collision monitor): локализацию даёт gt_localizer.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

NODES = ["map_server", "controller_server", "planner_server", "behavior_server", "bt_navigator"]


def generate_launch_description():
    pkg = get_package_share_directory("inspector_world")
    params = LaunchConfiguration("params_file")
    common = [params, {"use_sim_time": True}]
    return LaunchDescription([
        DeclareLaunchArgument("params_file", default_value=os.path.join(pkg, "config", "nav2_params.yaml")),
        DeclareLaunchArgument("map", default_value=os.path.join(pkg, "maps", "inspection_hall.yaml")),
        Node(package="nav2_map_server", executable="map_server", name="map_server", output="screen",
             parameters=[params, {"use_sim_time": True, "yaml_filename": LaunchConfiguration("map")}]),
        Node(package="nav2_controller", executable="controller_server", name="controller_server",
             output="screen", parameters=common),
        Node(package="nav2_planner", executable="planner_server", name="planner_server",
             output="screen", parameters=common),
        Node(package="nav2_behaviors", executable="behavior_server", name="behavior_server",
             output="screen", parameters=common),
        Node(package="nav2_bt_navigator", executable="bt_navigator", name="bt_navigator",
             output="screen", parameters=common),
        Node(package="nav2_lifecycle_manager", executable="lifecycle_manager", name="lifecycle_manager_navigation",
             output="screen",
             parameters=[{"use_sim_time": True, "autostart": True, "node_names": NODES, "bond_timeout": 0.0}]),
    ])
