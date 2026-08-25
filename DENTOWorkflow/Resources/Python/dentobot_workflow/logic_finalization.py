"""Extracted research guide and finalization methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class FinalizationLogicMixin:
    def createOrResetTemplateShellRoi(
        self,
        supportModelNode: vtkMRMLModelNode,
        roiNode: vtkMRMLMarkupsROINode | None = None,
        marginMm: float = 2.0,
    ) -> vtkMRMLMarkupsROINode:
        """Create/reset locked automatic world-RAS bounds around Step 4B anatomy."""

        summary = self.getDraftTemplateSupportModelSummary(supportModelNode)
        if summary["geometryState"] != "Current":
            raise ValueError(_("Update the stale Step 4B support draft first."))
        margin = float(marginMm)
        if not math.isfinite(margin) or margin < 0.0:
            raise ValueError(_("ROI margin must be a finite non-negative value."))
        worldSurface = model_polydata_in_world(supportModelNode)
        bounds = worldSurface.GetBounds()
        if len(bounds) != 6 or any(not math.isfinite(value) for value in bounds):
            raise RuntimeError(_("The Step 4B support draft has invalid world bounds."))

        reusedRoi = bool(
            roiNode and roiNode.IsA("vtkMRMLMarkupsROINode")
        )
        previousVisibility = bool(
            reusedRoi
            and roiNode.GetDisplayNode()
            and roiNode.GetDisplayNode().GetVisibility()
        )
        if roiNode:
            if not self.isTemplateShellRoiNode(roiNode):
                raise ValueError(
                    _(
                        "Select a DENTOBOT Step 5B automatic shell bounds ROI. Target-bounds "
                        "and unrelated ROIs cannot be adopted by Step 5B."
                    )
                )
            if roiNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            ) is not supportModelNode:
                raise ValueError(
                    _(
                        "The selected Step 5B ROI belongs to a different Step "
                        "4B support draft. Delete it or select its source model."
                    )
                )
        else:
            roiNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsROINode",
                "[Step 5B] DENTO Research Template Shell ROI",
            )
        if not roiNode:
            raise RuntimeError(_("Slicer could not create the automatic shell bounds ROI."))

        center = [
            (float(bounds[2 * axis]) + float(bounds[2 * axis + 1])) / 2.0
            for axis in range(3)
        ]
        size = [
            float(bounds[2 * axis + 1] - bounds[2 * axis]) + 2.0 * margin
            for axis in range(3)
        ]
        roiNode.SetAndObserveTransformNodeID(None)
        objectToNode = vtk.vtkMatrix4x4()
        objectToNode.Identity()
        roiNode.SetAndObserveObjectToNodeMatrix(objectToNode)
        roiNode.SetLocked(True)
        roiNode.SetName("[Step 5B] DENTO Research Template Shell ROI")
        roiNode.SetCenterWorld(*center)
        roiNode.SetSizeWorld(*size)
        roiNode.SetAttribute("DENTOBOT.MarkupsRole", "TemplateShellTrimROI")
        roiNode.SetAttribute(
            "DENTOBOT.TemplateGuideSchemaVersion",
            self.TEMPLATE_GUIDE_SCHEMA_VERSION,
        )
        roiNode.SetNodeReferenceID(
            self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
            supportModelNode.GetID(),
        )
        roiNode.CreateDefaultDisplayNodes()
        displayNode = roiNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(previousVisibility if reusedRoi else True)
        self.enforceWorkflowRoiNonInteractive(roiNode)
        self.refreshWorkflowLineageColors()
        supportLineageColor = self.lineageColorFromNode(supportModelNode)
        if supportLineageColor:
            self.setNodeLineageColor(
                roiNode,
                supportLineageColor,
                supportModelNode.GetAttribute("DENTOBOT.TargetSegmentID") or "",
                supportModelNode.GetAttribute("DENTOBOT.TargetFdiNumber") or "",
            )
        elif displayNode:
            self.clearNodeLineageColor(roiNode)
            displayNode.SetColor(0.95, 0.65, 0.15)
            displayNode.SetSelectedColor(0.95, 0.65, 0.15)
        return roiNode

    @staticmethod
    def isTemplateShellRoiNode(roiNode) -> bool:
        return bool(
            roiNode
            and roiNode.IsA("vtkMRMLMarkupsROINode")
            and roiNode.GetAttribute("DENTOBOT.MarkupsRole")
            == "TemplateShellTrimROI"
            and not roiNode.GetAttribute("DENTOBOT.BoundsRole")
        )

    def validateTemplateShellRoiForDeletion(
        self,
        roiNode: vtkMRMLMarkupsROINode,
    ) -> None:
        if not self.isTemplateShellRoiNode(roiNode):
            raise ValueError(_("Select a DENTOBOT Step 5B automatic shell bounds ROI."))
        if not slicer.mrmlScene.IsNodePresent(roiNode):
            raise ValueError(_("The selected automatic shell bounds ROI is no longer in the scene."))

    def deleteTemplateShellRoi(
        self,
        roiNode: vtkMRMLMarkupsROINode,
    ) -> dict:
        """Delete only a DENTOBOT Step 5B ROI and its unshared auxiliaries."""

        self.validateTemplateShellRoiForDeletion(roiNode)
        parameterNode = self.getParameterNode()
        if parameterNode.templateShellRoi is roiNode:
            parameterNode.templateShellRoi = None
        return self._removeSceneNodeAndOwnedAuxiliaries(roiNode)

    @staticmethod
    def _templateGuideParameters(
        clearanceMm: float,
        thicknessMm: float,
        samplingSpacingMm: float,
        channelDiameterMm: float,
        sleeveOuterDiameterMm: float,
        sleeveInnerDiameterMm: float,
        sleeveHeightMm: float,
    ) -> dict[str, float]:
        values = {
            "clearanceMm": float(clearanceMm),
            "thicknessMm": float(thicknessMm),
            "samplingSpacingMm": float(samplingSpacingMm),
            "channelDiameterMm": float(channelDiameterMm),
            "sleeveOuterDiameterMm": float(sleeveOuterDiameterMm),
            "sleeveInnerDiameterMm": float(sleeveInnerDiameterMm),
            "sleeveHeightMm": float(sleeveHeightMm),
        }
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError(_("All Step 5B dimensions must be finite."))
        if values["clearanceMm"] < 0.0:
            raise ValueError(_("Shell clearance must be zero or greater."))
        for key in (
            "thicknessMm",
            "samplingSpacingMm",
            "channelDiameterMm",
            "sleeveOuterDiameterMm",
            "sleeveInnerDiameterMm",
            "sleeveHeightMm",
        ):
            if values[key] <= 0.0:
                raise ValueError(_("All non-clearance Step 5B dimensions must be positive."))
        if values["sleeveInnerDiameterMm"] >= values["sleeveOuterDiameterMm"]:
            raise ValueError(_("Sleeve inner diameter must be smaller than outer diameter."))
        if values["channelDiameterMm"] < values["sleeveInnerDiameterMm"]:
            raise ValueError(
                _("Shell channel diameter must be at least the sleeve inner diameter.")
            )
        return values

    def validateResearchTemplateInputs(
        self,
        supportModelNode: vtkMRMLModelNode,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        roiNode: vtkMRMLMarkupsROINode,
        parameters: dict[str, float],
    ) -> dict:
        supportSummary = self.getDraftTemplateSupportModelSummary(
            supportModelNode
        )
        if supportSummary["geometryState"] != "Current":
            raise ValueError(_("Update the stale Step 4B support draft first."))
        if not self.isDentobotTrajectoryNode(trajectoryNode):
            raise ValueError(_("Select a DENTOBOT Step 4A trajectory."))
        trajectorySummary = self.getTrajectorySummary(trajectoryNode)
        if not trajectorySummary["isValid"] or trajectorySummary["definedPointCount"] != 2:
            raise ValueError(_("A complete non-zero Entry/Target trajectory is required."))
        if not trajectoryNode.GetLocked():
            raise ValueError(_("Lock the trajectory before generating Step 5B geometry."))
        trajectoryAssociation = self.getTrajectoryTargetAssociation(
            trajectoryNode
        )
        if not trajectoryAssociation:
            raise ValueError(
                _("Associate the Step 4A trajectory with the Step 4B target tooth.")
            )
        trajectorySegmentation = trajectoryAssociation["segmentationNode"]
        if (
            trajectorySegmentation.GetID()
            != supportSummary["sourceSegmentation"].GetID()
            or trajectoryAssociation["targetRecord"]["segmentId"]
            != supportSummary["targetSegmentId"]
        ):
            raise ValueError(
                _(
                    "The Step 4A trajectory and Step 4B support draft must belong to "
                    "the same target tooth lineage."
                )
            )
        if not self.isTemplateShellRoiNode(roiNode):
            raise ValueError(
                _(
                    "Create the DENTOBOT Step 5B automatic shell bounds ROI. "
                    "Step 4A target bounds cannot be used for shell generation."
                )
            )
        if roiNode.GetNodeReference(
            self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
        ) is not supportModelNode:
            raise ValueError(
                _("The automatic shell bounds ROI is not associated with the current Step 4B support draft.")
            )
        self.enforceWorkflowRoiNonInteractive(roiNode)
        roiBounds = [0.0] * 6
        roiNode.GetRASBounds(roiBounds)
        if (
            any(not math.isfinite(value) for value in roiBounds)
            or any(roiBounds[2 * axis] >= roiBounds[2 * axis + 1] for axis in range(3))
        ):
            raise ValueError(_("The automatic shell bounds ROI has invalid world-RAS bounds."))
        return {
            "supportSummary": supportSummary,
            "trajectorySummary": trajectorySummary,
            "roiBoundsRas": tuple(float(value) for value in roiBounds),
            "parameters": parameters,
        }

    @staticmethod
    def _createOrReuseRoleModel(
        modelNode: vtkMRMLModelNode | None,
        role: str,
        name: str,
    ) -> vtkMRMLModelNode:
        if modelNode:
            if (
                not modelNode.IsA("vtkMRMLModelNode")
                or modelNode.GetAttribute("DENTOBOT.ModelRole") != role
            ):
                raise ValueError(_("A selected Step 5B output has the wrong role."))
        else:
            modelNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                name,
            )
        if not modelNode:
            raise RuntimeError(_("Slicer could not create a Step 5B model."))
        modelNode.SetName(name)
        return modelNode

    def createOrUpdateResearchTemplate(
        self,
        supportModelNode: vtkMRMLModelNode,
        trajectoryNode: vtkMRMLMarkupsLineNode,
        roiNode: vtkMRMLMarkupsROINode,
        *,
        clearanceMm: float,
        thicknessMm: float,
        samplingSpacingMm: float,
        channelDiameterMm: float,
        sleeveOuterDiameterMm: float,
        sleeveInnerDiameterMm: float,
        sleeveHeightMm: float,
        shellModelNode: vtkMRMLModelNode | None = None,
        sleeveModelNode: vtkMRMLModelNode | None = None,
    ) -> tuple[vtkMRMLModelNode, vtkMRMLModelNode, dict]:
        """Generate persistent research shell/sleeve models without trained models."""

        parameters = self._templateGuideParameters(
            clearanceMm,
            thicknessMm,
            samplingSpacingMm,
            channelDiameterMm,
            sleeveOuterDiameterMm,
            sleeveInnerDiameterMm,
            sleeveHeightMm,
        )
        inputs = self.validateResearchTemplateInputs(
            supportModelNode,
            trajectoryNode,
            roiNode,
            parameters,
        )
        trajectoryPoints = (
            inputs["trajectorySummary"]["entryRas"],
            inputs["trajectorySummary"]["targetRas"],
        )
        anatomyWorld = model_polydata_in_world(supportModelNode)
        shellPolyData, shellMetrics = create_research_shell(
            anatomyWorld,
            inputs["roiBoundsRas"],
            trajectoryPoints[0],
            trajectoryPoints[1],
            clearance_mm=parameters["clearanceMm"],
            thickness_mm=parameters["thicknessMm"],
            sampling_spacing_mm=parameters["samplingSpacingMm"],
            channel_diameter_mm=parameters["channelDiameterMm"],
            sleeve_outer_diameter_mm=parameters["sleeveOuterDiameterMm"],
            sleeve_inner_diameter_mm=parameters["sleeveInnerDiameterMm"],
            sleeve_height_mm=parameters["sleeveHeightMm"],
        )
        sleevePolyData, sleeveMetrics = create_hollow_sleeve(
            trajectoryPoints[0],
            trajectoryPoints[1],
            outer_diameter_mm=parameters["sleeveOuterDiameterMm"],
            inner_diameter_mm=parameters["sleeveInnerDiameterMm"],
            height_mm=parameters["sleeveHeightMm"],
        )

        implicitDistance = vtk.vtkImplicitPolyDataDistance()
        implicitDistance.SetInput(anatomyWorld)
        sleeveDistances = [
            float(implicitDistance.EvaluateFunction(sleevePolyData.GetPoint(index)))
            for index in range(sleevePolyData.GetNumberOfPoints())
        ]
        minimumSleeveDistance = min(sleeveDistances) if sleeveDistances else math.nan
        warnings = []
        if minimumSleeveDistance < -parameters["samplingSpacingMm"]:
            warnings.append(
                _(
                    "The sleeve surface overlaps the support anatomy; move the "
                    "Entry point to the external tooth surface before fabrication research."
                )
            )
        if shellMetrics["surfaceRegionCount"] > 2:
            warnings.append(
                _(
                    "The shell contains multiple surface regions; verify that selected "
                    "supports form one connected removable guide body."
                )
            )

        reusedShell = bool(
            shellModelNode and shellModelNode.IsA("vtkMRMLModelNode")
        )
        reusedSleeve = bool(
            sleeveModelNode and sleeveModelNode.IsA("vtkMRMLModelNode")
        )
        shellVisibility = bool(
            reusedShell
            and shellModelNode.GetDisplayNode()
            and shellModelNode.GetDisplayNode().GetVisibility()
        )
        sleeveVisibility = bool(
            reusedSleeve
            and sleeveModelNode.GetDisplayNode()
            and sleeveModelNode.GetDisplayNode().GetVisibility()
        )
        shellModelNode = self._createOrReuseRoleModel(
            shellModelNode,
            "ResearchTemplateShell",
            "[Step 5B] DENTO Research Template Shell",
        )
        sleeveModelNode = self._createOrReuseRoleModel(
            sleeveModelNode,
            "ResearchTemplateSleeve",
            "[Step 5B] DENTO Research Template Sleeve",
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        parametersJson = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        warningsJson = json.dumps(warnings, separators=(",", ":"))
        trajectoryGeometryJson = json.dumps(
            {
                "entryRas": trajectoryPoints[0],
                "targetRas": trajectoryPoints[1],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        roiBoundsJson = json.dumps(
            inputs["roiBoundsRas"],
            separators=(",", ":"),
        )
        for modelNode, role, polyData, metrics in (
            (shellModelNode, "ResearchTemplateShell", shellPolyData, shellMetrics),
            (sleeveModelNode, "ResearchTemplateSleeve", sleevePolyData, sleeveMetrics),
        ):
            wasModifying = modelNode.StartModify()
            try:
                modelNode.SetAndObservePolyData(polyData)
                modelNode.SetAndObserveTransformNodeID(None)
                modelNode.SetAttribute("DENTOBOT.ModelRole", role)
                modelNode.SetAttribute(
                    "DENTOBOT.TemplateGuideSchemaVersion",
                    self.TEMPLATE_GUIDE_SCHEMA_VERSION,
                )
                modelNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
                modelNode.SetAttribute("DENTOBOT.GeometryState", "Current")
                modelNode.SetAttribute("DENTOBOT.StaleReason", None)
                modelNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
                modelNode.SetAttribute("DENTOBOT.ParametersJson", parametersJson)
                modelNode.SetAttribute(
                    "DENTOBOT.TrajectoryGeometryJson",
                    trajectoryGeometryJson,
                )
                modelNode.SetAttribute("DENTOBOT.RoiBoundsRasJson", roiBoundsJson)
                modelNode.SetAttribute(
                    "DENTOBOT.SourceModelUpdatedUtc",
                    supportModelNode.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                )
                modelNode.SetAttribute(
                    "DENTOBOT.GeometryMetricsJson",
                    json.dumps(metrics, sort_keys=True, separators=(",", ":")),
                )
                modelNode.SetAttribute("DENTOBOT.ValidationWarningsJson", warningsJson)
                modelNode.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE,
                    supportModelNode.GetID(),
                )
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_GUIDE_TRAJECTORY_REFERENCE_ROLE,
                    trajectoryNode.GetID(),
                )
                modelNode.SetNodeReferenceID(
                    self.TEMPLATE_GUIDE_ROI_REFERENCE_ROLE,
                    roiNode.GetID(),
                )
            finally:
                modelNode.EndModify(wasModifying)
            modelNode.CreateDefaultDisplayNodes()

        self.refreshWorkflowLineageColors()
        lineageColor = (
            self.lineageColorFromNode(supportModelNode)
            or self.lineageColorFromNode(trajectoryNode)
        )
        lineageSegmentId = (
            supportModelNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
        )
        lineageFdiNumber = (
            supportModelNode.GetAttribute("DENTOBOT.TargetFdiNumber") or ""
        )
        if lineageColor:
            for node in (
                supportModelNode,
                trajectoryNode,
                roiNode,
                shellModelNode,
                sleeveModelNode,
            ):
                self.setNodeLineageColor(
                    node,
                    lineageColor,
                    lineageSegmentId,
                    lineageFdiNumber,
                )

        shellDisplay = shellModelNode.GetDisplayNode()
        if shellDisplay:
            shellDisplay.SetVisibility(shellVisibility if reusedShell else True)
            if not lineageColor:
                shellDisplay.SetColor(0.20, 0.75, 0.85)
            shellDisplay.SetOpacity(0.72)
        sleeveDisplay = sleeveModelNode.GetDisplayNode()
        if sleeveDisplay:
            sleeveDisplay.SetVisibility(sleeveVisibility if reusedSleeve else True)
            if not lineageColor:
                sleeveDisplay.SetColor(0.80, 0.35, 0.85)
            sleeveDisplay.SetOpacity(0.90)
        return shellModelNode, sleeveModelNode, {
            "parameters": parameters,
            "shell": shellMetrics,
            "sleeve": sleeveMetrics,
            "minimumSleeveToAnatomyDistanceMm": minimumSleeveDistance,
            "warnings": warnings,
        }

    def validateTemplateFinalizationSourceShell(
        self,
        sourceShell: vtkMRMLModelNode,
    ) -> vtkMRMLModelNode:
        summary = self.getResearchTemplateModelSummary(
            sourceShell,
            "ResearchTemplateShell",
        )
        if summary["geometryState"] != "Current":
            raise ValueError(_("Regenerate the stale Step 5B shell before finalization."))
        return sourceShell

    @staticmethod
    def isTemplateTrimPlaneNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsPlaneNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == "TemplateFinalizationPlane"
        )

    @staticmethod
    def isTemplateTrimCurveNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsClosedCurveNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == "TemplateFinalizationCurve"
        )

    @staticmethod
    def isFinalizedTemplateShellModelNode(node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == "FinalizedTemplateShell"
        )

    @classmethod
    def templateTrimPlaneConstraintGeometry(
        cls,
        roiNode: vtkMRMLMarkupsROINode,
        originWorld,
    ) -> dict:
        """Project a plane origin onto the locked ROI Z axis."""

        if not cls.isTemplateShellRoiNode(roiNode):
            raise ValueError(_("Create the locked automatic Step 5B ROI first."))
        centerValues = [0.0, 0.0, 0.0]
        zAxisValues = [0.0, 0.0, 0.0]
        roiNode.GetCenterWorld(centerValues)
        roiNode.GetZAxisWorld(zAxisValues)
        center = np.asarray(centerValues, dtype=float)
        zAxis = np.asarray(zAxisValues, dtype=float)
        origin = np.asarray(originWorld, dtype=float)
        zLength = float(np.linalg.norm(zAxis))
        if (
            origin.shape != (3,)
            or not np.all(np.isfinite(origin))
            or not np.all(np.isfinite(center))
            or not np.all(np.isfinite(zAxis))
            or not math.isfinite(zLength)
            or zLength <= 1e-8
        ):
            raise ValueError(_("The Step 5C plane or Step 5B ROI frame is invalid."))
        zAxis /= zLength
        heightMm = float(np.dot(origin - center, zAxis))
        constrainedOrigin = center + heightMm * zAxis
        return {
            "center": tuple(float(value) for value in center),
            "zAxis": tuple(float(value) for value in zAxis),
            "heightMm": heightMm,
            "origin": tuple(float(value) for value in constrainedOrigin),
        }

    @classmethod
    def constrainTemplateTrimPlaneToRoi(
        cls,
        planeNode: vtkMRMLMarkupsPlaneNode,
        roiNode: vtkMRMLMarkupsROINode,
    ) -> dict:
        """Make a Step 5C plane an ROI-face-parallel, Z-height-only control."""

        if not cls.isTemplateTrimPlaneNode(planeNode):
            raise ValueError(_("Select a DENTOBOT Step 5C horizontal trim plane."))
        geometry = cls.templateTrimPlaneConstraintGeometry(
            roiNode,
            planeNode.GetOriginWorld(),
        )
        changed = False
        wasModifying = planeNode.StartModify()
        try:
            if planeNode.GetPlaneType() != planeNode.PlaneTypePointNormal:
                planeNode.SetPlaneType(planeNode.PlaneTypePointNormal)
                changed = True
            if (
                hasattr(planeNode, "GetNormalPointRequired")
                and planeNode.GetNormalPointRequired()
            ):
                planeNode.SetNormalPointRequired(False)
                changed = True
            if not np.allclose(
                np.asarray(planeNode.GetOriginWorld(), dtype=float),
                np.asarray(geometry["origin"], dtype=float),
                atol=1e-8,
            ):
                planeNode.SetOriginWorld(geometry["origin"])
                changed = True
            if not np.allclose(
                np.asarray(planeNode.GetNormalWorld(), dtype=float),
                np.asarray(geometry["zAxis"], dtype=float),
                atol=1e-8,
            ):
                planeNode.SetNormalWorld(geometry["zAxis"])
                changed = True
            if planeNode.GetLocked():
                planeNode.SetLocked(False)
                changed = True
            if not planeNode.GetSelectable():
                planeNode.SetSelectable(True)
                changed = True
            if (
                planeNode.GetAttribute(
                    "DENTOBOT.TemplateFinalizationPlaneConstraint"
                )
                != "RoiZHeightOnly"
            ):
                planeNode.SetAttribute(
                    "DENTOBOT.TemplateFinalizationPlaneConstraint",
                    "RoiZHeightOnly",
                )
                changed = True
            if planeNode.GetNodeReference(
                cls.TEMPLATE_FINALIZATION_ROI_REFERENCE_ROLE
            ) is not roiNode:
                planeNode.SetNodeReferenceID(
                    cls.TEMPLATE_FINALIZATION_ROI_REFERENCE_ROLE,
                    roiNode.GetID(),
                )
                changed = True
        finally:
            planeNode.EndModify(wasModifying)
        planeNode.CreateDefaultDisplayNodes()
        displayNode = planeNode.GetDisplayNode()
        if displayNode:
            for getterName, setterName in (
                ("GetHandlesInteractive", "SetHandlesInteractive"),
                (
                    "GetTranslationHandleVisibility",
                    "SetTranslationHandleVisibility",
                ),
                ("GetRotationHandleVisibility", "SetRotationHandleVisibility"),
                ("GetScaleHandleVisibility", "SetScaleHandleVisibility"),
                ("GetPointLabelsVisibility", "SetPointLabelsVisibility"),
                ("GetPropertiesLabelVisibility", "SetPropertiesLabelVisibility"),
            ):
                getter = getattr(displayNode, getterName, None)
                setter = getattr(displayNode, setterName, None)
                if getter and setter and getter():
                    setter(False)
                    changed = True
        geometry["changed"] = changed
        return geometry

    def createOrResetTemplateTrimPlane(
        self,
        sourceShell: vtkMRMLModelNode,
        planeNode: vtkMRMLMarkupsPlaneNode | None = None,
    ) -> vtkMRMLMarkupsPlaneNode:
        sourceShell = self.validateTemplateFinalizationSourceShell(sourceShell)
        if planeNode:
            if not self.isTemplateTrimPlaneNode(planeNode):
                raise ValueError(_("Select a DENTOBOT Step 5C horizontal trim plane."))
            associatedSource = planeNode.GetNodeReference(
                self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
            )
            if associatedSource is not sourceShell:
                raise ValueError(
                    _("The selected trim plane belongs to a different Step 5B shell.")
                )
        else:
            planeNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsPlaneNode",
                "[Step 5C] DENTO Horizontal Shell Trim Plane",
            )
        if not planeNode:
            raise RuntimeError(_("Slicer could not create the Step 5C trim plane."))

        bounds = [0.0] * 6
        sourceShell.GetRASBounds(bounds)
        center = tuple(
            (bounds[2 * axis] + bounds[2 * axis + 1]) / 2.0
            for axis in range(3)
        )
        planeNode.SetName("[Step 5C] DENTO Horizontal Shell Trim Plane")
        planeNode.SetPlaneType(planeNode.PlaneTypePointNormal)
        if hasattr(planeNode, "SetNormalPointRequired"):
            planeNode.SetNormalPointRequired(False)
        planeNode.SetOriginWorld(center)
        planeNode.SetNormalWorld((0.0, 0.0, 1.0))
        planeNode.SetSize(
            max((bounds[1] - bounds[0]) * 1.25, 1.0),
            max((bounds[3] - bounds[2]) * 1.25, 1.0),
        )
        planeNode.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TemplateFinalizationPlane",
        )
        planeNode.SetAttribute(
            "DENTOBOT.TemplateFinalizationSchemaVersion",
            self.TEMPLATE_FINALIZATION_SCHEMA_VERSION,
        )
        planeNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
        planeNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        planeNode.SetNodeReferenceID(
            self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE,
            sourceShell.GetID(),
        )
        planeNode.CreateDefaultDisplayNodes()
        displayNode = planeNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetHandlesInteractive(False)
            displayNode.SetTranslationHandleVisibility(False)
            displayNode.SetRotationHandleVisibility(False)
            displayNode.SetScaleHandleVisibility(False)
            displayNode.SetPointLabelsVisibility(False)
            displayNode.SetPropertiesLabelVisibility(False)
        sourceSummary = self.getResearchTemplateModelSummary(
            sourceShell,
            "ResearchTemplateShell",
        )
        roiNode = sourceSummary["roi"]
        if self.isTemplateShellRoiNode(roiNode):
            self.constrainTemplateTrimPlaneToRoi(planeNode, roiNode)
        lineageColor = self.lineageColorFromNode(sourceShell)
        if lineageColor:
            self.setNodeLineageColor(
                planeNode,
                lineageColor,
                sourceShell.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                sourceShell.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
            )
        return planeNode

    def createTemplateTrimCurve(
        self,
        sourceShell: vtkMRMLModelNode,
    ) -> vtkMRMLMarkupsClosedCurveNode:
        sourceShell = self.validateTemplateFinalizationSourceShell(sourceShell)
        curveNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsClosedCurveNode",
            "[Step 5C] DENTO Closed Shell Margin Curve",
        )
        if not curveNode:
            raise RuntimeError(_("Slicer could not create the Step 5C margin curve."))
        curveNode.SetAttribute(
            "DENTOBOT.MarkupsRole",
            "TemplateFinalizationCurve",
        )
        curveNode.SetAttribute(
            "DENTOBOT.TemplateFinalizationSchemaVersion",
            self.TEMPLATE_FINALIZATION_SCHEMA_VERSION,
        )
        curveNode.SetAttribute("DENTOBOT.Status", "ResearchOnly")
        curveNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        curveNode.SetNodeReferenceID(
            self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE,
            sourceShell.GetID(),
        )
        # Dynamic Modeler's Curve Cut maps this smooth closed path to the mesh.
        # Control points snap to the visible shell; using the shortest-distance
        # curve type itself can leave non-manifold seams on otherwise closed meshes.
        curveNode.SetCurveTypeToCardinalSpline()
        curveNode.CreateDefaultDisplayNodes()
        displayNode = curveNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetPointLabelsVisibility(False)
            displayNode.SetPropertiesLabelVisibility(False)
            displayNode.SetSnapMode(displayNode.SnapModeToVisibleSurface)
            displayNode.SetGlyphScale(1.2)
        lineageColor = self.lineageColorFromNode(sourceShell)
        if lineageColor:
            self.setNodeLineageColor(
                curveNode,
                lineageColor,
                sourceShell.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                sourceShell.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
            )
        return curveNode

    def validateTemplateFinalizationEditNode(
        self,
        sourceShell: vtkMRMLModelNode,
        editNode,
        mode: str,
        *,
        requireComplete: bool = True,
    ):
        self.validateTemplateFinalizationSourceShell(sourceShell)
        sourceSummary = self.getResearchTemplateModelSummary(
            sourceShell,
            "ResearchTemplateShell",
        )
        if mode not in {"PlaneCut", "CurveCut"}:
            raise ValueError(_("Select a supported Step 5C trim method."))
        if mode == "PlaneCut":
            if not self.isTemplateTrimPlaneNode(editNode):
                raise ValueError(_("Create the DENTOBOT Step 5C horizontal trim plane."))
            if requireComplete and editNode.GetNumberOfDefinedControlPoints() < 1:
                raise ValueError(_("The horizontal trim plane has no defined origin."))
            roiNode = sourceSummary["roi"]
            if self.isTemplateShellRoiNode(roiNode):
                if editNode.GetNodeReference(
                    self.TEMPLATE_FINALIZATION_ROI_REFERENCE_ROLE
                ) is not roiNode:
                    raise ValueError(
                        _("The horizontal trim plane is not linked to the current Step 5B ROI.")
                    )
                constraint = self.templateTrimPlaneConstraintGeometry(
                    roiNode,
                    editNode.GetOriginWorld(),
                )
                normal = np.asarray(editNode.GetNormalWorld(), dtype=float)
                expectedNormal = np.asarray(constraint["zAxis"], dtype=float)
                if (
                    normal.shape != (3,)
                    or not np.all(np.isfinite(normal))
                    or not np.allclose(normal, expectedNormal, atol=1e-6)
                ):
                    raise ValueError(
                        _("The horizontal trim plane must remain parallel to the Step 5B ROI faces.")
                    )
                if not np.allclose(
                    np.asarray(editNode.GetOriginWorld(), dtype=float),
                    np.asarray(constraint["origin"], dtype=float),
                    atol=1e-6,
                ):
                    raise ValueError(
                        _("The horizontal trim plane origin must remain on the Step 5B ROI Z axis.")
                    )
        else:
            if not self.isTemplateTrimCurveNode(editNode):
                raise ValueError(_("Create the DENTOBOT Step 5C closed margin curve."))
            if requireComplete and editNode.GetNumberOfDefinedControlPoints() < 3:
                raise ValueError(
                    _("Place at least three points to define the closed margin curve.")
                )
            if (
                requireComplete
                and (
                    not editNode.GetCurvePointsWorld()
                    or editNode.GetCurvePointsWorld().GetNumberOfPoints() < 3
                )
            ):
                raise ValueError(_("The closed margin curve does not form a usable path."))
        if editNode.GetNodeReference(
            self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
        ) is not sourceShell:
            raise ValueError(
                _("The Step 5C trim control belongs to a different raw shell.")
            )
        return editNode

    def templateFinalizationEditGeometryJson(self, editNode, mode: str) -> str:
        if mode == "PlaneCut":
            origin = editNode.GetOriginWorld()
            normal = editNode.GetNormalWorld()
            payload = {
                "normalRas": [float(value) for value in normal],
                "originRas": [float(value) for value in origin],
            }
        elif mode == "CurveCut":
            points = []
            for index in range(editNode.GetNumberOfDefinedControlPoints()):
                position = [0.0, 0.0, 0.0]
                editNode.GetNthControlPointPositionWorld(index, position)
                points.append([float(value) for value in position])
            payload = {
                "closed": bool(editNode.GetCurveClosed()),
                "controlPointsRas": points,
                "curveType": editNode.GetCurveTypeAsString(editNode.GetCurveType()),
            }
        else:
            raise ValueError(_("Select a supported Step 5C trim method."))
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _preparedFinalizationPolyData(polyData, capOpenBoundaries: bool) -> vtk.vtkPolyData:
        if not polyData or not polyData.GetNumberOfPoints() or not polyData.GetNumberOfCells():
            raise ValueError(_("The selected Dynamic Modeler cut region is empty."))
        previousPort = None
        if capOpenBoundaries:
            bounds = polyData.GetBounds()
            diagonal = math.sqrt(
                sum((bounds[2 * axis + 1] - bounds[2 * axis]) ** 2 for axis in range(3))
            )
            fillHoles = vtk.vtkFillHolesFilter()
            fillHoles.SetInputData(polyData)
            fillHoles.SetHoleSize(max(diagonal * 2.0, 1.0))
            previousPort = fillHoles.GetOutputPort()
        triangleFilter = vtk.vtkTriangleFilter()
        if previousPort:
            triangleFilter.SetInputConnection(previousPort)
        else:
            triangleFilter.SetInputData(polyData)
        cleanFilter = vtk.vtkCleanPolyData()
        cleanFilter.SetInputConnection(triangleFilter.GetOutputPort())
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputConnection(cleanFilter.GetOutputPort())
        normals.ConsistencyOn()
        normals.AutoOrientNormalsOn()
        normals.SplittingOff()
        normals.Update()
        output = vtk.vtkPolyData()
        output.DeepCopy(normals.GetOutput())
        return output

    @staticmethod
    def _finalizationDynamicOutputRoles() -> tuple[str, ...]:
        return (
            "PlaneCut.OutputNegativeModel",
            "PlaneCut.OutputPositiveModel",
            "CurveCut.OutputInside",
            "CurveCut.OutputOutside",
        )

    def _removeTemplateFinalizationProcessingNodes(
        self,
        finalShell: vtkMRMLModelNode,
    ) -> list[dict]:
        removals = []
        dynamicNode = finalShell.GetNodeReference(
            self.TEMPLATE_FINALIZATION_DYNAMIC_MODELER_REFERENCE_ROLE
        )
        if not dynamicNode:
            return removals
        outputNodes = []
        for role in self._finalizationDynamicOutputRoles():
            outputNode = dynamicNode.GetNodeReference(role)
            if outputNode and outputNode not in outputNodes:
                outputNodes.append(outputNode)
        finalShell.SetNodeReferenceID(
            self.TEMPLATE_FINALIZATION_DYNAMIC_MODELER_REFERENCE_ROLE,
            None,
        )
        if slicer.mrmlScene.IsNodePresent(dynamicNode):
            dynamicNode.SetContinuousUpdate(False)
            dynamicNodeId = dynamicNode.GetID()
            slicer.mrmlScene.RemoveNode(dynamicNode)
            removals.append(
                {"nodeId": dynamicNodeId, "nodeName": dynamicNode.GetName() or "", "auxiliaryNodeIds": []}
            )
        for outputNode in outputNodes:
            if (
                slicer.mrmlScene.IsNodePresent(outputNode)
                and outputNode.GetAttribute("DENTOBOT.ModelRole")
                == "TemplateFinalizationCutAuxiliary"
                and outputNode.GetAttribute("DENTOBOT.AuxiliaryOwnerNodeID")
                == finalShell.GetID()
            ):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(outputNode))
        return removals

    def createOrUpdateFinalizedTemplateShell(
        self,
        sourceShell: vtkMRMLModelNode,
        planeNode: vtkMRMLMarkupsPlaneNode | None,
        curveNode: vtkMRMLMarkupsClosedCurveNode | None,
        mode: str,
        keepRegion: str,
        finalShell: vtkMRMLModelNode | None = None,
    ) -> tuple[vtkMRMLModelNode, dict]:
        sourceShell = self.validateTemplateFinalizationSourceShell(sourceShell)
        editNode = planeNode if mode == "PlaneCut" else curveNode
        self.validateTemplateFinalizationEditNode(sourceShell, editNode, mode)
        allowedRegions = (
            {"Negative", "Positive"}
            if mode == "PlaneCut"
            else {"Inside", "Outside"}
        )
        if keepRegion not in allowedRegions:
            raise ValueError(_("Select which Step 5C cut region to keep."))
        if not getattr(slicer.modules, "dynamicmodeler", None):
            raise RuntimeError(_("Slicer's Dynamic Modeler module is unavailable."))

        createdFinalShell = finalShell is None
        if finalShell and not self.isFinalizedTemplateShellModelNode(finalShell):
            raise ValueError(_("Select the DENTOBOT Step 5C finalized shell."))
        if not finalShell:
            finalShell = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 5C] DENTO Finalized Research Template Shell",
            )
        if not finalShell:
            raise RuntimeError(_("Slicer could not create the Step 5C finalized shell."))
        if not createdFinalShell:
            self._removeTemplateFinalizationProcessingNodes(finalShell)

        dynamicNode = None
        outputNodes = []
        try:
            dynamicNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLDynamicModelerNode",
                f"[Step 5C] DENTO {mode} Dynamic Modeler",
            )
            if not dynamicNode:
                raise RuntimeError(_("Slicer could not create a Dynamic Modeler node."))
            dynamicNode.SetAttribute(
                "DENTOBOT.DynamicModelerRole",
                "TemplateFinalizationCut",
            )
            dynamicNode.SetAttribute("DENTOBOT.AuxiliaryOwnerNodeID", finalShell.GetID())
            dynamicNode.SetContinuousUpdate(False)

            if mode == "PlaneCut":
                outputRoleByRegion = {
                    "Negative": "PlaneCut.OutputNegativeModel",
                    "Positive": "PlaneCut.OutputPositiveModel",
                }
                dynamicNode.SetToolName("Plane cut")
                dynamicNode.SetNodeReferenceID("PlaneCut.InputModel", sourceShell.GetID())
                dynamicNode.SetNodeReferenceID("PlaneCut.InputPlane", editNode.GetID())
                dynamicNode.SetAttribute("CapSurface", "1")
                dynamicNode.SetAttribute("OperationType", "Union")
            else:
                outputRoleByRegion = {
                    "Inside": "CurveCut.OutputInside",
                    "Outside": "CurveCut.OutputOutside",
                }
                dynamicNode.SetToolName("Curve cut")
                dynamicNode.SetNodeReferenceID("CurveCut.InputModel", sourceShell.GetID())
                dynamicNode.SetNodeReferenceID("CurveCut.InputCurve", editNode.GetID())
                dynamicNode.SetAttribute("CurveCut.StraightCut", "1")

            for region, outputRole in outputRoleByRegion.items():
                outputNode = slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLModelNode",
                    f"[Step 5C] DENTO {mode} {region} (auxiliary)",
                )
                if not outputNode:
                    raise RuntimeError(_("Slicer could not create a cut output node."))
                outputNode.SetAttribute(
                    "DENTOBOT.ModelRole",
                    "TemplateFinalizationCutAuxiliary",
                )
                outputNode.SetAttribute("DENTOBOT.AuxiliaryOwnerNodeID", finalShell.GetID())
                outputNode.CreateDefaultDisplayNodes()
                outputNode.GetDisplayNode().SetVisibility(False)
                outputNodes.append(outputNode)
                dynamicNode.SetNodeReferenceID(outputRole, outputNode.GetID())

            slicer.modules.dynamicmodeler.logic().RunDynamicModelerTool(dynamicNode)
            keptOutput = dynamicNode.GetNodeReference(outputRoleByRegion[keepRegion])
            finalizedPolyData = self._preparedFinalizationPolyData(
                keptOutput.GetPolyData() if keptOutput else None,
                capOpenBoundaries=mode == "CurveCut",
            )
            topology = surface_topology(finalizedPolyData)
            if topology["boundaryOrNonManifoldEdgeCount"] != 0:
                raise ValueError(
                    _(
                        "The Step 5C result is not watertight after capping; "
                        "adjust the trim control before export."
                    )
                )

            timestamp = datetime.now(timezone.utc).isoformat()
            finalShell.SetName("[Step 5C] DENTO Finalized Research Template Shell")
            finalShell.SetAndObservePolyData(finalizedPolyData)
            finalShell.SetAndObserveTransformNodeID(None)
            finalShell.SetAttribute("DENTOBOT.ModelRole", "FinalizedTemplateShell")
            finalShell.SetAttribute(
                "DENTOBOT.TemplateFinalizationSchemaVersion",
                self.TEMPLATE_FINALIZATION_SCHEMA_VERSION,
            )
            finalShell.SetAttribute("DENTOBOT.Status", "ResearchOnly")
            finalShell.SetAttribute("DENTOBOT.GeometryState", "Current")
            finalShell.SetAttribute("DENTOBOT.StaleReason", None)
            finalShell.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
            finalShell.SetAttribute("DENTOBOT.FinalizationMethod", mode)
            finalShell.SetAttribute("DENTOBOT.FinalizationKeepRegion", keepRegion)
            finalShell.SetAttribute(
                "DENTOBOT.FinalizationEditGeometryJson",
                self.templateFinalizationEditGeometryJson(editNode, mode),
            )
            finalShell.SetAttribute(
                "DENTOBOT.SourceShellUpdatedUtc",
                sourceShell.GetAttribute("DENTOBOT.UpdatedUtc") or "",
            )
            finalShell.SetAttribute(
                "DENTOBOT.GeometryMetricsJson",
                json.dumps(topology, sort_keys=True, separators=(",", ":")),
            )
            finalShell.SetAttribute("DENTOBOT.UpdatedUtc", timestamp)
            finalShell.SetNodeReferenceID(
                self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE,
                sourceShell.GetID(),
            )
            finalShell.SetNodeReferenceID(
                self.TEMPLATE_FINALIZATION_EDIT_NODE_REFERENCE_ROLE,
                editNode.GetID(),
            )
            finalShell.SetNodeReferenceID(
                self.TEMPLATE_FINALIZATION_DYNAMIC_MODELER_REFERENCE_ROLE,
                dynamicNode.GetID(),
            )
            finalShell.CreateDefaultDisplayNodes()
            lineageColor = self.lineageColorFromNode(sourceShell)
            if lineageColor:
                self.setNodeLineageColor(
                    finalShell,
                    lineageColor,
                    sourceShell.GetAttribute(self.LINEAGE_TARGET_SEGMENT_ATTRIBUTE) or "",
                    sourceShell.GetAttribute(self.LINEAGE_TARGET_FDI_ATTRIBUTE) or "",
                )
            finalShell.GetDisplayNode().SetOpacity(0.82)
            finalShell.GetDisplayNode().SetVisibility(True)
            self.refreshWorkflowLineageColors()
            self.refreshWorkflowNodeStepTags()
            return finalShell, {
                "method": mode,
                "keepRegion": keepRegion,
                "topology": topology,
                "dynamicModelerNode": dynamicNode,
            }
        except Exception:
            if dynamicNode and slicer.mrmlScene.IsNodePresent(dynamicNode):
                slicer.mrmlScene.RemoveNode(dynamicNode)
            for outputNode in outputNodes:
                if slicer.mrmlScene.IsNodePresent(outputNode):
                    self._removeSceneNodeAndOwnedAuxiliaries(outputNode)
            if createdFinalShell and slicer.mrmlScene.IsNodePresent(finalShell):
                self._removeSceneNodeAndOwnedAuxiliaries(finalShell)
            elif finalShell:
                self.markFinalizedTemplateShellStale(
                    finalShell,
                    _("The latest Step 5C trim failed."),
                )
            raise

    def getFinalizedTemplateShellSummary(
        self,
        finalShell: vtkMRMLModelNode,
    ) -> dict:
        if not self.isFinalizedTemplateShellModelNode(finalShell):
            raise ValueError(_("Select the DENTOBOT Step 5C finalized shell."))
        polyData = finalShell.GetPolyData()
        if not polyData or not polyData.GetNumberOfPoints() or not polyData.GetNumberOfCells():
            raise ValueError(_("The Step 5C finalized shell contains no geometry."))
        return {
            "geometryState": finalShell.GetAttribute("DENTOBOT.GeometryState") or "Unknown",
            "staleReason": finalShell.GetAttribute("DENTOBOT.StaleReason") or "",
            "method": finalShell.GetAttribute("DENTOBOT.FinalizationMethod") or "",
            "keepRegion": finalShell.GetAttribute("DENTOBOT.FinalizationKeepRegion") or "",
            "editGeometryJson": finalShell.GetAttribute(
                "DENTOBOT.FinalizationEditGeometryJson"
            ) or "",
            "sourceShellUpdatedUtc": finalShell.GetAttribute(
                "DENTOBOT.SourceShellUpdatedUtc"
            ) or "",
            "sourceShell": finalShell.GetNodeReference(
                self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
            ),
            "editNode": finalShell.GetNodeReference(
                self.TEMPLATE_FINALIZATION_EDIT_NODE_REFERENCE_ROLE
            ),
            "dynamicModelerNode": finalShell.GetNodeReference(
                self.TEMPLATE_FINALIZATION_DYNAMIC_MODELER_REFERENCE_ROLE
            ),
            **surface_topology(polyData),
        }

    @staticmethod
    def markFinalizedTemplateShellStale(
        finalShell: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        if not DENTOWorkflowLogic.isFinalizedTemplateShellModelNode(finalShell):
            return False
        finalShell.SetAttribute("DENTOBOT.GeometryState", "Stale")
        finalShell.SetAttribute(
            "DENTOBOT.StaleReason",
            str(reason).strip() or "Step 5C inputs changed.",
        )
        return True

    def deleteTemplateFinalization(
        self,
        planeNode: vtkMRMLMarkupsPlaneNode | None,
        curveNode: vtkMRMLMarkupsClosedCurveNode | None,
        finalShell: vtkMRMLModelNode | None,
    ) -> list[dict]:
        nodes = [node for node in (planeNode, curveNode, finalShell) if node]
        if not nodes:
            raise ValueError(_("There is no DENTOBOT Step 5C edit to delete."))
        if planeNode and not self.isTemplateTrimPlaneNode(planeNode):
            raise ValueError(_("The selected plane is not owned by DENTOBOT Step 5C."))
        if curveNode and not self.isTemplateTrimCurveNode(curveNode):
            raise ValueError(_("The selected curve is not owned by DENTOBOT Step 5C."))
        if finalShell and not self.isFinalizedTemplateShellModelNode(finalShell):
            raise ValueError(_("The selected shell is not owned by DENTOBOT Step 5C."))

        parameterNode = self.getParameterNode()
        parameterNode.templateTrimPlane = None
        parameterNode.templateTrimCurve = None
        parameterNode.finalizedTemplateShellModel = None
        removals = []
        if finalShell:
            removals.extend(self._removeTemplateFinalizationProcessingNodes(finalShell))
            if slicer.mrmlScene.IsNodePresent(finalShell):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(finalShell))
        for editNode in (planeNode, curveNode):
            if editNode and slicer.mrmlScene.IsNodePresent(editNode):
                removals.append(self._removeSceneNodeAndOwnedAuxiliaries(editNode))
        return removals

    @staticmethod
    def startHorizontalPlanePlacement(planeNode: vtkMRMLMarkupsPlaneNode) -> None:
        if not DENTOWorkflowLogic.isTemplateTrimPlaneNode(planeNode):
            raise ValueError(_("Select a DENTOBOT Step 5C horizontal trim plane."))
        planeNode.RemoveAllControlPoints()
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsPlaneNode"
        )
        selectionNode.SetActivePlaceNodeID(planeNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(0)
        selectionNode.SetActivePlaceNodeClassName(
            "vtkMRMLMarkupsPlaneNode"
        )
        selectionNode.SetActivePlaceNodeID(planeNode.GetID())

    @staticmethod
    def startClosedCurvePlacement(curveNode: vtkMRMLMarkupsClosedCurveNode) -> None:
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsClosedCurveNode"
        )
        selectionNode.SetActivePlaceNodeID(curveNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(1)
        selectionNode.SetActivePlaceNodeClassName(
            "vtkMRMLMarkupsClosedCurveNode"
        )
        selectionNode.SetActivePlaceNodeID(curveNode.GetID())

    @staticmethod
    def isResearchTemplateModelNode(modelNode, role: str | None = None) -> bool:
        if not modelNode or not modelNode.IsA("vtkMRMLModelNode"):
            return False
        actualRole = modelNode.GetAttribute("DENTOBOT.ModelRole")
        validRoles = {"ResearchTemplateShell", "ResearchTemplateSleeve"}
        return actualRole == role if role else actualRole in validRoles

    def getResearchTemplateModelSummary(
        self,
        modelNode: vtkMRMLModelNode,
        expectedRole: str,
    ) -> dict:
        if not self.isResearchTemplateModelNode(modelNode, expectedRole):
            raise ValueError(_("Select the matching DENTOBOT Step 5B output model."))
        polyData = modelNode.GetPolyData()
        if not polyData or not polyData.GetNumberOfPoints() or not polyData.GetNumberOfCells():
            raise ValueError(_("A Step 5B output model contains no geometry."))
        topology = surface_topology(polyData)
        return {
            "role": expectedRole,
            "geometryState": modelNode.GetAttribute("DENTOBOT.GeometryState") or "Unknown",
            "staleReason": modelNode.GetAttribute("DENTOBOT.StaleReason") or "",
            "sourceModel": modelNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            ),
            "trajectory": modelNode.GetNodeReference(
                self.TEMPLATE_GUIDE_TRAJECTORY_REFERENCE_ROLE
            ),
            "roi": modelNode.GetNodeReference(self.TEMPLATE_GUIDE_ROI_REFERENCE_ROLE),
            "parametersJson": modelNode.GetAttribute("DENTOBOT.ParametersJson") or "{}",
            "trajectoryGeometryJson": modelNode.GetAttribute(
                "DENTOBOT.TrajectoryGeometryJson"
            ) or "{}",
            "roiBoundsRasJson": modelNode.GetAttribute(
                "DENTOBOT.RoiBoundsRasJson"
            ) or "[]",
            "sourceModelUpdatedUtc": modelNode.GetAttribute(
                "DENTOBOT.SourceModelUpdatedUtc"
            ) or "",
            "warnings": json.loads(
                modelNode.GetAttribute("DENTOBOT.ValidationWarningsJson") or "[]"
            ),
            **topology,
        }

    @staticmethod
    def markResearchTemplateModelsStale(
        shellModelNode: vtkMRMLModelNode | None,
        sleeveModelNode: vtkMRMLModelNode | None,
        reason: str,
    ) -> bool:
        changed = False
        for modelNode in (shellModelNode, sleeveModelNode):
            if not DENTOWorkflowLogic.isResearchTemplateModelNode(modelNode):
                continue
            modelNode.SetAttribute("DENTOBOT.GeometryState", "Stale")
            modelNode.SetAttribute(
                "DENTOBOT.StaleReason",
                str(reason).strip() or "Step 5B inputs changed.",
            )
            changed = True
        return changed

    def deleteResearchTemplateModels(
        self,
        shellModelNode: vtkMRMLModelNode | None,
        sleeveModelNode: vtkMRMLModelNode | None,
    ) -> list[dict]:
        nodes = [node for node in (shellModelNode, sleeveModelNode) if node]
        if not nodes:
            raise ValueError(_("There is no DENTOBOT Step 5B output to delete."))
        for node in nodes:
            if not self.isResearchTemplateModelNode(node):
                raise ValueError(_("A selected output is not owned by DENTOBOT Step 5B."))
        parameterNode = self.getParameterNode()
        if any(
            parameterNode.researchTemplateShellModel is node
            for node in nodes
        ):
            parameterNode.researchTemplateShellModel = None
        if any(
            parameterNode.researchTemplateSleeveModel is node
            for node in nodes
        ):
            parameterNode.researchTemplateSleeveModel = None
        return [self._removeSceneNodeAndOwnedAuxiliaries(node) for node in nodes]

    def exportResearchTemplateStls(
        self,
        directory: str | Path,
        shellModelNode: vtkMRMLModelNode,
        sleeveModelNode: vtkMRMLModelNode,
        *,
        overwrite: bool = False,
    ) -> dict[str, Path]:
        shellSummary = self.getFinalizedTemplateShellSummary(shellModelNode)
        sleeveSummary = self.getResearchTemplateModelSummary(
            sleeveModelNode,
            "ResearchTemplateSleeve",
        )
        if shellSummary["geometryState"] != "Current" or sleeveSummary["geometryState"] != "Current":
            raise ValueError(_("Regenerate stale Step 5B/5C outputs before STL export."))
        sourceShell = shellSummary["sourceShell"]
        sourceSummary = self.getResearchTemplateModelSummary(
            sourceShell,
            "ResearchTemplateShell",
        )
        if (
            sourceSummary["geometryState"] != "Current"
            or shellSummary["sourceShellUpdatedUtc"]
            != (sourceShell.GetAttribute("DENTOBOT.UpdatedUtc") or "")
        ):
            raise ValueError(_("Reapply Step 5C after the Step 5B source shell changes."))
        if shellSummary["boundaryOrNonManifoldEdgeCount"] != 0:
            raise ValueError(_("The Step 5C finalized shell is not watertight."))
        outputDirectory = Path(directory)
        if not outputDirectory.is_dir():
            raise ValueError(_("Select an existing local STL output directory."))
        paths = {
            "shell": outputDirectory / "DENTO_Research_Template_Shell.stl",
            "sleeve": outputDirectory / "DENTO_Research_Template_Sleeve.stl",
        }
        existing = [path.name for path in paths.values() if path.exists()]
        if existing and not overwrite:
            raise FileExistsError(
                _("STL output already exists: %1").replace("%1", ", ".join(existing))
            )
        return {
            "shell": write_stl_atomic(shellModelNode.GetPolyData(), paths["shell"]),
            "sleeve": write_stl_atomic(sleeveModelNode.GetPolyData(), paths["sleeve"]),
        }
