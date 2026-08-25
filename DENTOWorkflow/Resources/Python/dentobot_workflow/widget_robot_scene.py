"""Extracted robot scene and jaw setup methods; public APIs remain on RobotWidgetMixin."""

from __future__ import annotations

from .runtime import *


class RobotSceneWidgetMixin:
    def _clearRobotPlacement(self) -> None:
        if not hasattr(self, "ui"):
            return
        self._bindRobotPlacementNodes(None, None)
        self._disableRobotKeyboardShortcuts()
        self._updatingRobotPlacementUI = True
        try:
            self.ui.robotBaseTransformSelector.setCurrentNode(None)
            self.ui.robotMountPlaneSelector.setCurrentNode(None)
            self.ui.robotPlacementStatusLabel.text = _(
                "Load the seven articulated robot meshes to begin placement."
            )
            self.ui.robotPlacementStatusLabel.styleSheet = "color: #b36b00;"
        finally:
            self._updatingRobotPlacementUI = False

    def _updateDraftPhantomStatus(self, message: str = "", error: bool = False) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        if message:
            self.ui.draftOpenMouthStatusLabel.text = message
            self.ui.draftOpenMouthStatusLabel.styleSheet = (
                "color: #b00020;" if error else "color: #207227;"
            )
            return
        transform = self._parameterNode.draftJawTransform
        if self.logic.isDraftJawTransformNode(transform):
            angle = transform.GetAttribute("DENTOBOT.HingeAngleDeg") or "--"
            gap = transform.GetAttribute("DENTOBOT.AchievedIncisorGapMm") or "--"
            self.ui.draftOpenMouthStatusLabel.text = _(
                "Draft mouth open: pure TMJ hinge rotation %1°, measured incisor gap %2 mm."
            ).replace("%1", angle).replace("%2", gap)
            self.ui.draftOpenMouthStatusLabel.styleSheet = "color: #207227;"
        elif self.logic.draftPhantomModelNodes():
            pointCount = (
                self._parameterNode.draftJawLandmarks.GetNumberOfDefinedControlPoints()
                if self.logic.isDraftJawLandmarksNode(
                    self._parameterNode.draftJawLandmarks
                )
                else 0
            )
            self.ui.draftOpenMouthStatusLabel.text = _(
                "Draft phantom loaded. Jaw landmarks placed: %1/4."
            ).replace("%1", str(pointCount))
            self.ui.draftOpenMouthStatusLabel.styleSheet = "color: #b36b00;"
        else:
            self.ui.draftOpenMouthStatusLabel.text = _(
                "Load the local generic phantom to begin."
            )
            self.ui.draftOpenMouthStatusLabel.styleSheet = "color: #b36b00;"

    def _bindStep6CaseJawLandmarksNode(
        self,
        landmarksNode: vtkMRMLMarkupsFiducialNode | None,
    ) -> None:
        if landmarksNode is self._step6CaseJawLandmarksNode:
            return
        if self._step6CaseJawLandmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.removeObserver(
                    self._step6CaseJawLandmarksNode,
                    landmarkEvent,
                    self._onStep6CaseJawLandmarksModified,
                )
        self._step6CaseJawLandmarksNode = landmarksNode
        if landmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.addObserver(
                    landmarksNode,
                    landmarkEvent,
                    self._onStep6CaseJawLandmarksModified,
                )

    def _markStep6CaseJawOpeningStale(self, reason: str) -> None:
        if not self._parameterNode or not self.logic:
            return
        transform = self._parameterNode.step6CaseJawTransform
        if self.logic.isStep6CaseJawTransformNode(transform):
            transform.SetAttribute("DENTOBOT.GeometryState", "Stale")
            transform.SetAttribute("DENTOBOT.StaleReason", reason)
        model = self._parameterNode.step6OpenedLowerJawModel
        if self.logic.isStep6OpenedLowerJawModelNode(model):
            model.SetAttribute("DENTOBOT.GeometryState", "Stale")
        self.logic.invalidateStep6TaskConfirmation(
            self._parameterNode,
            reason,
            makeBaseStale=True,
        )
        self.logic.deleteRobotWorkspaceModel()
        self._step6MotionPlan = None
        if self._robotWorkflowFacade:
            self._robotWorkflowFacade.clearTransientState()

    def _onStep6CaseJawLandmarksModified(self, caller=None, event=None) -> None:
        del caller, event
        if (
            self._updatingStep6CaseJawLandmarks
            or not self._parameterNode
            or not self.logic
        ):
            return
        node = self._step6CaseJawLandmarksNode
        if not node or not self.logic.isStep6CaseJawLandmarksNode(node):
            return
        self._updatingStep6CaseJawLandmarks = True
        try:
            summary = self.logic.getStep6CaseJawLandmarkSummary(node)
        except ValueError:
            return
        finally:
            self._updatingStep6CaseJawLandmarks = False
        if self.logic.isStep6CaseJawTransformNode(
            self._parameterNode.step6CaseJawTransform
        ):
            self._markStep6CaseJawOpeningStale(
                _("Case jaw landmarks changed; apply the mouth opening again.")
            )
        if summary["isComplete"]:
            self.logic.stopTrajectoryPlacement()
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def _updateStep6CaseJawOpeningControls(self) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        imported = bool(self._parameterNode.step6PlanningContextImported)
        blocked = bool(
            self._parameterNode.robotBaseMountLocked
            or self.logic.isRos2MotionControlActive(
                self._parameterNode.robotBaseTransform
            )
        )
        node = self._parameterNode.step6CaseJawLandmarks
        summary = None
        if node and self.logic.isStep6CaseJawLandmarksNode(node):
            try:
                summary = self.logic.getStep6CaseJawLandmarkSummary(node)
            except ValueError:
                summary = None
        pointCount = summary["definedPointCount"] if summary else 0
        complete = bool(summary and summary["isComplete"])
        labels = self.logic.draftJawLandmarkButtonLabels()
        self._updatingRobotPlacementUI = True
        try:
            self.ui.step6CaseJawOpeningGroupBox.enabled = imported
            self.ui.createStep6CaseJawLandmarksButton.enabled = bool(
                imported and not blocked and not complete
            )
            self.ui.createStep6CaseJawLandmarksButton.text = (
                labels[pointCount]
                if pointCount < len(labels)
                else _("All landmarks placed")
            )
            self.ui.clearStep6CaseJawLandmarksButton.enabled = bool(
                imported and not blocked and pointCount > 0
            )
            self.ui.applyStep6CaseJawOpeningButton.enabled = bool(
                imported and not blocked and complete
            )
            self.ui.resetStep6CaseJawOpeningButton.enabled = bool(
                imported
                and not blocked
                and (
                    self.logic.isStep6CaseJawTransformNode(
                        self._parameterNode.step6CaseJawTransform
                    )
                    or self.logic.isStep6OpenedLowerJawModelNode(
                        self._parameterNode.step6OpenedLowerJawModel
                    )
                )
            )
        finally:
            self._updatingRobotPlacementUI = False

    def _updateStep6CaseJawOpeningStatus(
        self,
        message: str = "",
        error: bool = False,
    ) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        if message:
            self.ui.step6CaseJawOpeningStatusLabel.text = message
            self.ui.step6CaseJawOpeningStatusLabel.styleSheet = (
                "color: #b00020;" if error else "color: #207227;"
            )
            return
        if not self._parameterNode.step6PlanningContextImported:
            text = _("Import the Steps 0–5 planning package first.")
            style = "color: #b36b00;"
        else:
            issues = self.logic.step6CaseJawOpeningFreshnessIssues(
                self._parameterNode
            )
            if issues:
                node = self._parameterNode.step6CaseJawLandmarks
                pointCount = (
                    node.GetNumberOfDefinedControlPoints()
                    if self.logic.isStep6CaseJawLandmarksNode(node)
                    else 0
                )
                text = (
                    _("Case jaw landmarks placed: %1/4. %2")
                    .replace("%1", str(pointCount))
                    .replace("%2", " ".join(issues))
                )
                style = "color: #b36b00;"
            else:
                transform = self._parameterNode.step6CaseJawTransform
                angle = transform.GetAttribute("DENTOBOT.HingeAngleDeg") or "--"
                gap = transform.GetAttribute("DENTOBOT.AchievedIncisorGapMm") or "--"
                model = self._parameterNode.step6OpenedLowerJawModel
                try:
                    movingCount = len(
                        json.loads(
                            model.GetAttribute("DENTOBOT.MovingSegmentIdsJson") or "[]"
                        )
                    )
                except (TypeError, json.JSONDecodeError):
                    movingCount = 0
                text = _(
                    "Case mouth open: TMJ hinge rotation %1°, measured incisor "
                    "gap %2 mm; %3 lower-jaw surface(s) drive Step 6 collision."
                ).replace("%1", angle).replace("%2", gap).replace(
                    "%3", str(movingCount)
                )
                style = "color: #207227;"
        self.ui.step6CaseJawOpeningStatusLabel.text = text
        self.ui.step6CaseJawOpeningStatusLabel.styleSheet = style

    def onCreateStep6CaseJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            if not self._parameterNode.step6PlanningContextImported:
                raise ValueError(_("Import the Steps 0–5 planning package first."))
            node = self.logic.ensureStep6CaseJawLandmarksNode(
                self._parameterNode.step6CaseJawLandmarks
            )
            self._parameterNode.step6CaseJawLandmarks = node
            self._bindStep6CaseJawLandmarksNode(node)
            summary = self.logic.getStep6CaseJawLandmarkSummary(node)
            if summary["isComplete"]:
                return
            self.logic.startStep6CaseJawLandmarkPlacement(node)
            landmarkIndex = summary["definedPointCount"]
            self._updateStep6CaseJawOpeningStatus(
                _(
                    "Click one point in a 2D or 3D view for %1, then press the "
                    "placement button for the next landmark."
                ).replace(
                    "%1",
                    self.logic.draftJawLandmarkPlacementHints()[landmarkIndex],
                )
            )
            self._updateStep6CaseJawOpeningControls()
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onClearStep6CaseJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        node = self._parameterNode.step6CaseJawLandmarks
        if not self.logic.isStep6CaseJawLandmarksNode(node):
            return
        try:
            self.logic.stopTrajectoryPlacement()
            if (
                self._parameterNode.step6CaseJawTransform
                or self._parameterNode.step6OpenedLowerJawModel
            ):
                self.logic.resetStep6CaseJawOpening(self._parameterNode)
            self._updatingStep6CaseJawLandmarks = True
            node.RemoveAllControlPoints()
            self._updatingStep6CaseJawLandmarks = False
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _("Case jaw landmarks cleared. Place Left TMJ first.")
            )
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            self._updatingStep6CaseJawLandmarks = False
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onApplyStep6CaseJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            _transform, _model, _gapLine, summary = (
                self.logic.createOrUpdateStep6CaseJawOpening(self._parameterNode)
            )
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _(
                    "Applied case TMJ opening %1°; measured incisor gap %2 mm. "
                    "Continue to 6.1 with the opened planning anatomy."
                )
                .replace("%1", f"{summary['angleDeg']:.2f}")
                .replace("%2", f"{summary['gapMm']:.2f}")
            )
            self._applyStep6RecommendedView()
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onResetStep6CaseJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.resetStep6CaseJawOpening(self._parameterNode)
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _("Case jaw reset to the closed source pose; Step 6 is blocked.")
            )
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onStep6CaseJawTargetGapChanged(self, value: float = 0.0) -> None:
        del value
        if (
            self._updatingFromParameterNode
            or self._updatingRobotPlacementUI
            or not self._parameterNode
            or not self.logic
        ):
            return
        if self.logic.isStep6CaseJawTransformNode(
            self._parameterNode.step6CaseJawTransform
        ):
            self._markStep6CaseJawOpeningStale(
                _("Requested case incisor gap changed; apply the mouth opening again.")
            )
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def onLoadRobotModel(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.loadRobot()
        if not result.success:
            slicer.util.errorDisplay(result.message)
            return
        self._updateRobotPlacement()
        self.onFrameStep6ResearchWorkspace()
        self._applyStep6RecommendedView()
        self._updateRobotPlacementStatus(result.message)

    def onLoadDraftPhantom(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        if not self._confirmStep6SceneSwitch("phantom"):
            return
        if self._parameterNode.step6PlanningContextImported:
            self._parameterNode.step6PlanningContextImported = False
        try:
            skull, mandible, models = self.logic.createOrUpdateDraftPhantom()
            self._parameterNode.draftPhantomSkullModel = skull
            self._parameterNode.draftPhantomMandibleModel = mandible
            self.onFrameStep6ResearchWorkspace()
            if self.logic.isRobotBaseTransformNode(
                self._parameterNode.robotBaseTransform
            ):
                self.logic.positionRobotBaseNearResearchPhantom(
                    self._parameterNode.robotBaseTransform,
                    models,
                )
            self._updateRobotPlacement()
            self._applyStep6RecommendedView()
            self._updateDraftPhantomStatus(
                _(
                    "Loaded generic BodyParts3D neurocranium, maxilla, and mandible. "
                    "Place the first jaw landmark next."
                )
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onCreateDraftJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            node = self.logic.ensureDraftJawLandmarksNode(
                self._parameterNode.draftJawLandmarks
            )
            self._parameterNode.draftJawLandmarks = node
            self._bindDraftJawLandmarksNode(node)
            summary = self.logic.getDraftJawLandmarkSummary(node)
            if summary["isComplete"]:
                return
            self.logic.startDraftJawLandmarkPlacement(node)
            self._updateRobotPlacement()
            landmarkIndex = summary["definedPointCount"]
            placementHints = self.logic.draftJawLandmarkPlacementHints()
            self._updateDraftPhantomStatus(
                _(
                    "Click one point in a 3D view for %1, then pan to the next "
                    "landmark and press the button again."
                ).replace("%1", placementHints[landmarkIndex])
            )
        except (RuntimeError, ValueError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onClearDraftJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        node = self._parameterNode.draftJawLandmarks
        if not self.logic.isDraftJawLandmarksNode(node):
            return
        if node.GetNumberOfDefinedControlPoints() == 0:
            return
        try:
            self.logic.stopTrajectoryPlacement()
            self.logic.resetDraftJawOpening(
                self._parameterNode.draftPhantomMandibleModel,
                self._parameterNode.draftJawTransform,
                self._parameterNode.draftJawGapLine,
            )
            self._parameterNode.draftJawGapLine = None
            self.logic.clearDraftJawLandmarks(node)
            self._updateRobotPlacement()
            self._updateDraftPhantomStatus(
                _("Draft jaw landmarks cleared. Place the first landmark next.")
            )
        except (RuntimeError, ValueError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def _bindDraftJawLandmarksNode(
        self,
        landmarksNode: vtkMRMLMarkupsFiducialNode | None,
    ) -> None:
        if landmarksNode is self._draftJawLandmarksNode:
            return
        if self._draftJawLandmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.removeObserver(
                    self._draftJawLandmarksNode,
                    landmarkEvent,
                    self._onDraftJawLandmarksModified,
                )
        self._draftJawLandmarksNode = landmarksNode
        if landmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.addObserver(
                    landmarksNode,
                    landmarkEvent,
                    self._onDraftJawLandmarksModified,
                )

    def _onDraftJawLandmarksModified(self, caller=None, event=None) -> None:
        del caller, event
        if not self._parameterNode or not self.logic:
            return
        node = self._draftJawLandmarksNode
        if not node or not self.logic.isDraftJawLandmarksNode(node):
            return
        try:
            summary = self.logic.getDraftJawLandmarkSummary(node)
        except ValueError:
            return
        pointCount = summary["definedPointCount"]
        if pointCount >= 4:
            self.logic.stopTrajectoryPlacement()
            if not self.logic.isDraftJawTransformNode(
                self._parameterNode.draftJawTransform
            ):
                try:
                    self.onApplyDraftJawOpening()
                except (RuntimeError, ValueError) as exc:
                    self._updateDraftPhantomStatus(str(exc), error=True)
                    slicer.util.errorDisplay(str(exc))
        self._updateDraftJawLandmarkControls()
        if pointCount < 4:
            self._updateDraftPhantomStatus()

    def _updateDraftJawLandmarkControls(self, phantomLoaded: bool | None = None) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        if phantomLoaded is None:
            phantomLoaded = bool(
                self._parameterNode.draftPhantomSkullModel
                and self._parameterNode.draftPhantomMandibleModel
            )
        node = self._parameterNode.draftJawLandmarks
        summary = None
        if node and self.logic.isDraftJawLandmarksNode(node):
            try:
                summary = self.logic.getDraftJawLandmarkSummary(node)
            except ValueError:
                summary = None
        pointCount = summary["definedPointCount"] if summary else 0
        isComplete = bool(summary and summary["isComplete"])
        buttonLabels = self.logic.draftJawLandmarkButtonLabels()
        self._updatingRobotPlacementUI = True
        try:
            self.ui.createDraftJawLandmarksButton.enabled = bool(
                phantomLoaded and not isComplete
            )
            self.ui.createDraftJawLandmarksButton.text = (
                buttonLabels[pointCount]
                if pointCount < len(buttonLabels)
                else _("All landmarks placed")
            )
            self.ui.clearDraftJawLandmarksButton.enabled = bool(
                phantomLoaded and pointCount > 0
            )
            self.ui.applyDraftJawOpeningButton.enabled = bool(
                phantomLoaded and isComplete
            )
        finally:
            self._updatingRobotPlacementUI = False

    def onApplyDraftJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            transform, gapLine, summary = self.logic.createOrUpdateDraftJawOpening(
                self._parameterNode.draftPhantomMandibleModel,
                self._parameterNode.draftJawLandmarks,
                self._parameterNode.draftJawTransform,
                self._parameterNode.draftJawGapLine,
                self._parameterNode.draftJawTargetGapMm,
            )
            self._parameterNode.draftJawTransform = transform
            self._parameterNode.draftJawGapLine = gapLine
            self._updateRobotPlacement()
            self._updateDraftPhantomStatus(
                _(
                    "Draft mouth opened by pure TMJ hinge rotation %1°; measured "
                    "incisor gap %2 mm."
                )
                .replace("%1", f"{summary['angleDeg']:.2f}")
                .replace("%2", f"{summary['gapMm']:.2f}")
            )
        except (RuntimeError, ValueError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onResetDraftJaw(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        self.logic.resetDraftJawOpening(
            self._parameterNode.draftPhantomMandibleModel,
            self._parameterNode.draftJawTransform,
            self._parameterNode.draftJawGapLine,
        )
        self._parameterNode.draftJawGapLine = None
        self._updateRobotPlacement()
        self._updateDraftPhantomStatus(_("Draft mandible reset to the closed source pose."))

    def onDeleteDraftPhantom(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        removed = self.logic.deleteDraftPhantom(
            self._parameterNode.draftJawLandmarks,
            self._parameterNode.draftJawTransform,
            self._parameterNode.draftJawGapLine,
        )
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.draftPhantomSkullModel = None
            self._parameterNode.draftPhantomMandibleModel = None
            self._parameterNode.draftJawLandmarks = None
            self._parameterNode.draftJawTransform = None
            self._parameterNode.draftJawGapLine = None
        finally:
            self._parameterNode.EndModify(wasModifying)
        self._bindDraftJawLandmarksNode(None)
        self._updateRobotPlacement()
        logging.info("Deleted %d disposable draft phantom nodes", len(removed))

    def onCreateRobotMountPlane(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            planeNode = self.logic.createOrResetRobotMountPlane(
                self._parameterNode.robotMountPlane,
                self._parameterNode.robotBaseTransform,
            )
            self._parameterNode.robotMountPlane = planeNode
            try:
                slicer.modules.markups.logic().SetActiveListID(planeNode)
            except Exception:
                logging.debug("Could not make the robot mount plane active.")
            self._updateRobotPlacement()
            self._updateRobotPlacementStatus(
                _("Mount plane ready. Drag its handles, then click Snap Base to Plane.")
            )
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onSnapRobotBaseToPlane(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.snapRobotBaseToPlane(
                self._parameterNode.robotBaseTransform,
                self._parameterNode.robotMountPlane,
            )
            self._updateRobotPlacementStatus(
                _("Robot base snapped to the mount-plane origin and orientation.")
            )
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onFlipRobotMountPlane(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        planeNode = self._parameterNode.robotMountPlane
        if not self.logic.isRobotMountPlaneNode(planeNode):
            return
        normal = np.asarray(planeNode.GetNormalWorld(), dtype=float)
        planeNode.SetNormalWorld(tuple(float(value) for value in -normal))
        self._updateRobotPlacementStatus(_("Mount-plane normal flipped."))

    def _nudgeRobotBase(
        self,
        translationAxis: int | None,
        rotationAxis: int | None,
        direction: float,
    ) -> None:
        if not self._parameterNode or not self.logic:
            return
        if self._parameterNode.robotBaseMountLocked:
            return
        translation = [0.0, 0.0, 0.0]
        rotation = [0.0, 0.0, 0.0]
        if translationAxis is not None:
            translation[translationAxis] = (
                float(direction) * self._parameterNode.robotTranslationStepMm
            )
        if rotationAxis is not None:
            rotation[rotationAxis] = (
                float(direction) * self._parameterNode.robotRotationStepDeg
            )
        try:
            self.logic.nudgeRobotBase(
                self._parameterNode.robotBaseTransform,
                translationLocalMm=tuple(translation),
                rotationLocalDeg=tuple(rotation),
            )
            self._updateRobotPlacementStatus()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onRobotJointValueChanged(self, value: float) -> None:
        del value
        if (
            self._updatingRobotPlacementUI
            or not self._parameterNode
            or not self.logic
            or not self._robotWorkflowFacade
        ):
            return
        result = self._robotWorkflowFacade.requestCurrentJointState()
        if not result.success:
            self._updateRos2MotionControlStatus(
                _("ROS 2 joint update failed: %1").replace("%1", result.message)
            )
            self._updateRobotPlacement()
            return
        self._updateRobotPlacementStatus()

    def onRobotBaseTransformSelectionChanged(self, transformNode) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.robotBaseTransform = transformNode
        self._updateRobotPlacement()

    def onRobotMountPlaneSelectionChanged(self, planeNode) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.robotMountPlane = planeNode
        self._updateRobotPlacement()

    def onDraftPhantomSelectionChanged(self, node=None) -> None:
        del node
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.draftPhantomSkullModel = (
            self.ui.draftPhantomSkullSelector.currentNode()
        )
        self._parameterNode.draftPhantomMandibleModel = (
            self.ui.draftPhantomMandibleSelector.currentNode()
        )
        self._updateRobotPlacement()

    def onDraftJawLandmarksSelectionChanged(self, node) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.draftJawLandmarks = node
        self._bindDraftJawLandmarksNode(node)
        self._updateRobotPlacement()

    def onStep6CaseJawLandmarksSelectionChanged(self, node) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        if node and self.logic and not self.logic.isStep6CaseJawLandmarksNode(node):
            slicer.util.errorDisplay(_("Select the Step 6 case jaw landmark set."))
            return
        self._parameterNode.step6CaseJawLandmarks = node
        self._bindStep6CaseJawLandmarksNode(node)
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def onRobotKeyboardNudgeToggled(self, checked: bool) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.robotKeyboardNudgeEnabled = bool(checked)
        self._updateRobotKeyboardShortcutState()

    def onResetRobotJoints(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode:
            return
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.robotJoint1Deg = 0.0
            self._parameterNode.robotJoint2Mm = 0.0
            self._parameterNode.robotJoint3Deg = 0.0
            self._parameterNode.robotJoint4Mm = 0.0
            self._parameterNode.robotJoint5Deg = 0.0
            self._parameterNode.robotJoint6Deg = 0.0
        finally:
            self._parameterNode.EndModify(wasModifying)
        self._updateRobotPlacement()
        self._updateRobotPlacementStatus(_("All robot joints reset to selected zero."))

    def onResetRobotBase(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        baseTransform = self._parameterNode.robotBaseTransform
        if not self.logic.isRobotBaseTransformNode(baseTransform):
            return
        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        baseTransform.SetAndObserveTransformNodeID(None)
        baseTransform.SetMatrixTransformToParent(matrix)
        self._updateRobotPlacementStatus(_("Robot base reset to Slicer world RAS."))

    def onFrameStep6CaseScene(self, checked: bool = False) -> None:
        """Show the imported case in slice and 3D views (not the phantom workspace)."""
        del checked
        if not self._parameterNode or not self.logic:
            return
        self._showStep6CaseVolumeInSliceViewers()
        bounds = self.logic.step6CaseViewRasBounds(self._parameterNode)
        if bounds is None:
            return
        self._frameRasBoundsInViews(bounds)

    def onFrameStep6ResearchWorkspace(self, checked: bool = False) -> None:
        del checked
        if not self.logic:
            return
        bounds = self.logic.step6ResearchWorkspaceRasBounds(
            self.logic.robotModelNodes(),
            self.logic.draftPhantomModelNodes(),
        )
        if bounds is None:
            return
        self._frameRasBoundsInViews(bounds)

    def onFrameRobot(self, checked: bool = False) -> None:
        del checked
        self.onFrameStep6ResearchWorkspace()

    def onDeleteRobotSetup(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the simulation-only robot meshes, link transforms, base "
                "transform, and mount plane from this scene?"
            ),
            windowTitle=_("Delete Step 6 robot setup"),
        ):
            return
        if self.logic.isRos2MotionControlActive(
            self._parameterNode.robotBaseTransform
        ):
            disconnect_dentobot_motion_control(self.logic.robotModelNodes())
        removed = self.logic.deleteRobotPlacement(
            self._parameterNode.robotBaseTransform,
            self._parameterNode.robotMountPlane,
        )
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.robotBaseTransform = None
            self._parameterNode.robotMountPlane = None
            self._parameterNode.robotKeyboardNudgeEnabled = False
        finally:
            self._parameterNode.EndModify(wasModifying)
        self._clearRobotPlacement()
        logging.info("Deleted %d Step 6 robot placement nodes", len(removed))
