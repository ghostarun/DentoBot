"""Public 3D Slicer entrypoints for the modular DENTOBOT workflow."""

from __future__ import annotations

import sys
from pathlib import Path

from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
    ScriptedLoadableModuleWidget,
)
from slicer.util import VTKObservationMixin


_helperDirectory = Path(__file__).resolve().parent / "Resources" / "Python"
if str(_helperDirectory) not in sys.path:
    sys.path.insert(0, str(_helperDirectory))

from dentobot_workflow.logic_backend import BackendLogicMixin
from dentobot_workflow.logic_case_bundle import CaseBundleLogicMixin
from dentobot_workflow.logic_constants import LogicConstantsMixin
from dentobot_workflow.logic_core import CoreLogicMixin
from dentobot_workflow.logic_display import DisplayLogicMixin
from dentobot_workflow.logic_finalization import FinalizationLogicMixin
from dentobot_workflow.logic_guide import GuideLogicMixin
from dentobot_workflow.logic_guide_support import GuideSupportLogicMixin
from dentobot_workflow.logic_patient_shell import PatientShellLogicMixin
from dentobot_workflow.logic_robot import RobotLogicMixin
from dentobot_workflow.logic_segmentation import SegmentationLogicMixin
from dentobot_workflow.logic_step6_scene import Step6SceneLogicMixin
from dentobot_workflow.logic_workflow import WorkflowLogicMixin
from dentobot_workflow.parameter_state import DENTOWorkflowParameterNode
from dentobot_workflow.widget_application import ApplicationWidgetMixin
from dentobot_workflow.widget_bootstrap import BootstrapWidgetMixin
from dentobot_workflow.widget_case_backend import CaseBackendWidgetMixin
from dentobot_workflow.widget_guide_build import GuideBuildWidgetMixin
from dentobot_workflow.widget_guide_support import GuideSupportWidgetMixin
from dentobot_workflow.widget_lifecycle import LifecycleWidgetMixin
from dentobot_workflow.widget_panels import WorkflowPanelsWidgetMixin
from dentobot_workflow.widget_planning import PlanningWidgetMixin
from dentobot_workflow.widget_robot import RobotWidgetMixin
from dentobot_workflow.widget_segmentation import SegmentationWidgetMixin
from dentobot_workflow.widget_views import ViewerWidgetMixin


class DENTOWorkflow(ScriptedLoadableModule):
    """DENTOBOT's focused case-imaging entry point."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.parent.title = _("DENTO Workflow")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "DENTOBOT")]
        self.parent.dependencies = ["DICOM", "DynamicModeler", "Markups", "Models"]
        self.parent.contributors = ["Taruneswar (IITM)"]
        self.parent.helpText = _(
            "DENTOBOT provides a focused workflow for opening a case, loading "
            "CBCT DICOM data through Slicer, running the external inference "
            "backend, and interactively reviewing the returned dental anatomy."
        )
        self.parent.acknowledgementText = _(
            "Developed as an academic research prototype at IIT Madras. "
            "This software is not validated for clinical use."
        )


class DENTOWorkflowWidget(
    BootstrapWidgetMixin,
    CaseBackendWidgetMixin,
    GuideBuildWidgetMixin,
    GuideSupportWidgetMixin,
    PlanningWidgetMixin,
    SegmentationWidgetMixin,
    LifecycleWidgetMixin,
    WorkflowPanelsWidgetMixin,
    ApplicationWidgetMixin,
    ViewerWidgetMixin,
    RobotWidgetMixin,
    ScriptedLoadableModuleWidget,
    VTKObservationMixin,
):
    """Qt/MRML user interface for imaging and the external-compute bridge."""

    VIEW_CONTROLS_SETTINGS_PREFIX = "DENTOBOT/ViewControlsPalette"
    VIEW_CONTROLS_VISIBLE_SETTING = f"{VIEW_CONTROLS_SETTINGS_PREFIX}/Visible"
    VIEW_CONTROLS_GEOMETRY_SETTING = f"{VIEW_CONTROLS_SETTINGS_PREFIX}/Geometry"


class DENTOWorkflowLogic(
    LogicConstantsMixin,
    CoreLogicMixin,
    BackendLogicMixin,
    DisplayLogicMixin,
    SegmentationLogicMixin,
    FinalizationLogicMixin,
    GuideLogicMixin,
    PatientShellLogicMixin,
    GuideSupportLogicMixin,
    WorkflowLogicMixin,
    RobotLogicMixin,
    Step6SceneLogicMixin,
    CaseBundleLogicMixin,
    ScriptedLoadableModuleLogic,
):
    """Reusable MRML, volume-geometry, and external-bridge operations."""


from dentobot_workflow.slicer_tests import DENTOWorkflowTestMixin


class DENTOWorkflowTest(DENTOWorkflowTestMixin, ScriptedLoadableModuleTest):
    """Public compatibility wrapper for the external Slicer test suite."""

    pass
