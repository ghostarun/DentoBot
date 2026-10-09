"""Step 6 Feasibility Advisor GUI lifecycle and safety wiring checks."""

import ast
import re
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "DENTOWorkflow" / "Resources" / "Python"
GUI_PATH = PY / "dentobot_workflow" / "widget_step6_advisor.py"
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))
from dentobot_workflow.step6_control_reasons import ADVISOR_CONTROLS, annotate_step6_controls  # noqa: E402
ADVISOR_HOME_PATH = PY / "dentobot_workflow" / "advisor_home.py"

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
    "_advisorEnterPause",
    "_advisorOnContinue",
    "_advisorFinish",
    "_advisorShowSetup",
    "_advisorExplainControls",
}


def _literal_assignment(path, name):
    """Value of a module-level ``name = <literal>`` read from source, so the test never imports the module."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
    return ast.literal_eval(node.value)


CONSENT_TEXT = _literal_assignment(ADVISOR_HOME_PATH, "CONSENT_TEXT")


def _load_gui_methods():
    tree = ast.parse(GUI_PATH.read_text(encoding="utf-8"))
    source_class = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                        and node.name == "Step6AdvisorWidgetMixin")
    body = [node for node in source_class.body if (isinstance(node, ast.FunctionDef) and node.name in METHODS)
            or (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_ADVISOR_KIND_TEXT"
                                                     for t in node.targets))]
    assert {node.name for node in body if isinstance(node, ast.FunctionDef)} == METHODS

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
                return next(button for button in self.buttons if button.text == "Apply && Save")
            return None

    class FakePushButton:
        def __init__(self, text="", parent=None):
            self.text = text
            self.enabled = True
            self.clicked = SimpleNamespace(connect=lambda handler: None)

    class FakeQTimer:
        def __init__(self):
            self.single_shot = False
            self.interval = 0
            self.starts = 0
            self.timeout = SimpleNamespace(connect=lambda handler: setattr(self, "handler", handler))

        def setSingleShot(self, value):
            self.single_shot = value

        def setInterval(self, value):
            self.interval = value

        def start(self):
            self.starts += 1

    namespace = {
        "_": lambda text: text,
        "ADVISOR_CONTROLS": ADVISOR_CONTROLS,
        "annotate_step6_controls": annotate_step6_controls,
        "advisor": SimpleNamespace(
            APPLY_STEPS=("apply_base", "apply_policy"),
            DONE="done", EVALUATING="evaluating", FOUND="found", IDLE="idle", RESTORING="restoring",
            working_configuration_record=lambda *args, **kwargs: {"config": "fake"},
        ),
        "advisor_home": SimpleNamespace(CONSENT_TEXT=CONSENT_TEXT),
        "step6_working_config": SimpleNamespace(normalize=lambda value: value),
        "qt": SimpleNamespace(QMessageBox=FakeMessageBox, QTimer=FakeQTimer,
                              QTableWidgetItem=lambda text: SimpleNamespace(text=text), QPushButton=FakePushButton),
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
        self.visible = True

    def setVisible(self, value):
        self.visible = value


class CheckBox:
    def __init__(self, checked):
        self.checked = checked
        self.enabled = True


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


# ---- Step 6.3 consent, pause, Continue and Cancel wiring (S6-ADVISOR-GUI-01) -------------------


def _advisor_buttons():
    return {**_buttons(), "pauseConnectButton": Button(), "continueButton": Button()}


class ScriptedSession:
    """The slice of advisor_service.FeasibilityAdvisorSession that the dialog touches, scripted per test."""

    def __init__(self, *, finished=False, step_events=(), resume_events=(), cancel_error=None):
        self.phase = "idle"
        self.finished = finished
        self.outcome = "found"
        self.message = "search message"
        self.baseline = {"opening": 42.0}
        self.restore_issues = []
        self.calls = []
        self.consent_texts = []
        self.step_events = list(step_events)
        self.resume_events = list(resume_events)
        self.cancel_error = cancel_error

    def grant_home_revalidation_consent(self, text):
        self.calls.append("grant")
        self.consent_texts.append(text)

    def prepare(self):
        self.calls.append("prepare")
        return []

    def step(self):
        self.calls.append("step")
        return self.step_events.pop(0)

    def resume(self):
        self.calls.append("resume")
        return self.resume_events.pop(0)

    def cancel(self):
        self.calls.append("cancel")
        if self.cancel_error is not None:
            raise self.cancel_error

    def best_candidate(self):
        return None

    def ranked(self):
        return []


class AdvisorHost(GuiMixin):
    """Fake Step 6.3 host: the extracted dialog methods run unchanged over scripted widgets and session."""

    def __init__(self, session, *, mode="idle", consent=None):
        self.calls = []
        self._workflowActionBusy = mode == "running"
        self._robotSimulationPanel = None
        self._robotWorkflowFacade = SimpleNamespace(jointPlanningPolicy=lambda: {
            "planner_id": "fake", "planning_attempts": 1, "planning_time_sec": 1.0,
        })
        self._advisorState = {
            **_advisor_buttons(), "session": session, "timer": Timer(), "dialog": Dialog(),
            "running": mode == "running", "paused": mode == "paused", "restoreFailed": False,
            "configurationApplied": False, "fixButtons": [],
            "statusLabel": SimpleNamespace(text=""), "stagedLabel": SimpleNamespace(text=""),
        }
        if consent is not None:
            self._advisorState["consentBox"] = CheckBox(consent)
        self._advisorSetButtons(mode)

    # Qt helpers and production owners that these tests do not model.
    def _advisorShowSetup(self, issues=None):
        return None

    def _advisorFillResults(self):
        return None

    def _updateRobotPlacement(self):
        return None

    def _updateStep6PlanningUi(self, message="", error=False):
        return None

    def _refreshShellRobotCapabilities(self):
        return None

    def _onShellConnectRobot(self):
        self.calls.append(("connect", self._advisorState["dialog"].hidden))

    def _onShellDisconnectRobot(self):
        self.calls.append("disconnect")

    def _onShellSyncCollisionScene(self):
        self.calls.append("sync_scene")

    def _configureRobotSimulationShellSubstep(self, substep):
        self.calls.append(("substep", substep))


def _snapshot(widget):
    """Every GUI field except the status label text, so a test can prove that only the text changed."""
    view = {"_workflowActionBusy": widget._workflowActionBusy}
    for key, value in widget._advisorState.items():
        if key != "statusLabel":
            plain = isinstance(value, (Button, CheckBox, Dialog, Timer, SimpleNamespace))
            view[key] = vars(value).copy() if plain else value
    return view


def _dialog_build_source():
    tree = ast.parse(GUI_PATH.read_text(encoding="utf-8"))
    source_class = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                        and node.name == "Step6AdvisorWidgetMixin")
    return next(node for node in source_class.body if isinstance(node, ast.FunctionDef)
                and node.name == "_advisorBuildDialog")


def test_start_without_a_checked_consent_box_never_grants_and_still_prepares():
    for consent in (None, False):  # no checkbox at all, or the default unchecked box
        session = ScriptedSession()
        widget = AdvisorHost(session, consent=consent)
        widget._advisorOnStart()
        assert session.consent_texts == [], consent
        assert session.calls == ["prepare"], consent


def test_start_with_a_checked_consent_box_grants_the_exact_text_once_before_prepare():
    session = ScriptedSession()
    AdvisorHost(session, consent=True)._advisorOnStart()
    assert session.consent_texts == [CONSENT_TEXT]
    assert session.calls == ["grant", "prepare"]


def test_dialog_source_builds_an_unchecked_consent_box_whose_label_carries_the_exact_text():
    build = _dialog_build_source()
    statements = {ast.unparse(node) for node in ast.walk(build) if isinstance(node, ast.Assign)}
    assert "state['consentBox'].checked = False" in statements
    assert "state['consentBox'].objectName = 'DENTOBOTStep6AdvisorHomeConsentCheckBox'" in statements
    label = next(node.value for node in ast.walk(build) if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == "consentLabel" for target in node.targets))
    label_namespace = {"__builtins__": {}, "_": lambda text: text,
                       "advisor_home": SimpleNamespace(CONSENT_TEXT=CONSENT_TEXT)}
    label_text = eval(compile(ast.Expression(body=label.args[0]), "consentLabel", "eval"), label_namespace)
    assert CONSENT_TEXT in label_text
    assert "preserves a VALID branch" in label_text and "branch review instead" in label_text


def test_consent_box_can_be_ticked_only_before_a_search_starts_or_before_keep_searching():
    enabled = {mode: AdvisorHost(ScriptedSession(), mode=mode, consent=False)._advisorState["consentBox"].enabled
               for mode in ("idle", "running", "paused", "done")}
    assert enabled == {"idle": True, "running": False, "paused": False, "done": True}  # "done" = before Keep searching


def test_a_start_blocked_at_setup_resets_the_consent_box_too():
    session = ScriptedSession(finished=True)
    widget = AdvisorHost(session, consent=True)
    widget._advisorOnStart()
    assert session.calls == ["grant", "prepare"]
    assert widget._advisorState["consentBox"].checked is False  # consent is per search, also when setup blocked it
    assert widget._advisorState["statusLabel"].text == session.message


def test_continue_that_raises_keeps_the_search_paused_and_unchanged():
    widget = AdvisorHost(ScriptedSession(resume_events=[]), mode="paused")  # resume() raises IndexError
    before = _snapshot(widget)
    widget._advisorOnContinue()
    assert "Continue could not be evaluated" in widget._advisorState["statusLabel"].text
    assert "stays paused" in widget._advisorState["statusLabel"].text
    assert _snapshot(widget) == before and widget._advisorState["timer"].starts == 0


def test_the_paused_label_is_cleared_when_the_search_resumes_or_is_cancelled_from_the_pause():
    resumed = SimpleNamespace(kind="step", message="Resumed.")
    for action in ("continue", "cancel"):
        widget = AdvisorHost(ScriptedSession(resume_events=[resumed]), mode="paused")
        widget._advisorState["stagedLabel"].text = "Paused for your action: nothing continues until you press Continue"
        (widget._advisorOnContinue if action == "continue" else widget._advisorOnCancel)()
        assert widget._advisorState["stagedLabel"].text == "No candidate is staged.", action


def test_finish_resets_the_consent_box_to_unchecked():
    widget = AdvisorHost(ScriptedSession(finished=True), mode="running", consent=True)
    widget._advisorFinish()
    assert widget._advisorState["consentBox"].checked is False


def test_restore_unconfirmed_resets_the_consent_box_to_unchecked():
    widget = AdvisorHost(ScriptedSession(), mode="running", consent=True)
    widget._advisorReportRestoreUnconfirmed("Baseline restoration is not confirmed.")
    assert widget._advisorState["consentBox"].checked is False
    assert widget._advisorState["restoreFailed"] is True


def test_tick_on_a_pause_event_enters_pause_and_does_not_restart_the_timer():
    pause = SimpleNamespace(kind="pause", message="Connect ROS + MoveIt (6.1), then press Continue.", stage="base")
    widget = AdvisorHost(ScriptedSession(step_events=[pause]), mode="running")
    widget._advisorTick()
    state = widget._advisorState
    assert state["paused"] is True
    assert state["running"] is False
    assert widget._workflowActionBusy is False
    assert state["timer"].starts == 0
    assert state["statusLabel"].text == pause.message
    for key in ("pauseConnectButton", "continueButton"):
        assert state[key].visible is True and state[key].enabled is True, key
    assert state["cancelButton"].enabled is True
    assert state["startButton"].enabled is False
    assert state["closeButton"].enabled is False


def test_refused_continue_keeps_the_pause_and_changes_only_the_status_text():
    refusal = SimpleNamespace(kind="pause", message="Continue refused: ROS/MoveIt is still disconnected.")
    session = ScriptedSession(resume_events=[refusal])
    widget = AdvisorHost(session, mode="paused", consent=True)
    before = _snapshot(widget)
    widget._advisorOnContinue()
    assert session.calls == ["resume"]
    assert widget._advisorState["statusLabel"].text == refusal.message
    assert _snapshot(widget) == before


def test_accepted_continue_restarts_the_timer_and_marks_the_search_running():
    resumed = SimpleNamespace(kind="step", message="Resumed after the operator's Connect.")
    widget = AdvisorHost(ScriptedSession(resume_events=[resumed]), mode="paused")
    widget._advisorOnContinue()
    state = widget._advisorState
    assert state["paused"] is False
    assert state["running"] is True
    assert widget._workflowActionBusy is True
    assert state["timer"].starts == 1
    assert state["statusLabel"].text == resumed.message
    assert state["cancelButton"].enabled is True
    assert state["continueButton"].visible is False


def test_cancel_while_paused_cancels_once_restarts_the_timer_and_disables_cancel():
    session = ScriptedSession()
    widget = AdvisorHost(session, mode="paused")
    widget._advisorOnCancel()
    widget._advisorOnCancel()  # a repeated press must not cancel or restart the search again
    state = widget._advisorState
    assert session.calls == ["cancel"]
    assert state["paused"] is False
    assert state["running"] is True
    assert widget._workflowActionBusy is True
    assert state["timer"].starts == 1
    assert state["cancelButton"].enabled is False


def test_close_and_window_reject_while_paused_cancel_and_keep_the_dialog_open():
    for close in ("_advisorOnClose", "_advisorOnRejected"):
        session = ScriptedSession()
        widget = AdvisorHost(session, mode="paused")
        state = widget._advisorState
        getattr(widget, close)()
        assert session.calls == ["cancel"], close
        assert widget._advisorState is state, close
        assert state["dialog"].hidden is False and state["dialog"].deleted is False, close
        assert state["dialog"].shown is True and state["dialog"].raised is True, close
        assert state["timer"].starts == 1, close


def test_paused_close_with_a_failed_cancel_still_keeps_the_dialog_open():
    session = ScriptedSession(cancel_error=RuntimeError("cancel refused"))
    widget = AdvisorHost(session, mode="paused")
    state = widget._advisorState
    widget._advisorOnClose()
    assert widget._advisorState is state
    assert state["dialog"].deleted is False
    assert state["restoreFailed"] is True
    assert "cancel refused" in state["statusLabel"].text


def test_paused_search_refuses_navigation_and_other_fixes_but_not_connect():
    for fix in ("goto_6_1", "goto_6_2", "goto_6_3", "disconnect", "sync_scene"):
        session = ScriptedSession()
        widget = AdvisorHost(session, mode="paused")
        state = widget._advisorState
        widget._advisorOnFix(fix)
        assert widget.calls == [], fix
        assert widget._advisorState is state, fix
        assert state["dialog"].hidden is False and state["dialog"].deleted is False, fix
        assert session.calls == [], fix
        assert state["paused"] is True, fix


def test_paused_connect_runs_with_the_dialog_released_and_keeps_the_pause():
    widget = AdvisorHost(ScriptedSession(), mode="paused")
    state = widget._advisorState
    widget._advisorOnFix("connect")
    assert widget.calls == [("connect", True)]  # the modal dialog is released while the Connect owner runs
    assert widget._advisorState is state
    assert state["dialog"].shown is True
    assert state["paused"] is True
    assert state["pauseConnectButton"].visible is True and state["continueButton"].enabled is True


def test_connect_and_continue_are_visible_and_enabled_only_while_paused():
    for mode in ("idle", "running", "done", "paused"):
        state = AdvisorHost(ScriptedSession(), mode=mode)._advisorState
        for key in ("pauseConnectButton", "continueButton"):
            assert state[key].visible is (mode == "paused"), (mode, key)
            assert state[key].enabled is (mode == "paused"), (mode, key)


def test_close_is_disabled_while_a_search_runs_or_is_paused():
    for mode in ("running", "paused"):
        state = AdvisorHost(ScriptedSession(), mode=mode)._advisorState
        assert state["closeButton"].enabled is False, mode
    assert AdvisorHost(ScriptedSession(), mode="idle")._advisorState["closeButton"].enabled is True


class RefusingSession(ApplySession):
    def apply_and_save(self, **kwargs):
        raise PermissionError("Apply & Save refused because the original input identity is not current: "
                              "safe input identity unavailable")


def test_refused_apply_and_save_is_shown_in_the_dialog_and_on_the_branch_status():
    widget = ApplyWidget(True)
    widget._advisorState["session"] = RefusingSession()
    widget._advisorOnApplyAndSave()
    state = widget._advisorState
    assert state["statusLabel"].text.startswith("Not saved (refused): ")
    assert "Apply && Save refused" in state["statusLabel"].text  # escaped: a lone & is a Qt mnemonic marker
    assert widget._robotSimulationPanel.errors[-1] == (state["statusLabel"].text, "error")
    assert state["configurationApplied"] is False and state["restoreFailed"] is False


def test_advisor_ui_strings_escape_the_qt_mnemonic_ampersand():
    tree = ast.parse(GUI_PATH.read_text(encoding="utf-8"))
    skipped = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body and isinstance(node.body[0], ast.Expr):
            skipped.add(id(node.body[0].value))  # docstrings are not widget text
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setWindowTitle":
            skipped.update(id(child) for child in ast.walk(node))  # window titles take no mnemonic
    lone = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in skipped and len(node.value) > 3 and re.search(r"(?<!&)&(?!&)", node.value)]
    assert not lone, lone
    assert '_("Apply && Save to branch")' in GUI_PATH.read_text(encoding="utf-8")
    panel = (PY / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    assert "Apply && Save retains" in panel and "Apply & Save retains" not in panel  # 6.3 button tooltip


class FakeSetupTable:
    def __init__(self):
        self.rows = 0
        self.items = {}
        self.widgets = {}

    def setRowCount(self, value):
        self.rows = value
        self.items.clear()
        self.widgets.clear()

    def insertRow(self, row):
        self.rows += 1

    def setItem(self, row, column, item):
        self.items[(row, column)] = item

    def setCellWidget(self, row, column, widget):
        self.widgets[(row, column)] = widget

    def resizeRowsToContents(self):
        self.resized = True


class SetupWidget(GuiMixin):
    def __init__(self):
        self._workflowActionBusy = False
        self._advisorState = {"setupTable": FakeSetupTable(), "running": False, "fixButtons": []}


def test_setup_kind_column_states_what_each_row_blocks():
    rows = [
        SimpleNamespace(message="ROS/MoveIt is not connected.", severity="blocking", blocks="all",
                        fix_id="connect", fix_label="Connect"),
        SimpleNamespace(message="stale task confirmation: Confirm the task", severity="advisory",
                        blocks="consent_apply", fix_id="goto_6_3", fix_label="Confirm"),
        SimpleNamespace(message="MoveIt scene does not match Slicer (not checked): ", severity="advisory",
                        blocks="auto", fix_id="sync_scene", fix_label="Sync"),
        SimpleNamespace(message="collision audit: stale", severity="advisory", blocks="passes", fix_id="",
                        fix_label=""),
    ]
    widget = SetupWidget()
    widget._advisorShowSetup(rows)
    table = widget._advisorState["setupTable"]
    kinds = [table.items[(row, 1)].text for row in range(len(rows))]
    assert kinds == [
        "Blocks all: Start (with or without consent) and Apply",
        "Blocks consent search and Apply (Start without consent still runs)",
        "Search fixes this automatically (checked for each candidate)",
        "Blocks every candidate until fixed (the search cannot fix it)",
    ]
    assert "the search applies this" not in kinds and "blocks the search" not in kinds


def test_setup_kind_column_is_wide_enough_and_wraps_in_the_dialog_source():
    source = ast.get_source_segment(GUI_PATH.read_text(encoding="utf-8"), _dialog_build_source())
    assert "setColumnWidth(1, 300)" in source and "wordWrap = True" in source


def test_advisor_explainer_names_each_disabled_control_and_logs_nothing(caplog):
    import logging

    widget = SetupWidget()
    names = ("startButton", "cancelButton", "consentBox", "pauseConnectButton", "continueButton",
             "moreButton", "applyButton", "exportButton", "closeButton")
    buttons = {name: SimpleNamespace(enabled=False, toolTip="") for name in names}
    fix = SimpleNamespace(enabled=False, toolTip="")
    widget._advisorState.update(buttons, fixButtons=[fix], mode="running", running=True, cancelRequested=True)
    with caplog.at_level(logging.ERROR):
        widget._advisorExplainControls()
    assert buttons["startButton"].toolTip.startswith("Unavailable:")
    assert "already running" in buttons["startButton"].toolTip
    assert "Cancellation is already requested" in buttons["cancelButton"].toolTip
    assert fix.toolTip.endswith("Setup fixes wait until the running or paused search ends.")
    assert "skipped" not in caplog.text
