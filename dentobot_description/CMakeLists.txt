cmake_minimum_required(VERSION 3.16)
project(dentobot_description)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch meshes rviz urdf
  DESTINATION share/${PROJECT_NAME}
)

install(
  FILES README.md
  DESTINATION share/${PROJECT_NAME}
)

install(
  PROGRAMS scripts/neutral_joint_state_publisher.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME neutral_joint_state_publisher
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(
    test_description
    test/test_description.py
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  )
endif()

ament_package()
