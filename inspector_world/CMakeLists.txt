cmake_minimum_required(VERSION 3.8)
project(inspector_world)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch maps models worlds
  DESTINATION share/${PROJECT_NAME})

install(PROGRAMS
  tools/stop_all.sh
  tools/gt_localizer.py
  tools/route_runner.py
  tools/inspection_db.py
  tools/inspection_report.py
  tools/gauge_inference.py
  tools/gauge_reader_node.py
  tools/start_factory_profile.sh
  DESTINATION lib/${PROJECT_NAME})

ament_package()
