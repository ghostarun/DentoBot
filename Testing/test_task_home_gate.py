"""Pure host checks: 6.2 Task Home actions never grey out without a stated reason."""

from __future__ import annotations

import ast
import itertools
import random
import sys
from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))
from dentobot_workflow.task_home_gate import (  # noqa: E402
    format_blockers,
    task_home_action_blockers,
)

JOINT_NAMES = tuple(f"j{i}" for i in range(1, 6))


def _method(path: Path, class_name: str, name: str, namespace: dict):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.fix_missing_locations(ast.Module([node], [])), str(path), "exec"), namespace)
    return namespace[name]


CONTROL_STATE = _method(
    PYTHON / "dentobot_workflow/widget_robot.py",
    "RobotWidgetMixin",
    "_manualTaskHomeReviewControlState",
    {"JOINT_NAMES": JOINT_NAMES, "Mapping": Mapping, "isfinite": isfinite},
)

LABELS = {"review": "Review", "accept": "Accept", "apply": "Apply"}


def _joints(value=0.0):
    return {name: value for name in JOINT_NAMES}


def _context(**changes):
    context = dict(
        scene_prepared=True, scene_issues=(), anatomy_ready=True, anatomy_issues=(),
        robot_present=True, base_locked=True, ros2_active=True, preview_active=False,
        away_from_home=False, action_busy=False, preview_running=False,
        unresolved_jog=False, scene_synchronized=True, candidate_matches_accepted=True,
        draft_within_limits=True, draft_limit_note="", offline_edit_ready=True,
        candidate_matches_draft=True,
    )
    context.update(changes)
    return context


def _details(**changes):
    details = dict(
        setupMode="connected", staged=False, identityStatus="current",
        acceptanceStatus="review", acceptanceUncertainty="",
        acceptedJointPositionsSi=_joints(), candidateJointPositionsSi=_joints(),
    )
    details.update(changes)
    return details


def _enabled(context, details, success):
    """Mirror the widget's enable composition from the real control-state method."""

    live = bool(
        context["scene_prepared"] and context["robot_present"] and context["base_locked"]
        and context["ros2_active"] and not context["action_busy"]
        and not context["preview_running"] and not context["preview_active"]
        and not context["away_from_home"]
    )
    controls = CONTROL_STATE(None, live, SimpleNamespace(success=success, details=details))
    offline = details["setupMode"] == "offline"
    free = not context["action_busy"] and not context["unresolved_jog"]
    review = controls["review"] and free and (not offline or context["offline_edit_ready"])
    accept = controls["accept"] and free and (not offline or context["offline_edit_ready"])
    staged = details["staged"] is True
    apply = bool(
        live and context["anatomy_ready"] and (controls["review"] or (
            success and details["setupMode"] == "connected" and staged
            and details["identityStatus"] == "current"
            and details["acceptanceStatus"] == "review"
            and not details["acceptanceUncertainty"]
            and context["candidate_matches_draft"]
        ))
        and context["scene_synchronized"] and context["draft_within_limits"]
        and not context["unresolved_jog"]
    )
    # Review is hidden while staged and Accept while not; hidden actions are not judged.
    return {"review": staged or review, "accept": (not staged) or accept, "apply": apply}


def test_every_disabled_visible_action_has_a_specific_named_reason():
    bool_fields = (
        "scene_prepared", "robot_present", "base_locked", "ros2_active", "action_busy",
        "preview_running", "preview_active", "away_from_home", "unresolved_jog",
        "scene_synchronized", "anatomy_ready", "draft_within_limits",
        "candidate_matches_accepted", "offline_edit_ready", "candidate_matches_draft",
    )
    detail_variants = [
        dict(setupMode=mode, staged=staged, identityStatus=identity,
             acceptanceStatus=status, acceptanceUncertainty=uncertain)
        for mode in ("connected", "offline", "unknown")
        for staged in (False, True)
        for identity in ("current", "stale", "unknown")
        for status in ("review", "accepted", "rejected", "configuration_saved", "unknown")
        for uncertain in ("", "save outcome may have committed")
    ]
    checked = 0
    # Healthy baseline, then every single and pair of simultaneous failures, plus
    # a seeded random sample of denser combinations.
    healthy = _context()
    flips = [()]
    flips += [(f,) for f in bool_fields]
    flips += list(itertools.combinations(bool_fields, 2))
    rng = random.Random(6202)
    flips += [tuple(f for f in bool_fields if rng.random() < 0.4) for _ in range(300)]
    for flipped in flips:
        context = _context(**{f: not healthy[f] for f in flipped})
        for variant in detail_variants:
            for success in (True, False):
                details = _details(**variant)
                enabled = _enabled(context, details, success)
                blockers = task_home_action_blockers(
                    context, details, success, "façade said no", enabled
                )
                for action, is_enabled in enabled.items():
                    if is_enabled:
                        assert blockers[action] == ()
                        continue
                    assert blockers[action], (action, context, variant, success)
                    assert not blockers[action][0].startswith("Unavailable in the current state"), (
                        "an unexplained state fell through to the generic message",
                        action, context, variant, success, blockers[action],
                    )
                checked += 1
    assert checked > 10000


def test_each_prerequisite_is_named_with_where_to_fix_it():
    details = _details()
    cases = {
        "robot_present": "Load the robot in 6.1",
        "base_locked": "lock the Base in 6.1",
        "ros2_active": "Connect ROS + MoveIt in 6.1",
        "action_busy": "still running",
        "preview_active": "preview is active",
        "away_from_home": "away from Home",
        "unresolved_jog": "Reconcile in 6.3",
    }
    for field, expected in cases.items():
        context = _context(**{field: (field in {"action_busy", "preview_active", "away_from_home", "unresolved_jog"})})
        enabled = _enabled(context, details, True)
        assert enabled["review"] is False, field
        text = " ".join(task_home_action_blockers(context, details, True, "", enabled)["review"])
        assert expected in text, (field, text)
    context = _context(scene_prepared=False, scene_issues=("Base placement is stale.",))
    enabled = _enabled(context, details, True)
    assert "Base placement is stale." in " ".join(
        task_home_action_blockers(context, details, True, "", enabled)["review"]
    )


def test_unavailable_review_surfaces_facade_message_and_apply_names_limits():
    details = _details(identityStatus="unknown")
    context = _context(draft_within_limits=False, draft_limit_note="J2 exceeds reviewed maximum.")
    enabled = _enabled(context, details, False)
    blockers = task_home_action_blockers(
        context, details, False, "Planning inputs are stale: Task Home belongs to a different base pose.", enabled
    )
    assert any("different base pose" in line for line in blockers["review"])
    assert any("J2 exceeds reviewed maximum." in line for line in blockers["apply"])
    text = format_blockers(blockers, LABELS)
    assert text.startswith("Unavailable because:") and "different base pose" in text


def test_enabled_actions_report_nothing():
    details = _details()
    context = _context()
    enabled = _enabled(context, details, True)
    assert enabled == {"review": True, "accept": True, "apply": True}
    blockers = task_home_action_blockers(context, details, True, "", enabled)
    assert all(items == () for items in blockers.values())
    assert format_blockers(blockers, LABELS) == ""


def test_unmatched_state_is_reported_not_silent():
    blockers = task_home_action_blockers(
        _context(), _details(), True, "", {"review": False, "accept": True, "apply": True}
    )
    assert blockers["review"][0].startswith("Unavailable in the current state")
    assert "mode=connected" in blockers["review"][0]


def test_widget_never_greys_the_whole_home_group_and_always_explains():
    robot = (PYTHON / "dentobot_workflow/widget_robot.py").read_text(encoding="utf-8")
    manual = (PYTHON / "dentobot_workflow/widget_robot_manual.py").read_text(encoding="utf-8")
    panel = (PYTHON / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    assert "panel.homeGroup.enabled = True" in robot
    assert 'task_home_controls["group"]' not in robot
    assert "gate_context=None" in manual and "self._explainTaskHomeActionBlockers(" in manual
    assert "def setTaskHomeActionBlockers" in panel


def test_panel_blocker_display_keeps_base_status_and_tooltips():
    source = (PYTHON / "DENTORobotSimulationPanel.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and any(
        isinstance(b, ast.FunctionDef) and b.name == "setTaskHomeActionBlockers" for b in n.body))
    node = next(b for b in cls.body if isinstance(b, ast.FunctionDef) and b.name == "setTaskHomeActionBlockers")
    namespace: dict = {}
    exec(compile(ast.fix_missing_locations(ast.Module([node], [])), "panel", "exec"), namespace)

    class Button:
        def __init__(self, tip):
            self.toolTip = tip

    panel = SimpleNamespace(
        reviewTaskHomeButton=Button("review tip"), acceptTaskHomeButton=Button("accept tip"),
        applyTaskHomeButton=Button("apply tip"),
        taskHomeReviewStatusLabel=SimpleNamespace(text="Home review: review; identity: current."),
        _taskHomeStatusBase="Home review: review; identity: current.",
    )
    set_blockers = namespace["setTaskHomeActionBlockers"]
    set_blockers(panel, {"review": ("Connect ROS + MoveIt in 6.1.",), "accept": (), "apply": ()}, "Unavailable because:")
    assert "Unavailable: Connect ROS" in panel.reviewTaskHomeButton.toolTip
    assert panel.acceptTaskHomeButton.toolTip == "accept tip"
    assert panel.taskHomeReviewStatusLabel.text.endswith("Unavailable because:")
    set_blockers(panel, {"review": (), "accept": (), "apply": ()}, "")
    assert panel.reviewTaskHomeButton.toolTip == "review tip"
    assert panel.taskHomeReviewStatusLabel.text == "Home review: review; identity: current."
