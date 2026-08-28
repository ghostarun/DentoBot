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
        model_candidates = [*self.draftPhantomModelNodes(), *guidance_models]
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
        nonTargetTeeth: list[vtk.vtkPolyData] = []
        nonTargetAnatomy: list[vtk.vtkPolyData] = []
        for segmentId in anatomyIds:
            worldSurface = self._segmentationSegmentsSurfaceWorld(
                segmentation,
                {segmentId},
            )
            if worldSurface is None or worldSurface.GetNumberOfPoints() == 0:
                raise ValueError(
                    _("Step 6 collision anatomy segment %1 is empty.").replace(
                        "%1", str(segmentId)
                    )
                )
            if segmentId in lowerIds:
                worldSurface = self._step6CaseJawPolydataWorld(
                    parameterNode,
                    worldSurface,
                )
            triangle = vtk.vtkTriangleFilter()
            triangle.SetInputData(worldSurface)
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
                sources.append((sourceId, sourceName, collisionSurface))
            elif segmentId in toothIds:
                nonTargetTeeth.append(collisionSurface)
            else:
                nonTargetAnatomy.append(collisionSurface)

        # Keep the selected target tooth independent for the phase guard's
        # selective burr-contact rule.  The exact, transformed triangles for
        # all other teeth and for jaw anatomy are grouped into two disconnected
        # meshes.  This preserves geometry while avoiding dozens of separate
        # FCL world objects and their repeated broad-phase traversal at every
        # guarded preview sample.
        for category, surfaces in (
            ("non_target_teeth", nonTargetTeeth),
            ("non_target_anatomy", nonTargetAnatomy),
        ):
            combined = self._appendPolydata(surfaces)
            if combined is None:
                continue
            sources.append(
                (
                    f"{segmentation.GetID()}:anatomy:{category}",
                    f"dentobot_anatomy_{category}",
                    combined,
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
