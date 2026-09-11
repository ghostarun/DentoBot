"""Extracted draft phantom scene methods; public APIs remain on Step6SceneLogicMixin."""

from __future__ import annotations

from .runtime import *


class PhantomSceneLogicMixin:
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
