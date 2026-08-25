"""Extracted planning dependencies and deletion methods; public APIs remain on WorkflowLogicMixin."""

from __future__ import annotations

from .runtime import *


class PlanningDependencyLogicMixin:
    def createOrUpdateTargetBoundsRoi(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        roiNode: vtkMRMLMarkupsROINode | None = None,
    ) -> tuple[vtkMRMLMarkupsROINode, tuple[float, ...]]:
        """Create a locked visible ROI matching the selected tooth's RAS AABB."""

        targetRecord = self.validateTargetTooth(
            segmentationNode,
            segmentId,
        )
        bounds = self.getTargetToothBoundsWorld(
            segmentationNode,
            segmentId,
        )
        roiIsMarkup = bool(
            roiNode and roiNode.IsA("vtkMRMLMarkupsROINode")
        )
        boundsRole = (
            roiNode.GetAttribute("DENTOBOT.BoundsRole")
            if roiIsMarkup
            else None
        )
        markupsRole = (
            roiNode.GetAttribute("DENTOBOT.MarkupsRole")
            if roiIsMarkup
            else None
        )
        reusedRoi = bool(
            roiIsMarkup
            and (
                (
                    boundsRole == "TargetToothAABB"
                    and roiNode.GetAttribute("DENTOBOT.TargetSegmentID")
                    == targetRecord["segmentId"]
                    and roiNode.GetNodeReference(
                        self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
                    )
                    and roiNode.GetNodeReference(
                        self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
                    ).GetID()
                    == segmentationNode.GetID()
                )
                or (not boundsRole and not markupsRole)
            )
        )
        previousVisibility = bool(
            reusedRoi
            and roiNode.GetDisplayNode()
            and roiNode.GetDisplayNode().GetVisibility()
        )
        if not reusedRoi:
            roiNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsROINode",
                f'[Step 4A] DENTO Target Bounds FDI {targetRecord["fdiNumber"]}',
            )
        if not roiNode:
            raise RuntimeError(_("Slicer could not create target bounds."))

        center = [
            (bounds[axis * 2] + bounds[axis * 2 + 1]) / 2.0
            for axis in range(3)
        ]
        size = [
            bounds[axis * 2 + 1] - bounds[axis * 2]
            for axis in range(3)
        ]
        wasModifying = roiNode.StartModify()
        try:
            roiNode.SetAndObserveTransformNodeID(None)
            objectToNode = vtk.vtkMatrix4x4()
            objectToNode.Identity()
            roiNode.SetAndObserveObjectToNodeMatrix(objectToNode)
            roiNode.SetName(
                f'[Step 4A] DENTO Target Bounds FDI {targetRecord["fdiNumber"]}'
            )
            roiNode.SetCenterWorld(center)
            roiNode.SetSizeWorld(size)
            roiNode.SetLocked(True)
            roiNode.SetAttribute("DENTOBOT.BoundsRole", "TargetToothAABB")
            roiNode.SetAttribute("DENTOBOT.MarkupsRole", None)
            roiNode.SetAttribute("DENTOBOT.TemplateGuideSchemaVersion", None)
            roiNode.SetNodeReferenceID(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
                None,
            )
            roiNode.SetAttribute(
                "DENTOBOT.CoordinateSystem",
                "SlicerRASmm",
            )
            roiNode.SetAttribute(
                "DENTOBOT.TargetSegmentID",
                targetRecord["segmentId"],
            )
            roiNode.SetAttribute(
                "DENTOBOT.TargetFdiNumber",
                targetRecord["fdiNumber"] or "",
            )
            roiNode.SetNodeReferenceID(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE,
                segmentationNode.GetID(),
            )
        finally:
            roiNode.EndModify(wasModifying)

        roiNode.CreateDefaultDisplayNodes()
        displayNode = roiNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(previousVisibility if reusedRoi else True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetFillVisibility(False)
            displayNode.SetOutlineVisibility(True)
            displayNode.SetPropertiesLabelVisibility(False)
            if hasattr(displayNode, "SetHandlesInteractive"):
                displayNode.SetHandlesInteractive(False)
        self.enforceWorkflowRoiNonInteractive(roiNode)
        targetTrajectories = self.dentobotTrajectoriesForTarget(
            segmentationNode,
            targetRecord["segmentId"],
        )
        if targetTrajectories:
            self.setNodeLineageColor(
                roiNode,
                self.lineageColorForTarget(
                    targetRecord["segmentId"],
                    targetRecord.get("fdiNumber") or "",
                ),
                targetRecord["segmentId"],
                targetRecord.get("fdiNumber") or "",
            )
        else:
            self.clearNodeLineageColor(roiNode)
            if displayNode:
                displayNode.SetColor(1.0, 0.65, 0.0)
                displayNode.SetSelectedColor(1.0, 0.8, 0.2)
        return roiNode, bounds

    @staticmethod
    def isRasPointWithinBounds(
        point: list[float] | tuple[float, ...],
        bounds: tuple[float, float, float, float, float, float],
        toleranceMm: float = 1e-3,
    ) -> bool:
        """Return whether a point lies inside an inclusive world-RAS AABB."""

        if len(point) != 3 or len(bounds) != 6:
            raise ValueError(_("Invalid point or target bounds."))
        toleranceMm = float(toleranceMm)
        if not math.isfinite(toleranceMm) or toleranceMm < 0.0:
            raise ValueError(_("Bounds tolerance must be non-negative."))
        return all(
            bounds[axis * 2] - toleranceMm
            <= float(point[axis])
            <= bounds[axis * 2 + 1] + toleranceMm
            for axis in range(3)
        )

    def getTrajectoryBoundsReport(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Report any Entry/Target points outside the selected tooth AABB."""

        summary = self.getTrajectorySummary(trajectoryNode)
        bounds = self.getTargetToothBoundsWorld(
            segmentationNode,
            segmentId,
        )
        points = (summary["entryRas"], summary["targetRas"])
        invalidIndices = [
            index
            for index, point in enumerate(points)
            if point is not None
            and not self.isRasPointWithinBounds(point, bounds)
        ]
        return {
            "bounds": bounds,
            "invalidPointIndices": invalidIndices,
            "allDefinedPointsWithinBounds": not invalidIndices,
            "summary": summary,
        }

    @staticmethod
    def _isAuxiliaryNodeReferenced(auxiliaryNode) -> bool:
        """Return whether another scene node still owns an auxiliary node."""

        auxiliaryNodeId = auxiliaryNode.GetID() if auxiliaryNode else None
        if not auxiliaryNodeId:
            return False
        if auxiliaryNode.IsA("vtkMRMLDisplayNode"):
            for displayableNode in slicer.util.getNodesByClass(
                "vtkMRMLDisplayableNode"
            ):
                for index in range(displayableNode.GetNumberOfDisplayNodes()):
                    referencedNode = displayableNode.GetNthDisplayNode(index)
                    if (
                        referencedNode
                        and referencedNode.GetID() == auxiliaryNodeId
                    ):
                        return True
        if auxiliaryNode.IsA("vtkMRMLStorageNode"):
            for storableNode in slicer.util.getNodesByClass(
                "vtkMRMLStorableNode"
            ):
                referencedNode = storableNode.GetStorageNode()
                if (
                    referencedNode
                    and referencedNode.GetID() == auxiliaryNodeId
                ):
                    return True
        return False

    @classmethod
    def _removeSceneNodeAndOwnedAuxiliaries(cls, node) -> dict:
        """Remove one data node and only its now-unreferenced auxiliaries."""

        scene = slicer.mrmlScene
        if not node or not node.GetID() or not scene.IsNodePresent(node):
            raise ValueError(_("The selected node is no longer in the scene."))

        nodeId = node.GetID()
        nodeName = node.GetName() or ""
        auxiliaryNodes = {}
        if node.IsA("vtkMRMLDisplayableNode"):
            for index in range(node.GetNumberOfDisplayNodes()):
                auxiliaryNode = node.GetNthDisplayNode(index)
                if auxiliaryNode and auxiliaryNode.GetID():
                    auxiliaryNodes[auxiliaryNode.GetID()] = auxiliaryNode
        if node.IsA("vtkMRMLStorableNode"):
            storageNode = node.GetStorageNode()
            if storageNode and storageNode.GetID():
                auxiliaryNodes[storageNode.GetID()] = storageNode

        scene.RemoveNode(node)
        if scene.GetNodeByID(nodeId):
            raise RuntimeError(_("Slicer did not remove the selected node."))

        removedAuxiliaryNodeIds = []
        for auxiliaryNodeId, auxiliaryNode in auxiliaryNodes.items():
            if (
                scene.GetNodeByID(auxiliaryNodeId)
                and not cls._isAuxiliaryNodeReferenced(auxiliaryNode)
            ):
                scene.RemoveNode(auxiliaryNode)
                removedAuxiliaryNodeIds.append(auxiliaryNodeId)
        return {
            "nodeId": nodeId,
            "nodeName": nodeName,
            "auxiliaryNodeIds": removedAuxiliaryNodeIds,
        }

    @staticmethod
    def isDentobotTrajectoryNode(trajectoryNode) -> bool:
        return bool(
            trajectoryNode
            and trajectoryNode.IsA("vtkMRMLMarkupsLineNode")
            and trajectoryNode.GetAttribute("DENTOBOT.TrajectoryRole")
            == "EntryToTarget"
        )

    def validateDentobotTrajectoryForDeletion(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> None:
        if not self.isDentobotTrajectoryNode(trajectoryNode):
            raise ValueError(
                _("Select a DENTOBOT Step 4A trajectory to delete.")
            )
        if not slicer.mrmlScene.IsNodePresent(trajectoryNode):
            raise ValueError(_("The selected trajectory is no longer in the scene."))

    @staticmethod
    def _mrmlNodeReferencesNode(node, referencedNode) -> bool:
        if not node or not referencedNode:
            return False
        roles = []
        node.GetNodeReferenceRoles(roles)
        referencedId = referencedNode.GetID()
        for role in roles:
            for referenceIndex in range(node.GetNumberOfNodeReferences(role)):
                candidate = node.GetNthNodeReference(role, referenceIndex)
                if candidate and candidate.GetID() == referencedId:
                    return True
        return False

    def _activePlanningDownstreamEntries(self) -> list[dict]:
        parameterNode = self.getParameterNode()
        specifications = (
            ("targetDockingReferencePlane", "Step 4C"),
            ("targetDockingAssemblyModel", "Step 4C"),
            ("draftTemplateSupportModel", "Step 4B"),
            ("templateSupportBoundaryCurve", "Step 5A"),
            ("templateSupportBoundaryPlane", "Step 5A"),
            ("visibleTemplateSupportModel", "Step 5A"),
            ("templateInsertionDirection", "Step 5B"),
            ("templateUndercutSurfaceModel", "Step 5B"),
            ("templateUndercutBlockoutModel", "Step 5B"),
            ("patientContactShellModel", "Step 5B"),
            ("templateShellRoi", "Legacy Step 5B"),
            ("researchTemplateShellModel", "Legacy Step 5B"),
            ("researchTemplateSleeveModel", "Legacy Step 5B"),
            ("templateDockingAssemblyModel", "Step 5C"),
            ("templateDockingClearanceModel", "Step 5C"),
            ("templateDockingReinforcementModel", "Step 5C"),
            ("templateDockingChannelsModel", "Step 5C"),
            ("finalPrintableTemplateModel", "Step 5C"),
            ("templateTrimPlane", "Legacy Step 5C"),
            ("templateTrimCurve", "Legacy Step 5C"),
            ("finalizedTemplateShellModel", "Legacy Step 5C"),
        )
        entries = []
        seenNodeIds = set()
        for fieldName, stage in specifications:
            node = getattr(parameterNode, fieldName)
            nodeId = node.GetID() if node else None
            if (
                not nodeId
                or nodeId in seenNodeIds
                or not slicer.mrmlScene.IsNodePresent(node)
            ):
                continue
            seenNodeIds.add(nodeId)
            entries.append(
                {
                    "field": fieldName,
                    "stage": stage,
                    "node": node,
                    "nodeId": nodeId,
                    "nodeName": node.GetName() or "",
                }
            )
        return entries

    @staticmethod
    def _workflowImpactFromEntries(entries: list[dict], flags: dict) -> dict:
        stages = {}
        for entry in entries:
            stages.setdefault(entry["stage"], []).append(entry["nodeId"])
        orderedStages = [
            {"stage": stage, "nodeIds": nodeIds}
            for stage, nodeIds in stages.items()
        ]
        return {
            "hasDependents": bool(entries),
            "stages": orderedStages,
            "nodeIds": [entry["nodeId"] for entry in entries],
            "flags": dict(flags),
        }

    def getActivePlanningDownstreamImpact(self) -> dict:
        entries = self._activePlanningDownstreamEntries()
        fields = {entry["field"] for entry in entries}
        flags = {
            "targetDocking": bool(
                fields
                & {"targetDockingReferencePlane", "targetDockingAssemblyModel"}
            ),
            "draftSupport": "draftTemplateSupportModel" in fields,
            "supportSelection": bool(
                fields
                & {
                    "templateSupportBoundaryCurve",
                    "templateSupportBoundaryPlane",
                    "visibleTemplateSupportModel",
                }
            ),
            "undercut": bool(
                fields
                & {
                    "templateInsertionDirection",
                    "templateUndercutSurfaceModel",
                    "templateUndercutBlockoutModel",
                }
            ),
            "patientShell": "patientContactShellModel" in fields,
            "legacyResearch": bool(
                fields
                & {
                    "templateShellRoi",
                    "researchTemplateShellModel",
                    "researchTemplateSleeveModel",
                }
            ),
            "legacyFinalization": bool(
                fields
                & {
                    "templateTrimPlane",
                    "templateTrimCurve",
                    "finalizedTemplateShellModel",
                }
            ),
            "finalTemplate": bool(
                fields
                & {
                    "templateDockingAssemblyModel",
                    "templateDockingClearanceModel",
                    "templateDockingReinforcementModel",
                    "templateDockingChannelsModel",
                    "finalPrintableTemplateModel",
                }
            ),
            "selectedGuideReference": bool(
                self.getSelectedTemplateGuideTrajectories()
            ),
        }
        impact = self._workflowImpactFromEntries(entries, flags)
        impact["clearAllSelectedGuideReferences"] = True
        return impact

    def getTrajectoryDependentWorkflowImpact(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> dict:
        self.validateDentobotTrajectoryForDeletion(trajectoryNode)
        allEntries = self._activePlanningDownstreamEntries()
        affectedIds = {trajectoryNode.GetID()}
        affectedEntries = []
        remaining = list(allEntries)
        changed = True
        while changed:
            changed = False
            for entry in list(remaining):
                node = entry["node"]
                if any(
                    self._mrmlNodeReferencesNode(
                        node,
                        slicer.mrmlScene.GetNodeByID(nodeId),
                    )
                    for nodeId in affectedIds
                    if slicer.mrmlScene.GetNodeByID(nodeId)
                ):
                    affectedIds.add(entry["nodeId"])
                    affectedEntries.append(entry)
                    remaining.remove(entry)
                    changed = True

        selectedGuideReference = trajectoryNode in (
            self.getSelectedTemplateGuideTrajectories()
        )
        affectedFields = {entry["field"] for entry in affectedEntries}
        flags = {
            "targetDocking": bool(
                affectedFields
                & {"targetDockingReferencePlane", "targetDockingAssemblyModel"}
            ),
            "draftSupport": False,
            "supportSelection": bool(
                affectedFields
                & {
                    "templateSupportBoundaryCurve",
                    "templateSupportBoundaryPlane",
                    "visibleTemplateSupportModel",
                }
            ),
            "undercut": bool(
                affectedFields
                & {
                    "templateInsertionDirection",
                    "templateUndercutSurfaceModel",
                    "templateUndercutBlockoutModel",
                }
            ),
            "patientShell": "patientContactShellModel" in affectedFields,
            "legacyResearch": bool(
                affectedFields
                & {
                    "templateShellRoi",
                    "researchTemplateShellModel",
                    "researchTemplateSleeveModel",
                }
            ),
            "legacyFinalization": bool(
                affectedFields
                & {
                    "templateTrimPlane",
                    "templateTrimCurve",
                    "finalizedTemplateShellModel",
                }
            ),
            "finalTemplate": bool(
                affectedFields
                & {
                    "templateDockingAssemblyModel",
                    "templateDockingClearanceModel",
                    "templateDockingReinforcementModel",
                    "templateDockingChannelsModel",
                    "finalPrintableTemplateModel",
                }
            ),
            "selectedGuideReference": selectedGuideReference,
        }
        if flags["supportSelection"]:
            flags["undercut"] = flags["patientShell"] = True
            flags["legacyResearch"] = flags["legacyFinalization"] = True
            flags["finalTemplate"] = True
        if flags["undercut"]:
            flags["patientShell"] = True
            flags["finalTemplate"] = True
        if flags["patientShell"] or flags["targetDocking"]:
            flags["finalTemplate"] = True
        if flags["legacyResearch"]:
            flags["legacyFinalization"] = True
        if selectedGuideReference:
            flags["finalTemplate"] = True

        cascadeFields = set()
        if flags["targetDocking"]:
            cascadeFields.update(
                {"targetDockingReferencePlane", "targetDockingAssemblyModel"}
            )
        if flags["supportSelection"]:
            cascadeFields.update(
                {
                    "templateSupportBoundaryCurve",
                    "templateSupportBoundaryPlane",
                    "visibleTemplateSupportModel",
                }
            )
        if flags["undercut"]:
            cascadeFields.update(
                {
                    "templateInsertionDirection",
                    "templateUndercutSurfaceModel",
                    "templateUndercutBlockoutModel",
                }
            )
        if flags["patientShell"]:
            cascadeFields.add("patientContactShellModel")
        if flags["legacyResearch"]:
            cascadeFields.update(
                {
                    "templateShellRoi",
                    "researchTemplateShellModel",
                    "researchTemplateSleeveModel",
                }
            )
        if flags["legacyFinalization"]:
            cascadeFields.update(
                {
                    "templateTrimPlane",
                    "templateTrimCurve",
                    "finalizedTemplateShellModel",
                }
            )
        if flags["finalTemplate"]:
            cascadeFields.update(
                {
                    "templateDockingAssemblyModel",
                    "templateDockingClearanceModel",
                    "templateDockingReinforcementModel",
                    "templateDockingChannelsModel",
                    "finalPrintableTemplateModel",
                }
            )
        affectedEntries = [
            entry for entry in allEntries if entry["field"] in cascadeFields
        ]
        impact = self._workflowImpactFromEntries(affectedEntries, flags)
        impact["hasDependents"] = bool(affectedEntries)
        impact["trajectoryNodeId"] = trajectoryNode.GetID()
        return impact

    def _deletePlanningDownstreamFromImpact(self, impact: dict) -> dict:
        parameterNode = self.getParameterNode()
        flags = dict(impact.get("flags") or {})
        removals = []
        deletionErrors = []
        impactedNodeIds = set(impact.get("nodeIds") or [])

        def attemptDeletion(label: str, callback) -> None:
            try:
                result = callback()
                if isinstance(result, list):
                    removals.extend(result)
                elif result:
                    removals.append(result)
            except (RuntimeError, ValueError) as exc:
                deletionErrors.append(f"{label}: {exc}")
                logging.warning(
                    "Could not use the normal %s deletion path while "
                    "backtracking a saved scene; owned-node fallback will run: %s",
                    label,
                    exc,
                )

        parameterMrmlNode = parameterNode.parameterNode
        wasModifying = parameterMrmlNode.StartModify()
        try:
            finalModel = parameterNode.finalPrintableTemplateModel
            if flags.get("finalTemplate") and self.isFinalPrintableTemplateModelNode(
                finalModel
            ):
                attemptDeletion(
                    "Step 5C final template",
                    lambda: self.deleteFinalPrintableTemplate(finalModel),
                )

            if flags.get("legacyFinalization") and any(
                (
                    parameterNode.templateTrimPlane,
                    parameterNode.templateTrimCurve,
                    parameterNode.finalizedTemplateShellModel,
                )
            ):
                attemptDeletion(
                    "legacy Step 5C finalization",
                    lambda: self.deleteTemplateFinalization(
                        parameterNode.templateTrimPlane,
                        parameterNode.templateTrimCurve,
                        parameterNode.finalizedTemplateShellModel,
                    ),
                )

            if flags.get("legacyResearch") and any(
                (
                    parameterNode.researchTemplateShellModel,
                    parameterNode.researchTemplateSleeveModel,
                )
            ):
                attemptDeletion(
                    "legacy Step 5B models",
                    lambda: self.deleteResearchTemplateModels(
                        parameterNode.researchTemplateShellModel,
                        parameterNode.researchTemplateSleeveModel,
                    ),
                )
            if (
                flags.get("legacyResearch")
                and self.isTemplateShellRoiNode(parameterNode.templateShellRoi)
            ):
                attemptDeletion(
                    "legacy Step 5B ROI",
                    lambda: self.deleteTemplateShellRoi(
                        parameterNode.templateShellRoi
                    ),
                )

            if flags.get("patientShell") and self.isPatientContactShellModelNode(
                parameterNode.patientContactShellModel
            ):
                attemptDeletion(
                    "Step 5B patient-contact shell",
                    lambda: self.deletePatientContactShell(
                        parameterNode.patientContactShellModel
                    ),
                )

            if flags.get("undercut") and any(
                (
                    parameterNode.templateInsertionDirection,
                    parameterNode.templateUndercutSurfaceModel,
                    parameterNode.templateUndercutBlockoutModel,
                )
            ):
                attemptDeletion(
                    "Step 5B insertion/undercut",
                    lambda: self.deleteTemplateUndercutWorkflow(
                        parameterNode.templateInsertionDirection,
                        parameterNode.templateUndercutSurfaceModel,
                        parameterNode.templateUndercutBlockoutModel,
                    ),
                )

            if flags.get("supportSelection") and any(
                (
                    parameterNode.templateSupportBoundaryCurve,
                    parameterNode.visibleTemplateSupportModel,
                    parameterNode.templateSupportBoundaryPlane,
                )
            ):
                attemptDeletion(
                    "Step 5A visible support selection",
                    lambda: self.deleteTemplateSupportSelection(
                        parameterNode.templateSupportBoundaryCurve,
                        parameterNode.visibleTemplateSupportModel,
                        parameterNode.templateSupportBoundaryPlane,
                    ),
                )

            if flags.get("targetDocking") and self.isTargetDockingAssemblyModelNode(
                parameterNode.targetDockingAssemblyModel
            ):
                attemptDeletion(
                    "Step 4C docking assembly",
                    lambda: self.deleteTargetDockingAssembly(
                        parameterNode.targetDockingAssemblyModel
                    ),
                )

            if flags.get("draftSupport") and self.isDraftTemplateSupportModelNode(
                parameterNode.draftTemplateSupportModel
            ):
                attemptDeletion(
                    "Step 4B draft support",
                    lambda: self.deleteDraftTemplateSupportModel(
                        parameterNode.draftTemplateSupportModel
                    ),
                )

            if flags.get("selectedGuideReference"):
                role = self.TEMPLATE_SELECTED_GUIDE_TRAJECTORY_REFERENCE_ROLE
                retainedIds = []
                trajectoryNodeId = impact.get("trajectoryNodeId")
                if not impact.get("clearAllSelectedGuideReferences"):
                    retainedIds = [
                        node.GetID()
                        for node in self.getSelectedTemplateGuideTrajectories()
                        if node.GetID() != trajectoryNodeId
                    ]
                parameterMrmlNode.RemoveNodeReferenceIDs(role)
                for nodeId in retainedIds:
                    parameterMrmlNode.AddNodeReferenceID(role, nodeId)
        finally:
            parameterMrmlNode.EndModify(wasModifying)

        # Old MRB scenes may contain stale or partially migrated derived nodes
        # that fail a modern role-specific validator. Remove only nodes that
        # were explicitly reached through the active parameter-node branch.
        removedByNormalPath = {
            removal["nodeId"]
            for removal in removals
            if removal and removal.get("nodeId")
        }
        for nodeId in impactedNodeIds - removedByNormalPath:
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            if node and slicer.mrmlScene.IsNodePresent(node):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(node))

        removedNodeIds = []
        for removal in removals:
            if not removal:
                continue
            removedNodeIds.append(removal["nodeId"])
            removedNodeIds.extend(removal.get("auxiliaryNodeIds", []))
        return {
            "impact": impact,
            "removals": removals,
            "removedNodeIds": removedNodeIds,
            "deletionErrors": deletionErrors,
        }

    def deleteTrajectoryDependentWorkflow(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        *,
        impact: dict | None = None,
    ) -> dict:
        self.validateDentobotTrajectoryForDeletion(trajectoryNode)
        impact = impact or self.getTrajectoryDependentWorkflowImpact(
            trajectoryNode
        )
        return self._deletePlanningDownstreamFromImpact(impact)

    def deleteActivePlanningDownstreamWorkflow(
        self,
        *,
        impact: dict | None = None,
    ) -> dict:
        impact = impact or self.getActivePlanningDownstreamImpact()
        return self._deletePlanningDownstreamFromImpact(impact)

    def deleteTrajectoryNode(
        self,
        trajectoryNode: vtkMRMLMarkupsLineNode,
    ) -> dict:
        """Delete one trajectory plus descendants, preserving target inputs."""

        self.validateDentobotTrajectoryForDeletion(trajectoryNode)
        impact = self.getTrajectoryDependentWorkflowImpact(trajectoryNode)
        downstreamDeletion = None
        if (
            impact["hasDependents"]
            or impact.get("flags", {}).get("selectedGuideReference")
        ):
            downstreamDeletion = self.deleteTrajectoryDependentWorkflow(
                trajectoryNode,
                impact=impact,
            )
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if (
            selectionNode
            and selectionNode.GetActivePlaceNodeID() == trajectoryNode.GetID()
        ):
            self.stopTrajectoryPlacement()
        parameterNode = self.getParameterNode()
        if parameterNode.trajectoryLine is trajectoryNode:
            parameterNode.trajectoryLine = None
        removal = self._removeSceneNodeAndOwnedAuxiliaries(trajectoryNode)
        removal["downstreamDeletion"] = downstreamDeletion
        return removal
