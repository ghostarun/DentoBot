#-----------------------------------------------------------------------------
set(MODULE_NAME DENTOWorkflow)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  Resources/Python/DENTOApplicationShell.py
  Resources/Python/DENTOCaseBundle.py
  Resources/Python/DENTOViewPresets.py
  Resources/Python/DENTOGuideGeometry.py
  Resources/Python/DENTOPlatform.py
  Resources/Python/DENTOROS2Bridge.py
  Resources/Python/DENTORobotPlacement.py
  Resources/Python/DENTORobotSimulationPanel.py
  Resources/Python/DENTORobotWorkflowFacade.py
  Resources/Python/DENTOStep6Planning.py
  Resources/Python/DENTOStep6State.py
  Resources/Python/DENTOTemplateGeometry.py
  Resources/Python/DENTOTrajectoryGeometry.py
  Resources/Python/dentobot_workflow/__init__.py
  Resources/Python/dentobot_workflow/contracts.py
  Resources/Python/dentobot_workflow/parameter_state.py
  Resources/Python/dentobot_workflow/runtime.py
  Resources/Python/dentobot_workflow/widget_bootstrap.py
  Resources/Python/dentobot_workflow/widget_application.py
  Resources/Python/dentobot_workflow/widget_panels.py
  Resources/Python/dentobot_workflow/widget_lifecycle.py
  Resources/Python/dentobot_workflow/widget_segmentation.py
  Resources/Python/dentobot_workflow/widget_trajectory_view.py
  Resources/Python/dentobot_workflow/widget_planning_focus.py
  Resources/Python/dentobot_workflow/widget_docking.py
  Resources/Python/dentobot_workflow/widget_planning.py
  Resources/Python/dentobot_workflow/widget_guide_support_setup.py
  Resources/Python/dentobot_workflow/widget_guide_support.py
  Resources/Python/dentobot_workflow/widget_template_build.py
  Resources/Python/dentobot_workflow/widget_template_finalization.py
  Resources/Python/dentobot_workflow/widget_guide_build.py
  Resources/Python/dentobot_workflow/widget_case_backend.py
  Resources/Python/dentobot_workflow/widget_robot_shell.py
  Resources/Python/dentobot_workflow/widget_robot_placement.py
  Resources/Python/dentobot_workflow/widget_robot_scene.py
  Resources/Python/dentobot_workflow/widget_robot.py
  Resources/Python/dentobot_workflow/widget_view_catalog.py
  Resources/Python/dentobot_workflow/widget_view_controls.py
  Resources/Python/dentobot_workflow/widget_view_composition.py
  Resources/Python/dentobot_workflow/widget_navigation.py
  Resources/Python/dentobot_workflow/widget_views.py
  Resources/Python/dentobot_workflow/logic_constants.py
  Resources/Python/dentobot_workflow/logic_core.py
  Resources/Python/dentobot_workflow/logic_backend.py
  Resources/Python/dentobot_workflow/logic_display.py
  Resources/Python/dentobot_workflow/logic_segmentation.py
  Resources/Python/dentobot_workflow/logic_lineage.py
  Resources/Python/dentobot_workflow/logic_planning_dependencies.py
  Resources/Python/dentobot_workflow/logic_workflow.py
  Resources/Python/dentobot_workflow/logic_guide_support.py
  Resources/Python/dentobot_workflow/logic_patient_shell.py
  Resources/Python/dentobot_workflow/logic_docking.py
  Resources/Python/dentobot_workflow/logic_guide.py
  Resources/Python/dentobot_workflow/logic_finalization.py
  Resources/Python/dentobot_workflow/logic_case_bundle.py
  Resources/Python/dentobot_workflow/logic_phantom_scene.py
  Resources/Python/dentobot_workflow/logic_step6_scene.py
  Resources/Python/dentobot_workflow/logic_robot_placement.py
  Resources/Python/dentobot_workflow/logic_robot_scene_sync.py
  Resources/Python/dentobot_workflow/logic_robot.py
  Resources/Python/dentobot_workflow/slicer_tests.py
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
