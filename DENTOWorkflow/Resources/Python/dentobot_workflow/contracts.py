"""Stable internal contracts for the modular DENTOBOT workflow."""

from __future__ import annotations

from enum import IntEnum


class WorkflowStage(IntEnum):
    """Stable internal stage identifiers persisted by the existing workflow."""

    CASE = 0
    IMAGING = 1
    SEGMENTATION = 2
    REVIEW = 3
    DRILL_PLANNING = 4
    SUPPORT_SELECTION = 5
    DOCKING = 6
    SUPPORT_SURFACE = 7
    GUIDE_BUILD = 8
    FINALIZATION = 9
    ROBOT_SIMULATION = 10


PUBLIC_ENTRYPOINT_CLASSES = (
    "DENTOWorkflowParameterNode",
    "DENTOWorkflow",
    "DENTOWorkflowWidget",
    "DENTOWorkflowLogic",
    "DENTOWorkflowTest",
)

STAGE_COUNT = len(WorkflowStage)
