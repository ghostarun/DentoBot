"""Pure/static contracts for the incremental DENTOBOT application shell."""

from __future__ import annotations

import os
import sys
import ast
from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

from DENTOApplicationShell import (  # noqa: E402
    GUI_MODE_LEGACY,
    GUI_MODE_SHELL,
    WORKSPACE_SPECS,
    normalize_gui_mode,
    normalize_theme,
    step6_enabled,
    workspace_for_stage,
    workspace_index_for_stage,
)
from DENTOStep6State import JOINT_NAMES  # noqa: E402


def test_native_windows_fallback_disables_step6():
    previous = os.environ.get("DENTOBOT_WORKFLOW_PROFILE")
    try:
        os.environ["DENTOBOT_WORKFLOW_PROFILE"] = "native-windows-steps-0-5"
        assert not step6_enabled()
        os.environ["DENTOBOT_WORKFLOW_PROFILE"] = ""
        assert step6_enabled()
    finally:
        if previous is None:
            os.environ.pop("DENTOBOT_WORKFLOW_PROFILE", None)
        else:
            os.environ["DENTOBOT_WORKFLOW_PROFILE"] = previous


def test_six_workspaces_cover_every_legacy_stage_once():
    assert len(WORKSPACE_SPECS) == 6
    stages = [stage for spec in WORKSPACE_SPECS for stage in spec.stage_indices]
    assert stages == list(range(11))
    assert len(set(stages)) == 11


def test_workspace_mapping_preserves_segmentation_and_guide_substeps():
    assert workspace_for_stage(0).workspace_id == "case"
    assert workspace_for_stage(2).workspace_id == "segmentation"
    assert workspace_for_stage(3).workspace_id == "segmentation"
    assert workspace_for_stage(4).workspace_id == "drill_planning"
    assert workspace_for_stage(5).workspace_id == "guide_design"
    assert workspace_for_stage(9).workspace_id == "guide_design"
    assert workspace_for_stage(10).workspace_id == "robot_simulation"
    assert workspace_for_stage(10).substep_titles == (
        "6.0 Activate Verified PreparedBranch",
        "6.1A–6.1B Offline Base and ROS Gate",
        "6.2 Validated Task Home",
        "Planning & Diagnostics",
        "Preview & Control",
    )
    assert workspace_index_for_stage(999) == 0


def test_step6_navigation_and_primary_actions_use_phase_names():
    assert workspace_for_stage(10).substep_titles[-2:] == (
        "Planning & Diagnostics",
        "Preview & Control",
    )
    panel = (HELPERS / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    assert '"Preview Approach", self.previewControlGroup' in panel
    assert 'QPushButton("Prepare Drill Preview"' in panel
    assert '"Preview Drill", self.previewControlGroup' in panel
    assert "Goal 1" not in panel and "Goal 2" not in panel


def test_mode_and_theme_preferences_fail_closed_to_legacy_light():
    assert normalize_gui_mode("shell") == GUI_MODE_SHELL
    assert normalize_gui_mode("unexpected") == GUI_MODE_LEGACY
    assert normalize_theme("dark") == "dark"
    assert normalize_theme("unexpected") == "light"


def test_theme_resources_define_semantic_workspace_states():
    for name in ("dentobot-light.qss", "dentobot-dark.qss"):
        source = (
            ROOT / "DENTOWorkflow" / "Resources" / "Themes" / name
        ).read_text(encoding="utf-8")
        assert 'dentobotRole="workspace"' in source
        assert 'dentobotRole="warning"' in source
        assert 'dentobotRecommended="true"' in source


def test_workflow_owns_one_switchable_shell_and_restores_it_on_exit():
    application = (
        HELPERS / "dentobot_workflow/widget_application.py"
    ).read_text(encoding="utf-8")
    lifecycle = (
        HELPERS / "dentobot_workflow/widget_lifecycle.py"
    ).read_text(encoding="utf-8")
    assert "self._applicationShell = DENTOApplicationShell(" in application
    assert "DENTOApplicationShell.storedGuiMode()" in application
    exit_handler = lifecycle.split("def exit(self)", 1)[1].split(
        "def _addSceneObservers", 1
    )[0]
    assert "self._applicationShell.deactivate()" in exit_handler
    assert "DENTOWorkflow-v2" not in application + lifecycle


def test_new_shell_exposes_the_shared_view_controls_palette():
    shell = (HELPERS / "DENTOApplicationShell.py").read_text(encoding="utf-8")
    workflow = (
        HELPERS / "dentobot_workflow/widget_application.py"
    ).read_text(encoding="utf-8")
    assert "DENTOBOTViewControlsButton" in shell
    assert "self._on_view_controls_requested()" in shell
    assert "on_view_controls_requested=self.onOpenViewControlsPalette" in workflow


def test_shell_preferences_are_qsettings_not_parameter_node_fields():
    shell = (HELPERS / "DENTOApplicationShell.py").read_text(encoding="utf-8")
    workflow = (
        HELPERS / "dentobot_workflow/parameter_state.py"
    ).read_text(encoding="utf-8")
    parameter_block = workflow.split("class DENTOWorkflowParameterNode", 1)[1].split(
        "class DENTOWorkflow", 1
    )[0]
    assert "QSettings" in shell
    assert "GuiMode" not in parameter_block
    assert "Theme" not in parameter_block


def test_robot_shell_panel_is_presentation_only_and_uses_facade_callbacks():
    panel = (HELPERS / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    workflow = (
        HELPERS / "dentobot_workflow/widget_robot_shell.py"
    ).read_text(encoding="utf-8")
    assert "import DENTOROS2Bridge" not in panel
    assert "computeIK" not in panel
    assert '"solve_ik": self._onShellSolveIk' in workflow
    assert "self._robotWorkflowFacade.solveIk()" in workflow
    assert "self._robotWorkflowFacade.syncPlanningScene()" in workflow


def test_step6_cartesian_goal_requires_explicit_drag_toggle_and_has_no_plan_route():
    workflow = (
        HELPERS / "dentobot_workflow" / "widget_robot_shell.py"
    ).read_text(encoding="utf-8")
    assert '"set_tcp_drag_enabled": self._onShellSetTcpDragEnabled' in workflow
    assert '"nudge_tcp_goal": self._onShellNudgeTcpGoal' in workflow
    assert '"create_goal":' not in workflow
    assert '"plan_goal":' not in workflow
    assert "def _onShellPlanGoal" not in workflow
    assert "facade.setTcpDragEnabled(bool(enabled))" in workflow
    assert "return bool(result.success)" in workflow

    solve = workflow.split("def _onShellSolveIk", 1)[1].split(
        "def _onShellSyncCollisionScene", 1
    )[0]
    assert "errorDisplay" not in solve
    assert "if result.success is not True:" in solve
    assert "set(payload) != set(JOINT_NAMES)" in solve
    assert "isfinite(value) for value in payload.values()" in solve
    assert "stageTcpIkSolution(payload)" in solve
    assert solve.index("if failure:") < solve.index(
        "stageTcpIkSolution(payload)"
    )
    assert "_onShellGuardedManualJog" not in solve
    assert "planToGoal" not in solve and "_step6MotionPlan" not in solve

    substeps = workflow.split("visible_by_substep = {", 1)[1].split(
        "for group in visible_by_substep[index]", 1
    )[0]
    planning_and_diagnostics = substeps.split("3:", 1)[1].split("4:", 1)[0]
    assert "self._robotSimulationPanel.goalGroup" in planning_and_diagnostics


def test_tcp_ik_shell_stages_only_successful_complete_finite_j1_j5_payload():
    shell_path = HELPERS / "dentobot_workflow/widget_robot_shell.py"
    tree = ast.parse(shell_path.read_text(encoding="utf-8"))
    shell_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RobotShellWidgetMixin"
    )
    solve_node = next(
        node
        for node in shell_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "_onShellSolveIk"
    )
    namespace = {
        "Mapping": Mapping,
        "JOINT_NAMES": JOINT_NAMES,
        "isfinite": isfinite,
        "slicer": SimpleNamespace(
            util=SimpleNamespace(errorDisplay=lambda message: error_messages.append(message))
        ),
    }
    error_messages = []
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[solve_node], type_ignores=[])),
            str(shell_path),
            "exec",
        ),
        namespace,
    )
    solve = namespace["_onShellSolveIk"]

    def run(success, payload, details=None):
        joint_draft = {name: -1.0 for name in JOINT_NAMES}
        accepted_state = {name: float(index) for index, name in enumerate(JOINT_NAMES)}
        events = []
        result = SimpleNamespace(
            success=success,
            message="static validity unknown" if success is not True else "authoritative valid",
            payload=payload,
            details=details or {},
        )

        class Panel:
            _tcpIkStageFailureText = ""

            def showGoalResult(self, value):
                events.append(("show", value))

            def stageTcpIkSolution(self, value):
                events.append(("stage", dict(value)))
                joint_draft.update(value)
                return True

            def setManualJogDraftDisplayResult(self, ok, message):
                events.append(("draft_status", ok, message))

            def setManualJogStatus(self, state, message):
                events.append(("jog_status", state, message))

        panel = Panel()
        host = SimpleNamespace(
            _robotSimulationPanel=panel,
            _robotWorkflowFacade=SimpleNamespace(solveIk=lambda: result),
        )
        solve(host)
        return events, joint_draft, accepted_state

    valid = {name: float(index) + 0.25 for index, name in enumerate(JOINT_NAMES)}
    events, draft, accepted = run(True, valid)
    assert [event[0] for event in events] == ["show", "stage"]
    assert draft == valid
    assert accepted == {name: float(index) for index, name in enumerate(JOINT_NAMES)}

    invalid_responses = (
        (False, valid, {"authoritativeStaticValidity": False}),
        (False, {}, {"authoritativeStaticValidity": None, "failureEvidence": "unknown"}),
        (True, {name: value for name, value in valid.items() if name != JOINT_NAMES[-1]}, {}),
        (True, {**valid, JOINT_NAMES[0]: float("nan")}, {}),
        (True, {**valid, "unexpected_joint": 0.0}, {}),
    )
    for success, payload, details in invalid_responses:
        events, draft, accepted = run(success, payload, details)
        assert not any(event[0] == "stage" for event in events)
        assert draft == {name: -1.0 for name in JOINT_NAMES}
        assert accepted == {name: float(index) for index, name in enumerate(JOINT_NAMES)}
        assert any(event[0] == "draft_status" and event[1] is False for event in events)
        assert any(event[0] == "jog_status" for event in events)
    assert error_messages == []

    joint_draft = {name: -1.0 for name in JOINT_NAMES}
    accepted_state = {name: float(index) for index, name in enumerate(JOINT_NAMES)}
    events = []

    class GoalStatusLabel:
        text = ""

        def setProperty(self, name, value):
            events.append(("goal_status_property", name, value))

    class ExceptionPanel:
        _tcpIkStageFailureText = ""
        goalStatusLabel = GoalStatusLabel()

        def showGoalResult(self, value):
            events.append(("show", value))

        def stageTcpIkSolution(self, value):
            events.append(("stage", dict(value)))
            joint_draft.update(value)
            return True

        def setManualJogDraftDisplayResult(self, ok, message):
            events.append(("draft_status", ok, message))

        def setManualJogStatus(self, state, message):
            events.append(("jog_status", state, message))

    panel = ExceptionPanel()

    def raise_solve_error():
        raise RuntimeError("native IK review unavailable")

    host = SimpleNamespace(
        _robotSimulationPanel=panel,
        _robotWorkflowFacade=SimpleNamespace(solveIk=raise_solve_error),
    )
    solve(host)
    assert "native IK review unavailable" in panel.goalStatusLabel.text
    assert "retained" in panel.goalStatusLabel.text
    assert not any(event[0] == "stage" for event in events)
    assert joint_draft == {name: -1.0 for name in JOINT_NAMES}
    assert accepted_state == {name: float(index) for index, name in enumerate(JOINT_NAMES)}
    assert error_messages == []


def test_motion_diagnostics_show_the_retained_task_trajectory_and_base_identity():
    panel = (HELPERS / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    facade = (HELPERS / "DENTORobotWorkflowFacade.py").read_text(encoding="utf-8")
    assert "Evidence identity" in panel
    assert "session.task_fingerprint[:12]" in panel
    assert "session.trajectory_fingerprint[:12]" in panel
    assert "session.base_fingerprint[:12]" in panel
    assert "This is endpoint reachability" in panel
    assert '"failure_classification": "preentry_ik_unreachable"' in facade
    assert 'STEP6_JOINT_PLANNER_ID = "RRTConnectkConfigDefault"' in facade
    assert facade.count("planner_id=STEP6_JOINT_PLANNER_ID") == 3
    # Includes the clearance detour second-leg MoveIt call.
    assert facade.count("planner_id=self._joint_planner_id") == 4
    assert 'STEP6_JOINT_PLANNER_ALGORITHM = "geometric::RRTConnect"' in facade
    assert "Planning policy" in panel
    assert "approximate_ik_enabled" in panel
    assert "cartesian_planning_enabled" in panel
    assert panel.count('"Planning Parameters…"') == 2
    assert "def planningPolicy" in panel
    assert "STEP6_JOINT_PLANNER_ALGORITHMS.items()" in panel
    assert "requested joint planner" in panel
    assert "MoveGroup configured ID" in panel
    assert "execution algorithm unverified" in panel
    assert "Approximate IK:" in panel
    assert "Cartesian Stage 2/3:" in panel
    shell = (
        HELPERS / "dentobot_workflow" / "widget_robot_shell.py"
    ).read_text(encoding="utf-8")
    assert "**self._robotSimulationPanel.planningPolicy()" in shell


def test_step6_planning_controls_explain_bounds_and_locked_modes():
    panel = (HELPERS / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    assert "Start with this workflow's 1-attempt baseline" in panel
    assert "Start with this workflow's 5.0 s baseline" in panel
    assert "Locked off: the current PreEntry solver" in panel
    assert "Locked on: Stage 2/3 still use MoveIt Cartesian planning" in panel
    assert "layout.labelForField(field).toolTip = field.toolTip" in panel


def test_step6_planner_choices_match_moveit_and_reject_unknown_ids():
    import yaml
    from DENTORobotWorkflowFacade import (
        DENTORobotWorkflowFacade,
        STEP6_JOINT_PLANNER_ALGORITHMS,
    )

    ompl = yaml.safe_load(
        (ROOT / "dentobot_moveit_config/config/ompl_planning.yaml").read_text()
    )
    assert STEP6_JOINT_PLANNER_ALGORITHMS == {
        planner_id: ompl["planner_configs"][planner_id]["type"]
        for planner_id in ompl["dentobot_arm"]["planner_configs"]
    }
    assert set(STEP6_JOINT_PLANNER_ALGORITHMS) == {
        "RRTConnectkConfigDefault",
        "RRTkConfigDefault",
        "RRTstarkConfigDefault",
    }
    rejected = DENTORobotWorkflowFacade(None, lambda: None).planApproachPhase(
        planner_id="not-configured"
    )
    assert not rejected.success
    assert "not configured" in rejected.message


def test_step6_legacy_and_shell_use_the_same_seven_substep_cards():
    workflow = (
        HELPERS / "dentobot_workflow/widget_robot_shell.py"
    ).read_text(encoding="utf-8")
    assert "DENTOBOTStep6SubstepNavigator" in workflow
    assert "workspace_for_stage(10).substep_titles" in workflow
    assert "self._configureRobotSimulationShellSubstep(substep_index)" in workflow
    assert "def _restoreLegacyRobotSimulationGroups" in workflow
    assert "def _syncOfflinePlacementHost" in workflow


def test_step3b_shares_one_offline_placement_surface_with_step61() -> None:
    navigation = (
        HELPERS / "dentobot_workflow/widget_navigation.py"
    ).read_text(encoding="utf-8")
    panel = (HELPERS / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    placement = (
        HELPERS / "dentobot_workflow/widget_robot_placement.py"
    ).read_text(encoding="utf-8")
    scene = (
        HELPERS / "dentobot_workflow/widget_robot_scene.py"
    ).read_text(encoding="utf-8")
    assert "DENTOBOTStep3SubstepNavigator" in navigation
    assert "DENTOBOTStep3AContentWidget" not in navigation
    assert "_setStep3AOriginalWidgetsVisible" in navigation
    assert "3B — Offline Robot Placement" in navigation
    assert "Confirm and continue to Step 3B" in scene
    assert "onStep3BGoToStep4" in scene
    assert "PLACEMENT_SURFACE_ACTIONS" in panel
    assert "setPlacementSurfaceActive" in panel
    assert "PASS — Step 3B virtual-forehead auto-placement" in placement
    assert "_isOfflinePlacementSurfaceActive" in placement


def test_workflow_scroll_area_installs_combo_popup_wheel_guards() -> None:
    application = (
        HELPERS / "dentobot_workflow/widget_application.py"
    ).read_text(encoding="utf-8")
    scroll_support = (
        HELPERS / "dentobot_workflow/ui_scroll_support.py"
    ).read_text(encoding="utf-8")
    assert "installScrollAreaComboBoxWheelGuards(scrollArea)" in application
    assert "def installScrollAreaComboBoxWheelGuards" in scroll_support
    assert "setWindowFlags" not in scroll_support
    assert "showPopup" not in scroll_support
    assert "maxVisibleItems" in scroll_support


def test_new_empty_case_resets_entire_workflow_to_step_zero() -> None:
    lifecycle = (
        HELPERS / "dentobot_workflow/widget_lifecycle.py"
    ).read_text(encoding="utf-8")
    navigation = (
        HELPERS / "dentobot_workflow/widget_navigation.py"
    ).read_text(encoding="utf-8")
    case_backend = (
        HELPERS / "dentobot_workflow/widget_case_backend.py"
    ).read_text(encoding="utf-8")
    assert "_resetWorkflowStateForFreshCase" in lifecycle
    assert "_captureCaseFoundationSessionSnapshot" not in case_backend.split(
        "def onNewCase", 1
    )[1].split("def ", 1)[0]
    assert "self._pendingFreshCaseReset = True" in case_backend
    assert "_pendingFreshCaseReset" in navigation
    assert "_setWorkflowStage(0" in lifecycle


def test_lock_base_session_snapshot_tolerates_missing_landmarks() -> None:
    scene = (
        HELPERS / "dentobot_workflow/widget_robot_scene.py"
    ).read_text(encoding="utf-8")
    robot = (
        HELPERS / "dentobot_workflow/widget_robot.py"
    ).read_text(encoding="utf-8")
    capture = scene.split(
        "def _captureCaseFoundationSessionSnapshot", 1
    )[1].split("def ", 1)[0]
    assert "if landmarks is not None:" in capture
    assert 'landmarks.GetAttribute("DENTOBOT.SurfaceEvidenceJson")' in capture
    lock = robot.split("def onLockRobotBaseMount", 1)[1].split("def ", 1)[0]
    assert "try:" in lock
    assert "_captureCaseFoundationSessionSnapshot()" in lock
    assert "logging.exception" in lock


def test_saved_case_navigation_keeps_every_workspace_selectable():
    shell = (HELPERS / "DENTOApplicationShell.py").read_text(encoding="utf-8")
    navigation = (
        HELPERS / "dentobot_workflow/widget_navigation.py"
    ).read_text(encoding="utf-8")
    case_backend = (
        HELPERS / "dentobot_workflow/widget_case_backend.py"
    ).read_text(encoding="utf-8")
    assert "button.enabled = True" in shell
    assert "All workspaces remain selectable" in shell
    assert "workflowStageComboBox.enabled = True" in navigation
    assert "All Steps 1–6 remain selectable" in case_backend
