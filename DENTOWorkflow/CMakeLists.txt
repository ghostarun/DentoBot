#-----------------------------------------------------------------------------
set(MODULE_NAME DENTOWorkflow)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  Resources/Python/DENTOApplicationShell.py
  Resources/Python/DENTOCaseBundle.py
  Resources/Python/DENTOGuideGeometry.py
  Resources/Python/DENTOPlatform.py
  Resources/Python/DENTOROS2Bridge.py
  Resources/Python/DENTORobotPlacement.py
  Resources/Python/DENTORobotSimulationPanel.py
  Resources/Python/DENTORobotWorkflowFacade.py
  Resources/Python/DENTOStep6Planning.py
  Resources/Python/DENTOTemplateGeometry.py
  Resources/Python/DENTOTrajectoryGeometry.py
  )

set(MODULE_PYTHON_RESOURCES
  Resources/UI/${MODULE_NAME}.ui
  Resources/Themes/dentobot-light.qss
  Resources/Themes/dentobot-dark.qss
  )

# Keep one source copy in dentobot_description while making the exact tracked
# URDF/STLs available beside an installed scripted module. configure_file
# registers the inputs as CMake dependencies and copies them only to the build
# tree that slicerMacroBuildScriptedModule later installs/packages.
set(ROBOT_DESCRIPTION_FILES
  urdf/dentobot.urdf
  meshes/link-1.stl
  meshes/link-2.stl
  meshes/link-3.stl
  meshes/link-4.stl
  meshes/link-5.stl
  meshes/pneumatic_spindle-Copy.stl
  meshes/burr.stl
  )
set(ROBOT_DESCRIPTION_SOURCE_DIR
  ${CMAKE_CURRENT_SOURCE_DIR}/../dentobot_description
  )
set(ROBOT_DESCRIPTION_BUILD_DIR
  ${CMAKE_BINARY_DIR}/${Slicer_QTSCRIPTEDMODULES_LIB_DIR}/Resources/RobotDescription
  )
foreach(relative_path IN LISTS ROBOT_DESCRIPTION_FILES)
  get_filename_component(relative_directory ${relative_path} DIRECTORY)
  file(MAKE_DIRECTORY ${ROBOT_DESCRIPTION_BUILD_DIR}/${relative_directory})
  configure_file(
    ${ROBOT_DESCRIPTION_SOURCE_DIR}/${relative_path}
    ${ROBOT_DESCRIPTION_BUILD_DIR}/${relative_path}
    COPYONLY
    )
endforeach()

#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  WITH_GENERIC_TESTS
  )

#-----------------------------------------------------------------------------
if(BUILD_TESTING)
  slicer_add_python_unittest(SCRIPT ${MODULE_NAME}.py)
endif()
