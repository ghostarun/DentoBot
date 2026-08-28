# DENTOWorkflow internal package

This package holds the implementation behind the stable Slicer entrypoints in
`DENTOWorkflow.py`. The entrypoint only composes the public module, widget,
logic, parameter-node, and test classes. Existing MRML roles, `.dentocase`
fields, public method names, signal handlers, and algorithm bodies remain the
compatibility contract.

## Routing map

| Concern | Start here |
|---|---|
| Module construction and signal binding | `widget_bootstrap.py`, `widget_panels.py` |
| GUI mode, developer reload, persistent view palette | `widget_application.py` |
| Scene close/import/save and observer cleanup | `widget_lifecycle.py` |
| Case files and external inference controls | `widget_case_backend.py`, `logic_case_bundle.py`, `logic_backend.py` |
| Segmentation review | `widget_segmentation.py`, `logic_segmentation.py` |
| View inventory and presets | `widget_view_catalog.py`, `widget_view_controls.py`, `widget_view_composition.py` |
| Workflow navigation and interaction locks | `widget_navigation.py`, `logic_lineage.py` |
| Trajectory placement and verification | `widget_trajectory_view.py`, `widget_planning_focus.py`, `widget_planning.py` |
| Target docking | `widget_docking.py`, `logic_docking.py` |
| Downstream planning deletion/invalidation | `logic_planning_dependencies.py`, `logic_workflow.py` |
| Support selection and visible support surface | `widget_guide_support_setup.py`, `widget_guide_support.py`, `logic_guide_support.py` |
| Patient shell and unified template build | `widget_template_build.py`, `logic_patient_shell.py`, `logic_guide.py` |
| Template finalization and verification | `widget_template_finalization.py`, `logic_finalization.py` |
| Step 6 shell actions | `widget_robot_shell.py`, `widget_robot.py` |
| Robot placement, jaw/phantom setup | `widget_robot_placement.py`, `widget_robot_scene.py`, `logic_robot_placement.py`, `logic_phantom_scene.py` |
| Planning-scene synchronization, Step 6 jaw landmarks, and robot task state | `logic_robot_scene_sync.py`, `logic_robot.py`, `logic_step6_scene.py`, `logic_step6_landmark_review.py` |
| Persistent typed state and stage identifiers | `parameter_state.py`, `contracts.py` |
| Slicer-native regression archive | `slicer_tests.py` |

The older top-level `DENTO*.py` helpers remain stable algorithm/service seams.
In particular, UI modules call `DENTORobotWorkflowFacade`; they do not add a
second ROS, IK, collision, or kinematic implementation.

## Dependency and performance rules

- Domain modules may import `runtime.py` and narrower sibling mixins, but must
  not import the public `DENTOWorkflow` entrypoint.
- MRML and the typed parameter node remain authoritative. Do not introduce a
  second application-state database.
- Keep RAS/mm to ROS/metres conversion in the existing adapters.
- Keep UI code free of URDF parsing, FK/IK, collision mathematics, and direct
  ROS orchestration.
- Do not add a process, thread, socket, HTTP client, worker, or watched-folder
  boundary to solve code-organization problems.
- Routine implementation modules have a 1,500-line context ceiling. Split at
  cohesive method boundaries before exceeding it. `slicer_tests.py` and the
  shared compatibility-import module are explicit exceptions.
- The broad imports in `runtime.py` preserve globals for the mechanically
  relocated methods. Tightening them is optional cleanup and must be done in
  small, tested domain batches.

## Safe change sequence

1. Read `Workspace/docs/AGENT_CONTEXT.md`, today's logbook, and the relevant
   files from the routing table.
2. Change the narrowest domain module. Change a top-level `DENTO*.py` helper
   only when the shared service/algorithm contract itself changes.
3. Preserve public method signatures; `Testing/contracts/dentoworkflow_api.json`
   detects accidental API drift or duplicated owners.
4. Run `pytest -q Testing` and `git diff --check`.
5. For UI/lifecycle changes, run the focused Slicer smoke. For reload changes,
   run `Testing/run_dentobot_slicer_reload_smoke.py` through Slicer; it performs
   five reload cycles and checks both helper and internal-module replacement.
6. Record commands, evidence, failures, and unresolved risks in today's
   logbook. A synthetic pass is not clinical or hardware evidence.

The developer Reload button evicts both `DENTO*.py` helpers and all
`dentobot_workflow.*` modules before Slicer's supported scripted-module reload.
It preserves the MRML scene and requires the operator to reconnect ROS state.
