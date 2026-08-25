"""Extracted MRML display state methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class DisplayLogicMixin:
    @staticmethod
    def _segmentationAndDisplayNode(
        segmentationNode: vtkMRMLSegmentationNode,
    ):
        if not segmentationNode or not segmentationNode.IsA(
            "vtkMRMLSegmentationNode"
        ):
            raise ValueError(_("Select a valid segmentation node."))
        segmentationNode.CreateDefaultDisplayNodes()
        segmentation = segmentationNode.GetSegmentation()
        displayNode = segmentationNode.GetDisplayNode()
        if not segmentation or not displayNode:
            raise ValueError(_("The segmentation does not have valid display data."))
        return segmentation, displayNode

    def setSegmentationSegmentVisibility(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        visible: bool,
    ) -> None:
        segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        if not segmentId or not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        displayNode.SetVisibility(True)
        displayNode.SetSegmentVisibility(segmentId, bool(visible))

    def setAllSegmentationSegmentsVisibility(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        visible: bool,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        displayNode.SetVisibility(True)
        displayNode.SetAllSegmentsVisibility(bool(visible))

    def isolateSegmentationSegment(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> None:
        segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        if not segmentId or not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        displayNode.SetVisibility(True)
        displayNode.SetAllSegmentsVisibility(False)
        displayNode.SetSegmentVisibility(segmentId, True)

    def captureWorkflowDisplayState(
        self,
        segmentationNode: vtkMRMLSegmentationNode | None,
        displayableNodes: list,
    ) -> dict:
        """Capture exact display state for transient workflow view filtering."""

        state = {
            "segmentationNodeId": "",
            "segmentationDisplay": {},
            "segments": {},
            "nodes": {},
        }
        if segmentationNode:
            segmentation, displayNode = self._segmentationAndDisplayNode(
                segmentationNode
            )
            state["segmentationNodeId"] = segmentationNode.GetID()
            state["segmentationDisplay"] = {
                "visibility": bool(displayNode.GetVisibility()),
                "visibility2D": bool(displayNode.GetVisibility2D()),
                "visibility3D": bool(displayNode.GetVisibility3D()),
                "opacity3D": float(displayNode.GetOpacity3D()),
                "opacity2DFill": float(displayNode.GetOpacity2DFill()),
                "opacity2DOutline": float(displayNode.GetOpacity2DOutline()),
            }
            segmentIds = vtk.vtkStringArray()
            segmentation.GetSegmentIDs(segmentIds)
            for index in range(segmentIds.GetNumberOfValues()):
                segmentId = segmentIds.GetValue(index)
                state["segments"][segmentId] = {
                    "visibility": bool(
                        displayNode.GetSegmentVisibility(segmentId)
                    ),
                    "opacity3D": float(
                        displayNode.GetSegmentOpacity3D(segmentId)
                    ),
                    "opacity2DFill": float(
                        displayNode.GetSegmentOpacity2DFill(segmentId)
                    ),
                    "opacity2DOutline": float(
                        displayNode.GetSegmentOpacity2DOutline(segmentId)
                    ),
                }

        for node in displayableNodes:
            if (
                not node
                or not node.GetID()
                or not slicer.mrmlScene.IsNodePresent(node)
                or not node.IsA("vtkMRMLDisplayableNode")
            ):
                continue
            displayNode = node.GetDisplayNode()
            if not displayNode:
                continue
            nodeState = {"visibility": bool(displayNode.GetVisibility())}
            if hasattr(displayNode, "GetVisibility2D"):
                nodeState["visibility2D"] = bool(
                    displayNode.GetVisibility2D()
                )
            if hasattr(displayNode, "GetVisibility3D"):
                nodeState["visibility3D"] = bool(
                    displayNode.GetVisibility3D()
                )
            state["nodes"][node.GetID()] = nodeState
        return state

    @staticmethod
    def restoreWorkflowDisplayState(state: dict | None) -> None:
        """Restore a display snapshot without modifying MRML geometry."""

        if not state:
            return
        segmentationNodeId = state.get("segmentationNodeId")
        segmentationNode = (
            slicer.mrmlScene.GetNodeByID(segmentationNodeId)
            if segmentationNodeId
            else None
        )
        displayNode = (
            segmentationNode.GetDisplayNode() if segmentationNode else None
        )
        if displayNode and segmentationNode.GetSegmentation():
            displayState = state.get("segmentationDisplay", {})
            wasModifying = displayNode.StartModify()
            try:
                displayNode.SetVisibility(
                    bool(displayState.get("visibility", True))
                )
                displayNode.SetVisibility2D(
                    bool(displayState.get("visibility2D", True))
                )
                displayNode.SetVisibility3D(
                    bool(displayState.get("visibility3D", True))
                )
                displayNode.SetOpacity3D(
                    float(displayState.get("opacity3D", 1.0))
                )
                displayNode.SetOpacity2DFill(
                    float(displayState.get("opacity2DFill", 1.0))
                )
                displayNode.SetOpacity2DOutline(
                    float(displayState.get("opacity2DOutline", 1.0))
                )
                segmentation = segmentationNode.GetSegmentation()
                for segmentId, segmentState in state.get(
                    "segments", {}
                ).items():
                    if not segmentation.GetSegment(segmentId):
                        continue
                    displayNode.SetSegmentVisibility(
                        segmentId,
                        bool(segmentState.get("visibility", True)),
                    )
                    displayNode.SetSegmentOpacity3D(
                        segmentId,
                        float(segmentState.get("opacity3D", 1.0)),
                    )
                    displayNode.SetSegmentOpacity2DFill(
                        segmentId,
                        float(segmentState.get("opacity2DFill", 1.0)),
                    )
                    displayNode.SetSegmentOpacity2DOutline(
                        segmentId,
                        float(segmentState.get("opacity2DOutline", 1.0)),
                    )
            finally:
                displayNode.EndModify(wasModifying)

        for nodeId, nodeState in state.get("nodes", {}).items():
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            nodeDisplay = node.GetDisplayNode() if node else None
            if not nodeDisplay:
                continue
            nodeDisplay.SetVisibility(bool(nodeState.get("visibility", True)))
            if (
                "visibility2D" in nodeState
                and hasattr(nodeDisplay, "SetVisibility2D")
            ):
                nodeDisplay.SetVisibility2D(
                    bool(nodeState["visibility2D"])
                )
            if (
                "visibility3D" in nodeState
                and hasattr(nodeDisplay, "SetVisibility3D")
            ):
                nodeDisplay.SetVisibility3D(
                    bool(nodeState["visibility3D"])
                )

    def applyWorkflowDisplaySelection(
        self,
        segmentationNode: vtkMRMLSegmentationNode | None,
        visibleSegmentIds: set[str],
        managedDisplayableNodes: list,
        visibleNodeIds: set[str],
    ) -> dict:
        """Apply one display-only workflow selection by stable IDs."""

        existingVisibleSegmentIds = set()
        if segmentationNode:
            segmentation, displayNode = self._segmentationAndDisplayNode(
                segmentationNode
            )
            existingVisibleSegmentIds = {
                str(segmentId)
                for segmentId in visibleSegmentIds
                if segmentation.GetSegment(str(segmentId))
            }
            segmentIds = vtk.vtkStringArray()
            segmentation.GetSegmentIDs(segmentIds)
            wasModifying = displayNode.StartModify()
            try:
                hasVisibleMasks = bool(existingVisibleSegmentIds)
                displayNode.SetVisibility(hasVisibleMasks)
                displayNode.SetVisibility2D(hasVisibleMasks)
                displayNode.SetVisibility3D(hasVisibleMasks)
                for index in range(segmentIds.GetNumberOfValues()):
                    segmentId = segmentIds.GetValue(index)
                    visible = segmentId in existingVisibleSegmentIds
                    displayNode.SetSegmentVisibility(segmentId, visible)
                    if visible:
                        displayNode.SetSegmentOpacity3D(segmentId, 1.0)
                        displayNode.SetSegmentOpacity2DFill(segmentId, 1.0)
                        displayNode.SetSegmentOpacity2DOutline(segmentId, 1.0)
            finally:
                displayNode.EndModify(wasModifying)

        changedNodeIds = []
        for node in managedDisplayableNodes:
            if (
                not node
                or not node.GetID()
                or not slicer.mrmlScene.IsNodePresent(node)
            ):
                continue
            displayNode = node.GetDisplayNode()
            if not displayNode:
                continue
            visible = node.GetID() in visibleNodeIds
            if bool(displayNode.GetVisibility()) != visible:
                displayNode.SetVisibility(visible)
                changedNodeIds.append(node.GetID())
        return {
            "visibleSegmentIds": sorted(existingVisibleSegmentIds),
            "visibleNodeIds": sorted(visibleNodeIds),
            "changedNodeIds": changedNodeIds,
        }

    def setSegmentationSegmentHighlight(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str | None,
        contextOpacity: float = 0.25,
    ) -> None:
        """Emphasize one segment using display opacity without changing masks."""

        segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        if segmentId is not None and not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        contextOpacity = self._validatedOpacity(contextOpacity)
        segmentIds = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIds)
        wasModifying = displayNode.StartModify()
        try:
            for index in range(segmentIds.GetNumberOfValues()):
                currentSegmentId = segmentIds.GetValue(index)
                isHighlighted = segmentId is None or currentSegmentId == segmentId
                displayNode.SetSegmentOpacity3D(
                    currentSegmentId,
                    1.0 if isHighlighted else contextOpacity,
                )
                displayNode.SetSegmentOpacity2DFill(
                    currentSegmentId,
                    1.0 if isHighlighted else contextOpacity,
                )
                displayNode.SetSegmentOpacity2DOutline(
                    currentSegmentId,
                    1.0 if isHighlighted else 0.65,
                )
        finally:
            displayNode.EndModify(wasModifying)

    def applyTemplateSupportBoundaryFocus(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        sourceModel: vtkMRMLModelNode,
        contextModels: list[vtkMRMLModelNode | None] | None = None,
    ) -> dict:
        """Show only selected support-tooth masks and return exact display state.

        This is a transient placement aid.  It changes display nodes only and
        intentionally does not alter segmentation data, source geometry, or
        persisted workflow references.
        """

        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        if sourceSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale draft support model first."))
        if sourceSummary["sourceSegmentation"] is not segmentationNode:
            raise ValueError(
                _("The draft support model does not belong to this segmentation.")
            )
        segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        subjectSegmentIds = [
            sourceSummary["targetSegmentId"],
            *sourceSummary["supportSegmentIds"],
        ]
        if not subjectSegmentIds or any(
            not segmentation.GetSegment(segmentId)
            for segmentId in subjectSegmentIds
        ):
            raise ValueError(
                _("The draft support model references a missing tooth segment.")
            )

        segmentIds = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIds)
        state = {
            "segmentationNodeId": segmentationNode.GetID(),
            "subjectSegmentIds": list(subjectSegmentIds),
            "display": {
                "visibility": bool(displayNode.GetVisibility()),
                "visibility2D": bool(displayNode.GetVisibility2D()),
                "visibility3D": bool(displayNode.GetVisibility3D()),
                "opacity3D": float(displayNode.GetOpacity3D()),
                "opacity2DFill": float(displayNode.GetOpacity2DFill()),
                "opacity2DOutline": float(displayNode.GetOpacity2DOutline()),
            },
            "segments": {},
            "contextModels": {},
        }
        for index in range(segmentIds.GetNumberOfValues()):
            segmentId = segmentIds.GetValue(index)
            state["segments"][segmentId] = {
                "visibility": bool(displayNode.GetSegmentVisibility(segmentId)),
                "opacity3D": float(displayNode.GetSegmentOpacity3D(segmentId)),
                "opacity2DFill": float(
                    displayNode.GetSegmentOpacity2DFill(segmentId)
                ),
                "opacity2DOutline": float(
                    displayNode.GetSegmentOpacity2DOutline(segmentId)
                ),
            }

        seenModelIds = set()
        for modelNode in contextModels or []:
            if (
                not modelNode
                or not modelNode.IsA("vtkMRMLModelNode")
                or not modelNode.GetID()
                or modelNode.GetID() in seenModelIds
            ):
                continue
            seenModelIds.add(modelNode.GetID())
            modelNode.CreateDefaultDisplayNodes()
            modelDisplay = modelNode.GetDisplayNode()
            if modelDisplay:
                state["contextModels"][modelNode.GetID()] = {
                    "visibility": bool(modelDisplay.GetVisibility()),
                }

        try:
            selectedIds = set(subjectSegmentIds)
            wasModifying = displayNode.StartModify()
            try:
                displayNode.SetVisibility(True)
                displayNode.SetVisibility2D(True)
                displayNode.SetVisibility3D(True)
                displayNode.SetOpacity3D(1.0)
                displayNode.SetOpacity2DFill(1.0)
                displayNode.SetOpacity2DOutline(1.0)
                for segmentId in state["segments"]:
                    selected = segmentId in selectedIds
                    displayNode.SetSegmentVisibility(segmentId, selected)
                    if selected:
                        displayNode.SetSegmentOpacity3D(segmentId, 1.0)
                        displayNode.SetSegmentOpacity2DFill(segmentId, 1.0)
                        displayNode.SetSegmentOpacity2DOutline(segmentId, 1.0)
            finally:
                displayNode.EndModify(wasModifying)
            for modelId in state["contextModels"]:
                modelNode = slicer.mrmlScene.GetNodeByID(modelId)
                modelDisplay = modelNode.GetDisplayNode() if modelNode else None
                if modelDisplay:
                    modelDisplay.SetVisibility(False)
        except Exception:
            self.restoreTemplateSupportBoundaryFocus(state)
            raise

        state["hiddenSegmentCount"] = sum(
            segmentId not in set(subjectSegmentIds)
            for segmentId in state["segments"]
        )
        return state

    def applyTargetToothFocus(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        boundsRoi: vtkMRMLMarkupsROINode | None,
    ) -> dict:
        """Temporarily isolate one target mask and make its bounds visible."""

        targetRecord = self.validateTargetTooth(segmentationNode, segmentId)
        if not self.isTargetBoundsRoiForTarget(
            boundsRoi,
            segmentationNode,
            targetRecord["segmentId"],
        ):
            raise ValueError(_("Create or restore the target-tooth bounds first."))
        segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        segmentIds = vtk.vtkStringArray()
        segmentation.GetSegmentIDs(segmentIds)
        state = {
            "segmentationNodeId": segmentationNode.GetID(),
            "subjectSegmentIds": [targetRecord["segmentId"]],
            "display": {
                "visibility": bool(displayNode.GetVisibility()),
                "visibility2D": bool(displayNode.GetVisibility2D()),
                "visibility3D": bool(displayNode.GetVisibility3D()),
                "opacity3D": float(displayNode.GetOpacity3D()),
                "opacity2DFill": float(displayNode.GetOpacity2DFill()),
                "opacity2DOutline": float(displayNode.GetOpacity2DOutline()),
            },
            "segments": {},
            "contextModels": {},
            "boundsRoiNodeId": boundsRoi.GetID(),
            "boundsRoiVisibility": bool(
                boundsRoi.GetDisplayNode()
                and boundsRoi.GetDisplayNode().GetVisibility()
            ),
        }
        for index in range(segmentIds.GetNumberOfValues()):
            currentSegmentId = segmentIds.GetValue(index)
            state["segments"][currentSegmentId] = {
                "visibility": bool(
                    displayNode.GetSegmentVisibility(currentSegmentId)
                ),
                "opacity3D": float(
                    displayNode.GetSegmentOpacity3D(currentSegmentId)
                ),
                "opacity2DFill": float(
                    displayNode.GetSegmentOpacity2DFill(currentSegmentId)
                ),
                "opacity2DOutline": float(
                    displayNode.GetSegmentOpacity2DOutline(currentSegmentId)
                ),
            }
        try:
            wasModifying = displayNode.StartModify()
            try:
                displayNode.SetVisibility(True)
                displayNode.SetVisibility2D(True)
                displayNode.SetVisibility3D(True)
                displayNode.SetOpacity3D(1.0)
                displayNode.SetOpacity2DFill(1.0)
                displayNode.SetOpacity2DOutline(1.0)
                for currentSegmentId in state["segments"]:
                    selected = currentSegmentId == targetRecord["segmentId"]
                    displayNode.SetSegmentVisibility(currentSegmentId, selected)
                    if selected:
                        displayNode.SetSegmentOpacity3D(currentSegmentId, 1.0)
                        displayNode.SetSegmentOpacity2DFill(currentSegmentId, 1.0)
                        displayNode.SetSegmentOpacity2DOutline(currentSegmentId, 1.0)
            finally:
                displayNode.EndModify(wasModifying)
            boundsRoi.CreateDefaultDisplayNodes()
            boundsRoi.GetDisplayNode().SetVisibility(True)
            self.enforceWorkflowRoiNonInteractive(boundsRoi)
        except Exception:
            self.restoreTargetToothFocus(state)
            raise
        return state

    @staticmethod
    def restoreTargetToothFocus(state: dict | None) -> None:
        if not state:
            return
        DENTOWorkflowLogic.restoreTemplateSupportBoundaryFocus(state)
        roiNodeId = state.get("boundsRoiNodeId")
        roiNode = slicer.mrmlScene.GetNodeByID(roiNodeId) if roiNodeId else None
        displayNode = roiNode.GetDisplayNode() if roiNode else None
        if displayNode:
            displayNode.SetVisibility(bool(state.get("boundsRoiVisibility", True)))

    @staticmethod
    def restoreTemplateSupportBoundaryFocus(state: dict | None) -> None:
        """Restore a state returned by ``applyTemplateSupportBoundaryFocus``."""

        if not state:
            return
        segmentationNodeId = state.get("segmentationNodeId")
        segmentationNode = (
            slicer.mrmlScene.GetNodeByID(segmentationNodeId)
            if segmentationNodeId
            else None
        )
        displayNode = (
            segmentationNode.GetDisplayNode() if segmentationNode else None
        )
        displayState = state.get("display", {})
        segmentStates = state.get("segments", {})
        if displayNode and segmentationNode.GetSegmentation():
            segmentation = segmentationNode.GetSegmentation()
            wasModifying = displayNode.StartModify()
            try:
                displayNode.SetVisibility(bool(displayState.get("visibility", True)))
                displayNode.SetVisibility2D(
                    bool(displayState.get("visibility2D", True))
                )
                displayNode.SetVisibility3D(
                    bool(displayState.get("visibility3D", True))
                )
                displayNode.SetOpacity3D(float(displayState.get("opacity3D", 1.0)))
                displayNode.SetOpacity2DFill(
                    float(displayState.get("opacity2DFill", 1.0))
                )
                displayNode.SetOpacity2DOutline(
                    float(displayState.get("opacity2DOutline", 1.0))
                )
                for segmentId, segmentState in segmentStates.items():
                    if not segmentation.GetSegment(segmentId):
                        continue
                    displayNode.SetSegmentVisibility(
                        segmentId,
                        bool(segmentState.get("visibility", True)),
                    )
                    displayNode.SetSegmentOpacity3D(
                        segmentId,
                        float(segmentState.get("opacity3D", 1.0)),
                    )
                    displayNode.SetSegmentOpacity2DFill(
                        segmentId,
                        float(segmentState.get("opacity2DFill", 1.0)),
                    )
                    displayNode.SetSegmentOpacity2DOutline(
                        segmentId,
                        float(segmentState.get("opacity2DOutline", 1.0)),
                    )
            finally:
                displayNode.EndModify(wasModifying)

        for modelId, modelState in state.get("contextModels", {}).items():
            modelNode = slicer.mrmlScene.GetNodeByID(modelId)
            modelDisplay = modelNode.GetDisplayNode() if modelNode else None
            if modelDisplay:
                modelDisplay.SetVisibility(bool(modelState.get("visibility", True)))

    def setSegmentationVisibility2D(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        visible: bool,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        displayNode.SetVisibility(True)
        displayNode.SetVisibility2D(bool(visible))

    def getSegmentation2DRenderingMode(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> str:
        """Return the persisted display-only review/edit rendering choice."""

        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        storedMode = segmentationNode.GetAttribute(
            self.SEGMENTATION_2D_RENDERING_MODE_ATTRIBUTE
        )
        if storedMode in (
            self.SEGMENTATION_2D_RENDERING_MODE_SMOOTH,
            self.SEGMENTATION_2D_RENDERING_MODE_NATIVE,
        ):
            return storedMode
        preferredRepresentation = (
            displayNode.GetPreferredDisplayRepresentationName2D() or ""
        )
        actualRepresentation = displayNode.GetDisplayRepresentationName2D() or ""
        if self.SEGMENTATION_CLOSED_SURFACE_REPRESENTATION in (
            preferredRepresentation,
            actualRepresentation,
        ):
            return self.SEGMENTATION_2D_RENDERING_MODE_SMOOTH
        return self.SEGMENTATION_2D_RENDERING_MODE_NATIVE

    def setSegmentation2DRenderingMode(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        mode: str,
    ) -> None:
        """Switch slice display representation without modifying mask anatomy."""

        segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        if mode == self.SEGMENTATION_2D_RENDERING_MODE_SMOOTH:
            if not segmentation.ContainsRepresentation(
                self.SEGMENTATION_CLOSED_SURFACE_REPRESENTATION
            ):
                if not segmentationNode.CreateClosedSurfaceRepresentation():
                    raise RuntimeError(
                        _(
                            "Slicer could not generate the derived closed surfaces "
                            "needed for smooth 2D review."
                        )
                    )
            representationName = (
                self.SEGMENTATION_CLOSED_SURFACE_REPRESENTATION
            )
        elif mode == self.SEGMENTATION_2D_RENDERING_MODE_NATIVE:
            representationName = (
                self.SEGMENTATION_BINARY_LABELMAP_REPRESENTATION
            )
        else:
            raise ValueError(_("The 2D segmentation rendering mode is invalid."))

        wasModifying = segmentationNode.StartModify()
        try:
            displayNode.SetPreferredDisplayRepresentationName2D(
                representationName
            )
            segmentationNode.SetAttribute(
                self.SEGMENTATION_2D_RENDERING_MODE_ATTRIBUTE,
                mode,
            )
        finally:
            segmentationNode.EndModify(wasModifying)

    def ensureSegmentationDisplayQualityDefaults(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> str:
        """Migrate older scenes to the authoritative native-mask display."""

        _segmentation, _displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        storedMode = segmentationNode.GetAttribute(
            self.SEGMENTATION_2D_RENDERING_MODE_ATTRIBUTE
        )
        if storedMode in (
            self.SEGMENTATION_2D_RENDERING_MODE_SMOOTH,
            self.SEGMENTATION_2D_RENDERING_MODE_NATIVE,
        ):
            self.setSegmentation2DRenderingMode(segmentationNode, storedMode)
            return storedMode

        defaultMode = self.SEGMENTATION_2D_RENDERING_MODE_NATIVE
        self.setSegmentation2DRenderingMode(segmentationNode, defaultMode)
        return defaultMode

    @staticmethod
    def _scalarVolumeDisplayNode(
        volumeNode: vtkMRMLScalarVolumeNode,
    ):
        if not volumeNode or not volumeNode.IsA("vtkMRMLScalarVolumeNode"):
            raise ValueError(_("Select a valid scalar CBCT volume."))
        volumeNode.CreateDefaultDisplayNodes()
        displayNode = volumeNode.GetDisplayNode()
        if not displayNode or not displayNode.IsA(
            "vtkMRMLScalarVolumeDisplayNode"
        ):
            raise ValueError(_("The source CBCT display node is unavailable."))
        return displayNode

    @classmethod
    def getScalarVolumeInterpolation(
        cls,
        volumeNode: vtkMRMLScalarVolumeNode,
    ) -> bool:
        displayNode = cls._scalarVolumeDisplayNode(volumeNode)
        return bool(displayNode.GetInterpolate())

    @classmethod
    def setScalarVolumeInterpolation(
        cls,
        volumeNode: vtkMRMLScalarVolumeNode,
        enabled: bool,
    ) -> None:
        displayNode = cls._scalarVolumeDisplayNode(volumeNode)
        displayNode.SetInterpolate(bool(enabled))

    @classmethod
    def getScalarVolumeDisplaySettings(
        cls,
        volumeNode: vtkMRMLScalarVolumeNode,
    ) -> dict[str, object]:
        """Return native display mapping only; image voxels are never read/written."""

        displayNode = cls._scalarVolumeDisplayNode(volumeNode)
        colorNodeId = displayNode.GetColorNodeID() or ""
        return {
            "autoWindowLevel": bool(displayNode.GetAutoWindowLevel()),
            "window": float(displayNode.GetWindow()),
            "level": float(displayNode.GetLevel()),
            "interpolate": bool(displayNode.GetInterpolate()),
            "colorNodeId": colorNodeId,
            "invertedGrayscale": (
                colorNodeId == cls.SCALAR_VOLUME_INVERTED_GREY_COLOR_NODE_ID
            ),
        }

    @classmethod
    def setScalarVolumeAutoWindowLevel(
        cls,
        volumeNode: vtkMRMLScalarVolumeNode,
        enabled: bool,
    ) -> None:
        displayNode = cls._scalarVolumeDisplayNode(volumeNode)
        displayNode.SetAutoWindowLevel(bool(enabled))

    @classmethod
    def setScalarVolumeWindowLevel(
        cls,
        volumeNode: vtkMRMLScalarVolumeNode,
        window: float,
        level: float,
    ) -> None:
        window = float(window)
        level = float(level)
        if not math.isfinite(window) or window <= 0.0:
            raise ValueError(_("CBCT display window must be greater than zero."))
        if not math.isfinite(level):
            raise ValueError(_("CBCT display level must be finite."))
        displayNode = cls._scalarVolumeDisplayNode(volumeNode)
        wasModifying = displayNode.StartModify()
        try:
            displayNode.SetAutoWindowLevel(False)
            displayNode.SetWindowLevel(window, level)
        finally:
            displayNode.EndModify(wasModifying)

    @classmethod
    def setScalarVolumeInvertedGrayscale(
        cls,
        volumeNode: vtkMRMLScalarVolumeNode,
        inverted: bool,
    ) -> None:
        displayNode = cls._scalarVolumeDisplayNode(volumeNode)
        displayNode.SetAndObserveColorNodeID(
            cls.SCALAR_VOLUME_INVERTED_GREY_COLOR_NODE_ID
            if inverted
            else cls.SCALAR_VOLUME_GREY_COLOR_NODE_ID
        )

    @classmethod
    def restoreScalarVolumeDisplaySettings(
        cls,
        volumeNode: vtkMRMLScalarVolumeNode,
        settings: dict[str, object],
    ) -> None:
        """Restore a captured scalar-display state without touching image data."""

        if not isinstance(settings, dict):
            raise ValueError(_("The CBCT display baseline is invalid."))
        window = float(settings.get("window", math.nan))
        level = float(settings.get("level", math.nan))
        if not math.isfinite(window) or window <= 0.0 or not math.isfinite(level):
            raise ValueError(_("The CBCT display baseline has invalid window/level."))
        displayNode = cls._scalarVolumeDisplayNode(volumeNode)
        colorNodeId = str(settings.get("colorNodeId") or "")
        wasModifying = displayNode.StartModify()
        try:
            displayNode.SetAutoWindowLevel(False)
            displayNode.SetWindowLevel(window, level)
            displayNode.SetInterpolate(bool(settings.get("interpolate", True)))
            displayNode.SetAndObserveColorNodeID(
                colorNodeId or cls.SCALAR_VOLUME_GREY_COLOR_NODE_ID
            )
            displayNode.SetAutoWindowLevel(
                bool(settings.get("autoWindowLevel", False))
            )
        finally:
            displayNode.EndModify(wasModifying)

    def setSegmentationVisibility3D(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        visible: bool,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        displayNode.SetVisibility(True)
        displayNode.SetVisibility3D(bool(visible))

    def setSegmentationOpacity2D(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        opacity: float,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        opacity = self._validatedOpacity(opacity)
        displayNode.SetOpacity2DFill(opacity)
        displayNode.SetOpacity2DOutline(opacity)

    def setSegmentationOpacity3D(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        opacity: float,
    ) -> None:
        _segmentation, displayNode = self._segmentationAndDisplayNode(
            segmentationNode
        )
        displayNode.SetOpacity3D(self._validatedOpacity(opacity))

    @staticmethod
    def _validatedOpacity(opacity: float) -> float:
        opacity = float(opacity)
        if not math.isfinite(opacity) or opacity < 0.0 or opacity > 1.0:
            raise ValueError(_("Segmentation opacity must be between 0 and 1."))
        return opacity
