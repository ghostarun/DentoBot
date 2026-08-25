"""Extracted Step 6 case and phantom preparation methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class Step6SceneLogicMixin:
    @staticmethod
    def draftPhantomPaths() -> dict[str, Path]:
        """Resolve the local, non-patient BodyParts3D draft phantom files."""

        relativeRoot = Path("phantoms") / "bodyparts3d"
        candidates: list[Path] = []
        explicitRoot = os.environ.get("DENTOBOT_PHANTOM_ROOT", "").strip()
        if explicitRoot:
            candidates.append(Path(explicitRoot))
        candidates.append(Path("/workspace/data") / relativeRoot)
        workspaceRoot = os.environ.get("DENTOBOT_WORKSPACE_ROOT", "").strip()
        if workspaceRoot:
            candidates.append(Path(workspaceRoot) / "data" / relativeRoot)
        moduleDirectory = DENTOWORKFLOW_MODULE_DIRECTORY
        candidates.extend(
            ancestor / "data" / relativeRoot for ancestor in moduleDirectory.parents
        )
        filenames = {
            "Neurocranium": "neurocranium.stl",
            "Maxilla": "maxilla.stl",
            "Mandible": "mandible.stl",
        }
        for root in candidates:
            resolved = {name: root / filename for name, filename in filenames.items()}
            if all(path.is_file() for path in resolved.values()):
                return resolved
        raise RuntimeError(
            _(
                "The draft BodyParts3D phantom is unavailable. Restore "
                "data/phantoms/bodyparts3d or set DENTOBOT_PHANTOM_ROOT."
            )
        )

    @classmethod
    def draftPhantomModelNodes(cls) -> list[vtkMRMLModelNode]:
        return [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
            if node.GetAttribute("DENTOBOT.ModelRole")
            == cls.DRAFT_PHANTOM_MODEL_ROLE
        ]

    @classmethod
    def isDraftJawLandmarksNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsFiducialNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == cls.DRAFT_JAW_LANDMARKS_ROLE
        )

    @classmethod
    def isDraftJawTransformNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLLinearTransformNode")
            and node.GetAttribute("DENTOBOT.TransformRole")
            == cls.DRAFT_JAW_TRANSFORM_ROLE
        )

    @classmethod
    def isStep6CaseJawLandmarksNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsFiducialNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == cls.STEP6_CASE_JAW_LANDMARKS_ROLE
        )

    @classmethod
    def isStep6CaseJawTransformNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLLinearTransformNode")
            and node.GetAttribute("DENTOBOT.TransformRole")
            == cls.STEP6_CASE_JAW_TRANSFORM_ROLE
        )

    @classmethod
    def isStep6OpenedLowerJawModelNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == cls.STEP6_OPENED_LOWER_JAW_MODEL_ROLE
        )

    @classmethod
    def isStep6OpenedTargetGeometryModelNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLModelNode")
            and node.GetAttribute("DENTOBOT.ModelRole")
            == cls.STEP6_OPENED_TARGET_GEOMETRY_MODEL_ROLE
        )

    @classmethod
    def isStep6OpenedTrajectoryNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLMarkupsLineNode")
            and node.GetAttribute("DENTOBOT.MarkupsRole")
            == cls.STEP6_OPENED_TRAJECTORY_ROLE
        )

    @classmethod
    def isDraftPhantomWorkspaceTransformNode(cls, node) -> bool:
        return bool(
            node
            and node.IsA("vtkMRMLLinearTransformNode")
            and node.GetAttribute("DENTOBOT.TransformRole")
            == cls.DRAFT_PHANTOM_WORKSPACE_ROLE
        )

    @classmethod
    def draftPhantomWorkspaceTransformNodes(cls) -> list[vtkMRMLLinearTransformNode]:
        return [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode")
            if node.GetAttribute("DENTOBOT.TransformRole")
            == cls.DRAFT_PHANTOM_WORKSPACE_ROLE
        ]

    @staticmethod
    def _modelRasBounds(model: vtkMRMLModelNode) -> list[float]:
        bounds = [0.0] * 6
        model.GetRASBounds(bounds)
        return bounds

    @staticmethod
    def combinedRasBounds(boundsList: list[list[float]]) -> tuple[float, ...] | None:
        return combine_ras_bounds(boundsList)

    def step6ResearchWorkspaceRasBounds(
        self,
        robotModels: list[vtkMRMLModelNode],
        phantomModels: list[vtkMRMLModelNode],
    ) -> tuple[float, ...] | None:
        boundsList = [
            self._modelRasBounds(model)
            for model in [*robotModels, *phantomModels]
        ]
        return self.combinedRasBounds(boundsList)

    def _validateSingleStep6PhantomPlacement(
        self,
        resolvedModels: dict[str, vtkMRMLModelNode],
        workspaceTransform: vtkMRMLLinearTransformNode | None,
    ) -> None:
        reuseModelIds = {model.GetID() for model in resolvedModels.values()}
        extraModels = [
            node
            for node in self.draftPhantomModelNodes()
            if node.GetID() not in reuseModelIds
        ]
        if extraModels:
            raise ValueError(
                _(
                    "Only one draft phantom set is allowed in Step 6. Delete the "
                    "existing phantom before loading another."
                )
            )
        for part in (
            self.DRAFT_PHANTOM_SKULL_PART,
            self.DRAFT_PHANTOM_MAXILLA_PART,
            self.DRAFT_PHANTOM_MANDIBLE_PART,
        ):
            partNodes = [
                node
                for node in self.draftPhantomModelNodes()
                if node.GetAttribute("DENTOBOT.PhantomPart") == part
            ]
            if len(partNodes) > 1:
                raise ValueError(
                    _(
                        "Multiple draft phantom %1 meshes are present. Delete the "
                        "duplicate phantom before continuing."
                    ).replace("%1", part)
                )
        reuseWorkspaceId = workspaceTransform.GetID() if workspaceTransform else ""
        extraWorkspace = [
            node
            for node in self.draftPhantomWorkspaceTransformNodes()
            if node.GetID() != reuseWorkspaceId
        ]
        if extraWorkspace:
            raise ValueError(
                _(
                    "Multiple draft phantom workspace transforms are present. "
                    "Delete the existing phantom before loading another."
                )
            )

    def _validateSingleStep6RobotPlacement(
        self,
        baseTransform: vtkMRMLLinearTransformNode | None,
        linkModels: list[vtkMRMLModelNode],
        linkTransforms: list[vtkMRMLLinearTransformNode],
    ) -> None:
        reuseModelIds = {model.GetID() for model in linkModels}
        extraModels = [
            node for node in self.robotModelNodes() if node.GetID() not in reuseModelIds
        ]
        if extraModels:
            raise ValueError(
                _(
                    "Only one robot placement set is allowed in Step 6. Delete the "
                    "existing robot setup before loading another."
                )
            )
        linkNames = {
            node.GetAttribute("DENTOBOT.RobotLinkName")
            for node in self.robotModelNodes()
        }
        for linkName in linkNames:
            if not linkName:
                continue
            matching = [
                node
                for node in self.robotModelNodes()
                if node.GetAttribute("DENTOBOT.RobotLinkName") == linkName
            ]
            if len(matching) > 1:
                raise ValueError(
                    _(
                        "Multiple robot link meshes are present for %1. Delete the "
                        "duplicate robot setup before continuing."
                    ).replace("%1", linkName)
                )
        reuseTransformIds = {node.GetID() for node in linkTransforms}
        extraTransforms = [
            node
            for node in self.robotLinkTransformNodes()
            if node.GetID() not in reuseTransformIds
        ]
        if extraTransforms:
            raise ValueError(
                _(
                    "Only one robot placement set is allowed in Step 6. Delete the "
                    "existing robot setup before loading another."
                )
            )
        baseNodes = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLLinearTransformNode")
            if node.GetAttribute("DENTOBOT.TransformRole") == self.ROBOT_BASE_ROLE
        ]
        reuseBaseId = baseTransform.GetID() if baseTransform else ""
        extraBases = [node for node in baseNodes if node.GetID() != reuseBaseId]
        if extraBases:
            raise ValueError(
                _(
                    "Only one robot base transform is allowed in Step 6. Delete "
                    "the existing robot setup before loading another."
                )
            )

    def ensureDraftPhantomWorkspaceTransform(
        self,
        transform: vtkMRMLLinearTransformNode | None,
    ) -> vtkMRMLLinearTransformNode:
        if transform and not self.isDraftPhantomWorkspaceTransformNode(transform):
            raise ValueError(_("Select the Step 6 draft phantom workspace transform."))
        transform = transform or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode",
            "[Step 6] Draft Phantom Workspace",
        )
        transform.SetName("[Step 6] Draft Phantom Workspace")
        transform.SetAttribute(
            "DENTOBOT.TransformRole",
            self.DRAFT_PHANTOM_WORKSPACE_ROLE,
        )
        transform.SetAttribute("DENTOBOT.Status", "DisposableDesignCheck")
        transform.SetAttribute("DENTOBOT.CoordinateConvention", "WorldRASmm")
        transform.CreateDefaultDisplayNodes()
        display = transform.GetDisplayNode()
        if display:
            display.SetVisibility(False)
            display.SetEditorVisibility(False)
        return transform

    def _parentDraftPhantomModelsToWorkspace(
        self,
        workspaceTransform: vtkMRMLLinearTransformNode,
        models: list[vtkMRMLModelNode],
    ) -> None:
        workspaceId = workspaceTransform.GetID()
        for model in models:
            part = model.GetAttribute("DENTOBOT.PhantomPart")
            if part == self.DRAFT_PHANTOM_MANDIBLE_PART:
                jawTransform = model.GetParentTransformNode()
                if jawTransform and self.isDraftJawTransformNode(jawTransform):
                    jawTransform.SetAndObserveTransformNodeID(workspaceId)
                else:
                    model.SetAndObserveTransformNodeID(workspaceId)
            elif part in (
                self.DRAFT_PHANTOM_SKULL_PART,
                self.DRAFT_PHANTOM_MAXILLA_PART,
            ):
                model.SetAndObserveTransformNodeID(workspaceId)

    def _alignDraftPhantomWorkspaceTransform(
        self,
        workspaceTransform: vtkMRMLLinearTransformNode,
        nativeCenterRas: np.ndarray,
    ) -> None:
        targetCenter = np.asarray(self.STEP_6_RESEARCH_PHANTOM_CENTER_RAS, dtype=float)
        translation = targetCenter - nativeCenterRas
        matrix = np.eye(4, dtype=float)
        matrix[:3, 3] = translation
        workspaceTransform.SetAndObserveTransformNodeID(None)
        workspaceTransform.SetMatrixTransformToParent(self._vtkFromNumpyMatrix(matrix))
        workspaceTransform.SetAttribute("DENTOBOT.WorkspaceAligned", "1")

    def draftPhantomWorkspaceTransformForModel(
        self,
        model: vtkMRMLModelNode | None,
    ) -> vtkMRMLLinearTransformNode | None:
        if not model:
            return None
        parent = model.GetParentTransformNode()
        if parent and self.isDraftPhantomWorkspaceTransformNode(parent):
            return parent
        if parent and self.isDraftJawTransformNode(parent):
            workspace = parent.GetParentTransformNode()
            if workspace and self.isDraftPhantomWorkspaceTransformNode(workspace):
                return workspace
        workspaceNodes = self.draftPhantomWorkspaceTransformNodes()
        return workspaceNodes[0] if len(workspaceNodes) == 1 else None

    def positionRobotBaseNearResearchPhantom(
        self,
        baseTransform: vtkMRMLLinearTransformNode,
        phantomModels: list[vtkMRMLModelNode],
    ) -> bool:
        if not self.isRobotBaseTransformNode(baseTransform) or not phantomModels:
            return False
        worldMatrix = vtk.vtkMatrix4x4()
        baseTransform.GetMatrixTransformToWorld(worldMatrix)
        currentOrigin = np.array(
            [worldMatrix.GetElement(axis, 3) for axis in range(3)],
            dtype=float,
        )
        if np.linalg.norm(currentOrigin) > 5.0:
            return False
        phantomBounds = self.combinedRasBounds(
            [self._modelRasBounds(model) for model in phantomModels]
        )
        if phantomBounds is None:
            return False
        center = np.array(
            (
                (phantomBounds[0] + phantomBounds[1]) * 0.5,
                (phantomBounds[2] + phantomBounds[3]) * 0.5,
                (phantomBounds[4] + phantomBounds[5]) * 0.5,
            ),
            dtype=float,
        )
        suggestedOrigin = np.array(
            (
                center[0],
                center[1] + 180.0,
                max(80.0, center[2] - 80.0),
            ),
            dtype=float,
        )
        matrix = np.eye(4, dtype=float)
        matrix[:3, 3] = suggestedOrigin
        baseTransform.SetAndObserveTransformNodeID(None)
        baseTransform.SetMatrixTransformToParent(self._vtkFromNumpyMatrix(matrix))
        return True

    def createOrUpdateDraftPhantom(
        self,
    ) -> tuple[vtkMRMLModelNode, vtkMRMLModelNode, list[vtkMRMLModelNode]]:
        """Load/reuse the aligned generic skull, maxilla, and mandible meshes."""

        paths = self.draftPhantomPaths()
        nodes = self.draftPhantomModelNodes()
        workspaceNodes = self.draftPhantomWorkspaceTransformNodes()
        workspaceTransform = workspaceNodes[0] if workspaceNodes else None
        colors = {
            self.DRAFT_PHANTOM_SKULL_PART: (0.84, 0.80, 0.68),
            self.DRAFT_PHANTOM_MAXILLA_PART: (0.95, 0.88, 0.72),
            self.DRAFT_PHANTOM_MANDIBLE_PART: (0.92, 0.66, 0.42),
        }
        resolved: dict[str, vtkMRMLModelNode] = {}
        for part, path in paths.items():
            model = next(
                (
                    node
                    for node in nodes
                    if node.GetAttribute("DENTOBOT.PhantomPart") == part
                ),
                None,
            )
            if not model:
                model = slicer.modules.models.logic().AddModel(
                    str(path),
                    slicer.vtkMRMLStorageNode.CoordinateSystemRAS,
                )
            if not model or not model.GetPolyData() or not model.GetPolyData().GetNumberOfPoints():
                raise RuntimeError(
                    _("Slicer could not load the draft phantom mesh %1.").replace(
                        "%1", str(path)
                    )
                )
            model.SetName(f"[Step 6] Draft Phantom {part}")
            model.SetAttribute("DENTOBOT.ModelRole", self.DRAFT_PHANTOM_MODEL_ROLE)
            model.SetAttribute("DENTOBOT.PhantomPart", part)
            model.SetAttribute("DENTOBOT.Status", "DisposableDesignCheck")
            model.SetAttribute("DENTOBOT.SourceMeshPath", str(path))
            model.CreateDefaultDisplayNodes()
            display = model.GetDisplayNode()
            if display:
                display.SetVisibility(True)
                display.SetOpacity(0.82 if part != self.DRAFT_PHANTOM_MANDIBLE_PART else 0.92)
                display.SetColor(*colors[part])
            resolved[part] = model

        self._validateSingleStep6PhantomPlacement(resolved, workspaceTransform)
        workspaceTransform = self.ensureDraftPhantomWorkspaceTransform(
            workspaceTransform
        )
        if workspaceTransform.GetAttribute("DENTOBOT.WorkspaceAligned") != "1":
            for model in resolved.values():
                parent = model.GetParentTransformNode()
                if parent and self.isDraftJawTransformNode(parent):
                    if parent.GetParentTransformNode():
                        parent.SetAndObserveTransformNodeID(None)
                    model.SetAndObserveTransformNodeID(None)
                elif parent:
                    model.SetAndObserveTransformNodeID(None)
            nativeBounds = self.combinedRasBounds(
                [self._modelRasBounds(model) for model in resolved.values()]
            )
            if nativeBounds is None:
                raise RuntimeError(_("The draft phantom meshes have no finite bounds."))
            nativeCenter = np.array(
                (
                    (nativeBounds[0] + nativeBounds[1]) * 0.5,
                    (nativeBounds[2] + nativeBounds[3]) * 0.5,
                    (nativeBounds[4] + nativeBounds[5]) * 0.5,
                ),
                dtype=float,
            )
            self._parentDraftPhantomModelsToWorkspace(
                workspaceTransform,
                list(resolved.values()),
            )
            self._alignDraftPhantomWorkspaceTransform(
                workspaceTransform,
                nativeCenter,
            )
        else:
            self._parentDraftPhantomModelsToWorkspace(
                workspaceTransform,
                list(resolved.values()),
            )
        return (
            resolved[self.DRAFT_PHANTOM_SKULL_PART],
            resolved[self.DRAFT_PHANTOM_MANDIBLE_PART],
            list(resolved.values()),
        )

    @classmethod
    def draftPhantomExampleLandmarksNativeRas(cls) -> tuple[np.ndarray, ...]:
        """Anatomically approximate BodyParts3D-native landmark examples for tests."""

        return (
            np.array([-45.0, -105.0, 1500.0], dtype=float),
            np.array([45.0, -105.0, 1500.0], dtype=float),
            np.array([0.0, -178.0, 1472.0], dtype=float),
            np.array([0.0, -175.0, 1468.0], dtype=float),
        )

    @classmethod
    def draftPhantomExampleForeheadPlaneNativeRas(cls) -> np.ndarray:
        return np.array([0.0, -165.0, 1590.0], dtype=float)

    def draftPhantomNativePointToWorldRas(
        self,
        nativePointRas: np.ndarray,
        workspaceTransform: vtkMRMLLinearTransformNode | None = None,
    ) -> np.ndarray:
        nativePointRas = np.asarray(nativePointRas, dtype=float)
        if workspaceTransform is None:
            workspaceNodes = self.draftPhantomWorkspaceTransformNodes()
            workspaceTransform = (
                workspaceNodes[0] if len(workspaceNodes) == 1 else None
            )
        if (
            not workspaceTransform
            or workspaceTransform.GetAttribute("DENTOBOT.WorkspaceAligned") != "1"
        ):
            return nativePointRas
        worldMatrix = vtk.vtkMatrix4x4()
        workspaceTransform.GetMatrixTransformToWorld(worldMatrix)
        transformed = [0.0, 0.0, 0.0, 0.0]
        worldMatrix.MultiplyPoint(
            (
                float(nativePointRas[0]),
                float(nativePointRas[1]),
                float(nativePointRas[2]),
                1.0,
            ),
            transformed,
        )
        return np.asarray(transformed[:3], dtype=float)

    def draftPhantomExampleLandmarksWorldRas(
        self,
    ) -> tuple[np.ndarray, ...]:
        return tuple(
            self.draftPhantomNativePointToWorldRas(point)
            for point in self.draftPhantomExampleLandmarksNativeRas()
        )

    @classmethod
    def draftJawLandmarkPlacementHints(cls) -> tuple[str, ...]:
        return cls.DRAFT_JAW_LANDMARK_LABELS

    @classmethod
    def draftJawLandmarkButtonLabels(cls) -> tuple[str, ...]:
        return (
            _("Place first landmark (Left TMJ)"),
            _("Place second landmark (Right TMJ — first landmark is Left TMJ)"),
            _("Place third landmark (Upper incisor)"),
            _("Place fourth landmark (Lower incisor)"),
        )

    def ensureStep6CaseJawLandmarksNode(
        self,
        node: vtkMRMLMarkupsFiducialNode | None,
    ) -> vtkMRMLMarkupsFiducialNode:
        if node and not self.isStep6CaseJawLandmarksNode(node):
            raise ValueError(_("Select the Step 6 case jaw landmark set."))
        node = node or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode",
            "[Step 6.0A] Case Jaw Landmarks",
        )
        node.SetName("[Step 6.0A] Case Jaw Landmarks")
        if hasattr(node, "SetMaximumNumberOfControlPoints"):
            node.SetMaximumNumberOfControlPoints(len(self.DRAFT_JAW_LANDMARK_LABELS))
        node.SetLocked(False)
        node.SetSelectable(True)
        node.SetAttribute("DENTOBOT.MarkupsRole", self.STEP6_CASE_JAW_LANDMARKS_ROLE)
        node.SetAttribute("DENTOBOT.SchemaVersion", self.STEP6_CASE_JAW_SCHEMA_VERSION)
        node.SetAttribute("DENTOBOT.Status", "CasePlanningInput")
        node.SetAttribute(
            "DENTOBOT.PlacementOrder",
            "LeftTMJ,RightTMJ,UpperCentralIncisor,LowerCentralIncisor",
        )
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        if display:
            display.SetVisibility(True)
            display.SetVisibility2D(True)
            display.SetVisibility3D(True)
            display.SetColor(0.10, 0.85, 1.00)
            display.SetSelectedColor(1.0, 0.55, 0.10)
            display.SetPointLabelsVisibility(True)
            display.SetGlyphScale(1.4)
        return node

    def getStep6CaseJawLandmarkSummary(
        self,
        node: vtkMRMLMarkupsFiducialNode,
    ) -> dict:
        if not self.isStep6CaseJawLandmarksNode(node):
            raise ValueError(_("Create the Step 6 case jaw landmarks first."))
        expectedCount = len(self.DRAFT_JAW_LANDMARK_LABELS)
        pointCount = node.GetNumberOfDefinedControlPoints()
        if pointCount < 0 or pointCount > expectedCount:
            raise ValueError(_("The case jaw landmark markup has an invalid point count."))
        for index in range(min(pointCount, expectedCount)):
            desiredLabel = self.DRAFT_JAW_LANDMARK_LABELS[index]
            if node.GetNthControlPointLabel(index) != desiredLabel:
                node.SetNthControlPointLabel(index, desiredLabel)
        return {
            "definedPointCount": pointCount,
            "isComplete": pointCount == expectedCount,
        }

    @staticmethod
    def startStep6CaseJawLandmarkPlacement(
        landmarksNode: vtkMRMLMarkupsFiducialNode,
    ) -> None:
        if not DENTOWorkflowLogic.isStep6CaseJawLandmarksNode(landmarksNode):
            raise ValueError(_("Create the Step 6 case jaw landmarks first."))
        if landmarksNode.GetNumberOfDefinedControlPoints() >= 4:
            raise ValueError(_("All four case jaw landmarks are already placed."))
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsFiducialNode"
        )
        selectionNode.SetActivePlaceNodeID(landmarksNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(0)
        selectionNode.SetActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(landmarksNode.GetID())
        if (
            selectionNode.GetActivePlaceNodeID() != landmarksNode.GetID()
            or selectionNode.GetActivePlaceNodeClassName()
            != "vtkMRMLMarkupsFiducialNode"
            or not selectionNode.GetActivePlaceNodePlacementValid()
        ):
            DENTOWorkflowLogic.stopTrajectoryPlacement()
            raise RuntimeError(
                _("Slicer could not activate case jaw landmark placement.")
            )

    def step6CaseJawLandmarkPositions(
        self,
        node: vtkMRMLMarkupsFiducialNode,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        summary = self.getStep6CaseJawLandmarkSummary(node)
        if not summary["isComplete"]:
            raise ValueError(
                _(
                    "Place exactly four case landmarks in order: left TMJ, right "
                    "TMJ, upper central incisor, lower central incisor."
                )
            )
        positions = []
        for index in range(4):
            point = [0.0, 0.0, 0.0]
            node.GetNthControlPointPositionWorld(index, point)
            positions.append(np.asarray(point, dtype=float))
        return tuple(positions)

    def getDraftJawLandmarkSummary(
        self,
        node: vtkMRMLMarkupsFiducialNode,
    ) -> dict:
        if not self.isDraftJawLandmarksNode(node):
            raise ValueError(_("Create the Step 6 draft jaw landmarks first."))
        expectedCount = len(self.DRAFT_JAW_LANDMARK_LABELS)
        pointCount = node.GetNumberOfDefinedControlPoints()
        if pointCount < 0 or pointCount > expectedCount:
            raise ValueError(_("The draft jaw landmark markup has an invalid point count."))
        self.labelDraftJawLandmarks(node, pointCount)
        return {
            "definedPointCount": pointCount,
            "isComplete": pointCount == expectedCount,
        }

    def labelDraftJawLandmarks(
        self,
        node: vtkMRMLMarkupsFiducialNode,
        pointCount: int | None = None,
    ) -> None:
        if not self.isDraftJawLandmarksNode(node):
            raise ValueError(_("Create the Step 6 draft jaw landmarks first."))
        if pointCount is None:
            pointCount = node.GetNumberOfDefinedControlPoints()
        for index in range(min(pointCount, len(self.DRAFT_JAW_LANDMARK_LABELS))):
            desiredLabel = self.DRAFT_JAW_LANDMARK_LABELS[index]
            if node.GetNthControlPointLabel(index) != desiredLabel:
                node.SetNthControlPointLabel(index, desiredLabel)

    def ensureDraftJawLandmarksNode(
        self,
        node: vtkMRMLMarkupsFiducialNode | None,
    ) -> vtkMRMLMarkupsFiducialNode:
        if node and not self.isDraftJawLandmarksNode(node):
            raise ValueError(_("Select the Step 6 draft jaw landmark set."))
        node = node or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode",
            "[Step 6] Draft Jaw Landmarks",
        )
        node.SetName("[Step 6] Draft Jaw Landmarks")
        if hasattr(node, "SetMaximumNumberOfControlPoints"):
            node.SetMaximumNumberOfControlPoints(len(self.DRAFT_JAW_LANDMARK_LABELS))
        node.SetLocked(False)
        node.SetSelectable(True)
        node.SetAttribute("DENTOBOT.MarkupsRole", self.DRAFT_JAW_LANDMARKS_ROLE)
        node.SetAttribute("DENTOBOT.Status", "DisposableDesignCheck")
        node.SetAttribute(
            "DENTOBOT.PlacementOrder",
            "LeftTMJ,RightTMJ,UpperCentralIncisor,LowerCentralIncisor",
        )
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        if display:
            display.SetVisibility(True)
            display.SetVisibility2D(True)
            display.SetVisibility3D(True)
            display.SetColor(0.20, 0.90, 0.95)
            display.SetSelectedColor(1.0, 0.55, 0.10)
            display.SetPointLabelsVisibility(True)
            display.SetGlyphScale(1.4)
        return node

    def clearDraftJawLandmarks(
        self,
        node: vtkMRMLMarkupsFiducialNode,
    ) -> None:
        if not self.isDraftJawLandmarksNode(node):
            raise ValueError(_("Create the Step 6 draft jaw landmarks first."))
        node.RemoveAllControlPoints()

    def createOrResetDraftJawLandmarks(
        self,
        node: vtkMRMLMarkupsFiducialNode | None,
    ) -> vtkMRMLMarkupsFiducialNode:
        node = self.ensureDraftJawLandmarksNode(node)
        self.clearDraftJawLandmarks(node)
        return node

    @staticmethod
    def startDraftJawLandmarkPlacement(
        landmarksNode: vtkMRMLMarkupsFiducialNode,
    ) -> None:
        if not DENTOWorkflowLogic.isDraftJawLandmarksNode(landmarksNode):
            raise ValueError(_("Create the Step 6 draft jaw landmarks first."))
        if landmarksNode.GetNumberOfDefinedControlPoints() >= 4:
            raise ValueError(_("All four draft jaw landmarks are already placed."))
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        if not selectionNode:
            raise RuntimeError(_("Slicer's selection node is unavailable."))
        selectionNode.SetReferenceActivePlaceNodeClassName(
            "vtkMRMLMarkupsFiducialNode"
        )
        selectionNode.SetActivePlaceNodeID(landmarksNode.GetID())
        slicer.modules.markups.logic().StartPlaceMode(0)
        selectionNode.SetActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
        selectionNode.SetActivePlaceNodeID(landmarksNode.GetID())
        if (
            selectionNode.GetActivePlaceNodeID() != landmarksNode.GetID()
            or selectionNode.GetActivePlaceNodeClassName()
            != "vtkMRMLMarkupsFiducialNode"
            or not selectionNode.GetActivePlaceNodePlacementValid()
        ):
            DENTOWorkflowLogic.stopTrajectoryPlacement()
            raise RuntimeError(
                _("Slicer could not activate draft jaw landmark placement.")
            )

    def draftJawLandmarkPositions(
        self,
        node: vtkMRMLMarkupsFiducialNode,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        if not self.isDraftJawLandmarksNode(node):
            raise ValueError(_("Create the Step 6 draft jaw landmarks first."))
        if node.GetNumberOfDefinedControlPoints() != 4:
            raise ValueError(
                _(
                    "Place exactly four landmarks in order: left TMJ, right TMJ, "
                    "upper central incisor, lower central incisor."
                )
            )
        self.labelDraftJawLandmarks(node)
        positions = []
        for index in range(4):
            point = [0.0, 0.0, 0.0]
            node.GetNthControlPointPositionWorld(index, point)
            positions.append(np.asarray(point, dtype=float))
        return tuple(positions)

    def createOrUpdateDraftJawOpening(
        self,
        mandible: vtkMRMLModelNode,
        landmarks: vtkMRMLMarkupsFiducialNode,
        transform: vtkMRMLLinearTransformNode | None,
        gapLine: vtkMRMLMarkupsLineNode | None,
        targetGapMm: float,
    ) -> tuple[vtkMRMLLinearTransformNode, vtkMRMLMarkupsLineNode, dict]:
        if (
            not mandible
            or mandible.GetAttribute("DENTOBOT.PhantomPart")
            != self.DRAFT_PHANTOM_MANDIBLE_PART
        ):
            raise ValueError(_("Load or select the draft BodyParts3D mandible."))
        left, right, upper, lower = self.draftJawLandmarkPositions(landmarks)
        if transform and not self.isDraftJawTransformNode(transform):
            raise ValueError(_("Select the Step 6 draft jaw transform."))
        parent = mandible.GetParentTransformNode()
        workspaceTransform = self.draftPhantomWorkspaceTransformForModel(mandible)
        allowedParents = {transform, workspaceTransform}
        if parent and parent not in allowedParents:
            raise ValueError(
                _("The draft mandible is already under an unrelated transform.")
            )
        angle, matrix, openedLower, gap = solve_hinge_rotation_for_gap(
            left,
            right,
            upper,
            lower,
            float(targetGapMm),
        )
        parentToWorld = None
        if workspaceTransform:
            parentVtk = vtk.vtkMatrix4x4()
            workspaceTransform.GetMatrixTransformToWorld(parentVtk)
            parentToWorld = self._numpyFromVtkMatrix(parentVtk)
        jawMatrixLocal = world_transform_to_parent_local(matrix, parentToWorld)
        transform = transform or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode",
            "[Step 6] Draft TMJ Jaw Opening",
        )
        transform.SetName("[Step 6] Draft TMJ Jaw Opening")
        transform.SetAttribute("DENTOBOT.TransformRole", self.DRAFT_JAW_TRANSFORM_ROLE)
        transform.SetAttribute("DENTOBOT.Status", "DisposableDesignCheck")
        transform.SetAttribute("DENTOBOT.JawMotion", "PureTMJHingeRotation")
        transform.SetAttribute("DENTOBOT.TargetIncisorGapMm", f"{float(targetGapMm):.3f}")
        transform.SetAttribute("DENTOBOT.AchievedIncisorGapMm", f"{gap:.3f}")
        transform.SetAttribute("DENTOBOT.HingeAngleDeg", f"{angle:.3f}")
        workspaceParentId = (
            workspaceTransform.GetID() if workspaceTransform else None
        )
        transform.SetAndObserveTransformNodeID(workspaceParentId)
        transform.SetMatrixTransformToParent(self._vtkFromNumpyMatrix(jawMatrixLocal))
        mandible.SetAndObserveTransformNodeID(transform.GetID())

        if gapLine and (
            not gapLine.IsA("vtkMRMLMarkupsLineNode")
            or gapLine.GetAttribute("DENTOBOT.MarkupsRole")
            != self.DRAFT_JAW_GAP_LINE_ROLE
        ):
            raise ValueError(_("Select the Step 6 draft incisor-gap line."))
        gapLine = gapLine or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            "[Step 6] Draft Incisor Gap",
        )
        gapLine.SetName("[Step 6] Draft Incisor Gap")
        gapLine.RemoveAllControlPoints()
        gapLine.AddControlPointWorld(vtk.vtkVector3d(*upper))
        gapLine.AddControlPointWorld(vtk.vtkVector3d(*openedLower))
        gapLine.SetNthControlPointLabel(0, "Upper incisor")
        gapLine.SetNthControlPointLabel(1, "Opened lower incisor")
        gapLine.SetLocked(True)
        gapLine.SetSelectable(False)
        gapLine.SetAttribute("DENTOBOT.MarkupsRole", self.DRAFT_JAW_GAP_LINE_ROLE)
        gapLine.SetAttribute("DENTOBOT.Status", "DisposableDesignCheck")
        gapLine.CreateDefaultDisplayNodes()
        display = gapLine.GetDisplayNode()
        if display:
            display.SetVisibility(True)
            display.SetVisibility2D(True)
            display.SetVisibility3D(True)
            display.SetColor(0.15, 1.0, 0.25)
            display.SetPointLabelsVisibility(True)
            display.SetPropertiesLabelVisibility(True)
        return transform, gapLine, {
            "angleDeg": angle,
            "gapMm": gap,
            "openedLowerIncisorRas": openedLower,
        }

    def resetDraftJawOpening(
        self,
        mandible: vtkMRMLModelNode | None,
        transform: vtkMRMLLinearTransformNode | None,
        gapLine: vtkMRMLMarkupsLineNode | None,
    ) -> None:
        if self.isDraftJawTransformNode(transform):
            identity = vtk.vtkMatrix4x4()
            identity.Identity()
            transform.SetMatrixTransformToParent(identity)
        if mandible and transform and mandible.GetParentTransformNode() is transform:
            mandible.SetAndObserveTransformNodeID(transform.GetID())
        if gapLine and slicer.mrmlScene.IsNodePresent(gapLine):
            slicer.mrmlScene.RemoveNode(gapLine)

    def step6CaseJawSegmentIds(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> dict[str, tuple[str, ...]]:
        """Classify rigid upper and lower case surfaces from reviewed labels."""
        upper: list[str] = []
        lower: list[str] = []
        upperJaw: list[str] = []
        lowerJaw: list[str] = []
        for record in self.getSegmentationReviewRecords(segmentationNode):
            segmentId = str(record.get("segmentId") or "")
            if not segmentId:
                continue
            category = str(record.get("category") or "")
            if category == "Teeth":
                jaw = dental_jaw_from_fdi(record.get("fdiNumber"))
                if jaw == "upper":
                    upper.append(segmentId)
                elif jaw == "lower":
                    lower.append(segmentId)
                continue
            if category != "Jaws":
                continue
            sourceName = str(record.get("sourceName") or "").strip().lower()
            if "mandible" in sourceName or sourceName.startswith("lower_jaw"):
                lowerJaw.append(segmentId)
            elif "maxilla" in sourceName or sourceName.startswith("upper_jaw"):
                upperJaw.append(segmentId)
        return {
            "upperTeeth": tuple(upper),
            "lowerTeeth": tuple(lower),
            "upperJaw": tuple(upperJaw),
            "lowerJaw": tuple(lowerJaw),
            "upper": tuple(dict.fromkeys((*upper, *upperJaw))),
            "lower": tuple(dict.fromkeys((*lower, *lowerJaw))),
        }

    def _step6CaseJawGeometryFingerprint(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentIds: tuple[str, ...],
    ) -> str:
        segmentation = segmentationNode.GetSegmentation()
        if not segmentation:
            return ""
        representationName = (
            slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName()
        )
        records = []
        for segmentId in segmentIds:
            segment = segmentation.GetSegment(segmentId)
            polydata = (
                segment.GetRepresentation(representationName)
                if segment
                else None
            )
            if not polydata:
                records.append({"id": segmentId, "missing": True})
                continue
            bounds = polydata.GetBounds()
            records.append(
                {
                    "id": segmentId,
                    "points": int(polydata.GetNumberOfPoints()),
                    "cells": int(polydata.GetNumberOfCells()),
                    "bounds": tuple(round(float(value), 6) for value in bounds),
                }
            )
        parentMatrix = vtk.vtkMatrix4x4()
        parentMatrix.Identity()
        parent = segmentationNode.GetParentTransformNode()
        if parent:
            parent.GetMatrixTransformToWorld(parentMatrix)
        return fingerprint(
            {
                "segmentationId": str(segmentationNode.GetID() or ""),
                "parentToWorldRas": tuple(
                    round(float(parentMatrix.GetElement(row, column)), 9)
                    for row in range(4)
                    for column in range(4)
                ),
                "segments": records,
            }
        )

    def _step6CaseJawLandmarksFingerprint(
        self,
        landmarks: vtkMRMLMarkupsFiducialNode,
    ) -> str:
        positions = self.step6CaseJawLandmarkPositions(landmarks)
        return fingerprint(
            {
                "role": self.STEP6_CASE_JAW_LANDMARKS_ROLE,
                "pointsWorldRasMm": tuple(
                    tuple(round(float(value), 9) for value in point)
                    for point in positions
                ),
            }
        )

    def _step6TargetAttachedGeometryFingerprint(self, parameterNode) -> str:
        trajectory = self.getTrajectorySummary(parameterNode.trajectoryLine)
        modelSources = (
            [parameterNode.finalPrintableTemplateModel]
            if parameterNode.finalPrintableTemplateModel
            else [
                parameterNode.draftTemplateSupportModel,
                parameterNode.targetDockingAssemblyModel,
            ]
        )
        modelRecords = []
        for model in modelSources:
            if not model:
                continue
            polydata = model_polydata_in_world(model)
            bounds = polydata.GetBounds() if polydata else (0.0,) * 6
            modelRecords.append(
                {
                    "id": str(model.GetID() or ""),
                    "role": str(model.GetAttribute("DENTOBOT.ModelRole") or ""),
                    "points": int(polydata.GetNumberOfPoints()) if polydata else 0,
                    "cells": int(polydata.GetNumberOfCells()) if polydata else 0,
                    "boundsWorldRasMm": tuple(
                        round(float(value), 6) for value in bounds
                    ),
                }
            )
        return fingerprint(
            {
                "targetSegmentId": str(parameterNode.targetToothSegmentId or ""),
                "targetJaw": self.step6TargetJaw(parameterNode),
                "entryWorldRasMm": tuple(
                    round(float(value), 9)
                    for value in trajectory.get("entryRas", ())
                ),
                "targetWorldRasMm": tuple(
                    round(float(value), 9)
                    for value in trajectory.get("targetRas", ())
                ),
                "models": modelRecords,
            }
        )

    def step6TargetJaw(self, parameterNode) -> str:
        segmentation = parameterNode.teethSegmentation
        targetId = str(parameterNode.targetToothSegmentId or "")
        if not segmentation or not targetId:
            return ""
        for record in self.getTargetToothRecords(segmentation):
            if str(record.get("segmentId") or "") == targetId:
                return dental_jaw_from_fdi(record.get("fdiNumber")) or ""
        return ""

    def step6CaseJawOpeningFreshnessIssues(self, parameterNode) -> list[str]:
        """Return reasons the imported case is not in a current open-mouth pose."""
        if not bool(parameterNode.step6PlanningContextImported):
            return []
        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            return [_("The authoritative dental segmentation is missing.")]
        landmarks = parameterNode.step6CaseJawLandmarks
        if not self.isStep6CaseJawLandmarksNode(landmarks):
            return [_("Place the four Step 6 case jaw landmarks.")]
        try:
            summary = self.getStep6CaseJawLandmarkSummary(landmarks)
        except ValueError as exc:
            return [str(exc)]
        if not summary["isComplete"]:
            return [
                _("Place all four case landmarks: Left TMJ, Right TMJ, upper incisor, lower incisor.")
            ]
        transform = parameterNode.step6CaseJawTransform
        model = parameterNode.step6OpenedLowerJawModel
        if not self.isStep6CaseJawTransformNode(transform):
            return [_("Apply the Step 6 case open-mouth transform.")]
        if not self.isStep6OpenedLowerJawModelNode(model):
            return [_("The derived opened lower-jaw planning surface is missing.")]
        if transform.GetAttribute("DENTOBOT.GeometryState") != "Current":
            return [
                transform.GetAttribute("DENTOBOT.StaleReason")
                or _("Re-apply the Step 6 case open-mouth transform.")
            ]
        if transform.GetParentTransformNode() is not None:
            return [_("The case TMJ transform must remain in world RAS.")]
        left, right, upper, lower = self.step6CaseJawLandmarkPositions(landmarks)
        _angle, expectedMatrix, _openedLower, _gap = solve_hinge_rotation_for_gap(
            left,
            right,
            upper,
            lower,
            float(parameterNode.step6CaseJawTargetGapMm),
        )
        actualVtk = vtk.vtkMatrix4x4()
        transform.GetMatrixTransformToWorld(actualVtk)
        actualMatrix = self._numpyFromVtkMatrix(actualVtk)
        if not np.allclose(actualMatrix, expectedMatrix, atol=1e-6, rtol=0.0):
            return [
                _("The case TMJ transform matrix changed; re-apply the mouth opening.")
            ]
        if model.GetParentTransformNode() is not transform:
            return [_("The opened lower-jaw surface is detached from its TMJ transform.")]
        if self.step6TargetJaw(parameterNode) == "lower":
            if not self.isStep6OpenedTrajectoryNode(
                parameterNode.step6OpenedTrajectoryLine
            ):
                return [_("The opened mandibular Entry-to-Target display is missing.")]
            if parameterNode.finalPrintableTemplateModel and not (
                self.isStep6OpenedTargetGeometryModelNode(
                    parameterNode.step6OpenedTargetGeometryModel
                )
            ):
                return [_("The opened mandibular template display is missing.")]
        sourceId = transform.GetNodeReferenceID("DENTOBOT.SourceSegmentation")
        if sourceId != segmentation.GetID():
            return [_("The open-mouth transform belongs to a different segmentation.")]
        if (
            transform.GetAttribute("DENTOBOT.LandmarksFingerprint")
            != self._step6CaseJawLandmarksFingerprint(landmarks)
        ):
            return [
                _("Case jaw landmarks changed; re-apply the mouth opening.")
            ]
        if transform.GetAttribute("DENTOBOT.TargetSegmentID") != str(
            parameterNode.targetToothSegmentId or ""
        ):
            return [
                _("The selected target changed; re-apply the case mouth opening.")
            ]
        if (
            transform.GetAttribute("DENTOBOT.TargetAttachedGeometryFingerprint")
            != self._step6TargetAttachedGeometryFingerprint(parameterNode)
        ):
            return [
                _("Target trajectory or guide geometry changed; re-apply the mouth opening.")
            ]
        segmentGroups = self.step6CaseJawSegmentIds(segmentation)
        lowerIds = segmentGroups["lower"]
        if not lowerIds:
            return [_("No lower-jaw or mandibular tooth surfaces are available.")]
        expectedFingerprint = self._step6CaseJawGeometryFingerprint(
            segmentation,
            lowerIds,
        )
        if transform.GetAttribute("DENTOBOT.SourceGeometryFingerprint") != expectedFingerprint:
            return [
                _("Lower-jaw segmentation geometry changed; re-apply the mouth opening.")
            ]
        if model.GetAttribute("DENTOBOT.SourceGeometryFingerprint") != expectedFingerprint:
            return [
                _("The opened lower-jaw surface provenance is stale.")
            ]
        requestedGap = float(parameterNode.step6CaseJawTargetGapMm)
        recordedGap = transform.GetAttribute("DENTOBOT.TargetIncisorGapMm")
        try:
            gapMatches = (
                recordedGap is not None
                and abs(float(recordedGap) - requestedGap) <= 1e-6
            )
        except (TypeError, ValueError):
            gapMatches = False
        if not gapMatches:
            return [_("The requested incisor gap changed; re-apply the mouth opening.")]
        return []

    def _restoreStep6CaseLowerJawVisibility(
        self,
        segmentationNode: vtkMRMLSegmentationNode | None,
        model: vtkMRMLModelNode | None,
    ) -> None:
        if not segmentationNode or not model:
            return
        display = segmentationNode.GetDisplayNode()
        if not display:
            return
        try:
            states = json.loads(
                model.GetAttribute("DENTOBOT.SourceSegmentVisibility3DJson") or "{}"
            )
        except (TypeError, json.JSONDecodeError):
            states = {}
        for segmentId, visible in states.items():
            if segmentationNode.GetSegmentation().GetSegment(str(segmentId)):
                display.SetSegmentVisibility3D(str(segmentId), bool(visible))

    def _restoreStep6CaseTargetAttachedVisibility(self, parameterNode) -> None:
        modelProxy = parameterNode.step6OpenedTargetGeometryModel
        if modelProxy:
            try:
                states = json.loads(
                    modelProxy.GetAttribute("DENTOBOT.SourceDisplayVisibilityJson")
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                states = {}
            for nodeId, visible in states.items():
                node = slicer.mrmlScene.GetNodeByID(str(nodeId))
                display = node.GetDisplayNode() if node else None
                if display:
                    display.SetVisibility(bool(visible))
        trajectoryProxy = parameterNode.step6OpenedTrajectoryLine
        if trajectoryProxy:
            try:
                state = json.loads(
                    trajectoryProxy.GetAttribute("DENTOBOT.SourceDisplayVisibilityJson")
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                state = {}
            source = parameterNode.trajectoryLine
            display = source.GetDisplayNode() if source else None
            if display:
                display.SetVisibility(bool(state.get("visible", True)))
                display.SetVisibility2D(bool(state.get("visible2D", True)))
                display.SetVisibility3D(bool(state.get("visible3D", True)))

    def _updateStep6CaseTargetAttachedDisplay(
        self,
        parameterNode,
        transform: vtkMRMLLinearTransformNode,
    ) -> None:
        """Create derived display proxies without moving Steps 0–5 source nodes."""
        if self.step6TargetJaw(parameterNode) != "lower":
            self._restoreStep6CaseTargetAttachedVisibility(parameterNode)
            for node in (
                parameterNode.step6OpenedTargetGeometryModel,
                parameterNode.step6OpenedTrajectoryLine,
            ):
                if node and slicer.mrmlScene.IsNodePresent(node):
                    slicer.mrmlScene.RemoveNode(node)
            parameterNode.step6OpenedTargetGeometryModel = None
            parameterNode.step6OpenedTrajectoryLine = None
            return

        modelSources = (
            [parameterNode.finalPrintableTemplateModel]
            if parameterNode.finalPrintableTemplateModel
            else [
                parameterNode.draftTemplateSupportModel,
                parameterNode.targetDockingAssemblyModel,
            ]
        )
        modelSources = [node for node in modelSources if node is not None]
        surfaces = [model_polydata_in_world(node) for node in modelSources]
        combined = self._appendPolydata(surfaces)
        if combined is not None:
            proxy = parameterNode.step6OpenedTargetGeometryModel
            if proxy and not self.isStep6OpenedTargetGeometryModelNode(proxy):
                raise ValueError(_("Select the Step 6 opened target-geometry model."))
            proxy = proxy or slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 6.0A] Opened Target-Attached Geometry",
            )
            proxy.SetName("[Step 6.0A] Opened Target-Attached Geometry")
            proxy.SetAttribute(
                "DENTOBOT.ModelRole",
                self.STEP6_OPENED_TARGET_GEOMETRY_MODEL_ROLE,
            )
            proxy.SetAttribute("DENTOBOT.GeometryState", "Current")
            try:
                visibility = json.loads(
                    proxy.GetAttribute("DENTOBOT.SourceDisplayVisibilityJson")
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                visibility = {}
            for source in modelSources:
                sourceDisplay = source.GetDisplayNode()
                if sourceDisplay and source.GetID() not in visibility:
                    visibility[source.GetID()] = bool(sourceDisplay.GetVisibility())
                if sourceDisplay:
                    sourceDisplay.SetVisibility(False)
            proxy.SetAttribute(
                "DENTOBOT.SourceDisplayVisibilityJson",
                canonical_json(visibility),
            )
            proxy.SetAndObservePolyData(combined)
            proxy.SetAndObserveTransformNodeID(transform.GetID())
            proxy.SetSelectable(False)
            proxy.CreateDefaultDisplayNodes()
            proxyDisplay = proxy.GetDisplayNode()
            if proxyDisplay:
                proxyDisplay.SetVisibility(True)
                proxyDisplay.SetVisibility2D(False)
                proxyDisplay.SetVisibility3D(True)
                proxyDisplay.SetColor(0.95, 0.76, 0.18)
                proxyDisplay.SetOpacity(float(parameterNode.step6GuidesOpacity))
            parameterNode.step6OpenedTargetGeometryModel = proxy

        trajectory = parameterNode.trajectoryLine
        summary = self.getTrajectorySummary(trajectory) if trajectory else {}
        if summary.get("isValid"):
            proxyLine = parameterNode.step6OpenedTrajectoryLine
            if proxyLine and not self.isStep6OpenedTrajectoryNode(proxyLine):
                raise ValueError(_("Select the Step 6 opened trajectory line."))
            proxyLine = proxyLine or slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsLineNode",
                "[Step 6.0A] Opened Entry-to-Target",
            )
            proxyLine.SetName("[Step 6.0A] Opened Entry-to-Target")
            proxyLine.SetAttribute(
                "DENTOBOT.MarkupsRole",
                self.STEP6_OPENED_TRAJECTORY_ROLE,
            )
            proxyLine.SetAttribute("DENTOBOT.GeometryState", "Current")
            sourceDisplay = trajectory.GetDisplayNode()
            if not proxyLine.GetAttribute("DENTOBOT.SourceDisplayVisibilityJson"):
                proxyLine.SetAttribute(
                    "DENTOBOT.SourceDisplayVisibilityJson",
                    canonical_json(
                        {
                            "visible": bool(sourceDisplay.GetVisibility())
                            if sourceDisplay
                            else True,
                            "visible2D": bool(sourceDisplay.GetVisibility2D())
                            if sourceDisplay
                            else True,
                            "visible3D": bool(sourceDisplay.GetVisibility3D())
                            if sourceDisplay
                            else True,
                        }
                    ),
                )
            if sourceDisplay:
                sourceDisplay.SetVisibility(False)
            proxyLine.SetAndObserveTransformNodeID(None)
            proxyLine.RemoveAllControlPoints()
            proxyLine.AddControlPointWorld(vtk.vtkVector3d(*summary["entryRas"]))
            proxyLine.AddControlPointWorld(vtk.vtkVector3d(*summary["targetRas"]))
            proxyLine.SetNthControlPointLabel(0, "Entry")
            proxyLine.SetNthControlPointLabel(1, "Target")
            proxyLine.SetLocked(True)
            proxyLine.SetAndObserveTransformNodeID(transform.GetID())
            proxyLine.CreateDefaultDisplayNodes()
            proxyDisplay = proxyLine.GetDisplayNode()
            if proxyDisplay:
                proxyDisplay.SetVisibility(True)
                proxyDisplay.SetVisibility2D(True)
                proxyDisplay.SetVisibility3D(True)
                proxyDisplay.SetColor(1.0, 0.25, 0.15)
                proxyDisplay.SetSelectedColor(1.0, 0.85, 0.15)
                proxyDisplay.SetLineThickness(0.5)
            parameterNode.step6OpenedTrajectoryLine = proxyLine

    def createOrUpdateStep6CaseJawOpening(
        self,
        parameterNode,
    ) -> tuple[vtkMRMLLinearTransformNode, vtkMRMLModelNode, vtkMRMLMarkupsLineNode, dict]:
        if not bool(parameterNode.step6PlanningContextImported):
            raise ValueError(_("Import the Steps 0–5 planning package first."))
        if bool(parameterNode.robotBaseMountLocked) or self.isRos2MotionControlActive(
            parameterNode.robotBaseTransform
        ):
            raise ValueError(
                _("Disconnect ROS and unlock the robot base before changing the case jaw pose.")
            )
        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            raise ValueError(_("The imported case has no authoritative dental segmentation."))
        lowerIds = self.step6CaseJawSegmentIds(segmentation)["lower"]
        if not lowerIds:
            raise ValueError(
                _("The imported segmentation has no mandibular jaw or lower-tooth surfaces.")
            )
        left, right, upper, lower = self.step6CaseJawLandmarkPositions(
            parameterNode.step6CaseJawLandmarks
        )
        angle, matrix, openedLower, gap = solve_hinge_rotation_for_gap(
            left,
            right,
            upper,
            lower,
            float(parameterNode.step6CaseJawTargetGapMm),
        )
        sourceSurface = self._segmentationSegmentsSurfaceWorld(
            segmentation,
            set(lowerIds),
        )
        if sourceSurface is None or sourceSurface.GetNumberOfPoints() == 0:
            raise ValueError(_("Could not build the lower-jaw closed surface."))
        sourceFingerprint = self._step6CaseJawGeometryFingerprint(
            segmentation,
            lowerIds,
        )

        transform = parameterNode.step6CaseJawTransform
        if transform and not self.isStep6CaseJawTransformNode(transform):
            raise ValueError(_("Select the Step 6 case jaw transform."))
        transform = transform or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLLinearTransformNode",
            "[Step 6.0A] Case TMJ Mouth Opening",
        )
        transform.SetName("[Step 6.0A] Case TMJ Mouth Opening")
        transform.SetAttribute("DENTOBOT.TransformRole", self.STEP6_CASE_JAW_TRANSFORM_ROLE)
        transform.SetAttribute("DENTOBOT.SchemaVersion", self.STEP6_CASE_JAW_SCHEMA_VERSION)
        transform.SetAttribute("DENTOBOT.GeometryState", "Current")
        transform.SetAttribute("DENTOBOT.StaleReason", None)
        transform.SetAttribute("DENTOBOT.JawMotion", "PureTMJHingeRotation")
        transform.SetAttribute(
            "DENTOBOT.TargetIncisorGapMm",
            f"{float(parameterNode.step6CaseJawTargetGapMm):.6f}",
        )
        transform.SetAttribute("DENTOBOT.AchievedIncisorGapMm", f"{gap:.6f}")
        transform.SetAttribute("DENTOBOT.HingeAngleDeg", f"{angle:.6f}")
        transform.SetAttribute("DENTOBOT.SourceGeometryFingerprint", sourceFingerprint)
        transform.SetAttribute(
            "DENTOBOT.LandmarksFingerprint",
            self._step6CaseJawLandmarksFingerprint(
                parameterNode.step6CaseJawLandmarks
            ),
        )
        transform.SetAttribute(
            "DENTOBOT.TargetSegmentID",
            str(parameterNode.targetToothSegmentId or ""),
        )
        transform.SetAttribute(
            "DENTOBOT.TargetAttachedGeometryFingerprint",
            self._step6TargetAttachedGeometryFingerprint(parameterNode),
        )
        transform.SetAttribute("DENTOBOT.MovingSegmentIdsJson", canonical_json(lowerIds))
        transform.SetNodeReferenceID(
            "DENTOBOT.SourceSegmentation",
            segmentation.GetID(),
        )
        transform.SetAndObserveTransformNodeID(None)
        transform.SetMatrixTransformToParent(self._vtkFromNumpyMatrix(matrix))

        model = parameterNode.step6OpenedLowerJawModel
        if model and not self.isStep6OpenedLowerJawModelNode(model):
            raise ValueError(_("Select the Step 6 opened lower-jaw model."))
        model = model or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode",
            "[Step 6.0A] Opened Lower Jaw Planning Surface",
        )
        model.SetName("[Step 6.0A] Opened Lower Jaw Planning Surface")
        model.SetAttribute("DENTOBOT.ModelRole", self.STEP6_OPENED_LOWER_JAW_MODEL_ROLE)
        model.SetAttribute("DENTOBOT.SchemaVersion", self.STEP6_CASE_JAW_SCHEMA_VERSION)
        model.SetAttribute("DENTOBOT.GeometryState", "Current")
        model.SetAttribute("DENTOBOT.SourceGeometryFingerprint", sourceFingerprint)
        model.SetAttribute("DENTOBOT.MovingSegmentIdsJson", canonical_json(lowerIds))
        display = segmentation.GetDisplayNode()
        if display:
            try:
                visibility = json.loads(
                    model.GetAttribute("DENTOBOT.SourceSegmentVisibility3DJson")
                    or "{}"
                )
            except (TypeError, json.JSONDecodeError):
                visibility = {}
            for segmentId in lowerIds:
                if segmentId not in visibility:
                    visibility[segmentId] = bool(
                        display.GetSegmentVisibility3D(segmentId)
                    )
            model.SetAttribute(
                "DENTOBOT.SourceSegmentVisibility3DJson",
                canonical_json(visibility),
            )
        model.SetAndObservePolyData(sourceSurface)
        model.SetAndObserveTransformNodeID(transform.GetID())
        model.SetSelectable(False)
        model.CreateDefaultDisplayNodes()
        modelDisplay = model.GetDisplayNode()
        if modelDisplay:
            modelDisplay.SetVisibility(True)
            modelDisplay.SetVisibility2D(False)
            modelDisplay.SetVisibility3D(True)
            modelDisplay.SetColor(0.90, 0.74, 0.56)
            modelDisplay.SetOpacity(float(parameterNode.step6MasksOpacity))
        if display:
            for segmentId in lowerIds:
                display.SetSegmentVisibility3D(segmentId, False)

        gapLine = parameterNode.step6CaseJawGapLine
        if gapLine and (
            not gapLine.IsA("vtkMRMLMarkupsLineNode")
            or gapLine.GetAttribute("DENTOBOT.MarkupsRole")
            != self.STEP6_CASE_JAW_GAP_LINE_ROLE
        ):
            raise ValueError(_("Select the Step 6 case incisor-gap line."))
        gapLine = gapLine or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsLineNode",
            "[Step 6.0A] Case Incisor Gap",
        )
        gapLine.SetName("[Step 6.0A] Case Incisor Gap")
        gapLine.RemoveAllControlPoints()
        gapLine.AddControlPointWorld(vtk.vtkVector3d(*upper))
        gapLine.AddControlPointWorld(vtk.vtkVector3d(*openedLower))
        gapLine.SetNthControlPointLabel(0, "Upper incisor")
        gapLine.SetNthControlPointLabel(1, "Opened lower incisor")
        gapLine.SetLocked(True)
        gapLine.SetSelectable(False)
        gapLine.SetAttribute("DENTOBOT.MarkupsRole", self.STEP6_CASE_JAW_GAP_LINE_ROLE)
        gapLine.SetAttribute("DENTOBOT.SchemaVersion", self.STEP6_CASE_JAW_SCHEMA_VERSION)
        gapLine.CreateDefaultDisplayNodes()
        gapDisplay = gapLine.GetDisplayNode()
        if gapDisplay:
            gapDisplay.SetVisibility(True)
            gapDisplay.SetVisibility2D(True)
            gapDisplay.SetVisibility3D(True)
            gapDisplay.SetColor(0.15, 1.0, 0.25)
            gapDisplay.SetPointLabelsVisibility(True)
            gapDisplay.SetPropertiesLabelVisibility(True)

        parameterNode.step6CaseJawTransform = transform
        parameterNode.step6OpenedLowerJawModel = model
        parameterNode.step6CaseJawGapLine = gapLine
        self._updateStep6CaseTargetAttachedDisplay(parameterNode, transform)
        self.invalidateStep6TaskConfirmation(
            parameterNode,
            _("Case jaw opening changed."),
            makeBaseStale=True,
        )
        self.deleteRobotWorkspaceModel()
        return transform, model, gapLine, {
            "angleDeg": angle,
            "gapMm": gap,
            "openedLowerIncisorRas": openedLower,
            "movingSegmentCount": len(lowerIds),
        }

    def resetStep6CaseJawOpening(self, parameterNode) -> None:
        if bool(parameterNode.robotBaseMountLocked) or self.isRos2MotionControlActive(
            parameterNode.robotBaseTransform
        ):
            raise ValueError(
                _("Disconnect ROS and unlock the robot base before resetting the case jaw.")
            )
        model = parameterNode.step6OpenedLowerJawModel
        transform = parameterNode.step6CaseJawTransform
        gapLine = parameterNode.step6CaseJawGapLine
        self._restoreStep6CaseLowerJawVisibility(
            parameterNode.teethSegmentation,
            model,
        )
        self._restoreStep6CaseTargetAttachedVisibility(parameterNode)
        for node in (
            parameterNode.step6OpenedTrajectoryLine,
            parameterNode.step6OpenedTargetGeometryModel,
            gapLine,
            model,
            transform,
        ):
            if node and slicer.mrmlScene.IsNodePresent(node):
                slicer.mrmlScene.RemoveNode(node)
        parameterNode.step6OpenedTrajectoryLine = None
        parameterNode.step6OpenedTargetGeometryModel = None
        parameterNode.step6CaseJawTransform = None
        parameterNode.step6OpenedLowerJawModel = None
        parameterNode.step6CaseJawGapLine = None
        self.invalidateStep6TaskConfirmation(
            parameterNode,
            _("Case jaw opening was reset."),
            makeBaseStale=True,
        )
        self.deleteRobotWorkspaceModel()

    def deleteDraftPhantom(
        self,
        landmarks=None,
        transform=None,
        gapLine=None,
    ) -> list[str]:
        nodes = [
            *self.draftPhantomModelNodes(),
            *self.draftPhantomWorkspaceTransformNodes(),
            landmarks,
            transform,
            gapLine,
        ]
        removed = []
        for node in dict.fromkeys(node for node in nodes if node):
            if slicer.mrmlScene.IsNodePresent(node):
                removed.append(node.GetName())
                slicer.mrmlScene.RemoveNode(node)
        return removed
