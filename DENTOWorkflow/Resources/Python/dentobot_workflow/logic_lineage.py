"""Extracted workflow lineage methods; public APIs remain on WorkflowLogicMixin."""

from __future__ import annotations

from .runtime import *
from .dental_semantics import (
    associate_pulp_components,
    enclosed_tooth_void,
    occupied_components,
    semantic_document,
)


class MissingTargetPulpError(ValueError):
    """The selected tooth has no associated pulp mask yet."""


class LineageLogicMixin:
    PULP_REPORT_ATTRIBUTE = "DENTOBOT.PulpInventoryJson"

    def _pulpInventoryFingerprint(self, segmentationNode, records):
        """Fingerprint segment identity and binary geometry without report state."""
        digest = hashlib.sha256()
        segmentation = segmentationNode.GetSegmentation()
        for record in sorted(records, key=lambda item: item["segmentId"]):
            segmentId = record["segmentId"]
            segment = segmentation.GetSegment(segmentId)
            digest.update(json.dumps([
                segmentId, record.get("structureType"),
                record.get("canonicalFdiNumber"),
            ], separators=(",", ":")).encode())
            image = slicer.vtkOrientedImageData()
            if not segmentationNode.GetBinaryLabelmapRepresentation(segmentId, image):
                digest.update(b"no-labelmap")
                continue
            matrix = vtk.vtkMatrix4x4()
            image.GetImageToWorldMatrix(matrix)
            source = slicer.util.arrayFromSegmentInternalBinaryLabelmap(segmentationNode, segmentId)
            points = np.argwhere(source == int(segment.GetLabelValue()))
            if len(points):
                ijk = points[:, ::-1] + np.asarray(image.GetExtent()[::2], dtype=np.int64)
                affine = np.asarray([[matrix.GetElement(i, j) for j in range(4)] for i in range(3)])
                world = ijk @ affine[:, :3].T + affine[:, 3]
                digest.update(np.ascontiguousarray(np.rint(world * 1000).astype("<i8")).tobytes())
        return digest.hexdigest()

    def getPulpInventoryReport(self, segmentationNode):
        raw = segmentationNode.GetAttribute(self.PULP_REPORT_ATTRIBUTE) if segmentationNode else None
        if not raw:
            return None
        try:
            report = json.loads(raw)
            if report.get("schemaVersion") != 1:
                return None
            records = self.getSegmentationReviewRecords(segmentationNode)
            report["stale"] = report.get("fingerprint") != self._pulpInventoryFingerprint(segmentationNode, records)
            return report
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def checkPulpInventory(self, segmentationNode, progress=None):
        """Audit one run; only the report attribute is written."""
        records = self.getSegmentationReviewRecords(segmentationNode)
        metadata = segmentationNode.GetAttribute("DENTOBOT.SegmentMetricsJson") or ""
        try:
            document = json.loads(metadata)
            sourceMetrics = {
                str(item.get("segmentId")): item
                for item in document.get("segments", [])
                if isinstance(item, dict) and item.get("segmentId")
            }
            segmentation = segmentationNode.GetSegmentation()
            sourceBacked = bool(sourceMetrics) and all(
                record["segmentId"] in sourceMetrics
                and sourceMetrics[record["segmentId"]].get("sourceName")
                and int(sourceMetrics[record["segmentId"]].get("labelId") or -1)
                == int(segmentation.GetSegment(record["segmentId"]).GetLabelValue())
                for record in records if record.get("structureType") == "TOOTH"
            )
            trusted = (isinstance(document.get("semantic"), dict) or sourceBacked) and not self._semanticPersistenceIssues(segmentationNode, records)
            trusted = trusted and segmentationNode.GetAttribute(self.SEMANTIC_PERSISTENCE_ATTRIBUTE) != "stale"
        except (TypeError, ValueError, json.JSONDecodeError):
            trusted = False
        try:
            self.getSegmentationSourceVolume(segmentationNode)
            hasSource = True
        except (TypeError, ValueError, RuntimeError):
            hasSource = False
        teeth = [record for record in records if record.get("structureType") == "TOOTH"]
        knownFdi = {str(record.get("canonicalFdiNumber")) for record in teeth if record.get("canonicalFdiNumber")}
        counts = {"associated": 0, "missing": 0, "candidate": 0, "cannot-evaluate": 0, "ambiguous": 0}
        rows = []
        for index, tooth in enumerate(sorted(teeth, key=lambda item: (str(item.get("canonicalFdiNumber") or "99"), item["segmentId"])), 1):
            toothId = tooth["segmentId"]
            fdi = str(tooth.get("canonicalFdiNumber") or "")
            row = {"fdi": fdi, "toothSegmentId": toothId, "pulpSegmentId": "", "status": "", "reason": "", "voxelCount": 0,
                   "reviewState": self.getSegmentationReviewState(segmentationNode)}
            if not trusted or not hasSource or tooth.get("validationState") not in {"VALID", "MANUALLY_CONFIRMED"} or not fdi:
                row.update(status="cannot-evaluate", reason="Trusted tooth identity, semantic metadata, or source volume is unavailable")
            elif sum(str(item.get("canonicalFdiNumber") or "") == fdi for item in teeth) != 1:
                row.update(status="ambiguous", reason="Multiple tooth masks claim this FDI identity")
            else:
                try:
                    association = self.getTargetPulpAssociation(segmentationNode, toothId, persist=False, requireReview=False)
                    pulpId = association["pulpSegmentId"]
                    segment = segmentationNode.GetSegmentation().GetSegment(pulpId)
                    derivation = vtk.mutable("")
                    isCandidate = segment.GetTag("DENTOBOT.Derivation", derivation) and str(derivation) == "enclosed-tooth-void-v1"
                    row.update(status="candidate" if isCandidate else "associated", pulpSegmentId=pulpId)
                    if isCandidate:
                        row["voxelCount"] = int(np.count_nonzero(slicer.util.arrayFromSegmentInternalBinaryLabelmap(segmentationNode, pulpId) == int(segment.GetLabelValue())))
                except MissingTargetPulpError:
                    row.update(status="missing", reason="No associated pulp mask; enclosed-void preparation may be attempted")
                except (TypeError, ValueError, RuntimeError) as exc:
                    row.update(status="ambiguous", reason=str(exc))
            counts[row["status"]] += 1
            rows.append(row)
            if progress:
                progress(index, len(teeth), fdi)
        absent = [f"{quadrant}{number}" for quadrant in range(1, 5) for number in range(1, 9) if f"{quadrant}{number}" not in knownFdi]
        report = {"schemaVersion": 1, "fingerprint": self._pulpInventoryFingerprint(segmentationNode, records),
                  "counts": counts, "rows": rows, "absentFdi": absent, "runId": segmentationNode.GetAttribute("DENTOBOT.RunId") or ""}
        segmentationNode.SetAttribute(self.PULP_REPORT_ATTRIBUTE, json.dumps(report, sort_keys=True, separators=(",", ":")))
        return report

    def createMissingPulpCandidates(self, segmentationNode, progress=None):
        report = self.getPulpInventoryReport(segmentationNode)
        if not report or report.get("stale"):
            raise ValueError(_("Check Pulp Masks for this run before creating candidates."))
        outcomes = {}
        pending = [row for row in report["rows"] if row["status"] in {"missing", "failed"}]
        for index, row in enumerate(pending, 1):
            if progress:
                progress(index - 1, len(pending), row["fdi"])
            if row["status"] not in {"missing", "failed"}:
                continue
            try:
                toothId = row["toothSegmentId"]
                fdi = row["fdi"]
                candidateId, count = self._createEnclosedPulpCandidate(segmentationNode, toothId, fdi, invalidateReview=False)
                outcomes[toothId] = ("created", candidateId, count, "Review this derived mask before planning")
            except (TypeError, ValueError, RuntimeError) as exc:
                outcomes[row["toothSegmentId"]] = ("failed", "", 0, str(exc))
            if progress:
                progress(index, len(pending), row["fdi"])
        if any(outcome[0] == "created" for outcome in outcomes.values()):
            self.invalidateSegmentationReviewAfterEdit(segmentationNode)
            if self.getSegmentationReviewState(segmentationNode) != "Needs Correction":
                self.setSegmentationReviewState(segmentationNode, "Needs Correction")
            segmentationNode.SetAttribute("DENTOBOT.ReviewInvalidationReason", "Derived pulp candidates require Step 2 review")
        final = {key: value for key, value in report.items() if key != "stale"}
        for row in final["rows"]:
            outcome = outcomes.get(row["toothSegmentId"])
            if outcome:
                row.update(status=outcome[0], pulpSegmentId=outcome[1], voxelCount=outcome[2], reason=outcome[3])
                row["reviewState"] = self.getSegmentationReviewState(segmentationNode)
        final["counts"] = {
            key: sum(row["status"] == key or (key == "candidate" and row["status"] == "created")
                     or (key == "missing" and row["status"] == "failed") for row in final["rows"])
            for key in ("associated", "missing", "candidate", "cannot-evaluate", "ambiguous")
        }
        final["fingerprint"] = self._pulpInventoryFingerprint(
            segmentationNode, self.getSegmentationReviewRecords(segmentationNode)
        )
        final["createdCount"] = sum(outcome[0] == "created" for outcome in outcomes.values())
        final["failedCount"] = sum(outcome[0] == "failed" for outcome in outcomes.values())
        segmentationNode.SetAttribute(self.PULP_REPORT_ATTRIBUTE, json.dumps(final, sort_keys=True, separators=(",", ":")))
        return final

    def _derivedPulpAssociation(self, segmentationNode, records, toothId, fdi, requireReview=True):
        """Validate a reviewed derived mask against its source tooth envelope."""

        segmentation = segmentationNode.GetSegmentation()
        matches = []
        for record in records:
            segmentId = record["segmentId"]
            segment = segmentation.GetSegment(segmentId)
            derivation, parent = vtk.mutable(""), vtk.mutable("")
            if not segment.GetTag("DENTOBOT.Derivation", derivation):
                continue
            if str(derivation) != "enclosed-tooth-void-v1":
                continue
            if segment.GetTag("DENTOBOT.SourceToothSegmentID", parent) and str(parent) == toothId:
                matches.append(record)
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError(_("Multiple derived pulp masks claim the selected tooth."))
        if requireReview and self.getSegmentationReviewState(segmentationNode) != "Reviewed":
            raise ValueError(_("Review the derived pulp mask in Step 2 before assisted generation."))
        record = matches[0]
        reference = self.getSegmentationSourceVolume(segmentationNode)
        tooth = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, toothId, reference)
        expected = set(enclosed_tooth_void([tuple(point) for point in np.argwhere(tooth > 0)]))
        mask = slicer.util.arrayFromSegmentBinaryLabelmap(segmentationNode, record["segmentId"], reference)
        actual = {tuple(point) for point in np.argwhere(mask > 0)}
        if mask.shape != tooth.shape or actual != expected:
            raise ValueError(_("The reviewed derived pulp mask no longer matches the tooth's enclosed void."))
        componentId = f"{record['segmentId']}#component-1"
        association = {
            "validationState": "VALID",
            "associationConfidence": "HIGH",
            "parentToothSegmentIds": [toothId],
            "sourceSegmentIds": [record["segmentId"]],
            "associationMethod": "enclosed-tooth-void-v1",
            "components": [{
                "componentId": componentId,
                "sourceSegmentId": record["segmentId"],
                "selected": {"toothSegmentId": toothId, "toothFdiNumber": fdi},
            }],
        }
        return record, association

    def _createEnclosedPulpCandidate(self, segmentationNode, toothId, fdi, *, invalidateReview=True):
        """Make a reviewable pulp segment from one empty closed tooth pocket."""

        segmentation = segmentationNode.GetSegmentation()
        toothSegment = segmentation.GetSegment(toothId)
        source = slicer.util.arrayFromSegmentInternalBinaryLabelmap(segmentationNode, toothId)
        tooth = source == int(toothSegment.GetLabelValue())
        occupied = np.argwhere(tooth)
        if len(occupied) == 0:
            raise ValueError(_("The selected tooth mask is empty."))
        low, high = occupied.min(axis=0), occupied.max(axis=0)
        if np.any(low == 0) or np.any(high == np.asarray(tooth.shape) - 1):
            raise ValueError(_("The tooth touches the image boundary; its interior cannot be confirmed."))
        cavity = enclosed_tooth_void([tuple(point) for point in occupied])
        if any(source[point] != 0 for point in cavity):
            raise ValueError(_("The enclosed tooth region is occupied by another source label."))
        image = slicer.vtkOrientedImageData()
        if not segmentationNode.GetBinaryLabelmapRepresentation(toothId, image):
            raise ValueError(_("The tooth image geometry is unavailable."))
        offset = np.asarray(image.GetExtent()[::2][::-1], dtype=int)
        reference = self.getSegmentationSourceVolume(segmentationNode)
        alignedTooth = slicer.util.arrayFromSegmentBinaryLabelmap(
            segmentationNode, toothId, reference
        )
        alignedOccupied = occupied + offset
        if (
            np.any(alignedOccupied < 0)
            or np.any(alignedOccupied >= np.asarray(alignedTooth.shape))
            or int(np.count_nonzero(alignedTooth)) != len(occupied)
            or not np.all(alignedTooth[tuple(alignedOccupied.T)] > 0)
        ):
            raise ValueError(_("The tooth labelmap and source volume geometry do not align."))
        alignedCavity = np.asarray(cavity, dtype=int) + offset
        mask = np.zeros(alignedTooth.shape, dtype=np.uint8)
        mask[tuple(alignedCavity.T)] = 1
        attributes = (
            "DENTOBOT.SegmentMetricsJson",
            self.SEMANTIC_STATUS_ATTRIBUTE,
            self.SEMANTIC_FINGERPRINT_ATTRIBUTE,
            self.SEMANTIC_PERSISTENCE_ATTRIBUTE,
            "DENTOBOT.ReviewState",
            "DENTOBOT.ReviewUpdatedUtc",
            "DENTOBOT.LastSegmentationEditUtc",
            "DENTOBOT.SegmentMetricsValidity",
            "DENTOBOT.ReviewInvalidationReason",
        )
        previous = {key: segmentationNode.GetAttribute(key) for key in attributes}
        candidateId = segmentation.AddEmptySegment(
            f"dentobot-derived-pulp-fdi{fdi}", f"derived_pulp_fdi1{fdi}", (1.0, 0.6, 0.1)
        )
        try:
            slicer.util.updateSegmentBinaryLabelmapFromArray(
                mask, segmentationNode, candidateId, reference
            )
            candidate = segmentation.GetSegment(candidateId)
            candidate.SetTag("DENTOBOT.Derivation", "enclosed-tooth-void-v1")
            candidate.SetTag("DENTOBOT.SourceToothSegmentID", toothId)
            metrics = json.loads(segmentationNode.GetAttribute("DENTOBOT.SegmentMetricsJson") or "{}")
            volume = float(abs(np.prod(image.GetSpacing())) * len(cavity))
            metrics.setdefault("segments", []).append({
                "segmentId": candidateId,
                "labelId": int(candidate.GetLabelValue()),
                "sourceName": candidate.GetName(),
                "voxelCount": len(cavity),
                "volumeMm3": volume,
            })
            records = self._semanticRecordsFromMetrics(segmentationNode)
            metrics["semantic"] = semantic_document(records)
            wasModifying = segmentationNode.StartModify()
            try:
                segmentationNode.SetAttribute("DENTOBOT.SegmentMetricsJson", json.dumps(metrics, sort_keys=True, separators=(",", ":")))
                self._setSemanticMetadataAttributes(segmentationNode, metrics["semantic"], persistenceState="current")
            finally:
                segmentationNode.EndModify(wasModifying)
            if invalidateReview:
                self.invalidateSegmentationReviewAfterEdit(segmentationNode)
                if self.getSegmentationReviewState(segmentationNode) != "Needs Correction":
                    self.setSegmentationReviewState(segmentationNode, "Needs Correction")
                segmentationNode.SetAttribute(
                    "DENTOBOT.ReviewInvalidationReason",
                    f"Derived pulp candidate for FDI{fdi} requires Step 2 review",
                )
        except Exception:
            segmentation.RemoveSegment(candidateId)
            for key, value in previous.items():
                segmentationNode.SetAttribute(key, value)
            raise
        return candidateId, len(cavity)

    def prepareTargetPulpMask(self, segmentationNode, toothId):
        """Check existing pulp or create one reviewable enclosed-void candidate."""

        try:
            association = self.getTargetPulpAssociation(segmentationNode, toothId)
        except MissingTargetPulpError:
            tooth = self.validateTargetTooth(segmentationNode, toothId)
            fdi = str(tooth.get("canonicalFdiNumber") or tooth.get("fdiNumber"))
            candidateId, count = self._createEnclosedPulpCandidate(
                segmentationNode, toothId, fdi
            )
            return {"status": "created", "pulpSegmentId": candidateId, "voxelCount": count}
        return {"status": "ready", "pulpSegmentId": association["pulpSegmentId"]}

    def getScalarVolumeNodes(self) -> list[vtkMRMLScalarVolumeNode]:
        return list(slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"))

    def getLatestScalarVolumeNode(self) -> vtkMRMLScalarVolumeNode | None:
        volumeNodes = self.getScalarVolumeNodes()
        return volumeNodes[-1] if volumeNodes else None

    def getLatestTeethSegmentationNode(self) -> vtkMRMLSegmentationNode | None:
        """Return the latest Bridge C result, without selecting unrelated nodes."""

        segmentationNodes = list(
            slicer.util.getNodesByClass("vtkMRMLSegmentationNode")
        )
        bridgeResults = [
            node
            for node in segmentationNodes
            if node.GetAttribute("DENTOBOT.BridgeOperation") == "segment-teeth"
        ]
        return bridgeResults[-1] if bridgeResults else None

    def getTargetToothRecords(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
    ) -> list[dict]:
        """Return only whole-tooth segments eligible for draft targeting."""

        return [
            record
            for record in self.getSegmentationReviewRecords(segmentationNode)
            if record.get("structureType") == "TOOTH"
            and record.get("canonicalName")
            and record.get("canonicalFdiNumber")
            and record.get("validationState") in {"VALID", "MANUALLY_CONFIRMED"}
        ]

    @staticmethod
    def dentalArchForFdi(fdiNumber: str) -> str:
        """Return Upper/Lower for a permanent-tooth FDI code, else empty."""

        match = re.fullmatch(r"([1-4])([1-8])", str(fdiNumber or "").strip())
        if not match:
            return ""
        return "Upper" if match.group(1) in {"1", "2"} else "Lower"

    def validateTargetTooth(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> dict:
        """Return the selected whole-tooth record or raise an actionable error."""

        if not isinstance(segmentId, str) or not segmentId.strip():
            raise ValueError(_("Select a target tooth before planning."))
        targetId = segmentId.strip()
        targetRecords = {
            record["segmentId"]: record
            for record in self.getTargetToothRecords(segmentationNode)
        }
        record = targetRecords.get(targetId)
        if not record:
            raise ValueError(
                _(
                    "The selected target does not exist or is not a whole-tooth "
                    "segment."
                )
            )
        return record

    @staticmethod
    def _semanticWorldPoints(
        segmentationNode: vtkMRMLSegmentationNode,
        image,
        ijkPoints: list[tuple[int, int, int]],
    ) -> np.ndarray:
        if not ijkPoints:
            return np.empty((0, 3), dtype=float)
        imageToLocal = vtk.vtkMatrix4x4()
        image.GetImageToWorldMatrix(imageToLocal)
        localToWorld = vtk.vtkMatrix4x4()
        localToWorld.Identity()
        parent = segmentationNode.GetParentTransformNode()
        if parent and not parent.GetMatrixTransformToWorld(localToWorld):
            raise ValueError(
                _(
                    "Pulp spatial association requires a linear segmentation "
                    "transform."
                )
            )
        imageToWorld = vtk.vtkMatrix4x4()
        vtk.vtkMatrix4x4.Multiply4x4(
            localToWorld,
            imageToLocal,
            imageToWorld,
        )
        points = []
        for ijk in ijkPoints:
            mapped = imageToWorld.MultiplyPoint((*ijk, 1.0))
            scale = float(mapped[3])
            if not math.isfinite(scale) or abs(scale) <= 1e-12:
                raise ValueError(_("Pulp voxel-to-world mapping is invalid."))
            point = np.asarray(mapped[:3], dtype=float) / scale
            if point.shape != (3,) or not np.all(np.isfinite(point)):
                raise ValueError(_("Pulp voxel-to-world mapping is invalid."))
            points.append(point)
        return np.asarray(points, dtype=float)

    @staticmethod
    def _semanticPointPolyData(points: np.ndarray) -> vtk.vtkPolyData:
        pointData = vtk.vtkPoints()
        pointData.SetNumberOfPoints(int(len(points)))
        for index, point in enumerate(points):
            pointData.SetPoint(index, *[float(value) for value in point])
        polyData = vtk.vtkPolyData()
        polyData.SetPoints(pointData)
        return polyData

    @classmethod
    def _semanticInsideFraction(
        cls,
        surface: vtk.vtkPolyData,
        points: np.ndarray,
    ) -> float:
        if len(points) == 0:
            return 0.0
        selector = vtk.vtkSelectEnclosedPoints()
        selector.SetInputData(cls._semanticPointPolyData(points))
        selector.SetSurfaceData(surface)
        selector.Update()
        selected = selector.GetOutput().GetPointData().GetArray(
            "SelectedPoints"
        )
        if selected is None:
            raise ValueError(_("Could not evaluate tooth enclosure evidence."))
        values = np.asarray(vtk_to_numpy(selected))
        return float(np.mean(values > 0))

    def _semanticPulpComponents(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        record: dict,
    ) -> list[dict]:
        segmentId = str(record.get("segmentId") or "")
        image = slicer.vtkOrientedImageData()
        if not segmentationNode.GetBinaryLabelmapRepresentation(segmentId, image):
            raise ValueError(_("The pulp segment has no binary labelmap."))
        scalars = image.GetPointData().GetScalars()
        dimensions = tuple(int(value) for value in image.GetDimensions())
        if scalars is None or not all(value > 0 for value in dimensions):
            return []
        values = vtk_to_numpy(scalars)
        expected = int(np.prod(dimensions))
        if len(values) != expected:
            raise ValueError(_("The pulp binary labelmap geometry is invalid."))
        mask = values.reshape(tuple(reversed(dimensions))) > 0
        occupied = np.argwhere(mask)[:, ::-1]
        if len(occupied) == 0:
            return []
        extent = image.GetExtent()
        offset = np.asarray(extent[::2], dtype=int)
        components = occupied_components(
            [tuple(int(value) for value in point + offset) for point in occupied]
        )
        result = []
        for index, component in enumerate(components, 1):
            result.append(
                {
                    "componentId": f"{segmentId}#component-{index}",
                    "sourceSegmentId": segmentId,
                    "voxelCount": len(component),
                    "pointsWorld": self._semanticWorldPoints(
                        segmentationNode,
                        image,
                        component,
                    ),
                }
            )
        return result

    def _semanticPulpCandidates(
        self,
        pulpRecord: dict,
        component: dict,
        toothSurfaces: dict[str, dict],
    ) -> list[dict]:
        points = component["pointsWorld"]
        if len(points) == 0:
            return []
        distances = {}
        insideFractions = {}
        for toothId, tooth in toothSurfaces.items():
            distance = vtk.vtkImplicitPolyDataDistance()
            distance.SetInput(tooth["surface"])
            values = np.asarray(
                [
                    abs(float(distance.EvaluateFunction(point)))
                    for point in points
                ],
                dtype=float,
            )
            distances[toothId] = np.where(
                np.isfinite(values),
                values,
                1e9,
            )
            insideFractions[toothId] = self._semanticInsideFraction(
                tooth["surface"],
                points,
            )
        toothIds = list(toothSurfaces)
        distanceMatrix = np.vstack([distances[toothId] for toothId in toothIds])
        nearestIndices = np.argmin(distanceMatrix, axis=0)
        sourceHint = pulpRecord.get("sourceFdiHint")
        candidates = []
        for index, toothId in enumerate(toothIds):
            values = distances[toothId]
            candidates.append(
                {
                    "toothSegmentId": toothId,
                    "toothFdiNumber": toothSurfaces[toothId]["record"].get(
                        "canonicalFdiNumber"
                    ) or toothSurfaces[toothId]["record"].get("fdiNumber"),
                    "sourceFdiHint": sourceHint,
                    "insideFraction": insideFractions[toothId],
                    "voxelIntersectionFraction": insideFractions[toothId],
                    "nearestToothFraction": float(
                        np.mean(nearestIndices == index)
                    ),
                    "minSurfaceDistanceMm": float(np.min(values)),
                    "robustSurfaceDistanceMm": float(np.quantile(values, 0.90)),
                    "componentVoxelCount": int(len(points)),
                }
            )
        return candidates

    def getTargetPulpAssociation(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
        *,
        persist: bool = True,
        requireReview: bool = True,
    ) -> dict:
        """Resolve one target's pulp from reviewed geometry and persist its relation."""

        targetRecord = self.validateTargetTooth(segmentationNode, segmentId)
        if (
            segmentationNode.GetAttribute(self.SEMANTIC_PERSISTENCE_ATTRIBUTE)
            == "stale"
        ):
            raise ValueError(
                _(
                    "Assisted generation is blocked: the canonical dental "
                    "registry no longer matches the imported segmentation."
                )
            )
        if self._semanticPersistenceIssues(segmentationNode):
            raise ValueError(
                _(
                    "Assisted generation is blocked: the canonical dental "
                    "registry does not match the current segmentation."
                )
            )
        targetId = targetRecord["segmentId"]
        targetFdi = str(targetRecord.get("canonicalFdiNumber") or targetRecord.get("fdiNumber") or "")
        records = self.getSegmentationReviewRecords(segmentationNode)
        derived = self._derivedPulpAssociation(segmentationNode, records, targetId, targetFdi, requireReview)
        if derived:
            pulpRecord, association = derived
            updatedRecords, semantic = (
                self.persistSemanticPulpAssociation(segmentationNode, association)
                if persist else (records, None)
            )
            return {
                **association,
                "pulpSegmentId": pulpRecord["segmentId"],
                "componentIds": [association["components"][0]["componentId"]],
                "targetSegmentId": targetId,
                "targetFdiNumber": targetFdi,
                "semantic": semantic,
                "semanticRecords": updatedRecords,
            }
        toothRecords = [
            record
            for record in records
            if record.get("structureType") == "TOOTH"
            and record.get("canonicalFdiNumber")
        ]
        toothSurfaces = {}
        for record in toothRecords:
            try:
                toothSurfaces[record["segmentId"]] = {
                    "record": record,
                    "surface": self._getClosedSurfaceWorldCopy(
                        segmentationNode,
                        record["segmentId"],
                    ),
                }
            except (TypeError, ValueError, RuntimeError):
                continue
        if targetId not in toothSurfaces:
            raise ValueError(_("The selected target tooth has no usable surface."))

        pulpRecords = [
            record for record in records
            if record.get("structureType") in {"PULP", "OTHER"}
        ]

        accepted = []
        relevantFailures = []
        for pulpRecord in pulpRecords:
            try:
                components = self._semanticPulpComponents(
                    segmentationNode,
                    pulpRecord,
                )
            except (TypeError, ValueError, RuntimeError) as exc:
                if str(pulpRecord.get("sourceFdiHint") or "") == targetFdi:
                    relevantFailures.append(
                        {
                            "validationState": "INVALID",
                            "reason": str(exc),
                            "sourceSegmentId": pulpRecord["segmentId"],
                        }
                    )
                continue
            if not components:
                if str(pulpRecord.get("sourceFdiHint") or "") == targetFdi:
                    relevantFailures.append(
                        {
                            "validationState": "MISSING",
                            "reason": "the hinted pulp mask is empty",
                            "sourceSegmentId": pulpRecord["segmentId"],
                        }
                    )
                continue
            componentPayloads = []
            for component in components:
                componentPayloads.append(
                    {
                        "componentId": component["componentId"],
                        "sourceSegmentId": component["sourceSegmentId"],
                        "candidates": self._semanticPulpCandidates(
                            pulpRecord,
                            component,
                            toothSurfaces,
                        ),
                    }
                )
            association = associate_pulp_components(componentPayloads, targetId)
            targetGateSeen = any(
                any(
                    candidate.get("toothSegmentId") == targetId
                    and candidate.get("passesSpatialGate")
                    for candidate in componentDecision.get("candidates", [])
                )
                for componentDecision in association.get("components", [])
            )
            if (
                association.get("validationState") == "VALID"
                and association.get("parentToothSegmentIds") == [targetId]
                and (
                    pulpRecord.get("structureType") == "PULP"
                    or all(
                        float(component["selected"]["insideFraction"]) == 1.0
                        for component in association["components"]
                    )
                )
            ):
                accepted.append((pulpRecord, association))
            elif (
                pulpRecord.get("structureType") == "OTHER"
                and association.get("validationState") == "VALID"
                and association.get("parentToothSegmentIds") == [targetId]
            ):
                relevantFailures.append({
                    "validationState": "INVALID",
                    "reason": "unknown mask is not fully inside the selected tooth",
                })
            elif targetGateSeen or targetId in association.get(
                "parentToothSegmentIds", []
            ):
                relevantFailures.append(association)

        if len(accepted) > 1:
            raise ValueError(
                _(
                    "Assisted generation is blocked: multiple pulp segments "
                    "spatially claim the selected tooth."
                )
            )
        if not accepted:
            if relevantFailures:
                failure = relevantFailures[0]
                raise ValueError(
                    _(
                        "Assisted generation is blocked by pulp semantic state "
                        "%1: %2"
                    ).replace("%1", str(failure.get("validationState") or "INVALID"))
                    .replace("%2", str(failure.get("reason") or "review required"))
                )
            raise MissingTargetPulpError(_(
                "No associated pulp mask is ready for this tooth. In Step 2, "
                "select the tooth and click Prepare Pulp Mask before placing crown entries."
            ))

        pulpRecord, association = accepted[0]
        if association.get("associationConfidence") != "HIGH":
            raise ValueError(
                _(
                    "Assisted generation requires HIGH-confidence pulp "
                    "association; review the spatial disagreement manually."
                )
            )
        updatedRecords, semantic = (
            self.persistSemanticPulpAssociation(segmentationNode, association)
            if persist else (records, None)
        )
        if not persist:
            return {
                **association,
                "pulpSegmentId": pulpRecord["segmentId"],
                "targetSegmentId": targetId,
                "targetFdiNumber": targetFdi,
            }
        selected = next(
            (
                record
                for record in updatedRecords
                if record.get("segmentId") == pulpRecord["segmentId"]
            ),
        )
        if (
            selected.get("validationState") != "VALID"
            or selected.get("associationConfidence") != "HIGH"
            or selected.get("parentToothSegmentIds") != [targetId]
        ):
            raise RuntimeError(_("The accepted pulp relation did not persist safely."))
        return {
            **association,
            "pulpSegmentId": pulpRecord["segmentId"],
            "componentIds": [
                component.get("componentId")
                for component in association.get("components", [])
            ],
            "targetSegmentId": targetId,
            "targetFdiNumber": targetFdi,
            "semantic": semantic,
            "semanticRecords": updatedRecords,
        }

    def getTargetToothBoundsWorld(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> tuple[float, float, float, float, float, float]:
        """Return finite axis-aligned world-RAS bounds for one whole tooth."""

        self.validateTargetTooth(segmentationNode, segmentId)
        try:
            return self.getSegmentationSegmentBoundsWorld(
                segmentationNode,
                segmentId,
            )
        except ValueError as exc:
            raise ValueError(
                _(
                    "The selected target tooth has no closed surface from "
                    "which to calculate placement bounds."
                )
            ) from exc

    def getSegmentationSegmentBoundsWorld(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> tuple[float, float, float, float, float, float]:
        """Return finite world-RAS bounds for any existing segment surface."""

        if not segmentationNode or not segmentationNode.IsA(
            "vtkMRMLSegmentationNode"
        ):
            raise ValueError(_("A teeth segmentation is required."))
        segmentation = segmentationNode.GetSegmentation()
        if not segmentId or not segmentation or not segmentation.GetSegment(segmentId):
            raise ValueError(_("The selected segment does not exist."))
        closedSurface = self._getClosedSurfaceWorldCopy(
            segmentationNode,
            segmentId,
        )
        bounds = tuple(float(value) for value in closedSurface.GetBounds())
        if (
            len(bounds) != 6
            or any(not math.isfinite(value) for value in bounds)
            or any(
                bounds[axis * 2 + 1] <= bounds[axis * 2]
                for axis in range(3)
            )
        ):
            raise ValueError(
                _("The selected segment has invalid world-RAS bounds.")
            )
        return bounds

    @staticmethod
    def formatRasBounds(
        bounds: tuple[float, float, float, float, float, float],
    ) -> str:
        """Format world-RAS axis-aligned bounds for the planning panel."""

        if len(bounds) != 6:
            raise ValueError(_("Six target-bound values are required."))
        return (
            f"R [{bounds[0]:.3f}, {bounds[1]:.3f}], "
            f"A [{bounds[2]:.3f}, {bounds[3]:.3f}], "
            f"S [{bounds[4]:.3f}, {bounds[5]:.3f}] mm"
        )

    @staticmethod
    def lineageColorForTarget(
        segmentId: str,
        fdiNumber: str = "",
    ) -> tuple[float, float, float]:
        """Return a stable vivid color for one authoritative target tooth."""

        normalizedSegmentId = str(segmentId or "").strip()
        if not normalizedSegmentId:
            raise ValueError(_("A target segment ID is required for lineage color."))
        fdiMatch = re.fullmatch(r"([1-4])([1-8])", str(fdiNumber or ""))
        if fdiMatch:
            ordinal = (int(fdiMatch.group(1)) - 1) * 8 + int(
                fdiMatch.group(2)
            ) - 1
        else:
            ordinal = (
                uuid.uuid5(uuid.NAMESPACE_OID, normalizedSegmentId).int % 32
            )
        hue = (0.055 + ordinal * 0.618033988749895) % 1.0
        return tuple(
            round(float(component), 6)
            for component in colorsys.hsv_to_rgb(hue, 0.74, 0.94)
        )

    @classmethod
    def lineageColorFromNode(cls, node) -> tuple[float, float, float] | None:
        """Read a validated persisted target-lineage color from one node."""

        if not node:
            return None
        try:
            values = json.loads(
                node.GetAttribute(cls.LINEAGE_COLOR_ATTRIBUTE) or "null"
            )
        except (json.JSONDecodeError, TypeError):
            return None
        if (
            not isinstance(values, list)
            or len(values) != 3
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
                or float(value) > 1.0
                for value in values
            )
        ):
            return None
        return tuple(float(value) for value in values)

    @classmethod
    def setNodeLineageColor(
        cls,
        node,
        color: tuple[float, float, float],
        segmentId: str,
        fdiNumber: str = "",
    ) -> bool:
        """Persist and display one visual lineage color without changing identity."""

        normalizedColor = tuple(round(float(value), 6) for value in color)
        if (
            len(normalizedColor) != 3
            or any(
                not math.isfinite(value) or value < 0.0 or value > 1.0
                for value in normalizedColor
            )
        ):
            raise ValueError(_("A lineage color must contain three RGB values."))
        serializedColor = json.dumps(
            list(normalizedColor),
            separators=(",", ":"),
        )
        normalizedSegmentId = str(segmentId or "").strip()
        normalizedFdi = str(fdiNumber or "").strip()
        changed = any(
            (
                node.GetAttribute(cls.LINEAGE_COLOR_ATTRIBUTE)
                != serializedColor,
                node.GetAttribute(cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE)
                != normalizedSegmentId,
                node.GetAttribute(cls.LINEAGE_TARGET_FDI_ATTRIBUTE)
                != normalizedFdi,
            )
        )
        if changed:
            wasModifying = node.StartModify()
            try:
                node.SetAttribute(cls.LINEAGE_COLOR_ATTRIBUTE, serializedColor)
                node.SetAttribute(
                    cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE,
                    normalizedSegmentId,
                )
                node.SetAttribute(
                    cls.LINEAGE_TARGET_FDI_ATTRIBUTE,
                    normalizedFdi,
                )
            finally:
                node.EndModify(wasModifying)
        if node.IsA("vtkMRMLDisplayableNode"):
            node.CreateDefaultDisplayNodes()
            displayNode = node.GetDisplayNode()
            if displayNode:
                displayNode.SetColor(*normalizedColor)
                if hasattr(displayNode, "SetSelectedColor"):
                    displayNode.SetSelectedColor(*normalizedColor)
                if hasattr(displayNode, "SetActiveColor"):
                    displayNode.SetActiveColor(*normalizedColor)
        return changed

    @classmethod
    def clearNodeLineageColor(cls, node) -> None:
        if not node:
            return
        attributeNames = (
            cls.LINEAGE_COLOR_ATTRIBUTE,
            cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE,
            cls.LINEAGE_TARGET_FDI_ATTRIBUTE,
        )
        if not any(node.GetAttribute(name) for name in attributeNames):
            return
        wasModifying = node.StartModify()
        try:
            for attributeName in attributeNames:
                node.SetAttribute(attributeName, None)
        finally:
            node.EndModify(wasModifying)

    @classmethod
    def _filterStep6TargetAttachedModels(
        cls,
        modelNodes: list,
        targetSegmentId: str,
    ) -> list:
        """Exclude and hide target-attached models carrying another target lineage."""
        result = []
        for node in modelNodes:
            if not node:
                continue
            lineageTargetId = (
                node.GetAttribute(cls.LINEAGE_TARGET_SEGMENT_ATTRIBUTE)
                or node.GetAttribute("DENTOBOT.TargetSegmentID")
                or ""
            )
            if lineageTargetId and lineageTargetId != str(targetSegmentId or ""):
                display = node.GetDisplayNode()
                if display:
                    display.SetVisibility(False)
                node.SetAttribute("DENTOBOT.GeometryState", "Stale")
                node.SetAttribute(
                    "DENTOBOT.StaleReason",
                    "Target changed; regenerate target-attached planning geometry.",
                )
                continue
            result.append(node)
        return result

    def dentobotTrajectoriesForTarget(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> list[vtkMRMLMarkupsLineNode]:
        """Return every DENTOBOT trajectory in one authoritative tooth group."""

        segmentationId = segmentationNode.GetID() if segmentationNode else None
        return [
            node
            for node in slicer.util.getNodesByClass(
                "vtkMRMLMarkupsLineNode"
            )
            if (
                self.isDentobotTrajectoryNode(node)
                and node.GetAttribute("DENTOBOT.TargetSegmentID") == segmentId
                and node.GetNodeReference(
                    self.TARGET_SEGMENTATION_REFERENCE_ROLE
                )
                and node.GetNodeReference(
                    self.TARGET_SEGMENTATION_REFERENCE_ROLE
                ).GetID()
                == segmentationId
            )
        ]

    def isTargetBoundsRoiForTarget(
        self,
        roiNode: vtkMRMLMarkupsROINode | None,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> bool:
        """Return whether an ROI is the exact Step 4A bounds for one tooth."""

        referencedSegmentation = (
            roiNode.GetNodeReference(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
            )
            if roiNode and roiNode.IsA("vtkMRMLMarkupsROINode")
            else None
        )
        return bool(
            referencedSegmentation
            and segmentationNode
            and referencedSegmentation.GetID() == segmentationNode.GetID()
            and roiNode.GetAttribute("DENTOBOT.BoundsRole")
            == "TargetToothAABB"
            and roiNode.GetAttribute("DENTOBOT.TargetSegmentID") == segmentId
        )

    def findTargetBoundsRoi(
        self,
        segmentationNode: vtkMRMLSegmentationNode,
        segmentId: str,
    ) -> vtkMRMLMarkupsROINode | None:
        """Find an existing exact target ROI so tooth switching creates no duplicate."""

        for roiNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsROINode"
        ):
            if self.isTargetBoundsRoiForTarget(
                roiNode,
                segmentationNode,
                segmentId,
            ):
                return roiNode
        return None

    def refreshWorkflowLineageColors(self) -> list[str]:
        """Propagate target-tooth colors through role/reference-linked descendants."""

        changedNodeIds = []
        groupColors: dict[tuple[str, str], tuple[float, float, float]] = {}
        groupFdi: dict[tuple[str, str], str] = {}
        for trajectoryNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsLineNode"
        ):
            if not self.isDentobotTrajectoryNode(trajectoryNode):
                continue
            try:
                self.enforceTrajectoryControlPointInvariant(trajectoryNode)
                segmentationNode = trajectoryNode.GetNodeReference(
                    self.TARGET_SEGMENTATION_REFERENCE_ROLE
                )
                segmentId = trajectoryNode.GetAttribute(
                    "DENTOBOT.TargetSegmentID"
                ) or ""
                targetRecord = self.validateTargetTooth(
                    segmentationNode,
                    segmentId,
                )
            except ValueError:
                continue
            key = (segmentationNode.GetID(), segmentId)
            fdiNumber = targetRecord.get("fdiNumber") or ""
            color = self.lineageColorForTarget(segmentId, fdiNumber)
            groupColors[key] = color
            groupFdi[key] = fdiNumber
            if self.setNodeLineageColor(
                trajectoryNode,
                color,
                segmentId,
                fdiNumber,
            ):
                changedNodeIds.append(trajectoryNode.GetID())

        for roiNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsROINode"
        ):
            if roiNode.GetAttribute("DENTOBOT.BoundsRole") != "TargetToothAABB":
                continue
            segmentationNode = roiNode.GetNodeReference(
                self.TARGET_BOUNDS_SEGMENTATION_REFERENCE_ROLE
            )
            segmentId = roiNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
            key = (
                segmentationNode.GetID() if segmentationNode else "",
                segmentId,
            )
            color = groupColors.get(key)
            if color and self.setNodeLineageColor(
                roiNode,
                color,
                segmentId,
                groupFdi.get(key, ""),
            ):
                changedNodeIds.append(roiNode.GetID())

        supportLineages: dict[str, tuple[tuple[float, float, float], str, str]] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isDraftTemplateSupportModelNode(modelNode):
                continue
            segmentationNode = modelNode.GetNodeReference(
                self.TEMPLATE_SOURCE_SEGMENTATION_REFERENCE_ROLE
            )
            segmentId = modelNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
            key = (
                segmentationNode.GetID() if segmentationNode else "",
                segmentId,
            )
            color = groupColors.get(key)
            if not color:
                continue
            fdiNumber = groupFdi.get(key, "")
            if self.setNodeLineageColor(
                modelNode,
                color,
                segmentId,
                fdiNumber,
            ):
                changedNodeIds.append(modelNode.GetID())
            supportLineages[modelNode.GetID()] = (
                color,
                segmentId,
                fdiNumber,
            )

        for curveNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsClosedCurveNode"
        ):
            if not self.isTemplateSupportBoundaryNode(curveNode):
                continue
            supportModel = curveNode.GetNodeReference(
                self.TEMPLATE_SUPPORT_BOUNDARY_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(curveNode, *lineage):
                changedNodeIds.append(curveNode.GetID())
        for planeNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsPlaneNode"
        ):
            if not self.isTemplateSupportBoundaryPlaneNode(planeNode):
                continue
            supportModel = planeNode.GetNodeReference(
                self.TEMPLATE_SUPPORT_PLANE_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(planeNode, *lineage):
                changedNodeIds.append(planeNode.GetID())

        visibleSupportLineages: dict[
            str,
            tuple[tuple[float, float, float], str, str],
        ] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isVisibleTemplateSupportModelNode(modelNode):
                continue
            supportModel = modelNode.GetNodeReference(
                self.TEMPLATE_VISIBLE_SUPPORT_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
            if lineage:
                visibleSupportLineages[modelNode.GetID()] = lineage

        for lineNode in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode"):
            if not self.isTemplateInsertionDirectionNode(lineNode):
                continue
            visibleSupport = lineNode.GetNodeReference(
                self.TEMPLATE_INSERTION_DIRECTION_SOURCE_SURFACE_REFERENCE_ROLE
            )
            lineage = (
                visibleSupportLineages.get(visibleSupport.GetID())
                if visibleSupport
                else None
            )
            if lineage and self.setNodeLineageColor(lineNode, *lineage):
                changedNodeIds.append(lineNode.GetID())

        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not (
                self.isTemplateUndercutSurfaceModelNode(modelNode)
                or self.isTemplateUndercutBlockoutModelNode(modelNode)
            ):
                continue
            visibleSupport = modelNode.GetNodeReference(
                self.TEMPLATE_UNDERCUT_SOURCE_SURFACE_REFERENCE_ROLE
            )
            lineage = (
                visibleSupportLineages.get(visibleSupport.GetID())
                if visibleSupport
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())

        patientShellLineages: dict[
            str,
            tuple[tuple[float, float, float], str, str],
        ] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isPatientContactShellModelNode(modelNode):
                continue
            visibleSupport = modelNode.GetNodeReference(
                self.TEMPLATE_PATIENT_SHELL_SOURCE_SURFACE_REFERENCE_ROLE
            )
            lineage = (
                visibleSupportLineages.get(visibleSupport.GetID())
                if visibleSupport
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
            if lineage:
                patientShellLineages[modelNode.GetID()] = lineage

        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if modelNode.GetAttribute("DENTOBOT.ModelRole") not in {
                "TemplateDockingAssembly",
                "TemplateDockingClearance",
                "TemplateDockingReinforcement",
                "TemplateDockingChannels",
                "FinalPrintableTemplate",
            }:
                continue
            patientShell = modelNode.GetNodeReference(
                self.TEMPLATE_FINAL_GUIDE_PATIENT_SHELL_REFERENCE_ROLE
            )
            lineage = (
                patientShellLineages.get(patientShell.GetID())
                if patientShell
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())

        for roiNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsROINode"
        ):
            if not self.isTemplateShellRoiNode(roiNode):
                continue
            supportModel = roiNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(roiNode, *lineage):
                changedNodeIds.append(roiNode.GetID())

        researchLineages: dict[str, tuple[tuple[float, float, float], str, str]] = {}
        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isResearchTemplateModelNode(modelNode):
                continue
            supportModel = modelNode.GetNodeReference(
                self.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            )
            lineage = (
                supportLineages.get(supportModel.GetID())
                if supportModel
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
            if lineage:
                researchLineages[modelNode.GetID()] = lineage

        for className, acceptsNode in (
            ("vtkMRMLMarkupsPlaneNode", self.isTemplateTrimPlaneNode),
            ("vtkMRMLMarkupsClosedCurveNode", self.isTemplateTrimCurveNode),
        ):
            for markupNode in slicer.util.getNodesByClass(className):
                if not acceptsNode(markupNode):
                    continue
                sourceShell = markupNode.GetNodeReference(
                    self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
                )
                lineage = (
                    researchLineages.get(sourceShell.GetID())
                    if sourceShell
                    else None
                )
                if lineage and self.setNodeLineageColor(markupNode, *lineage):
                    changedNodeIds.append(markupNode.GetID())

        for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isFinalizedTemplateShellModelNode(modelNode):
                continue
            sourceShell = modelNode.GetNodeReference(
                self.TEMPLATE_FINALIZATION_SOURCE_SHELL_REFERENCE_ROLE
            )
            lineage = (
                researchLineages.get(sourceShell.GetID())
                if sourceShell
                else None
            )
            if lineage and self.setNodeLineageColor(modelNode, *lineage):
                changedNodeIds.append(modelNode.GetID())
        return changedNodeIds

    def applyTrajectoryGroupEmphasis(
        self,
        segmentationNode: vtkMRMLSegmentationNode | None,
        activeSegmentId: str,
        activeTrajectoryNode: vtkMRMLMarkupsLineNode | None = None,
    ) -> None:
        """Emphasize the exact selected trajectory and then its tooth group."""

        activeSegmentationId = (
            segmentationNode.GetID() if segmentationNode else ""
        )
        for trajectoryNode in slicer.util.getNodesByClass(
            "vtkMRMLMarkupsLineNode"
        ):
            if not self.isDentobotTrajectoryNode(trajectoryNode):
                continue
            displayNode = trajectoryNode.GetDisplayNode()
            if not displayNode:
                continue
            targetSegmentation = trajectoryNode.GetNodeReference(
                self.TARGET_SEGMENTATION_REFERENCE_ROLE
            )
            isActiveGroup = bool(
                activeSegmentId
                and targetSegmentation
                and targetSegmentation.GetID() == activeSegmentationId
                and trajectoryNode.GetAttribute("DENTOBOT.TargetSegmentID")
                == activeSegmentId
            )
            hasActiveGroup = bool(activeSegmentationId and activeSegmentId)
            isSelected = bool(
                activeTrajectoryNode
                and trajectoryNode.GetID() == activeTrajectoryNode.GetID()
            )
            if isSelected:
                displayNode.SetVisibility(True)
                if hasattr(displayNode, "SetVisibility2D"):
                    displayNode.SetVisibility2D(True)
                if hasattr(displayNode, "SetVisibility3D"):
                    displayNode.SetVisibility3D(True)
                opacity, thickness, glyphScale = 1.0, 0.75, 1.65
            elif isActiveGroup and activeTrajectoryNode:
                opacity, thickness, glyphScale = 0.32, 0.24, 0.95
            elif isActiveGroup:
                opacity, thickness, glyphScale = 1.0, 0.55, 1.45
            elif hasActiveGroup:
                opacity, thickness, glyphScale = 0.38, 0.20, 0.90
            else:
                opacity, thickness, glyphScale = 0.68, 0.25, 1.0
            displayNode.SetOpacity(opacity)
            displayNode.SetLineThickness(thickness)
            displayNode.SetGlyphScale(glyphScale)
            displayNode.SetPointLabelsVisibility(isSelected or (
                isActiveGroup and activeTrajectoryNode is None
            ))
