"""The mouth-opening spin commits the spin's gap, not the node's old gap (S6-MULTI-JAW-STALE-01).

Live finding (evidence: S6-MULTI-JAW-STALE-01-20261009T164748Z, OPEN-FDI34 attempt): one real XTest press on the
opening spin's up arrow reached the spin (the Base left ProvisionalLocked for Stale, which only the opening commit
does), but the spin then read 40.0 again and the value stayed 40.0.

The handler ``onStep6CaseJawTargetGapChanged`` previews the spin's value, then calls
``commitCaseFoundationOpeningPreview``. The commit re-solves from ``parameterNode.step6CaseJawTargetGapMm``
(logic_case_foundation.py), so when the node still held the old gap, the commit stored the old gap and invalidated
Step 6 (Base Stale and unlocked, _invalidateCaseFoundationPoseDependents). The fix writes the spin's gap into the
node before the commit.

The handler is extracted from widget_robot_scene.py. The logic fake mirrors the production read of the node gap in
commitCaseFoundationOpeningPreview; nothing else is faked for the handler.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "DENTOWorkflow" / "Resources" / "Python" / "dentobot_workflow" / "widget_robot_scene.py"


def _load_handler():
    tree = ast.parse(SCENE.read_text(encoding="utf-8"))
    owner = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(item, ast.FunctionDef) and item.name == "onStep6CaseJawTargetGapChanged" for item in node.body)
    )
    node = next(item for item in owner.body if isinstance(item, ast.FunctionDef)
                and item.name == "onStep6CaseJawTargetGapChanged")
    node.decorator_list = []
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(SCENE), "exec"), namespace)
    return namespace["onStep6CaseJawTargetGapChanged"]


HANDLER = _load_handler()
TRANSFORM = object()  # a stand-in for the opening transform node


class FakeLogic:
    """Production-shaped opening owners. The commit reads the node's gap, as commitCaseFoundationOpeningPreview does."""

    def __init__(self, node):
        self.node = node
        self.previews = []
        self.commits = []
        self.base_stale = False

    def isStep6CaseJawTransformNode(self, node):
        return node is TRANSFORM

    def previewCaseFoundationOpening(self, parameter_node, target_gap_mm):
        self.previews.append(float(target_gap_mm))
        self.node.caseFoundationPreviewUncommitted = True
        return {"gapMm": float(target_gap_mm)}

    def commitCaseFoundationOpeningPreview(self, parameter_node):
        if not parameter_node.caseFoundationPreviewUncommitted:
            return {}
        gap = float(parameter_node.step6CaseJawTargetGapMm)  # production reads the node here
        self.previews.append(gap)
        self.commits.append(gap)
        self.base_stale = True  # _invalidateCaseFoundationPoseDependents(openingOnly=True)
        self.node.caseFoundationPreviewUncommitted = False
        return {"gap": gap}


class FakeWidget:
    def __init__(self, node_gap, *, transform=True):
        self._updatingFromParameterNode = False
        self._updatingRobotPlacementUI = False
        self._parameterNode = SimpleNamespace(
            step6CaseJawTransform=TRANSFORM if transform else None,
            step6CaseJawTargetGapMm=float(node_gap),
            caseFoundationPreviewUncommitted=False,
        )
        self.logic = FakeLogic(self._parameterNode)
        self.status = []
        self.controls_refreshed = 0

    def _updateStep6CaseJawOpeningStatus(self, text="", error=False):
        self.status.append((text, error))

    def _updateStep6CaseJawOpeningControls(self):
        self.controls_refreshed += 1

    def _updateStep6PlanningUi(self, message="", error=False):
        self.planning_refreshed = getattr(self, "planning_refreshed", 0) + 1

    def onStep6CaseJawTargetGapChanged(self, value=0.0):
        return HANDLER(self, value)


def test_the_commit_solves_at_the_spin_value_when_the_node_still_holds_the_old_gap():
    widget = FakeWidget(40.0)
    widget.onStep6CaseJawTargetGapChanged(41.0)  # one up-arrow step, node not yet written
    assert widget._parameterNode.step6CaseJawTargetGapMm == 41.0
    assert widget.logic.commits == [41.0]
    assert widget.logic.previews[-1] == 41.0
    assert widget.logic.base_stale is True  # a real opening change still invalidates Step 6
    assert widget.controls_refreshed == 1


def test_no_commit_happens_at_the_old_gap_on_a_real_step():
    widget = FakeWidget(40.0)
    widget.onStep6CaseJawTargetGapChanged(41.0)
    assert 40.0 not in widget.logic.commits
    assert widget.logic.commits == [41.0]


def test_when_the_node_already_holds_the_spin_value_the_behaviour_is_unchanged():
    widget = FakeWidget(44.0)
    widget.onStep6CaseJawTargetGapChanged(44.0)
    assert widget._parameterNode.step6CaseJawTargetGapMm == 44.0
    assert widget.logic.commits == [44.0]


def test_a_down_step_commits_the_lower_gap():
    widget = FakeWidget(40.0)
    widget.onStep6CaseJawTargetGapChanged(39.0)
    assert widget._parameterNode.step6CaseJawTargetGapMm == 39.0
    assert widget.logic.commits == [39.0]


def test_without_an_opening_transform_the_node_is_not_written_and_nothing_is_committed():
    widget = FakeWidget(40.0, transform=False)
    widget.onStep6CaseJawTargetGapChanged(41.0)
    assert widget._parameterNode.step6CaseJawTargetGapMm == 40.0
    assert widget.logic.commits == [] and widget.logic.previews == []
    assert widget.logic.base_stale is False


def test_a_refused_commit_is_reported_and_the_controls_still_refresh():
    widget = FakeWidget(40.0)

    def refuse(parameter_node, target_gap_mm):
        raise ValueError("opening solve refused")

    widget.logic.previewCaseFoundationOpening = refuse
    widget.onStep6CaseJawTargetGapChanged(41.0)
    assert ("opening solve refused", True) in widget.status
    assert widget.controls_refreshed == 1
