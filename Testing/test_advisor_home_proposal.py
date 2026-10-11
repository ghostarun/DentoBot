"""Pure immutable snapshots and exclusive evidence for Auto Task Home proposals."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "DENTOWorkflow" / "Resources" / "Python"
if str(PY) not in sys.path:
    sys.path.insert(0, str(PY))

from dentobot_workflow import advisor_home_proposal as proposal  # noqa: E402


def _artifact_root(tmp_path):
    return Path(os.environ.get("DENTOBOT_ADVISOR_HOME_TEST_ROOT", tmp_path))


def test_outcome_is_an_immutable_copy_of_generator_attribution():
    details = {
        "source": {"incisorFdi": ["11", "21", "31", "41"], "centerWorldRasMm": [1.0, 2.0, 3.0]},
        "positionResidualMm": 0.002,
        "guardEvidence": {"sceneMatches": True},
        "candidateJointPositionsSi": {"j1": 0.1, "j2": -0.2},
    }
    result = SimpleNamespace(
        success=True,
        code="auto_task_home_draft_ready",
        message="Draft ready.",
        details=details,
        payload={"j1": 0.1, "j2": -0.2},
    )

    outcome = proposal.outcome_from_result(result, staged=True)
    details["source"]["centerWorldRasMm"][0] = 99.0
    details["candidateJointPositionsSi"]["j1"] = 99.0

    assert outcome.status == "staged"
    assert outcome.success is True and outcome.staged is True
    assert outcome.code == result.code and outcome.message == result.message
    assert outcome.details["source"]["centerWorldRasMm"] == (1.0, 2.0, 3.0)
    assert outcome.candidate_si_joints["j1"] == 0.1
    try:
        outcome.details["source"]["new"] = "mutation"
        assert False, "details must be immutable"
    except TypeError:
        pass
    try:
        outcome.candidate_si_joints["j1"] = 5.0
        assert False, "candidate joints must be immutable"
    except TypeError:
        pass


def test_result_without_identity_does_not_gain_one():
    outcome = proposal.outcome_from_result(SimpleNamespace(
        success=False,
        code="auto_task_home_blocked",
        message="Home is blocked.",
        details={"source": {"midpointWorldRasMm": [1.0, 2.0, 3.0]}, "failureEvidence": {"guard": "refused"}},
        payload=None,
    ), staged=False)

    assert outcome.status == "refused"
    assert "source" in outcome.details and "failureEvidence" in outcome.details
    assert "identity" not in outcome.details
    assert outcome.candidate_si_joints is None


def test_stage_refusal_and_all_failure_outcomes_are_explicit():
    result = SimpleNamespace(
        success=True, code="auto_task_home_draft_ready", message="Generated.",
        details={"source": {"incisorFdi": ["11", "21", "31", "41"]}}, payload={"j1": 0.1},
    )
    refused_stage = proposal.outcome_from_result(
        result, staged=False, stage_message="Auto Task Home was not staged: controls refused the draft."
    )
    no_result = proposal.no_result_outcome()
    error = proposal.error_outcome("Generator raised ValueError.")

    assert refused_stage.status == "stage_refused"
    assert refused_stage.success is True and refused_stage.staged is False
    assert refused_stage.message == "Generated."
    assert "controls refused" in refused_stage.display_message
    assert no_result.status == "no_result" and no_result.staged is False
    assert no_result.code == "auto_task_home_no_result"
    assert error.status == "error" and error.staged is False
    assert error.code == "auto_task_home_exception"


def test_artifacts_are_safe_json_exclusive_and_draft_only(tmp_path):
    result = SimpleNamespace(
        success=True,
        code="auto_task_home_draft_ready",
        message="Draft ready.",
        details={
            "source": {"centerWorldRasMm": [1.0, 2.0, 3.0], "incisorFdi": ["11", "21", "31", "41"]},
            "positionResidualMm": 0.002,
            "guardEvidence": {"sceneMatches": True},
            "identityStatus": "current",
            "candidateJointPositionsSi": {"j1": 0.1, "j2": -0.2},
        },
        payload={"j1": 0.1, "j2": -0.2},
    )
    outcome = proposal.outcome_from_result(result, staged=True)
    root = _artifact_root(tmp_path)
    captured_at = datetime(2026, 10, 11, 15, 16, 1, tzinfo=timezone.utc)

    first = Path(proposal.write_proposal_artifact(root, outcome, captured_at=captured_at))
    second = Path(proposal.write_proposal_artifact(root, outcome, captured_at=captured_at))
    record = json.loads(first.read_text(encoding="utf-8"))

    assert first.parent == root and second.parent == root
    assert first != second and first.exists() and second.exists()
    assert record["scope"] == "draft-only; operator acceptance required"
    assert record["status"] == "staged" and record["staged"] is True
    assert record["details"]["source"]["incisorFdi"] == ["11", "21", "31", "41"]
    assert record["details"]["identityStatus"] == "current"
    assert record["candidateJointPositionsSi"]["j1"] == 0.1
    assert "accepted" not in record and "validated" not in record
    assert "identity" not in proposal.outcome_from_result(
        SimpleNamespace(success=False, code="x", message="y", details={"source": {}}), staged=False
    ).details

    summary = proposal.make_summary(outcome, artifact_path=str(first))
    displayed = proposal.format_summary(summary)
    assert "Draft only; operator acceptance is required" in displayed
    assert str(first) in displayed


def test_non_finite_diagnostic_values_remain_json_serializable():
    outcome = proposal.outcome_from_result(SimpleNamespace(
        success=False, code="diagnostic", message="no proposal",
        details={"positionResidualMm": float("nan")}, payload=None,
    ), staged=False)

    assert outcome.details["positionResidualMm"] == "[non-finite-number]"
