"""Extracted trajectory verification view methods; public APIs remain on PlanningWidgetMixin."""

from __future__ import annotations

from .runtime import *


class TrajectoryViewWidgetMixin:
    @staticmethod
    def _trajectoryGeometrySnapshot(trajectoryNode) -> dict:
        """Capture only point state that can change trajectory geometry."""

        if not trajectoryNode or not trajectoryNode.IsA(
            "vtkMRMLMarkupsLineNode"
        ):
            return {"controlPointCount": 0, "points": ()}
        points = []
        for index in range(trajectoryNode.GetNumberOfControlPoints()):
            status = int(
                trajectoryNode.GetNthControlPointPositionStatus(index)
            )
            pointRas = None
            if status == int(slicer.vtkMRMLMarkupsNode.PositionDefined):
                point = [0.0, 0.0, 0.0]
                trajectoryNode.GetNthControlPointPositionWorld(index, point)
                pointRas = tuple(float(value) for value in point)
            points.append((status, pointRas))
        return {
            "controlPointCount": int(
                trajectoryNode.GetNumberOfControlPoints()
            ),
            "points": tuple(points),
        }

    @staticmethod
    def _trajectoryGeometrySnapshotsMatch(
        left: dict | None,
        right: dict | None,
        toleranceMm: float = 1e-6,
    ) -> bool:
        """Compare point count/status and world-RAS positions with tolerance."""

        if left is None or right is None:
            return left is right
        if left.get("controlPointCount") != right.get("controlPointCount"):
            return False
        leftPoints = left.get("points") or ()
        rightPoints = right.get("points") or ()
        if len(leftPoints) != len(rightPoints):
            return False
        for (leftStatus, leftRas), (rightStatus, rightRas) in zip(
            leftPoints,
            rightPoints,
        ):
            if leftStatus != rightStatus or (leftRas is None) != (rightRas is None):
                return False
            if leftRas is None:
                continue
            if any(
                not math.isclose(
                    float(leftValue),
                    float(rightValue),
                    rel_tol=0.0,
                    abs_tol=float(toleranceMm),
                )
                for leftValue, rightValue in zip(leftRas, rightRas)
            ):
                return False
        return True

    def _bindPlanningTrajectoryNode(self, trajectoryNode) -> None:
        """Observe the selected trajectory once so measurements stay current."""

        candidateDisplayNode = (
            trajectoryNode.GetDisplayNode() if trajectoryNode else None
        )
        if (
            trajectoryNode is self._planningTrajectoryNode
            and candidateDisplayNode is self._planningTrajectoryDisplayNode
        ):
            return
        if self._planningTrajectoryDisplayNode:
            self.removeObserver(
                self._planningTrajectoryDisplayNode,
                slicer.vtkMRMLMarkupsDisplayNode.JumpToPointEvent,
                self._onPlanningTrajectoryJumpToPoint,
            )
        self._planningTrajectoryDisplayNode = None
        if self._planningTrajectoryNode:
            for trajectoryEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.removeObserver(
                    self._planningTrajectoryNode,
                    trajectoryEvent,
                    self._onPlanningTrajectoryModified,
                )
            self.removeObserver(
                self._planningTrajectoryNode,
                slicer.vtkMRMLMarkupsNode.PointStartInteractionEvent,
                self._onPlanningTrajectoryInteractionStarted,
            )
            self.removeObserver(
                self._planningTrajectoryNode,
                slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent,
                self._onPlanningTrajectoryInteractionEnded,
            )
        self._trajectoryVerificationPointInteractionActive = False
        previousNode = self._planningTrajectoryNode
        self._planningTrajectoryNode = trajectoryNode
        if previousNode and previousNode is not trajectoryNode:
            previousNodeId = previousNode.GetID()
            if previousNodeId:
                self._planningTrajectoryGeometryByNodeId.pop(
                    previousNodeId,
                    None,
                )
        if trajectoryNode:
            trajectoryNode.SetSelectable(True)
            trajectoryNode.CreateDefaultDisplayNodes()
            self._planningTrajectoryDisplayNode = trajectoryNode.GetDisplayNode()
            if trajectoryNode.GetID():
                self._planningTrajectoryGeometryByNodeId[
                    trajectoryNode.GetID()
                ] = self._trajectoryGeometrySnapshot(trajectoryNode)
            for trajectoryEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.addObserver(
                    trajectoryNode,
                    trajectoryEvent,
                    self._onPlanningTrajectoryModified,
                )
            self.addObserver(
                trajectoryNode,
                slicer.vtkMRMLMarkupsNode.PointStartInteractionEvent,
                self._onPlanningTrajectoryInteractionStarted,
            )
            self.addObserver(
                trajectoryNode,
                slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent,
                self._onPlanningTrajectoryInteractionEnded,
            )
            if self._planningTrajectoryDisplayNode:
                self.addObserver(
                    self._planningTrajectoryDisplayNode,
                    slicer.vtkMRMLMarkupsDisplayNode.JumpToPointEvent,
                    self._onPlanningTrajectoryJumpToPoint,
                )

    def _onPlanningTrajectoryJumpToPoint(self, caller=None, event=None) -> None:
        """Navigate to a clicked Entry/Target even when geometry is locked."""

        del event
        trajectoryNode = self._planningTrajectoryNode
        if not caller or not trajectoryNode:
            return
        try:
            pointIndex = int(caller.GetActiveControlPoint())
        except (AttributeError, TypeError, ValueError):
            pointIndex = -1
        if (
            pointIndex < 0
            or pointIndex >= trajectoryNode.GetNumberOfControlPoints()
            or not trajectoryNode.GetNthControlPointPositionStatus(pointIndex)
            == slicer.vtkMRMLMarkupsNode.PositionDefined
        ):
            return
        pointRas = [0.0, 0.0, 0.0]
        trajectoryNode.GetNthControlPointPositionWorld(pointIndex, pointRas)
        try:
            self._enableCrossViewNavigation()
            crosshairNode = self._workflowCrosshairNode()
            crosshairNode.SetCrosshairRAS(pointRas)
            slicer.modules.markups.logic().JumpSlicesToLocation(
                float(pointRas[0]),
                float(pointRas[1]),
                float(pointRas[2]),
                True,
            )
        except Exception:
            logging.debug(
                "Could not navigate linked views to trajectory control point %d.",
                pointIndex,
            )

    def _bindAssistedTrajectoryEntryNode(self, entryNode) -> None:
        if entryNode is self._assistedTrajectoryEntryNode:
            return
        if self._assistedTrajectoryEntryNode:
            for entryEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.removeObserver(
                    self._assistedTrajectoryEntryNode,
                    entryEvent,
                    self._onAssistedTrajectoryEntryModified,
                )
        self._assistedTrajectoryEntryNode = entryNode
        if entryNode:
            for entryEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.addObserver(
                    entryNode,
                    entryEvent,
                    self._onAssistedTrajectoryEntryModified,
                )

    def _onAssistedTrajectoryEntryModified(self, caller=None, event=None) -> None:
        del caller, event
        if not self._updatingPlanningUI:
            self._updateAssistedTrajectoryControls()

    def _onPlanningTrajectoryInteractionStarted(self, caller=None, event=None) -> None:
        del event
        if (
            caller
            and self.logic
            and self.logic.isDentobotTrajectoryNode(caller)
            and not self._confirmAndDeleteTrajectoryDependents(
                caller,
                _("edit its Entry/Target points"),
            )
        ):
            self.logic.stopTrajectoryPlacement()
            caller.SetLocked(True)
            self._updatePlanning()
            return
        if self._trajectoryVerificationEnabled:
            self._trajectoryVerificationPointInteractionActive = True

    def _onPlanningTrajectoryInteractionEnded(self, caller=None, event=None) -> None:
        del caller, event
        wasActive = self._trajectoryVerificationPointInteractionActive
        self._trajectoryVerificationPointInteractionActive = False
        if not wasActive or not self._trajectoryVerificationEnabled:
            return
        self._updatePlanning()

    def _onPlanningTrajectoryModified(self, caller=None, event=None) -> None:
        del event
        if (
            self._updatingPlanningUI
            or self._restoringTrajectoryAssociation
            or self._caseBundleRestoreDepth > 0
            or not self.logic
        ):
            return
        trajectoryNode = (
            caller
            if caller and caller.IsA("vtkMRMLMarkupsLineNode")
            else self._planningTrajectoryNode
        )
        trajectoryNodeId = trajectoryNode.GetID() if trajectoryNode else None
        currentGeometry = self._trajectoryGeometrySnapshot(trajectoryNode)
        previousGeometry = (
            self._planningTrajectoryGeometryByNodeId.get(trajectoryNodeId)
            if trajectoryNodeId
            else None
        )
        if previousGeometry is None:
            if trajectoryNodeId:
                self._planningTrajectoryGeometryByNodeId[
                    trajectoryNodeId
                ] = currentGeometry
            return
        if self._trajectoryGeometrySnapshotsMatch(
            previousGeometry,
            currentGeometry,
        ):
            # MRML ModifiedEvent also reports labels, references, lock state,
            # selectability, and display synchronization.  Those are not
            # trajectory edits and must not invalidate Step 4C/5C/6.
            return
        self._updatingPlanningUI = True
        try:
            if trajectoryNode:
                self.logic.labelTrajectoryControlPoints(
                    trajectoryNode
                )
                self._enforceTrajectoryBounds(
                    trajectoryNode
                )
        finally:
            self._updatingPlanningUI = False
        finalGeometry = self._trajectoryGeometrySnapshot(trajectoryNode)
        if trajectoryNodeId:
            self._planningTrajectoryGeometryByNodeId[
                trajectoryNodeId
            ] = finalGeometry
        if self._trajectoryGeometrySnapshotsMatch(
            previousGeometry,
            finalGeometry,
        ):
            self._updatePlanning()
            return
        if self._parameterNode and trajectoryNode:
            self.logic.invalidateStep6TaskConfirmation(
                self._parameterNode,
                _("Approved trajectory geometry changed."),
            )
            self._step6MotionPlan = None
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
            try:
                dockingSummary = self.logic.getTargetDockingAssemblySummary(
                    self._parameterNode.targetDockingAssemblyModel
                )
                if trajectoryNode in dockingSummary["trajectories"]:
                    reason = _("A Step 4A source trajectory changed.")
                    self.logic.markTargetDockingAssemblyStale(
                        self._parameterNode.targetDockingAssemblyModel,
                        reason,
                    )
                    self.logic.markFinalPrintableTemplateStale(
                        self._parameterNode.finalPrintableTemplateModel,
                        reason,
                    )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
        self._updatePlanning()
        self._updateTargetDocking()

    def _setTrajectoryVerificationStatus(
        self,
        message: str,
        *,
        error: bool = False,
        active: bool = False,
    ) -> None:
        if not hasattr(self, "ui"):
            return
        self.ui.trajectoryVerificationStatusLabel.text = message
        self.ui.trajectoryVerificationStatusLabel.styleSheet = (
            "color: #b00020;"
            if error
            else "color: #207227;"
            if active
            else "color: #666666;"
        )

    def _setTrajectoryVerificationEnabledUi(self, enabled: bool) -> None:
        if not hasattr(self, "ui"):
            return
        self._updatingTrajectoryVerificationUI = True
        try:
            self.ui.trajectoryVerificationEnabledCheckBox.checked = bool(enabled)
            self.ui.trajectoryVerificationRotationSlider.enabled = bool(enabled)
            self.ui.resetTrajectoryVerificationButton.enabled = bool(enabled)
        finally:
            self._updatingTrajectoryVerificationUI = False

    def _trajectoryVerificationInputs(self) -> dict:
        if not self._parameterNode or not self.logic:
            raise ValueError(_("DENTO Workflow is not initialized."))
        trajectoryNode = self._parameterNode.trajectoryLine
        summary = self.logic.getTrajectorySummary(trajectoryNode)
        if summary["definedPointCount"] != 2 or not summary["isValid"]:
            raise ValueError(
                _("Define a complete non-zero Entry/Target trajectory first.")
            )
        volumeNode = None
        association = self.logic.getTrajectoryTargetAssociation(trajectoryNode)
        if association:
            try:
                volumeNode = self.logic.getSegmentationSourceVolume(
                    association["segmentationNode"]
                )
            except ValueError as exc:
                raise ValueError(
                    _(
                        "The trajectory's authoritative segmentation has no available "
                        "source CBCT. Restore that referenced volume before verification."
                    )
                ) from exc
        if volumeNode is None:
            volumeNode = self._parameterNode.inputVolume
        if (
            not volumeNode
            or not volumeNode.IsA("vtkMRMLScalarVolumeNode")
            or not volumeNode.GetImageData()
        ):
            raise ValueError(_("Select or restore the trajectory's source CBCT first."))
        layoutManager = slicer.app.layoutManager() if slicer.app else None
        if not layoutManager:
            raise RuntimeError(_("Slicer's layout manager is unavailable."))
        viewNames = [str(name) for name in layoutManager.sliceViewNames()]
        if not viewNames:
            raise RuntimeError(
                _("No 2D slice view is available. Exit the Step 5C isolated 3D view first.")
            )
        sliceViewName = "Red" if "Red" in viewNames else viewNames[0]
        sliceWidget = layoutManager.sliceWidget(sliceViewName)
        if not sliceWidget:
            raise RuntimeError(_("Slicer could not access the verification slice view."))
        sliceNode = sliceWidget.mrmlSliceNode()
        compositeNode = sliceWidget.mrmlSliceCompositeNode()
        if not sliceNode or not compositeNode:
            raise RuntimeError(_("The verification slice MRML nodes are unavailable."))
        return {
            "volumeNode": volumeNode,
            "trajectoryNode": trajectoryNode,
            "summary": summary,
            "sliceViewName": sliceViewName,
            "sliceWidget": sliceWidget,
            "sliceNode": sliceNode,
            "compositeNode": compositeNode,
        }

    @staticmethod
    def _captureSliceToRasElements(sliceNode) -> tuple[float, ...]:
        matrix = sliceNode.GetSliceToRAS()
        return tuple(
            float(matrix.GetElement(row, column))
            for row in range(4)
            for column in range(4)
        )

    @staticmethod
    def _matrixFromElements(elements: tuple[float, ...]) -> vtk.vtkMatrix4x4:
        if len(elements) != 16:
            raise ValueError(_("A saved slice matrix must contain 16 elements."))
        matrix = vtk.vtkMatrix4x4()
        for row in range(4):
            for column in range(4):
                matrix.SetElement(row, column, float(elements[4 * row + column]))
        return matrix

    @staticmethod
    def _sliceMatricesDiffer(first, second, tolerance: float = 1e-8) -> bool:
        return any(
            abs(float(first.GetElement(row, column)) - float(second.GetElement(row, column)))
            > tolerance
            for row in range(4)
            for column in range(4)
        )

    def _captureTrajectoryVerificationSliceState(self, inputs: dict) -> dict:
        sliceNode = inputs["sliceNode"]
        compositeNode = inputs["compositeNode"]
        volumeNode = inputs["volumeNode"]
        volumeNode.CreateDefaultDisplayNodes()
        volumeDisplayNode = volumeNode.GetDisplayNode()
        return {
            "sliceViewName": inputs["sliceViewName"],
            "sliceNodeId": sliceNode.GetID(),
            "compositeNodeId": compositeNode.GetID(),
            "sliceToRas": self._captureSliceToRasElements(sliceNode),
            "fieldOfView": tuple(float(value) for value in sliceNode.GetFieldOfView()),
            "backgroundVolumeId": compositeNode.GetBackgroundVolumeID(),
            "foregroundVolumeId": compositeNode.GetForegroundVolumeID(),
            "labelVolumeId": compositeNode.GetLabelVolumeID(),
            "foregroundOpacity": float(compositeNode.GetForegroundOpacity()),
            "labelOpacity": float(compositeNode.GetLabelOpacity()),
            "linkedControl": bool(compositeNode.GetLinkedControl()),
            "hotLinkedControl": bool(compositeNode.GetHotLinkedControl()),
            "volumeDisplayNodeId": (
                volumeDisplayNode.GetID() if volumeDisplayNode else None
            ),
            "volumeInterpolate": (
                bool(volumeDisplayNode.GetInterpolate())
                if volumeDisplayNode and hasattr(volumeDisplayNode, "GetInterpolate")
                else None
            ),
        }

    def _captureTrajectoryVerificationDisplayState(self, trajectoryNode) -> None:
        self._restoreTrajectoryVerificationDisplayState()
        displayNode = trajectoryNode.GetDisplayNode() if trajectoryNode else None
        if trajectoryNode and not displayNode:
            trajectoryNode.CreateDefaultDisplayNodes()
            displayNode = trajectoryNode.GetDisplayNode()
        if not displayNode:
            raise RuntimeError(_("Slicer could not create the trajectory overlay display."))
        self._trajectoryVerificationPriorDisplayState = {
            "trajectoryNodeId": trajectoryNode.GetID(),
            "visibility": bool(displayNode.GetVisibility()),
            "visibility2D": bool(displayNode.GetVisibility2D()),
            "sliceProjection": bool(displayNode.GetSliceProjection()),
            "sliceProjectionUseFiducialColor": bool(
                displayNode.GetSliceProjectionUseFiducialColor()
            ),
            "sliceProjectionOpacity": float(displayNode.GetSliceProjectionOpacity()),
        }
        displayNode.SetVisibility(True)
        displayNode.SetVisibility2D(True)
        displayNode.SetSliceProjection(True)
        displayNode.SetSliceProjectionUseFiducialColor(True)
        displayNode.SetSliceProjectionOpacity(1.0)

    def _restoreTrajectoryVerificationDisplayState(self) -> None:
        state = self._trajectoryVerificationPriorDisplayState
        self._trajectoryVerificationPriorDisplayState = None
        if not state:
            return
        trajectoryNode = slicer.mrmlScene.GetNodeByID(state["trajectoryNodeId"])
        displayNode = trajectoryNode.GetDisplayNode() if trajectoryNode else None
        if not displayNode:
            return
        displayNode.SetVisibility(state["visibility"])
        displayNode.SetVisibility2D(state["visibility2D"])
        displayNode.SetSliceProjection(state["sliceProjection"])
        displayNode.SetSliceProjectionUseFiducialColor(
            state["sliceProjectionUseFiducialColor"]
        )
        displayNode.SetSliceProjectionOpacity(state["sliceProjectionOpacity"])

    def _trajectoryVerificationFieldOfView(
        self,
        inputs: dict,
        sliceMatrix,
    ) -> tuple[float, float]:
        """Fit the target bounds and trajectory with a small margin."""

        summary = inputs["summary"]
        midpoint = np.asarray(
            [sliceMatrix.GetElement(row, 3) for row in range(3)],
            dtype=float,
        )
        xAxis = np.asarray(
            [sliceMatrix.GetElement(row, 0) for row in range(3)],
            dtype=float,
        )
        yAxis = np.asarray(
            [sliceMatrix.GetElement(row, 1) for row in range(3)],
            dtype=float,
        )
        projectedX = []
        projectedY = []
        roiNode = self._parameterNode.targetToothBoundsRoi if self._parameterNode else None
        if roiNode and roiNode.IsA("vtkMRMLMarkupsROINode"):
            bounds = [0.0] * 6
            roiNode.GetRASBounds(bounds)
            if all(math.isfinite(value) for value in bounds):
                for rValue in (bounds[0], bounds[1]):
                    for aValue in (bounds[2], bounds[3]):
                        for sValue in (bounds[4], bounds[5]):
                            relative = np.asarray((rValue, aValue, sValue)) - midpoint
                            projectedX.append(float(np.dot(relative, xAxis)))
                            projectedY.append(float(np.dot(relative, yAxis)))
        for point in (summary["entryRas"], summary["targetRas"]):
            relative = np.asarray(point, dtype=float) - midpoint
            projectedX.append(float(np.dot(relative, xAxis)))
            projectedY.append(float(np.dot(relative, yAxis)))

        projectedWidth = max(projectedX) - min(projectedX)
        projectedHeight = max(projectedY) - min(projectedY)
        if roiNode and roiNode.IsA("vtkMRMLMarkupsROINode"):
            roiSize = [0.0, 0.0, 0.0]
            roiNode.GetSizeWorld(roiSize)
            rotationInvariantExtent = float(np.linalg.norm(roiSize))
        else:
            rotationInvariantExtent = 0.0
        contentWidth = max(projectedWidth, rotationInvariantExtent, 5.0) * 1.25
        contentHeight = max(
            projectedHeight,
            rotationInvariantExtent,
            float(summary["lengthMm"]),
            5.0,
        ) * 1.25
        dimensions = inputs["sliceNode"].GetDimensions()
        aspect = (
            float(dimensions[0]) / float(dimensions[1])
            if dimensions[0] > 0 and dimensions[1] > 0
            else 1.0
        )
        height = max(contentHeight, contentWidth / max(aspect, 1e-6))
        return height * aspect, height

    def _applyTrajectoryVerificationView(
        self,
        *,
        fit: bool,
        deterministicOrientation: bool = False,
    ) -> None:
        if not self._trajectoryVerificationEnabled:
            return
        inputs = self._trajectoryVerificationInputs()
        priorState = self._trajectoryVerificationPriorSliceState
        if (
            not priorState
            or inputs["sliceNode"].GetID() != priorState["sliceNodeId"]
            or inputs["compositeNode"].GetID() != priorState["compositeNodeId"]
        ):
            raise RuntimeError(
                _("The verification slice view changed. Disable and enable verification again.")
            )

        displayState = self._trajectoryVerificationPriorDisplayState
        if (
            not displayState
            or displayState["trajectoryNodeId"] != inputs["trajectoryNode"].GetID()
        ):
            self._captureTrajectoryVerificationDisplayState(inputs["trajectoryNode"])

        compositeNode = inputs["compositeNode"]
        if compositeNode.GetLinkedControl():
            compositeNode.SetLinkedControl(False)
        if compositeNode.GetHotLinkedControl():
            compositeNode.SetHotLinkedControl(False)
        sliceNode = inputs["sliceNode"]
        trajectoryNodeId = inputs["trajectoryNode"].GetID()
        continuousOrientationAvailable = bool(
            not deterministicOrientation
            and trajectoryNodeId == self._trajectoryVerificationAppliedTrajectoryNodeId
            and self._trajectoryVerificationLastAppliedAngleDeg is not None
        )
        if continuousOrientationAvailable:
            angleDeltaDeg = (
                self._trajectoryVerificationAngleDeg
                - self._trajectoryVerificationLastAppliedAngleDeg
            )
            matrix = self.logic.transportTrajectorySliceMatrix(
                sliceNode.GetSliceToRAS(),
                inputs["summary"]["entryRas"],
                inputs["summary"]["targetRas"],
                angleDeltaDeg,
            )
        else:
            matrix = self.logic.computeTrajectorySliceMatrix(
                inputs["summary"]["entryRas"],
                inputs["summary"]["targetRas"],
                self._trajectoryVerificationAngleDeg,
            )
        if self._sliceMatricesDiffer(sliceNode.GetSliceToRAS(), matrix):
            sliceNode.GetSliceToRAS().DeepCopy(matrix)
            sliceNode.UpdateMatrices()
        self._trajectoryVerificationAppliedTrajectoryNodeId = trajectoryNodeId
        self._trajectoryVerificationLastAppliedAngleDeg = (
            self._trajectoryVerificationAngleDeg
        )
        if fit:
            width, height = self._trajectoryVerificationFieldOfView(inputs, matrix)
            currentFieldOfView = sliceNode.GetFieldOfView()
            sliceNode.SetFieldOfView(width, height, currentFieldOfView[2])
            sliceNode.UpdateMatrices()

        if compositeNode.GetBackgroundVolumeID() != inputs["volumeNode"].GetID():
            compositeNode.SetBackgroundVolumeID(inputs["volumeNode"].GetID())
        volumeDisplayNode = inputs["volumeNode"].GetDisplayNode()
        if volumeDisplayNode and hasattr(volumeDisplayNode, "SetInterpolate"):
            volumeDisplayNode.SetInterpolate(
                bool(self.ui.trajectoryVerificationSmoothInterpolationCheckBox.checked)
            )

        self._setTrajectoryVerificationStatus(
            _(
                "%1 view: longitudinal Entry→Target plane at %2°. "
                "Point drags stay in this plane; use Rotation to inspect circumference."
            )
            .replace("%1", inputs["sliceViewName"])
            .replace("%2", f"{self._trajectoryVerificationAngleDeg:.0f}"),
            active=True,
        )

    def _applyPendingTrajectoryVerificationUpdate(self) -> None:
        self._trajectoryVerificationUpdatePending = False
        if (
            not self._trajectoryVerificationEnabled
            or self._trajectoryVerificationPointInteractionActive
        ):
            return
        try:
            self._applyTrajectoryVerificationView(fit=False)
        except (RuntimeError, ValueError) as exc:
            self._restoreTrajectoryVerificationViewState(updateUi=True)
            self._setTrajectoryVerificationStatus(str(exc), error=True)

    def _scheduleTrajectoryVerificationUpdate(self) -> None:
        if (
            not self._trajectoryVerificationEnabled
            or self._trajectoryVerificationPointInteractionActive
            or self._trajectoryVerificationUpdatePending
        ):
            return
        self._trajectoryVerificationUpdatePending = True
        # Collapse rapid slider/wheel events to roughly one display refresh per
        # 60 Hz frame. Slicer's native reslice pipeline still performs the only
        # image operation; no volume is generated or copied.
        qt.QTimer.singleShot(16, self._applyPendingTrajectoryVerificationUpdate)

    def _enableTrajectoryVerificationView(self) -> None:
        if self._templateFinalizationViewIsolated():
            self._restoreTemplateFinalizationViewState(updateUi=True)
        inputs = self._trajectoryVerificationInputs()
        if self._trajectoryVerificationPriorSliceState:
            self._restoreTrajectoryVerificationViewState(updateUi=False)
            inputs = self._trajectoryVerificationInputs()
        self._trajectoryVerificationPriorSliceState = (
            self._captureTrajectoryVerificationSliceState(inputs)
        )
        self._trajectoryVerificationEnabled = True
        self._trajectoryVerificationPointInteractionActive = False
        self._trajectoryVerificationAppliedTrajectoryNodeId = None
        self._trajectoryVerificationLastAppliedAngleDeg = None
        self._captureTrajectoryVerificationDisplayState(inputs["trajectoryNode"])
        try:
            self._applyTrajectoryVerificationView(
                fit=True,
                deterministicOrientation=True,
            )
        except Exception:
            self._restoreTrajectoryVerificationViewState(updateUi=False)
            raise
        self._setTrajectoryVerificationEnabledUi(True)

    def _restoreTrajectoryVerificationViewState(self, *, updateUi: bool) -> None:
        state = self._trajectoryVerificationPriorSliceState
        self._trajectoryVerificationPriorSliceState = None
        self._trajectoryVerificationEnabled = False
        self._trajectoryVerificationUpdatePending = False
        self._trajectoryVerificationPointInteractionActive = False
        self._trajectoryVerificationAppliedTrajectoryNodeId = None
        self._trajectoryVerificationLastAppliedAngleDeg = None
        self._restoreTrajectoryVerificationDisplayState()
        if state:
            sliceNode = slicer.mrmlScene.GetNodeByID(state["sliceNodeId"])
            compositeNode = slicer.mrmlScene.GetNodeByID(state["compositeNodeId"])
            if sliceNode and sliceNode.IsA("vtkMRMLSliceNode"):
                matrix = self._matrixFromElements(state["sliceToRas"])
                sliceNode.GetSliceToRAS().DeepCopy(matrix)
                sliceNode.UpdateMatrices()
                sliceNode.SetFieldOfView(*state["fieldOfView"])
            if compositeNode and compositeNode.IsA("vtkMRMLSliceCompositeNode"):
                compositeNode.SetLinkedControl(False)
                compositeNode.SetHotLinkedControl(False)
                compositeNode.SetBackgroundVolumeID(state["backgroundVolumeId"])
                compositeNode.SetForegroundVolumeID(state["foregroundVolumeId"])
                compositeNode.SetLabelVolumeID(state["labelVolumeId"])
                compositeNode.SetForegroundOpacity(state["foregroundOpacity"])
                compositeNode.SetLabelOpacity(state["labelOpacity"])
                compositeNode.SetHotLinkedControl(state["hotLinkedControl"])
                compositeNode.SetLinkedControl(state["linkedControl"])
            volumeDisplayNode = (
                slicer.mrmlScene.GetNodeByID(state.get("volumeDisplayNodeId"))
                if state.get("volumeDisplayNodeId")
                else None
            )
            if (
                volumeDisplayNode
                and state.get("volumeInterpolate") is not None
                and hasattr(volumeDisplayNode, "SetInterpolate")
            ):
                volumeDisplayNode.SetInterpolate(bool(state["volumeInterpolate"]))
        if updateUi:
            self._setTrajectoryVerificationEnabledUi(False)

    def onTrajectoryVerificationToggled(self, enabled: bool) -> None:
        if self._updatingTrajectoryVerificationUI:
            return
        if not enabled:
            self._restoreTrajectoryVerificationViewState(updateUi=True)
            self._updateTrajectoryVerificationControls()
            return
        try:
            self._enableTrajectoryVerificationView()
            self._updateTrajectoryVerificationControls()
        except (RuntimeError, ValueError) as exc:
            self._restoreTrajectoryVerificationViewState(updateUi=True)
            self._setTrajectoryVerificationStatus(str(exc), error=True)

    def onTrajectoryVerificationRotationChanged(self, angleDeg: int) -> None:
        if self._updatingTrajectoryVerificationUI:
            return
        self._trajectoryVerificationAngleDeg = float(angleDeg)
        self.ui.trajectoryVerificationRotationValueLabel.text = f"{int(angleDeg)}°"
        if self._parameterNode:
            self._presentSelectedTrajectory(
                self._parameterNode.trajectoryLine,
                centerSlices=True,
            )
        self._scheduleTrajectoryVerificationUpdate()

    def onTrajectoryVerificationSmoothingToggled(self, checked: bool) -> None:
        del checked
        if self._updatingTrajectoryVerificationUI:
            return
        if not self._trajectoryVerificationEnabled:
            return
        try:
            inputs = self._trajectoryVerificationInputs()
            displayNode = inputs["volumeNode"].GetDisplayNode()
            if displayNode and hasattr(displayNode, "SetInterpolate"):
                displayNode.SetInterpolate(
                    bool(
                        self.ui.trajectoryVerificationSmoothInterpolationCheckBox.checked
                    )
                )
        except (RuntimeError, ValueError) as exc:
            self._setTrajectoryVerificationStatus(str(exc), error=True)

    def onResetTrajectoryVerification(self) -> None:
        self._trajectoryVerificationAngleDeg = 0.0
        self._updatingTrajectoryVerificationUI = True
        try:
            self.ui.trajectoryVerificationRotationSlider.value = 0
            self.ui.trajectoryVerificationRotationValueLabel.text = _("0°")
        finally:
            self._updatingTrajectoryVerificationUI = False
        if self._trajectoryVerificationEnabled:
            try:
                self._applyTrajectoryVerificationView(
                    fit=True,
                    deterministicOrientation=True,
                )
            except (RuntimeError, ValueError) as exc:
                self._restoreTrajectoryVerificationViewState(updateUi=True)
                self._setTrajectoryVerificationStatus(str(exc), error=True)

    def _updateTrajectoryVerificationControls(self) -> None:
        if not hasattr(self, "ui"):
            return
        canEnable = False
        reason = _("Complete Entry and Target and select a CBCT to enable verification.")
        if self._parameterNode and self.logic:
            try:
                inputs = self._trajectoryVerificationInputs()
                canEnable = True
                reason = _("Ready to align the %1 slice view through Entry and Target.").replace(
                    "%1", inputs["sliceViewName"]
                )
            except (RuntimeError, ValueError) as exc:
                reason = str(exc)
        if self._trajectoryVerificationEnabled and not canEnable:
            self._restoreTrajectoryVerificationViewState(updateUi=True)

        self._updatingTrajectoryVerificationUI = True
        try:
            self.ui.trajectoryVerificationEnabledCheckBox.enabled = bool(
                canEnable or self._trajectoryVerificationEnabled
            )
            self.ui.trajectoryVerificationEnabledCheckBox.checked = bool(
                self._trajectoryVerificationEnabled
            )
            self.ui.trajectoryVerificationRotationSlider.enabled = bool(
                self._trajectoryVerificationEnabled
            )
            self.ui.resetTrajectoryVerificationButton.enabled = bool(
                self._trajectoryVerificationEnabled
            )
            self.ui.trajectoryVerificationRotationSlider.value = int(
                round(self._trajectoryVerificationAngleDeg)
            )
            self.ui.trajectoryVerificationRotationValueLabel.text = (
                f"{self._trajectoryVerificationAngleDeg:.0f}°"
            )
        finally:
            self._updatingTrajectoryVerificationUI = False
        if self._trajectoryVerificationEnabled:
            self._scheduleTrajectoryVerificationUpdate()
        else:
            self._setTrajectoryVerificationStatus(reason)

    def _ensureTargetBounds(
        self,
        segmentationNode,
        targetRecord: dict,
    ) -> tuple[float, ...] | None:
        """Create/update the visible active-tooth AABB and persist its node."""

        if not self._parameterNode or not self.logic:
            return None
        previousRoi = self._parameterNode.targetToothBoundsRoi
        candidateRoi = previousRoi
        if not self.logic.isTargetBoundsRoiForTarget(
            candidateRoi,
            segmentationNode,
            targetRecord["segmentId"],
        ):
            candidateRoi = self.logic.findTargetBoundsRoi(
                segmentationNode,
                targetRecord["segmentId"],
            )
        try:
            roiNode, bounds = self.logic.createOrUpdateTargetBoundsRoi(
                segmentationNode,
                targetRecord["segmentId"],
                candidateRoi,
            )
        except (RuntimeError, ValueError) as exc:
            self._planningConstraintWarning = str(exc)
            self.ui.targetBoundsValueLabel.text = _("--")
            return None

        if (
            previousRoi
            and previousRoi is not roiNode
            and previousRoi.GetDisplayNode()
        ):
            previousRoi.GetDisplayNode().SetVisibility(False)
        if self._parameterNode.targetToothBoundsRoi is not roiNode:
            self._parameterNode.targetToothBoundsRoi = roiNode
        self.ui.targetBoundsValueLabel.text = (
            self.logic.formatRasBounds(bounds)
        )
        trajectoryNode = self._parameterNode.trajectoryLine
        if trajectoryNode:
            if trajectoryNode.GetNodeReference(
                self.logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE
            ) is not roiNode:
                trajectoryNode.SetNodeReferenceID(
                    self.logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
                    roiNode.GetID(),
                )
        return bounds

    def _enforceTrajectoryBounds(self, trajectoryNode) -> bool:
        """Reject or restore any trajectory point outside the target-tooth AABB."""

        if (
            not trajectoryNode
            or not self._parameterNode
            or not self.logic
            or not self._parameterNode.teethSegmentation
            or not self._parameterNode.targetToothSegmentId
        ):
            return True
        try:
            report = self.logic.getTrajectoryBoundsReport(
                trajectoryNode,
                self._parameterNode.teethSegmentation,
                self._parameterNode.targetToothSegmentId,
            )
        except ValueError as exc:
            self._planningConstraintWarning = str(exc)
            return False

        invalidIndices = report["invalidPointIndices"]
        if not invalidIndices:
            summary = report["summary"]
            currentPoints = [
                list(point)
                for point in (
                    summary["entryRas"],
                    summary["targetRas"],
                )
                if point is not None
            ]
            previousPoints = self._validTrajectoryPointsByNodeId.get(
                trajectoryNode.GetID(),
                [],
            )
            if (
                not self._planningConstraintWarning
                or currentPoints != previousPoints
            ):
                self._planningConstraintWarning = ""
            self._validTrajectoryPointsByNodeId[
                trajectoryNode.GetID()
            ] = currentPoints
            return True

        previousPoints = self._validTrajectoryPointsByNodeId.get(
            trajectoryNode.GetID(),
            [],
        )
        bounds = report["bounds"]
        wasModifying = trajectoryNode.StartModify()
        try:
            for pointIndex in sorted(invalidIndices, reverse=True):
                previousPoint = (
                    previousPoints[pointIndex]
                    if pointIndex < len(previousPoints)
                    else None
                )
                if (
                    previousPoint is not None
                    and self.logic.isRasPointWithinBounds(
                        previousPoint,
                        bounds,
                    )
                ):
                    trajectoryNode.SetNthControlPointPositionWorld(
                        pointIndex,
                        previousPoint,
                    )
                else:
                    trajectoryNode.RemoveNthControlPoint(pointIndex)
        finally:
            trajectoryNode.EndModify(wasModifying)

        rejectedNames = ", ".join(
            ("Entry", "Target")[index] for index in invalidIndices
        )
        self._planningConstraintWarning = (
            _(
                "%1 was outside the selected tooth bounds and was rejected. "
                "Place both points inside the orange target box."
            ).replace("%1", rejectedNames)
        )
        return False

    def _applyTargetPriorityHighlight(self) -> None:
        """Keep the Step 4A target dominant over Step 3 review selection."""

        if self._templateSupportBoundaryFocusState:
            return
        if (
            not self._parameterNode
            or not self.logic
            or not self._parameterNode.teethSegmentation
        ):
            return
        segmentationNode = self._parameterNode.teethSegmentation
        targetId = self._parameterNode.targetToothSegmentId
        if targetId in self._targetToothRecordsById:
            self.logic.setSegmentationVisibility2D(segmentationNode, True)
            self.logic.setSegmentationVisibility3D(segmentationNode, True)
            self.logic.setSegmentationSegmentVisibility(
                segmentationNode,
                targetId,
                True,
            )
            self.logic.setSegmentationSegmentHighlight(
                segmentationNode,
                targetId,
            )
            treeWidget = self.ui.segmentTreeWidget
            targetItem = None
            for groupIndex in range(treeWidget.topLevelItemCount):
                groupItem = treeWidget.topLevelItem(groupIndex)
                for childIndex in range(groupItem.childCount()):
                    item = groupItem.child(childIndex)
                    if str(item.data(0, qt.Qt.UserRole)) == targetId:
                        targetItem = item
                        break
                if targetItem:
                    break
            if targetItem and treeWidget.currentItem() is not targetItem:
                self._updatingSegmentationReviewUI = True
                try:
                    treeWidget.setCurrentItem(targetItem)
                finally:
                    self._updatingSegmentationReviewUI = False
                self._updateSelectedSegmentDetails(targetId)
        else:
            selectedId = self._selectedReviewSegmentId()
            self.logic.setSegmentationSegmentHighlight(
                segmentationNode,
                selectedId,
            )
