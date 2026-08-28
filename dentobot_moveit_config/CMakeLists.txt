cmake_minimum_required(VERSION 3.16)
project(dentobot_moveit_config)

find_package(ament_cmake REQUIRED)
find_package(jsoncpp REQUIRED)
find_package(moveit_core REQUIRED)
find_package(moveit_ros_planning REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)

add_executable(collision_guard src/collision_guard.cpp)
target_compile_features(collision_guard PUBLIC cxx_std_17)
target_link_libraries(collision_guard JsonCpp::JsonCpp)
ament_target_dependencies(
  collision_guard
  moveit_core
  moveit_ros_planning
  rclcpp
  std_msgs
)

install(
  TARGETS collision_guard
  DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
