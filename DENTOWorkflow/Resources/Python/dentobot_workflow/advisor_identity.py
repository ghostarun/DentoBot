"""Input-identity capture for the advisor session (S6-ADVISOR-GUI-01), moved out of ``advisor_service``.

A plain mixin of the session: it reads the production logic/facade/node records the session already holds
and never writes anything. Behaviour is unchanged by the move (module line budget only).
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from dentobot_workflow import advisor_home as home_mod
from dentobot_workflow import feasibility_advisor as fa


class AdvisorIdentityMixin:
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

    def _capture_input_identity(self) -> dict:
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
            if not identity.get(key):
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
            if fa.fingerprint_of(self._stable_identity(current)) != fa.fingerprint_of(self._stable_identity(self._base_identity)):
                return False, "branch, trajectory, source geometry, saved Home joints, Base, limits, or audited scene geometry changed"
            return True, ""
        if fa.fingerprint_of(current) != fa.fingerprint_of(self._base_identity):
            return False, "branch, trajectory, source geometry, Task Home, Base, limits, or audited scene changed"
        return True, ""

    def _stable_identity(self, identity: Mapping, *, source_only: bool = False) -> dict:
        return home_mod.stable_identity(identity, self.saved_home or {}, source_only=source_only)
