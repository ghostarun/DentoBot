"""Pure snapshots and JSON evidence for advisor-triggered Auto Task Home drafts."""

from __future__ import annotations

import json
import math
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from numbers import Integral, Real
from pathlib import Path
from types import MappingProxyType
from typing import Any


_MISSING = object()


def _freeze_json_value(value: Any, depth: int = 0) -> Any:
    """Copy JSON-shaped data into immutable containers without retaining live objects."""

    if depth > 16:
        return "[depth-limited]"
    if value is None or isinstance(value, (bool, str)):
        return value[:20000] if isinstance(value, str) else value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        return number if math.isfinite(number) else "[non-finite-number]"
    if isinstance(value, Mapping):
        copied = {}
        for key, item in list(value.items())[:5000]:
            if isinstance(key, str):
                copied[key[:256]] = _freeze_json_value(item, depth + 1)
        return MappingProxyType(copied)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_json_value(item, depth + 1) for item in value[:5000])
    return f"[unsupported:{type(value).__name__}]"


def _plain_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json_value(item) for item in value]
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(value)[:20000]
    except Exception:
        return "[unprintable]"


@dataclass(frozen=True)
class ProposalOutcome:
    """Immutable record of the generator result and its separate GUI staging outcome."""

    status: str
    success: bool
    staged: bool
    code: str
    message: str
    details: Mapping[str, Any]
    candidate_si_joints: Mapping[str, Any] | None
    stage_message: str = ""

    @property
    def display_message(self) -> str:
        return self.stage_message or self.message


@dataclass(frozen=True)
class ProposalSummary:
    """Small widget-retained pointer to the most recent proposal and its evidence."""

    status: str
    success: bool
    staged: bool
    code: str
    message: str
    artifact_path: str = ""
    evidence_error: str = ""


def outcome_from_result(result: Any, *, staged: bool, stage_message: str = "") -> ProposalOutcome:
    """Copy actual result fields; never infer an identity, acceptance, or validation claim."""

    raw_details = getattr(result, "details", None)
    details = _freeze_json_value(raw_details if isinstance(raw_details, Mapping) else {})
    candidate = _MISSING
    if isinstance(raw_details, Mapping):
        candidate = raw_details.get("candidateJointPositionsSi", _MISSING)
    if candidate is _MISSING:
        candidate = getattr(result, "payload", None)
    candidate_copy = (
        _freeze_json_value(candidate) if isinstance(candidate, Mapping) else None
    )
    success = getattr(result, "success", False) is True
    if success and staged:
        status = "staged"
    elif success:
        status = "stage_refused"
        if not stage_message:
            stage_message = "Auto Task Home was not staged by the draft controls."
    elif staged:
        status = "inconsistent_result"
    else:
        status = "refused"
    return ProposalOutcome(
        status=status,
        success=success,
        staged=bool(staged),
        code=_text(getattr(result, "code", "")),
        message=_text(getattr(result, "message", "")),
        details=details,
        candidate_si_joints=candidate_copy,
        stage_message=_text(stage_message),
    )


def no_result_outcome(message: str = "Auto Task Home returned no result.") -> ProposalOutcome:
    return ProposalOutcome(
        status="no_result", success=False, staged=False, code="auto_task_home_no_result",
        message=_text(message), details=MappingProxyType({}), candidate_si_joints=None,
    )


def error_outcome(message: str, *, code: str = "auto_task_home_exception") -> ProposalOutcome:
    return ProposalOutcome(
        status="error", success=False, staged=False, code=_text(code),
        message=_text(message), details=MappingProxyType({}), candidate_si_joints=None,
    )


def make_summary(
    outcome: ProposalOutcome, *, artifact_path: str = "", evidence_error: str = ""
) -> ProposalSummary:
    return ProposalSummary(
        status=outcome.status,
        success=outcome.success,
        staged=outcome.staged,
        code=outcome.code,
        message=outcome.display_message,
        artifact_path=_text(artifact_path),
        evidence_error=_text(evidence_error),
    )


def format_summary(summary: ProposalSummary) -> str:
    labels = {
        "staged": "draft staged",
        "stage_refused": "draft staging refused",
        "refused": "proposal refused",
        "no_result": "no proposal result",
        "error": "proposal failed",
        "inconsistent_result": "proposal/staging result needs inspection",
    }
    state = labels.get(summary.status, summary.status or "unknown result")
    text = f"Previous Auto Task Home: {state}. Draft only; operator acceptance is required."
    if summary.message:
        text += " " + summary.message[:500]
    if summary.artifact_path:
        text += " Evidence: " + summary.artifact_path
    if summary.evidence_error:
        text += " Evidence could not be saved: " + summary.evidence_error[:500]
    return text


def _artifact_record(outcome: ProposalOutcome, captured_at: datetime) -> dict:
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    captured_at = captured_at.astimezone(timezone.utc)
    return {
        "schema_version": 1,
        "record_type": "advisor_auto_task_home_proposal",
        "captured_at_utc": captured_at.isoformat().replace("+00:00", "Z"),
        "scope": "draft-only; operator acceptance required",
        "status": outcome.status,
        "success": outcome.success,
        "staged": outcome.staged,
        "code": outcome.code,
        "message": outcome.message,
        "stage_message": outcome.stage_message,
        "details": _plain_json_value(outcome.details),
        "candidateJointPositionsSi": _plain_json_value(outcome.candidate_si_joints),
    }


def write_proposal_artifact(
    root: str | Path,
    outcome: ProposalOutcome,
    *,
    captured_at: datetime | None = None,
    previous_batch: Mapping | None = None,
) -> str:
    """Write a unique JSON artifact with exclusive creation; existing files are never replaced."""

    if root is None or not str(root).strip():
        raise ValueError("The advisor evidence root is unavailable.")
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = captured_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp = stamp.astimezone(timezone.utc)
    record = _artifact_record(outcome, stamp)
    if previous_batch is not None:
        record["previous_batch"] = _plain_json_value(_freeze_json_value(previous_batch))
    serialized = json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    for _ in range(8):
        token = uuid.uuid4().hex
        filename = f"S6-ADVISOR-GUI-01-auto-home-proposal-{stamp.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}-{token}.json"
        path = directory / filename
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            return str(path)
        except FileExistsError:
            continue
    raise FileExistsError("Could not allocate a unique Auto Task Home proposal artifact name.")
