"""Extracted robot scene synchronization methods; public APIs remain on RobotLogicMixin."""

from __future__ import annotations

from .runtime import *


class RobotSceneSyncLogicMixin:
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
            if (
                str(parameterNode.step6CaseJawPreparationMode)
                == "TargetJawFallback"
            ):
                targetJaw = self.step6TargetJaw(parameterNode)
                fallbackSurface = self._segmentationSegmentsSurfaceWorld(
                    segmentation,
                    set(jawGroups.get(targetJaw, ())),
                )
                if fallbackSurface:
                    samples.extend(
                        self._subsample_polydata_points(
                            fallbackSurface,
                            stride=80,
                        )
                    )
                fixedSurface = None
                movingSurface = None
            else:
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
        if str(parameterNode.step6CaseJawPreparationMode) == "TargetJawFallback":
            return polydataWorld
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
            or str(parameterNode.step6CaseJawPreparationMode)
            == "TargetJawFallback"
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

    @staticmethod
    def _collisionAuditPolydataEvidence(polydata: vtk.vtkPolyData) -> dict:
        """Return deterministic, bounded evidence for one exact mesh copy."""
        if polydata is None or polydata.GetNumberOfPoints() <= 0:
            raise ValueError(_("Collision-audit surface is empty."))
        triangle = vtk.vtkTriangleFilter()
        triangle.SetInputData(polydata)
        triangle.PassLinesOff()
        triangle.PassVertsOff()
        triangle.Update()
        surface = vtk.vtkPolyData()
        surface.DeepCopy(triangle.GetOutput())
        points = np.ascontiguousarray(
            vtk_to_numpy(surface.GetPoints().GetData()), dtype="<f8"
        )
        polygons = np.ascontiguousarray(
            vtk_to_numpy(surface.GetPolys().GetData()), dtype="<i8"
        )
        digest = hashlib.sha256()
        digest.update(str(tuple(points.shape)).encode("ascii"))
        digest.update(points.tobytes(order="C"))
        digest.update(str(tuple(polygons.shape)).encode("ascii"))
        digest.update(polygons.tobytes(order="C"))
        connectivity = vtk.vtkConnectivityFilter()
        connectivity.SetInputData(surface)
        connectivity.SetExtractionModeToAllRegions()
        connectivity.ColorRegionsOff()
        connectivity.Update()
        topology = surface_topology(surface)
        return {
            "surface": surface,
            "fingerprint": digest.hexdigest(),
            "point_count": int(surface.GetNumberOfPoints()),
            "cell_count": int(surface.GetNumberOfPolys()),
            "bounds": tuple(float(value) for value in surface.GetBounds()),
            "connected_component_count": int(
                connectivity.GetNumberOfExtractedRegions()
            ),
            "boundary_or_nonmanifold_edge_count": int(
                topology["boundaryOrNonManifoldEdgeCount"]
            ),
        }

    def collisionSceneAuditRecord(self, parameterNode):
        payload = str(parameterNode.step6CollisionSceneAuditJson or "").strip()
        return parse_collision_scene_audit(payload) if payload else None

    def collisionSceneAuditFreshnessIssues(self, parameterNode) -> tuple[str, ...]:
        try:
            audit = self.collisionSceneAuditRecord(parameterNode)
        except (ValueError, json.JSONDecodeError):
            return (_("The saved collision-scene audit is invalid."),)
        if audit is None:
            return (_("Synchronize and audit the Step 6 collision scene."),)
        issues = []
        if audit.base_fingerprint != self.robotBaseFingerprint(parameterNode):
            issues.append(_("Collision-scene evidence belongs to a different base pose."))
        if audit.status != "Acknowledged":
            issues.append(
                _(
                    "Collision-scene audit is not fully acknowledged "
                    "(status: %1)."
                ).replace("%1", audit.status)
            )
        acknowledgement = audit.runtime_acknowledgement
        if acknowledgement.get("status") != "Acknowledged":
            issues.append(
                _(
                    "MoveIt PlanningScene acknowledgement is not yet available; "
                    "publisher success is not runtime-scene proof."
                )
            )
        return tuple(issues)

    def _syncCollisionAuditDisplayCopy(
        self,
        *,
        source_id: str,
        outgoing_id: str,
        outgoing_base_mm: vtk.vtkPolyData,
        base_world: vtk.vtkMatrix4x4,
        outgoing_fingerprint: str,
        opacity: float,
    ) -> vtkMRMLModelNode:
        """Create one transient world-RAS display copy of the exact payload."""
        existing = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
            if node.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true"
            and node.GetAttribute("DENTOBOT.MoveItObstacleSource") == source_id
        ]
        node = existing[0] if existing else slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode", f"[Step 6 Audit] {outgoing_id}"
        )
        for duplicate in existing[1:]:
            slicer.mrmlScene.RemoveNode(duplicate)
        world_copy = self._transformPolydataWithMatrix(
            outgoing_base_mm,
            base_world,
        )
        node.SetName(f"[Step 6 Audit] {outgoing_id}")
        node.SetAndObserveTransformNodeID(None)
        node.SetAndObservePolyData(world_copy)
        node.SetAttribute("DENTOBOT.CollisionAuditCopy", "true")
        node.SetAttribute("DENTOBOT.MoveItObstacleSource", source_id)
        node.SetAttribute("DENTOBOT.OutgoingCollisionObjectId", outgoing_id)
        node.SetAttribute(
            "DENTOBOT.OutgoingCollisionFingerprint", outgoing_fingerprint
        )
        node.SetAttribute("DENTOBOT.CoordinateFrame", "SlicerWorldRAS")
        node.SetAttribute("DENTOBOT.IntendedUse", "DisplayOnlyAuditOverlay")
        node.SaveWithSceneOff()
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        if display:
            display.SetVisibility(False)
            display.SetOpacity(max(0.0, min(1.0, float(opacity))))
            display.SetColor(0.10, 0.95, 0.95)
            display.SetRepresentation(1)
            display.SetLineWidth(2.0)
        return node

    def syncStep6MoveItPlanningScene(self, parameterNode) -> int:
        """Publish Step 6 anatomy/guide surfaces in the base_link frame."""
        try:
            prior_audit = self.collisionSceneAuditRecord(parameterNode)
        except (ValueError, json.JSONDecodeError):
            prior_audit = None
        base_transform = parameterNode.robotBaseTransform
        if base_transform is None:
            raise ValueError(_("Select the Step 6 robot base before syncing obstacles."))
        if bool(parameterNode.step6PlanningContextImported):
            jawIssues = self.step6CaseJawOpeningFreshnessIssues(parameterNode)
            if jawIssues:
                raise ValueError(" ".join(jawIssues))
        sources: list[dict[str, object]] = []

        def append_source(
            *,
            source_id: str,
            source_name: str,
            source_role: str,
            classification: str,
            source_world: vtk.vtkPolyData,
            prepared_world: vtk.vtkPolyData,
            jaw_transform_applied: bool,
        ) -> None:
            sources.append(
                {
                    "sourceId": str(source_id),
                    "sourceName": str(source_name),
                    "sourceRole": str(source_role),
                    "classification": str(classification),
                    "sourceWorld": source_world,
                    "preparedWorld": prepared_world,
                    "jawTransformApplicationCount": (
                        1 if jaw_transform_applied else 0
                    ),
                }
            )
        # A verified 5C template already contains the support shell and docking
        # assembly.  Publishing those precursors again creates coincident world
        # objects with different identities.  Use the final template when it is
        # available; only fall back to its components for pre-final test scenes.
        guidance_models = (
            [parameterNode.finalPrintableTemplateModel]
            if parameterNode.finalPrintableTemplateModel is not None
            else [
                parameterNode.draftTemplateSupportModel,
                parameterNode.targetDockingAssemblyModel,
            ]
        )
        phantom_models = self.draftPhantomModelNodes()
        model_candidates = [*phantom_models, *guidance_models]
        for model in dict.fromkeys(node for node in model_candidates if node is not None):
            if not isinstance(model, vtkMRMLModelNode):
                continue
            source_world = model_polydata_in_world(model)
            prepared_world = source_world
            is_target_attached = model in {
                parameterNode.draftTemplateSupportModel,
                parameterNode.finalPrintableTemplateModel,
                parameterNode.targetDockingAssemblyModel,
            }
            jaw_applied = bool(
                is_target_attached
                and bool(parameterNode.step6PlanningContextImported)
                and self.step6TargetJaw(parameterNode) == "lower"
                and str(parameterNode.step6CaseJawPreparationMode)
                != "TargetJawFallback"
            )
            if is_target_attached:
                prepared_world = self._step6TargetAttachedPolydataWorld(
                    parameterNode,
                    source_world,
                )
            if prepared_world is None or prepared_world.GetNumberOfPoints() == 0:
                continue
            if model in phantom_models:
                role = "draft-phantom-anatomy"
                classification = "fixed-test-anatomy"
            elif model is parameterNode.finalPrintableTemplateModel:
                role = "verified-final-template"
                classification = (
                    "moving-target-attached" if jaw_applied else "fixed-target-attached"
                )
            elif model is parameterNode.draftTemplateSupportModel:
                role = "draft-template-support"
                classification = (
                    "moving-target-attached" if jaw_applied else "fixed-target-attached"
                )
            else:
                role = "target-docking-assembly"
                classification = (
                    "moving-target-attached" if jaw_applied else "fixed-target-attached"
                )
            append_source(
                source_id=model.GetID(),
                source_name=model.GetName(),
                source_role=role,
                classification=classification,
                source_world=source_world,
                prepared_world=prepared_world,
                jaw_transform_applied=jaw_applied,
            )

        segmentation = parameterNode.teethSegmentation
        target_id = str(parameterNode.targetToothSegmentId or "")
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
        lowerIds = set(jawGroups["lower"])
        toothIds = set(
            (*jawGroups.get("upperTeeth", ()), *jawGroups.get("lowerTeeth", ()))
        )
        anatomyIds = tuple(
            dict.fromkeys((*jawGroups.get("upper", ()), *jawGroups.get("lower", ())))
        )
        for segmentId in anatomyIds:
            sourceWorld = self._segmentationSegmentsSurfaceWorld(
                segmentation,
                {segmentId},
            )
            if sourceWorld is None or sourceWorld.GetNumberOfPoints() == 0:
                raise ValueError(
                    _("Step 6 collision anatomy segment %1 is empty.").replace(
                        "%1", str(segmentId)
                    )
                )
            isMoving = segmentId in lowerIds
            preparedWorld = sourceWorld
            if isMoving:
                preparedWorld = self._step6CaseJawPolydataWorld(
                    parameterNode,
                    sourceWorld,
                )
            triangle = vtk.vtkTriangleFilter()
            triangle.SetInputData(preparedWorld)
            triangle.PassLinesOff()
            triangle.PassVertsOff()
            triangle.Update()
            collisionSurface = vtk.vtkPolyData()
            collisionSurface.DeepCopy(triangle.GetOutput())
            topology = surface_topology(collisionSurface)
            if topology["boundaryOrNonManifoldEdgeCount"] != 0:
                raise ValueError(
                    _(
                        "Step 6 collision anatomy segment %1 is not a closed, "
                        "watertight surface."
                    ).replace("%1", str(segmentId))
                )
            if segmentId == target_id:
                sourceId = f"{segmentation.GetID()}:target:{target_id}"
                sourceName = self.step6TargetCollisionObjectName(parameterNode)
                sourceRole = "selected-target-tooth"
            elif segmentId in toothIds:
                sourceId = f"{segmentation.GetID()}:anatomy:{segmentId}"
                sourceName = "dentobot_tooth_" + re.sub(
                    r"[^A-Za-z0-9_.-]+", "_", str(segmentId)
                ) + "_" + fingerprint(str(segmentId))[:8]
                sourceRole = "non-target-tooth"
            else:
                sourceId = f"{segmentation.GetID()}:anatomy:{segmentId}"
                sourceName = "dentobot_jaw_" + re.sub(
                    r"[^A-Za-z0-9_.-]+", "_", str(segmentId)
                ) + "_" + fingerprint(str(segmentId))[:8]
                sourceRole = "jaw-anatomy"
            append_source(
                source_id=sourceId,
                source_name=sourceName,
                source_role=sourceRole,
                classification="moving" if isMoving else "fixed",
                source_world=sourceWorld,
                prepared_world=collisionSurface,
                jaw_transform_applied=isMoving,
            )

        active_ids = {str(source["sourceId"]) for source in sources}
        remove_stale_moveit_obstacle_proxies(active_ids)
        for node in list(slicer.util.getNodesByClass("vtkMRMLModelNode")):
            if (
                node.GetAttribute("DENTOBOT.CollisionAuditCopy") == "true"
                and node.GetAttribute("DENTOBOT.MoveItObstacleSource")
                not in active_ids
            ):
                slicer.mrmlScene.RemoveNode(node)
        base_world = self._worldMatrixFromTransform(base_transform)
        world_to_base = vtk.vtkMatrix4x4()
        vtk.vtkMatrix4x4.Invert(base_world, world_to_base)
        world_to_base_fingerprint = fingerprint(
            {
                "direction": "world-RAS-mm-to-base_link-RAS-mm",
                "matrix": vtk_matrix_elements(world_to_base),
                "applicationCount": 1,
            }
        )
        jaw_preparation_fingerprint = fingerprint(
            {
                "mode": str(parameterNode.step6CaseJawPreparationMode or ""),
                "record": str(parameterNode.step6CaseJawPreparationJson or ""),
            }
        )
        object_records: list[dict[str, object]] = []
        for source in sources:
            source_id = str(source["sourceId"])
            source_name = str(source["sourceName"])
            source_world = source["sourceWorld"]
            world_surface = source["preparedWorld"]
            base_surface = self._polydataWorldToRobotBase(
                world_surface,
                base_transform,
            )
            source_evidence = self._collisionAuditPolydataEvidence(source_world)
            prepared_evidence = self._collisionAuditPolydataEvidence(world_surface)
            outgoing_evidence = self._collisionAuditPolydataEvidence(base_surface)
            record = {
                "source_id": source_id,
                "source_name": source_name,
                "source_role": str(source["sourceRole"]),
                "classification": str(source["classification"]),
                "source_revision": fingerprint(
                    {
                        "sourceId": source_id,
                        "sourceFingerprint": source_evidence["fingerprint"],
                    }
                ),
                "source_fingerprint": source_evidence["fingerprint"],
                "prepared_world_fingerprint": prepared_evidence["fingerprint"],
                "outgoing_fingerprint": outgoing_evidence["fingerprint"],
                "source_point_count": source_evidence["point_count"],
                "source_cell_count": source_evidence["cell_count"],
                "outgoing_point_count": outgoing_evidence["point_count"],
                "outgoing_cell_count": outgoing_evidence["cell_count"],
                "source_bounds_world_ras_mm": source_evidence["bounds"],
                "prepared_bounds_world_ras_mm": prepared_evidence["bounds"],
                "outgoing_bounds_base_link_mm": outgoing_evidence["bounds"],
                "connected_component_count": outgoing_evidence[
                    "connected_component_count"
                ],
                "boundary_or_nonmanifold_edge_count": outgoing_evidence[
                    "boundary_or_nonmanifold_edge_count"
                ],
                "jaw_transform_application_count": int(
                    source["jawTransformApplicationCount"]
                ),
                "jaw_transform_fingerprint": (
                    jaw_preparation_fingerprint
                    if int(source["jawTransformApplicationCount"])
                    else ""
                ),
                "world_to_base_fingerprint": world_to_base_fingerprint,
                "world_to_base_application_count": 1,
                "source_coordinate_frame": "SlicerWorldRAS",
                "source_linear_unit": "mm",
                "outgoing_coordinate_frame": "base_link",
                "outgoing_linear_unit_before_publish": "mm",
                "publisher_linear_scale_m_per_mm": 0.001,
                "collision_padding_mm": 0.0,
                "outgoing_collision_object_id": source_name,
                "publish_status": "Pending",
                "runtime_acknowledgement_status": "NotQueried",
            }
            self._syncCollisionAuditDisplayCopy(
                source_id=source_id,
                outgoing_id=source_name,
                outgoing_base_mm=outgoing_evidence["surface"],
                base_world=base_world,
                outgoing_fingerprint=str(outgoing_evidence["fingerprint"]),
                opacity=float(parameterNode.step6CollisionAuditOpacity),
            )
            ok, message = sync_moveit_obstacle_polydata(
                source_id=source_id,
                source_name=source_name,
                polydata_base_mm=outgoing_evidence["surface"],
            )
            if not ok:
                record["publish_status"] = "Failed"
                record["publish_error"] = str(message)
                object_records.append(record)
                audit = build_collision_scene_audit(
                    status="PublishFailed",
                    base_fingerprint=self.robotBaseFingerprint(parameterNode),
                    jaw_preparation_fingerprint=jaw_preparation_fingerprint,
                    world_to_base_fingerprint=world_to_base_fingerprint,
                    object_records=object_records,
                    runtime_acknowledgement={
                        "status": "NotAcknowledged",
                        "reason": "Collision-object publication failed.",
                        "acknowledged_object_ids": [],
                    },
                )
                parameterNode.step6CollisionSceneAuditJson = canonical_json(
                    audit.to_dict()
                )
                raise RuntimeError(message)
            record["publish_status"] = "PublishReturnedSuccess"
            object_records.append(record)
        acknowledgement = acknowledge_moveit_collision_scene(
            expected_objects=object_records,
            current_joint_positions_si=joint_positions_si_from_display(
                parameterNode.robotJoint1Deg,
                parameterNode.robotJoint2Mm,
                parameterNode.robotJoint3Deg,
                parameterNode.robotJoint4Mm,
                parameterNode.robotJoint5Deg,
                parameterNode.robotJoint6Deg,
            ),
        )
        audit = build_collision_scene_audit(
            status=(
                "Acknowledged"
                if acknowledgement.get("status") == "Acknowledged"
                else "RuntimeAcknowledgementFailed"
            ),
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            jaw_preparation_fingerprint=jaw_preparation_fingerprint,
            world_to_base_fingerprint=world_to_base_fingerprint,
            object_records=object_records,
            runtime_acknowledgement=acknowledgement,
        )
        parameterNode.step6CollisionSceneAuditJson = canonical_json(audit.to_dict())
        if (
            prior_audit is not None
            and prior_audit.audit_fingerprint != audit.audit_fingerprint
        ):
            self.markStep6MotionDiagnosticStale(
                parameterNode,
                _("Collision-scene payload or runtime acknowledgement changed."),
            )
        if audit.status != "Acknowledged":
            mismatches = acknowledgement.get("mismatches", ())
            raise RuntimeError(
                _(
                    "MoveIt collision-scene acknowledgement failed: %1"
                ).replace(
                    "%1",
                    "; ".join(str(item) for item in mismatches)
                    or str(acknowledgement.get("reason") or "unknown mismatch"),
                )
            )
        return len(sources)
