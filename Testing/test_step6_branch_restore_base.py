"""Yes on "Restore branch Step 6 configuration" (S6-MULTI-JAW-STALE-01, live run 2026-10-09).

Live finding: Import + Yes was pressed before any robot was loaded. The saved Base could not be
accepted (Accept Base locks through the robot owners, which need a loaded robot), so the restore
stopped inside its Base step: the saved planning policy and the saved Task Home were never applied.

These checks run the real restore mixin method and the real DENTORobotWorkflowFacade. The fakes are
the MRML-like pieces only: a transform that copies its parent matrix on set and exposes it through
GetMatrixTransformToWorld, a parameter node with declared fields, a template node that stores the
saved record as an attribute, and the Slicer-side logic owners the restore calls. The matrix reader
and the capture method are extracted from production source, not re-implemented.
"""

import ast
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PY))

from dentobot_workflow import mouth_portal  # noqa: E402
from dentobot_workflow import step6_working_config as wc  # noqa: E402
from DENTORobotWorkflowFacade import DENTORobotWorkflowFacade  # noqa: E402

BRANCH_WIDGET = PY / "dentobot_workflow" / "widget_step6_branch_config.py"
CASE_BUNDLE = PY / "dentobot_workflow" / "logic_case_bundle.py"
ROBOT_LOGIC = PY / "dentobot_workflow" / "logic_robot.py"

BRANCH_ID = "guide-fdi11"
FOUNDATION = "foundation-fdi11"
HOME = {"link-1_Revolute-1": 0.1, "link-2_Slider-2": 0.02}
AUTHORITY = "DENTOBOT.RobotBasePlacementAuthority"


def _pose(angle_deg, origin):
    angle = math.radians(angle_deg)
    c, s = math.cos(angle), math.sin(angle)
    return [
        [c, -s, 0.0, origin[0]],
        [s, c, 0.0, origin[1]],
        [0.0, 0.0, 1.0, origin[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


# The saved FDI11 (upper) Base, and the live pose left over from the FDI34 (lower) branch.
SAVED_BASE = _pose(7.0, (-97.889, 13.212, 187.347))
FDI34_BASE = _pose(0.0, (-117.231, 34.704, 175.195))


class FakeVtkMatrix4x4:
    def __init__(self):
        self._values = [[1.0 if row == column else 0.0 for column in range(4)] for row in range(4)]

    def GetElement(self, row, column):
        return self._values[row][column]

    def SetElement(self, row, column, value):
        self._values[row][column] = float(value)


FAKE_VTK = SimpleNamespace(vtkMatrix4x4=FakeVtkMatrix4x4)


class FakeMrmlTransform:
    """Copies the parent matrix on set (as MRML does) and reads it back through the world getter."""

    def __init__(self, matrix):
        self._parent = [[float(value) for value in row] for row in matrix]
        self._attributes = {}
        self._parent_id = ""

    def SetMatrixTransformToParent(self, matrix):
        self._parent = [[float(matrix.GetElement(row, column)) for column in range(4)] for row in range(4)]

    def GetMatrixTransformToWorld(self, matrix):
        for row in range(4):
            for column in range(4):
                matrix.SetElement(row, column, self._parent[row][column])

    def SetAndObserveTransformNodeID(self, node_id):
        self._parent_id = node_id or ""

    def GetTransformNodeID(self):
        return self._parent_id

    def GetAttribute(self, name):
        return self._attributes.get(name)

    def SetAttribute(self, name, value):
        if value is None:
            self._attributes.pop(name, None)
        else:
            self._attributes[name] = str(value)


class FakeParameterNode:
    """Declared parameter-node fields only, so a misspelt field fails instead of silently appearing."""

    def __init__(self, base):
        self.inputVolume = object()
        self.teethSegmentation = object()
        self.robotBaseTransform = base
        self.robotBaseMountLocked = False
        self.step6BasePlacementStatus = "Unlocked"
        self.step6BasePlacementSource = "test"
        self.step6BasePlacementRevision = 0
        self.step6PlanningContextImported = True
        self.step6CaseJawTargetGapMm = 40.0
        self.step6AllowSpindleGuideContact = False
        self.step6TaskHomeJson = ""


class FakeTemplateNode:
    def __init__(self):
        self._attributes = {}

    def GetAttribute(self, name):
        return self._attributes.get(name)

    def SetAttribute(self, name, value):
        self._attributes[name] = str(value)


class FakeJogControl:
    def __init__(self):
        self.values = []

    def setValue(self, value):
        self.values.append(value)


class FakePanel:
    def __init__(self):
        self.manualJogJointControls = {joint: (None, FakeJogControl()) for joint in HOME}
        self.statuses = []
        self.policies = []

    def showBranchConfigStatus(self, text, state="status"):
        self.statuses.append((state, text))

    def setPlanningPolicy(self, planner_id, planning_attempts, planning_time_sec):
        self.policies.append((planner_id, planning_attempts, planning_time_sec))


def _extract_methods(path, class_name, names):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    found = [node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in found} == set(names), path
    return found


def _compile_members(path, body, namespace):
    module = ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *body],
        type_ignores=[],
    )
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace


DIALOGS = []


def _widget_mixin():
    tree = ast.parse(BRANCH_WIDGET.read_text(encoding="utf-8"))
    barrier = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == "_barrierTuningSummary")
    mixin = ast.ClassDef(
        name="Step6BranchConfigWidgetMixin",
        bases=[],
        keywords=[],
        body=_extract_methods(
            BRANCH_WIDGET,
            "Step6BranchConfigWidgetMixin",
            {"onRestoreStep6WorkingConfiguration", "_currentStep6WorkingConfiguration",
             "_step6WorkingConfigurationSummary", "_step6RobotPresentForBaseLock",
             "_offerStep6WorkingConfigurationRestore"},
        ),
        decorator_list=[],
    )
    # The Yes/No dialog text is recorded and answered No, so the dialog test never restores.
    slicer = SimpleNamespace(util=SimpleNamespace(
        confirmYesNoDisplay=lambda text, **kwargs: (DIALOGS.append(text), False)[1],
        errorDisplay=lambda *a, **k: None,
    ))
    namespace = _compile_members(
        BRANCH_WIDGET,
        [barrier, mixin],
        {
            "_": lambda value: value,
            "json": json,
            "math": math,
            "slicer": slicer,
            "step6_working_config": wc,
            "DEFAULT_BARRIER_TUNING": mouth_portal.DEFAULT_BARRIER_TUNING,
        },
    )
    return namespace["Step6BranchConfigWidgetMixin"]


# Production owners, extracted by AST and compiled against the fake VTK matrix.
WORLD_MATRIX = _compile_members(
    ROBOT_LOGIC,
    _extract_methods(ROBOT_LOGIC, "RobotLogicMixin", {"_worldMatrixFromTransform"}),
    {"vtk": FAKE_VTK},
)["_worldMatrixFromTransform"]
CAPTURE = _compile_members(
    CASE_BUNDLE,
    _extract_methods(CASE_BUNDLE, "CaseBundleLogicMixin", {"captureStep6WorkingConfiguration"}),
    {"vtk": FAKE_VTK, "step6_working_config": wc},
)["captureStep6WorkingConfiguration"]


class FakeRestoreLogic:
    """Slicer-side owners the restore calls; the matrix reader and the capture are production code."""

    ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE = AUTHORITY
    ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY = "ManualSimulationBaseUnreviewed"
    ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY = "ManualSimulationBaseReviewed"
    ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY = "QuarantinedCircularMountPlane"

    _worldMatrixFromTransform = WORLD_MATRIX
    captureStep6WorkingConfiguration = CAPTURE

    def __init__(self, template):
        self.template = template
        self.robot_models = []  # no robot loaded: the state when Yes was pressed in the live runs
        self.opening_applied = []
        self.barrier_applied = []

    def robotModelNodes(self):
        return list(self.robot_models)

    @staticmethod
    def isRos2MotionControlActive(base):
        return False

    @staticmethod
    def isRobotBaseTransformNode(base):
        return isinstance(base, FakeMrmlTransform)

    def ensureRobotBaseTransform(self, base):
        return base

    def setRobotBaseMountLocked(self, parameter_node, locked):
        parameter_node.robotBaseMountLocked = bool(locked)
        parameter_node.robotBaseTransform.SetAttribute(
            AUTHORITY,
            self.ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY if locked else self.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
        )

    @staticmethod
    def _vtkFromNumpyMatrix(matrix):
        result = FakeVtkMatrix4x4()
        for row in range(4):
            for column in range(4):
                result.SetElement(row, column, matrix[row][column])
        return result

    def robotBaseFingerprint(self, parameter_node):
        return "fp:" + json.dumps(_live_matrix(parameter_node.robotBaseTransform))

    @staticmethod
    def step6CaseJawPlacementFreshnessIssues(parameter_node):
        return []

    @staticmethod
    def step6CaseJawOpeningFreshnessIssues(parameter_node):
        return []

    def createOrUpdateStep6CaseJawOpening(self, parameter_node):
        self.opening_applied.append(float(parameter_node.step6CaseJawTargetGapMm))

    @staticmethod
    def importStep6PlanningContext(parameter_node):
        raise AssertionError("the planning context is already imported in these scenarios")

    def setStep6MouthBarrierTuning(self, parameter_node, **tuning):
        self.barrier_applied.append(tuning)

    @staticmethod
    def step6MouthBarrierTuning(parameter_node):
        return dict(mouth_portal.DEFAULT_BARRIER_TUNING)

    @staticmethod
    def taskHomeRecord(parameter_node):
        return None  # the live Task Home is not saved on this branch

    def step6WorkingConfiguration(self, parameter_node, branchId=""):
        return wc.loads(self.template.GetAttribute(wc.ATTRIBUTE))

    @staticmethod
    def evaluatePreparedBranchEligibility(parameter_node, **kwargs):
        return {
            "eligible": True,
            "reason": "VALID",
            "message": "PreparedBranch is current and verified.",
            "branch_id": BRANCH_ID,
            "branch": {"branch_foundation_fingerprint": FOUNDATION},
        }


def _live_matrix(transform):
    """The live Base read the way the production reader reads it (rounded for comparison)."""
    matrix = WORLD_MATRIX(None, transform)
    return [[round(matrix.GetElement(row, column), 9) for column in range(4)] for row in range(4)]


def _rounded(values):
    return [[round(float(value), 9) for value in row] for row in values]


Step6BranchConfigWidgetMixin = _widget_mixin()


class FakeWidget(Step6BranchConfigWidgetMixin):
    def __init__(self, parameter_node, logic, facade, panel):
        self._parameterNode = parameter_node
        self.logic = logic
        self._robotWorkflowFacade = facade
        self._robotSimulationPanel = panel
        self._updatingFromParameterNode = False
        self._step6WorkingConfigurationRestoreSucceeded = False
        self.planning_ui = []
        self.spin_guide_calls = []

    def _updateRobotPlacement(self):
        pass

    def _refreshStep6WorkingConfigurationStatus(self):
        pass

    def _updateStep6PlanningUi(self, message="", error=False):
        self.planning_ui.append((message, error))

    def _updateStep6CaseJawOpeningControls(self):
        pass

    def _onSetSpindleGuideContact(self, value):
        self.spin_guide_calls.append(value)
        self._parameterNode.step6AllowSpindleGuideContact = bool(value)


def _saved_record(planner_id, planning_time_sec, base):
    return wc.dumps({
        "branch_id": BRANCH_ID,
        "branch_foundation_fingerprint": FOUNDATION,
        "config": {
            "mouth_opening_mm": 45.9,
            "base_world_mm": base,
            "task_home_si": HOME,
            "planner_id": planner_id,
            "planning_attempts": 5,
            "planning_time_sec": planning_time_sec,
            "corridor_margin_samples": 0,
            "allow_spindle_guide_contact": False,
        },
    })


def make_case(*, live_base=FDI34_BASE, planner_id="", planning_time_sec=5.0, base=SAVED_BASE,
              robot_loaded=False, locked=False):
    template = FakeTemplateNode()
    template.SetAttribute(wc.ATTRIBUTE, _saved_record(planner_id, planning_time_sec, base))
    parameter_node = FakeParameterNode(FakeMrmlTransform(live_base))
    parameter_node.robotBaseMountLocked = locked
    logic = FakeRestoreLogic(template)
    logic.robot_models = ["robot-model"] if robot_loaded else []
    facade = DENTORobotWorkflowFacade(logic, lambda: parameter_node)
    panel = FakePanel()
    return SimpleNamespace(
        widget=FakeWidget(parameter_node, logic, facade, panel),
        parameter_node=parameter_node,
        logic=logic,
        facade=facade,
        panel=panel,
    )


def _staged_home(case):
    return {joint: control.values for joint, (_, control) in case.panel.manualJogJointControls.items()}


def test_yes_before_a_robot_is_loaded_applies_planning_and_home_and_leaves_the_base_pending():
    case = make_case(planner_id="", planning_time_sec=5.0)

    steps = case.widget.onRestoreStep6WorkingConfiguration()

    assert "base_pending" in steps and "base" not in steps
    # Nothing moved, nothing was unlocked, and no review candidate was left behind.
    assert _live_matrix(case.parameter_node.robotBaseTransform) == _rounded(FDI34_BASE)
    assert case.parameter_node.robotBaseMountLocked is False
    assert case.facade.manualBaseReview().details["staged"] is False
    # The planning policy is applied through the facade and the panel (live was 10 s; saved 5 s).
    policy = case.facade.jointPlanningPolicy()
    assert (policy["planning_attempts"], policy["planning_time_sec"]) == (5, 5.0)
    assert case.panel.policies == [(policy["planner_id"], 5, 5.0)]
    # The saved opening goes through its owner, and Task Home is staged only.
    assert case.logic.opening_applied == [45.9]
    assert _staged_home(case) == {
        "link-1_Revolute-1": [math.degrees(HOME["link-1_Revolute-1"])],
        "link-2_Slider-2": [HOME["link-2_Slider-2"] * 1000.0],
    }
    # The restore says it is partial, names the next action, and does not claim success.
    assert case.widget._step6WorkingConfigurationRestoreSucceeded is False
    _state, text = case.panel.statuses[-1]
    assert "Partly restored" in text and "NOT applied yet" in text
    assert "load the ROS robot" in text and "Restore Branch Step 6 Config again" in text
    assert "Restore stopped" not in text
    message, error = case.widget.planning_ui[-1]
    assert "NOT applied yet" in message and error is False


def test_restore_again_after_the_robot_is_loaded_applies_the_saved_base_and_locks_it_at_the_saved_pose():
    case = make_case(planner_id="", planning_time_sec=5.0)
    case.widget.onRestoreStep6WorkingConfiguration()
    case.logic.robot_models = ["robot-model"]

    steps = case.widget.onRestoreStep6WorkingConfiguration()

    assert "base" in steps and "base_pending" not in steps
    assert _live_matrix(case.parameter_node.robotBaseTransform) == _rounded(SAVED_BASE)
    assert case.parameter_node.robotBaseMountLocked is True
    assert case.facade.manualBaseReview().details["staged"] is False
    assert case.widget._step6WorkingConfigurationRestoreSucceeded is True
    _state, text = case.panel.statuses[-1]
    assert text.startswith("Restored:") and "NOT applied" not in text


def test_yes_with_a_robot_loaded_applies_base_policy_and_home_in_one_pass():
    case = make_case(planner_id="", planning_time_sec=5.0, robot_loaded=True)

    steps = case.widget.onRestoreStep6WorkingConfiguration()

    assert "base" in steps and "base_pending" not in steps
    assert _live_matrix(case.parameter_node.robotBaseTransform) == _rounded(SAVED_BASE)
    assert case.parameter_node.robotBaseMountLocked is True
    policy = case.facade.jointPlanningPolicy()
    assert (policy["planning_attempts"], policy["planning_time_sec"]) == (5, 5.0)
    assert case.logic.opening_applied == [45.9]
    assert _staged_home(case)["link-2_Slider-2"] == [HOME["link-2_Slider-2"] * 1000.0]
    assert case.widget._step6WorkingConfigurationRestoreSucceeded is True


def test_equal_unlocked_base_without_a_robot_names_accept_base_as_the_next_action():
    # The saved Base equals the live pose, so only the planning policy differs (live 10 s, saved 5 s).
    case = make_case(live_base=SAVED_BASE, planner_id="", planning_time_sec=5.0)

    steps = case.widget.onRestoreStep6WorkingConfiguration()

    assert "base_pending" in steps
    assert case.parameter_node.robotBaseMountLocked is False
    assert _live_matrix(case.parameter_node.robotBaseTransform) == _rounded(SAVED_BASE)
    assert case.facade.jointPlanningPolicy()["planning_time_sec"] == 5.0
    _state, text = case.panel.statuses[-1]
    assert "not accepted yet" in text and "press Accept Base" in text
    assert "NOT applied yet" not in text  # the Base origin already matches; only acceptance is pending
    assert case.widget._step6WorkingConfigurationRestoreSucceeded is False


def test_a_locked_base_at_another_pose_is_not_unlocked_when_no_robot_is_loaded():
    case = make_case(planner_id="", planning_time_sec=5.0, locked=True)

    steps = case.widget.onRestoreStep6WorkingConfiguration()

    assert "base_pending" in steps
    assert case.parameter_node.robotBaseMountLocked is True  # no unlock before a Base that cannot be accepted
    assert _live_matrix(case.parameter_node.robotBaseTransform) == _rounded(FDI34_BASE)
    assert case.facade.jointPlanningPolicy()["planning_time_sec"] == 5.0


def test_yes_dialog_says_the_base_waits_for_the_robot_only_when_no_robot_is_loaded():
    for robot_loaded, expect_note in ((False, True), (True, False)):
        case = make_case(planner_id="", planning_time_sec=5.0, robot_loaded=robot_loaded)
        DIALOGS.clear()

        case.widget._offerStep6WorkingConfigurationRestore()

        assert len(DIALOGS) == 1
        assert "Restore it now? The saved Task Home is only staged; nothing moves." in DIALOGS[0]
        assert ("stays pending until you load it" in DIALOGS[0]) is expect_note
        assert case.parameter_node.robotBaseMountLocked is False  # answered No: nothing applied
        assert case.logic.opening_applied == []
