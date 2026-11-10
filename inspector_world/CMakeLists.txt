cmake_minimum_required(VERSION 3.8)
project(inspector_world)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch maps models worlds
  DESTINATION share/${PROJECT_NAME})

install(PROGRAMS tools/stop_all.sh tools/gt_localizer.py tools/route_runner.py
  DESTINATION lib/${PROJECT_NAME})

ament_package()
