"""Extracted docking and printable guide methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.logic_docking import DockingLogicMixin


class GuideLogicMixin(DockingLogicMixin):











    def getEligibleTemplateGuideTrajectories(
        self,
        sourceModel: vtkMRMLModelNode,
    ) -> list[vtkMRMLMarkupsLineNode]:
        """Return trajectories for the current target tooth."""

        sourceSummary = self.getDraftTemplateSupportModelSummary(sourceModel)
        sourceSegmentation = sourceSummary["sourceSegmentation"]
        eligible = []
        for trajectoryNode in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode"):
            if not self.isDentobotTrajectoryNode(trajectoryNode):
                continue
            association = self.getTrajectoryTargetAssociation(trajectoryNode)
            if not association:
                continue
            if (
                association["segmentationNode"] is sourceSegmentation
                and association["targetRecord"]["segmentId"]
                == sourceSummary["targetSegmentId"]
            ):
                eligible.append(trajectoryNode)
        return eligible

    def getSelectedTemplateGuideTrajectories(
        self,
    ) -> list[vtkMRMLMarkupsLineNode]:
        parameterMrmlNode = self.getParameterNode().parameterNode
        role = self.TEMPLATE_SELECTED_GUIDE_TRAJECTORY_REFERENCE_ROLE
        return [
            parameterMrmlNode.GetNthNodeReference(role, index)
            for index in range(parameterMrmlNode.GetNumberOfNodeReferences(role))
            if parameterMrmlNode.GetNthNodeReference(role, index)
        ]

    def setSelectedTemplateGuideTrajectories(
        self,
        sourceModel: vtkMRMLModelNode,
        trajectories: list[vtkMRMLMarkupsLineNode],
    ) -> None:
        self.requireCaseFoundationPose(self.getParameterNode())
        if not 1 <= len(trajectories) <= 2:
            raise ValueError(_("Select one trajectory, or an explicit pair at most."))
        eligibleById = {
            node.GetID(): node
            for node in self.getEligibleTemplateGuideTrajectories(sourceModel)
        }
        selectedIds = []
        for trajectoryNode in trajectories:
            if not trajectoryNode or trajectoryNode.GetID() not in eligibleById:
                raise ValueError(
                    _("Every guide trajectory must belong to the current target tooth.")
                )
            if trajectoryNode.GetID() in selectedIds:
                raise ValueError(_("A guide trajectory cannot be selected more than once."))
            selectedIds.append(trajectoryNode.GetID())
        parameterMrmlNode = self.getParameterNode().parameterNode
        role = self.TEMPLATE_SELECTED_GUIDE_TRAJECTORY_REFERENCE_ROLE
        wasModifying = parameterMrmlNode.StartModify()
        try:
            parameterMrmlNode.RemoveNodeReferenceIDs(role)
            for nodeId in selectedIds:
                parameterMrmlNode.AddNodeReferenceID(role, nodeId)
        finally:
            parameterMrmlNode.EndModify(wasModifying)

    def _validateFinalGuideInputs(
        self,
        patientShell: vtkMRMLModelNode,
        targetDockingAssembly: vtkMRMLModelNode,
        trajectories: list[vtkMRMLMarkupsLineNode],
        parameters: dict[str, float],
    ) -> dict:
        foundation = self.requireCaseFoundationPose(self.getParameterNode())
        shellSummary = self.getPatientContactShellSummary(patientShell)
        if shellSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale patient-contact shell first."))
        if not trajectories:
            raise ValueError(_("Select at least one guide trajectory."))
        if len(trajectories) > 2:
            raise ValueError(_("A unified template supports two trajectories at most."))
        sourceSummary = self.getDraftTemplateSupportModelSummary(
            shellSummary["sourceModel"]
        )
        targetDockingSummary = self.getTargetDockingAssemblySummary(
            targetDockingAssembly
        )
        if targetDockingSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale Step 4C docking assembly first."))
        if targetDockingSummary["orientationState"] != "Confirmed":
            raise ValueError(
                _(
                    "Confirm the collision-screened Step 4C dock orientation "
                    "before integrating it with the patient-contact shell."
                )
            )
        if (
            targetDockingSummary["segmentation"]
            is not sourceSummary["sourceSegmentation"]
            or targetDockingSummary["targetSegmentId"]
            != sourceSummary["targetSegmentId"]
        ):
            raise ValueError(
                _("The Step 4C docking assembly belongs to another target anatomy.")
            )
        if [node.GetID() for node in targetDockingSummary["trajectories"]] != [
            node.GetID() for node in trajectories
        ]:
            raise ValueError(
                _("The Step 4C assembly must match the selected guide trajectory or explicit pair.")
            )
        eligibleIds = {
            node.GetID()
            for node in self.getEligibleTemplateGuideTrajectories(
                shellSummary["sourceModel"]
            )
        }
        trajectoryRecords = []
        seenIds = set()
        jawOwners = set()
        for trajectoryNode in trajectories:
            if not self.isDentobotTrajectoryNode(trajectoryNode):
                raise ValueError(_("Select only DENTOBOT Entry-to-Target trajectories."))
            if trajectoryNode.GetID() in seenIds:
                raise ValueError(_("A guide trajectory cannot be selected more than once."))
            seenIds.add(trajectoryNode.GetID())
            if trajectoryNode.GetID() not in eligibleIds:
                raise ValueError(
                    _("A selected trajectory is not associated with this support anatomy.")
                )
            summary = self.getTrajectorySummary(trajectoryNode)
            if not summary["isValid"] or summary["definedPointCount"] != 2:
                raise ValueError(_("Every guide trajectory needs valid Entry and Target points."))
            if not trajectoryNode.GetLocked():
                raise ValueError(_("Lock every selected trajectory before guide fusion."))
            jawOwner = self.bindCaseFoundationNode(
                self.getParameterNode(), trajectoryNode
            )
            jawOwners.add(jawOwner)
            trajectoryRecords.append(
                {
                    "node": trajectoryNode,
                    "entryRas": tuple(float(value) for value in summary["entryRas"]),
                    "targetRas": tuple(float(value) for value in summary["targetRas"]),
                    "lengthMm": float(summary["lengthMm"]),
                }
            )
        if len(jawOwners) != 1 or "" in jawOwners:
            raise ValueError(
                _("A trajectory pair must share one target identity and jaw owner.")
            )
        return {
            "shellSummary": shellSummary,
            "sourceSummary": sourceSummary,
            "targetDockingSummary": targetDockingSummary,
            "trajectories": trajectoryRecords,
            "parameters": parameters,
            "planningPoseFingerprint": foundation["planning_pose_fingerprint"],
        }

    @staticmethod
    def _setRepeatedNodeReferences(modelNode, role: str, nodes: list) -> None:
        modelNode.RemoveNodeReferenceIDs(role)
        for node in nodes:
            modelNode.AddNodeReferenceID(role, node.GetID())

    def createOrUpdateFinalPrintableTemplate(
        self,
        patientShell: vtkMRMLModelNode,
        targetDockingAssembly: vtkMRMLModelNode,
        trajectories: list[vtkMRMLMarkupsLineNode],
        *,
        outerDiameterMm: float,
        innerDiameterMm: float,
        heightMm: float,
        dockingClearanceMm: float,
        reinforcementRadialMm: float,
        reinforcementDepthMm: float,
        samplingSpacingMm: float,
        dockingModel: vtkMRMLModelNode | None = None,
        clearanceModel: vtkMRMLModelNode | None = None,
        reinforcementModel: vtkMRMLModelNode | None = None,
        channelsModel: vtkMRMLModelNode | None = None,
        finalModel: vtkMRMLModelNode | None = None,
    ) -> tuple[vtkMRMLModelNode, dict[str, vtkMRMLModelNode], dict]:
        foundation = self.requireCaseFoundationPose(self.getParameterNode())
        parameters = normalize_docking_parameters(
            outer_diameter_mm=outerDiameterMm,
            inner_diameter_mm=innerDiameterMm,
            height_mm=heightMm,
            clearance_mm=dockingClearanceMm,
            reinforcement_radial_mm=reinforcementRadialMm,
            reinforcement_depth_mm=reinforcementDepthMm,
            processing_resolution_mm=samplingSpacingMm,
        )
        inputs = self._validateFinalGuideInputs(
            patientShell,
            targetDockingAssembly,
            trajectories,
            parameters,
        )
        trajectoryGeometry = [
            {
                "entryRas": record["entryRas"],
                "targetRas": record["targetRas"],
            }
            for record in inputs["trajectories"]
        ]
        trajectorySurfaces, trajectoryAssemblyMetrics = create_multi_trajectory_docking_geometry(
            trajectoryGeometry,
            parameters,
        )
        targetDockingParameters = json.loads(
            inputs["targetDockingSummary"]["parametersJson"]
        )
        targetDockingSurfaces, targetDockingMetrics = (
            create_target_frame_docking_geometry(
                inputs["targetDockingSummary"]["frame"],
                targetDockingParameters,
            )
        )
        shellContactBranches, shellContactMetrics = (
            create_independent_shell_contact_reinforcements(
                model_polydata_in_world(patientShell),
                targetDockingSurfaces["dockComponents"],
                dock_metrics=targetDockingMetrics["docks"],
                bridge_diameter_mm=max(
                    float(targetDockingParameters["connectorDiameterMm"]),
                    2.0 * float(parameters["reinforcementRadialMm"]),
                ),
                bore_radius_mm=(
                    float(targetDockingParameters["boreDiameterMm"]) / 2.0
                ),
                reinforcement_outer_radius_mm=(
                    float(targetDockingParameters["outerDiameterMm"]) / 2.0
                    + float(targetDockingParameters["reinforcementRadialMm"])
                ),
                reinforcement_depth_mm=float(
                    targetDockingParameters["reinforcementRadialMm"]
                ),
                processing_spacing_mm=float(
                    targetDockingParameters["processingResolutionMm"]
                ),
                endpoint_overlap_mm=float(
                    targetDockingParameters["connectorThicknessMm"]
                ),
            )
        )
        reinforcementAppend = vtk.vtkAppendPolyData()
        reinforcementAppend.AddInputData(targetDockingSurfaces["reinforcement"])
        reinforcementAppend.AddInputData(shellContactBranches)
        reinforcementAppend.Update()
        reinforcementTriangle = vtk.vtkTriangleFilter()
        reinforcementTriangle.SetInputConnection(reinforcementAppend.GetOutputPort())
        reinforcementTriangle.Update()
        reinforcedTargetDocking = vtk.vtkPolyData()
        reinforcedTargetDocking.DeepCopy(reinforcementTriangle.GetOutput())
        protectedTargetDocking, dockingExclusionMetrics = subtract_guide_exclusion(
            targetDockingSurfaces["docking"],
            trajectorySurfaces["clearance"],
            spacing_mm=parameters["processingResolutionMm"],
            scalar_name="DENTOBOT.TargetDockingGuideExclusionMask",
        )
        if int(dockingExclusionMetrics.get("excludedOccupiedSampleCount", 0)) > 0:
            raise ValueError(
                _(
                    "A Step 4C robot dock intersects the protected trajectory-guide envelope. Increase the centroid-to-dock radius or revise the approved geometry; DENTOBOT will not trim a load-bearing dock to make it fit."
                )
            )
        protectedTargetReinforcement, reinforcementExclusionMetrics = (
            subtract_guide_exclusion(
                reinforcedTargetDocking,
                trajectorySurfaces["clearance"],
                spacing_mm=parameters["processingResolutionMm"],
                scalar_name="DENTOBOT.TargetDockingReinforcementGuideExclusionMask",
            )
        )
        targetDockingSurfaces = {
            **targetDockingSurfaces,
            "docking": protectedTargetDocking,
            "reinforcement": protectedTargetReinforcement,
        }
        surfaces = combine_guide_geometry_sets(
            (trajectorySurfaces, targetDockingSurfaces)
        )
        assemblyMetrics = {
            "method": "SeparatedTrajectoryGuidesAndFourOcclusalDockBranchesV3",
            "trajectoryGuide": trajectoryAssemblyMetrics,
            "targetDocking": targetDockingMetrics,
            "shellContactBranches": shellContactMetrics,
            # Compatibility alias for older report readers.
            "shellContactReinforcement": shellContactMetrics,
            "trajectoryGuideExclusion": {
                "docking": dockingExclusionMetrics,
                "reinforcement": reinforcementExclusionMetrics,
            },
            "trajectoryCount": len(trajectoryGeometry),
            "dockCount": int(targetDockingMetrics.get("dockCount", 0)),
        }
        finalPolyData, fusionMetrics = fuse_shell_and_docking_voxel(
            model_polydata_in_world(patientShell),
            surfaces["docking"],
            surfaces["clearance"],
            surfaces["reinforcement"],
            surfaces["channels"],
            sampling_spacing_mm=parameters["processingResolutionMm"],
        )
        roleModels = {
            "docking": self._createOrReuseRoleModel(
                dockingModel,
                "TemplateDockingAssembly",
                "[Step 5B] DENTO Trajectory Guides and Robot Docks",
            ),
            "clearance": self._createOrReuseRoleModel(
                clearanceModel,
                "TemplateDockingClearance",
                "[Step 5B] DENTO Docking Clearance (auxiliary)",
            ),
            "reinforcement": self._createOrReuseRoleModel(
                reinforcementModel,
                "TemplateDockingReinforcement",
                "[Step 5B] DENTO Guide Collars and Dock Attachments",
            ),
            "channels": self._createOrReuseRoleModel(
                channelsModel,
                "TemplateDockingChannels",
                "[Step 5B] DENTO Guide and Dock Channels (auxiliary)",
            ),
        }
        finalModel = self._createOrReuseRoleModel(
            finalModel,
            "FinalPrintableTemplate",
            "[Step 5C] DENTO Final Printable Template",
        )
        parametersJson = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        trajectoryJson = json.dumps(
            trajectoryGeometry,
            sort_keys=True,
            separators=(",", ":"),
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        sourceTrajectoryNodes = [record["node"] for record in inputs["trajectories"]]
        modelRoles = {
            "docking": "TemplateDockingAssembly",
            "clearance": "TemplateDockingClearance",
            "reinforcement": "TemplateDockingReinforcement",
            "channels": "TemplateDockingChannels",
        }
        for key, modelNode in roleModels.items():
            wasModifying = modelNode.StartModify()
            try:
                modelNode.SetAndObservePolyData(surfaces[key])
                modelNode.SetAndObserveTransformNodeID(None)
                modelNode.SetAttribute("DENTOBOT.ModelRole", modelRoles[key])
                modelNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
                modelNode.SetAttribute("DENTOBOT.GeometryState", "Current")
                modelNode.SetAttribute("DENTOBOT.StaleReason", None)
                modelNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
                modelNode.SetAttribute("DENTOBOT.ParametersJson", parametersJson)
                modelNode.SetAttribute("DENTOBOT.TrajectoryGeometryJson", trajectoryJson)
                modelNode.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
                modelNode.SetAttribute(
                    "DENTOBOT.PlanningPoseFingerprint",
                    foundation["planning_pose_fingerprint"],
                )
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_FINAL_GUIDE_PATIENT_SHELL_REFERENCE_ROLE,
                    patientShell.GetID(),
                )
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_FINAL_GUIDE_TARGET_DOCKING_REFERENCE_ROLE,
                    targetDockingAssembly.GetID(),
                )
                self._setRepeatedNodeReferences(
                    modelNode,
                    self.TEMPLATE_FINAL_GUIDE_SOURCE_TRAJECTORY_REFERENCE_ROLE,
                    sourceTrajectoryNodes,
                )
            finally:
                modelNode.EndModify(wasModifying)
            modelNode.CreateDefaultDisplayNodes()
            displayNode = modelNode.GetDisplayNode()
            if displayNode:
                displayNode.SetVisibility(key in {"docking", "reinforcement"})
                displayNode.SetVisibility2D(False)
                displayNode.SetVisibility3D(True)
                displayNode.SetBackfaceCulling(False)
        displayColors = {
            "docking": (0.10, 0.72, 0.92),
            "clearance": (0.90, 0.25, 0.22),
            "reinforcement": (0.95, 0.58, 0.12),
            "channels": (0.42, 0.20, 0.82),
        }
        for key, color in displayColors.items():
            roleModels[key].GetDisplayNode().SetColor(*color)
            roleModels[key].GetDisplayNode().SetOpacity(
                0.35 if key in {"clearance", "channels"} else 1.0
            )

        wasModifying = finalModel.StartModify()
        try:
            finalModel.SetAndObservePolyData(finalPolyData)
            finalModel.SetAndObserveTransformNodeID(None)
            finalModel.SetAttribute("DENTOBOT.ModelRole", "FinalPrintableTemplate")
            finalModel.SetAttribute(
                "DENTOBOT.FinalGuideSchemaVersion",
                self.TEMPLATE_FINAL_GUIDE_SCHEMA_VERSION,
            )
            finalModel.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            finalModel.SetAttribute("DENTOBOT.GeometryState", "Current")
            finalModel.SetAttribute("DENTOBOT.StaleReason", None)
            finalModel.SetAttribute("DENTOBOT.VerificationState", "NotVerified")
            finalModel.SetAttribute(
                "DENTOBOT.PairingIntent",
                "Single" if len(sourceTrajectoryNodes) == 1 else "ExplicitPair",
            )
            finalModel.SetAttribute(
                "DENTOBOT.PrimaryTrajectoryNodeID", sourceTrajectoryNodes[0].GetID()
            )
            finalModel.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            finalModel.SetAttribute("DENTOBOT.ParametersJson", parametersJson)
            finalModel.SetAttribute("DENTOBOT.TrajectoryGeometryJson", trajectoryJson)
            finalModel.SetAttribute(
                "DENTOBOT.PatientShellUpdatedUtc",
                patientShell.GetAttribute("DENTOBOT.UpdatedUtc") or "",
            )
            finalModel.SetAttribute(
                "DENTOBOT.TargetDockingUpdatedUtc",
                targetDockingAssembly.GetAttribute("DENTOBOT.UpdatedUtc") or "",
            )
            finalModel.SetAttribute(
                "DENTOBOT.GeometryMetricsJson",
                json.dumps(fusionMetrics, sort_keys=True, separators=(",", ":")),
            )
            finalModel.SetAttribute(
                "DENTOBOT.DockingMetricsJson",
                json.dumps(assemblyMetrics, sort_keys=True, separators=(",", ":")),
            )
            finalModel.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
            finalModel.SetAttribute(
                "DENTOBOT.PlanningPoseFingerprint",
                foundation["planning_pose_fingerprint"],
            )
            finalModel.SetNodeReferenceID(
                self.TEMPLATE_FINAL_GUIDE_PATIENT_SHELL_REFERENCE_ROLE,
                patientShell.GetID(),
            )
            finalModel.SetNodeReferenceID(
                self.TEMPLATE_FINAL_GUIDE_TARGET_DOCKING_REFERENCE_ROLE,
                targetDockingAssembly.GetID(),
            )
            finalModel.SetNodeReferenceID(
                self.TEMPLATE_FINAL_GUIDE_DOCKING_REFERENCE_ROLE,
                roleModels["docking"].GetID(),
            )
            finalModel.SetNodeReferenceID(
                self.TEMPLATE_FINAL_GUIDE_CLEARANCE_REFERENCE_ROLE,
                roleModels["clearance"].GetID(),
            )
            finalModel.SetNodeReferenceID(
                self.TEMPLATE_FINAL_GUIDE_REINFORCEMENT_REFERENCE_ROLE,
                roleModels["reinforcement"].GetID(),
            )
            finalModel.SetNodeReferenceID(
                self.TEMPLATE_FINAL_GUIDE_CHANNELS_REFERENCE_ROLE,
                roleModels["channels"].GetID(),
            )
            self._setRepeatedNodeReferences(
                finalModel,
                self.TEMPLATE_FINAL_GUIDE_SOURCE_TRAJECTORY_REFERENCE_ROLE,
                sourceTrajectoryNodes,
            )
        finally:
            finalModel.EndModify(wasModifying)
        finalModel.CreateDefaultDisplayNodes()
        finalDisplay = finalModel.GetDisplayNode()
        if finalDisplay:
            finalDisplay.SetVisibility(True)
            finalDisplay.SetVisibility2D(False)
            finalDisplay.SetVisibility3D(True)
            finalDisplay.SetColor(0.95, 0.72, 0.20)
            finalDisplay.SetBackfaceCulling(False)
        patientDisplay = patientShell.GetDisplayNode()
        if patientDisplay:
            patientDisplay.SetVisibility(False)
        for modelNode in roleModels.values():
            lineageColor = self.lineageColorFromNode(patientShell)
            if lineageColor:
                self.setNodeLineageColor(
                    modelNode,
                    lineageColor,
                    patientShell.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                    patientShell.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
                )
        for node in (
            patientShell,
            targetDockingAssembly,
            finalModel,
            *roleModels.values(),
        ):
            self.bindCaseFoundationNode(self.getParameterNode(), node)
        return finalModel, roleModels, {
            "parameters": parameters,
            "assembly": assemblyMetrics,
            "fusion": fusionMetrics,
        }

    @staticmethod
    def isFinalPrintableTemplateModelNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole") == "FinalPrintableTemplate"
        )

    def getFinalPrintableTemplateSummary(self, finalModel: vtkMRMLModelNode) -> dict:
        if not self.isFinalPrintableTemplateModelNode(finalModel):
            raise ValueError(_("Select the DENTOBOT final printable template."))
        polyData = finalModel.GetPolyData()
        if not polyData or not polyData.GetNumberOfCells():
            raise ValueError(_("The final printable template contains no geometry."))
        patientShell = finalModel.GetNodeReference(
            self.TEMPLATE_FINAL_GUIDE_PATIENT_SHELL_REFERENCE_ROLE
        )
        targetDockingAssembly = finalModel.GetNodeReference(
            self.TEMPLATE_FINAL_GUIDE_TARGET_DOCKING_REFERENCE_ROLE
        )
        roleModels = {
            "docking": finalModel.GetNodeReference(
                self.TEMPLATE_FINAL_GUIDE_DOCKING_REFERENCE_ROLE
            ),
            "clearance": finalModel.GetNodeReference(
                self.TEMPLATE_FINAL_GUIDE_CLEARANCE_REFERENCE_ROLE
            ),
            "reinforcement": finalModel.GetNodeReference(
                self.TEMPLATE_FINAL_GUIDE_REINFORCEMENT_REFERENCE_ROLE
            ),
            "channels": finalModel.GetNodeReference(
                self.TEMPLATE_FINAL_GUIDE_CHANNELS_REFERENCE_ROLE
            ),
        }
        expectedRoles = {
            "docking": "TemplateDockingAssembly",
            "clearance": "TemplateDockingClearance",
            "reinforcement": "TemplateDockingReinforcement",
            "channels": "TemplateDockingChannels",
        }
        if not self.isPatientContactShellModelNode(patientShell):
            raise ValueError(_("The final template lost its patient-shell reference."))
        if not self.isTargetDockingAssemblyModelNode(targetDockingAssembly):
            raise ValueError(_("The final template lost its Step 4C docking reference."))
        for key, modelNode in roleModels.items():
            if (
                not modelNode
                or modelNode.GetAttribute("DENTOBOT.ModelRole") != expectedRoles[key]
            ):
                raise ValueError(_("The final template lost a docking provenance model."))
        role = self.TEMPLATE_FINAL_GUIDE_SOURCE_TRAJECTORY_REFERENCE_ROLE
        trajectories = [
            finalModel.GetNthNodeReference(role, index)
            for index in range(finalModel.GetNumberOfNodeReferences(role))
            if finalModel.GetNthNodeReference(role, index)
        ]
        if not trajectories:
            raise ValueError(_("The final template lost its source trajectory references."))
        schemaVersion = (
            finalModel.GetAttribute("DENTOBOT.FinalGuideSchemaVersion") or "Legacy"
        )
        geometryState = finalModel.GetAttribute("DENTOBOT.GeometryState") or "Unknown"
        staleReason = finalModel.GetAttribute("DENTOBOT.StaleReason") or ""
        if schemaVersion != self.TEMPLATE_FINAL_GUIDE_SCHEMA_VERSION:
            geometryState = "Stale"
            staleReason = _(
                "This final template predates through-bore protection for the Step 4C docks; regenerate it."
            )
        return {
            "schemaVersion": schemaVersion,
            "geometryState": geometryState,
            "staleReason": staleReason,
            "verificationState": finalModel.GetAttribute("DENTOBOT.VerificationState") or "NotVerified",
            "patientShell": patientShell,
            "targetDockingAssembly": targetDockingAssembly,
            "roleModels": roleModels,
            "trajectories": trajectories,
            "parametersJson": finalModel.GetAttribute("DENTOBOT.ParametersJson") or "",
            "trajectoryGeometryJson": finalModel.GetAttribute("DENTOBOT.TrajectoryGeometryJson") or "",
            "patientShellUpdatedUtc": finalModel.GetAttribute("DENTOBOT.PatientShellUpdatedUtc") or "",
            "targetDockingUpdatedUtc": finalModel.GetAttribute("DENTOBOT.TargetDockingUpdatedUtc") or "",
            "metrics": json.loads(
                finalModel.GetAttribute("DENTOBOT.GeometryMetricsJson") or "{}"
            ),
            "dockingMetrics": json.loads(
                finalModel.GetAttribute("DENTOBOT.DockingMetricsJson") or "{}"
            ),
            "verification": json.loads(
                finalModel.GetAttribute("DENTOBOT.VerificationJson") or "{}"
            ),
        }

    @staticmethod
    def markFinalPrintableTemplateStale(
        finalModel: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        if not DENTOWorkflowLogic.isFinalPrintableTemplateModelNode(finalModel):
            return False
        finalModel.SetAttribute("DENTOBOT.GeometryState", "Stale")
        finalModel.SetAttribute("DENTOBOT.VerificationState", "NotVerified")
        finalModel.SetAttribute("DENTOBOT.VerificationJson", None)
        finalModel.SetAttribute(
            "DENTOBOT.StaleReason",
            str(reason).strip() or "Patient shell, trajectory, or docking parameters changed.",
        )
        return True

    def verifyFinalPrintableTemplate(
        self,
        finalModel: vtkMRMLModelNode,
    ) -> dict:
        """Verify final geometry and its explicit MRML provenance.

        This is a computational research gate, not a clinical validation.  A
        WARNING may be exported after review; any FAIL blocks normal export.
        """

        self.requireCaseFoundationPose(self.getParameterNode())
        summary = self.getFinalPrintableTemplateSummary(finalModel)
        checks = []

        def add(result: str, name: str, details: str) -> None:
            checks.append(
                {
                    "result": str(result),
                    "name": str(name),
                    "details": str(details),
                }
            )

        if summary["geometryState"] == "Current":
            add("PASS", _("Derived-state freshness"), _("Final geometry is current."))
        else:
            add(
                "FAIL",
                _("Derived-state freshness"),
                summary["staleReason"] or _("Final geometry is stale."),
            )

        shellSummary = None
        try:
            shellSummary = self.getPatientContactShellSummary(summary["patientShell"])
            shellCurrent = shellSummary["geometryState"] == "Current"
            add(
                "PASS" if shellCurrent else "FAIL",
                _("Patient-contact shell provenance"),
                _("Current shell retains segmentation, visible support, boundary, insertion, blockout, and processing references.")
                if shellCurrent
                else shellSummary["staleReason"] or _("Patient-contact shell is stale."),
            )
            add(
                "PASS"
                if summary["patientShellUpdatedUtc"]
                == (summary["patientShell"].GetAttribute("DENTOBOT.UpdatedUtc") or "")
                else "FAIL",
                _("Patient-shell snapshot"),
                _("Final geometry was generated from the current patient shell.")
                if summary["patientShellUpdatedUtc"]
                == (summary["patientShell"].GetAttribute("DENTOBOT.UpdatedUtc") or "")
                else _("Patient shell changed after final fusion."),
            )
            visibleSummary = self.getVisibleTemplateSupportModelSummary(
                shellSummary["visibleSupport"]
            )
            visibleCurrent = visibleSummary["geometryState"] == "Current"
            fittingLimited = bool(
                visibleCurrent
                and visibleSummary["boundary"] is shellSummary["boundary"]
                and visibleSummary["sourceSegmentation"]
                is shellSummary["sourceSegmentation"]
            )
            add(
                "PASS" if fittingLimited else "FAIL",
                _("Visible-support fitting surface"),
                _("Fitting provenance is limited to the clinician-selected visible support ROI.")
                if fittingLimited
                else _("Visible-support ROI provenance is stale or inconsistent."),
            )
            directionSummary = self.getTemplateInsertionDirectionSummary(
                shellSummary["insertionDirection"]
            )
            insertionCurrent = (
                directionSummary["geometryJson"]
                == shellSummary["insertionGeometryJson"]
            )
            add(
                "PASS" if insertionCurrent else "FAIL",
                _("Insertion direction snapshot"),
                _("Undercut-aware shell uses the current world-RAS insertion direction.")
                if insertionCurrent
                else _("Insertion direction changed after shell generation."),
            )
            add(
                "PASS" if shellSummary["undercutState"] == "Processed" else "FAIL",
                _("Undercut/blockout processing"),
                _("Directional blockout is recorded in the shell provenance.")
                if shellSummary["undercutState"] == "Processed"
                else _("Shell does not record completed undercut processing."),
            )
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            add("FAIL", _("Patient-contact shell provenance"), str(exc))

        dockingSummary = None
        try:
            dockingSummary = self.getTargetDockingAssemblySummary(
                summary["targetDockingAssembly"]
            )
            dockingCurrent = dockingSummary["geometryState"] == "Current"
            add(
                "PASS" if dockingCurrent else "FAIL",
                _("Step 4C docking provenance"),
                _("Four-dock assembly and explicit source references are current.")
                if dockingCurrent
                else dockingSummary["staleReason"] or _("Step 4C assembly is stale."),
            )
            orientationConfirmed = (
                dockingSummary["orientationState"] == "Confirmed"
            )
            add(
                "PASS" if orientationConfirmed else "FAIL",
                _("Step 4C orientation confirmation"),
                _("The current collision-screened yaw was explicitly confirmed.")
                if orientationConfirmed
                else _("The Step 4C dock orientation is still a draft."),
            )
            collisionScreen = dockingSummary["metrics"].get(
                "collisionScreen"
            ) or {}
            collisionCount = int(collisionScreen.get("collidingDockCount", 0))
            omittedCount = len(
                dockingSummary.get("omittedObstacleSegmentIds") or []
            )
            add(
                "PASS" if collisionCount == 0 else "FAIL",
                _("Same-jaw dock collision screen"),
                _(
                    "No sampled collision was detected against %1 other "
                    "same-jaw whole-tooth surface(s)."
                ).replace(
                    "%1", str(collisionScreen.get("obstacleSurfaceCount", 0))
                )
                if collisionCount == 0
                else _("%1 dock(s) still intersect sampled same-jaw tooth geometry.")
                .replace("%1", str(collisionCount)),
            )
            if omittedCount:
                add(
                    "WARNING",
                    _("Same-jaw obstacle coverage"),
                    _(
                        "%1 whole-tooth surface(s) could not be included in "
                        "the draft collision screen."
                    ).replace("%1", str(omittedCount)),
                )
            dockingSnapshotCurrent = summary["targetDockingUpdatedUtc"] == (
                summary["targetDockingAssembly"].GetAttribute("DENTOBOT.UpdatedUtc")
                or ""
            )
            add(
                "PASS" if dockingSnapshotCurrent else "FAIL",
                _("Step 4C snapshot"),
                _("Final geometry uses the current Step 4C assembly.")
                if dockingSnapshotCurrent
                else _("Step 4C assembly changed after final fusion."),
            )
            dockCount = int(dockingSummary["metrics"].get("dockCount", 0))
            topResidual = float(
                dockingSummary["metrics"].get("topPlaneMaxResidualMm", math.inf)
            )
            layoutSpecification = str(
                dockingSummary["metrics"].get("layoutSpecification", "")
            )
            frameValid = (
                dockCount == 4
                and math.isfinite(topResidual)
                and topResidual <= 0.10
                and layoutSpecification
                == "FourIndependentOcclusalTangentDockBranches"
                and dockingSummary["metrics"].get("centralHubPresent") is False
                and int(dockingSummary["metrics"].get("radialSpokeCount", -1)) == 0
                and int(
                    dockingSummary["metrics"].get(
                        "independentDockComponentCount",
                        0,
                    )
                )
                == 4
            )
            add(
                "PASS" if frameValid else "FAIL",
                _("Four independent occlusal-plane docks"),
                _(
                    "Four independent docks, no central hub/spokes; maximum top-face plane residual %1 mm."
                ).replace(
                    "%1", f"{topResidual:.4f}"
                )
                if math.isfinite(topResidual)
                else _("Dock count, layout, or occlusal-plane metadata is invalid."),
            )
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            add("FAIL", _("Step 4C docking provenance"), str(exc))

        currentTrajectoryGeometry = []
        maxAxisErrorDeg = 0.0
        trajectoryError = ""
        try:
            storedTrajectoryGeometry = json.loads(summary["trajectoryGeometryJson"])
            if len(summary["trajectories"]) not in (1, 2):
                raise ValueError(_("The final template requires one or two trajectories."))
            for index, trajectoryNode in enumerate(summary["trajectories"]):
                trajectorySummary = self.getTrajectorySummary(trajectoryNode)
                if (
                    not trajectorySummary["isValid"]
                    or trajectorySummary["definedPointCount"] != 2
                    or not trajectoryNode.GetLocked()
                ):
                    raise ValueError(
                        _("Every final-template trajectory must remain complete and locked.")
                    )
                currentRecord = {
                    "entryRas": [float(value) for value in trajectorySummary["entryRas"]],
                    "targetRas": [float(value) for value in trajectorySummary["targetRas"]],
                }
                currentTrajectoryGeometry.append(currentRecord)
                storedRecord = storedTrajectoryGeometry[index]
                storedAxis = np.asarray(storedRecord["targetRas"], dtype=float) - np.asarray(
                    storedRecord["entryRas"], dtype=float
                )
                currentAxis = np.asarray(currentRecord["targetRas"], dtype=float) - np.asarray(
                    currentRecord["entryRas"], dtype=float
                )
                storedAxis /= float(np.linalg.norm(storedAxis))
                currentAxis /= float(np.linalg.norm(currentAxis))
                maxAxisErrorDeg = max(
                    maxAxisErrorDeg,
                    math.degrees(
                        math.acos(
                            float(np.clip(np.dot(storedAxis, currentAxis), -1.0, 1.0))
                        )
                    ),
                )
            expectedJson = json.dumps(
                currentTrajectoryGeometry,
                sort_keys=True,
                separators=(",", ":"),
            )
            if expectedJson != summary["trajectoryGeometryJson"]:
                raise ValueError(_("A source trajectory changed after final fusion."))
            if dockingSummary and summary["trajectories"] != dockingSummary["trajectories"]:
                raise ValueError(_("Final and Step 4C source trajectory sets differ."))
        except (RuntimeError, ValueError, IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
            trajectoryError = str(exc)
        add(
            "FAIL" if trajectoryError or maxAxisErrorDeg > 0.10 else "PASS",
            _("Trajectory guide-axis agreement"),
            trajectoryError
            or _("Maximum stored/current guide-axis deviation is %1°.").replace(
                "%1", f"{maxAxisErrorDeg:.4f}"
            ),
        )

        topology = surface_topology(finalModel.GetPolyData())
        add(
            "PASS" if topology["triangleCount"] > 0 else "FAIL",
            _("Non-empty printable surface"),
            _("%1 triangles.").replace("%1", str(topology["triangleCount"])),
        )
        occupiedVolumeRegions = int(
            summary["metrics"].get("occupiedVolumeRegionCount", 0)
        )
        add(
            "PASS" if occupiedVolumeRegions == 1 else "FAIL",
            _("One connected printable solid"),
            _("%1 connected occupied volume(s); %2 watertight boundary surface region(s).")
            .replace("%1", str(occupiedVolumeRegions))
            .replace("%2", str(topology["surfaceRegionCount"])),
        )
        add(
            "PASS"
            if topology["boundaryOrNonManifoldEdgeCount"] == 0
            else "FAIL",
            _("Watertight manifold topology"),
            _("%1 boundary/non-manifold edge(s).").replace(
                "%1", str(topology["boundaryOrNonManifoldEdgeCount"])
            ),
        )

        fusionMetrics = summary["metrics"]
        occupancyValid = all(
            int(fusionMetrics.get(key, 0)) > 0
            for key in (
                "occupiedSampleCount",
                "dockingSampleCount",
                "reinforcementSampleCount",
                "channelSampleCount",
            )
        )
        channelsPreserved = (
            occupancyValid
            and int(fusionMetrics.get("channelExcludedOccupiedSampleCount", 0))
            > 0
            and int(fusionMetrics.get("channelResidualOccupiedSampleCount", -1))
            == 0
        )
        add(
            "PASS" if channelsPreserved else "FAIL",
            _("Guide union and channel preservation"),
            _("Subtractive guide channels removed occupied material and contain no residual fused voxels.")
            if channelsPreserved
            else _(
                "A required fused/channel mask is empty or material remains in a protected channel."
            ),
        )

        try:
            assemblyMetrics = summary["dockingMetrics"]
            branchMetrics = assemblyMetrics.get("shellContactBranches", {})
            exclusionMetrics = assemblyMetrics.get("trajectoryGuideExclusion", {})
            boreProtection = assemblyMetrics.get("targetDocking", {}).get(
                "boreProtection", {}
            )
            separatedGeometry = (
                assemblyMetrics.get("method")
                == "SeparatedTrajectoryGuidesAndFourOcclusalDockBranchesV3"
                and int(branchMetrics.get("branchCount", 0)) == 4
                and branchMetrics.get("method")
                == "FourIndependentBoreTangentShellAttachmentsV2"
                and float(
                    branchMetrics.get("minimumBoreSurfaceClearanceMm", 0.0)
                )
                > 0.0
                and exclusionMetrics.get("docking", {}).get("method")
                == "ProtectedTrajectoryGuideEnvelopeSubtraction"
                and int(
                    exclusionMetrics.get("docking", {}).get(
                        "excludedOccupiedSampleCount",
                        -1,
                    )
                )
                == 0
                and exclusionMetrics.get("reinforcement", {}).get("method")
                == "ProtectedTrajectoryGuideEnvelopeSubtraction"
            )
            add(
                "PASS" if separatedGeometry else "FAIL",
                _("Dock attachment and trajectory-guide exclusion"),
                _(
                    "All four docks have independent shell attachments and both dock solids and attachments were clipped against the protected trajectory-guide envelope."
                )
                if separatedGeometry
                else _(
                    "Four independent shell attachments or trajectory-guide exclusion metadata is missing."
                ),
            )
            boresOpen = (
                boreProtection.get("method")
                == "ExtendedThroughDockReinforcementAndAttachmentOverlapV1"
                and int(boreProtection.get("channelCount", 0)) == 4
                and float(boreProtection.get("endOverhangMm", 0.0)) > 0.0
                and int(fusionMetrics.get("channelResidualOccupiedSampleCount", -1))
                == 0
            )
            add(
                "PASS" if boresOpen else "FAIL",
                _("Four through-open robot-dock bores"),
                _("All four bore channels extend through dock reinforcement and connector overlap, with no residual fused voxels.")
                if boresOpen
                else _("One or more robot-dock bores lacks complete through-channel protection."),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            add("FAIL", _("Dock attachment and trajectory-guide exclusion"), str(exc))

        try:
            guideParameters = json.loads(summary["parametersJson"])
            shellParameters = json.loads(shellSummary["parametersJson"]) if shellSummary else {}
            dockParameters = (
                json.loads(dockingSummary["parametersJson"])
                if dockingSummary
                else {}
            )
            spacing = float(guideParameters["processingResolutionMm"])
            shellThickness = float(shellParameters["shellThicknessMm"])
            wallValid = shellThickness > spacing
            add(
                "PASS" if wallValid else "FAIL",
                _("Non-degenerate shell wall"),
                _("Requested shell thickness %1 mm at %2 mm processing resolution.")
                .replace("%1", f"{shellThickness:.2f}")
                .replace("%2", f"{spacing:.2f}"),
            )
            minimumBore = min(
                float(guideParameters["innerDiameterMm"]),
                float(dockParameters["boreDiameterMm"]),
            )
            boreSamples = minimumBore / spacing
            add(
                "PASS" if boreSamples >= 3.0 else "WARNING",
                _("Minimum guide-hole sampling"),
                _("Smallest bore spans approximately %1 samples; verify physical dimensions after printing.").replace(
                    "%1", f"{boreSamples:.2f}"
                ),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            add("FAIL", _("Dimension metadata"), str(exc))

        add(
            "WARNING",
            _("Clinical collision and fit review"),
            _(
                "Computational topology cannot establish gingival clearance, "
                "patient fit, robot-interface strength, or safe drill access. "
                "Inspect the final model against the CBCT/segmentation and validate on a phantom."
            ),
        )
        overall = (
            "FAIL"
            if any(check["result"] == "FAIL" for check in checks)
            else "WARNING"
            if any(check["result"] == "WARNING" for check in checks)
            else "PASS"
        )
        parameterNode = self.getParameterNode()
        registry = self.syncDentoCaseTrajectoryRegistry(parameterNode)
        branch = next(
            (
                value
                for value in registry["prepared_branches"].values()
                if value.get("template_node_id") == finalModel.GetID()
            ),
            None,
        )
        if branch is None:
            raise ValueError(_("The final template has no PreparedBranch identity."))
        verification = {
            "schemaVersion": "1.0",
            "overall": overall,
            "verifiedUtc": datetime.now(timezone.utc).isoformat(),
            "finalModelUpdatedUtc": finalModel.GetAttribute("DENTOBOT.UpdatedUtc") or "",
            "preparedBranchId": branch["branch_id"],
            "preparedBranchRevision": branch["revision"],
            "planningPoseFingerprint": branch["planning_pose_fingerprint"],
            "checks": checks,
        }
        wasModifying = finalModel.StartModify()
        try:
            finalModel.SetAttribute("DENTOBOT.VerificationState", overall)
            finalModel.SetAttribute(
                "DENTOBOT.VerificationJson",
                json.dumps(verification, sort_keys=True, separators=(",", ":")),
            )
            finalModel.SetAttribute("DENTOBOT.VerifiedUtc", verification["verifiedUtc"])
        finally:
            finalModel.EndModify(wasModifying)
        registry = self.syncDentoCaseTrajectoryRegistry(parameterNode)
        if overall in {"PASS", "WARNING"}:
            registry = select_prepared_branch(registry, branch["branch_id"])
            parameterNode.step6TrajectoryRegistryJson = canonical_json(registry)
        return verification

    def exportFinalPrintableTemplateStl(
        self,
        directory: str | Path,
        finalModel: vtkMRMLModelNode,
        *,
        overwrite: bool = False,
    ) -> Path:
        verification = self.verifyFinalPrintableTemplate(finalModel)
        if verification["overall"] == "FAIL":
            raise ValueError(_("Final verification failed; STL export is blocked."))
        eligibility = self.evaluatePreparedBranchEligibility(self.getParameterNode())
        if not eligibility["eligible"]:
            raise ValueError(eligibility["message"])
        summary = self.getFinalPrintableTemplateSummary(finalModel)
        if summary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale final template before export."))
        verification = summary["verification"]
        if (
            summary["verificationState"] not in {"PASS", "WARNING"}
            or verification.get("overall") != summary["verificationState"]
            or verification.get("finalModelUpdatedUtc")
            != (finalModel.GetAttribute("DENTOBOT.UpdatedUtc") or "")
        ):
            raise ValueError(_("Run current Step 5C final verification before export."))
        topology = surface_topology(finalModel.GetPolyData())
        if (
            topology["triangleCount"] <= 0
            or topology["boundaryOrNonManifoldEdgeCount"] != 0
            or int(summary["metrics"].get("occupiedVolumeRegionCount", 0)) != 1
        ):
            raise ValueError(_("Final geometry no longer passes printable topology checks."))
        outputDirectory = Path(directory)
        if not outputDirectory.is_dir():
            raise ValueError(_("Select an existing local STL output directory."))
        outputPath = outputDirectory / "DENTO_Final_Printable_Template.stl"
        if outputPath.exists() and not overwrite:
            raise FileExistsError(
                _("STL output already exists: %1").replace("%1", outputPath.name)
            )
        writtenPath = write_stl_atomic(finalModel.GetPolyData(), outputPath)
        finalModel.SetAttribute("DENTOBOT.LastExportedStlPath", str(writtenPath))
        finalModel.SetAttribute(
            "DENTOBOT.LastExportedUtc",
            datetime.now(timezone.utc).isoformat(),
        )
        return writtenPath

    def deleteFinalPrintableTemplate(
        self,
        finalModel: vtkMRMLModelNode,
    ) -> list[dict]:
        summary = self.getFinalPrintableTemplateSummary(finalModel)
        parameterNode = self.getParameterNode()
        parameterNode.finalPrintableTemplateModel = None
        parameterNode.templateDockingAssemblyModel = None
        parameterNode.templateDockingClearanceModel = None
        parameterNode.templateDockingReinforcementModel = None
        parameterNode.templateDockingChannelsModel = None
        removals = []
        for node in [*summary["roleModels"].values(), finalModel]:
            if slicer.mrmlScene.IsNodePresent(node):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(node))
        return removals
