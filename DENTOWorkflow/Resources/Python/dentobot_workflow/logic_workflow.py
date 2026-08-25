"""Extracted workflow lineage and trajectories methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.logic_lineage import LineageLogicMixin


from dentobot_workflow.logic_planning_dependencies import PlanningDependencyLogicMixin


class WorkflowLogicMixin(PlanningDependencyLogicMixin, LineageLogicMixin):


































    def enforceTrajectoryControlPointInvariant(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Enforce a non-destructive two-point Entry/Target line contract."""

        if not trajectoryNode or not trajectoryNode.IsA(
            "vtkMRMLMarkupsLineNode"
        ):
            raise ValueError(_("Select a valid trajectory line node."))
        if (
            trajectoryNode.GetNumberOfControlPoints() > 2
            or trajectoryNode.GetNumberOfDefinedControlPoints() > 2
        ):
            raise ValueError(
                _(
                    "A trajectory may contain only Entry and Target. Remove "
                    "extra points before using it in DENTOBOT."
                )
            )
        if trajectoryNode.GetMaximumNumberOfControlPoints() != 2:
            raise ValueError(
                _("The selected line does not enforce the two-point trajectory contract.")
            )
        self.labelTrajectoryControlPoints(trajectoryNode)

    def createTrajectoryNode(
        self,
        name: str = "DENTO Trajectory",
    ) -> vtkMRMLMarkupsLineNode:
        """Create a draft entry-to-target line in the current MRML scene."""

        if not isinstance(name, str) or not name.strip():
            raise ValueError(_("Trajectory name must not be empty."))
        trajectoryNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            name.strip(),
        )
        if not trajectoryNode:
            raise RuntimeError(_("Slicer could not create a trajectory line."))
        if trajectoryNode.GetMaximumNumberOfControlPoints() != 2:
            slicer.mrmlScene.RemoveNode(trajectoryNode)
            raise RuntimeError(
                _("The created trajectory does not enforce two control points.")
            )
        trajectoryNode.CreateDefaultDisplayNodes()
        trajectoryNode.SetAttribute("DENTOBOT.TrajectoryRole", "EntryToTarget")
        trajectoryNode.SetAttribute(
            "DENTOBOT.CoordinateSystem",
            "SlicerRASmm",
        )
        trajectoryNode.SetAttribute("DENTOBOT.PlanningStatus", "Draft")
        self.enforceTrajectoryControlPointInvariant(trajectoryNode)
        return trajectoryNode

    @staticmethod
    def isAssistedTrajectoryEntryNode(entryNode) -> bool:
        return bool(
            entryNode
            and entryNode.IsA("vtkMRMLMarkupsFiducialNode")
            and entryNode.GetAttribute("DENTOBOT.MarkupsRole")
            == "AssistedTrajectoryEntries"
        )

    def getAssistedTrajectoryEntrySummary(
        self,
        entryNode: vtkMRMLMarkupsFiducialNode,
    ) -> dict:
        if not self.isAssistedTrajectoryEntryNode(entryNode):
            raise ValueError(_("Create the assisted Step 4A entry points first."))
        try:
            expectedCount = int(
                entryNode.GetAttribute("DENTOBOT.ExpectedEntryCount") or "0"
            )
        except ValueError as exc:
            raise ValueError(_("The assisted entry count is invalid.")) from exc
        if expectedCount not in (1, 2):
            raise ValueError(_("The assisted entry count must be one or two."))
        pointCount = entryNode.GetNumberOfDefinedControlPoints()
        if pointCount < 0 or pointCount > expectedCount:
            raise ValueError(_("The assisted entry markup has an invalid point count."))
        points = []
        for index in range(pointCount):
            point = [0.0, 0.0, 0.0]
            entryNode.GetNthControlPointPositionWorld(index, point)
            if not all(math.isfinite(float(value)) for value in point):
                raise ValueError(_("An assisted entry point is not finite."))
            desiredLabel = _("Entry %1").replace("%1", str(index + 1))
            if entryNode.GetNthControlPointLabel(index) != desiredLabel:
                entryNode.SetNthControlPointLabel(index, desiredLabel)
            points.append([float(value) for value in point])
        return {
            "expectedCount": expectedCount,
            "definedPointCount": pointCount,
            "entryPointsRas": points,
            "isComplete": pointCount == expectedCount,
        }

    def validateAssistedTrajectoryEntryAssociation(
        self,
        entryNode: vtkMRMLMarkupsFiducialNode,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        expectedCount: int,
    ) -> dict:
        targetRecord = self.validateTargetTooth(segmentationNode, segmentId)
        summary = self.getAssistedTrajectoryEntrySummary(entryNode)
        referencedSegmentation = entryNode.GetNodeReference(
            self.ASSISTED_ENTRY_SEGMENTATION_REFERENCE_ROLE
        )
        if (
            referencedSegmentation is not segmentationNode
            or entryNode.GetAttribute("DENTOBOT.TargetSegmentID")
            != targetRecord["segmentId"]
        ):
            raise ValueError(
                _(
                    "The assisted entry points belong to a different target "
                    "tooth. Place a new assisted Step 4A entry set."
                )
            )
        if summary["expectedCount"] != int(expectedCount):
            raise ValueError(
                _(
                    "The requested trajectory count changed. Replace the "
                    "assisted entry points before generating targets."
                )
            )
        return {"targetRecord": targetRecord, **summary}

    def createOrResetAssistedTrajectoryEntries(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        expectedCount: int,
        entryNode: vtkMRMLMarkupsFiducialNode | None = None,
    ) -> tuple[vtkMRMLMarkupsFiducialNode, dict]:
        targetRecord = self.validateTargetTooth(segmentationNode, segmentId)
        expectedCount = int(expectedCount)
        if expectedCount not in (1, 2):
            raise ValueError(_("Choose one or two assisted trajectories."))

        reusable = bool(
            self.isAssistedTrajectoryEntryNode(entryNode)
            and entryNode.GetNodeReference(
                self.ASSISTED_ENTRY_SEGMENTATION_REFERENCE_ROLE
            )
            is segmentationNode
            and entryNode.GetAttribute("DENTOBOT.TargetSegmentID")
            == targetRecord["segmentId"]
        )
        if not reusable:
            entryNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsFiducialNode",
                _("[Step 4A] DENTO Assisted Entries FDI %1").replace(
                    "%1", targetRecord.get("fdiNumber") or "Unknown"
                ),
            )
        if not entryNode:
            raise RuntimeError(_("Slicer could not create assisted entry points."))

        entryNode.SetLocked(False)
        entryNode.RemoveAllControlPoints()
        entryNode.SetMaximumNumberOfControlPoints(expectedCount)
        wasModifying = entryNode.StartModify()
        try:
            entryNode.SetName(
                _("[Step 4A] DENTO Assisted Entries FDI %1").replace(
                    "%1", targetRecord.get("fdiNumber") or "Unknown"
                )
            )
            entryNode.SetAttribute(
                "DENTOBOT.MarkupsRole", "AssistedTrajectoryEntries"
            )
            entryNode.SetAttribute(
                "DENTOBOT.AssistedEntrySchemaVersion",
                self.ASSISTED_ENTRY_SCHEMA_VERSION,
            )
            entryNode.SetAttribute("DENTOBOT.CoordinateSystem", "SlicerRASmm")
            entryNode.SetAttribute(
                "DENTOBOT.ExpectedEntryCount", str(expectedCount)
            )
            entryNode.SetAttribute(
                "DENTOBOT.TargetSegmentID", targetRecord["segmentId"]
            )
            entryNode.SetAttribute(
                "DENTOBOT.TargetFdiNumber",
                targetRecord.get("fdiNumber") or "",
            )
            entryNode.SetAttribute("DENTOBOT.GeometryState", "AwaitingEntries")
            entryNode.SetNodeReferenceID(
                self.ASSISTED_ENTRY_SEGMENTATION_REFERENCE_ROLE,
                segmentationNode.GetID(),
            )
        finally:
            entryNode.EndModify(wasModifying)
        entryNode.CreateDefaultDisplayNodes()
        # Lineage color is assigned only after the first trajectory exists.
        self.clearNodeLineageColor(entryNode)
        displayNode = entryNode.GetDisplayNode()
        if displayNode:
            displayNode.SetColor(1.0, 0.55, 0.05)
            displayNode.SetSelectedColor(1.0, 0.75, 0.15)
            displayNode.SetPointLabelsVisibility(True)
            displayNode.SetGlyphScale(1.5)
        return entryNode, self.getAssistedTrajectoryEntrySummary(entryNode)

    @staticmethod
    def startAssistedTrajectoryEntryPlacement(
        entryNode: vtkMRMLMarkupsFiducialNode,
    ) -> None:
        if not DENTOWorkflowLogic.isAssistedTrajectoryEntryNode(entryNode):
            raise ValueError(_("Create the assisted Step 4A entry points first."))
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsFiducialNode"
        )
        selectionNode.SetActivePlaceNodeID(entryNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(1)
        selectionNode.SetActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(entryNode.GetID())
        if (
            selectionNode.GetActivePlaceNodeID() != entryNode.GetID()
            or not selectionNode.GetActivePlaceNodePlacementValid()
        ):
            DENTOWorkflowLogic.stopTrajectoryPlacement()
            raise RuntimeError(_("Slicer could not activate assisted entry placement."))

    def generateAssistedTrajectories(
        self,
        entryNode: vtkMRMLMarkupsFiducialNode,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        rootCount: int,
        targetBoundsRoi: vtkMRMLMarkupsROINode | None = None,
    ) -> tuple[list[vtkMRMLMarkupsLineNode], dict]:
        rootCount = int(rootCount)
        inputs = self.validateAssistedTrajectoryEntryAssociation(
            entryNode,
            segmentationNode,
            segmentId,
            rootCount,
        )
        if not inputs["isComplete"]:
            raise ValueError(
                _("Place all requested crown entry points before generating targets.")
            )
        existing = self.dentobotTrajectoriesForTarget(
            segmentationNode, inputs["targetRecord"]["segmentId"]
        )
        if existing:
            raise ValueError(
                _(
                    "This target tooth already has a DENTOBOT trajectory. "
                    "Delete the old trajectory set before assisted regeneration "
                    "so the one/two-trajectory contract stays unambiguous."
                )
            )

        bounds = self.getTargetToothBoundsWorld(segmentationNode, segmentId)
        if any(
            not self.isRasPointWithinBounds(point, bounds)
            for point in inputs["entryPointsRas"]
        ):
            raise ValueError(
                _("Every assisted crown entry point must lie inside the target-tooth bounds.")
            )
        surface = self._getClosedSurfaceCopy(segmentationNode, segmentId)
        pointData = surface.GetPoints().GetData() if surface.GetPoints() else None
        if not pointData:
            raise ValueError(_("The target tooth has no usable surface points."))
        analysis = infer_root_targets(
            vtk_to_numpy(pointData),
            inputs["entryPointsRas"],
            rootCount,
        )

        created = []
        try:
            for index, (entry, target) in enumerate(
                zip(inputs["entryPointsRas"], analysis["targetsRas"]),
                start=1,
            ):
                trajectoryNode = self.createTrajectoryNode(
                    _("DENTO Assisted Trajectory %1").replace("%1", str(index))
                )
                created.append(trajectoryNode)
                self.enableAutomaticTrajectoryName(trajectoryNode)
                self.configureTrajectoryTarget(
                    trajectoryNode,
                    segmentationNode,
                    inputs["targetRecord"]["segmentId"],
                )
                trajectoryNode.AddControlPointWorld(vtk.vtkVector3d(*entry))
                trajectoryNode.AddControlPointWorld(vtk.vtkVector3d(*target))
                self.labelTrajectoryControlPoints(trajectoryNode)
                trajectoryNode.SetLocked(False)
                trajectoryNode.SetNodeReferenceID(
                    self.ASSISTED_TRAJECTORY_ENTRY_REFERENCE_ROLE,
                    entryNode.GetID(),
                )
                if targetBoundsRoi:
                    trajectoryNode.SetNodeReferenceID(
                        self.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
                        targetBoundsRoi.GetID(),
                    )
                trajectoryNode.SetAttribute(
                    "DENTOBOT.TrajectoryCreationMethod", analysis["method"]
                )
                trajectoryNode.SetAttribute(
                    "DENTOBOT.AssistedRootOrdinal", str(index)
                )
                trajectoryNode.SetAttribute(
                    "DENTOBOT.AssistedTargetState", "RequiresManualVerification"
                )
                trajectoryNode.SetAttribute(
                    "DENTOBOT.AssistedAnalysisJson",
                    json.dumps(analysis, separators=(",", ":"), sort_keys=True),
                )
                summary = self.getTrajectorySummary(trajectoryNode)
                if not summary["isValid"]:
                    raise RuntimeError(_("An assisted trajectory was degenerate."))
            entryNode.SetLocked(True)
            entryNode.SetAttribute("DENTOBOT.GeometryState", "TargetsGenerated")
            self.setNodeLineageColor(
                entryNode,
                self.lineageColorForTarget(
                    inputs["targetRecord"]["segmentId"],
                    inputs["targetRecord"].get("fdiNumber") or "",
                ),
                inputs["targetRecord"]["segmentId"],
                inputs["targetRecord"].get("fdiNumber") or "",
            )
            self.refreshManagedTrajectoryNames()
            self.refreshWorkflowLineageColors()
            return created, analysis
        except Exception:
            for trajectoryNode in created:
                if slicer.mrmlScene.IsNodePresent(trajectoryNode):
                    slicer.mrmlScene.RemoveNode(trajectoryNode)
            raise

    def enableAutomaticTrajectoryName(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Opt a DENTOBOT trajectory into informative, managed display names."""

        if not self.isDentobotTrajectoryNode(trajectoryNode):
            raise ValueError(_("Select a DENTOBOT Step 4A trajectory."))
        trajectoryNode.SetAttribute(self.TRAJECTORY_AUTO_NAME_ATTRIBUTE, "1")

    @staticmethod
    def _trajectoryStateLabel(trajectorySummary: dict) -> str:
        pointCount = trajectorySummary["definedPointCount"]
        if pointCount == 0:
            return _("Empty")
        if pointCount == 1:
            return _("Entry only")
        return _("Complete") if trajectorySummary["isValid"] else _("Invalid")

    def refreshManagedTrajectoryNames(self) -> list[str]:
        """Disambiguate managed and legacy default trajectory names.

        Names are presentation only. Grouping and numbering use persisted MRML
        references and segment IDs, never editable node names.
        """

        trajectories = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode")
            if self.isDentobotTrajectoryNode(node)
        ]
        for trajectoryNode in trajectories:
            name = trajectoryNode.GetName() or ""
            if re.fullmatch(
                r"(?:\[Step 4A\]\s+)?DENTO Trajectory FDI\s+\d+",
                name,
            ):
                trajectoryNode.SetAttribute(
                    self.TRAJECTORY_AUTO_NAME_ATTRIBUTE,
                    "1",
                )

        managedGroups: dict[tuple[str, str], list] = {}
        for trajectoryNode in trajectories:
            if trajectoryNode.GetAttribute(
                self.TRAJECTORY_AUTO_NAME_ATTRIBUTE
            ) != "1":
                continue
            segmentationNode = trajectoryNode.GetNodeReference(
                self.TARGET_SEGMENTATION_REFERENCE_ROLE
            )
            segmentId = trajectoryNode.GetAttribute(
                "DENTOBOT.TargetSegmentID"
            ) or ""
            key = (
                segmentationNode.GetID() if segmentationNode else "",
                segmentId,
            )
            managedGroups.setdefault(key, []).append(trajectoryNode)

        changedNodeIds = []
        for (_segmentationId, segmentId), group in managedGroups.items():
            for index, trajectoryNode in enumerate(group, start=1):
                fdiNumber = trajectoryNode.GetAttribute(
                    "DENTOBOT.TargetFdiNumber"
                ) or ""
                targetLabel = (
                    f"FDI {fdiNumber}"
                    if fdiNumber
                    else segmentId
                    if segmentId
                    else _("Unassigned")
                )
                stateLabel = self._trajectoryStateLabel(
                    self.getTrajectorySummary(trajectoryNode)
                )
                desiredName = _("[Step 4A] DENTO %1 - Trajectory %2 [%3]")
                desiredName = (
                    desiredName.replace("%1", targetLabel)
                    .replace("%2", str(index))
                    .replace("%3", stateLabel)
                )
                if trajectoryNode.GetName() != desiredName:
                    trajectoryNode.SetName(desiredName)
                    changedNodeIds.append(trajectoryNode.GetID())
        return changedNodeIds

    @staticmethod
    def ensureWorkflowNodeStepTag(node, stepName: str) -> bool:
        """Prefix one workflow-owned node for clear Slicer Data-view grouping."""

        if not node:
            return False
        currentName = node.GetName() or node.GetClassName()
        untaggedName = re.sub(
            r"^\[Step [^\]]+\]\s*",
            "",
            currentName,
        )
        desiredName = f"[{stepName}] {untaggedName}"
        if currentName == desiredName:
            return False
        node.SetName(desiredName)
        return True

    @staticmethod
    def enforceWorkflowRoiNonInteractive(roiNode) -> bool:
        """Make a workflow-owned bounds ROI visible-only in slice/3D views."""

        if not roiNode or not roiNode.IsA("vtkMRMLMarkupsROINode"):
            return False
        changed = False
        wasModifying = roiNode.StartModify()
        try:
            if not roiNode.GetLocked():
                roiNode.SetLocked(True)
                changed = True
            if hasattr(roiNode, "GetSelectable") and roiNode.GetSelectable():
                roiNode.SetSelectable(False)
                changed = True
        finally:
            roiNode.EndModify(wasModifying)
        displayNode = roiNode.GetDisplayNode()
        if displayNode:
            for getterName, setterName in (
                ("GetHandlesInteractive", "SetHandlesInteractive"),
                ("GetTranslationHandleVisibility", "SetTranslationHandleVisibility"),
                ("GetRotationHandleVisibility", "SetRotationHandleVisibility"),
                ("GetScaleHandleVisibility", "SetScaleHandleVisibility"),
            ):
                getter = getattr(displayNode, getterName, None)
                setter = getattr(displayNode, setterName, None)
                if getter and setter and getter():
                    setter(False)
                    changed = True
        return changed

    def refreshWorkflowNodeStepTags(self) -> list[str]:
        """Tag every DENTOBOT-owned Step 4A/4B/4C/5A/5B/5C object by role."""

        taggedNodeIds = []
        for trajectoryNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsLineNode"
        ):
            stepName = (
                "Step 4A"
                if self.isDentobotTrajectoryNode(trajectoryNode)
                else "Step 5B"
                if self.isTemplateInsertionDirectionNode(trajectoryNode)
                else None
            )
            if stepName and self.ensureWorkflowNodeStepTag(
                trajectoryNode,
                stepName,
            ):
                taggedNodeIds.append(trajectoryNode.GetID())
        for entryNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsFiducialNode"
        ):
            if (
                self.isAssistedTrajectoryEntryNode(entryNode)
                and self.ensureWorkflowNodeStepTag(entryNode, "Step 4A")
            ):
                taggedNodeIds.append(entryNode.GetID())
        for roiNode in slicer.util.getNodesByClass("vtkMRMLMarkupsROINode"):
            stepName = None
            if roiNode.GetAttribute("DENTOBOT.BoundsRole") == "TargetToothAABB":
                stepName = "Step 4A"
            elif self.isTemplateShellRoiNode(roiNode):
                stepName = "Step 5B"
            if stepName and self.enforceWorkflowRoiNonInteractive(roiNode):
                taggedNodeIds.append(roiNode.GetID())
            if (
                stepName
                and self.ensureWorkflowNodeStepTag(roiNode, stepName)
                and roiNode.GetID() not in taggedNodeIds
            ):
                taggedNodeIds.append(roiNode.GetID())
        for className, acceptsNode in (
            ("vtkMRMLMarkupsPlaneNode", self.isTemplateTrimPlaneNode),
            ("vtkMRMLMarkupsClosedCurveNode", self.isTemplateTrimCurveNode),
        ):
            for markupNode in slicer.util.getNodesByClass(className):
                if (
                    acceptsNode(markupNode)
                    and self.ensureWorkflowNodeStepTag(markupNode, "Step 5C")
                ):
                    taggedNodeIds.append(markupNode.GetID())
        for curveNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsClosedCurveNode"
        ):
            if (
                self.isTemplateSupportBoundaryNode(curveNode)
                and self.ensureWorkflowNodeStepTag(curveNode, "Step 5A")
            ):
                taggedNodeIds.append(curveNode.GetID())
        for planeNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsPlaneNode"
        ):
            if (
                self.isTargetDockingReferencePlaneNode(planeNode)
                and self.ensureWorkflowNodeStepTag(planeNode, "Step 4C")
            ):
                taggedNodeIds.append(planeNode.GetID())
            if (
                self.isTemplateSupportBoundaryPlaneNode(planeNode)
                and self.ensureWorkflowNodeStepTag(planeNode, "Step 5A")
            ):
                taggedNodeIds.append(planeNode.GetID())
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            role = modelNode.GetAttribute("DENTOBOT.ModelRole")
            stepName = (
                "Step 4C"
                if role == "TargetDockingAssembly"
                else "Step 4B"
                if role == "TemplateSupportDraft"
                else "Step 5A"
                if role == "VisibleTemplateSupportSurface"
                else "Step 5B"
                if role
                in {
                    "PatientContactShell",
                    "TemplateUndercutSurface",
                    "TemplateUndercutBlockout",
                    "TemplateDockingAssembly",
                    "TemplateDockingClearance",
                    "TemplateDockingReinforcement",
                    "TemplateDockingChannels",
                    "TemplateFittingSurface",
                    "TemplateHollowCandidate",
                    "ResearchTemplateShell",
                    "ResearchTemplateSleeve",
                }
                else "Step 5C"
                if role in {"FinalizedTemplateShell", "FinalPrintableTemplate"}
                else None
            )
            if stepName and self.ensureWorkflowNodeStepTag(modelNode, stepName):
                taggedNodeIds.append(modelNode.GetID())
        return taggedNodeIds

    def configureTrajectoryTarget(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Associate a draft trajectory with one authoritative tooth segment."""

        self.enforceTrajectoryControlPointInvariant(trajectoryNode)
        self.getTrajectorySummary(trajectoryNode)
        targetRecord = self.validateTargetTooth(segmentationNode, segmentId)
        wasModifying = trajectoryNode.StartModify()
        try:
            trajectoryNode.SetNodeReferenceID(
                self.TARGET_SEGMENTATION_REFERENCE_ROLE,
                segmentationNode.GetID(),
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.TargetSegmentID",
                targetRecord["segmentId"],
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.TargetSegmentName",
                targetRecord["sourceName"],
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.TargetFdiNumber",
                targetRecord["fdiNumber"] or "",
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.TrajectoryRole",
                "EntryToTarget",
            )
            trajectoryNode.SetAttribute(
                "DENTOBOT.CoordinateSystem",
                "SlicerRASmm",
            )
            trajectoryNode.SetAttribute("DENTOBOT.PlanningStatus", "Draft")
        finally:
            trajectoryNode.EndModify(wasModifying)
        self.labelTrajectoryControlPoints(trajectoryNode)
        self.setNodeLineageColor(
            trajectoryNode,
            self.lineageColorForTarget(
                targetRecord["segmentId"],
                targetRecord.get("fdiNumber") or "",
            ),
            targetRecord["segmentId"],
            targetRecord.get("fdiNumber") or "",
        )
        self.refreshWorkflowLineageColors()
        return targetRecord

    def getTrajectoryTargetAssociation(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> dict | None:
        """Return and validate a trajectory's persisted target association.

        An entirely unassociated Markups line returns ``None`` so it can be
        adopted for the active tooth. Partial or dangling persisted state is
        rejected rather than silently overwritten.
        """

        self.getTrajectorySummary(trajectoryNode)
        segmentationNode = trajectoryNode.GetNodeReference(
            self.TARGET_SEGMENTATION_REFERENCE_ROLE
        )
        segmentId = trajectoryNode.GetAttribute(
            "DENTOBOT.TargetSegmentID"
        ) or ""
        roiNode = trajectoryNode.GetNodeReference(
            self.TARGET_BOUNDS_ROI_REFERENCE_ROLE
        )
        hasOtherTargetMetadata = any(
            trajectoryNode.GetAttribute(attributeName)
            for attributeName in (
                "DENTOBOT.TargetSegmentName",
                "DENTOBOT.TargetFdiNumber",
            )
        )
        if not segmentationNode and not segmentId:
            if roiNode or hasOtherTargetMetadata:
                raise ValueError(
                    _(
                        "The selected trajectory has an incomplete saved target "
                        "association. Repair or delete it; DENTOBOT will not "
                        "guess from its editable name."
                    )
                )
            return None
        if not segmentationNode or not segmentId:
            raise ValueError(
                _(
                    "The selected trajectory has an incomplete saved target "
                    "association. Repair or delete it; DENTOBOT will not guess "
                    "from its editable name."
                )
            )
        if not segmentationNode.IsA("vtkMRMLSegmentationNode"):
            raise ValueError(
                _("The selected trajectory references an invalid segmentation.")
            )
        targetRecord = self.validateTargetTooth(segmentationNode, segmentId)
        if roiNode:
            if not roiNode.IsA("vtkMRMLMarkupsROINode"):
                raise ValueError(
                    _("The selected trajectory references an invalid target ROI.")
                )
            roiRole = roiNode.GetAttribute("DENTOBOT.BoundsRole")
            roiSegmentId = roiNode.GetAttribute("DENTOBOT.TargetSegmentID")
            roiSegmentation = roiNode.GetNodeReference(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
            )
            if (
                roiRole != "TargetToothAABB"
                or roiSegmentId != segmentId
                or roiSegmentation is not segmentationNode
            ):
                raise ValueError(
                    _(
                        "The selected trajectory's saved target ROI does not "
                        "match its target tooth association."
                    )
                )
        return {
            "segmentationNode": segmentationNode,
            "targetRecord": targetRecord,
            "targetBoundsRoi": roiNode,
        }

    def clearTrajectoryTarget(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        """Remove a stale target association without deleting trajectory geometry."""

        self.getTrajectorySummary(trajectoryNode)
        wasModifying = trajectoryNode.StartModify()
        try:
            trajectoryNode.SetNodeReferenceID(
                self.TARGET_SEGMENTATION_REFERENCE_ROLE,
                None,
            )
            trajectoryNode.SetNodeReferenceID(
                self.TARGET_BOUNDS_ROI_REFERENCE_ROLE,
                None,
            )
            for attributeName in (
                "DENTOBOT.TargetSegmentID",
                "DENTOBOT.TargetSegmentName",
                "DENTOBOT.TargetFdiNumber",
            ):
                trajectoryNode.SetAttribute(attributeName, None)
        finally:
            trajectoryNode.EndModify(wasModifying)
        self.clearNodeLineageColor(trajectoryNode)
        displayNode = trajectoryNode.GetDisplayNode()
        if displayNode:
            displayNode.SetColor(0.65, 0.65, 0.65)
            displayNode.SetSelectedColor(0.75, 0.75, 0.75)
