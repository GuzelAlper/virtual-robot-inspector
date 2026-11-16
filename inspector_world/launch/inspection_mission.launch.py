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
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg = get_package_share_directory("inspector_world")
    launch_dir = os.path.join(pkg, "launch")
    default_model_dir = os.path.expanduser("~/inspection_models")
    default_world = os.path.join(pkg, "worlds", "inspection_hall.sdf")
    default_map = os.path.join(pkg, "maps", "inspection_hall.yaml")
    default_route = os.path.join(pkg, "config", "route.yaml")
    world = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(launch_dir, "inspection_world.launch.py")),
        launch_arguments={"rviz": LaunchConfiguration("rviz"), "lidar": LaunchConfiguration("lidar"),
                          "d455": "false", "software_render": LaunchConfiguration("software_render"),
                          "camera_view": LaunchConfiguration("camera_view"),
                          "world": LaunchConfiguration("world"),
                          "spawn_x": LaunchConfiguration("spawn_x"),
                          "spawn_y": LaunchConfiguration("spawn_y"),
                          "spawn_yaw": LaunchConfiguration("spawn_yaw")}.items())
    nav = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(launch_dir, "navigation.launch.py")),
        launch_arguments={"map": LaunchConfiguration("map")}.items(),
    )
    return LaunchDescription([
        DeclareLaunchArgument("world", default_value=default_world),
        DeclareLaunchArgument("map", default_value=default_map),
        DeclareLaunchArgument("route", default_value=default_route),
        DeclareLaunchArgument("spawn_x", default_value="0.0"),
        DeclareLaunchArgument("spawn_y", default_value="0.0"),
        DeclareLaunchArgument("spawn_yaw", default_value="0.0"),
        DeclareLaunchArgument("rviz", default_value="false"),
        DeclareLaunchArgument("lidar", default_value="false"),
        DeclareLaunchArgument("software_render", default_value="false", description="Рендер на CPU (если камера чёрная)"),
        DeclareLaunchArgument("camera_view", default_value="true", description="Окно с камерой робота"),
        DeclareLaunchArgument("ai", default_value="true", description="Распознавание приборов"),
        DeclareLaunchArgument("ai_view", default_value="true", description="Окно с результатом нейросети"),
        DeclareLaunchArgument(
            "locator_model",
            default_value=os.path.join(default_model_dir, "best_gauge_locator.pt"),
        ),
        DeclareLaunchArgument(
            "reader_model",
            default_value=os.path.join(default_model_dir, "best_gauge_distribution_reader.pt"),
        ),
        DeclareLaunchArgument("nav_delay", default_value="40.0", description="Через сколько секунд запускать Nav2"),
        DeclareLaunchArgument(
            "hop_dist",
            default_value="0.0",
            description="Боковой переход отключён: соседние приборы посещаются устойчиво через Nav2",
        ),
        world,
        TimerAction(period=5.0, actions=[
            Node(
                package="inspector_world",
                executable="gauge_reader_node.py",
                name="gauge_reader",
                output="screen",
                emulate_tty=True,
                arguments=[
                    "--locator", LaunchConfiguration("locator_model"),
                    "--reader", LaunchConfiguration("reader_model"),
                    "--device", "cpu",
                    "--output-dir", os.path.expanduser("~/inspection_ai"),
                ],
                condition=IfCondition(LaunchConfiguration("ai")),
            ),
            Node(
                package="rqt_image_view",
                executable="rqt_image_view",
                name="ai_camera_view",
                arguments=["/inspection/annotated_image"],
                condition=IfCondition(LaunchConfiguration("ai_view")),
            ),
        ]),
        TimerAction(period=LaunchConfiguration("nav_delay"), actions=[nav]),
        DeclareLaunchArgument("dwell", default_value="2.5", description="Сколько секунд стоять у прибора"),
        TimerAction(period=LaunchConfiguration("nav_delay"), actions=[
            Node(package="inspector_world", executable="route_runner.py", name="route_runner",
                 output="screen", emulate_tty=True,
                 arguments=[
                     "--dwell", LaunchConfiguration("dwell"),
                     "--hop-dist", LaunchConfiguration("hop_dist"),
                     "--route", LaunchConfiguration("route"),
                 ])]),
    ])
