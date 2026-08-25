"""Extracted robot placement and simulation planning methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class RobotLogicMixin:
    @classmethod
    def isRobotBaseTransformNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLLinearTransformNode")
            and node.GetAttribute("DENTOBOT.TransformRole") == cls.ROBOT_BASE_ROLE
        )

    @classmethod
    def isRos2MotionControlActive(cls, base_transform) -> bool:
        return bool(
            base_transform
            and cls.isRobotBaseTransformNode(base_transform)
            and base_transform.GetAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE) == "true"
        )

    def ensureRobotBaseTransform(
        self,
        base_transform: vtkMRMLLinearTransformNode | None,
    ) -> vtkMRMLLinearTransformNode:
        """Create or reuse the Step 6 robot-base transform without loading STLs."""
        if base_transform is not None and not self.isRobotBaseTransformNode(
            base_transform
        ):
            raise ValueError(_("Select the DENTOBOT Step 6 robot-base transform."))
        if base_transform is not None:
            return base_transform
        existing = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode")
            if self.isRobotBaseTransformNode(node)
        ]
        if len(existing) > 1:
            raise ValueError(
                _(
                    "Multiple Step 6 robot-base transforms are present. Delete "
                    "the duplicate robot setup before continuing."
                )
            )
        if existing:
            return existing[0]
        base_transform = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode",
            "[Step 6] DENTO Robot Base Placement",
        )
        identity = vtk.vtkMatrix4x4()
        identity.Identity()
        base_transform.SetMatrixTransformToParent(identity)
        base_transform.SetName("[Step 6] DENTO Robot Base Placement")
        base_transform.SetAndObserveTransformNodeID(None)
        base_transform.SetAttribute("DENTOBOT.TransformRole", self.ROBOT_BASE_ROLE)
        base_transform.SetAttribute(
            "DENTOBOT.RobotPlacementSchemaVersion",
            self.ROBOT_PLACEMENT_SCHEMA_VERSION,
        )
        base_transform.SetAttribute("DENTOBOT.Status", "SimulationOnly")
        base_transform.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        base_transform.CreateDefaultDisplayNodes()
        base_display = base_transform.GetDisplayNode()
        if base_display:
            base_display.SetVisibility(True)
            for method_name, value in (
                ("SetEditorVisibility", True),
                ("SetHandlesInteractive", True),
                ("SetTranslationHandleVisibility", True),
                ("SetRotationHandleVisibility", True),
                ("SetScaleHandleVisibility", False),
            ):
                method = getattr(base_display, method_name, None)
                if method:
                    method(value)
        return base_transform

    @classmethod
    def isRobotMountPlaneNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsPlaneNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole") == cls.ROBOT_MOUNT_PLANE_ROLE
        )

    @classmethod
    def robotModelNodes(cls) -> list[vtkMRMLModelNode]:
        return [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
            if node.GetAttribute("DENTOBOT.ModelRole") == cls.ROBOT_LINK_MODEL_ROLE
        ]

    @classmethod
    def robotLinkTransformNodes(cls) -> list[vtkMRMLLinearTransformNode]:
        return [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode")
            if node.GetAttribute("DENTOBOT.TransformRole") == cls.ROBOT_LINK_POSE_ROLE
        ]

    @classmethod
    def robotWorkspaceModelNode(cls) -> vtkMRMLModelNode | None:
        nodes = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
            if node.GetAttribute("DENTOBOT.ModelRole")
            == cls.ROBOT_WORKSPACE_MODEL_ROLE
        ]
        if len(nodes) > 1:
            raise ValueError(_("Multiple Step 6 robot workspace clouds are present."))
        return nodes[0] if nodes else None

    @staticmethod
    def _nodeByRobotLink(nodes: list, linkName: str):
        return next(
            (
                node
                for node in nodes
                if node.GetAttribute("DENTOBOT.RobotLinkName") == linkName
            ),
            None,
        )

    def createOrUpdateRobotPlacement(
        self,
        baseTransform: vtkMRMLLinearTransformNode | None,
        jointPositionsSi: dict[str, float],
    ) -> tuple[vtkMRMLLinearTransformNode, list[vtkMRMLModelNode]]:
        """Load/reuse STL links and parent their URDF FK under one Slicer base."""

        baseTransform = self.ensureRobotBaseTransform(baseTransform)
        models = self.robotModelNodes()
        linkTransforms = self.robotLinkTransformNodes()
        self._validateSingleStep6RobotPlacement(
            baseTransform,
            models,
            linkTransforms,
        )
        baseTransform.SetName("[Step 6] DENTO Robot Base Placement")
        baseTransform.SetAndObserveTransformNodeID(None)
        baseTransform.SetAttribute("DENTOBOT.TransformRole", self.ROBOT_BASE_ROLE)
        baseTransform.SetAttribute(
            "DENTOBOT.RobotPlacementSchemaVersion",
            self.ROBOT_PLACEMENT_SCHEMA_VERSION,
        )
        baseTransform.SetAttribute("DENTOBOT.Status", "SimulationOnly")
        baseTransform.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        baseTransform.CreateDefaultDisplayNodes()
        baseDisplay = baseTransform.GetDisplayNode()
        if baseDisplay:
            baseDisplay.SetVisibility(True)
            for methodName, value in (
                ("SetEditorVisibility", True),
                ("SetHandlesInteractive", True),
                ("SetTranslationHandleVisibility", True),
                ("SetRotationHandleVisibility", True),
                ("SetScaleHandleVisibility", False),
            ):
                method = getattr(baseDisplay, methodName, None)
                if method:
                    method(value)

        urdfPath, packageRoot = self.robotDescriptionPaths()
        poses = robot_link_mesh_poses_mm(
            urdfPath,
            packageRoot,
            jointPositionsSi,
        )
        displayColors = (
            (0.72, 0.75, 0.80),
            (0.22, 0.55, 0.86),
            (0.85, 0.48, 0.18),
            (0.30, 0.70, 0.45),
            (0.65, 0.42, 0.78),
            (0.85, 0.75, 0.22),
            (0.88, 0.28, 0.28),
        )
        resolvedModels = []
        for index, pose in enumerate(poses):
            model = self._nodeByRobotLink(models, pose.link_name)
            if not model:
                model = slicer.modules.models.logic().AddModel(
                    str(pose.mesh_path),
                    slicer.vtkMRMLStorageNode.CoordinateSystemRAS,
                )
                if not model:
                    raise RuntimeError(
                        _("Slicer could not load robot mesh %1.").replace(
                            "%1", str(pose.mesh_path)
                        )
                    )
                models.append(model)
            linkTransform = self._nodeByRobotLink(linkTransforms, pose.link_name)
            if not linkTransform:
                linkTransform = slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLLinearTransformNode",
                    f"[Step 6] DENTO {pose.link_name} URDF Pose",
                )
                linkTransforms.append(linkTransform)
            linkTransform.SetName(f"[Step 6] DENTO {pose.link_name} URDF Pose")
            linkTransform.SetAttribute(
                "DENTOBOT.TransformRole",
                self.ROBOT_LINK_POSE_ROLE,
            )
            linkTransform.SetAttribute("DENTOBOT.RobotLinkName", pose.link_name)
            linkTransform.SetAttribute("DENTOBOT.Status", "SimulationOnly")
            linkTransform.SetMatrixTransformToParent(
                self._vtkFromNumpyMatrix(pose.matrix_base_from_mesh_mm)
            )
            linkTransform.SetAndObserveTransformNodeID(baseTransform.GetID())

            model.SetName(f"[Step 6] DENTO Robot {pose.link_name}")
            model.SetAttribute("DENTOBOT.ModelRole", self.ROBOT_LINK_MODEL_ROLE)
            model.SetAttribute("DENTOBOT.RobotLinkName", pose.link_name)
            model.SetAttribute("DENTOBOT.Status", "SimulationOnly")
            model.SetAttribute("DENTOBOT.SourceMeshPath", str(pose.mesh_path))
            model.SetAndObserveTransformNodeID(linkTransform.GetID())
            model.CreateDefaultDisplayNodes()
            modelDisplay = model.GetDisplayNode()
            if modelDisplay:
                modelDisplay.SetVisibility(True)
                modelDisplay.SetOpacity(1.0)
                modelDisplay.SetColor(*displayColors[index % len(displayColors)])
            resolvedModels.append(model)
        return baseTransform, resolvedModels

    def updateRobotJointPoses(self, jointPositionsSi: dict[str, float]) -> int:
        """Update link-local transforms while preserving the world base pose."""

        urdfPath, packageRoot = self.robotDescriptionPaths()
        poses = robot_link_mesh_poses_mm(urdfPath, packageRoot, jointPositionsSi)
        linkTransforms = self.robotLinkTransformNodes()
        updated = 0
        for pose in poses:
            transformNode = self._nodeByRobotLink(linkTransforms, pose.link_name)
            if not transformNode:
                continue
            transformNode.SetMatrixTransformToParent(
                self._vtkFromNumpyMatrix(pose.matrix_base_from_mesh_mm)
            )
            updated += 1
        return updated

    def createOrResetRobotMountPlane(
        self,
        planeNode: vtkMRMLMarkupsPlaneNode | None,
        baseTransform: vtkMRMLLinearTransformNode | None,
    ) -> vtkMRMLMarkupsPlaneNode:
        if planeNode and not self.isRobotMountPlaneNode(planeNode):
            raise ValueError(_("Select the DENTOBOT Step 6 robot mount plane."))
        planeNode = planeNode or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsPlaneNode",
            "[Step 6] DENTO Robot Mount Plane",
        )
        if not planeNode:
            raise RuntimeError(_("Slicer could not create the robot mount plane."))
        baseMatrix = vtk.vtkMatrix4x4()
        baseMatrix.Identity()
        if baseTransform:
            baseTransform.GetMatrixTransformToWorld(baseMatrix)
        planeNode.SetName("[Step 6] DENTO Robot Mount Plane")
        planeNode.SetPlaneType(planeNode.PlaneTypePointNormal)
        if hasattr(planeNode, "SetNormalPointRequired"):
            planeNode.SetNormalPointRequired(False)
        planeNode.SetOriginWorld(
            tuple(baseMatrix.GetElement(axis, 3) for axis in range(3))
        )
        planeNode.SetNormalWorld(
            tuple(baseMatrix.GetElement(axis, 2) for axis in range(3))
        )
        planeNode.SetSize(120.0, 120.0)
        planeNode.SetLocked(False)
        planeNode.SetSelectable(True)
        planeNode.SetAttribute("DENTOBOT.MarkupsRole", self.ROBOT_MOUNT_PLANE_ROLE)
        planeNode.SetAttribute(
            "DENTOBOT.RobotPlacementSchemaVersion",
            self.ROBOT_PLACEMENT_SCHEMA_VERSION,
        )
        planeNode.SetAttribute("DENTOBOT.Status", "SimulationOnly")
        planeNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        planeNode.CreateDefaultDisplayNodes()
        displayNode = planeNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetOpacity(0.28)
            displayNode.SetColor(0.15, 0.80, 0.95)
            displayNode.SetHandlesInteractive(True)
            displayNode.SetTranslationHandleVisibility(True)
            displayNode.SetRotationHandleVisibility(True)
            displayNode.SetScaleHandleVisibility(False)
            displayNode.SetPointLabelsVisibility(False)
            displayNode.SetPropertiesLabelVisibility(False)
        return planeNode

    @classmethod
    def step6ForeheadProxyNodes(cls) -> list[vtkMRMLModelNode]:
        return [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
            if node.GetAttribute("DENTOBOT.ModelRole") == cls.ROBOT_FOREHEAD_PROXY_ROLE
        ]

    def createOrUpdateStep6ForeheadProxy(self, parameterNode) -> vtkMRMLModelNode:
        plane = parameterNode.robotMountPlane
        if not self.isRobotMountPlaneNode(plane):
            raise ValueError(_("Create and position the mount plane before the forehead proxy."))
        existing = self.step6ForeheadProxyNodes()
        selected = parameterNode.robotForeheadProxyModel
        if selected is not None and selected not in existing:
            raise ValueError(_("The selected forehead proxy is not owned by Step 6."))
        if len(existing) > 1:
            raise ValueError(_("Multiple Step 6 forehead proxies are present; remove duplicates before continuing."))
        model = selected or (existing[0] if existing else None)
        width = float(parameterNode.step6ForeheadProxyWidthMm)
        height = float(parameterNode.step6ForeheadProxyHeightMm)
        depth = float(parameterNode.step6ForeheadProxyDepthMm)
        offset = float(parameterNode.step6ForeheadProxyOffsetMm)
        if not all(math.isfinite(value) and value > 0.0 for value in (width, height, depth)):
            raise ValueError(_("Forehead-proxy width, height, and depth must be positive."))
        if not math.isfinite(offset):
            raise ValueError(_("Forehead-proxy offset must be finite."))
        plane_matrix = vtk.vtkMatrix4x4()
        plane.GetObjectToWorldMatrix(plane_matrix)
        origin = np.asarray(
            [plane_matrix.GetElement(axis, 3) for axis in range(3)], dtype=float
        )
        x_axis = np.asarray(
            [plane_matrix.GetElement(axis, 0) for axis in range(3)], dtype=float
        )
        y_axis = np.asarray(
            [plane_matrix.GetElement(axis, 1) for axis in range(3)], dtype=float
        )
        normal = np.asarray(
            [plane_matrix.GetElement(axis, 2) for axis in range(3)], dtype=float
        )
        points = vtk.vtkPoints()
        quads = vtk.vtkCellArray()
        columns, rows = 40, 24
        point_ids = []
        for row in range(rows + 1):
            v = -1.0 + 2.0 * row / rows
            row_ids = []
            for column in range(columns + 1):
                u = -1.0 + 2.0 * column / columns
                local_x = 0.5 * width * u
                local_y = 0.5 * height * v
                # A shallow paraboloid is tangent to the mount plane at its
                # centre and curves away from it toward every boundary.
                local_z = offset - depth * (0.55 * u * u + 0.45 * v * v)
                world = origin + x_axis * local_x + y_axis * local_y + normal * local_z
                row_ids.append(points.InsertNextPoint(*map(float, world)))
            point_ids.append(row_ids)
        for row in range(rows):
            for column in range(columns):
                quad = vtk.vtkQuad()
                quad.GetPointIds().SetId(0, point_ids[row][column])
                quad.GetPointIds().SetId(1, point_ids[row][column + 1])
                quad.GetPointIds().SetId(2, point_ids[row + 1][column + 1])
                quad.GetPointIds().SetId(3, point_ids[row + 1][column])
                quads.InsertNextCell(quad)
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetPolys(quads)
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(polydata)
        normals.AutoOrientNormalsOn()
        normals.SplittingOff()
        normals.Update()
        resolved = vtk.vtkPolyData()
        resolved.DeepCopy(normals.GetOutput())
        if model is None:
            model = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode", "[Step 6] Provisional Forehead Contact Envelope"
            )
        model.SetName("[Step 6] Provisional Forehead Contact Envelope")
        model.SetAttribute("DENTOBOT.ModelRole", self.ROBOT_FOREHEAD_PROXY_ROLE)
        model.SetAttribute("DENTOBOT.RegistrationState", "Unregistered")
        model.SetAttribute("DENTOBOT.GeometryState", "Provisional")
        model.SetAttribute("DENTOBOT.IntendedUse", "VisualizationOnly")
        model.SetAttribute("DENTOBOT.ExcludedFromCollision", "true")
        model.SetAttribute("DENTOBOT.RegistrationEvidence", "false")
        model.SetAttribute("DENTOBOT.CoordinateSystem", "SlicerRASmm")
        model.SetAndObserveTransformNodeID(None)
        model.SetAndObservePolyData(resolved)
        model.CreateDefaultDisplayNodes()
        display = model.GetDisplayNode()
        if display:
            display.SetVisibility(True)
            display.SetVisibility2D(False)
            display.SetVisibility3D(True)
            display.SetColor(0.35, 0.75, 0.95)
            display.SetOpacity(float(parameterNode.step6ForeheadProxyOpacity))
            display.SetBackfaceCulling(False)
        model.SetSelectable(True)
        parameterNode.robotForeheadProxyModel = model
        self.invalidateStep6TaskConfirmation(
            parameterNode,
            _("Provisional forehead-proxy geometry changed."),
            makeBaseStale=bool(parameterNode.robotBaseMountLocked),
        )
        return model

    def step6CbctVolumeRenderingDisplayNode(self, parameterNode):
        volume = parameterNode.inputVolume
        if volume is None or not hasattr(slicer.modules, "volumerendering"):
            return None
        stored_id = str(parameterNode.step6CbctVolumeRenderingNodeId or "")
        stored = slicer.mrmlScene.GetNodeByID(stored_id) if stored_id else None
        if stored is not None:
            return stored
        logic = slicer.modules.volumerendering.logic()
        display = logic.GetFirstVolumeRenderingDisplayNode(volume)
        if display is not None:
            parameterNode.step6CbctVolumeRenderingNodeId = display.GetID()
        return display

    def applyStep6CbctRenderingPreset(
        self,
        parameterNode,
        presetName: str,
        *,
        createIfMissing: bool,
    ) -> bool:
        volume = parameterNode.inputVolume
        if volume is None:
            raise ValueError(_("Load the case CBCT before enabling 3D context."))
        if not hasattr(slicer.modules, "volumerendering"):
            raise RuntimeError(_("Slicer's Volume Rendering module is unavailable."))
        logic = slicer.modules.volumerendering.logic()
        display = self.step6CbctVolumeRenderingDisplayNode(parameterNode)
        if display is None and createIfMissing:
            display = logic.CreateDefaultVolumeRenderingNodes(volume)
            if display is None:
                raise RuntimeError(_("Slicer could not create a CBCT renderer."))
            parameterNode.step6CbctVolumeRenderingNodeId = display.GetID()
            display.SetAttribute("DENTOBOT.DisplayRole", "Step6CbctContext")
        if display is None:
            return False
        presetName = str(presetName or "current")
        if presetName == "current":
            logic.CopyScalarDisplayToVolumeRenderingDisplayNode(
                display, volume.GetDisplayNode()
            )
        elif presetName in {"CT-Bone", "uCT-Skull"}:
            preset = logic.GetPresetByName(presetName)
            if preset is None:
                raise ValueError(_("Volume-rendering preset %1 is unavailable.").replace("%1", presetName))
            property_node = display.GetVolumePropertyNode()
            if property_node is None:
                property_node = slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLVolumePropertyNode",
                    f"[Step 6] {presetName} Intensity Appearance",
                )
                display.SetAndObserveVolumePropertyNodeID(property_node.GetID())
            property_node.Copy(preset)
            property_node.SetName(f"[Step 6] {presetName} Intensity Appearance")
        else:
            raise ValueError(_("Unknown CBCT intensity-appearance preset."))
        display.SetVisibility(True)
        self._captureStep6CbctBaseOpacity(display)
        self._applyStep6CbctOpacity(display, float(parameterNode.step6CbctOpacity))
        return True

    @staticmethod
    def _captureStep6CbctBaseOpacity(display) -> None:
        property_node = display.GetVolumePropertyNode() if display else None
        volume_property = property_node.GetVolumeProperty() if property_node else None
        opacity_function = volume_property.GetScalarOpacity() if volume_property else None
        if opacity_function is None:
            return
        points = []
        for index in range(opacity_function.GetSize()):
            values = [0.0, 0.0, 0.0, 0.0]
            opacity_function.GetNodeValue(index, values)
            points.append([float(value) for value in values])
        display.SetAttribute(
            "DENTOBOT.Step6BaseScalarOpacityJson",
            json.dumps(points, separators=(",", ":")),
        )

    @staticmethod
    def _applyStep6CbctOpacity(display, opacity: float) -> None:
        if display is None:
            return
        property_node = display.GetVolumePropertyNode()
        volume_property = property_node.GetVolumeProperty() if property_node else None
        opacity_function = volume_property.GetScalarOpacity() if volume_property else None
        if opacity_function is None:
            return
        try:
            points = json.loads(
                display.GetAttribute("DENTOBOT.Step6BaseScalarOpacityJson") or "[]"
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            points = []
        if not points:
            return
        scale = max(0.0, min(1.0, float(opacity)))
        opacity_function.RemoveAllPoints()
        for point in points:
            if len(point) != 4:
                continue
            opacity_function.AddPoint(
                float(point[0]),
                float(point[1]) * scale,
                float(point[2]),
                float(point[3]),
            )
        property_node.Modified()

    def enableStep6CbctVolumeRendering(self, parameterNode, presetName: str):
        self.applyStep6CbctRenderingPreset(
            parameterNode,
            presetName,
            createIfMissing=True,
        )
        return self.step6CbctVolumeRenderingDisplayNode(parameterNode)

    def setStep6Appearance(
        self,
        parameterNode,
        key: str,
        *,
        visible: bool,
        opacity: float,
    ) -> None:
        opacity = max(0.0, min(1.0, float(opacity)))
        parameter_fields = {
            "cbct": "step6CbctOpacity",
            "masks": "step6MasksOpacity",
            "robot": "step6RobotOpacity",
            "goal_robot": "step6GoalRobotOpacity",
            "guides": "step6GuidesOpacity",
            "mount_plane": "step6MountPlaneOpacity",
            "trajectory": "step6TrajectoryOpacity",
            "forehead_proxy": "step6ForeheadProxyOpacity",
        }
        if key not in parameter_fields:
            raise ValueError(_("Unknown Step 6 appearance element."))
        setattr(parameterNode, parameter_fields[key], opacity)

        displays = []
        if key == "cbct":
            display = self.step6CbctVolumeRenderingDisplayNode(parameterNode)
            if display is not None:
                display.SetVisibility(bool(visible))
                self._applyStep6CbctOpacity(display, opacity)
                return
        elif key == "masks" and parameterNode.teethSegmentation:
            display = parameterNode.teethSegmentation.GetDisplayNode()
            if display:
                display.SetVisibility(bool(visible))
                set_opacity = getattr(display, "SetOpacity3D", None)
                if set_opacity:
                    set_opacity(opacity)
                return
        elif key == "robot":
            displays.extend(
                node.GetDisplayNode() for node in self.robotModelNodes() if node.GetDisplayNode()
            )
            ros_robot = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
            if ros_robot:
                displays.extend(
                    node.GetDisplayNode()
                    for index in range(ros_robot.GetNumberOfNodeReferences("model"))
                    for node in [ros_robot.GetNthNodeReference("model", index)]
                    if node and node.GetDisplayNode()
                )
        elif key == "goal_robot":
            ros_robot = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
            if ros_robot:
                displays.extend(
                    node.GetDisplayNode()
                    for index in range(ros_robot.GetNumberOfNodeReferences("goal_model"))
                    for node in [ros_robot.GetNthNodeReference("goal_model", index)]
                    if node and node.GetDisplayNode()
                )
        elif key == "guides":
            displays.extend(
                node.GetDisplayNode()
                for node in (
                    parameterNode.draftTemplateSupportModel,
                    parameterNode.visibleTemplateSupportModel,
                    parameterNode.targetDockingAssemblyModel,
                    parameterNode.finalPrintableTemplateModel,
                )
                if node and node.GetDisplayNode()
            )
        elif key == "mount_plane" and parameterNode.robotMountPlane:
            display = parameterNode.robotMountPlane.GetDisplayNode()
            if display:
                displays.append(display)
        elif key == "trajectory" and parameterNode.trajectoryLine:
            display = parameterNode.trajectoryLine.GetDisplayNode()
            if display:
                displays.append(display)
        elif key == "forehead_proxy" and parameterNode.robotForeheadProxyModel:
            display = parameterNode.robotForeheadProxyModel.GetDisplayNode()
            if display:
                displays.append(display)
        for display in dict.fromkeys(displays):
            display.SetVisibility(bool(visible))
            set_opacity = getattr(display, "SetOpacity", None)
            if set_opacity:
                set_opacity(opacity)

    def snapRobotBaseToPlane(
        self,
        baseTransform: vtkMRMLLinearTransformNode,
        planeNode: vtkMRMLMarkupsPlaneNode,
    ) -> np.ndarray:
        if not self.isRobotBaseTransformNode(baseTransform):
            raise ValueError(_("Load or select the DENTOBOT robot base first."))
        if not self.isRobotMountPlaneNode(planeNode):
            raise ValueError(_("Create or select the DENTOBOT mount plane first."))
        planeMatrix = vtk.vtkMatrix4x4()
        planeNode.GetObjectToWorldMatrix(planeMatrix)
        snapped = orthonormal_plane_pose(self._numpyFromVtkMatrix(planeMatrix))
        baseTransform.SetAndObserveTransformNodeID(None)
        baseTransform.SetMatrixTransformToParent(self._vtkFromNumpyMatrix(snapped))
        return snapped

    def nudgeRobotBase(
        self,
        baseTransform: vtkMRMLLinearTransformNode,
        *,
        translationLocalMm: tuple[float, float, float] = (0.0, 0.0, 0.0),
        rotationLocalDeg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> np.ndarray:
        if not self.isRobotBaseTransformNode(baseTransform):
            raise ValueError(_("Load or select the DENTOBOT robot base first."))
        currentVtk = vtk.vtkMatrix4x4()
        baseTransform.GetMatrixTransformToWorld(currentVtk)
        nudged = local_nudge_matrix(
            self._numpyFromVtkMatrix(currentVtk),
            translation_local_mm=translationLocalMm,
            rotation_local_deg=rotationLocalDeg,
        )
        baseTransform.SetAndObserveTransformNodeID(None)
        baseTransform.SetMatrixTransformToParent(self._vtkFromNumpyMatrix(nudged))
        return nudged

    def buildPlanningContextNodeMap(self, parameterNode) -> dict[str, str]:
        def node_id(node) -> str:
            return node.GetID() if node else ""

        return {
            "inputVolume": node_id(parameterNode.inputVolume),
            "teethSegmentation": node_id(parameterNode.teethSegmentation),
            "trajectoryLine": node_id(parameterNode.trajectoryLine),
            "targetDockingAssemblyModel": node_id(
                parameterNode.targetDockingAssemblyModel
            ),
            "finalPrintableTemplateModel": node_id(
                parameterNode.finalPrintableTemplateModel
            ),
            "draftTemplateSupportModel": node_id(
                parameterNode.draftTemplateSupportModel
            ),
            "visibleTemplateSupportModel": node_id(
                parameterNode.visibleTemplateSupportModel
            ),
            "targetToothBoundsRoi": node_id(parameterNode.targetToothBoundsRoi),
        }

    def step6CaseViewNodes(self, parameterNode) -> list:
        """Return MRML nodes that make up the imported Step 6 case scene."""
        nodes = []
        for role in CASE_VIEW_ROLES:
            node = getattr(parameterNode, role, None)
            if node is not None:
                nodes.append(node)
        return nodes

    @staticmethod
    def _nodeRasBounds(node) -> list[float] | None:
        if node is None:
            return None
        getter = getattr(node, "GetRASBounds", None)
        if getter is None:
            return None
        bounds = [0.0] * 6
        getter(bounds)
        if not np.all(np.isfinite(bounds)):
            return None
        return bounds

    def step6CaseViewRasBounds(self, parameterNode) -> tuple[float, ...] | None:
        """Combined world-RAS bounds of the imported case package."""
        bounds_list = [
            bounds
            for node in self.step6CaseViewNodes(parameterNode)
            if (bounds := self._nodeRasBounds(node)) is not None
        ]
        return self.combinedRasBounds(bounds_list)

    @staticmethod
    def _subsample_polydata_points(
        polydata: vtk.vtkPolyData,
        *,
        stride: int = 50,
    ) -> list[tuple[float, float, float]]:
        if polydata is None or polydata.GetNumberOfPoints() <= 0:
            return []
        step = max(int(stride), 1)
        points = polydata.GetPoints()
        sampled: list[tuple[float, float, float]] = []
        for index in range(0, polydata.GetNumberOfPoints(), step):
            sampled.append(tuple(points.GetPoint(index)))
        return sampled

    def step6SegmentationAnatomyPointsMm(
        self,
        segmentationNode,
        *,
        stride: int = 80,
    ) -> list[tuple[float, float, float]]:
        """Return subsampled closed-surface points for all tooth segments."""
        if not segmentationNode:
            return []
        samples: list[tuple[float, float, float]] = []
        for record in self.getTargetToothRecords(segmentationNode):
            segment_id = record.get("segmentId")
            if not segment_id:
                continue
            try:
                surface = self._getClosedSurfaceCopy(segmentationNode, segment_id)
            except (RuntimeError, ValueError):
                continue
            if surface is None or surface.GetNumberOfPoints() <= 0:
                continue
            samples.extend(
                self._subsample_polydata_points(surface, stride=stride),
            )
        return samples

    def step6EnvironmentObstaclePointsMm(self, parameterNode) -> np.ndarray:
        """Return a coarse obstacle point cloud for Step 6 environment screening."""
        samples: list[tuple[float, float, float]] = []
        if parameterNode.teethSegmentation:
            segmentation = parameterNode.teethSegmentation
            jawGroups = self.step6CaseJawSegmentIds(segmentation)
            fixedSurface = self._segmentationSegmentsSurfaceWorld(
                segmentation,
                set(jawGroups["upper"]),
            )
            movingSurface = self._segmentationSegmentsSurfaceWorld(
                segmentation,
                set(jawGroups["lower"]),
            )
            if fixedSurface:
                samples.extend(
                    self._subsample_polydata_points(fixedSurface, stride=80),
                )
            if movingSurface:
                if bool(parameterNode.step6PlanningContextImported):
                    movingSurface = self._step6CaseJawPolydataWorld(
                        parameterNode,
                        movingSurface,
                    )
                samples.extend(
                    self._subsample_polydata_points(movingSurface, stride=80),
                )
        if parameterNode.draftTemplateSupportModel:
            try:
                collision_world, _ = self.templateCollisionAnatomyWorld(
                    parameterNode.draftTemplateSupportModel,
                )
                collision_world = self._step6TargetAttachedPolydataWorld(
                    parameterNode,
                    collision_world,
                )
                samples.extend(
                    self._subsample_polydata_points(collision_world, stride=40),
                )
            except ValueError:
                pass
        if parameterNode.finalPrintableTemplateModel:
            template_poly = self._step6TargetAttachedModelPolydataWorld(
                parameterNode,
                parameterNode.finalPrintableTemplateModel,
            )
            samples.extend(
                self._subsample_polydata_points(template_poly, stride=60),
            )
        if parameterNode.targetDockingAssemblyModel:
            dock_poly = self._step6TargetAttachedModelPolydataWorld(
                parameterNode,
                parameterNode.targetDockingAssemblyModel,
            )
            samples.extend(
                self._subsample_polydata_points(dock_poly, stride=40),
            )
        for phantom_model in self.draftPhantomModelNodes():
            if not phantom_model:
                continue
            phantom_poly = model_polydata_in_world(phantom_model)
            samples.extend(
                self._subsample_polydata_points(phantom_poly, stride=60),
            )
        if not samples:
            return np.zeros((0, 3), dtype=float)
        return np.asarray(samples, dtype=float)

    @staticmethod
    def _transformPolydataWithMatrix(
        polydata: vtk.vtkPolyData,
        matrix: vtk.vtkMatrix4x4,
    ) -> vtk.vtkPolyData:
        transform = vtk.vtkTransform()
        transform.SetMatrix(matrix)
        surfaceFilter = vtk.vtkTransformPolyDataFilter()
        surfaceFilter.SetInputData(polydata)
        surfaceFilter.SetTransform(transform)
        surfaceFilter.Update()
        result = vtk.vtkPolyData()
        result.DeepCopy(surfaceFilter.GetOutput())
        return result

    @staticmethod
    def _appendPolydata(
        surfaces: list[vtk.vtkPolyData | None],
    ) -> vtk.vtkPolyData | None:
        valid = [
            surface
            for surface in surfaces
            if surface is not None and surface.GetNumberOfPoints() > 0
        ]
        if not valid:
            return None
        append = vtk.vtkAppendPolyData()
        for surface in valid:
            append.AddInputData(surface)
        append.Update()
        result = vtk.vtkPolyData()
        result.DeepCopy(append.GetOutput())
        return result

    def _step6CaseJawMatrixWorld(self, parameterNode) -> vtk.vtkMatrix4x4:
        issues = self.step6CaseJawOpeningFreshnessIssues(parameterNode)
        if issues:
            raise ValueError(" ".join(issues))
        matrix = vtk.vtkMatrix4x4()
        parameterNode.step6CaseJawTransform.GetMatrixTransformToWorld(matrix)
        return matrix

    def _step6CaseJawPolydataWorld(
        self,
        parameterNode,
        polydataWorld: vtk.vtkPolyData,
    ) -> vtk.vtkPolyData:
        return self._transformPolydataWithMatrix(
            polydataWorld,
            self._step6CaseJawMatrixWorld(parameterNode),
        )

    def _step6TargetAttachedPolydataWorld(
        self,
        parameterNode,
        polydataWorld: vtk.vtkPolyData,
    ) -> vtk.vtkPolyData:
        if (
            bool(parameterNode.step6PlanningContextImported)
            and self.step6TargetJaw(parameterNode) == "lower"
        ):
            return self._step6CaseJawPolydataWorld(parameterNode, polydataWorld)
        return polydataWorld

    def _step6TargetAttachedModelPolydataWorld(
        self,
        parameterNode,
        model: vtkMRMLModelNode,
    ) -> vtk.vtkPolyData:
        polydata = model_polydata_in_world(model)
        return self._step6TargetAttachedPolydataWorld(parameterNode, polydata)

    def step6TrajectorySummary(self, parameterNode) -> dict:
        """Return Entry/Target in the active opened-mouth Step 6 world pose."""
        summary = self.getTrajectorySummary(parameterNode.trajectoryLine)
        if (
            not summary.get("isValid")
            or not bool(parameterNode.step6PlanningContextImported)
            or self.step6TargetJaw(parameterNode) != "lower"
        ):
            return summary
        matrix = self._step6CaseJawMatrixWorld(parameterNode)
        transformed = dict(summary)
        for key in ("entryRas", "targetRas"):
            point = [*map(float, summary[key]), 1.0]
            result = [0.0, 0.0, 0.0, 0.0]
            matrix.MultiplyPoint(point, result)
            transformed[key] = np.asarray(result[:3], dtype=float)
        return transformed

    def _polydataWorldToRobotBase(
        self,
        polydata_world: vtk.vtkPolyData,
        base_transform: vtkMRMLLinearTransformNode,
    ) -> vtk.vtkPolyData:
        """Express world-RAS millimetre surface geometry in base_link RAS."""
        base_world = self._worldMatrixFromTransform(base_transform)
        world_to_base = vtk.vtkMatrix4x4()
        vtk.vtkMatrix4x4.Invert(base_world, world_to_base)
        transform = vtk.vtkTransform()
        transform.SetMatrix(world_to_base)
        surface_filter = vtk.vtkTransformPolyDataFilter()
        surface_filter.SetInputData(polydata_world)
        surface_filter.SetTransform(transform)
        surface_filter.Update()
        result = vtk.vtkPolyData()
        result.DeepCopy(surface_filter.GetOutput())
        return result

    def _segmentationSegmentsSurfaceWorld(
        self,
        segmentation_node: vtkMRMLSegmentationNode,
        segment_ids: set[str],
    ) -> vtk.vtkPolyData | None:
        """Combine explicit segmentation surfaces in world-RAS coordinates."""
        if segmentation_node is None or not segment_ids:
            return None
        segmentation_node.CreateClosedSurfaceRepresentation()
        parent_to_world = vtk.vtkGeneralTransform()
        slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(
            segmentation_node.GetParentTransformNode(),
            None,
            parent_to_world,
        )
        append = vtk.vtkAppendPolyData()
        surface_count = 0
        for segment_id in sorted(str(value) for value in segment_ids if value):
            try:
                surface = self._getClosedSurfaceCopy(segmentation_node, segment_id)
            except (RuntimeError, ValueError):
                continue
            if surface is None or surface.GetNumberOfPoints() == 0:
                continue
            surface_filter = vtk.vtkTransformPolyDataFilter()
            surface_filter.SetInputData(surface)
            surface_filter.SetTransform(parent_to_world)
            surface_filter.Update()
            append.AddInputData(surface_filter.GetOutput())
            surface_count += 1
        if surface_count == 0:
            return None
        append.Update()
        combined = vtk.vtkPolyData()
        combined.DeepCopy(append.GetOutput())
        return combined

    def _segmentationSurfaceWorld(
        self,
        segmentation_node: vtkMRMLSegmentationNode,
        segment_ids: set[str] | None = None,
    ) -> vtk.vtkPolyData | None:
        """Combine available tooth closed surfaces in world-RAS coordinates."""
        if segmentation_node is None:
            return None
        available_ids = {
            str(record.get("segmentId") or "")
            for record in self.getTargetToothRecords(segmentation_node)
            if record.get("segmentId")
        }
        selected_ids = (
            available_ids
            if segment_ids is None
            else available_ids.intersection(segment_ids)
        )
        return self._segmentationSegmentsSurfaceWorld(
            segmentation_node,
            selected_ids,
        )

    def syncStep6MoveItPlanningScene(self, parameterNode) -> int:
        """Publish Step 6 anatomy/guide surfaces in the base_link frame."""
        base_transform = parameterNode.robotBaseTransform
        if base_transform is None:
            raise ValueError(_("Select the Step 6 robot base before syncing obstacles."))
        if bool(parameterNode.step6PlanningContextImported):
            jawIssues = self.step6CaseJawOpeningFreshnessIssues(parameterNode)
            if jawIssues:
                raise ValueError(" ".join(jawIssues))
        sources: list[tuple[str, str, vtk.vtkPolyData]] = []
        model_candidates = [
            *self.draftPhantomModelNodes(),
            parameterNode.draftTemplateSupportModel,
            parameterNode.finalPrintableTemplateModel,
            parameterNode.targetDockingAssemblyModel,
        ]
        for model in dict.fromkeys(node for node in model_candidates if node is not None):
            if not isinstance(model, vtkMRMLModelNode):
                continue
            world_surface = model_polydata_in_world(model)
            if model in {
                parameterNode.draftTemplateSupportModel,
                parameterNode.finalPrintableTemplateModel,
                parameterNode.targetDockingAssemblyModel,
            }:
                world_surface = self._step6TargetAttachedPolydataWorld(
                    parameterNode,
                    world_surface,
                )
            if world_surface is None or world_surface.GetNumberOfPoints() == 0:
                continue
            sources.append((model.GetID(), model.GetName(), world_surface))

        segmentation = parameterNode.teethSegmentation
        target_id = str(parameterNode.targetToothSegmentId or "")
        all_tooth_ids = {
            str(record.get("segmentId") or "")
            for record in self.getTargetToothRecords(segmentation)
            if record.get("segmentId")
        } if segmentation else set()
        jawGroups = (
            self.step6CaseJawSegmentIds(segmentation)
            if segmentation
            else {
                "upperTeeth": (),
                "lowerTeeth": (),
                "upperJaw": (),
                "lowerJaw": (),
            }
        )
        lowerToothIds = set(jawGroups["lowerTeeth"])
        target_world = self._segmentationSegmentsSurfaceWorld(
            segmentation,
            {target_id} if target_id else set(),
        ) if segmentation else None
        if target_world is not None and target_id in lowerToothIds:
            target_world = self._step6CaseJawPolydataWorld(
                parameterNode,
                target_world,
            )
        if target_world is not None:
            sources.append(
                (
                    f"{segmentation.GetID()}:target:{target_id}",
                    self.step6TargetCollisionObjectName(parameterNode),
                    target_world,
                )
            )
        nonTargetIds = all_tooth_ids - {target_id}
        fixedNonTarget = self._segmentationSegmentsSurfaceWorld(
            segmentation,
            nonTargetIds - lowerToothIds,
        ) if segmentation else None
        movingNonTarget = self._segmentationSegmentsSurfaceWorld(
            segmentation,
            nonTargetIds.intersection(lowerToothIds),
        ) if segmentation else None
        if movingNonTarget is not None:
            movingNonTarget = self._step6CaseJawPolydataWorld(
                parameterNode,
                movingNonTarget,
            )
        non_target_world = self._appendPolydata(
            [fixedNonTarget, movingNonTarget],
        )
        if non_target_world is not None:
            sources.append(
                (
                    f"{segmentation.GetID()}:non-target-teeth",
                    "dentobot_non_target_teeth",
                    non_target_world,
                )
            )
        fixedJaw = self._segmentationSegmentsSurfaceWorld(
            segmentation,
            set(jawGroups["upperJaw"]),
        ) if segmentation else None
        movingJaw = self._segmentationSegmentsSurfaceWorld(
            segmentation,
            set(jawGroups["lowerJaw"]),
        ) if segmentation else None
        if movingJaw is not None:
            movingJaw = self._step6CaseJawPolydataWorld(
                parameterNode,
                movingJaw,
            )
        jawWorld = self._appendPolydata([fixedJaw, movingJaw])
        if jawWorld is not None:
            sources.append(
                (
                    f"{segmentation.GetID()}:case-jaw-bones",
                    "dentobot_case_jaw_bones",
                    jawWorld,
                )
            )

        active_ids = {source_id for source_id, _name, _surface in sources}
        remove_stale_moveit_obstacle_proxies(active_ids)
        for source_id, source_name, world_surface in sources:
            base_surface = self._polydataWorldToRobotBase(
                world_surface,
                base_transform,
            )
            ok, message = sync_moveit_obstacle_polydata(
                source_id=source_id,
                source_name=source_name,
                polydata_base_mm=base_surface,
            )
            if not ok:
                raise RuntimeError(message)
        return len(sources)

    @staticmethod
    def step6TargetCollisionObjectName(parameterNode) -> str:
        segment_id = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            str(parameterNode.targetToothSegmentId or "unknown"),
        )
        return f"dentobot_target_tooth_{segment_id}"

    def step6TargetCollisionObjectId(self, parameterNode) -> str:
        segmentation = parameterNode.teethSegmentation
        target_id = str(parameterNode.targetToothSegmentId or "")
        if segmentation is None or not target_id:
            return ""
        source_id = f"{segmentation.GetID()}:target:{target_id}"
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if (
                node.GetAttribute("DENTOBOT.MoveItObstacleProxy") == "true"
                and node.GetAttribute("DENTOBOT.MoveItObstacleSource") == source_id
            ):
                return str(node.GetID() or "")
        return ""

    def importStep6PlanningContext(self, parameterNode) -> PlanningContextReport:
        report = validate_planning_context(
            self.buildPlanningContextNodeMap(parameterNode),
        )
        if not report.ready:
            raise ValueError(report.message)
        freshnessIssues = self.step6PlanningContextFreshnessIssues(parameterNode)
        if freshnessIssues:
            raise ValueError(
                _(
                    "Planning package contains stale or unverified geometry: %1"
                ).replace("%1", " ".join(freshnessIssues))
            )
        base_transform = self.ensureRobotBaseTransform(
            parameterNode.robotBaseTransform,
        )
        parameterNode.robotBaseTransform = base_transform
        parameterNode.step6PlanningContextImported = True
        base_transform.SetAttribute(self.STEP6_PLANNING_CONTEXT_ATTRIBUTE, "true")
        return report

    def step6PlanningContextFreshnessIssues(self, parameterNode) -> list[str]:
        """Return deterministic reasons a saved case is unsafe for Step 6."""
        issues = []
        trajectory = parameterNode.trajectoryLine
        if trajectory is None or trajectory.GetNumberOfDefinedControlPoints() != 2:
            issues.append(_("Step 4A trajectory must contain exactly two points."))
        elif not trajectory.GetLocked():
            issues.append(_("Step 4A trajectory is not locked."))
        elif trajectory.GetAttribute("DENTOBOT.CoordinateSystem") != "SlicerRASmm":
            issues.append(_("Step 4A trajectory is not declared in Slicer RAS mm."))

        docking = parameterNode.targetDockingAssemblyModel
        if docking is None:
            issues.append(_("Step 4C docking assembly is missing."))
        else:
            state = docking.GetAttribute("DENTOBOT.GeometryState") or "Unknown"
            orientation = docking.GetAttribute("DENTOBOT.OrientationState") or "Unknown"
            if state != "Current" or orientation != "Confirmed":
                reason = docking.GetAttribute("DENTOBOT.StaleReason") or _(
                    "regenerate and confirm the docking assembly"
                )
                issues.append(
                    _("Step 4C docking assembly is %1/%2 (%3)")
                    .replace("%1", state)
                    .replace("%2", orientation)
                    .replace("%3", reason)
                )

        finalTemplate = parameterNode.finalPrintableTemplateModel
        if finalTemplate is None:
            issues.append(_("Step 5C printable template is missing."))
        else:
            state = finalTemplate.GetAttribute("DENTOBOT.GeometryState") or "Unknown"
            verification = (
                finalTemplate.GetAttribute("DENTOBOT.VerificationState") or "NotVerified"
            )
            if state != "Current" or verification not in {"PASS", "WARNING"}:
                reason = finalTemplate.GetAttribute("DENTOBOT.StaleReason") or _(
                    "regenerate and verify the printable template"
                )
                issues.append(
                    _("Step 5C printable template is %1/%2 (%3)")
                    .replace("%1", state)
                    .replace("%2", verification)
                    .replace("%3", reason)
                )
        if bool(parameterNode.step6PlanningContextImported):
            issues.extend(self.step6CaseJawOpeningFreshnessIssues(parameterNode))
        return issues

    def setRobotBaseMountLocked(self, parameterNode, locked: bool) -> None:
        requested_status = (
            BasePlacementStatus.PROVISIONAL_LOCKED
            if locked
            else BasePlacementStatus.UNLOCKED
        )
        current_status = normalize_base_status(parameterNode.step6BasePlacementStatus)
        state_changed = bool(parameterNode.robotBaseMountLocked) != bool(locked) or (
            current_status is not requested_status
        )
        parameterNode.robotBaseMountLocked = bool(locked)
        parameterNode.step6BasePlacementStatus = requested_status.value
        if state_changed:
            parameterNode.step6BasePlacementSource = (
                "manual-mount-plane" if locked else "operator-unlocked"
            )
            parameterNode.step6BasePlacementRevision = max(
                0, int(parameterNode.step6BasePlacementRevision)
            ) + 1
            self.invalidateStep6TaskConfirmation(
                parameterNode,
                _("Robot base lock state changed."),
            )
        base_transform = parameterNode.robotBaseTransform
        plane_node = parameterNode.robotMountPlane
        if base_transform and self.isRobotBaseTransformNode(base_transform):
            base_transform.SetAttribute(
                "DENTOBOT.RobotBaseMountLocked",
                "true" if locked else "false",
            )
            display = base_transform.GetDisplayNode()
            if display:
                for method_name, value in (
                    ("SetEditorVisibility", not locked),
                    ("SetHandlesInteractive", not locked),
                    ("SetTranslationHandleVisibility", not locked),
                    ("SetRotationHandleVisibility", not locked),
                    ("SetScaleHandleVisibility", False),
                ):
                    method = getattr(display, method_name, None)
                    if method:
                        method(value)
        if plane_node and self.isRobotMountPlaneNode(plane_node):
            plane_node.SetLocked(locked)
            plane_node.SetSelectable(not locked)
            display = plane_node.GetDisplayNode()
            if display:
                display.SetHandlesInteractive(not locked)
                display.SetTranslationHandleVisibility(not locked)
                display.SetRotationHandleVisibility(not locked)

    def robotProfileFingerprint(self) -> str:
        return str(self.caseBundleRobotProfile().get("identitySha256") or "")

    def robotBaseFingerprint(self, parameterNode) -> str:
        base = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base):
            return ""
        pose_fingerprint = self.robotBasePoseFingerprint(base)
        return fingerprint(
            {
                "poseFingerprint": pose_fingerprint,
                "status": normalize_base_status(
                    parameterNode.step6BasePlacementStatus
                    or ("LegacyLocked" if parameterNode.robotBaseMountLocked else "Unlocked")
                ).value,
                "source": str(parameterNode.step6BasePlacementSource or "legacy-scene"),
                "sourceRevision": int(parameterNode.step6BasePlacementRevision),
            }
        )

    def robotBasePoseFingerprint(self, base) -> str:
        if not self.isRobotBaseTransformNode(base):
            return ""
        matrix = self._worldMatrixFromTransform(base)
        elements = tuple(
            tuple(round(float(matrix.GetElement(row, column)), 9) for column in range(4))
            for row in range(4)
        )
        return fingerprint({"matrixToWorldRas": elements})

    def step6TrajectoryRevision(self, parameterNode) -> str:
        trajectory = parameterNode.trajectoryLine
        if trajectory is None:
            return ""
        summary = self.step6TrajectorySummary(parameterNode)
        if not summary.get("isValid"):
            return ""
        attributes = {}
        for name in (
            "DENTOBOT.CoordinateSystem",
            "DENTOBOT.LineageTargetSegmentID",
            "DENTOBOT.GeometryState",
            "DENTOBOT.SchemaVersion",
        ):
            value = trajectory.GetAttribute(name)
            if value is not None:
                attributes[name] = str(value)
        return fingerprint(
            {
                "entryRasMm": tuple(round(float(value), 9) for value in summary["entryRas"]),
                "targetRasMm": tuple(round(float(value), 9) for value in summary["targetRas"]),
                "locked": bool(trajectory.GetLocked()),
                "attributes": attributes,
            }
        )

    def step6TaskLimitsFingerprint(self, parameterNode) -> str:
        limits = self.getTaskJointLimits(parameterNode)
        return fingerprint(
            {
                "minimumDisplay": limits.as_display_vector(),
                "maximumDisplay": limits.as_display_max_vector(),
                "reviewedProposal": str(parameterNode.step6AssistedLimitProposalJson or ""),
            }
        )

    def taskHomeRecord(self, parameterNode):
        payload = str(parameterNode.step6TaskHomeJson or "").strip()
        return parse_task_home(payload) if payload else None

    def saveCurrentTaskHome(self, parameterNode):
        state = normalize_base_status(parameterNode.step6BasePlacementStatus)
        if state not in {
            BasePlacementStatus.PROVISIONAL_LOCKED,
            BasePlacementStatus.REGISTERED_LOCKED,
        }:
            raise ValueError(_("Provisionally lock the robot base before saving Task Home."))
        previous = self.taskHomeRecord(parameterNode)
        record = build_task_home(
            joint_positions_si_from_display(
                parameterNode.robotJoint1Deg,
                parameterNode.robotJoint2Mm,
                parameterNode.robotJoint3Deg,
                parameterNode.robotJoint4Mm,
                parameterNode.robotJoint5Deg,
                parameterNode.robotJoint6Deg,
            ),
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            robot_profile_fingerprint=self.robotProfileFingerprint(),
            revision=(previous.revision + 1 if previous else 1),
        )
        parameterNode.step6TaskHomeJson = canonical_json(record.to_dict())
        self.invalidateStep6TaskConfirmation(parameterNode, _("Task Home changed."))
        return record

    def taskHomeFreshnessIssues(self, parameterNode) -> tuple[str, ...]:
        try:
            record = self.taskHomeRecord(parameterNode)
        except (ValueError, json.JSONDecodeError):
            return (_("Saved Task Home record is invalid."),)
        if record is None:
            return (_("Save a case/base-specific Task Home."),)
        issues = []
        if record.base_fingerprint != self.robotBaseFingerprint(parameterNode):
            issues.append(_("Task Home belongs to a different base pose."))
        if record.robot_profile_fingerprint != self.robotProfileFingerprint():
            issues.append(_("Task Home belongs to different robot resources."))
        return tuple(issues)

    def proposeAssistedTaskLimits(self, parameterNode, workspaceResult):
        mechanical = default_task_joint_limits_from_urdf(self.robotDescriptionPaths()[0])
        previous_revision = 0
        try:
            previous = json.loads(parameterNode.step6AssistedLimitProposalJson or "{}")
            previous_revision = int(previous.get("revision", 0))
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
        proposal = build_assisted_limit_proposal(
            workspaceResult.accepted_joint_display_vectors,
            mechanical.as_display_vector(),
            mechanical.as_display_max_vector(),
            revision=previous_revision + 1,
            reviewed=False,
        )
        parameterNode.step6AssistedLimitProposalJson = canonical_json(proposal.to_dict())
        self.invalidateStep6TaskConfirmation(parameterNode, _("Workspace limit proposal changed."))
        return proposal

    def reviewAndApplyAssistedTaskLimits(self, parameterNode):
        try:
            data = json.loads(parameterNode.step6AssistedLimitProposalJson or "")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(_("Generate an assisted-limit proposal first.")) from exc
        minima = tuple(float(value) for value in data.get("minimum_display", ()))
        maxima = tuple(float(value) for value in data.get("maximum_display", ()))
        if len(minima) != 6 or len(maxima) != 6:
            raise ValueError(_("The assisted-limit proposal is invalid."))
        fields = (
            ("robotJoint1TaskMinDeg", "robotJoint1TaskMaxDeg"),
            ("robotJoint2TaskMinMm", "robotJoint2TaskMaxMm"),
            ("robotJoint3TaskMinDeg", "robotJoint3TaskMaxDeg"),
            ("robotJoint4TaskMinMm", "robotJoint4TaskMaxMm"),
            ("robotJoint5TaskMinDeg", "robotJoint5TaskMaxDeg"),
            ("robotJoint6TaskMinDeg", "robotJoint6TaskMaxDeg"),
        )
        for index, (minimum_field, maximum_field) in enumerate(fields):
            setattr(parameterNode, minimum_field, minima[index])
            setattr(parameterNode, maximum_field, maxima[index])
        data["reviewed"] = True
        parameterNode.step6AssistedLimitProposalJson = canonical_json(data)
        self.invalidateStep6TaskConfirmation(parameterNode, _("Reviewed task limits changed."))
        return data

    def assistedTaskLimitsReviewed(self, parameterNode) -> bool:
        try:
            data = json.loads(parameterNode.step6AssistedLimitProposalJson or "")
            return bool(data.get("reviewed"))
        except (ValueError, TypeError, json.JSONDecodeError):
            return False

    def confirmStep6Task(self, parameterNode):
        if normalize_base_status(parameterNode.step6BasePlacementStatus) not in {
            BasePlacementStatus.PROVISIONAL_LOCKED,
            BasePlacementStatus.REGISTERED_LOCKED,
        }:
            raise ValueError(_("Review and provisionally lock the robot base first."))
        home_issues = self.taskHomeFreshnessIssues(parameterNode)
        if home_issues:
            raise ValueError(" ".join(home_issues))
        if not self.assistedTaskLimitsReviewed(parameterNode):
            raise ValueError(_("Review and apply the assisted task-limit proposal first."))
        freshness = self.step6PlanningContextFreshnessIssues(parameterNode)
        if freshness:
            raise ValueError(" ".join(freshness))
        trajectory = self.step6TrajectorySummary(parameterNode)
        home = self.taskHomeRecord(parameterNode)
        record = build_task_snapshot(
            target_segment_id=str(parameterNode.targetToothSegmentId or ""),
            trajectory_revision=self.step6TrajectoryRevision(parameterNode),
            entry_ras_mm=trajectory["entryRas"],
            target_ras_mm=trajectory["targetRas"],
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            home_fingerprint=fingerprint(home.to_dict()),
            limits_fingerprint=self.step6TaskLimitsFingerprint(parameterNode),
            robot_profile_fingerprint=self.robotProfileFingerprint(),
            tool_frame=str(parameterNode.step6ToolFrame),
            tool_provenance="CAD-derived/provisional/un-calibrated",
            corridor_radius_mm=float(parameterNode.step6TrajectoryCorridorRadiusMm),
        )
        parameterNode.step6ConfirmedTaskJson = canonical_json(record.to_dict())
        return record

    def confirmedTaskRecord(self, parameterNode):
        payload = str(parameterNode.step6ConfirmedTaskJson or "").strip()
        return parse_task_snapshot(payload) if payload else None

    def confirmedTaskFreshnessIssues(self, parameterNode) -> tuple[str, ...]:
        try:
            snapshot = self.confirmedTaskRecord(parameterNode)
        except (ValueError, json.JSONDecodeError):
            return (_("Confirmed Step 6 task record is invalid."),)
        if snapshot is None:
            return (_("Confirm the immutable Step 6 task snapshot."),)
        home = self.taskHomeRecord(parameterNode)
        return task_snapshot_invalidation_reasons(
            snapshot,
            target_segment_id=str(parameterNode.targetToothSegmentId or ""),
            trajectory_revision=self.step6TrajectoryRevision(parameterNode),
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            home_fingerprint=fingerprint(home.to_dict()) if home else "",
            limits_fingerprint=self.step6TaskLimitsFingerprint(parameterNode),
            robot_profile_fingerprint=self.robotProfileFingerprint(),
            tool_frame=str(parameterNode.step6ToolFrame),
        )

    def invalidateStep6TaskConfirmation(
        self,
        parameterNode,
        reason: str,
        *,
        makeBaseStale: bool = False,
    ) -> None:
        had_confirmation = bool(str(parameterNode.step6ConfirmedTaskJson or "").strip())
        parameterNode.step6ConfirmedTaskJson = ""
        if makeBaseStale and parameterNode.robotBaseMountLocked:
            parameterNode.step6BasePlacementStatus = BasePlacementStatus.STALE.value
            parameterNode.robotBaseMountLocked = False
        workspace = self.robotWorkspaceModelNode()
        if workspace is not None:
            workspace.SetAttribute("DENTOBOT.WorkspaceState", "Stale")
        if had_confirmation:
            logging.warning("Invalidated Step 6 task confirmation: %s", reason)

    def getTaskJointLimits(self, parameterNode) -> TaskJointLimits:
        urdf_path, _package_root = self.robotDescriptionPaths()
        urdf_limits = default_task_joint_limits_from_urdf(urdf_path)
        task_limits = build_task_joint_limits_from_parameter_values(
            j1_min=parameterNode.robotJoint1TaskMinDeg,
            j1_max=parameterNode.robotJoint1TaskMaxDeg,
            j2_min=parameterNode.robotJoint2TaskMinMm,
            j2_max=parameterNode.robotJoint2TaskMaxMm,
            j3_min=parameterNode.robotJoint3TaskMinDeg,
            j3_max=parameterNode.robotJoint3TaskMaxDeg,
            j4_min=parameterNode.robotJoint4TaskMinMm,
            j4_max=parameterNode.robotJoint4TaskMaxMm,
            j5_min=parameterNode.robotJoint5TaskMinDeg,
            j5_max=parameterNode.robotJoint5TaskMaxDeg,
            j6_min=parameterNode.robotJoint6TaskMinDeg,
            j6_max=parameterNode.robotJoint6TaskMaxDeg,
        )
        return apply_task_joint_limits_to_display_ranges(task_limits, urdf_limits)

    def createOrUpdateRobotWorkspace(
        self,
        parameterNode,
    ) -> tuple[vtkMRMLModelNode, WorkspaceSampleResult]:
        """Create a base-parented, deterministic provisional-TCP reach cloud."""
        base_transform = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base_transform):
            raise ValueError(_("Load the Step 6 robot and place its base first."))
        sample_count = int(parameterNode.robotWorkspaceSampleCount)
        if sample_count < 50 or sample_count > 5000:
            raise ValueError(_("Workspace sample count must be between 50 and 5000."))
        urdf_path, package_root = self.robotDescriptionPaths()
        base_world = self._numpyFromVtkMatrix(
            self._worldMatrixFromTransform(base_transform),
        )
        result = sample_filtered_tcp_workspace(
            limits=self.getTaskJointLimits(parameterNode),
            sample_count=sample_count,
            current_display_joints=(
                parameterNode.robotJoint1Deg,
                parameterNode.robotJoint2Mm,
                parameterNode.robotJoint3Deg,
                parameterNode.robotJoint4Mm,
                parameterNode.robotJoint5Deg,
                parameterNode.robotJoint6Deg,
            ),
            urdf_path=urdf_path,
            package_root=package_root,
            base_world_matrix=base_world,
            coarse_self_clearance_mm=max(
                5.0,
                float(parameterNode.robotCoarseSelfClearanceMm),
            ),
            environment_points_mm=self.step6EnvironmentObstaclePointsMm(parameterNode),
            environment_clearance_mm=float(parameterNode.robotEnvironmentClearanceMm),
        )
        if not result.accepted_tcp_base_mm:
            raise RuntimeError(
                _(
                    "All sampled configurations were rejected. Widen valid task "
                    "limits or review the draft clearances/base placement."
                )
            )

        points = vtk.vtkPoints()
        vertices = vtk.vtkCellArray()
        for point in result.accepted_tcp_base_mm:
            point_id = points.InsertNextPoint(*point)
            vertices.InsertNextCell(1)
            vertices.InsertCellPoint(point_id)
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetVerts(vertices)

        model = self.robotWorkspaceModelNode()
        if not model:
            model = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 6] DENTO Filtered TCP Workspace",
            )
        model.SetName("[Step 6] DENTO Filtered TCP Workspace")
        model.SetAttribute("DENTOBOT.ModelRole", self.ROBOT_WORKSPACE_MODEL_ROLE)
        model.SetAttribute("DENTOBOT.Status", "SimulationOnly")
        model.SetAttribute("DENTOBOT.WorkspaceState", "Current")
        model.SetAttribute("DENTOBOT.WorkspaceAlgorithm", "Halton6D+URDFFK+AABB")
        model.SetAttribute("DENTOBOT.WorkspaceRequested", str(result.requested_count))
        model.SetAttribute("DENTOBOT.WorkspaceAccepted", str(result.accepted_count))
        model.SetAndObservePolyData(polydata)
        model.SetAndObserveTransformNodeID(base_transform.GetID())
        model.SetSaveWithScene(False)
        model.CreateDefaultDisplayNodes()
        display = model.GetDisplayNode()
        if display:
            display.SetVisibility(True)
            display.SetVisibility2D(False)
            display.SetVisibility3D(True)
            display.SetColor(0.10, 0.82, 0.95)
            display.SetOpacity(0.55)
            display.SetRepresentation(0)  # vtkMRMLDisplayNode::Points
            display.SetPointSize(3.0)
            display.SetLighting(False)
        model.SetSelectable(False)
        return model, result

    def deleteRobotWorkspaceModel(self) -> bool:
        model = self.robotWorkspaceModelNode()
        if not model:
            return False
        slicer.mrmlScene.RemoveNode(model)
        return True

    def applyTaskJointLimitsToJointControls(self, parameterNode) -> TaskJointLimits:
        limits = self.getTaskJointLimits(parameterNode)
        display_ranges = apply_task_joint_limits_to_display_ranges(
            limits,
            default_task_joint_limits_from_urdf(self.robotDescriptionPaths()[0]),
        )
        return display_ranges

    def resetTaskJointLimitsToUrdf(self, parameterNode) -> TaskJointLimits:
        urdf_path, _package_root = self.robotDescriptionPaths()
        limits = default_task_joint_limits_from_urdf(urdf_path)
        parameterNode.robotJoint1TaskMinDeg = limits.joint_1.minimum
        parameterNode.robotJoint1TaskMaxDeg = limits.joint_1.maximum
        parameterNode.robotJoint2TaskMinMm = limits.joint_2.minimum
        parameterNode.robotJoint2TaskMaxMm = limits.joint_2.maximum
        parameterNode.robotJoint3TaskMinDeg = limits.joint_3.minimum
        parameterNode.robotJoint3TaskMaxDeg = limits.joint_3.maximum
        parameterNode.robotJoint4TaskMinMm = limits.joint_4.minimum
        parameterNode.robotJoint4TaskMaxMm = limits.joint_4.maximum
        parameterNode.robotJoint5TaskMinDeg = limits.joint_5.minimum
        parameterNode.robotJoint5TaskMaxDeg = limits.joint_5.maximum
        parameterNode.robotJoint6TaskMinDeg = limits.joint_6.minimum
        parameterNode.robotJoint6TaskMaxDeg = limits.joint_6.maximum
        return limits

    def planStep6TrajectoryMotion(self, parameterNode) -> MotionPlanResult:
        if not parameterNode.step6PlanningContextImported:
            raise ValueError(
                _("Import the Step 6 planning package before motion planning.")
            )
        freshnessIssues = self.step6PlanningContextFreshnessIssues(parameterNode)
        if freshnessIssues:
            parameterNode.step6PlanningContextImported = False
            raise ValueError(
                _("Step 6 planning context became stale: %1").replace(
                    "%1", " ".join(freshnessIssues)
                )
            )
        if not parameterNode.robotBaseMountLocked:
            raise ValueError(
                _("Lock the robot base mount before motion planning.")
            )
        if not parameterNode.robotBaseTransform:
            raise ValueError(_("Load or create the Step 6 robot base first."))
        ros_active = self.isRos2MotionControlActive(parameterNode.robotBaseTransform)
        if not step6_motion_plan_robot_ready(
            ros_motion_active=ros_active,
            mrml_link_count=len(self.robotModelNodes()),
        ):
            raise ValueError(
                _("Load the ROS robot or MRML fallback before motion planning.")
            )
        summary = self.step6TrajectorySummary(parameterNode)
        if not summary.get("isValid"):
            raise ValueError(_("Select a valid Entry-to-Target trajectory first."))

        urdf_path, package_root = self.robotDescriptionPaths()
        base_world = self._numpyFromVtkMatrix(
            self._worldMatrixFromTransform(parameterNode.robotBaseTransform),
        )
        start_display = (
            parameterNode.robotJoint1Deg,
            parameterNode.robotJoint2Mm,
            parameterNode.robotJoint3Deg,
            parameterNode.robotJoint4Mm,
            parameterNode.robotJoint5Deg,
            parameterNode.robotJoint6Deg,
        )
        limits = self.getTaskJointLimits(parameterNode)
        if ros_active:
            obstacle_count = self.syncStep6MoveItPlanningScene(parameterNode)
            moveit_result = plan_moveit_cartesian_path(
                entry_ras_mm=summary["entryRas"],
                target_ras_mm=summary["targetRas"],
                sample_count=int(parameterNode.robotMotionPlanSampleCount),
                base_transform=parameterNode.robotBaseTransform,
                avoid_collisions=True,
                minimum_fraction=0.99,
            )
            return MotionPlanResult(
                success=moveit_result.success,
                message=(
                    f"{moveit_result.message} Planning scene contained "
                    f"{obstacle_count} Step 6 collision surface(s); the manual "
                    "command guard requires 5 mm self/world clearance."
                ),
                waypoint_joint_vectors_si=moveit_result.waypoint_joint_vectors_si,
                planner="moveit_cartesian",
                cartesian_fraction=moveit_result.fraction,
                waypoint_times_sec=moveit_result.waypoint_times_sec,
            )
        environment_points = self.step6EnvironmentObstaclePointsMm(parameterNode)
        return plan_trajectory_motion(
            entry_ras_mm=summary["entryRas"],
            target_ras_mm=summary["targetRas"],
            start_display_joints=start_display,
            limits=limits,
            urdf_path=urdf_path,
            package_root=package_root,
            base_world_matrix=base_world,
            sample_count=int(parameterNode.robotMotionPlanSampleCount),
            coarse_self_clearance_mm=max(
                5.0,
                float(parameterNode.robotCoarseSelfClearanceMm),
            ),
            environment_points_mm=environment_points,
            environment_clearance_mm=float(parameterNode.robotEnvironmentClearanceMm),
        )

    def step6ApproachPoints(self, parameterNode):
        summary = self.step6TrajectorySummary(parameterNode)
        if not summary.get("isValid"):
            raise ValueError(_("Select a valid Entry-to-Target trajectory first."))
        return approach_points(
            summary["entryRas"],
            summary["targetRas"],
            float(parameterNode.step6ApproachStandoffMm),
        )

    def _worldMatrixFromTransform(
        self,
        transform_node: vtkMRMLLinearTransformNode,
    ) -> vtk.vtkMatrix4x4:
        matrix = vtk.vtkMatrix4x4()
        transform_node.GetMatrixTransformToWorld(matrix)
        return matrix

    def deleteRobotPlacement(
        self,
        baseTransform: vtkMRMLLinearTransformNode | None,
        planeNode: vtkMRMLMarkupsPlaneNode | None,
    ) -> list[str]:
        nodes = [*self.robotModelNodes(), *self.robotLinkTransformNodes()]
        workspace = self.robotWorkspaceModelNode()
        if workspace:
            nodes.append(workspace)
        if self.isRobotBaseTransformNode(baseTransform):
            nodes.append(baseTransform)
        if self.isRobotMountPlaneNode(planeNode):
            nodes.append(planeNode)
        nodes.extend(self.step6ForeheadProxyNodes())
        removed = []
        for node in dict.fromkeys(nodes):
            if slicer.mrmlScene.IsNodePresent(node):
                removed.append(node.GetName())
                slicer.mrmlScene.RemoveNode(node)
        return removed
