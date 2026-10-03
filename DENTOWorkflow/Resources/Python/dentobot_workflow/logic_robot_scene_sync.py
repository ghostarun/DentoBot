"""Extracted robot scene synchronization methods; public APIs remain on RobotLogicMixin."""

from __future__ import annotations

from .runtime import *

_ANATOMY_REVIEW_SESSION = str(uuid.uuid4())
_HISTORICAL_ANATOMY_REVIEW_ENV = "DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW"


class RobotSceneSyncLogicMixin:
    _STEP6_ANATOMY_REVIEW_PROXY_ATTRIBUTE = "DENTOBOT.Step6AnatomyReviewProxy"
    _STEP6_ANATOMY_REVIEW_SOURCE_NODE_ATTRIBUTE = (
        "DENTOBOT.Step6AnatomyReviewSourceSegmentationNodeId"
    )
    _STEP6_ANATOMY_REVIEW_SOURCE_SEGMENT_ATTRIBUTE = (
        "DENTOBOT.Step6AnatomyReviewSourceSegmentId"
    )
    _STEP6_ANATOMY_REVIEW_ACTIVE_ATTRIBUTE = (
        "DENTOBOT.Step6AnatomyReviewCollisionProxyActive"
    )

    def step6AnatomyReviewCandidates(self, parameterNode) -> tuple[dict[str, str], ...]:
        """Return whole non-target teeth eligible for an explicit local review.

        This deliberately exposes no automatic outlier selection.  The current
        x4 evidence can direct an operator to FDI15, but the workflow must stay
        useful for any later reviewed non-target tooth and must never silently
        remove a complete anatomy object from collision evaluation.
        """

        segmentation = parameterNode.teethSegmentation
        target_id = str(parameterNode.targetToothSegmentId or "")
        if segmentation is None:
            return ()
        return tuple(
            {
                "segmentId": str(record["segmentId"]),
                "displayName": str(record.get("displayName") or record["segmentId"]),
                "fdiNumber": str(record.get("fdiNumber") or ""),
            }
            for record in self.getTargetToothRecords(segmentation)
            if str(record.get("segmentId") or "")
            and str(record.get("segmentId") or "") != target_id
        )

    def step6AnatomyReviewProxyNode(self, parameterNode):
        """Return the one session-only review node for this source segmentation."""

        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            return None
        source_id = str(segmentation.GetID() or "")
        candidates = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
            if node.GetAttribute(self._STEP6_ANATOMY_REVIEW_PROXY_ATTRIBUTE) == "true"
            and node.GetAttribute(self._STEP6_ANATOMY_REVIEW_SOURCE_NODE_ATTRIBUTE)
            == source_id
        ]
        if len(candidates) > 1:
            raise ValueError("Multiple anatomy-review copies exist; resolve them before collision synchronization.")
        return candidates[-1] if candidates else None

    def _step6AnatomyReviewFingerprint(self, node, segment_id: str) -> str:
        return self._collisionAuditPolydataEvidence(
            self._segmentationSegmentsSurfaceWorld(node, {segment_id})
        )["fingerprint"]

    def _validateStep6AnatomyReview(self, parameterNode, state) -> None:
        """Reject changed review inputs before accepting or publishing a proxy."""
        proxy = state["proxyNode"]
        if proxy.GetAttribute("DENTOBOT.Step6AnatomyReviewSession") != _ANATOMY_REVIEW_SESSION:
            raise ValueError("Anatomy review belongs to an earlier module session; discard and recreate it.")
        segment_id = state["sourceSegmentId"]
        if segment_id not in {
            record["segmentId"] for record in self.step6AnatomyReviewCandidates(parameterNode)
        }:
            raise ValueError("The reviewed segment is no longer eligible non-target anatomy.")
        source_fingerprint = self._step6AnatomyReviewFingerprint(
            parameterNode.teethSegmentation, segment_id
        )
        if source_fingerprint != proxy.GetAttribute("DENTOBOT.Step6AnatomyReviewSourceFingerprint"):
            raise ValueError("Source anatomy or its transform changed; discard and recreate the review copy.")
        if state.get("active") and self._step6AnatomyReviewFingerprint(
            proxy, state["proxySegmentId"]
        ) != proxy.GetAttribute("DENTOBOT.Step6AnatomyReviewAcceptedFingerprint"):
            raise ValueError("Reviewed anatomy changed after acceptance; disable and review it again.")

    def step6AnatomyReviewFreshnessIssues(self, parameterNode) -> tuple[str, ...]:
        try:
            state = self.step6AnatomyReviewState(parameterNode)
            if state.get("active"):
                if not state.get("effectiveActive"):
                    return (
                        "Historical anatomy-review proxy is disabled for the baseline; "
                        "discard the session proxy before planning.",
                    )
                self._validateStep6AnatomyReview(parameterNode, state)
        except (RuntimeError, ValueError, TypeError) as exc:
            return (str(exc),)
        return ()

    def step6AnatomyReviewState(self, parameterNode) -> dict[str, object]:
        """Describe the non-persistent manual anatomy-review state."""

        proxy = self.step6AnatomyReviewProxyNode(parameterNode)
        if proxy is None:
            return {
                "exists": False, "active": False, "effectiveActive": False,
                "historicalOverrideEnabled": os.environ.get(
                    _HISTORICAL_ANATOMY_REVIEW_ENV, ""
                ) == "1",
            }
        segment_id = str(
            proxy.GetAttribute(self._STEP6_ANATOMY_REVIEW_SOURCE_SEGMENT_ATTRIBUTE)
            or ""
        )
        return {
            "exists": True,
            "active": proxy.GetAttribute(
                self._STEP6_ANATOMY_REVIEW_ACTIVE_ATTRIBUTE
            )
            == "true",
            "historicalOverrideEnabled": os.environ.get(
                _HISTORICAL_ANATOMY_REVIEW_ENV, ""
            )
            == "1",
            "effectiveActive": (
                proxy.GetAttribute(self._STEP6_ANATOMY_REVIEW_ACTIVE_ATTRIBUTE)
                == "true"
                and os.environ.get(_HISTORICAL_ANATOMY_REVIEW_ENV, "") == "1"
            ),
            "proxyNode": proxy,
            "sourceSegmentId": segment_id,
            "proxySegmentId": str(
                proxy.GetAttribute("DENTOBOT.Step6AnatomyReviewProxySegmentId")
                or segment_id
            ),
            "operatorDecision": str(
                proxy.GetAttribute("DENTOBOT.Step6AnatomyReviewDecision") or "Pending"
            ),
        }

    def beginStep6AnatomyReview(self, parameterNode, segmentId: str) -> dict[str, object]:
        """Create an editable, session-only copy of one non-target tooth.

        The source segmentation is never changed and the copy is inactive until
        the operator explicitly confirms a reviewed local artifact.  The node
        uses ``SaveWithSceneOff`` so neither the proxy nor its decision can be
        smuggled into an MRML scene or DentoCase as authoritative anatomy.
        """

        segmentation_node = parameterNode.teethSegmentation
        if segmentation_node is None:
            raise ValueError(_("A teeth segmentation is required for anatomy review."))
        candidates = {
            record["segmentId"]: record
            for record in self.step6AnatomyReviewCandidates(parameterNode)
        }
        segment_id = str(segmentId or "")
        record = candidates.get(segment_id)
        if record is None:
            raise ValueError(
                _("Select a non-target whole-tooth segment for manual review.")
            )
        existing = self.step6AnatomyReviewProxyNode(parameterNode)
        if existing is not None:
            existing_id = str(
                existing.GetAttribute(
                    self._STEP6_ANATOMY_REVIEW_SOURCE_SEGMENT_ATTRIBUTE
                )
                or ""
            )
            if existing_id != segment_id:
                raise ValueError(
                    _(
                        "Discard the current session anatomy-review copy before "
                        "reviewing another tooth."
                    )
                )
            return self.step6AnatomyReviewState(parameterNode)

        proxy = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLSegmentationNode",
            "[Step 6] Research Simulation Anatomy Review — %s"
            % str(record["displayName"]),
        )
        try:
            copied = proxy.GetSegmentation().CopySegmentFromSegmentation(
                segmentation_node.GetSegmentation(), segment_id, False
            )
            if not copied or proxy.GetSegmentation().GetSegment(segment_id) is None:
                raise RuntimeError("Could not copy the selected source segment.")
            proxy.SetAndObserveTransformNodeID(segmentation_node.GetTransformNodeID())
            proxy.GetSegmentation().SetConversionParameter(
                slicer.vtkSegmentationConverter.GetReferenceImageGeometryParameterName(),
                segmentation_node.GetSegmentation().GetConversionParameter(
                    slicer.vtkSegmentationConverter.GetReferenceImageGeometryParameterName()
                ),
            )
            proxy.SetAttribute(
                "DENTOBOT.Step6AnatomyReviewSourceFingerprint",
                self._step6AnatomyReviewFingerprint(segmentation_node, segment_id),
            )
            proxy.SetAttribute(self._STEP6_ANATOMY_REVIEW_PROXY_ATTRIBUTE, "true")
            proxy.SetAttribute("DENTOBOT.Step6AnatomyReviewSession", _ANATOMY_REVIEW_SESSION)
            proxy.SetAttribute(
                self._STEP6_ANATOMY_REVIEW_SOURCE_NODE_ATTRIBUTE,
                segmentation_node.GetID(),
            )
            proxy.SetAttribute(
                self._STEP6_ANATOMY_REVIEW_SOURCE_SEGMENT_ATTRIBUTE, segment_id
            )
            proxy.SetAttribute("DENTOBOT.Step6AnatomyReviewProxySegmentId", segment_id)
            proxy.SetAttribute(self._STEP6_ANATOMY_REVIEW_ACTIVE_ATTRIBUTE, "false")
            proxy.SetAttribute("DENTOBOT.Step6AnatomyReviewDecision", "Pending")
            proxy.SetAttribute("DENTOBOT.ResearchOnly", "true")
            proxy.SetAttribute(
                "DENTOBOT.IntendedUse",
                "SessionOnlyManualSegmentationArtifactReview",
            )
            source_volume = self.getSegmentationSourceVolume(segmentation_node)
            proxy.SetNodeReferenceID(
                self.SOURCE_VOLUME_REFERENCE_ROLE, source_volume.GetID()
            )
            proxy.SetAttribute("DENTOBOT.SourceVolumeID", source_volume.GetID())
            proxy.SaveWithSceneOff()
            proxy.CreateDefaultDisplayNodes()
            display = proxy.GetDisplayNode()
            if display is not None:
                display.SaveWithSceneOff()
                display.SetVisibility(True)
                display.SetVisibility2D(True)
                display.SetVisibility3D(True)
                display.SetSegmentVisibility(segment_id, True)
                display.SetSegmentVisibility3D(segment_id, True)
                display.SetSegmentOpacity3D(segment_id, 0.85)
        except Exception:
            slicer.mrmlScene.RemoveNode(proxy)
            raise
        return self.step6AnatomyReviewState(parameterNode)

    def setStep6AnatomyReviewProxyActive(self, parameterNode, active: bool) -> dict[str, object]:
        """Explicitly accept or disable the reviewed, local proxy for this session."""

        state = self.step6AnatomyReviewState(parameterNode)
        proxy = state.get("proxyNode")
        if proxy is None:
            raise ValueError(_("Create a session anatomy-review copy first."))
        if active:
            if not state.get("historicalOverrideEnabled"):
                raise ValueError(_("Anatomy-review overrides are retired from the baseline."))
            self._validateStep6AnatomyReview(parameterNode, state)
            proxy_segment_id = str(state.get("proxySegmentId") or "")
            surface = self._segmentationSegmentsSurfaceWorld(proxy, {proxy_segment_id})
            if surface is None or surface.GetNumberOfPoints() == 0:
                raise ValueError(_("The reviewed proxy has no closed-surface geometry."))
            topology = surface_topology(surface)
            if topology["boundaryOrNonManifoldEdgeCount"] != 0:
                raise ValueError(
                    _("The reviewed proxy is not closed and watertight; repair it before use.")
                )
            proxy.SetAttribute(
                "DENTOBOT.Step6AnatomyReviewDecision",
                "SEGMENTATION_ARTIFACT_MANUAL_REVIEW",
            )
            proxy.SetAttribute(
                "DENTOBOT.Step6AnatomyReviewAcceptedFingerprint",
                self._step6AnatomyReviewFingerprint(proxy, proxy_segment_id),
            )
        else:
            proxy.SetAttribute("DENTOBOT.Step6AnatomyReviewDecision", "Pending")
        proxy.SetAttribute(
            self._STEP6_ANATOMY_REVIEW_ACTIVE_ATTRIBUTE,
            "true" if active else "false",
        )
        proxy.SetAttribute(
            "DENTOBOT.Step6AnatomyReviewUpdatedUtc",
            datetime.now(timezone.utc).isoformat(),
        )
        return self.step6AnatomyReviewState(parameterNode)

    def discardStep6AnatomyReview(self, parameterNode) -> bool:
        """Discard the proxy only; the source segmentation stays untouched."""

        proxy = self.step6AnatomyReviewProxyNode(parameterNode)
        if proxy is None:
            return False
        slicer.mrmlScene.RemoveNode(proxy)
        return True

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

    @staticmethod
    def _modelRasBounds(node) -> list[float] | None:
        """Return finite world-RAS bounds for a model when available."""

        return RobotSceneSyncLogicMixin._nodeRasBounds(node)

    @staticmethod
    def combinedRasBounds(boundsList: list[list[float]]) -> tuple[float, ...] | None:
        """Combine finite bounds using the shared Slicer RAS convention."""

        return combine_ras_bounds(boundsList)

    def step6CaseViewRasBounds(self, parameterNode) -> tuple[float, ...] | None:
        """Combined world-RAS bounds of the imported case package."""
        bounds_list = [
            bounds
            for node in self.step6CaseViewNodes(parameterNode)
            if (bounds := self._nodeRasBounds(node)) is not None
        ]
        return self.combinedRasBounds(bounds_list)

    def step6ResearchWorkspaceRasBounds(
        self,
        robotModels: list,
        caseModels: list,
    ) -> tuple[float, ...] | None:
        """Combined bounds for the transient robot and Case Foundation scene."""

        bounds_list = [
            self._modelRasBounds(model)
            for model in [*robotModels, *caseModels]
        ]
        return self.combinedRasBounds(
            [bounds for bounds in bounds_list if bounds is not None]
        )

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
                if self.evaluateCaseFoundationEligibility(parameterNode)["pose"]["eligible"]:
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
        del parameterNode
        # Jaw-owned nodes are transformed at the MRML parent boundary already.
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
        return self.getTrajectorySummary(parameterNode.trajectoryLine)

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
        base_transform: vtkMRMLLinearTransformNode,
        outgoing_fingerprint: str,
        opacity: float,
    ) -> vtkMRMLModelNode:
        """Display the exact base-frame payload under its locked base transform."""
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
        node.SetName(f"[Step 6 Audit] {outgoing_id}")
        node.SetAndObserveTransformNodeID(base_transform.GetID())
        node.SetAndObservePolyData(outgoing_base_mm)
        node.SetAttribute("DENTOBOT.CollisionAuditCopy", "true")
        node.SetAttribute("DENTOBOT.MoveItObstacleSource", source_id)
        node.SetAttribute("DENTOBOT.OutgoingCollisionObjectId", outgoing_id)
        node.SetAttribute(
            "DENTOBOT.OutgoingCollisionFingerprint", outgoing_fingerprint
        )
        node.SetAttribute("DENTOBOT.CoordinateFrame", "base_link")
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

    MOUTH_PORTAL_NODE_NAME = "[Step 6] Mouth Portal Vertices"
    MOUTH_PORTAL_ROLE = "Step6MouthPortalVertices"

    def _step6ToothSegmentIdsByFdi(self, segmentation) -> dict[str, str]:
        records = self.getSegmentationReviewRecords(segmentation)
        return {
            str(record["canonicalFdiNumber"]): str(record["segmentId"])
            for record in records
            if record.get("structureType") == "TOOTH" and record.get("canonicalFdiNumber")
        }

    def step6MouthPortalVerticesNode(self):
        for node in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            if node.GetAttribute("DENTOBOT.MarkupsRole") == self.MOUTH_PORTAL_ROLE:
                return node
        return None

    def buildStep6MouthPortalVertices(self, parameterNode, *, replace_existing: bool = False):
        """Auto-derive the 4 canine cusp tips (editable markups) for the mouth portal.

        Lower canines are taken after the virtual mouth opening. A missing
        canine is replaced by the first premolar, then the lateral incisor, and
        the substitution is labelled. Existing operator-edited points are kept
        unless ``replace_existing``.
        """
        from dentobot_workflow.mouth_portal import PORTAL_VERTEX_FDI, choose_vertex_teeth, cusp_tip
        from vtk.util.numpy_support import vtk_to_numpy

        existing = self.step6MouthPortalVerticesNode()
        if existing is not None and existing.GetNumberOfControlPoints() == 4 and not replace_existing:
            return existing
        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            raise ValueError(_("Load the teeth segmentation before building the mouth portal."))
        by_fdi = self._step6ToothSegmentIdsByFdi(segmentation)
        chosen = choose_vertex_teeth(by_fdi)
        points = {}
        for vertex, choice in chosen.items():
            world = self._segmentationSegmentsSurfaceWorld(segmentation, {by_fdi[choice["fdi"]]})
            if world is None or world.GetNumberOfPoints() == 0:
                raise ValueError(_("Mouth portal tooth %1 has no surface.").replace("%1", choice["fdi"]))
            if vertex.startswith(("3", "4")):
                world = self._step6CaseJawPolydataWorld(parameterNode, world)
            points[vertex] = vtk_to_numpy(world.GetPoints().GetData()).astype(float)
        upper = np.mean([points[v].mean(axis=0) for v in ("13", "23")], axis=0)
        lower = np.mean([points[v].mean(axis=0) for v in ("33", "43")], axis=0)
        occlusal_upper = lower - upper  # upper crowns bite toward the lower arch
        tips = {v: cusp_tip(points[v], occlusal_upper if v in ("13", "23") else -occlusal_upper)
                for v in PORTAL_VERTEX_FDI}
        node = existing or slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode", self.MOUTH_PORTAL_NODE_NAME
        )
        node.SetAttribute("DENTOBOT.MarkupsRole", self.MOUTH_PORTAL_ROLE)
        node.SetAttribute("DENTOBOT.IntendedUse", "SimulationPlanningGate")
        node.SetAttribute("DENTOBOT.MouthPortalVertexTeeth", json.dumps(chosen, sort_keys=True))
        # Outward = anterior: away from the posterior teeth (molars, else premolars).
        posterior = []
        for group in (("16", "26", "36", "46"), ("17", "27", "37", "47"), ("15", "25", "35", "45")):
            for fdi in group:
                if fdi in by_fdi:
                    world = self._segmentationSegmentsSurfaceWorld(segmentation, {by_fdi[fdi]})
                    if world is not None and world.GetNumberOfPoints() > 0:
                        if fdi.startswith(("3", "4")):
                            world = self._step6CaseJawPolydataWorld(parameterNode, world)
                        posterior.append(vtk_to_numpy(world.GetPoints().GetData()).astype(float).mean(axis=0))
            if posterior:
                break
        if not posterior:
            raise ValueError(_("No molar or premolar is available to orient the mouth portal outward."))
        node.SetAttribute(
            "DENTOBOT.MouthPortalPosteriorCentroidMm",
            ",".join(f"{float(v):.6f}" for v in np.mean(posterior, axis=0)),
        )
        node.RemoveAllControlPoints()
        for vertex in PORTAL_VERTEX_FDI:
            label = vertex if not chosen[vertex]["substituted"] else f"{vertex}->{chosen[vertex]['fdi']}"
            node.AddControlPoint(vtk.vtkVector3d(*tips[vertex]), label)
        node.CreateDefaultDisplayNodes()
        return node

    def _step6MouthPortalAnteriorPointsWorld(self, parameterNode):
        """Anterior-tooth surface points (lower after mouth opening) for the lip line."""
        from dentobot_workflow.mouth_portal import ANTERIOR_TEETH_FDI
        from vtk.util.numpy_support import vtk_to_numpy

        segmentation = parameterNode.teethSegmentation
        if segmentation is None:
            return None
        by_fdi = self._step6ToothSegmentIdsByFdi(segmentation)
        points = []
        for fdi in ANTERIOR_TEETH_FDI:
            if fdi not in by_fdi:
                continue
            world = self._segmentationSegmentsSurfaceWorld(segmentation, {by_fdi[fdi]})
            if world is None or world.GetNumberOfPoints() == 0:
                continue
            if fdi.startswith(("3", "4")):
                world = self._step6CaseJawPolydataWorld(parameterNode, world)
            points.append(vtk_to_numpy(world.GetPoints().GetData()).astype(float))
        return np.vstack(points) if points else None

    def step6MouthPortal(self, parameterNode, outside_hint_mm=None):
        """Portal from the current (possibly operator-edited) vertex markups."""
        from dentobot_workflow.mouth_portal import build_portal

        node = self.buildStep6MouthPortalVertices(parameterNode)
        if node.GetNumberOfControlPoints() != 4:
            raise ValueError(_("The mouth portal needs exactly 4 vertex points."))
        vertices = []
        for index in range(4):
            position = [0.0, 0.0, 0.0]
            node.GetNthControlPointPositionWorld(index, position)
            vertices.append(position)
        if outside_hint_mm is None:
            # Anterior of the portal: mirror the posterior-teeth centroid through it.
            posterior = [float(v) for v in str(
                node.GetAttribute("DENTOBOT.MouthPortalPosteriorCentroidMm") or ""
            ).split(",") if v.strip()]
            if len(posterior) != 3:
                raise ValueError(_("Rebuild the mouth portal: its outward orientation is missing."))
            centre = np.mean(np.asarray(vertices, dtype=float), axis=0)
            outside_hint_mm = 2.0 * centre - np.asarray(posterior, dtype=float)
        teeth = json.loads(node.GetAttribute("DENTOBOT.MouthPortalVertexTeeth") or "{}")
        mode = self.step6MouthBarrierEdgeMode(parameterNode)
        key = (node.GetMTime(), parameterNode.teethSegmentation.GetMTime(),
               str(parameterNode.step6CaseJawPreparationJson or ""), mode,
               tuple(round(float(v), 6) for v in np.asarray(outside_hint_mm, float)))
        cached = getattr(self, "_step6MouthPortalCache", None)
        if cached is not None and cached[0] == key:
            return cached[1]
        portal = build_portal(vertices, outside_hint_mm, teeth)
        anterior = self._step6MouthPortalAnteriorPointsWorld(parameterNode)
        if anterior is None:
            raise ValueError(_("No anterior tooth surface is available to place the lip-line portal."))
        from dentobot_workflow.mouth_portal import apply_edge_mode, enlarge_portal, shift_portal_to_lip_line
        portal = shift_portal_to_lip_line(portal, anterior)
        if mode == "gum_line":
            upper, lower, sources = self._step6MouthGumPointsWorld(parameterNode)
            portal = apply_edge_mode(portal, mode, upper, lower)
            portal.vertex_teeth["gum_line_sources"] = sources
        else:
            portal = apply_edge_mode(portal, mode)
        portal = enlarge_portal(portal)
        self._step6MouthPortalCache = (key, portal)
        return portal

    MOUTH_BARRIER_MODEL_NAME = "[Step 6] Mouth Barrier"
    MOUTH_BARRIER_ROLE = "Step6MouthBarrierDisplay"

    def step6MouthBarrierEdgeMode(self, parameterNode) -> str:
        """Advanced option (6.3): "gum_line" (default), "biting_edge" or "off"."""
        from dentobot_workflow.mouth_portal import BARRIER_DEFAULT_EDGE_MODE, BARRIER_EDGE_MODES

        mode = str(getattr(parameterNode, "step6MouthBarrierEdgeMode", "") or BARRIER_DEFAULT_EDGE_MODE)
        return mode if mode in BARRIER_EDGE_MODES else BARRIER_DEFAULT_EDGE_MODE

    def _step6MouthGumPointsWorld(self, parameterNode):
        """Gum points of the anterior teeth (13..23 upper, 33..43 lower after mouth
        opening): most occlusal jaw-bone-covered tooth point + 2 mm toward the
        biting edge; crown-height estimate when no jaw bone is segmented."""
        from dentobot_workflow.mouth_portal import cusp_tip, gum_points_from_crest
        from vtk.util.numpy_support import vtk_to_numpy

        segmentation = parameterNode.teethSegmentation
        by_fdi = self._step6ToothSegmentIdsByFdi(segmentation)
        groups = self.step6CaseJawSegmentIds(segmentation)
        arches = {"upper": ("13", "12", "11", "21", "22", "23"), "lower": ("33", "32", "31", "41", "42", "43")}
        teeth, distance = {}, {}
        for arch, fdis in arches.items():
            for fdi in fdis:
                if fdi not in by_fdi:
                    continue
                world = self._segmentationSegmentsSurfaceWorld(segmentation, {by_fdi[fdi]})
                if world is None or world.GetNumberOfPoints() == 0:
                    continue
                if arch == "lower":
                    world = self._step6CaseJawPolydataWorld(parameterNode, world)
                points = vtk_to_numpy(world.GetPoints().GetData()).astype(float)
                teeth[(arch, fdi)] = points[:: max(1, len(points) // 4000)]
            jaw_ids = set(groups.get("upperJaw" if arch == "upper" else "lowerJaw", ()))
            jaw = self._segmentationSegmentsSurfaceWorld(segmentation, jaw_ids) if jaw_ids else None
            if jaw is not None and jaw.GetNumberOfPoints() and arch == "lower":
                jaw = self._step6CaseJawPolydataWorld(parameterNode, jaw)
            if jaw is not None and jaw.GetNumberOfPoints():
                implicit = vtk.vtkImplicitPolyDataDistance()
                implicit.SetInput(jaw)
                distance[arch] = implicit
        upper_all = [p for (arch, _f), p in teeth.items() if arch == "upper"]
        lower_all = [p for (arch, _f), p in teeth.items() if arch == "lower"]
        if not upper_all or not lower_all:
            raise ValueError(_("Gum-line mouth barrier needs upper and lower anterior teeth."))
        occlusal = np.vstack(lower_all).mean(axis=0) - np.vstack(upper_all).mean(axis=0)
        occlusal /= np.linalg.norm(occlusal)
        out = {"upper": [], "lower": []}
        sources = {}
        for (arch, fdi), points in teeth.items():
            direction = occlusal if arch == "upper" else -occlusal
            implicit = distance.get(arch)
            bone = (np.array([implicit.EvaluateFunction(tuple(p)) for p in points])
                    if implicit is not None else np.full(len(points), np.inf))
            point, source = gum_points_from_crest(points, bone, direction, cusp_tip(points, direction))
            out[arch].append(point)
            sources[fdi] = source
        return np.asarray(out["upper"]), np.asarray(out["lower"]), sources

    def step6MouthBarrier(self, parameterNode):
        """3D mouth barrier (lip slab + cheek walls) for the current opening, or None when off."""
        from dentobot_workflow.mouth_portal import build_mouth_barrier
        from vtk.util.numpy_support import vtk_to_numpy

        if self.step6MouthBarrierEdgeMode(parameterNode) == "off":
            return None
        opening = self.step6MouthPortal(parameterNode)
        segmentation = parameterNode.teethSegmentation
        groups = self.step6CaseJawSegmentIds(segmentation)
        lower = set(groups.get("lower", ()))
        teeth_ids = set((*groups.get("upperTeeth", ()), *groups.get("lowerTeeth", ())))
        teeth, extent = [], []
        for segment_id in dict.fromkeys((*groups.get("upper", ()), *groups.get("lower", ()))):
            world = self._segmentationSegmentsSurfaceWorld(segmentation, {segment_id})
            if world is None or world.GetNumberOfPoints() == 0:
                continue
            if segment_id in lower:
                world = self._step6CaseJawPolydataWorld(parameterNode, world)
            points = vtk_to_numpy(world.GetPoints().GetData()).astype(float)
            extent.append(points)
            if segment_id in teeth_ids:
                teeth.append(points)
        if not teeth:
            raise ValueError(_("The mouth barrier needs segmented teeth."))
        return build_mouth_barrier(opening, np.vstack(extent), np.vstack(teeth))

    def step6MouthBarrierPolydataWorld(self, parameterNode) -> list:
        """[(part_name, closed vtkPolyData world RAS mm)] for MoveIt and preflight; [] when off."""
        barrier = self.step6MouthBarrier(parameterNode)
        if barrier is None:
            for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
                if node.GetAttribute("DENTOBOT.ModelRole") == self.MOUTH_BARRIER_ROLE and node.GetDisplayNode():
                    node.GetDisplayNode().SetVisibility(False)
            return []
        parts = []
        for part in barrier.parts:
            points = vtk.vtkPoints()
            for point in part.points_mm:
                points.InsertNextPoint(*(float(v) for v in point))
            cells = vtk.vtkCellArray()
            for tri in part.triangles:
                cells.InsertNextCell(3)
                for index in tri:
                    cells.InsertCellPoint(int(index))
            polydata = vtk.vtkPolyData()
            polydata.SetPoints(points)
            polydata.SetPolys(cells)
            parts.append((part.name, polydata))
        self._showStep6MouthBarrier(parts, barrier.summary,
                                    bool(getattr(parameterNode, "step6ShowMouthBarrier", True)),
                                    float(getattr(parameterNode, "step6MouthBarrierOpacity", 0.12)))
        return parts

    def setStep6MouthBarrierVisible(self, visible: bool) -> None:
        """Show/hide the barrier display model only; MoveIt keeps the barrier."""
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if node.GetAttribute("DENTOBOT.ModelRole") == self.MOUTH_BARRIER_ROLE and node.GetDisplayNode():
                node.GetDisplayNode().SetVisibility(bool(visible))

    def setStep6MouthBarrierOpacity(self, opacity: float) -> None:
        """Display opacity of the barrier model only; MoveIt keeps the barrier."""
        opacity = min(1.0, max(0.0, float(opacity)))
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if node.GetAttribute("DENTOBOT.ModelRole") == self.MOUTH_BARRIER_ROLE and node.GetDisplayNode():
                node.SetAttribute("DENTOBOT.DisplayOpacity", f"{opacity:.2f}")
                node.GetDisplayNode().SetOpacity(opacity)

    TASK_SPACE_BOX_ROLE = "Step6TaskSpaceBox"
    TASK_SPACE_BOX_MODEL_NAME = "[Step 6] Task-Space Box (incisor-centred, display only)"

    def updateStep6TaskSpaceBox(self, center_world_ras_mm, side_mm: float, opacity: float,
                                visible: bool) -> None:
        """Optional cube around the incisor-centred task space (operator 2026-10-03).

        Display only: it neither bounds sampling nor enters the MoveIt scene. Cool
        blue with edges so it stays distinct from the rose mouth barrier.
        """
        node = next((n for n in slicer.util.getNodesByClass("vtkMRMLModelNode")
                     if n.GetAttribute("DENTOBOT.ModelRole") == self.TASK_SPACE_BOX_ROLE), None)
        if not visible or center_world_ras_mm is None:
            if node is not None and node.GetDisplayNode():
                node.GetDisplayNode().SetVisibility(False)
            return
        side = float(side_mm)
        if not side > 0.0:
            raise ValueError("Task-space box side length must be positive.")
        cube = vtk.vtkCubeSource()
        cube.SetCenter(*(float(value) for value in center_world_ras_mm))
        cube.SetXLength(side)
        cube.SetYLength(side)
        cube.SetZLength(side)
        cube.Update()
        if node is None:
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", self.TASK_SPACE_BOX_MODEL_NAME)
            node.SetAttribute("DENTOBOT.ModelRole", self.TASK_SPACE_BOX_ROLE)
            node.SaveWithSceneOff()
        surface = vtk.vtkPolyData()
        surface.DeepCopy(cube.GetOutput())
        node.SetAndObservePolyData(surface)
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        display.SetColor(0.20, 0.55, 1.0)
        display.SetEdgeVisibility(True)
        display.SetEdgeColor(0.35, 0.70, 1.0)
        display.SetOpacity(min(1.0, max(0.0, float(opacity))))
        display.SetVisibility2D(False)
        display.SetVisibility(True)

    def step6TaskSpaceBoxShown(self) -> bool:
        return any(n.GetAttribute("DENTOBOT.ModelRole") == self.TASK_SPACE_BOX_ROLE
                   and n.GetDisplayNode() is not None and bool(n.GetDisplayNode().GetVisibility())
                   for n in slicer.util.getNodesByClass("vtkMRMLModelNode"))

    @staticmethod
    def setStep6ViewFrameBoxVisible(visible: bool) -> None:
        """Slicer's magenta 3D-view frame box (not task space); hidden in Step 6."""
        for view_node in slicer.util.getNodesByClass("vtkMRMLViewNode"):
            if bool(view_node.GetBoxVisible()) != bool(visible):
                view_node.SetBoxVisible(bool(visible))

    @staticmethod
    def setStep6DepthPeeling(enabled: bool) -> None:
        """3D-view depth peeling (display only; operator run option 2026-10-03)."""
        for view_node in slicer.util.getNodesByClass("vtkMRMLViewNode"):
            if bool(view_node.GetUseDepthPeeling()) != bool(enabled):
                view_node.SetUseDepthPeeling(bool(enabled))

    @staticmethod
    def step6DepthPeelingEnabled() -> bool:
        views = slicer.util.getNodesByClass("vtkMRMLViewNode")
        return all(bool(view_node.GetUseDepthPeeling()) for view_node in views) if views else True

    def _showStep6MouthBarrier(self, parts, summary, visible: bool = True,
                               opacity: float = 0.12) -> None:
        """Display-only model so the barrier is visible in the viewport and recordings."""
        node = next((n for n in slicer.util.getNodesByClass("vtkMRMLModelNode")
                     if n.GetAttribute("DENTOBOT.ModelRole") == self.MOUTH_BARRIER_ROLE), None)
        if node is None:
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", self.MOUTH_BARRIER_MODEL_NAME)
            node.SetAttribute("DENTOBOT.ModelRole", self.MOUTH_BARRIER_ROLE)
            node.SetAttribute("DENTOBOT.IntendedUse", "SimulationPlanningGate")
            node.SaveWithSceneOff()
        merged = vtk.vtkAppendPolyData()
        for _name, polydata in parts:
            merged.AddInputData(polydata)
        merged.Update()
        surface = vtk.vtkPolyData()
        surface.DeepCopy(merged.GetOutput())
        node.SetAndObservePolyData(surface)
        node.SetAttribute("DENTOBOT.MouthBarrierSummary", json.dumps(summary, sort_keys=True))
        opacity = min(1.0, max(0.0, float(opacity)))
        node.SetAttribute("DENTOBOT.DisplayOpacity", f"{opacity:.2f}")
        node.CreateDefaultDisplayNodes()
        display = node.GetDisplayNode()
        if display:
            display.SetColor(0.95, 0.45, 0.60)
            display.SetOpacity(opacity)
            display.SetVisibility(bool(visible))
            display.SetVisibility2D(False)

    def checkStep6MouthPortalGate(self, parameterNode, tcp_path_world_ras_mm) -> dict:
        """Gate: the TCP path must enter the mouth through the barrier opening."""
        from dentobot_workflow.mouth_portal import check_tcp_path

        mode = self.step6MouthBarrierEdgeMode(parameterNode)
        if mode == "off":
            return {"status": "skipped", "reason": "mouth_barrier_off", "edge_mode": mode}
        portal = self.step6MouthPortal(parameterNode)
        result = check_tcp_path(portal, tcp_path_world_ras_mm)
        result["edge_mode"] = mode
        result["vertex_teeth"] = portal.vertex_teeth
        result["portal_vertices_ras_mm"] = portal.vertices_mm.tolist()
        return result

    def syncStep6MoveItPlanningScene(
        self,
        parameterNode,
        *,
        expected_policy_fingerprint: str = "",
        require_correlated_readback: bool = False,
        defer_runtime_acknowledgement: bool = False,
        progress=None,
    ) -> int:
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
        model_candidates = guidance_models
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
                and model.GetAttribute("DENTOBOT.JawOwner") == "MovingLower"
            )
            if is_target_attached:
                prepared_world = self._step6TargetAttachedPolydataWorld(
                    parameterNode,
                    source_world,
                )
            if prepared_world is None or prepared_world.GetNumberOfPoints() == 0:
                continue
            if model is parameterNode.finalPrintableTemplateModel:
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
                # Keep the same normalized shape as step6CaseJawSegmentIds.
                "upper": (),
                "lower": (),
            }
        )
        lowerIds = set(jawGroups["lower"])
        toothIds = set(
            (*jawGroups.get("upperTeeth", ()), *jawGroups.get("lowerTeeth", ()))
        )
        anatomyIds = tuple(
            dict.fromkeys((*jawGroups.get("upper", ()), *jawGroups.get("lower", ())))
        )
        if progress:
            progress("Preparing collision anatomy", 0, len(anatomyIds))
        for segmentIndex, segmentId in enumerate(anatomyIds, start=1):
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
            # A reviewed proxy can replace collision geometry only for one
            # explicitly confirmed local artifact. Keep the original source
            # world mesh and canonical object identity in the audit so the
            # collision-scene record explains exactly what was substituted.
            review_state = self.step6AnatomyReviewState(parameterNode)
            review_proxy = review_state.get("proxyNode")
            review_active = bool(
                review_state.get("effectiveActive")
                and str(review_state.get("sourceSegmentId") or "") == str(segmentId)
                and review_proxy is not None
            )
            collisionWorld = sourceWorld
            if review_active:
                self._validateStep6AnatomyReview(parameterNode, review_state)
                collisionWorld = self._segmentationSegmentsSurfaceWorld(
                    review_proxy,
                    {str(review_state.get("proxySegmentId") or segmentId)},
                )
                if collisionWorld is None or collisionWorld.GetNumberOfPoints() == 0:
                    raise ValueError(
                        _("The active reviewed anatomy proxy has no collision surface.")
                    )
            preparedWorld = collisionWorld
            if isMoving:
                preparedWorld = self._step6CaseJawPolydataWorld(
                    parameterNode,
                    collisionWorld,
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
                classification=(
                    "reviewed-session-proxy-moving"
                    if review_active and isMoving
                    else "reviewed-session-proxy-fixed"
                    if review_active
                    else "moving"
                    if isMoving
                    else "fixed"
                ),
                source_world=sourceWorld,
                prepared_world=collisionSurface,
                jaw_transform_applied=isMoving,
            )
            if progress:
                progress("Preparing collision anatomy", segmentIndex, len(anatomyIds))

        # 3D mouth barrier (operator 2026-10-02): virtual lips/cheeks as hard
        # obstacles for the whole robot. Edge mode "off" publishes nothing.
        if segmentation is not None and self.step6MouthBarrierEdgeMode(parameterNode) != "off":
            try:
                barrier_parts = self.step6MouthBarrierPolydataWorld(parameterNode)
            except (ValueError, np.linalg.LinAlgError) as exc:
                raise ValueError(
                    _("The 3D mouth barrier could not be built: %1. Set the mouth barrier "
                      "edges to Off in the 6.3 advanced options to plan without it.").replace("%1", str(exc))
                ) from exc
            for part_name, part_world in barrier_parts:
                append_source(
                    source_id=f"{segmentation.GetID()}:mouth-barrier:{part_name}",
                    source_name=f"dentobot_mouth_barrier_{part_name}",
                    source_role="mouth-barrier",
                    classification="virtual-barrier",
                    source_world=part_world,
                    prepared_world=part_world,
                    jaw_transform_applied=False,
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
        if progress:
            progress("Publishing collision scene", 0, len(sources))
        pause_render = getattr(slicer.app, "pauseRender", None)
        resume_render = getattr(slicer.app, "resumeRender", None)
        rendering_paused = False
        try:
            if callable(pause_render) and callable(resume_render):
                pause_render()
                rendering_paused = True
            for sourceIndex, source in enumerate(sources, start=1):
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
                    # The published mesh vertices are already expressed in
                    # base_link, so the CollisionObject pose must be identity.
                    # Keep this explicit for the runtime readback contract.
                    "outgoing_pose_base_link_m_xyzw": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
                    "outgoing_pose_source": "vertices_already_in_base_link_frame",
                    "outgoing_collision_object_id": source_name,
                    "publish_status": "Pending",
                    "runtime_acknowledgement_status": "NotQueried",
                }
                self._syncCollisionAuditDisplayCopy(
                    source_id=source_id,
                    outgoing_id=source_name,
                    outgoing_base_mm=outgoing_evidence["surface"],
                    base_transform=base_transform,
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
                if progress:
                    progress("Publishing collision scene", sourceIndex, len(sources))
        finally:
            if rendering_paused:
                resume_render()
        if progress:
            progress("Checking MoveIt collision-scene readback", None, None)
        current_joint_positions_si = monitored_joint_positions_si()
        if any(
            name not in current_joint_positions_si for name in JOINT_NAMES
        ):
            current_joint_positions_si = joint_positions_si_from_display(
                parameterNode.robotJoint1Deg,
                parameterNode.robotJoint2Mm,
                parameterNode.robotJoint3Deg,
                parameterNode.robotJoint4Mm,
                parameterNode.robotJoint5Deg,
            )
        if defer_runtime_acknowledgement:
            acknowledgement = {
                "status": "Deferred",
                "reason": (
                    "Ordinary joint-status readback was deferred; the diagnostic "
                    "task-status request must prove exact scene identity and policy."
                ),
                "acknowledged_object_ids": [],
                "mismatches": [],
                "expected_policy_fingerprint": expected_policy_fingerprint or None,
                "readback_correlated": False,
                "trusted": False,
                "attribution_allowed": False,
            }
        else:
            acknowledgement = acknowledge_moveit_collision_scene(
                expected_objects=object_records,
                current_joint_positions_si=current_joint_positions_si,
                expected_policy_fingerprint=expected_policy_fingerprint,
                require_correlated_readback=require_correlated_readback,
            )
        audit = build_collision_scene_audit(
            status=(
                "Acknowledged"
                if acknowledgement.get("status") == "Acknowledged"
                else "RuntimeAcknowledgementDeferred"
                if defer_runtime_acknowledgement
                else "RuntimeAcknowledgementFailed"
            ),
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            jaw_preparation_fingerprint=jaw_preparation_fingerprint,
            world_to_base_fingerprint=world_to_base_fingerprint,
            object_records=object_records,
            runtime_acknowledgement=acknowledgement,
        )
        if prior_audit is not None:
            previous = prior_audit.to_dict()
            current = audit.to_dict()
            for item in (previous, current):
                item.pop("generated_at_utc", None)
                item.pop("audit_fingerprint", None)
            if previous == current:
                # A fresh, identical acknowledgement must not stale validated Home.
                audit = prior_audit
        parameterNode.step6CollisionSceneAuditJson = canonical_json(audit.to_dict())
        if (
            prior_audit is not None
            and prior_audit.audit_fingerprint != audit.audit_fingerprint
        ):
            self.markStep6MotionDiagnosticStale(
                parameterNode,
                _("Collision-scene payload or runtime acknowledgement changed."),
            )
        if defer_runtime_acknowledgement:
            return len(sources)
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
