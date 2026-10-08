"""Run-local helpers for the bounded S6-ADVISOR-GUI-01 B verification (decision D1/O4).

Used only by the session commands ``Testing/step6_session_commands/advisor_*.py`` inside the existing persistent
headed Step 6 session (``run_dentobot_step6_headed_review.py`` + ``step6_session_driver.py``). Nothing here starts a
runtime, connects, jogs or writes a Home record. Three small pieces:

* ``invariant_snapshot`` / ``snapshot_diff`` — the before/after configuration, Home and joint invariants;
* ``OwnerGuard`` — makes forbidden production owners fail loudly and counts every attempted call;
* ``Timeline`` — an append-only, flushed-per-line monotonic log, so evidence survives a stall or a kill, plus
  ``instrument_session`` which stamps the actual handler/step times used to evaluate an independently timed Cancel.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

JOINT_SOURCES = ("accepted", "monitored", "displayed")
# Fields that may legitimately differ after a consented search: the Home revalidations create new validation
# revisions/timestamps and the production re-confirmation rewrites the confirmed task. Everything else must be equal.
EXPECTED_AUTHORITY_DRIFT = ("home_record_sha256", "home_revision", "home_validated_at_utc", "confirmed_task_fingerprint",
                            "base_placement_revision", "audit_fingerprint")


def _sha(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _matrix(node, logic) -> list:
    import vtk

    matrix = vtk.vtkMatrix4x4()
    node.robotBaseTransform.GetMatrixTransformToWorld(matrix)
    return [[round(matrix.GetElement(r, c), 9) for c in range(4)] for r in range(4)]


def invariant_snapshot(logic, facade, node, *, label: str = "", matrix_reader: Callable | None = None) -> dict:
    """Read-only record of everything the advisor must leave unchanged (or change only through the owners)."""

    home = logic.taskHomeRecord(node)
    joint_reader = getattr(facade, "taskHomeJointIdentity", None)
    joints = joint_reader() if callable(joint_reader) else {}
    confirmed = logic.confirmedTaskRecord(node)
    audit = logic.collisionSceneAuditRecord(node)
    policy = facade.jointPlanningPolicy()
    registry = json.loads(str(getattr(node, "step6TrajectoryRegistryJson", "") or "{}") or "{}")
    return {
        "label": label,
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ros_active": bool(logic.isRos2MotionControlActive(node.robotBaseTransform)),
        "base_world_mm": (matrix_reader or (lambda: _matrix(node, logic)))(),
        "base_locked": bool(node.robotBaseMountLocked),
        "opening_mm": float(node.step6CaseJawTargetGapMm),
        "branch_id": str(registry.get("selected_branch_id") or ""),
        "planning_policy": {k: policy.get(k) for k in ("planner_id", "planning_attempts", "planning_time_sec")},
        "corridor_margin_samples": int(facade.approachCorridorMarginSamples()),
        "spindle_allowance": bool(getattr(node, "step6AllowSpindleGuideContact", False)),
        "barrier_edge_mode": str(getattr(node, "step6MouthBarrierEdgeMode", "") or ""),
        "barrier_tuning": [float(getattr(node, name, float("nan"))) for name in (
            "step6MouthBarrierLipMarginMm", "step6MouthBarrierLipSlabMm", "step6MouthBarrierPortalEnlargeMm")],
        "home_joints_si": dict(zip(home.joint_names, home.joint_positions_si)) if home is not None else None,
        "home_record_sha256": _sha(getattr(node, "step6TaskHomeJson", "") or ""),
        "home_revision": getattr(home, "revision", None),
        "home_validated_at_utc": str(getattr(home, "validated_at_utc", "") or ""),
        "home_validation_gap": str(facade.taskHomeValidationGap(node) or ""),
        "joints_si": {k: (dict(v) if isinstance(v, Mapping) else None) for k, v in (joints or {}).items()},
        "confirmed_task_fingerprint": str(getattr(confirmed, "snapshot_fingerprint", "") or ""),
        "audit_fingerprint": str(getattr(audit, "audit_fingerprint", "") or ""),
        "base_placement_revision": int(getattr(node, "step6BasePlacementRevision", 0) or 0),
    }


def snapshot_diff(before: Mapping, after: Mapping, *, allow: Iterable[str] = ()) -> dict:
    """Changed keys split into unexpected vs allowed (``label``/``utc`` never count)."""

    allowed = set(allow)
    changed = sorted(k for k in set(before) | set(after) if k not in ("label", "utc") and before.get(k) != after.get(k))
    return {"changed": changed, "unexpected": [k for k in changed if k not in allowed],
            "allowed": [k for k in changed if k in allowed]}


def joints_equal_saved(snapshot: Mapping, tolerance: float = 1.0e-12) -> list:
    """Why accepted/monitored/displayed are not exactly the saved Home joints ([] when equal)."""

    saved = snapshot.get("home_joints_si") or {}
    issues = []
    for source in JOINT_SOURCES:
        vector = (snapshot.get("joints_si") or {}).get(source)
        if not vector or set(vector) != set(saved):
            issues.append(f"{source} unavailable")
        else:
            try:
                values = [float(v) for v in (*vector.values(), *saved.values())]
                if not all(math.isfinite(v) for v in values):
                    raise ValueError("non-finite joint")
                if max(abs(float(vector[n]) - float(saved[n])) for n in saved) > tolerance:
                    issues.append(f"{source} differs from the saved Home")
            except (TypeError, ValueError, OverflowError):
                issues.append(f"{source} unavailable (invalid joint value)")
    return issues if saved else ["no saved Task Home"]


def retain_command_failure(logic, facade, node, *, steps, before, guards, path, failure) -> dict:
    """Keep the first command failure, owner counts and restoration evidence even when the command raises."""

    result = {"steps": steps, "before": before, "after": None, "guards": {k: g.report() for k, g in guards.items()},
              "first_failure": f"{type(failure).__name__}: {failure}"[:400]}
    try:
        result["after"] = invariant_snapshot(logic, facade, node, label="after-failed-command")
        result["invariant_diff"] = snapshot_diff(before, result["after"], allow=EXPECTED_AUTHORITY_DRIFT)
        result["joint_issues_after"] = joints_equal_saved(result["after"])
    except Exception as exc:
        result["after_snapshot_error"] = f"{type(exc).__name__}: {exc}"[:300]
    Path(path).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


class OwnerGuard:
    """Wrap production owner methods: ``refuse`` raises (and counts), ``count`` only counts; ``restore`` unwraps."""

    def __init__(self, target, *, refuse: Iterable[str] = (), count: Iterable[str] = ()):
        self.target = target
        self.calls: dict = {}
        self._originals: dict = {}
        try:
            for name in tuple(refuse):
                self._wrap(name, refuse=True)
            for name in tuple(count):
                self._wrap(name, refuse=False)
        except Exception:
            self.restore()
            raise

    def _wrap(self, name: str, *, refuse: bool) -> None:
        original = getattr(self.target, name)
        self._originals[name] = (original, name in vars(self.target))
        self.calls[name] = {"refused" if refuse else "called": 0}

        def guarded(*args, **kwargs):
            key = "refused" if refuse else "called"
            self.calls[name][key] += 1
            if refuse:
                raise RuntimeError(f"advisor probe guard: {name} is not permitted in this run")
            return original(*args, **kwargs)

        setattr(self.target, name, guarded)

    def restore(self) -> None:
        for name, (original, was_instance_attribute) in self._originals.items():
            if was_instance_attribute:
                setattr(self.target, name, original)
            else:
                delattr(self.target, name)  # the class method is visible again
        self._originals.clear()

    def report(self) -> dict:
        return {name: dict(value) for name, value in self.calls.items()}

    def refused_total(self) -> int:
        return sum(v.get("refused", 0) for v in self.calls.values())


class Timeline:
    """Append-only JSONL of CLOCK_MONOTONIC stamps, flushed and fsynced per line."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")

    def stamp(self, kind: str, **fields) -> dict:
        row = {"mono_ns": time.monotonic_ns(), "wall_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "pid": os.getpid(), "kind": kind, **fields}
        self._file.write(json.dumps(row, default=str) + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        return row

    def close(self) -> None:
        self._file.close()


def instrument_session(session, widget, timeline: Timeline) -> Callable:
    """Stamp every ``session.step()`` (before, with the sub-step label, and after) and the Cancel handler entry.

    The Cancel signal already captures its bound handler, so an instance monkeypatch would miss real clicks.
    A temporary Python profile hook stamps entry into that exact handler's code and chains the previous hook.
    Returns an ``undo`` callable; neither observation changes results or timing decisions.
    """

    original_step = session.step
    original_cancel = widget._advisorOnCancel
    cancel_code = getattr(original_cancel, "__func__", original_cancel).__code__
    previous_profile = sys.getprofile()

    def step():
        label = session.progress()
        timeline.stamp("step_start", phase=label.get("phase"), stage=label.get("stage"), step=label.get("step"),
                       candidate=label.get("index"), cand_label=label.get("label"))
        try:
            event = original_step()
        finally:
            timeline.stamp("step_end")
        timeline.stamp("step_event", event=getattr(event, "kind", ""), message=str(getattr(event, "message", ""))[:160])
        return event

    def profile(frame, event, arg):
        if event == "call" and frame.f_code is cancel_code:
            timeline.stamp("cancel_handler_entry", phase=session.phase)
        if previous_profile is not None:
            previous_profile(frame, event, arg)

    session.step = step
    sys.setprofile(profile)

    def undo():
        session.step = original_step
        sys.setprofile(previous_profile)

    return undo


def cancel_latency(rows: Iterable[Mapping], helper: Mapping) -> dict:
    """Combine the in-process timeline with the independent external input stamps.

    ``helper`` carries the external process' ``t_send_before_ns``/``t_send_after_ns`` (same CLOCK_MONOTONIC).
    Reports the delivery delay to the actual handler, the step interval that covered the input and the restore start.
    """

    rows = list(rows)
    handler = next((r for r in rows if r["kind"] == "cancel_handler_entry" and r["mono_ns"] >= helper["t_send_before_ns"]), None)
    covering = None
    for index, row in enumerate(rows):
        if row["kind"] == "step_start" and row["mono_ns"] <= helper["t_send_after_ns"]:
            end = next((r for r in rows[index + 1:] if r["kind"] == "step_end"), None)
            if end is None or end["mono_ns"] >= helper["t_send_before_ns"]:
                covering = {"step": row.get("step"), "candidate": row.get("candidate"), "start_ns": row["mono_ns"],
                            "end_ns": end["mono_ns"] if end else None}
    restore_start = next((r for r in rows if r["kind"] == "step_start" and r.get("phase") == "restoring"
                          and handler is not None and r["mono_ns"] >= handler["mono_ns"]), None)
    result = {"sent_before_ns": helper["t_send_before_ns"], "sent_after_ns": helper["t_send_after_ns"],
              "handler_ns": handler["mono_ns"] if handler else None, "covering_step": covering}
    if handler is not None:
        result["delivery_delay_ms"] = round((handler["mono_ns"] - helper["t_send_after_ns"]) / 1e6, 3)
        if restore_start is not None:
            result["cancel_to_restore_start_ms"] = round((restore_start["mono_ns"] - handler["mono_ns"]) / 1e6, 3)
        done = next((r for r in rows if r["kind"] == "step_event" and r.get("event") == "done"
                     and r["mono_ns"] >= handler["mono_ns"]), None)
        if done is not None:
            result["cancel_to_done_ms"] = round((done["mono_ns"] - handler["mono_ns"]) / 1e6, 3)
    return result
