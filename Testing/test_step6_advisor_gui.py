"""Step 6 Feasibility Advisor GUI lifecycle and safety wiring checks."""

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "DENTOWorkflow" / "Resources" / "Python"
GUI_PATH = PY / "dentobot_workflow" / "widget_step6_advisor.py"

METHODS = {
    "_advisorSetButtons",
    "_advisorOnStart",
    "_advisorOnCancel",
    "_advisorOnRejected",
    "_advisorOnClose",
    "_advisorOnFix",
    "_advisorCloseForNavigation",
    "_advisorTick",
    "_advisorBeginErrorRecovery",
    "_advisorReportRestoreUnconfirmed",
    "_advisorOnApplyAndSave",
    "_advisorOnExport",
}


def _load_gui_methods():
    tree = ast.parse(GUI_PATH.read_text(encoding="utf-8"))
    source_class = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                        and node.name == "Step6AdvisorWidgetMixin")
    body = [node for node in source_class.body if isinstance(node, ast.FunctionDef)
            and node.name in METHODS]
    assert {node.name for node in body} == METHODS

    class FakeMessageBox:
        Question = 1
        YesRole = 2
        NoRole = 3
        auto_confirm = True

        def __init__(self, parent=None):
            self.parent = parent
            self.buttons = []

        def setIcon(self, value):
            self.icon = value

        def setWindowTitle(self, value):
            self.title = value

        def setText(self, value):
            self.text = value

        def addButton(self, text, role):
            button = SimpleNamespace(text=text, role=role)
            self.buttons.append(button)
            return button

        def setDefaultButton(self, button):
            self.default = button

        def setEscapeButton(self, button):
            self.escape = button

        def exec_(self):
            return None

        def clickedButton(self):
            if self.auto_confirm:
                return next(button for button in self.buttons if button.text == "Apply & Save")
            return None

    namespace = {
        "_": lambda text: text,
        "advisor": SimpleNamespace(
            APPLY_STEPS=("apply_base", "apply_policy"),
            DONE="done", EVALUATING="evaluating", FOUND="found", IDLE="idle", RESTORING="restoring",
            working_configuration_record=lambda *args, **kwargs: {"config": "fake"},
        ),
        "step6_working_config": SimpleNamespace(normalize=lambda value: value),
        "qt": SimpleNamespace(QMessageBox=FakeMessageBox),
    }
    module = ast.fix_missing_locations(ast.Module(
        body=[ast.ClassDef(name="GuiMixin", bases=[], keywords=[], body=body, decorator_list=[])],
        type_ignores=[],
    ))
    exec(compile(module, str(GUI_PATH), "exec"), namespace)
    namespace["FakeMessageBox"] = FakeMessageBox
    return namespace["GuiMixin"]


GuiMixin = _load_gui_methods()


class Button:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.toolTip = ""


class Dialog:
    def __init__(self):
        self.hidden = False
        self.deleted = False
        self.shown = False
        self.raised = False

    def hide(self):
        self.hidden = True

    def show(self):
        self.shown = True

    def raise_(self):
        self.raised = True

    def deleteLater(self):
        self.deleted = True


class Timer:
    def __init__(self):
        self.starts = 0

    def start(self):
        self.starts += 1


def _buttons():
    return {name: Button() for name in (
        "startButton", "cancelButton", "moreButton", "applyButton", "exportButton", "closeButton",
    )}


class ApplySession:
    finished = True
    phase = "done"
    outcome = "found"
    baseline = {"opening": 42.0}
    saved_home = {"j1": 0.1}
    original = {"opening": 42.0}

    def __init__(self):
        self.apply_count = 0

    def best_candidate(self):
        return {"state_key": "best"}

    def required_acknowledgements(self, candidate):
        return []

    def apply_and_save(self, **kwargs):
        self.apply_count += 1


class Panel:
    def __init__(self):
        self.errors = []

    def showBranchConfigStatus(self, message, kind):
        self.errors.append((message, kind))


class ApplyWidget(GuiMixin):
    def __init__(self, restore_succeeds):
        self._workflowActionBusy = False
        self._step6WorkingConfigurationRestoreSucceeded = False
        self.restore_succeeds = restore_succeeds
        self._robotSimulationPanel = Panel()
        self.planning_errors = []
        session = ApplySession()
        self._advisorState = {
            **_buttons(), "session": session, "running": False, "restoreFailed": False,
            "configurationApplied": False, "fixButtons": [], "dialog": Dialog(),
            "statusLabel": SimpleNamespace(text=""), "stagedLabel": SimpleNamespace(text=""),
        }

    def _step6WorkingConfigurationSummary(self, value):
        return "fake configuration summary"

    def onRestoreStep6WorkingConfiguration(self):
        self._step6WorkingConfigurationRestoreSucceeded = self.restore_succeeds

    def _refreshStep6WorkingConfigurationStatus(self):
        return None

    def _updateStep6PlanningUi(self, message="", error=False):
        self.planning_errors.append((message, error))


def test_apply_save_reports_restore_success_and_failure_separately():
    for restore_succeeds in (True, False):
        widget = ApplyWidget(restore_succeeds)
        widget._advisorOnApplyAndSave()
        state = widget._advisorState
        assert state["session"].apply_count == 1
        if restore_succeeds:
            assert "restored through the Restore owner" in state["statusLabel"].text
            assert "not complete" not in state["statusLabel"].text
        else:
            assert "Saved on this branch, but Restore did not complete" in state["statusLabel"].text
            assert "Do not plan" in state["statusLabel"].text
            assert state["restoreFailed"] is True
            assert state["applyButton"].enabled is False
            assert widget._robotSimulationPanel.errors[-1][1] == "error"


def test_busy_state_blocks_duplicate_start_and_export():
    class Session:
        phase = "evaluating"
        baseline = {"opening": 42.0}
        finished = False

        def prepare(self):
            raise AssertionError("duplicate Start must not prepare another session")

        def export_evidence(self):
            raise AssertionError("Export must not run while the search is busy")

    class BusyWidget(GuiMixin):
        def __init__(self):
            self._workflowActionBusy = True
            self._advisorState = {
                **_buttons(), "session": Session(), "running": True,
                "restoreFailed": False, "configurationApplied": False,
                "fixButtons": [Button()],
            }

    widget = BusyWidget()
    widget._advisorOnStart()
    widget._advisorOnExport()
    widget._advisorOnApplyAndSave()
    widget._advisorOnFix("goto_6_1")
    widget._advisorSetButtons("running")
    state = widget._advisorState
    assert state["cancelButton"].enabled is True
    assert state["startButton"].enabled is False
    assert state["exportButton"].enabled is False
    assert state["applyButton"].enabled is False
    assert state["fixButtons"][0].enabled is False
    assert state["closeButton"].enabled is False


def test_navigation_fix_closes_and_releases_application_modal_dialog():
    calls = []

    class NavigationWidget(GuiMixin):
        def _onShellConnectRobot(self):
            calls.append("connect")

        def _onShellDisconnectRobot(self):
            calls.append("disconnect")

        def _onShellSyncCollisionScene(self):
            calls.append("sync_scene")

        def _configureRobotSimulationShellSubstep(self, substep):
            calls.append(substep)

    widget = NavigationWidget()
    dialog = Dialog()
    widget._workflowActionBusy = False
    widget._advisorState = {"dialog": dialog, "running": False}
    widget._advisorOnFix("goto_6_2")
    assert calls == [2]
    assert dialog.hidden and dialog.deleted
    assert dialog.shown is False
    assert widget._advisorState is None


def test_window_reject_requests_cancel_and_keeps_dialog_visible_until_done():
    class Session:
        def __init__(self):
            self.cancelled = 0

        def cancel(self):
            self.cancelled += 1

    widget = GuiMixin()
    session = Session()
    dialog = Dialog()
    widget._workflowActionBusy = True
    widget._advisorState = {
        "running": True, "session": session, "dialog": dialog,
        "cancelButton": Button(), "statusLabel": SimpleNamespace(text=""),
    }
    widget._advisorOnRejected()
    assert session.cancelled == 1
    assert widget._advisorState["running"] is True
    assert widget._workflowActionBusy is True
    assert widget._advisorState["cancelButton"].enabled is False
    assert dialog.shown and dialog.raised
    assert "restoration will be attempted" in widget._advisorState["statusLabel"].text


def test_unexpected_tick_error_requests_one_bounded_restore_and_drives_one_step_per_tick():
    class Session:
        finished = False

        def __init__(self):
            self.step_calls = 0
            self.cancelled = 0

        def step(self):
            self.step_calls += 1
            if self.step_calls == 1:
                raise RuntimeError("tick failure")
            self.finished = True
            return SimpleNamespace(kind="done", stage="", event=None)

        def cancel(self):
            self.cancelled += 1

    class RecoveryWidget(GuiMixin):
        def __init__(self, session):
            self._workflowActionBusy = True
            self.timer = Timer()
            self.finished = 0
            self._advisorState = {
                "running": True, "session": session, "timer": self.timer,
                "statusLabel": SimpleNamespace(text=""), "fixButtons": [],
                **_buttons(),
            }

        def _advisorShowProgress(self, event):
            return None

        def _advisorFinish(self):
            self.finished += 1
            self._advisorState["running"] = False
            self._workflowActionBusy = False

    session = Session()
    widget = RecoveryWidget(session)
    widget._advisorTick()
    assert session.cancelled == 1
    assert widget._advisorState["running"] is True
    assert widget._advisorState["errorRecovery"]["remaining"] == len(
        GuiMixin.__dict__.get("APPLY_STEPS", ("apply_base", "apply_policy"))
    ) + 2
    assert widget.timer.starts == 1
    widget._advisorTick()
    assert session.step_calls == 2
    assert widget.finished == 1
    assert widget.timer.starts == 1


def test_gui_source_names_temporary_trials_and_never_calls_planner_preview_or_home_acceptance():
    source = GUI_PATH.read_text(encoding="utf-8")
    assert "temporarily changes the live simulation configuration" in source
    assert "attempts to restore the starting configuration" in source
    assert "evaluated only when the baseline's own contact evidence names the lip slab" in source
    assert "otherwise they stay UNTESTED" in source
    assert "never moves the robot or uses different joints" in source
    assert "unless you tick the Task Home consent" in source
    tree = ast.parse(source)
    forbidden_calls = {
        "planApproachPhase", "planDrillingPhase", "previewApproach", "previewDrilling",
        "acceptManualTaskHomeReview", "acceptTaskHomeReview", "confirmTask", "applyTaskHome",
    }
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert calls.isdisjoint(forbidden_calls)


def test_advisor_button_owner_callback_and_mixin_installation_remain_wired():
    panel = (PY / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    shell = (PY / "dentobot_workflow" / "widget_robot_shell.py").read_text(encoding="utf-8")
    robot = (PY / "dentobot_workflow" / "widget_robot.py").read_text(encoding="utf-8")
    cmake = (ROOT / "DENTOWorkflow" / "CMakeLists.txt").read_text(encoding="utf-8")
    structure = (ROOT / "Testing" / "test_modular_structure.py").read_text(encoding="utf-8")
    assert '"find_working_config": 3' in panel
    assert '"DENTOBOTStep6FindWorkingConfigButton"' in panel
    assert "Each trial temporarily changes the live simulation configuration" in panel
    assert "attempts to restore the starting configuration" in panel
    assert "own contact evidence names the lip slab" in panel
    assert "otherwise they stay UNTESTED" in panel
    assert "nothing is applied or saved" not in panel
    assert '"find_working_config": self._onStep6FindWorkingConfig' in shell
    assert "Step6AdvisorWidgetMixin" in robot and "Step6AdvisorWidgetMixin" in structure
    assert "widget_step6_advisor.py" in cmake
