"""Extracted final printable template assembly methods."""

from __future__ import annotations

from .runtime import *
from .workflow_progress import WorkflowCancelled, WorkflowProgress


class TemplateAssemblyWidgetMixin:

    def _createOrUpdateFinalPrintableTemplate(self, progress=None):
        if not self._parameterNode or not self.logic:
            raise RuntimeError(_("DENTOWorkflow is not ready."))
        targetDockingAssembly = self._parameterNode.targetDockingAssemblyModel
        trajectories = self.logic.getSelectedTemplateGuideTrajectories()
        if not trajectories and self._parameterNode.trajectoryLine:
            trajectories = [self._parameterNode.trajectoryLine]
        currentFinal = self._parameterNode.finalPrintableTemplateModel
        reuseCurrent = False
        if self.logic.isFinalPrintableTemplateModelNode(currentFinal):
            try:
                reuseCurrent = (
                    self.logic.getFinalPrintableTemplateSummary(currentFinal)["trajectories"]
                    == trajectories
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
        finalModel, roleModels, details = (
            self.logic.createOrUpdateFinalPrintableTemplate(
                self._parameterNode.patientContactShellModel,
                targetDockingAssembly,
                trajectories,
                outerDiameterMm=self._parameterNode.templateSleeveOuterDiameterMm,
                innerDiameterMm=self._parameterNode.templateSleeveInnerDiameterMm,
                heightMm=self._parameterNode.templateSleeveHeightMm,
                dockingClearanceMm=self._parameterNode.templateDockingClearanceMm,
                reinforcementRadialMm=(
                    self._parameterNode.templateReinforcementRadialMm
                ),
                reinforcementDepthMm=(
                    self._parameterNode.templateReinforcementDepthMm
                ),
                samplingSpacingMm=self._parameterNode.templateSamplingSpacingMm,
                dockingModel=(self._parameterNode.templateDockingAssemblyModel if reuseCurrent else None),
                clearanceModel=(self._parameterNode.templateDockingClearanceModel if reuseCurrent else None),
                reinforcementModel=(
                    self._parameterNode.templateDockingReinforcementModel if reuseCurrent else None
                ),
                channelsModel=(self._parameterNode.templateDockingChannelsModel if reuseCurrent else None),
                finalModel=currentFinal if reuseCurrent else None,
                progress=progress,
            )
        )
        if progress:
            progress("Registering unified template outputs", can_cancel=False)
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.templateDockingAssemblyModel = roleModels["docking"]
            self._parameterNode.templateDockingClearanceModel = roleModels["clearance"]
            self._parameterNode.templateDockingReinforcementModel = roleModels[
                "reinforcement"
            ]
            self._parameterNode.templateDockingChannelsModel = roleModels["channels"]
            self._parameterNode.finalPrintableTemplateModel = finalModel
        finally:
            self._parameterNode.EndModify(wasModifying)
        if progress:
            progress("Recording template lineage", can_cancel=False)
        for role, node in (
            (
                self.logic.TEMPLATE_FINAL_GUIDE_RESEARCH_SHELL_REFERENCE_ROLE,
                self._parameterNode.researchTemplateShellModel,
            ),
            (
                self.logic.TEMPLATE_FINAL_GUIDE_RESEARCH_SLEEVE_REFERENCE_ROLE,
                self._parameterNode.researchTemplateSleeveModel,
            ),
            (
                self.logic.TEMPLATE_FINAL_GUIDE_FINALIZED_SHELL_REFERENCE_ROLE,
                self._parameterNode.finalizedTemplateShellModel,
            ),
        ):
            finalModel.SetNodeReferenceID(role, node.GetID() if node else None)
        self.logic.syncDentoCaseTrajectoryRegistry(self._parameterNode)
        if progress:
            progress("Refreshing template review", can_cancel=False)
        logging.info(
            "Generated unified template %s from %d trajectories with %d triangles",
            finalModel.GetID(),
            details["assembly"]["trajectoryCount"],
            details["fusion"]["triangleCount"],
        )
        self._updateTemplateGuide()
        self._updateTemplateFinalization()
        return finalModel, roleModels, details

    def onGenerateFinalPrintableTemplate(self) -> None:
        """Compatibility action: rebuild only the unified fusion stage."""

        if not self._parameterNode or not self.logic:
            return
        if getattr(self, "_workflowActionBusy", False):
            return
        self._workflowActionBusy = True
        progress = WorkflowProgress("Step 5B unified template")
        try:
            self._createOrUpdateFinalPrintableTemplate(progress=progress.update)
        except WorkflowCancelled as exc:
            self.ui.templateDockingFusionStatusLabel.text = str(exc)
            self.ui.templateDockingFusionStatusLabel.styleSheet = "color: #b36b00;"
        except (RuntimeError, ValueError) as exc:
            self.ui.templateDockingFusionStatusLabel.text = str(exc)
            self.ui.templateDockingFusionStatusLabel.styleSheet = "color: #b00020;"
            progress.close()
            slicer.util.errorDisplay(str(exc))
        finally:
            progress.close()
            self._workflowActionBusy = False

    def _completeTemplateBuildPreflight(self) -> dict:
        if not self._parameterNode or not self.logic:
            raise RuntimeError(_("DENTOWorkflow is not ready."))
        try:
            self._normalizedTemplateDockingParameters()
        except ValueError as exc:
            raise ValueError(
                _("Review Step 5B · Unified template dimensions (section 2): %1").replace(
                    "%1", str(exc)
                )
            ) from exc
        sourceSummary = self.logic.getDraftTemplateSupportModelSummary(
            self._parameterNode.draftTemplateSupportModel
        )
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale Step 4B support draft first."))
        visibleSummary = self.logic.getVisibleTemplateSupportModelSummary(
            self._parameterNode.visibleTemplateSupportModel
        )
        if visibleSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale visible support preview first."))
        if visibleSummary["sourceModel"] is not self._parameterNode.draftTemplateSupportModel:
            raise ValueError(_("The visible support preview belongs to another support model."))
        directionSummary = self.logic.getTemplateInsertionDirectionSummary(
            self._parameterNode.templateInsertionDirection
        )
        if directionSummary["sourceSurface"] is not self._parameterNode.visibleTemplateSupportModel:
            raise ValueError(_("Refresh the insertion direction from the current trajectory."))
        dockingSummary = self.logic.getTargetDockingAssemblySummary(
            self._parameterNode.targetDockingAssemblyModel
        )
        if dockingSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale Step 4C docking assembly first."))
        if dockingSummary["orientationState"] != "Confirmed":
            raise ValueError(
                _(
                    "Confirm the collision-screened Step 4C dock orientation "
                    "before building the complete template."
                )
            )
        if (
            dockingSummary["segmentation"] is not sourceSummary["sourceSegmentation"]
            or dockingSummary["targetSegmentId"] != sourceSummary["targetSegmentId"]
        ):
            raise ValueError(_("The Step 4C assembly belongs to another target anatomy."))
        trajectories = self.logic.getSelectedTemplateGuideTrajectories()
        if not trajectories and self._parameterNode.trajectoryLine:
            trajectories = [self._parameterNode.trajectoryLine]
        eligible = self.logic.getEligibleTemplateGuideTrajectories(
            self._parameterNode.draftTemplateSupportModel
        )
        if not 1 <= len(trajectories) <= 2 or any(
            trajectoryNode not in eligible for trajectoryNode in trajectories
        ):
            raise ValueError(_("Choose one current-target trajectory or an explicit pair."))
        for trajectoryNode in trajectories:
            trajectorySummary = self.logic.getTrajectorySummary(trajectoryNode)
            if (
                not trajectorySummary["isValid"]
                or trajectorySummary["definedPointCount"] != 2
                or not trajectoryNode.GetLocked()
            ):
                raise ValueError(_("Complete and lock every selected Step 5B trajectory first."))
        if dockingSummary["trajectories"] != trajectories:
            raise ValueError(_("Step 4C must match the selected trajectory or explicit pair."))
        return {
            "sourceSummary": sourceSummary,
            "visibleSummary": visibleSummary,
            "directionSummary": directionSummary,
            "dockingSummary": dockingSummary,
        }

    def onBuildOrUpdateCompleteTemplate(self) -> None:
        """Generate only missing/stale Step 5B stages, then inspect the result."""

        if not self._parameterNode or not self.logic:
            return
        if getattr(self, "_workflowActionBusy", False):
            return
        self._workflowActionBusy = True
        progress = WorkflowProgress("Step 5B complete template")
        generatedStages = []
        reusedStages = []
        try:
            # Preflight the inexpensive plan/dock contracts before any voxel work.
            progress.update("Checking inputs")
            self._completeTemplateBuildPreflight()
            self._updateTemplateGuide()

            blockoutCurrent = False
            try:
                blockoutCurrent = (
                    self.logic.getTemplateUndercutOutputSummary(
                        self._parameterNode.templateUndercutBlockoutModel,
                        "TemplateUndercutBlockout",
                    )["geometryState"]
                    == "Current"
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
            if blockoutCurrent:
                progress.update("Reusing directional blockout", 1, 3)
                reusedStages.append(_("directional blockout"))
            else:
                progress.update("Building directional blockout", 0, 3)
                self._createOrUpdateTemplateUndercuts()
                progress.update("Directional blockout complete", 1, 3)
                generatedStages.append(_("directional blockout"))

            shellCurrent = False
            try:
                shellCurrent = (
                    self.logic.getPatientContactShellSummary(
                        self._parameterNode.patientContactShellModel
                    )["geometryState"]
                    == "Current"
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
            if shellCurrent:
                progress.update("Reusing patient shell", 2, 3)
                reusedStages.append(_("patient shell"))
            else:
                progress.update("Building patient shell", 1, 3)
                self._createOrUpdatePatientContactShell(progress=progress.update)
                progress.update("Patient shell complete", 2, 3)
                generatedStages.append(_("patient shell"))

            self._updateTemplateGuide()
            finalCurrent = False
            try:
                finalCurrent = (
                    self.logic.getFinalPrintableTemplateSummary(
                        self._parameterNode.finalPrintableTemplateModel
                    )["geometryState"]
                    == "Current"
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
            if finalCurrent:
                progress.update("Reusing unified fusion", 3, 3)
                reusedStages.append(_("unified guide/dock fusion"))
            else:
                progress.update("Building unified fusion", 2, 3)
                self._createOrUpdateFinalPrintableTemplate(progress=progress.update)
                progress.update("Unified fusion complete", 3, 3)
                generatedStages.append(_("unified guide/dock fusion"))

            self.ui.templateDockingFusionGroupBox.collapsed = False
            self._applyWorkflowViewPreset("final_only")
            self.onFrameWorkflowView()
            generatedText = ", ".join(generatedStages) or _("none")
            reusedText = ", ".join(reusedStages) or _("none")
            self.ui.templateDockingFusionStatusLabel.text = (
                _("Complete template is current. Generated: %1. Reused: %2.")
                .replace("%1", generatedText)
                .replace("%2", reusedText)
            )
            self.ui.templateDockingFusionStatusLabel.styleSheet = "color: #207227;"
        except WorkflowCancelled as exc:
            self.ui.templateDockingFusionGroupBox.collapsed = False
            self.ui.templateDockingFusionStatusLabel.text = str(exc)
            self.ui.templateDockingFusionStatusLabel.styleSheet = "color: #b36b00;"
        except (RuntimeError, ValueError) as exc:
            self.ui.templateDockingFusionGroupBox.collapsed = False
            self.ui.templateDockingFusionStatusLabel.text = str(exc)
            self.ui.templateDockingFusionStatusLabel.styleSheet = "color: #b00020;"
            progress.close()
            slicer.util.errorDisplay(str(exc))
        finally:
            progress.close()
            self._workflowActionBusy = False

    def _inspectTemplatePreset(self, presetKey: str) -> None:
        if not self._parameterNode or not self.logic:
            return
        self._applyWorkflowViewPreset(presetKey)
        self.onFrameWorkflowView()

    def onInspectTemplateFit(self) -> None:
        self._inspectTemplatePreset("undercut_analysis")

    def onInspectShellAndGuides(self) -> None:
        self._inspectTemplatePreset("shell_guides")

    def onInspectUnifiedTemplate(self) -> None:
        self._inspectTemplatePreset("final_only")

    def onDeleteFinalPrintableTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        finalModel = self._parameterNode.finalPrintableTemplateModel
        if not self.logic.isFinalPrintableTemplateModelNode(finalModel):
            slicer.util.errorDisplay(_("Select the DENTOBOT unified template to delete."))
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the unified template and its docking, clearance, reinforcement, "
                "and channel provenance models? The patient-contact shell, trajectories, "
                "and authoritative segmentation are preserved."
            ),
            windowTitle=_("Delete unified printable template"),
        ):
            return
        try:
            removals = self.logic.deleteFinalPrintableTemplate(finalModel)
            logging.info(
                "Deleted unified template subtree containing %d nodes",
                len(removals),
            )
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def _deleteFinalPrintableTemplateCascade(self) -> list[dict]:
        finalModel = (
            self._parameterNode.finalPrintableTemplateModel
            if self._parameterNode
            else None
        )
        if not self.logic.isFinalPrintableTemplateModelNode(finalModel):
            return []
        return self.logic.deleteFinalPrintableTemplate(finalModel)
