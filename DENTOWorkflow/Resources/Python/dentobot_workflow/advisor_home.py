"""Consent-gated Task Home revalidation for the advisor (S6-ADVISOR-GUI-01, decision D1 option O4).

Tarun approved ("do it", 2026-10-08) that an explicit-consent SIMULATION search may re-validate the
unchanged saved Task Home joints under each trial configuration through the existing production
owners, creating new Home validation revisions. Nothing else changes:

* only ``stageManualTaskHomeReview(saved joints)`` + ``acceptManualTaskHomeReview()`` create authority
  (the production accept path itself requires accepted == monitored == displayed == candidate within
  1e-12 and applies the strict collision guard); this module never writes a Home record, a validation
  flag or a cached key, never jogs, never submits different joints and never connects;
* a guard rejection fails the candidate (``HomeRevalidationRejected``); a state/identity/ownership
  problem or an unknown outcome stops for the operator (``HomeRevalidationRefused``);
* every attempt is recorded in a ledger (revisions, timestamps, outcome) written to the evidence root.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from pathlib import Path

JOINT_TOLERANCE_SI = 1.0e-12  # the production Task Home accept path's own equality test
CONSENT_GATE = "home_revalidation"
CONSENT_TEXT = (
    "I allow this search, in SIMULATION ONLY, to re-validate my saved Task Home joint values (no joint is moved "
    "and no different joints are used) under each trial configuration, creating new Task Home validation "
    "revisions, and to re-validate the same original joint values again when the search ends or is cancelled. "
    "The collision guards still apply to every validation, and clinically sensitive stages still need their own review."
)
MAX_CONSECUTIVE_REJECTIONS = 5  # a repeatedly rejected Home is a setup problem, not a search result
# The only production owner code that is the collision guard's verdict on the unchanged joints. Every other refusal of
# acceptManualTaskHomeReview (outstanding jog, state unavailable/invalid, monitor mismatch, runtime/scene missing,
# unknown outcome) is a state/ownership problem: it stops for the operator and is never counted as a rejection.
GUARD_REJECTION_CODE = "task_home_collision_rejected"


class HomeRevalidationRefused(RuntimeError):
    """State, identity, ownership or an unknown outcome: stop for the operator; no authority was created."""


class HomeRevalidationRejected(RuntimeError):
    """The production guard rejected the unchanged joints under this configuration: the candidate fails."""


def consent_digest(text: str = CONSENT_TEXT) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def record_identity(record) -> dict:
    """Stable mapping of a Task Home record (fields the production record carries)."""

    if record is None:
        return {}
    to_dict = getattr(record, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        return dict(value) if isinstance(value, Mapping) else {}
    fields = (
        "joint_names", "joint_positions_si", "base_fingerprint", "robot_profile_fingerprint",
        "revision", "runtime_validation_status", "collision_audit_fingerprint", "guard_policy_fingerprint",
        "validated_at_utc", "minimum_clearance_mm", "world_object_count",
    )
    return {name: getattr(record, name) for name in fields if hasattr(record, name)}


def record_summary(record) -> dict:
    if record is None:
        return {"revision": None, "status": "", "validated_at_utc": "", "base_fingerprint": "", "audit": ""}
    return {
        "revision": getattr(record, "revision", None),
        "status": str(getattr(record, "runtime_validation_status", "") or ""),
        "validated_at_utc": str(getattr(record, "validated_at_utc", "") or ""),
        "base_fingerprint": str(getattr(record, "base_fingerprint", "") or ""),
        "audit": str(getattr(record, "collision_audit_fingerprint", "") or ""),
    }


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def stable_identity(identity: Mapping, saved_joints: Mapping, *, source_only: bool = False) -> dict:
    """The input identity without revision-bound authority (Home record, confirmed task, audit base binding).

    Authority is re-established by the production owners and ledgered; geometry/source identity must be equal.
    ``source_only`` also drops the audited scene (it is stale between an opening change and Connect).
    """

    stable = {k: v for k, v in identity.items() if k not in ("saved_home", "confirmed_task_fingerprint")}
    stable["saved_home_joints"] = {k: round(float(v), 9) for k, v in sorted((saved_joints or {}).items())}
    scene = dict(stable.get("audited_scene_sources") or {})
    stable["audited_scene_sources"] = {k: scene.get(k) for k in ("objects", "jaw_preparation_fingerprint",
                                                                  "world_to_base_fingerprint", "runtime_acknowledgement_status")}
    if source_only:
        stable.pop("audited_scene_sources", None)
        stable.pop("collision_audit_status", None)
    return stable


class OperatorPause:
    """A search paused for an operator action (Connect after an opening change): frozen identity + audit file."""

    def __init__(self, root):
        self.root = Path(root)
        self.info: dict | None = None

    def _log(self, update: dict) -> None:
        path = self.root / "pause.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.root.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**data, **update}, indent=1, default=str), encoding="utf-8")

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def enter(self, *, candidate: int, stage: str, step: str, message: str, frozen: Mapping) -> None:
        self.info = {"reason": "connect", "candidate": candidate, "stage": stage, "step": step, "frozen": dict(frozen)}
        self._log({"paused_at": self._now(), "candidate": candidate, "step": step, "message": message,
                   "frozen_identity_fingerprint": _fingerprint(frozen)})

    def drift(self, now: Mapping) -> list:
        frozen = (self.info or {}).get("frozen", {})
        return sorted(k for k in set(now) | set(frozen) if now.get(k) != frozen.get(k))

    def refused(self, message: str) -> None:
        self._log({"last_refusal": message, "refused_utc": self._now()})

    def resumed(self) -> None:
        self._log({"resumed_utc": self._now()})
        self.info = None


class HomeRevalidator:
    """One session's production Home revalidations and their attributed ledger."""

    def __init__(self, logic, facade, node, saved_joints: Mapping, root):
        self.logic, self.facade, self.node = logic, facade, node
        self.saved = {str(k): float(v) for k, v in saved_joints.items()}
        self.root = Path(root)
        self.ledger: list = []
        self.consecutive_rejections = 0
        self.expected_identity: dict = record_identity(logic.taskHomeRecord(node))

    # ---- identity ---------------------------------------------------------------------------
    def joint_issues(self) -> list:
        """Why accepted / monitored / displayed J1–J5 are not exactly the saved Home joints ([] when equal)."""

        reader = getattr(self.facade, "taskHomeJointIdentity", None)
        if not callable(reader):
            return ["the accepted/monitored/displayed joint identity cannot be read"]
        try:
            identity = reader()
        except Exception as exc:  # recorded, never hidden
            return [f"the accepted/monitored/displayed joint identity could not be read: {exc}"[:240]]
        if identity is not None and not isinstance(identity, Mapping):
            return ["the accepted/monitored/displayed joint identity is malformed"]
        issues = []
        for source in ("accepted", "monitored", "displayed"):
            vector = (identity or {}).get(source)
            if not isinstance(vector, Mapping) or set(vector) != set(self.saved):
                issues.append(f"{source} J1–J5 are unavailable")
                continue
            try:
                worst = max(abs(float(vector[name]) - self.saved[name]) for name in self.saved)
            except (TypeError, ValueError, OverflowError):
                issues.append(f"{source} J1–J5 are unavailable (non-numeric value)")
                continue
            if worst > JOINT_TOLERANCE_SI:
                issues.append(f"{source} J1–J5 differ from the saved Task Home by {worst:.3g} (SI)")
        return issues

    def external_change_issue(self, record) -> str:
        if _fingerprint(record_identity(record)) != _fingerprint(self.expected_identity):
            return "the saved Task Home changed outside the advisor's own recorded revalidations"
        return ""

    # ---- the only authority-creating path -------------------------------------------------
    def revalidate(self, *, kind: str, index: int, label: str, active: bool) -> dict:
        """Re-validate the unchanged saved joints once through the production owners."""

        entry = {"sequence": len(self.ledger) + 1, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "kind": kind, "candidate": index, "label": label, "joints_si": dict(self.saved),
                 "before": record_summary(self.logic.taskHomeRecord(self.node)), "after": None,
                 "outcome": "started", "code": "", "message": ""}
        self.ledger.append(entry)
        try:
            return self._attempt(entry, active)
        except (HomeRevalidationRefused, HomeRevalidationRejected):
            raise
        except Exception as exc:  # anything unexpected may follow a committed accept: record it, never retry
            message = f"Task Home revalidation failed unexpectedly ({type(exc).__name__}: {exc}); the outcome is unknown and is not retried"[:300]
            return self._finish(entry, "refused", "unexpected", message, raises=HomeRevalidationRefused(message))

    def _attempt(self, entry: dict, active: bool) -> dict:
        facade = self.facade
        try:
            self._preconditions(active)
        except HomeRevalidationRefused as exc:
            return self._finish(entry, "refused", "", str(exc), raises=exc)
        try:
            staged = facade.stageManualTaskHomeReview(dict(self.saved))
        except Exception as exc:  # recorded, never hidden; a possibly committed stage is cleared through its owner
            self._cancel_staged(entry)
            message = f"Home review could not be staged: {exc}"[:300]
            return self._finish(entry, "refused", "", message, raises=HomeRevalidationRefused(message))
        if not staged.success:
            self._cancel_staged(entry)
            message = "Home review was not staged: " + str(staged.message)[:240]
            return self._finish(entry, "refused", str(staged.code), message, raises=HomeRevalidationRefused(message))
        try:
            result = facade.acceptManualTaskHomeReview()
        except Exception as exc:  # the production owner may or may not have committed: unknown
            message = f"Task Home acceptance raised ({exc}); the outcome is unknown and is not retried"[:300]
            return self._finish(entry, "refused", "unknown", message, raises=HomeRevalidationRefused(message))
        code = str(getattr(result, "code", ""))
        if getattr(result, "success", False):
            return self._accepted(entry, code, str(result.message))
        owner_code = str(((getattr(result, "details", None) or {}).get("failureEvidence") or {}).get("code") or code)
        if code == "manual_task_home_acceptance_unknown":
            message = "Task Home acceptance reported an unknown outcome: " + str(result.message)[:240]
            return self._finish(entry, "refused", code, message, raises=HomeRevalidationRefused(message))
        self._cancel_staged(entry)
        if owner_code != GUARD_REJECTION_CODE:  # a state/ownership refusal, not the collision guard's verdict
            message = f"Task Home acceptance was refused by the production owner ({owner_code}): " + str(result.message)[:200]
            return self._finish(entry, "refused", owner_code, message, raises=HomeRevalidationRefused(message))
        message = "the production guard rejected the unchanged saved joints: " + str(result.message)[:240]
        self.consecutive_rejections += 1
        return self._finish(entry, "rejected", owner_code, message, raises=HomeRevalidationRejected(message))

    def _preconditions(self, active: bool) -> None:
        facade = self.facade
        if not active:
            raise HomeRevalidationRefused("ROS/MoveIt is not connected; the advisor never connects by itself")
        if (getattr(facade, "_manual_task_home_acceptance_in_progress", False)
                or getattr(facade, "_manual_task_home_reconciliation_in_progress", False)):
            raise HomeRevalidationRefused("a Task Home review or reconciliation is already in progress")
        review = getattr(facade, "manualTaskHomeReview", None)
        if callable(review) and (review().details or {}).get("staged"):
            raise HomeRevalidationRefused("a Task Home review is already staged; the advisor never overwrites it")
        foreign = self.external_change_issue(self.logic.taskHomeRecord(self.node))
        if foreign:
            raise HomeRevalidationRefused(foreign + "; the advisor never revalidates over a change it did not make")
        issues = self.joint_issues()
        if issues:
            raise HomeRevalidationRefused("saved-joint identity check failed: " + "; ".join(issues)[:240])

    def _cancel_staged(self, entry: dict) -> None:
        cancel = getattr(self.facade, "cancelManualTaskHomeReview", None)
        if callable(cancel):
            try:
                cancel()
            except Exception as exc:  # the staged candidate stays detached; the failure is recorded in the ledger entry
                entry["cancel_error"] = f"{type(exc).__name__}: {exc}"[:200]

    def _accepted(self, entry: dict, code: str, message: str) -> dict:
        record = self.logic.taskHomeRecord(self.node)
        gap = str(self.facade.taskHomeValidationGap(self.node) or "")
        after = record_summary(record)
        saved_ok = record is not None and all(
            abs(float(dict(zip(record.joint_names, record.joint_positions_si)).get(name, 1e9)) - value)
            <= JOINT_TOLERANCE_SI for name, value in self.saved.items())
        entry["after"] = after
        if not saved_ok:
            message = "the saved Task Home joints changed during acceptance"
            return self._finish(entry, "refused", code, message, raises=HomeRevalidationRefused(message))
        self.expected_identity = record_identity(record)  # the accept was the advisor's own, whatever the gap says
        if gap:
            self.consecutive_rejections += 1
            message = "accepted but not runtime-validated: " + gap[:200]
            return self._finish(entry, "rejected", code, message, raises=HomeRevalidationRejected(message))
        self.consecutive_rejections = 0
        return self._finish(entry, "validated", code, message[:240])

    def _finish(self, entry: dict, outcome: str, code: str, message: str, raises=None) -> dict:
        entry.update(outcome=outcome, code=code, message=message)
        if entry["after"] is None:
            try:
                entry["after"] = record_summary(self.logic.taskHomeRecord(self.node))
            except Exception as exc:  # the record could not be read either: say so
                entry["after"] = {"revision": None, "status": f"unreadable: {type(exc).__name__}", "validated_at_utc": "",
                                  "base_fingerprint": "", "audit": ""}
        self.write()
        if raises is not None:
            raise raises
        return entry

    def write(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "home-revalidations.json").write_text(json.dumps(self.ledger, indent=1, default=str), encoding="utf-8")

    def summary_lines(self) -> list:
        rows = []
        for e in self.ledger:
            before, after = e["before"] or {}, e["after"] or {}
            rows.append(f"#{e['sequence']} {e['kind']} candidate {e['candidate']} ({e['label']}): {e['outcome']}; "
                        f"revision {before.get('revision')}→{after.get('revision')}; validated_at {after.get('validated_at_utc') or '-'}"
                        + (f"; {e['message']}" if e["outcome"] != "validated" else ""))
        return rows
