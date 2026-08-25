"""Extracted workflow lineage methods; public APIs remain on WorkflowLogicMixin."""

from __future__ import annotations

from .runtime import *


class LineageLogicMixin:
    def getScalarVolumeNodes(self) -> list[vtkMRMLScalarVolumeNode]:
        return list(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"))

    def getLatestScalarVolumeNode(self) -> vtkMRMLScalarVolumeNode | None:
        volumeNodes = self.getScalarVolumeNodes()
        return volumeNodes[-1] if volumeNodes else None

    def getLatestTeethSegmentationNode(self) -> vtkMRMLSegmentationNode | None:
        """Return the latest Bridge C result, without selecting unrelated nodes."""

        segmentationNodes = list(
            slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        )
        bridgeResults = [
            node
            for node in segmentationNodes
            if node.GetAttribute("DENTOBOT.BridgeOperation") == "segment-teeth"
        ]
        return bridgeResults[-1] if bridgeResults else None

    def getTargetToothRecords(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> list[dict]:
        """Return only whole-tooth segments eligible for draft targeting."""

        return [
            record
            for record in self.getSegmentationReviewRecords(segmentationNode)
            if record["category"] == "Teeth"
        ]

    @staticmethod
    def dentalArchForFdi(fdiNumber: str) -> str:
        """Return Upper/Lower for a permanent-tooth FDI code, else empty."""

        match = re.fullmatch(r"([1-4])([1-8])", str(fdiNumber or "").strip())
        if not match:
            return ""
        return "Upper" if match.group(1) in {"1", "2"} else "Lower"

    def validateTargetTooth(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Return the selected whole-tooth record or raise an actionable error."""

        if not isinstance(segmentId, str) or not segmentId.strip():
            raise ValueError(_("Select a target tooth before planning."))
        targetId = segmentId.strip()
        targetRecords = {
            record["segmentId"]: record
            for record in self.getTargetToothRecords(segmentationNode)
        }
        record = targetRecords.get(targetId)
        if not record:
            raise ValueError(
                _(
                    "The selected target does not exist or is not a whole-tooth "
                    "segment."
                )
            )
        return record

    def getTargetToothBoundsWorld(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> tuple[float, float, float, float, float, float]:
        """Return finite axis-aligned world-RAS bounds for one whole tooth."""

        self.validateTargetTooth(segmentationNode, segmentId)
        try:
            return self.getSegmentationSegmentBoundsWorld(
                segmentationNode,
                segmentId,
            )
        except ValueError as exc:
            raise ValueError(
                _(
                    "The selected target tooth has no closed surface from "
                    "which to calculate placement bounds."
                )
            ) from exc

    def getSegmentationSegmentBoundsWorld(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> tuple[float, float, float, float, float, float]:
        """Return finite world-RAS bounds for any existing segment surface."""

        if not segmentationNode or not segmentationNode.IsA(
            "vtkMRMLSegmentationNode"
        ):
            raise ValueError(_("A teeth segmentation is required."))
        segmentation = segmentationNode.GetSegmentation()
        if not segmentId or not segmentation or not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        closedSurface = self._getClosedSurfaceWorldCopy(
            segmentationNode,
            segmentId,
        )
        bounds = tuple(float(value) for value in closedSurface.GetBounds())
        if (
            len(bounds) != 6
            or any(not math.isfinite(value) for value in bounds)
            or any(
                bounds[axis * 2 + 1] <= bounds[axis * 2]
                for axis in range(3)
            )
        ):
            raise ValueError(
                _("The selected segment has invalid world-RAS bounds.")
            )
        return bounds

    @staticmethod
    def formatRasBounds(
        bounds: tuple[float, float, float, float, float, float],
    ) -> str:
        """Format world-RAS axis-aligned bounds for the planning panel."""

        if len(bounds) != 6:
            raise ValueError(_("Six target-bound values are required."))
        return (
            f"R [{bounds[0]:.3f}, {bounds[1]:.3f}], "
            f"A [{bounds[2]:.3f}, {bounds[3]:.3f}], "
            f"S [{bounds[4]:.3f}, {bounds[5]:.3f}] mm"
        )

    @staticmethod
    def lineageColorForTarget(
        segmentId: str,
        fdiNumber: str = "",
    ) -> tuple[float, float, float]:
        """Return a stable vivid color for one authoritative target tooth."""

        normalizedSegmentId = str(segmentId or "").strip()
        if not normalizedSegmentId:
            raise ValueError(_("A target segment ID is required for lineage color."))
        fdiMatch = re.fullmatch(r"([1-4])([1-8])", str(fdiNumber or ""))
        if fdiMatch:
            ordinal = (int(fdiMatch.group(1)) - 1) * 8 + int(
                fdiMatch.group(2)
            ) - 1
        else:
            ordinal = (
                uuid.uuid5(uuid.NAMESPACE_OID, normalizedSegmentId).int % 32
            )
        hue = (0.055 + ordinal * 0.618033988749895) % 1.0
        return tuple(
            round(float(component), 6)
            for component in colorsys.hsv_to_rgb(hue, 0.74, 0.94)
        )

    @classmethod
    def lineageColorFromNode(cls, node) -> tuple[float, float, float] | None:
        """Read a validated persisted target-lineage color from one node."""

        if not node:
            return None
        try:
            values = json.loads(
                node.GetAttribute(cls.LINEAGE_COLOR_ATTRIBUTE) or "null"
            )
        except (json.JSONDecodeError, TypeError):
            return None
        if (
            not isinstance(values, list)
            or len(values) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
                or float(value) > 1.0
                for value in values
            )
        ):
            return None
        return tuple(float(value) for value in values)

    @classmethod
    def setNodeLineageColor(
        cls,
        node,
        color: tuple[float, float, float],
        segmentId: str,
        fdiNumber: str = "",
    ) -> bool:
        """Persist and display one visual lineage color without changing identity."""

        normalizedColor = tuple(round(float(value), 6) for value in color)
        if (
            len(normalizedColor) != 3
            or any(
                not math.isfinite(value) or value < 0.0 or value > 1.0
                for value in normalizedColor
            )
        ):
            raise ValueError(_("A lineage color must contain three RGB values."))
        serializedColor = json.dumps(
            list(normalizedColor),
            separators=(",", ":"),
        )
        normalizedSegmentId = str(segmentId or "").strip()
        normalizedFdi = str(fdiNumber or "").strip()
        changed = any(
            (
                node.GetAttribute(cls.LINEAGE_COLOR_ATTRIBUTE)
                != serializedColor,
                node.GetAttribute(cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE)
                != normalizedSegmentId,
                node.GetAttribute(cls.LINEAGE_TARGET_FDI_ATTRIBUTE)
                != normalizedFdi,
            )
        )
        if changed:
            wasModifying = node.StartModify()
            try:
                node.SetAttribute(cls.LINEAGE_COLOR_ATTRIBUTE, serializedColor)
                node.SetAttribute(
                    cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE,
                    normalizedSegmentId,
                )
                node.SetAttribute(
                    cls.LINEAGE_TARGET_FDI_ATTRIBUTE,
                    normalizedFdi,
                )
            finally:
                node.EndModify(wasModifying)
        if node.IsA("vtkMRMLDisplayableNode"):
            node.CreateDefaultDisplayNodes()
            displayNode = node.GetDisplayNode()
            if displayNode:
                displayNode.SetColor(*normalizedColor)
                if hasattr(displayNode, "SetSelectedColor"):
                    displayNode.SetSelectedColor(*normalizedColor)
                if hasattr(displayNode, "SetActiveColor"):
                    displayNode.SetActiveColor(*normalizedColor)
        return changed

    @classmethod
    def clearNodeLineageColor(cls, node) -> None:
        if not node:
            return
        attributeNames = (
            cls.LINEAGE_COLOR_ATTRIBUTE,
            cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE,
            cls.LINEAGE_TARGET_FDI_ATTRIBUTE,
        )
        if not any(node.GetAttribute(name) for name in attributeNames):
            return
        wasModifying = node.StartModify()
        try:
            for attributeName in attributeNames:
                node.SetAttribute(attributeName, None)
        finally:
            node.EndModify(wasModifying)

    def dentobotTrajectoriesForTarget(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> list[vtkMRMLMarkupsLineNode]:
        """Return every DENTOBOT trajectory in one authoritative tooth group."""

        segmentationId = segmentationNode.GetID() if segmentationNode else None
        return [
            node
            for node in slicer.util.getNodesByClass(
                "vtkMRMLMarkupsLineNode"
            )
            if (
                self.isDentobotTrajectoryNode(node)
                and node.GetAttribute("DENTOBOT.TargetSegmentID") == segmentId
                and node.GetNodeReference(
                    self.TARGET_SEGMENTATION_REFERENCE_ROLE
                )
                and node.GetNodeReference(
                    self.TARGET_SEGMENTATION_REFERENCE_ROLE
                ).GetID()
                == segmentationId
            )
        ]

    def isTargetBoundsRoiForTarget(
        self,
        roiNode: vtkMRMLMarkupsROINode | None,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> bool:
        """Return whether an ROI is the exact Step 4A bounds for one tooth."""

        referencedSegmentation = (
            roiNode.GetNodeReference(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
            )
            if roiNode and roiNode.IsA("vtkMRMLMarkupsROINode")
            else None
        )
        return bool(
            referencedSegmentation
            and segmentationNode
            and referencedSegmentation.GetID() == segmentationNode.GetID()
            and roiNode.GetAttribute("DENTOBOT.BoundsRole")
            == "TargetToothAABB"
            and roiNode.GetAttribute("DENTOBOT.TargetSegmentID") == segmentId
        )

    def findTargetBoundsRoi(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> vtkMRMLMarkupsROINode | None:
        """Find an existing exact target ROI so tooth switching creates no duplicate."""

        for roiNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsROINode"
        ):
            if self.isTargetBoundsRoiForTarget(
                roiNode,
                segmentationNode,
                segmentId,
            ):
                return roiNode
        return None

    def refreshWorkflowLineageColors(self) -> list[str]:
        """Propagate target-tooth colors through role/reference-linked descendants."""

        changedNodeIds = []
        groupColors: dict[tuple[str, str], tuple[float, float, float]] = {}
        groupFdi: dict[tuple[str, str], str] = {}
        for trajectoryNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsLineNode"
        ):
            if not self.isDentobotTrajectoryNode(trajectoryNode):
                continue
            try:
                self.enforceTrajectoryControlPointInvariant(trajectoryNode)
                segmentationNode = trajectoryNode.GetNodeReference(
                    self.TARGET_SEGMENTATION_REFERENCE_ROLE
                )
                segmentId = trajectoryNode.GetAttribute(
                    "DENTOBOT.TargetSegmentID"
                ) or ""
                targetRecord = self.validateTargetTooth(
                    segmentationNode,
                    segmentId,
                )
            except ValueError:
                continue
            key = (segmentationNode.GetID(), segmentId)
            fdiNumber = targetRecord.get("fdiNumber") or ""
            color = self.lineageColorForTarget(segmentId, fdiNumber)
            groupColors[key] = color
            groupFdi[key] = fdiNumber
            if self.setNodeLineageColor(
                trajectoryNode,
                color,
                segmentId,
                fdiNumber,
            ):
                changedNodeIds.append(trajectoryNode.GetID())

        for roiNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsROINode"
        ):
            if roiNode.GetAttribute("DENTOBOT.BoundsRole") != "TargetToothAABB":
                continue
            segmentationNode = roiNode.GetNodeReference(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
            )
            segmentId = roiNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
            key = (
                segmentationNode.GetID() if segmentationNode else "",
                segmentId,
            )
            color = groupColors.get(key)
            if color and self.setNodeLineageColor(
                roiNode,
                color,
                segmentId,
                groupFdi.get(key, ""),
            ):
                changedNodeIds.append(roiNode.GetID())

        supportLineages: dict[str, tuple[tuple[float, float, float], str, str]] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isDraftTemplateSupportModelNode(modelNode):
                continue
            segmentationNode = modelNode.GetNodeReference(
                self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE
            )
            segmentId = modelNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
            key = (
                segmentationNode.GetID() if segmentationNode else "",
                segmentId,
            )
            color = groupColors.get(key)
            if not color:
                continue
            fdiNumber = groupFdi.get(key, "")
            if self.setNodeLineageColor(
                modelNode,
                color,
                segmentId,
                fdiNumber,
            ):
                changedNodeIds.append(modelNode.GetID())
            supportLineages[modelNode.GetID()] = (
                color,
                segmentId,
                fdiNumber,
            )

        for curveNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsClosedCurveNode"
        ):
            if not self.isTemplateSupportBoundaryNode(curveNode):
                continue
            supportModel = curveNode.GetNodeReference(
                self.TEMPLATE_SUPPORT_BOUNDARY_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(curveNode, *lineage):
                changedNodeIds.append(curveNode.GetID())
        for planeNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsPlaneNode"
        ):
            if not self.isTemplateSupportBoundaryPlaneNode(planeNode):
                continue
            supportModel = planeNode.GetNodeReference(
                self.TEMPLATE_SUPPORT_PLANE_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(planeNode, *lineage):
                changedNodeIds.append(planeNode.GetID())

        visibleSupportLineages: dict[
            str,
            tuple[tuple[float, float, float], str, str],
        ] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isVisibleTemplateSupportModelNode(modelNode):
                continue
            supportModel = modelNode.GetNodeReference(
                self.TEMPLATE_VISIBLE_SUPPORT_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
            if lineage:
                visibleSupportLineages[modelNode.GetID()] = lineage

        for lineNode in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode"):
            if not self.isTemplateInsertionDirectionNode(lineNode):
                continue
            visibleSupport = lineNode.GetNodeReference(
                self.TEMPLATE_INSERTION_DIRECTION_SOURCE_SURFACE_REFERENCE_ROLE
            )
            lineage = (
                visibleSupportLineages.get(visibleSupport.GetID())
                if visibleSupport
                else None
            )
            if lineage and self.setNodeLineageColor(lineNode, *lineage):
                changedNodeIds.append(lineNode.GetID())

        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not (
                self.isTemplateUndercutSurfaceModelNode(modelNode)
                or self.isTemplateUndercutBlockoutModelNode(modelNode)
            ):
                continue
            visibleSupport = modelNode.GetNodeReference(
                self.TEMPLATE_UNDERCUT_SOURCE_SURFACE_REFERENCE_ROLE
            )
            lineage = (
                visibleSupportLineages.get(visibleSupport.GetID())
                if visibleSupport
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())

        patientShellLineages: dict[
            str,
            tuple[tuple[float, float, float], str, str],
        ] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isPatientContactShellModelNode(modelNode):
                continue
            visibleSupport = modelNode.GetNodeReference(
                self.TEMPLATE_PATIENT_SHELL_SOURCE_SURFACE_REFERENCE_ROLE
            )
            lineage = (
                visibleSupportLineages.get(visibleSupport.GetID())
                if visibleSupport
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
            if lineage:
                patientShellLineages[modelNode.GetID()] = lineage

        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if modelNode.GetAttribute("DENTOBOT.ModelRole") not in {
                "TemplateDockingAssembly",
                "TemplateDockingClearance",
                "TemplateDockingReinforcement",
                "TemplateDockingChannels",
                "FinalPrintableTemplate",
            }:
                continue
            patientShell = modelNode.GetNodeReference(
                self.TEMPLATE_FINAL_GUIDE_PATIENT_SHELL_REFERENCE_ROLE
            )
            lineage = (
                patientShellLineages.get(patientShell.GetID())
                if patientShell
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())

        for roiNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsROINode"
        ):
            if not self.isTemplateShellRoiNode(roiNode):
                continue
            supportModel = roiNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(roiNode, *lineage):
                changedNodeIds.append(roiNode.GetID())

        researchLineages: dict[str, tuple[tuple[float, float, float], str, str]] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isResearchTemplateModelNode(modelNode):
                continue
            supportModel = modelNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
            if lineage:
                researchLineages[modelNode.GetID()] = lineage

        for className, acceptsNode in (
            ("vtkMRMLMarkupsPlaneNode", self.isTemplateTrimPlaneNode),
            ("vtkMRMLMarkupsClosedCurveNode", self.isTemplateTrimCurveNode),
        ):
            for markupNode in slicer.util.getNodesByClass(className):
                if not acceptsNode(markupNode):
                    continue
                sourceShell = markupNode.GetNodeReference(
                    self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
                )
                lineage = (
                    researchLineages.get(sourceShell.GetID())
                    if sourceShell
                    else None
                )
                if lineage and self.setNodeLineageColor(markupNode, *lineage):
                    changedNodeIds.append(markupNode.GetID())

        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isFinalizedTemplateShellModelNode(modelNode):
                continue
            sourceShell = modelNode.GetNodeReference(
                self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
            )
            lineage = (
                researchLineages.get(sourceShell.GetID())
                if sourceShell
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
        return changedNodeIds

    def applyTrajectoryGroupEmphasis(
        self,
        segmentationNode: vtkMRMLSegmentationNode | None,
        activeSegmentId: str,
        activeTrajectoryNode: vtkMRMLMarkupsLineNode | None = None,
    ) -> None:
        """Emphasize the exact selected trajectory and then its tooth group."""

        activeSegmentationId = (
            segmentationNode.GetID() if segmentationNode else ""
        )
        for trajectoryNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsLineNode"
        ):
            if not self.isDentobotTrajectoryNode(trajectoryNode):
                continue
            displayNode = trajectoryNode.GetDisplayNode()
            if not displayNode:
                continue
            targetSegmentation = trajectoryNode.GetNodeReference(
                self.TARGET_SEGMENTATION_REFERENCE_ROLE
            )
            isActiveGroup = bool(
                activeSegmentId
                and targetSegmentation
                and targetSegmentation.GetID() == activeSegmentationId
                and trajectoryNode.GetAttribute("DENTOBOT.TargetSegmentID")
                == activeSegmentId
            )
            hasActiveGroup = bool(activeSegmentationId and activeSegmentId)
            isSelected = bool(
                activeTrajectoryNode
                and trajectoryNode.GetID() == activeTrajectoryNode.GetID()
            )
            if isSelected:
                displayNode.SetVisibility(True)
                if hasattr(displayNode, "SetVisibility2D"):
                    displayNode.SetVisibility2D(True)
                if hasattr(displayNode, "SetVisibility3D"):
                    displayNode.SetVisibility3D(True)
                opacity, thickness, glyphScale = 1.0, 0.75, 1.65
            elif isActiveGroup and activeTrajectoryNode:
                opacity, thickness, glyphScale = 0.32, 0.24, 0.95
            elif isActiveGroup:
                opacity, thickness, glyphScale = 1.0, 0.55, 1.45
            elif hasActiveGroup:
                opacity, thickness, glyphScale = 0.38, 0.20, 0.90
            else:
                opacity, thickness, glyphScale = 0.68, 0.25, 1.0
            displayNode.SetOpacity(opacity)
            displayNode.SetLineThickness(thickness)
            displayNode.SetGlyphScale(glyphScale)
            displayNode.SetPointLabelsVisibility(isSelected or (
                isActiveGroup and activeTrajectoryNode is None
            ))
