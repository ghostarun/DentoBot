"""Plain records shared by case inspection, prefix selection and the catalog.

These records describe saved evidence. They never confer live workflow authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid


INVENTORY_SCHEMA_VERSION = "1.0"
CHECKPOINT_DEFINITION_VERSION = "1.0"
LIVE_FRESHNESS = "Unverified"


@dataclass(frozen=True)
class Checkpoint:
    id: str
    label: str
    order: int
    scope: str
    requires: tuple[str, ...] = ()
    artifact_roles: tuple[str, ...] = ()
    parameter_fields: tuple[str, ...] = ()
    reference_roles: tuple[str, ...] = ()
    readiness_owner: str = ""


# Initial saved-artifact descriptors, not a replacement for workflow action gates.
# Step 6 records require an audited inventory with explicit artifact dependencies.
CHECKPOINTS = (
    Checkpoint("source.volume", "Step 1 — Source imaging", 10, "shared",
               artifact_roles=("inputVolume",), readiness_owner="logic_segmentation"),
    Checkpoint("anatomy.segmentation", "Step 2 — Segmentation", 20, "shared",
               ("source.volume",), ("teethSegmentation",), readiness_owner="logic_segmentation"),
    Checkpoint("foundation.pose", "Step 3A — Case Foundation", 30, "shared",
               ("anatomy.segmentation",), ("step6CaseJawTransform",),
               readiness_owner="logic_case_foundation"),
    Checkpoint("foundation.base", "Step 3B / 6.1 — Base configuration", 40, "shared",
               ("foundation.pose",), ("robotBaseTransform",), readiness_owner="logic_robot_placement"),
    Checkpoint("trajectory.plan", "Step 4A — Trajectory", 50, "target",
               ("foundation.pose",), ("trajectoryLine", "targetToothBoundsRoi"),
               readiness_owner="logic_workflow"),
    Checkpoint("support.selection", "Step 4B — Supports", 60, "branch",
               ("trajectory.plan",), ("draftTemplateSupportModel",), readiness_owner="logic_guide_support"),
    Checkpoint("dock.assembly", "Step 4C — Dock assembly", 70, "branch",
               ("trajectory.plan", "support.selection"),
               ("targetDockingReferencePlane", "targetDockingAssemblyModel"), readiness_owner="logic_docking"),
    Checkpoint("support.surface", "Step 5A — Support surface", 80, "branch",
               ("support.selection",),
               ("templateSupportBoundaryCurve", "templateSupportBoundaryPlane", "visibleTemplateSupportModel", "templateInsertionDirection"),
               readiness_owner="logic_guide_support"),
    Checkpoint("template.build", "Step 5B — Unified template", 90, "branch",
               ("dock.assembly", "support.surface"), ("patientContactShellModel", "finalPrintableTemplateModel"), readiness_owner="logic_guide"),
    Checkpoint("template.verify", "Step 5C — Template verification", 100, "branch",
               ("template.build",), ("finalizedTemplateShellModel",), readiness_owner="logic_finalization"),
    Checkpoint("simulation.home", "Step 6 — Home configuration", 110, "target",
               ("foundation.base",), parameter_fields=("step6TaskHomeJson",), readiness_owner="logic_robot"),
    Checkpoint("simulation.workspace", "Step 6 — Workspace diagnostics", 120, "target",
               parameter_fields=("step6AssistedLimitProposalJson",), readiness_owner="logic_robot"),
    Checkpoint("simulation.planning", "Step 6 — Planning diagnostics", 130, "branch",
               parameter_fields=("step6MotionDiagnosticJson",), readiness_owner="DENTORobotWorkflowFacade"),
)


@dataclass(frozen=True)
class Artifact:
    id: str
    checkpoint_id: str
    scope: str
    target_id: str = ""
    branch_id: str = ""
    state: str = "Unknown"
    role: str = ""
    dependencies: tuple[str, ...] = ()
    trajectory_ids: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class Branch:
    id: str
    target_id: str
    trajectory_ids: tuple[str, ...]
    pairing_intent: str = "Single"
    state: str = "Unknown"


@dataclass(frozen=True)
class CaseInventory:
    path: str
    package_id: str
    case_id: str
    label: str
    archive_schema: str
    package_sha256: str
    checked_at_utc: str
    target_ids: tuple[str, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    branches: tuple[Branch, ...] = ()
    ownership_complete: bool = False
    unknown_ownership: tuple[str, ...] = ()
    definition_version: str = CHECKPOINT_DEFINITION_VERSION
    live_freshness: str = LIVE_FRESHNESS
    integrity: str = "Valid"
    legacy_identity: bool = True
    historical_record_count: int = 0
    stat_size: int = 0
    stat_mtime_ns: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaseInventory":
        values = dict(data)
        values["target_ids"] = tuple(values.get("target_ids", ()))
        values["unknown_ownership"] = tuple(values.get("unknown_ownership", ()))
        values["artifacts"] = tuple(
            Artifact(**{**item, "dependencies": tuple(item.get("dependencies", ())),
                        "trajectory_ids": tuple(item.get("trajectory_ids", ()))})
            for item in values.get("artifacts", ())
        )
        values["branches"] = tuple(
            Branch(**{**item, "trajectory_ids": tuple(item.get("trajectory_ids", ()))})
            for item in values.get("branches", ())
        )
        return cls(**values)


@dataclass(frozen=True)
class PrefixSelection:
    target_id: str
    branch_id: str
    checkpoint_id: str
    allowed: bool
    included_ids: tuple[str, ...] = ()
    excluded_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    latest_complete_checkpoint: str | None = None
    new_case_id: str = ""
    history_policy: str = "Fresh"


def new_case_id() -> str:
    """Generate container identity without changing geometry/safety fingerprints."""
    return str(uuid.uuid4())
