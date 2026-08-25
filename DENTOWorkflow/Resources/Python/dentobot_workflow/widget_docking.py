"""Extracted target docking controls methods; public APIs remain on PlanningWidgetMixin."""

from __future__ import annotations

from .runtime import *


class DockingWidgetMixin:
    def _targetDockingParameters(self) -> dict:
        if not self._parameterNode:
            raise ValueError(_("DENTOWorkflow has no active parameter node."))
        return normalize_target_docking_parameters(
            pattern_radius_mm=self._parameterNode.targetDockingPatternRadiusMm,
            outer_diameter_mm=self._parameterNode.targetDockingOuterDiameterMm,
            bore_diameter_mm=self._parameterNode.targetDockingBoreDiameterMm,
            connector_diameter_mm=(
                self._parameterNode.targetDockingConnectorDiameterMm
            ),
            connector_thickness_mm=(
                self._parameterNode.targetDockingConnectorThicknessMm
            ),
            shared_depth_mm=self._parameterNode.targetDockingSharedDepthMm,
            individual_depths_mm=(
                self._parameterNode.targetDockingDepth1Mm,
                self._parameterNode.targetDockingDepth2Mm,
                self._parameterNode.targetDockingDepth3Mm,
                self._parameterNode.targetDockingDepth4Mm,
            ),
            individual_depths_enabled=(
                self._parameterNode.targetDockingIndividualDepthsEnabled
            ),
            yaw_deg=self._parameterNode.targetDockingYawDeg,
            collision_clearance_mm=(
                self._parameterNode.targetDockingCollisionClearanceMm
            ),
            clearance_mm=self._parameterNode.templateDockingClearanceMm,
            reinforcement_radial_mm=(
                self._parameterNode.templateReinforcementRadialMm
            ),
            processing_resolution_mm=(
                self._parameterNode.templateSamplingSpacingMm
            ),
        )

    def _updateTargetDocking(self) -> None:
        if self._updatingTargetDockingUI or not hasattr(self, "ui"):
            return
        if not self._parameterNode or not self.logic:
            self.ui.generateTargetDockingAssemblyButton.enabled = False
            self.ui.deleteTargetDockingAssemblyButton.enabled = False
            self.ui.targetDockingTrajectorySummaryLabel.text = _("--")
            return
        individual = bool(
            self._parameterNode.targetDockingIndividualDepthsEnabled
        )
        self.ui.targetDockingIndividualDepthsWidget.visible = individual
        self.ui.targetDockingSharedDepthSpinBox.enabled = not individual
        planeNode = self._parameterNode.targetDockingReferencePlane
        assemblyModel = self._parameterNode.targetDockingAssemblyModel
        desiredYaw = int(round(float(self._parameterNode.targetDockingYawDeg)))
        self._updatingTargetDockingUI = True
        try:
            if int(self.ui.targetDockingYawSlider.value) != desiredYaw:
                self.ui.targetDockingYawSlider.value = desiredYaw
            self.ui.targetDockingYawValueLabel.text = f"{desiredYaw}°"
            if self.ui.targetDockingReferencePlaneSelector.currentNode() is not planeNode:
                self.ui.targetDockingReferencePlaneSelector.setCurrentNode(planeNode)
            if self.ui.targetDockingAssemblyModelSelector.currentNode() is not assemblyModel:
                self.ui.targetDockingAssemblyModelSelector.setCurrentNode(assemblyModel)
        finally:
            self._updatingTargetDockingUI = False

        inputError = ""
        trajectories = []
        parameters = None
        supportSummary = None
        try:
            segmentationNode = self._parameterNode.teethSegmentation
            targetSegmentId = self._parameterNode.targetToothSegmentId
            self.logic.validateTargetTooth(segmentationNode, targetSegmentId)
            if self.logic.getSegmentationReviewState(segmentationNode) != "Reviewed":
                raise ValueError(_("Mark the authoritative segmentation Reviewed first."))
            trajectories = self.logic.targetDockingTrajectoriesForTarget(
                segmentationNode,
                targetSegmentId,
            )
            supportSummary = self.logic.getDraftTemplateSupportModelSummary(
                self._parameterNode.draftTemplateSupportModel
            )
            if supportSummary["geometryState"] != "Current":
                raise ValueError(_("Update the stale Step 4B support draft first."))
            if supportSummary["sourceSegmentation"] is not segmentationNode:
                raise ValueError(_("The Step 4B support draft uses another segmentation."))
            if supportSummary["targetSegmentId"] != targetSegmentId:
                raise ValueError(_("The Step 4B support draft uses another target tooth."))
            parameters = self._targetDockingParameters()
        except (RuntimeError, ValueError) as exc:
            inputError = str(exc)
        self.ui.targetDockingTrajectorySummaryLabel.text = (
            ", ".join(node.GetName() or _("Unnamed") for node in trajectories)
            if trajectories
            else _("--")
        )
        self._bindSelectedGuideTrajectoryNodes(trajectories)

        summary = None
        outputError = ""
        if assemblyModel:
            try:
                summary = self.logic.getTargetDockingAssemblySummary(assemblyModel)
                trajectoryGeometry = []
                for node in trajectories:
                    trajectorySummary = self.logic.getTrajectorySummary(node)
                    trajectoryGeometry.append(
                        {
                            "entryRas": [
                                float(value)
                                for value in trajectorySummary["entryRas"]
                            ],
                            "targetRas": [
                                float(value)
                                for value in trajectorySummary["targetRas"]
                            ],
                        }
                    )
                staleReason = ""
                if inputError:
                    staleReason = inputError
                elif summary["segmentation"] is not self._parameterNode.teethSegmentation:
                    staleReason = _("The authoritative segmentation changed.")
                elif summary["targetSegmentId"] != self._parameterNode.targetToothSegmentId:
                    staleReason = _("The target tooth changed.")
                elif summary["trajectories"] != trajectories:
                    staleReason = _("The target trajectory set changed.")
                elif summary.get("supportModel") is not self._parameterNode.draftTemplateSupportModel:
                    staleReason = _("The Step 4B support-anatomy draft changed.")
                elif summary.get("supportSegmentIds") != supportSummary["supportSegmentIds"]:
                    staleReason = _("The Step 4B support-tooth selection changed.")
                elif summary.get("supportDraftUpdatedUtc") != supportSummary["updatedUtc"]:
                    staleReason = _("The Step 4B support-anatomy geometry changed.")
                elif summary["parametersJson"] != json.dumps(
                    parameters,
                    sort_keys=True,
                    separators=(",", ":"),
                ):
                    staleReason = _("A Step 4C docking dimension changed.")
                elif summary["trajectoryGeometryJson"] != json.dumps(
                    trajectoryGeometry,
                    sort_keys=True,
                    separators=(",", ":"),
                ):
                    staleReason = _("A source trajectory geometry changed.")
                if staleReason:
                    self.logic.markTargetDockingAssemblyStale(
                        assemblyModel,
                        staleReason,
                    )
                    self.logic.markFinalPrintableTemplateStale(
                        self._parameterNode.finalPrintableTemplateModel,
                        staleReason,
                    )
                    summary = self.logic.getTargetDockingAssemblySummary(
                        assemblyModel
                    )
                elif (
                    summary["geometryState"] == "Stale"
                    and summary["staleReason"]
                    in {
                        _("A Step 4C docking parameter changed."),
                        _("A source guide trajectory changed."),
                        _(
                            "The requested Step 4C yaw changed; apply it to "
                            "rebuild the draft."
                        ),
                    }
                ):
                    # Parameter-wrapper signals may fire while an MRB restores
                    # widget values. If all authoritative references, stored
                    # dimensions, and trajectory geometry still agree, the
                    # stale mark was a no-op UI synchronization artifact. The
                    # orientation remains Draft and still requires confirmation.
                    assemblyModel.SetAttribute("DENTOBOT.GeometryState", "Current")
                    assemblyModel.SetAttribute("DENTOBOT.StaleReason", None)
                    summary = self.logic.getTargetDockingAssemblySummary(
                        assemblyModel
                    )
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                outputError = str(exc)
        self.ui.generateTargetDockingAssemblyButton.enabled = bool(
            trajectories and parameters and supportSummary and not outputError
        )
        self.ui.deleteTargetDockingAssemblyButton.enabled = bool(
            self.logic.isTargetDockingAssemblyModelNode(assemblyModel)
        )
        isCurrent = bool(summary and summary["geometryState"] == "Current")
        isConfirmed = bool(
            isCurrent and summary.get("orientationState") == "Confirmed"
        )
        self._parameterNode.targetDockingYawConfirmed = isConfirmed
        self.ui.applyTargetDockingYawButton.enabled = bool(
            trajectories
            and parameters
            and not outputError
            and self.logic.isTargetDockingAssemblyModelNode(assemblyModel)
        )
        self.ui.confirmTargetDockingYawButton.enabled = isCurrent
        self.ui.targetDockingOrientationStateLabel.text = (
            _("CONFIRMED — dock orientation may enter Step 5B fusion")
            if isConfirmed
            else _("DRAFT — inspect, adjust yaw if needed, then confirm")
        )
        self.ui.targetDockingOrientationStateLabel.styleSheet = (
            "color: #207227; font-weight: 700;"
            if isConfirmed
            else "color: #b36b00; font-weight: 700;"
        )
        if summary:
            collisionScreen = summary["metrics"].get("collisionScreen") or {}
            autoYawSearch = summary["metrics"].get("autoYawSearch") or {}
            collisionCount = int(collisionScreen.get("collidingDockCount", 0))
            obstacleCount = int(collisionScreen.get("obstacleSurfaceCount", 0))
            freeCandidates = autoYawSearch.get("collisionFreeCandidateCount")
            autoSuffix = (
                _("; %1 collision-free sweep candidate(s)").replace(
                    "%1", str(freeCandidates)
                )
                if freeCandidates is not None
                else ""
            )
            omittedCount = len(summary.get("omittedObstacleSegmentIds") or [])
            omittedSuffix = (
                _("; WARNING: %1 same-jaw tooth surface(s) could not be screened")
                .replace("%1", str(omittedCount))
                if omittedCount
                else ""
            )
            self.ui.targetDockingAutoYawStatusLabel.text = (
                _(
                    "Yaw %1° screened against %2 other same-jaw whole-tooth "
                    "surface(s): %3 dock collision(s)%4%5. Draft screen only."
                )
                .replace("%1", f"{float(summary['metrics'].get('yawDeg', 0.0)):.1f}")
                .replace("%2", str(obstacleCount))
                .replace("%3", str(collisionCount))
                .replace("%4", autoSuffix)
                .replace("%5", omittedSuffix)
            )
            self.ui.targetDockingAutoYawStatusLabel.styleSheet = (
                "color: #207227;" if not collisionCount and not omittedCount
                else "color: #b36b00;"
            )
        else:
            self.ui.targetDockingAutoYawStatusLabel.text = _(
                "Generate a draft to calculate yaw against all other "
                "same-jaw whole-tooth surfaces."
            )
            self.ui.targetDockingAutoYawStatusLabel.styleSheet = "color: #1f5f99;"
        if outputError:
            message, style = outputError, "color: #b00020;"
        elif inputError:
            message, style = inputError, "color: #b36b00;"
        elif isCurrent:
            message = _(
                "Four independent docks are current at yaw %1°: top/opening "
                "faces on the target-crown occlusal plane, %2 mm radius, %3 mm "
                "bore, maximum face-plane residual %4 mm. %5"
            ).replace("%1", f"{parameters['yawDeg']:.1f}").replace(
                "%2", f"{parameters['patternRadiusMm']:.2f}"
            ).replace(
                "%3",
                f"{parameters['boreDiameterMm']:.2f}",
            ).replace(
                "%4",
                f"{summary['metrics'].get('topPlaneMaxResidualMm', 0.0):.4f}",
            ).replace(
                "%5",
                _("Orientation confirmed.")
                if isConfirmed
                else _("Draft orientation still requires confirmation."),
            )
            style = "color: #207227;" if isConfirmed else "color: #b36b00;"
        elif summary:
            message = _("Step 4C assembly is stale: %1").replace(
                "%1",
                summary["staleReason"] or _("regeneration required"),
            )
            style = "color: #b36b00;"
        else:
            message = _(
                "Ready to generate four independent occlusal-plane docks from the locked trajectory set."
            )
            style = "color: #1f5f99;"
        self.ui.targetDockingStatusLabel.text = message
        self.ui.targetDockingStatusLabel.styleSheet = style

    def onTargetDockingInputChanged(self, *args) -> None:
        del args
        if (
            self._updatingTargetDockingUI
            or self._updatingFromParameterNode
            or not self._parameterNode
            or not self.logic
        ):
            return
        reason = _("A Step 4C docking parameter changed.")
        assemblyModel = self._parameterNode.targetDockingAssemblyModel
        if self.logic.isTargetDockingAssemblyModelNode(assemblyModel):
            try:
                storedParametersJson = (
                    assemblyModel.GetAttribute("DENTOBOT.ParametersJson") or ""
                )
                currentParametersJson = json.dumps(
                    self._targetDockingParameters(),
                    sort_keys=True,
                    separators=(",", ":"),
                )
            except (RuntimeError, ValueError):
                storedParametersJson = ""
                currentParametersJson = "invalid"
            if storedParametersJson == currentParametersJson:
                qt.QTimer.singleShot(0, self._updateTargetDocking)
                return
        self._parameterNode.targetDockingYawConfirmed = False
        for node in (
            self._parameterNode.targetDockingAssemblyModel,
            self._parameterNode.targetDockingReferencePlane,
        ):
            if node:
                node.SetAttribute("DENTOBOT.OrientationState", "Draft")
                node.SetAttribute("DENTOBOT.OrientationConfirmedUtc", None)
        self.logic.markTargetDockingAssemblyStale(
            self._parameterNode.targetDockingAssemblyModel,
            reason,
        )
        self.logic.markFinalPrintableTemplateStale(
            self._parameterNode.finalPrintableTemplateModel,
            reason,
        )
        qt.QTimer.singleShot(0, self._updateTargetDocking)

    def onTargetDockingYawChanged(self, value: int) -> None:
        if (
            self._updatingTargetDockingUI
            or self._updatingFromParameterNode
            or not self._parameterNode
            or not self.logic
        ):
            return
        yaw = float(value)
        self.ui.targetDockingYawValueLabel.text = f"{int(value)}°"
        assemblyModel = self._parameterNode.targetDockingAssemblyModel
        planeNode = self._parameterNode.targetDockingReferencePlane
        storedParameters = {}
        if self.logic.isTargetDockingAssemblyModelNode(assemblyModel):
            try:
                storedParameters = json.loads(
                    assemblyModel.GetAttribute("DENTOBOT.ParametersJson") or "{}"
                )
            except json.JSONDecodeError:
                storedParameters = {}
        # Parameter-node binding can deliver a queued slider signal after the
        # explicit synchronization guard has ended.  A value that agrees with
        # both the restored parameter and the persisted docking provenance is
        # not an operator edit and must not invalidate confirmed orientation.
        if math.isclose(
            float(self._parameterNode.targetDockingYawDeg),
            yaw,
            abs_tol=1e-9,
        ) and math.isclose(
            float(storedParameters.get("yawDeg", math.inf)),
            yaw,
            abs_tol=1e-9,
        ):
            qt.QTimer.singleShot(0, self._updateTargetDocking)
            return
        self._parameterNode.targetDockingYawDeg = yaw
        self._parameterNode.targetDockingYawConfirmed = False
        for node in (assemblyModel, planeNode):
            if node:
                node.SetAttribute("DENTOBOT.OrientationState", "Draft")
                node.SetAttribute("DENTOBOT.OrientationConfirmedUtc", None)
        if self.logic.isTargetDockingAssemblyModelNode(assemblyModel):
            if not math.isclose(
                float(storedParameters.get("yawDeg", math.inf)),
                yaw,
                abs_tol=1e-9,
            ):
                reason = _(
                    "The requested Step 4C yaw changed; apply it to rebuild the draft."
                )
                self.logic.markTargetDockingAssemblyStale(assemblyModel, reason)
                self.logic.markFinalPrintableTemplateStale(
                    self._parameterNode.finalPrintableTemplateModel,
                    reason,
                )
        qt.QTimer.singleShot(0, self._updateTargetDocking)

    def _regenerateTargetDocking(self, *, autoSelectYaw: bool) -> None:
        trajectories = self.logic.targetDockingTrajectoriesForTarget(
            self._parameterNode.teethSegmentation,
            self._parameterNode.targetToothSegmentId,
        )
        planeNode, assemblyModel, details = (
            self.logic.createOrUpdateTargetDockingAssembly(
                self._parameterNode.teethSegmentation,
                self._parameterNode.targetToothSegmentId,
                trajectories,
                self._targetDockingParameters(),
                supportModel=self._parameterNode.draftTemplateSupportModel,
                planeNode=self._parameterNode.targetDockingReferencePlane,
                assemblyModel=self._parameterNode.targetDockingAssemblyModel,
                autoSelectYaw=autoSelectYaw,
                measurementsVisible=(
                    self._parameterNode.targetDockingMeasurementsVisible
                ),
            )
        )
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.targetDockingReferencePlane = planeNode
            self._parameterNode.targetDockingAssemblyModel = assemblyModel
            self._parameterNode.targetDockingYawDeg = float(
                details["parameters"]["yawDeg"]
            )
            self._parameterNode.targetDockingYawConfirmed = False
        finally:
            self._parameterNode.EndModify(wasModifying)
        self.logic.markFinalPrintableTemplateStale(
            self._parameterNode.finalPrintableTemplateModel,
            _("The Step 4C docking assembly was regenerated."),
        )
        logging.info(
            "Generated Step 4C four-dock draft %s at yaw %.1f degrees "
            "with %d docks and %d screened collisions",
            assemblyModel.GetID(),
            float(details["parameters"]["yawDeg"]),
            details["metrics"]["dockCount"],
            int(
                details["metrics"].get("collisionScreen", {}).get(
                    "collidingDockCount", 0
                )
            ),
        )
        self._updateTargetDocking()
        self._updateTemplateGuide()

    def onApplyTargetDockingYaw(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            self._regenerateTargetDocking(autoSelectYaw=False)
        except (RuntimeError, ValueError) as exc:
            self.ui.targetDockingStatusLabel.text = str(exc)
            self.ui.targetDockingStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onConfirmTargetDockingYaw(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        assemblyModel = self._parameterNode.targetDockingAssemblyModel
        try:
            summary = self.logic.getTargetDockingAssemblySummary(assemblyModel)
            if summary["geometryState"] != "Current":
                raise ValueError(_("Apply or regenerate the stale Step 4C draft first."))
            expectedParametersJson = json.dumps(
                self._targetDockingParameters(),
                sort_keys=True,
                separators=(",", ":"),
            )
            if summary["parametersJson"] != expectedParametersJson:
                raise ValueError(
                    _("Apply the current docking dimensions and yaw before confirmation.")
                )
            collisionScreen = summary["metrics"].get("collisionScreen") or {}
            collisionCount = int(collisionScreen.get("collidingDockCount", 0))
            omittedCount = len(summary.get("omittedObstacleSegmentIds") or [])
            if (collisionCount or omittedCount) and not slicer.util.confirmYesNoDisplay(
                _(
                    "This draft reports %1 colliding dock(s), and %2 same-jaw "
                    "tooth surface(s) were omitted from screening. The screen "
                    "uses sampled segmentation surfaces and is not clinical "
                    "collision validation. Confirm this orientation anyway?"
                )
                .replace("%1", str(collisionCount))
                .replace("%2", str(omittedCount)),
                windowTitle=_("Confirm Step 4C draft orientation"),
            ):
                return
            timestamp = datetime.now(timezone.utc).isoformat()
            for node in (assemblyModel, summary["plane"]):
                node.SetAttribute("DENTOBOT.OrientationState", "Confirmed")
                node.SetAttribute("DENTOBOT.OrientationConfirmedUtc", timestamp)
            self._parameterNode.targetDockingYawConfirmed = True
            self.logic.markFinalPrintableTemplateStale(
                self._parameterNode.finalPrintableTemplateModel,
                _("The Step 4C dock orientation confirmation changed."),
            )
            self._updateTargetDocking()
            self._updateTemplateGuide()
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onTargetDockingMeasurementsVisibilityChanged(self, visible: bool) -> None:
        if self._updatingTargetDockingUI or not self._parameterNode:
            return
        self._parameterNode.targetDockingMeasurementsVisible = bool(visible)
        assemblyModel = self._parameterNode.targetDockingAssemblyModel
        if assemblyModel:
            role = self.logic.TARGET_DOCKING_MEASUREMENT_REFERENCE_ROLE
            for index in range(assemblyModel.GetNumberOfNodeReferences(role)):
                node = assemblyModel.GetNthNodeReference(role, index)
                displayNode = node.GetDisplayNode() if node else None
                if displayNode:
                    displayNode.SetVisibility(bool(visible))
                    displayNode.SetVisibility2D(bool(visible))
                    displayNode.SetVisibility3D(bool(visible))
        self._refreshWorkflowViewAfterStateChange()

    def onTargetDockingReferencePlaneSelectionChanged(self, planeNode) -> None:
        if self._updatingTargetDockingUI or not self._parameterNode:
            return
        self._parameterNode.targetDockingReferencePlane = planeNode
        self._updateTargetDocking()

    def onTargetDockingAssemblySelectionChanged(self, assemblyModel) -> None:
        if self._updatingTargetDockingUI or not self._parameterNode:
            return
        self._parameterNode.targetDockingAssemblyModel = assemblyModel
        self._updateTargetDocking()

    def onGenerateTargetDockingAssembly(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            self._regenerateTargetDocking(autoSelectYaw=True)
        except (RuntimeError, ValueError) as exc:
            self.ui.targetDockingStatusLabel.text = str(exc)
            self.ui.targetDockingStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onDeleteTargetDockingAssembly(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        assemblyModel = self._parameterNode.targetDockingAssemblyModel
        if not self.logic.isTargetDockingAssemblyModelNode(assemblyModel):
            slicer.util.errorDisplay(_("Select the DENTOBOT Step 4C assembly."))
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the Step 4C four-dock assembly and reference plane? "
                "Any integrated Step 5B final template will also be deleted. "
                "The segmentation and trajectories are preserved."
            ),
            windowTitle=_("Delete Step 4C docking assembly"),
        ):
            return
        try:
            self._deleteFinalPrintableTemplateCascade()
            removals = self.logic.deleteTargetDockingAssembly(assemblyModel)
            logging.info("Deleted Step 4C docking subtree containing %d nodes", len(removals))
            self._updateTargetDocking()
            self._updateTemplateGuide()
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))
