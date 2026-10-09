"""Input-identity capture for the advisor session (S6-ADVISOR-GUI-01), moved out of ``advisor_service``.

A plain mixin of the session: it reads production records and tracks run-local expected input identity.
It never writes production state or authority.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from dentobot_workflow import advisor_home as home_mod
from dentobot_workflow import feasibility_advisor as fa

# Legacy Step 6 case jaw landmarks are optional: a case with no landmarks node is identified by this fixed value.
# Landmarks are only a fallback when auto opening fails; creating them later changes the identity (stale).
ABSENT_JAW_LANDMARKS_IDENTITY = "absent:v1"


class AdvisorIdentityMixin:
    def _trial_identity_issues(self) -> list:
        """Refuse foreign input drift before another trial or restore owner runs."""

        if self._home is None:
            return []
        try:
            # A trial's own Base change clears the operator's confirmation (advisor-owned, F8); stable_identity never compares it.
            raw = self._capture_input_identity(confirmation_optional=True)
            current = self._stable_identity(raw)
            expected = self._stable_identity(self._trial_identity)
            changed = sorted(k for k in set(current) | set(expected) if current.get(k) != expected.get(k))
            if (raw.get("audited_scene_sources") or {}).get("base_fingerprint") != (
                    self._trial_identity.get("audited_scene_sources") or {}).get("base_fingerprint"):
                changed.append("audited scene Base binding")
        except Exception as exc:
            return [f"trial input identity could not be read: {exc}"[:250]]
        return ["trial input identity changed outside an advisor owner: " + ", ".join(changed)] if changed else []

    @staticmethod
    def _unchanged_scene_sources(scene, step):
        rows = []
        for row in (scene or {}).get("objects") or ():
            if step in ("apply_barrier", "apply_opening") and row.get("source_role") == "mouth-barrier":
                continue
            if step == "apply_opening":
                # Prepared/outgoing geometry moves at the requested opening; its original geometry does not.
                rows.append({k: row.get(k) for k in ("source_name", "source_role", "classification", "source_fingerprint",
                                                   "source_point_count", "source_cell_count")})
                continue
            rows.append({k: v for k, v in row.items() if step != "apply_base" or k not in (
                "outgoing_fingerprint", "outgoing_bounds_base_link_mm")})
        return rows

    def _advance_trial_identity(self, step: str, *, commit: bool = True) -> None:
        """Attribute only known fields changed by a successful configuration owner."""

        if self._home is None:
            return
        current = self._capture_input_identity(confirmation_optional=True)
        before, after = self._stable_identity(self._trial_identity), self._stable_identity(current)
        allowed = {"apply_base": {"saved_base", "audited_scene_sources", "collision_audit_status"},
                   "apply_barrier": {"mouth_barrier", "audited_scene_sources", "collision_audit_status"},
                   "apply_opening": {"audited_scene_sources", "collision_audit_status"}}.get(step, set())
        if step == "apply_opening":
            # Preparation changes at the requested opening; all other source/environment fields stay exact.
            before = {**before, "source_environment": dict(before.get("source_environment") or {})}
            after = {**after, "source_environment": dict(after.get("source_environment") or {})}
            before["source_environment"].pop("jaw_configuration_fingerprint", None)
            after["source_environment"].pop("jaw_configuration_fingerprint", None)
        changed = sorted(k for k in set(before) | set(after)
                         if k not in allowed and before.get(k) != after.get(k))
        if step in ("apply_base", "apply_barrier", "apply_opening") and self._unchanged_scene_sources(
                before.get("audited_scene_sources"), step) != self._unchanged_scene_sources(after.get("audited_scene_sources"), step):
            changed.append("unrelated audited scene sources")
        scene_before = self._trial_identity.get("audited_scene_sources") or {}
        scene_after = current.get("audited_scene_sources") or {}
        for field in ("base_fingerprint", "jaw_preparation_fingerprint", "world_to_base_fingerprint"):
            permitted = (step == "apply_base" and field == "world_to_base_fingerprint"
                         or step == "apply_base" and field == "base_fingerprint"
                         or step == "apply_opening" and field == "jaw_preparation_fingerprint")
            if not permitted and scene_before.get(field) != scene_after.get(field):
                changed.append("audited scene " + field)
        if self._active():
            if scene_after.get("runtime_acknowledgement_status") != "Acknowledged":
                changed.append("audited scene runtime acknowledgement")
            freshness = self.logic.collisionSceneAuditFreshnessIssues(self.node)
            if freshness:
                changed.append("audited scene freshness: " + "; ".join(freshness))
        if changed:
            raise home_mod.HomeRevalidationRefused("immutable input identity changed during " + step + ": " + ", ".join(changed))
        if commit:
            self._trial_identity = current

    def _ctx_matrix(self, transform_node):
        import numpy as np
        import vtk

        matrix = vtk.vtkMatrix4x4()
        transform_node.GetMatrixTransformToWorld(matrix)
        return np.array([[matrix.GetElement(r, c) for c in range(4)] for r in range(4)])

    def _persisted_registry(self) -> dict:
        """Read the saved registry directly; eligibility checks must not sync/migrate it."""

        raw = str(getattr(self.node, "step6TrajectoryRegistryJson", "") or "").strip()
        registry = json.loads(raw) if raw else {}
        if not isinstance(registry, dict):
            raise ValueError("the saved PreparedBranch registry is unavailable")
        branches = registry.get("prepared_branches")
        if not isinstance(branches, Mapping):
            raise ValueError("the saved PreparedBranch registry has no branch map")
        return registry

    @staticmethod
    def _home_record_identity(record) -> dict:
        return home_mod.record_identity(record)

    @staticmethod
    def _scene_source_identity(audit) -> dict:
        """Stable audited geometry identity, excluding MRML/runtime object IDs and timestamps."""

        rows = []
        for raw in getattr(audit, "object_records", ()) or ():
            if not isinstance(raw, Mapping):
                continue
            rows.append({key: raw.get(key) for key in (
                "source_name", "source_role", "classification", "source_fingerprint",
                "prepared_world_fingerprint", "outgoing_fingerprint", "jaw_transform_fingerprint",
                "jaw_transform_application_count", "world_to_base_application_count",
                "source_point_count", "source_cell_count", "outgoing_point_count", "outgoing_cell_count",
                "source_bounds_world_ras_mm", "prepared_bounds_world_ras_mm", "outgoing_bounds_base_link_mm",
                "connected_component_count", "boundary_or_nonmanifold_edge_count",
                "publisher_linear_scale_m_per_mm", "collision_padding_mm",
            )})
        rows.sort(key=lambda row: (str(row.get("source_role") or ""), str(row.get("source_name") or "")))
        return {"objects": rows, "fingerprint": fa.fingerprint_of(rows) if rows else ""}

    def _capture_input_identity(self, *, confirmation_optional: bool = False) -> dict:
        """Capture current source identity using existing logic/facade records only."""

        logic, node = self.logic, self.node
        registry = self._persisted_registry()
        branch_id = str(registry.get("selected_branch_id") or "")
        branches = registry.get("prepared_branches") or {}
        branch = branches.get(branch_id) if branch_id else None
        if not isinstance(branch, Mapping) or not branch_id:
            raise ValueError("the selected PreparedBranch identity is unavailable")
        eligibility = logic.evaluatePreparedBranchEligibility(node, branch_id, registry=registry)
        if eligibility.get("reason") != "VALID":
            raise ValueError("the selected PreparedBranch is no longer VALID: "
                             + str(eligibility.get("message") or eligibility.get("reason")))
        if str(eligibility.get("branch_id") or "") != branch_id:
            raise ValueError("the selected PreparedBranch changed during identity capture")

        # This existing snapshot is read-only. Keep only source/environment fields
        # below; jaw opening and Base are candidate state and are captured separately.
        snapshot_fn = getattr(logic, "buildCaseFoundationSnapshot", None)
        if not callable(snapshot_fn):
            raise ValueError("the Case Foundation source snapshot API is unavailable")
        foundation = snapshot_fn(node)
        audit = logic.collisionSceneAuditRecord(node)
        home = logic.taskHomeRecord(node)
        confirmed = logic.confirmedTaskRecord(node)
        trajectory_ids = [str(value) for value in branch.get("trajectory_ids") or ()]
        trajectory_revisions = {}
        for tooth in (registry.get("teeth") or {}).values():
            for slot in ((tooth.get("trajectory_set") or {}).get("slots") or ()):
                trajectory_id = str(slot.get("trajectory_id") or "")
                if trajectory_id in trajectory_ids:
                    trajectory_revisions[trajectory_id] = str(slot.get("trajectory_fingerprint") or "")
        active_trajectory_revision = str(logic.step6TrajectoryRevision(node) or "")
        scene = self._scene_source_identity(audit) if audit is not None else {}
        if audit is not None:
            scene.update({
                "base_fingerprint": str(getattr(audit, "base_fingerprint", "") or ""),
                "jaw_preparation_fingerprint": str(getattr(audit, "jaw_preparation_fingerprint", "") or ""),
                "world_to_base_fingerprint": str(getattr(audit, "world_to_base_fingerprint", "") or ""),
                "runtime_acknowledgement_status": str(
                    (getattr(audit, "runtime_acknowledgement", {}) or {}).get("status") or ""
                ),
            })
            scene["fingerprint"] = fa.fingerprint_of({key: value for key, value in scene.items() if key != "fingerprint"})
        source_fields = (
            "case_identity", "anatomy_fingerprint", "source_volume_fingerprint", "source_segmentation_fingerprint",
            "jaw_source_fingerprint", "jaw_landmarks_fingerprint", "landmark_positions_ras_mm",
            "landmark_review_fingerprint", "hinge_model_schema", "jaw_configuration_fingerprint",
            "robot_profile_fingerprint", "tool_identity", "tool_fingerprint", "limits_fingerprint",
            "workspace_fingerprint",
        )
        source_environment = {
            key: (foundation.get(key) if isinstance(foundation, Mapping) else getattr(foundation, key, None))
            for key in source_fields
        }
        if source_environment.get("jaw_landmarks_fingerprint") == "":
            # The Case Foundation snapshot reports an empty landmark fingerprint only when no landmarks node exists
            # (a partial node raises there). Bind that explicit absence; a missing field (None) still fails closed.
            source_environment["jaw_landmarks_fingerprint"] = ABSENT_JAW_LANDMARKS_IDENTITY
        home_identity = self._home_record_identity(home)
        base_matrix = self._ctx_matrix(node.robotBaseTransform)
        policy = self.facade.jointPlanningPolicy()
        identity = {
            "schema": fa.ADVISOR_SCHEMA,
            "target_fdi": self.target_fdi,
            "selected_branch_id": branch_id,
            "branch_revision": str(branch.get("revision") or ""),
            "branch_foundation_fingerprint": str(branch.get("branch_foundation_fingerprint") or ""),
            "trajectory_ids": trajectory_ids,
            "trajectory_revisions": trajectory_revisions,
            "active_trajectory_revision": active_trajectory_revision,
            "source_environment": source_environment,
            "audited_scene_sources": scene,
            "collision_audit_status": str(getattr(audit, "status", "") or ""),
            "robot_profile": str(logic.robotProfileFingerprint() or ""),
            "confirmed_task_fingerprint": str(getattr(confirmed, "snapshot_fingerprint", "") or ""),
            "saved_base": fa.fingerprint_of([round(float(v), 9) for v in base_matrix.flatten()]),
            "saved_home": fa.fingerprint_of(home_identity),
            "home_joints": {str(n): round(float(v), 9) for n, v in zip(getattr(home, "joint_names", ()) or (),
                                                                       getattr(home, "joint_positions_si", ()) or ())},
            "mouth_barrier": {"edge_mode": str(getattr(node, "step6MouthBarrierEdgeMode", "") or ""),
                              "tuning": self._live_barrier_tuning()},
            "limits": fa.fingerprint_of(vars(self.limits)),
            "task_limits": str(logic.step6TaskLimitsFingerprint(node) or ""),
            "corridor_margin_samples": int(self.facade.approachCorridorMarginSamples()),
            "planning_policy": {key: policy.get(key) for key in (
                "planner_id", "planning_attempts", "planning_time_sec", "independent_replans")},
        }
        missing = []
        if not self.target_fdi:
            missing.append("active target identity")
        for key in ("branch_revision", "branch_foundation_fingerprint", "active_trajectory_revision",
                    "robot_profile", "confirmed_task_fingerprint", "saved_home", "task_limits"):
            if not identity.get(key) and not (key == "confirmed_task_fingerprint" and confirmation_optional):
                missing.append(key)
        if not home_identity:
            missing.append("saved Task Home identity")
        if not trajectory_ids or set(trajectory_revisions) != set(trajectory_ids) or not all(trajectory_revisions.values()):
            missing.append("selected branch trajectory revisions")
        if not all(source_environment.get(key) for key in (
                "case_identity", "anatomy_fingerprint", "source_volume_fingerprint", "source_segmentation_fingerprint",
                "jaw_source_fingerprint", "jaw_landmarks_fingerprint", "jaw_configuration_fingerprint",
                "tool_identity", "tool_fingerprint", "limits_fingerprint")):
            missing.append("source geometry/environment fingerprints")
        if (not scene.get("objects") or not scene.get("base_fingerprint")
                or not scene.get("jaw_preparation_fingerprint") or not scene.get("world_to_base_fingerprint")
                or not scene.get("runtime_acknowledgement_status") or not scene.get("fingerprint")
                or not identity["collision_audit_status"]):
            missing.append("audited scene geometry")
        if missing:
            raise ValueError("safe input identity unavailable: " + ", ".join(missing))
        return identity

    def _identity_matches_baseline(self) -> tuple[bool, str]:
        if not self._identity_available:
            return False, self._identity_error or "safe input identity is unavailable"
        try:
            current = self._capture_input_identity()
        except Exception as exc:
            return False, str(exc)[:300]
        if self._home is not None:  # revision-bound authority is re-established and ledgered, not compared
            issues = self._trial_identity_issues()
            if issues:
                return False, "; ".join(issues)
            if fa.fingerprint_of(self._stable_identity(current)) != fa.fingerprint_of(self._stable_identity(self._base_identity)):
                return False, "branch, trajectory, source geometry, saved Home joints, Base, limits, or audited scene geometry changed"
            return True, ""
        if fa.fingerprint_of(current) != fa.fingerprint_of(self._base_identity):
            return False, "branch, trajectory, source geometry, Task Home, Base, limits, or audited scene changed"
        return True, ""

    def _stable_identity(self, identity: Mapping, *, source_only: bool = False) -> dict:
        return home_mod.stable_identity(identity, self.saved_home or {}, source_only=source_only)

    def _capture_base_snapshot(self) -> dict | None:
        """The accepted Base identity an exact restore reinstates (None when the owner cannot describe it).

        A missing snapshot keeps the restore on the ordinary Base owner path, which bumps the revision and so
        leaves the saved Task Home for explicit 6.2 review (fail-closed); the search itself is not blocked here.
        """

        capture = getattr(self.facade, "manualBaseIdentitySnapshot", None)
        if not callable(capture):
            return None
        try:
            snapshot = dict(capture())
        except Exception:
            return None
        if not snapshot.get("locked") or not snapshot.get("collision_audit_fingerprint"):
            return None
        return snapshot

    def _capture_planning_policy(self) -> tuple:
        """The CURRENT production planning policy (planner, attempts, time), else the documented fallback."""
        try:
            live = self.facade.jointPlanningPolicy()
            policy = fa.policy_values({fa.PLANNER_ID: live["planner_id"],
                                       fa.PLANNING_ATTEMPTS: live["planning_attempts"],
                                       fa.PLANNING_TIME_SEC: live["planning_time_sec"]})
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            return fa.policy_values(None), (
                "fallback feasibility_advisor.DEFAULT_POLICY (facade planning policy unavailable: "
                + str(exc)[:160] + ")")
        return policy, "facade DENTORobotWorkflowFacade.jointPlanningPolicy() at search start"

    # ---- unconfirmed restoration (S6-ADVISOR-GUI-01 F7) ---------------------------------------------
    def _unconfirmed_restore_reason(self) -> str:
        getter = getattr(self.facade, "advisorRestoreUnconfirmed", None)
        return str(getter() or "") if callable(getter) else ""

    def _restore_is_current(self) -> bool:
        """True only when the Base is locked, Task Home is validated against it and the task is confirmed again."""
        node, logic = self.node, self.logic
        return bool(
            node.robotBaseMountLocked
            and not logic.taskHomeFreshnessIssues(node)
            and not self.facade.taskHomeValidationGap(node)
            and not logic.confirmedTaskFreshnessIssues(node)
        )

    def _record_restore_outcome(self) -> None:
        """An unconfirmed restore is recorded on the facade, so a closed and reopened advisor still blocks."""
        if self.restore_issues:
            setter = getattr(self.facade, "setAdvisorRestoreUnconfirmed", None)
            if callable(setter):
                setter("; ".join(self.restore_issues)[:400])
        else:
            clearer = getattr(self.facade, "clearAdvisorRestoreUnconfirmed", None)
            if callable(clearer):
                clearer()

    # ---- operator Task confirmation (S6-ADVISOR-GUI-01 F8) ----------------------------------------------
    # A candidate may confirm the task for its trial (temporary machinery). The search must never leave the
    # operator's confirmation different from what it was before the search.
    def _confirmed_task_fingerprint(self) -> str:
        record = self.logic.confirmedTaskRecord(self.node)
        return str(getattr(record, "snapshot_fingerprint", "") or "") if record is not None else ""

    def _do_apply_confirm(self, current):
        if current.stage == "restore":
            if not self._original_confirmation:  # nothing was confirmed before the search: cleared by the restore check
                return "no operator confirmation before the search (cleared by the restore check)"
            if self._confirmed_task_fingerprint() == self._original_confirmation:
                return "original task confirmation is already current"
        result = self.facade.confirmTask()
        current.observed["confirm"] = [bool(result.success), str(result.code), str(result.message)[:300]]
        if not result.success:
            raise RuntimeError("Task was not confirmed: " + str(result.message)[:200])
        if current.stage == "restore" and self._confirmed_task_fingerprint() != self._original_confirmation:
            raise RuntimeError("the restored task confirmation differs from the original")
        return "task confirmed"

    def _confirmation_restore_issue(self) -> str:
        """Every search end: the confirmation is exactly the pre-search state ("" when so, else the unconfirmed-restore reason)."""
        try:
            if not self._original_confirmation and self._confirmed_task_fingerprint():
                self.facade.clearTaskConfirmation("advisor restore: no operator confirmation before search")
            current = self._confirmed_task_fingerprint()
        except Exception as exc:
            return "the Task confirmation could not be restored: " + str(exc)[:200]
        if current != self._original_confirmation:
            return ("the Task confirmation after the search (%s) is not the one before it (%s)"
                    % (current[:12] or "none", self._original_confirmation[:12] or "none"))
        return ""

    def _operator_confirmation_drift(self) -> str:
        """Read-only, for Apply & Save: "" when the confirmation is the operator's own pre-search state."""
        current = self._confirmed_task_fingerprint()
        if current == self._original_confirmation:
            return ""
        return ("the Task confirmation (%s) is not the operator's own from before the search (%s); "
                "only the operator's Confirm Task can provide it" % (current[:12] or "none", self._original_confirmation[:12] or "none"))
