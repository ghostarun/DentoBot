"""Extracted robot placement and display methods; public APIs remain on RobotLogicMixin."""

from __future__ import annotations

from .runtime import *
from dentobot_workflow.offline_placement_status import (
    classify_offline_base_placement,
)


class RobotPlacementLogicMixin:
    ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE = (
        "DENTOBOT.RobotBasePlacementAuthority"
    )
    ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY = "ManualSimulationBaseUnreviewed"
    ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY = "ManualSimulationBaseReviewed"
    ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY = "QuarantinedCircularMountPlane"
    ROBOT_BASE_VIRTUAL_FOREHEAD_AUTHORITY = "VirtualForeheadPriorV1"

    def offlinePlacementMirrorState(self, parameterNode) -> dict[str, object]:
        """Shared 3B / 6.1 classifier: pass, manual, or missing."""

        pose = self.evaluateCaseFoundationEligibility(parameterNode)["pose"]
        pose_eligible = bool(pose.get("eligible"))
        pose_fingerprint = ""
        if pose_eligible:
            try:
                snapshot = self.buildCaseFoundationSnapshot(parameterNode)
                pose_fingerprint = str(snapshot.planning_pose_fingerprint or "")
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pose_fingerprint = str(
                    pose.get("planning_pose_fingerprint") or ""
                )
        base = parameterNode.robotBaseTransform
        authority = ""
        base_fingerprint = ""
        if self.isRobotBaseTransformNode(base):
            authority = str(
                base.GetAttribute(self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE)
                or ""
            )
            base_fingerprint = str(
                base.GetAttribute("DENTOBOT.CaseFoundationFingerprint") or ""
            )
        state = classify_offline_base_placement(
            pose_eligible=pose_eligible,
            robot_link_count=len(self.robotModelNodes()),
            placement_authority=authority,
            base_case_fingerprint=base_fingerprint,
            pose_fingerprint=pose_fingerprint,
        )
        return {
            "state": state,
            "poseEligible": pose_eligible,
            "placementAuthority": authority,
            "poseFingerprint": pose_fingerprint,
            "baseFingerprint": base_fingerprint,
            "robotLinkCount": len(self.robotModelNodes()),
        }

    def _validateSingleStep6RobotPlacement(
        self,
        baseTransform,
        linkModels: list,
        linkTransforms: list,
    ) -> None:
        modelIds = {node.GetID() for node in linkModels}
        if any(node.GetID() not in modelIds for node in self.robotModelNodes()):
            raise ValueError(_("Only one robot placement set is allowed in Step 6."))
        names = [node.GetAttribute("DENTOBOT.RobotLinkName") for node in self.robotModelNodes()]
        if any(name and names.count(name) > 1 for name in names):
            raise ValueError(_("Duplicate robot link meshes are present."))
        transformIds = {node.GetID() for node in linkTransforms}
        if any(
            node.GetID() not in transformIds
            for node in self.robotLinkTransformNodes()
        ):
            raise ValueError(_("Duplicate robot link transforms are present."))
        baseId = baseTransform.GetID() if baseTransform else ""
        extraBases = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode")
            if node.GetAttribute("DENTOBOT.TransformRole") == self.ROBOT_BASE_ROLE
            and node.GetID() != baseId
        ]
        if extraBases:
            raise ValueError(_("Only one robot base transform is allowed in Step 6."))

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
        base_transform.SetAttribute(
            self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
            self.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
        )
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
        if not baseTransform.GetAttribute(
            self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE
        ):
            baseTransform.SetAttribute(
                self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
                self.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
            )
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
            linkTransform.SetSaveWithScene(False)
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
            model.SetSaveWithScene(False)
            model.CreateDefaultDisplayNodes()
            modelStorage = model.GetStorageNode()
            if modelStorage:
                modelStorage.SetSaveWithScene(False)
            modelDisplay = model.GetDisplayNode()
            if modelDisplay:
                modelDisplay.SetSaveWithScene(False)
                modelDisplay.SetVisibility(True)
                modelDisplay.SetOpacity(1.0)
                modelDisplay.SetColor(*displayColors[index % len(displayColors)])
            resolvedModels.append(model)
        return baseTransform, resolvedModels

    def deleteTransientRobotRuntimeNodes(self) -> list[str]:
        """Remove reconstructible local robot meshes/poses from a restored scene."""
        nodes = [*self.robotModelNodes(), *self.robotLinkTransformNodes()]
        workspace = self.robotWorkspaceModelNode()
        if workspace:
            nodes.append(workspace)
        removed = []
        for node in dict.fromkeys(nodes):
            if slicer.mrmlScene.IsNodePresent(node):
                removed.append(node.GetName())
                slicer.mrmlScene.RemoveNode(node)
        return removed

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
        planeNode.SetLocked(True)
        planeNode.SetSelectable(False)
        planeNode.SetAttribute("DENTOBOT.MarkupsRole", self.ROBOT_MOUNT_PLANE_ROLE)
        planeNode.SetAttribute(
            "DENTOBOT.RobotPlacementSchemaVersion",
            self.ROBOT_PLACEMENT_SCHEMA_VERSION,
        )
        planeNode.SetAttribute("DENTOBOT.Status", "SimulationOnly")
        planeNode.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        planeNode.SetAttribute("DENTOBOT.GeometryState", "QuarantinedLegacy")
        planeNode.SetAttribute("DENTOBOT.IntendedUse", "VisualizationOnly")
        planeNode.SetAttribute("DENTOBOT.ExcludedFromPlacement", "true")
        planeNode.SetAttribute(
            "DENTOBOT.StaleReason",
            "Circular base-derived mount plane; not forehead or mount-face evidence.",
        )
        planeNode.CreateDefaultDisplayNodes()
        displayNode = planeNode.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetOpacity(0.28)
            displayNode.SetColor(0.15, 0.80, 0.95)
            displayNode.SetHandlesInteractive(False)
            displayNode.SetTranslationHandleVisibility(False)
            displayNode.SetRotationHandleVisibility(False)
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

    def _volumeRasBounds6(self, volume) -> np.ndarray | None:
        if volume is None:
            return None
        bounds = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        volume.GetRASBounds(bounds)
        return np.asarray(bounds, dtype=float)

    def _applyIndependentForeheadMountPlane(
        self,
        parameterNode,
        plane,
        fingerprint: str,
    ):
        from dentobot_workflow.virtual_forehead_mount import PLACEMENT_AUTHORITY

        node = parameterNode.robotMountPlane
        if node is not None and not self.isRobotMountPlaneNode(node):
            raise ValueError(_("Select the DENTOBOT robot mount plane."))
        node = node or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsPlaneNode",
            "[Step 6] Virtual Forehead Mount Plane",
        )
        node.SetName("[Step 6] Virtual Forehead Mount Plane")
        node.SetPlaneType(node.PlaneTypePointNormal)
        if hasattr(node, "SetNormalPointRequired"):
            node.SetNormalPointRequired(False)
        node.SetOriginWorld(tuple(float(v) for v in plane.origin_mm))
        node.SetNormalWorld(tuple(float(v) for v in plane.z_hat))
        node.SetSize(
            float(parameterNode.step6ForeheadProxyWidthMm),
            float(parameterNode.step6ForeheadProxyHeightMm),
        )
        node.SetLocked(True)
        node.SetSelectable(False)
        node.SetAttribute("DENTOBOT.MarkupsRole", self.ROBOT_MOUNT_PLANE_ROLE)
        node.SetAttribute(
            "DENTOBOT.RobotPlacementSchemaVersion",
            self.ROBOT_PLACEMENT_SCHEMA_VERSION,
        )
        node.SetAttribute("DENTOBOT.Status", "SimulationOnly")
        node.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        node.SetAttribute("DENTOBOT.GeometryState", "Provisional")
        node.SetAttribute("DENTOBOT.IntendedUse", "VisualizationOnly")
        node.SetAttribute("DENTOBOT.ExcludedFromPlacement", "false")
        node.SetAttribute("DENTOBOT.PlacementAuthority", PLACEMENT_AUTHORITY)
        node.SetAttribute("DENTOBOT.CaseFoundationFingerprint", str(fingerprint))
        node.SetAttribute(
            "DENTOBOT.ForeheadOriginMm",
            ",".join(f"{float(v):.9f}" for v in plane.origin_mm),
        )
        node.SetAttribute(
            "DENTOBOT.ForeheadX",
            ",".join(f"{float(v):.9f}" for v in plane.x_hat),
        )
        node.SetAttribute(
            "DENTOBOT.ForeheadY",
            ",".join(f"{float(v):.9f}" for v in plane.y_hat),
        )
        node.SetAttribute(
            "DENTOBOT.ForeheadZ",
            ",".join(f"{float(v):.9f}" for v in plane.z_hat),
        )
        node.SetAttribute("DENTOBOT.StaleReason", None)
        node.CreateDefaultDisplayNodes()
        displayNode = node.GetDisplayNode()
        if displayNode:
            displayNode.SetVisibility(True)
            displayNode.SetVisibility2D(True)
            displayNode.SetVisibility3D(True)
            displayNode.SetOpacity(0.28)
            displayNode.SetColor(0.15, 0.80, 0.95)
            displayNode.SetHandlesInteractive(False)
            displayNode.SetTranslationHandleVisibility(False)
            displayNode.SetRotationHandleVisibility(False)
        parameterNode.robotMountPlane = node
        return node

    def _foreheadFrameFromStoredPlane(self, plane_node) -> np.ndarray:
        def _vec(name: str) -> np.ndarray:
            text = str(plane_node.GetAttribute(name) or "")
            parts = [float(part) for part in text.split(",") if part.strip()]
            if len(parts) != 3:
                raise ValueError(
                    _("Propose virtual forehead + base first so the constructed "
                      "forehead axes are stored (not Markups in-plane X/Y).")
                )
            return np.asarray(parts, dtype=float)

        matrix = np.eye(4, dtype=float)
        matrix[:3, 0] = _vec("DENTOBOT.ForeheadX")
        matrix[:3, 1] = _vec("DENTOBOT.ForeheadY")
        matrix[:3, 2] = _vec("DENTOBOT.ForeheadZ")
        matrix[:3, 3] = _vec("DENTOBOT.ForeheadOriginMm")
        return matrix

    def dumpForeheadRelativeSeating(self, parameterNode) -> dict[str, object]:
        from dentobot_workflow.virtual_forehead_mount import forehead_relative_seating

        plane = parameterNode.robotMountPlane
        if plane is None or not self.isRobotMountPlaneNode(plane):
            raise ValueError(_("Propose virtual forehead + base first."))
        base = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base):
            raise ValueError(_("Load the robot and propose a virtual forehead first."))
        world = vtk.vtkMatrix4x4()
        base.GetMatrixTransformToWorld(world)
        seating = forehead_relative_seating(
            self._foreheadFrameFromStoredPlane(plane),
            self._numpyFromVtkMatrix(world),
        )
        joints = (
            float(parameterNode.robotJoint1Deg),
            float(parameterNode.robotJoint2Mm),
            float(parameterNode.robotJoint3Deg),
            float(parameterNode.robotJoint4Mm),
            float(parameterNode.robotJoint5Deg),
            float(parameterNode.robotJoint6Deg),
        )
        seating["joints"] = joints
        seating["copyLine"] = (
            f"{seating['copyLine']} joints={joints[0]:.4f},{joints[1]:.4f},"
            f"{joints[2]:.4f},{joints[3]:.4f},{joints[4]:.4f},{joints[5]:.4f}"
        )
        return seating

    def createOrUpdateIndependentForeheadProxy(self, parameterNode, plane) -> vtkMRMLModelNode:
        width = float(parameterNode.step6ForeheadProxyWidthMm)
        height = float(parameterNode.step6ForeheadProxyHeightMm)
        depth = float(parameterNode.step6ForeheadProxyDepthMm)
        offset = float(parameterNode.step6ForeheadProxyOffsetMm)
        if not all(math.isfinite(value) and value > 0.0 for value in (width, height, depth)):
            raise ValueError(_("Forehead-proxy width, height, and depth must be positive."))
        existing = self.step6ForeheadProxyNodes()
        selected = parameterNode.robotForeheadProxyModel
        if selected is not None and selected not in existing:
            raise ValueError(_("The selected forehead proxy is not owned by Step 6."))
        if len(existing) > 1:
            raise ValueError(_("Multiple Step 6 forehead proxies are present; remove duplicates before continuing."))
        model = selected or (existing[0] if existing else None)
        origin = np.asarray(plane.origin_mm, dtype=float)
        x_axis = np.asarray(plane.x_hat, dtype=float)
        y_axis = np.asarray(plane.y_hat, dtype=float)
        normal = np.asarray(plane.z_hat, dtype=float)
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
                "vtkMRMLModelNode", "[Step 6] Virtual Forehead Contact Envelope"
            )
        from dentobot_workflow.virtual_forehead_mount import PLACEMENT_AUTHORITY

        model.SetName("[Step 6] Virtual Forehead Contact Envelope")
        model.SetAttribute("DENTOBOT.ModelRole", self.ROBOT_FOREHEAD_PROXY_ROLE)
        model.SetAttribute("DENTOBOT.RegistrationState", "Unregistered")
        model.SetAttribute("DENTOBOT.GeometryState", "Provisional")
        model.SetAttribute("DENTOBOT.IntendedUse", "VisualizationOnly")
        model.SetAttribute("DENTOBOT.ExcludedFromCollision", "true")
        model.SetAttribute("DENTOBOT.RegistrationEvidence", "false")
        model.SetAttribute("DENTOBOT.CoordinateSystem", "SlicerRASmm")
        model.SetAttribute("DENTOBOT.PlacementAuthority", PLACEMENT_AUTHORITY)
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
        return model

    def proposeVirtualForeheadAndBase(self, parameterNode) -> dict[str, object]:
        """Independent virtual-forehead prior then unreviewed Manual Simulation Base."""

        from DENTORobotPlacement import (
            drill_tip_origin_base_m,
            joint_positions_si_from_display,
        )
        from dentobot_workflow.virtual_forehead_mount import (
            DEFAULT_JOINT_DISPLAY,
            PLACEMENT_AUTHORITY,
            VirtualForeheadConfig,
            arch_scale_from_laterals,
            propose_virtual_forehead_plane,
            seat_base_on_forehead,
            slide_base_for_tcp_target,
        )
        from dentobot_workflow.virtual_open_mouth_articulator import transform_point

        pose = self.evaluateCaseFoundationEligibility(parameterNode)["pose"]
        if not pose["eligible"]:
            raise ValueError(str(pose["message"]))
        if self.isRos2MotionControlActive(parameterNode.robotBaseTransform):
            raise ValueError(_("Disconnect ROS before proposing a virtual forehead base."))
        snapshot = self.buildCaseFoundationSnapshot(parameterNode)
        fingerprint = str(snapshot.planning_pose_fingerprint)
        proposal = self.proposeCaseFoundationArticulatorInputs(parameterNode)
        frame = proposal["dentalFrame"]
        laterals = (proposal["lateralLeftMm"], proposal["lateralRightMm"])
        scale = 1.0
        if laterals[0] is not None and laterals[1] is not None:
            scale = arch_scale_from_laterals(laterals[0], laterals[1])
        transform = parameterNode.step6CaseJawTransform
        lower_closed = np.asarray(proposal["lowerIncisorMm"], dtype=float)
        target = lower_closed
        if self.isStep6CaseJawTransformNode(transform):
            world = vtk.vtkMatrix4x4()
            transform.GetMatrixTransformToWorld(world)
            target = transform_point(self._numpyFromVtkMatrix(world), lower_closed)
        config = VirtualForeheadConfig(
            patch_width_mm=float(parameterNode.step6ForeheadProxyWidthMm),
            patch_height_mm=float(parameterNode.step6ForeheadProxyHeightMm),
            patch_depth_mm=float(parameterNode.step6ForeheadProxyDepthMm),
        )
        plane = propose_virtual_forehead_plane(
            frame,
            arch_scale=scale,
            volume_ras_bounds=self._volumeRasBounds6(parameterNode.inputVolume),
            config=config,
        )
        self._applyIndependentForeheadMountPlane(parameterNode, plane, fingerprint)
        proxy = self.createOrUpdateIndependentForeheadProxy(parameterNode, plane)
        proxy.SetAttribute("DENTOBOT.CaseFoundationFingerprint", fingerprint)
        joints_si = joint_positions_si_from_display(*DEFAULT_JOINT_DISPLAY)
        tcp_base = np.array([0.0, 0.0, 0.0], dtype=float)
        try:
            urdf_path, package_root = self.robotDescriptionPaths()
            tcp_base_m = drill_tip_origin_base_m(joints_si, urdf_path, package_root)
            tcp_base = np.asarray(tcp_base_m, dtype=float) * 1000.0
        except (OSError, RuntimeError, ValueError):
            tcp_base = np.array([0.0, -80.0, 40.0], dtype=float)
        matrix = seat_base_on_forehead(plane, config=config)
        unslid_tcp = (matrix @ np.append(tcp_base, 1.0))[:3]
        unslid_error = float(np.linalg.norm(unslid_tcp - np.asarray(target, dtype=float)))
        slid = {
            "errorMm": unslid_error,
            "slideUMm": 0.0,
            "slideVMm": 0.0,
            "yawDeg": 0.0,
            "matrix_world_ras": matrix,
            "tcpSlideApplied": False,
        }
        if config.apply_tcp_slide_on_propose:
            candidate = slide_base_for_tcp_target(
                plane, tcp_base, target, config=config
            )
            if float(candidate["errorMm"]) <= 80.0:
                matrix = candidate["matrix_world_ras"]
                slid = {
                    **candidate,
                    "tcpSlideApplied": True,
                }
        base = self.ensureRobotBaseTransform(parameterNode.robotBaseTransform)
        parameterNode.robotBaseTransform = base
        if not self.robotModelNodes():
            base, _models = self.createOrUpdateRobotPlacement(base, joints_si)
            parameterNode.robotBaseTransform = base
        parameterNode.robotJoint1Deg = DEFAULT_JOINT_DISPLAY[0]
        parameterNode.robotJoint2Mm = DEFAULT_JOINT_DISPLAY[1]
        parameterNode.robotJoint3Deg = DEFAULT_JOINT_DISPLAY[2]
        parameterNode.robotJoint4Mm = DEFAULT_JOINT_DISPLAY[3]
        parameterNode.robotJoint5Deg = DEFAULT_JOINT_DISPLAY[4]
        parameterNode.robotJoint6Deg = DEFAULT_JOINT_DISPLAY[5]
        self.updateRobotJointPoses(joints_si)
        for model in self.robotModelNodes():
            display = model.GetDisplayNode() if model else None
            if display:
                display.SetVisibility(True)
                display.SetOpacity(1.0)
        base.SetAndObserveTransformNodeID(None)
        base.SetMatrixTransformToParent(self._vtkFromNumpyMatrix(matrix))
        base.SetAttribute(
            self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
            self.ROBOT_BASE_VIRTUAL_FOREHEAD_AUTHORITY,
        )
        base.SetAttribute("DENTOBOT.CaseFoundationFingerprint", fingerprint)
        base.SetAttribute("DENTOBOT.VirtualForeheadPrior", "1")
        base.SetAttribute(
            "DENTOBOT.PlacementWarning",
            "Virtual forehead prior (visualization only). Review and lock "
            "the Manual Simulation Base; not physical mount truth.",
        )
        parameterNode.robotBaseMountLocked = False
        parameterNode.step6BasePlacementStatus = BasePlacementStatus.UNLOCKED.value
        parameterNode.step6BasePlacementSource = "virtual-forehead-prior"
        self._applyRobotBaseMountInteractionState(parameterNode, False)
        self.invalidateStep6TaskConfirmation(
            parameterNode,
            _("Virtual forehead prior proposed a new unreviewed base."),
        )
        summary = {
            "placementAuthority": PLACEMENT_AUTHORITY,
            "hingeEligible": True,
            "originMm": plane.origin_mm.tolist(),
            "pushedForFov": plane.pushed_for_fov,
            "slideUMm": float(slid["slideUMm"]),
            "slideVMm": float(slid["slideVMm"]),
            "yawDeg": float(slid["yawDeg"]),
            "tcpErrorMm": slid["errorMm"],
            "tcpSlideApplied": bool(slid.get("tcpSlideApplied", False)),
            "tcpAimMm": np.asarray(target, dtype=float).tolist(),
            "archScale": plane.arch_scale,
            "caseFoundationFingerprint": fingerprint,
        }
        return summary


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
            "collision_audit": "step6CollisionAuditOpacity",
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
        elif key == "masks":
            for segmentation in (
                parameterNode.teethSegmentation,
                parameterNode.step6FixedUpperAnatomy,
                parameterNode.step6MovingLowerAnatomy,
            ):
                display = segmentation.GetDisplayNode() if segmentation else None
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
        elif key == "trajectory":
            if parameterNode.trajectoryLine:
                display = parameterNode.trajectoryLine.GetDisplayNode()
                if display:
                    displays.append(display)
            # Include the transient TCP path generated from the actual phase
            # waypoints under the same trajectory visibility/opacity control.
            # It is display-only and never participates in case lineage or
            # MoveIt collision synchronization.
            displays.extend(
                node.GetDisplayNode()
                for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
                if node.GetAttribute("DENTOBOT.Step6PhasePlanPath") == "true"
                and node.GetDisplayNode()
            )
        elif key == "forehead_proxy" and parameterNode.robotForeheadProxyModel:
            display = parameterNode.robotForeheadProxyModel.GetDisplayNode()
            if display:
                displays.append(display)
        elif key == "collision_audit":
            displays.extend(
                node.GetDisplayNode()
                for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
                if node.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true"
                and node.GetDisplayNode()
            )
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
        baseTransform.SetAttribute(
            self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
            self.ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY,
        )
        baseTransform.SetAttribute(
            "DENTOBOT.PlacementWarning",
            "Quarantined circular mount-plane snap; manual review and repositioning required.",
        )
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
        baseTransform.SetAttribute(
            self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
            self.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
        )
        baseTransform.SetAttribute("DENTOBOT.PlacementWarning", None)
        return nudged
