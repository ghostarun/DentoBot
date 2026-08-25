"""Pure/static contracts for the incremental DENTOBOT application shell."""

from __future__ import annotations

import sys
from pathlib import Path


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
    workspace_for_stage,
    workspace_index_for_stage,
)


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
    assert len(workspace_for_stage(10).substep_titles) == 7
    assert workspace_index_for_stage(999) == 0


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
