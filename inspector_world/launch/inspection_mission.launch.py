"""Полная автономная миссия одной командой:
симуляция Go2 в сцене → Nav2 → обход приборов по маршруту → отчёт.

    ros2 launch inspector_world inspection_mission.launch.py
    ros2 launch inspector_world inspection_mission.launch.py lidar:=true rviz:=true

Тайминги: контроллеры ходьбы Go2 активируются ~30 с после старта (их запускает
пакет unitree_go2_sim), поэтому Nav2 стартует через nav_delay (40 с), а миссия
сама ждёт, пока Nav2 станет активным.
"""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory("inspector_world")
    launch_dir = os.path.join(pkg, "launch")
    world = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(launch_dir, "inspection_world.launch.py")),
        launch_arguments={"rviz": LaunchConfiguration("rviz"), "lidar": LaunchConfiguration("lidar"),
                          "d455": "false", "software_render": LaunchConfiguration("software_render"),
                          "camera_view": LaunchConfiguration("camera_view")}.items())
    nav = IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(launch_dir, "navigation.launch.py")))
    return LaunchDescription([
        DeclareLaunchArgument("rviz", default_value="false"),
        DeclareLaunchArgument("lidar", default_value="false"),
        DeclareLaunchArgument("software_render", default_value="false", description="Рендер на CPU (если камера чёрная)"),
        DeclareLaunchArgument("camera_view", default_value="true", description="Окно с камерой робота"),
        DeclareLaunchArgument("nav_delay", default_value="40.0", description="Через сколько секунд запускать Nav2"),
        world,
        TimerAction(period=LaunchConfiguration("nav_delay"), actions=[nav]),
        DeclareLaunchArgument("dwell", default_value="2.5", description="Сколько секунд стоять у прибора"),
        TimerAction(period=LaunchConfiguration("nav_delay"), actions=[
            Node(package="inspector_world", executable="route_runner.py", name="route_runner",
                 output="screen", emulate_tty=True, arguments=["--dwell", LaunchConfiguration("dwell")])]),
    ])
