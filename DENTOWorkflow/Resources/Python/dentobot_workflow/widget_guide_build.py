"""Extracted guide build and finalization UI methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.widget_template_build import TemplateBuildWidgetMixin


from dentobot_workflow.widget_template_finalization import TemplateFinalizationWidgetMixin


class GuideBuildWidgetMixin(TemplateFinalizationWidgetMixin, TemplateBuildWidgetMixin):






























    def _createOrUpdatePatientContactShell(self):
        if not self._parameterNode or not self.logic:
            raise RuntimeError(_("DENTOWorkflow is not ready."))
        shellModel, details = self.logic.createOrUpdatePatientContactShell(
            self._parameterNode.draftTemplateSupportModel,
            self._parameterNode.visibleTemplateSupportModel,
            self._parameterNode.templateInsertionDirection,
            self._parameterNode.templateUndercutBlockoutModel,
            clearanceMm=self._parameterNode.templateShellClearanceMm,
            thicknessMm=self._parameterNode.templateShellThicknessMm,
            samplingSpacingMm=self._parameterNode.templateSamplingSpacingMm,
            blockoutSafetyMm=self._parameterNode.templateBlockoutSafetyMm,
            voxelClosingMm=self._parameterNode.templateShellVoxelClosingMm,
            shellModel=self._parameterNode.patientContactShellModel,
        )
        self._parameterNode.patientContactShellModel = shellModel
        self.logic.markFinalPrintableTemplateStale(
            self._parameterNode.finalPrintableTemplateModel,
            _("The patient-contact shell was regenerated."),
        )
        logging.info(
            "Generated patient-contact shell %s with %d triangles and %d component(s)",
            shellModel.GetID(),
            details["metrics"]["triangleCount"],
            details["metrics"]["surfaceRegionCount"],
        )
        self._updateTemplateGuide()
        self.ui.templateDockingFusionGroupBox.collapsed = False
        return shellModel, details

    def onGeneratePatientContactShell(self) -> None:
        """Advanced staged action: regenerate only the cached patient shell."""

        if not self._parameterNode or not self.logic:
            return
        try:
            self._createOrUpdatePatientContactShell()
        except (RuntimeError, ValueError) as exc:
            self.ui.patientContactShellStatusLabel.text = str(exc)
            self.ui.patientContactShellStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onDeletePatientContactShell(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        shellModel = self._parameterNode.patientContactShellModel
        if not self.logic.isPatientContactShellModelNode(shellModel):
            slicer.util.errorDisplay(
                _("Select a DENTOBOT patient-contact shell to delete.")
            )
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the patient-contact shell and its owned boundary-bridge/"
                "Margin/Hollow processing nodes? The visible support boundary, "
                "preview, full support anatomy, and authoritative segmentation "
                "will be preserved."
            ),
            windowTitle=_("Delete patient-contact shell"),
        ):
            return
        try:
            self._deleteFinalPrintableTemplateCascade()
            removals = self.logic.deletePatientContactShell(shellModel)
            self._parameterNode.patientContactShellModel = None
            logging.info(
                "Deleted patient-contact shell subtree containing %d nodes",
                len(removals),
            )
            self._updateTemplateGuide()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onCreateTemplateShellRoi(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            roiNode = self.logic.createOrResetTemplateShellRoi(
                self._parameterNode.draftTemplateSupportModel,
                self._parameterNode.templateShellRoi,
            )
            self._parameterNode.templateShellRoi = roiNode
            self._updateTemplateGuide()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onDeleteTemplateShellRoi(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        roiNode = self._parameterNode.templateShellRoi
        try:
            self.logic.validateTemplateShellRoiForDeletion(roiNode)
        except ValueError as exc:
            slicer.util.errorDisplay(str(exc))
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Permanently delete the Step 5B automatic shell bounds ROI? Existing "
                "shell and sleeve outputs will be kept but marked stale. "
                "The Step 4B support draft, trajectory, and dimensions will be kept "
                "so a fresh ROI can be created."
            ),
            windowTitle=_("Delete Step 5B automatic shell bounds ROI"),
        ):
            return
        try:
            removal = self.logic.deleteTemplateShellRoi(roiNode)
            self._parameterNode.templateShellRoi = None
            self.logic.markResearchTemplateModelsStale(
                self._parameterNode.researchTemplateShellModel,
                self._parameterNode.researchTemplateSleeveModel,
                _("Automatic shell bounds ROI was deleted."),
            )
            logging.info(
                "Deleted DENTOBOT Step 5B shell ROI %s and %d owned auxiliary nodes",
                removal["nodeId"],
                len(removal["auxiliaryNodeIds"]),
            )
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onGenerateResearchTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        parameters = self._templateGuideParameters()
        try:
            roiNode = self.logic.createOrResetTemplateShellRoi(
                self._parameterNode.draftTemplateSupportModel,
                self._parameterNode.templateShellRoi,
            )
            self._parameterNode.templateShellRoi = roiNode
            shellModel, sleeveModel, details = self.logic.createOrUpdateResearchTemplate(
                self._parameterNode.draftTemplateSupportModel,
                self._parameterNode.trajectoryLine,
                roiNode,
                clearanceMm=parameters["clearanceMm"],
                thicknessMm=parameters["thicknessMm"],
                samplingSpacingMm=parameters["samplingSpacingMm"],
                channelDiameterMm=parameters["channelDiameterMm"],
                sleeveOuterDiameterMm=parameters["sleeveOuterDiameterMm"],
                sleeveInnerDiameterMm=parameters["sleeveInnerDiameterMm"],
                sleeveHeightMm=parameters["sleeveHeightMm"],
                shellModelNode=self._parameterNode.researchTemplateShellModel,
                sleeveModelNode=self._parameterNode.researchTemplateSleeveModel,
            )
            self._parameterNode.researchTemplateShellModel = shellModel
            self._parameterNode.researchTemplateSleeveModel = sleeveModel
            logging.info(
                "Generated DENTOBOT Step 5B shell (%d triangles) and sleeve (%d triangles)",
                details["shell"]["triangleCount"],
                details["sleeve"]["triangleCount"],
            )
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            self.ui.templateGuideStatusLabel.text = str(exc)
            self.ui.templateGuideStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onDeleteResearchTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Permanently delete the DENTOBOT Step 5B shell and sleeve? "
                "Any dependent Step 5C plane, curve, finalized shell, and Dynamic "
                "Modeler auxiliaries will also be deleted. The Step 4B support draft, "
                "trajectory, ROI, and dimensions will be kept."
            ),
            windowTitle=_("Delete Step 5B research template"),
        ):
            return
        try:
            if (
                self._parameterNode.templateTrimPlane
                or self._parameterNode.templateTrimCurve
                or self._parameterNode.finalizedTemplateShellModel
            ):
                self.logic.deleteTemplateFinalization(
                    self._parameterNode.templateTrimPlane,
                    self._parameterNode.templateTrimCurve,
                    self._parameterNode.finalizedTemplateShellModel,
                )
                self._parameterNode.templateTrimPlane = None
                self._parameterNode.templateTrimCurve = None
                self._parameterNode.finalizedTemplateShellModel = None
            removals = self.logic.deleteResearchTemplateModels(
                self._parameterNode.researchTemplateShellModel,
                self._parameterNode.researchTemplateSleeveModel,
            )
            self._parameterNode.researchTemplateShellModel = None
            self._parameterNode.researchTemplateSleeveModel = None
            logging.info(
                "Deleted %d DENTOBOT Step 5B model nodes",
                len(removals),
            )
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))









































