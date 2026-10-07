"""Case bundle validation methods for the workflow logic."""

from __future__ import annotations

import copy

from .runtime import *
from DENTOStep6State import REGISTRY_PROVENANCE_FRAME_KEY


class CaseValidationLogicMixin:
    @staticmethod
    def robotDescriptionPaths() -> tuple[Path, Path]:
        moduleDirectory = DENTOWORKFLOW_MODULE_DIRECTORY
        candidates = (
            moduleDirectory.parent / "dentobot_description",
            moduleDirectory / "Resources" / "RobotDescription",
        )
        for packageRoot in candidates:
            urdfPath = packageRoot / "urdf" / "dentobot.urdf"
            if urdfPath.is_file() and (packageRoot / "meshes").is_dir():
                return urdfPath, packageRoot
        raise RuntimeError(
            _(
                "The tracked DENTOBOT URDF/STL resources are unavailable. "
                "Rebuild/reinstall the extension or restore dentobot_description."
            )
        )

    def caseBundleRobotProfile(self) -> dict[str, object]:
        """Return a portable fingerprint of the installed simulation resources."""

        _urdfPath, descriptionRoot = self.robotDescriptionPaths()
        moduleDirectory = DENTOWORKFLOW_MODULE_DIRECTORY
        moveitCandidates = (
            moduleDirectory.parent / "dentobot_moveit_config",
            descriptionRoot.parent / "dentobot_moveit_config",
        )
        moveitRoot = next(
            (candidate for candidate in moveitCandidates if candidate.is_dir()),
            None,
        )
        return build_robot_profile(descriptionRoot, moveitRoot)

    @staticmethod
    def _caseBundleMatrixValues(matrix: vtk.vtkMatrix4x4) -> list[float]:
        return [
            float(matrix.GetElement(row, column))
            for row in range(4)
            for column in range(4)
        ]

    @classmethod
    def _caseBundleNodeRecord(cls, fieldName: str, node) -> dict[str, object]:
        record: dict[str, object] = {
            "field": fieldName,
            "id": str(node.GetID() or ""),
            "class": str(node.GetClassName()),
            "name": str(node.GetName() or ""),
        }
        attributeNames = (
            "DENTOBOT.ModelRole",
            "DENTOBOT.TrajectoryRole",
            "DENTOBOT.MarkupsRole",
            "DENTOBOT.TransformRole",
            "DENTOBOT.GeometryState",
            "DENTOBOT.VerificationState",
            "DENTOBOT.FinalGuideSchemaVersion",
            "DENTOBOT.OrientationState",
            "DENTOBOT.SchemaVersion",
            "DENTOBOT.CoordinateSystem",
            "DENTOBOT.StaleReason",
            "DENTOBOT.RobotBaseMountLocked",
            "DENTOBOT.JawMotion",
            "DENTOBOT.HingeModelSchema",
            "DENTOBOT.OpenMouthModelVersion",
            "DENTOBOT.ArticulatorProvenanceJson",
            "DENTOBOT.TargetIncisorGapMm",
            "DENTOBOT.AchievedIncisorGapMm",
            "DENTOBOT.HingeAngleDeg",
            "DENTOBOT.SourceGeometryFingerprint",
            "DENTOBOT.LandmarksFingerprint",
            cls.SEMANTIC_SCHEMA_ATTRIBUTE,
            cls.SEMANTIC_STATUS_ATTRIBUTE,
            cls.SEMANTIC_FINGERPRINT_ATTRIBUTE,
            cls.SEMANTIC_PERSISTENCE_ATTRIBUTE,
            "DENTOBOT.TargetSegmentID",
            "DENTOBOT.TargetAttachedGeometryFingerprint",
            "DENTOBOT.MovingSegmentIdsJson",
            "DENTOBOT.FixedSegmentIdsJson",
            "DENTOBOT.FixedGeometryFingerprint",
            cls.REGISTRY_TARGET_ID_ATTRIBUTE,
            cls.REGISTRY_TRAJECTORY_ID_ATTRIBUTE,
            cls.REGISTRY_TRAJECTORY_SLOT_ATTRIBUTE,
            cls.REGISTRY_TRAJECTORY_FINGERPRINT_ATTRIBUTE,
            cls.REGISTRY_GUIDE_SET_ID_ATTRIBUTE,
            cls.REGISTRY_TEMPLATE_ID_ATTRIBUTE,
            cls.REGISTRY_SHELL_ID_ATTRIBUTE,
        )
        attributes = {
            name: str(node.GetAttribute(name))
            for name in attributeNames
            if node.GetAttribute(name) is not None
        }
        if attributes:
            record["attributes"] = attributes
        if node.IsA("vtkMRMLMarkupsNode"):
            points = []
            for index in range(node.GetNumberOfDefinedControlPoints()):
                point = [0.0, 0.0, 0.0]
                node.GetNthControlPointPositionWorld(index, point)
                points.append(cls._registryWorldPoint(point))
            record["controlPointsWorldRasMm"] = points
            record["locked"] = bool(node.GetLocked())
            record["selectable"] = bool(node.GetSelectable())
        if node.IsA("vtkMRMLLinearTransformNode"):
            matrix = vtk.vtkMatrix4x4()
            node.GetMatrixTransformToWorld(matrix)
            record["matrixToWorldRas"] = cls._caseBundleMatrixValues(matrix)
        if node.IsA("vtkMRMLModelNode"):
            polydata = node.GetPolyData()
            record["mesh"] = {
                "points": int(polydata.GetNumberOfPoints()) if polydata else 0,
                "cells": int(polydata.GetNumberOfCells()) if polydata else 0,
            }
            bounds = [0.0] * 6
            node.GetRASBounds(bounds)
            record["boundsWorldRasMm"] = [float(value) for value in bounds]
        if node.IsA("vtkMRMLScalarVolumeNode"):
            matrix = vtk.vtkMatrix4x4()
            node.GetIJKToRASMatrix(matrix)
            image = node.GetImageData()
            record["volumeGeometry"] = {
                "dimensions": list(image.GetDimensions()) if image else [0, 0, 0],
                "spacingMm": [float(value) for value in node.GetSpacing()],
                "ijkToRas": cls._caseBundleMatrixValues(matrix),
            }
        if node.IsA("vtkMRMLSegmentationNode"):
            record["segmentCount"] = int(
                node.GetSegmentation().GetNumberOfSegments()
            )
        return record

    def caseBundleWorkflowSummary(self, parameterNode) -> dict[str, object]:
        return self._caseBundleWorkflowSummary(parameterNode)

    def _caseBundleWorkflowSummary(self, parameterNode, *, legacyProvenance=False) -> dict[str, object]:
        """Describe persistent case state without duplicating its geometry."""

        foundation = self.evaluateCaseFoundationEligibility(parameterNode)
        registry = self.syncDentoCaseTrajectoryRegistry(parameterNode, legacyProvenance=legacyProvenance)
        reviewedTargets = []
        segmentation = parameterNode.teethSegmentation
        if segmentation is not None and self.getSegmentationReviewState(segmentation) == "Reviewed":
            for record in self.getSegmentationReviewRecords(segmentation):
                fdi = str(record.get("fdiNumber") or "")
                if not fdi or str(record.get("structureType") or "").upper() != "TOOTH":
                    continue
                tooth = registry["teeth"].get("FDI" + fdi, {})
                target_id = tooth.get("target_id") or self._stableDentoCaseId(
                    "target", segmentation.GetAttribute("DENTOBOT.CaseIdentity") or "",
                    record["segmentId"], "FDI" + fdi,
                )
                reviewedTargets.append({"targetId": target_id, "fdi": fdi,
                                        "segmentId": record["segmentId"]})
        preparedBranchCount = len(registry["prepared_branches"])
        caseClassification = (
            "FoundationOnly"
            if foundation["pose"]["eligible"]
            and foundation["base"]["eligible"]
            and preparedBranchCount == 0
            else "PlanningPackage"
            if preparedBranchCount
            else "PartialOrInspectable"
        )

        fields = (
            "inputVolume",
            "teethSegmentation",
            "targetToothBoundsRoi",
            "trajectoryLine",
            "draftTemplateSupportModel",
            "targetDockingReferencePlane",
            "targetDockingAssemblyModel",
            "templateSupportBoundaryCurve",
            "templateSupportBoundaryPlane",
            "visibleTemplateSupportModel",
            "templateInsertionDirection",
            "patientContactShellModel",
            "finalPrintableTemplateModel",
            "robotBaseTransform",
            "robotMountPlane",
            "robotForeheadProxyModel",
            "step6CaseJawLandmarks",
            "step6CaseJawTransform",
            "step6CaseJawGapLine",
            "step6OpenedLowerJawModel",
            "step6FixedUpperAnatomy",
            "step6MovingLowerAnatomy",
        )
        records = []
        for fieldName in fields:
            node = getattr(parameterNode, fieldName, None)
            if node is not None and node.GetID():
                records.append(self._caseBundleNodeRecord(fieldName, node))
        schemaVersion = str(parameterNode.dentoCaseSchemaVersion or "1.0")
        return {
            "schemaVersion": schemaVersion,
            "caseLabel": str(parameterNode.caseName or ""),
            "coordinateSystem": {
                "world": "SlicerRAS",
                "lengthUnit": "mm",
            },
            "caseClassification": caseClassification,
            "reviewedTargets": reviewedTargets,
            "caseFoundation": {
                **foundation,
                "preparedBranchCount": preparedBranchCount,
            },
            "nodes": records,
            "step6": {
                "planningContextImportedAtSave": bool(
                    parameterNode.step6PlanningContextImported
                ),
                "basePlacement": {
                    "status": str(parameterNode.step6BasePlacementStatus),
                    "source": str(parameterNode.step6BasePlacementSource),
                    "sourceRevision": int(parameterNode.step6BasePlacementRevision),
                    "fingerprint": self.robotBaseFingerprint(parameterNode),
                },
                "foreheadProxy": {
                    "present": bool(parameterNode.robotForeheadProxyModel),
                    "registrationState": "Unregistered",
                    "geometryState": "Provisional",
                    "intendedUse": "VisualizationOnly",
                    "widthMm": float(parameterNode.step6ForeheadProxyWidthMm),
                    "heightMm": float(parameterNode.step6ForeheadProxyHeightMm),
                    "depthMm": float(parameterNode.step6ForeheadProxyDepthMm),
                    "offsetMm": float(parameterNode.step6ForeheadProxyOffsetMm),
                },
                "jawOpening": {
                    "requiredForImportedCase": True,
                    "preparationMode": str(
                        parameterNode.step6CaseJawPreparationMode
                        or "ClosedSource"
                    ),
                    "placementReady": not bool(
                        self.step6CaseJawPlacementFreshnessIssues(parameterNode)
                    )
                    if parameterNode.step6PlanningContextImported
                    else False,
                    "targetGapMm": float(parameterNode.step6CaseJawTargetGapMm),
                    "current": not bool(
                        self.step6CaseJawOpeningFreshnessIssues(parameterNode)
                    )
                    if parameterNode.step6PlanningContextImported
                    else False,
                    "sourceGeometryFingerprint": (
                        parameterNode.step6CaseJawTransform.GetAttribute(
                            "DENTOBOT.SourceGeometryFingerprint"
                        )
                        if self.isStep6CaseJawTransformNode(
                            parameterNode.step6CaseJawTransform
                        )
                        else ""
                    ),
                    "motionModel": "VirtualOpenMouthArticulator",
                    "hingeModelSchema": (
                        parameterNode.step6CaseJawTransform.GetAttribute(
                            "DENTOBOT.HingeModelSchema"
                        )
                        if self.isStep6CaseJawTransformNode(
                            parameterNode.step6CaseJawTransform
                        )
                        else ""
                    ),
                    "articulatorProvenance": (
                        json.loads(
                            parameterNode.step6CaseJawTransform.GetAttribute(
                                "DENTOBOT.ArticulatorProvenanceJson"
                            )
                            or "{}"
                        )
                        if self.isStep6CaseJawTransformNode(
                            parameterNode.step6CaseJawTransform
                        )
                        else None
                    ),
                },
                "taskHome": (
                    json.loads(parameterNode.step6TaskHomeJson)
                    if str(parameterNode.step6TaskHomeJson or "").strip()
                    else None
                ),
                "assistedLimitProposal": (
                    json.loads(parameterNode.step6AssistedLimitProposalJson)
                    if str(parameterNode.step6AssistedLimitProposalJson or "").strip()
                    else None
                ),
                "confirmedTask": (
                    json.loads(parameterNode.step6ConfirmedTaskJson)
                    if str(parameterNode.step6ConfirmedTaskJson or "").strip()
                    else None
                ),
                "appearance": {
                    "cbctOpacity": float(parameterNode.step6CbctOpacity),
                    "masksOpacity": float(parameterNode.step6MasksOpacity),
                    "robotOpacity": float(parameterNode.step6RobotOpacity),
                    "goalRobotOpacity": float(parameterNode.step6GoalRobotOpacity),
                    "guidesOpacity": float(parameterNode.step6GuidesOpacity),
                    "mountPlaneOpacity": float(parameterNode.step6MountPlaneOpacity),
                    "trajectoryOpacity": float(parameterNode.step6TrajectoryOpacity),
                    "foreheadProxyOpacity": float(parameterNode.step6ForeheadProxyOpacity),
                },
                # Legacy integrity must finish before readiness evaluation,
                # which synchronizes the registry using current provenance.
                # This derived field is excluded from the lineage comparison.
                "freshnessIssuesAtSave": (
                    None if legacyProvenance
                    else self.step6PlanningContextFreshnessIssues(parameterNode)
                ),
                "runtimeRestorePolicy": "never-auto-connect",
                "environment": (
                    json.loads(parameterNode.step6EnvironmentJson)
                    if schemaVersion == DENTOCASE_STATE_SCHEMA_VERSION
                    and str(parameterNode.step6EnvironmentJson or "").strip()
                    else None
                ),
                "trajectoryRegistry": (
                    json.loads(parameterNode.step6TrajectoryRegistryJson)
                    if schemaVersion == DENTOCASE_STATE_SCHEMA_VERSION
                    and str(parameterNode.step6TrajectoryRegistryJson or "").strip()
                    else None
                ),
            },
        }

    @classmethod
    def _caseBundleValuesMatch(
        cls,
        expected: object,
        actual: object,
        tolerance: float = 1e-6,
    ) -> bool:
        del cls
        return lineage_snapshot_matches(expected, actual, tolerance)

    @classmethod
    def _caseBundleActualAtRecordedShape(
        cls,
        expected: object,
        actual: object,
    ) -> object:
        """Project current metadata to the fields recorded by schema-V1.

        Schema-V1 intentionally permits lineage extensions. An older bundle
        cannot contain attributes introduced by newer software, while current
        scene hydration may legitimately add those attributes before the first
        integrity comparison. Every field that the package did record remains
        strict; only actual-only dictionary keys are omitted. Lists, geometry,
        matrices, control points, and scalar values retain exact shape/value
        comparison.
        """

        if not isinstance(expected, dict) or not isinstance(actual, dict):
            return actual
        projected: dict[str, object] = {}
        for key, expectedValue in expected.items():
            if key not in actual:
                # Preserve a deterministic mismatch instead of silently
                # treating a missing historically recorded field as optional.
                projected[key] = {"__dentobot_missing_recorded_field__": key}
                continue
            projected[key] = cls._caseBundleActualAtRecordedShape(
                expectedValue,
                actual[key],
            )
        return projected

    def _caseBundleUnlockedBaseRevisionDrift(
        self,
        parameterNode,
        expectedStep6: dict[str, object],
    ) -> bool:
        """Recognize the retained pre-schema-3 unlocked-base revision drift.

        One retained package serialized the unlocked MRML revision one step
        ahead of the lineage/environment record.  Accept only that exact
        bookkeeping discrepancy after independently matching the persisted
        base pose, state, source, authority, and fingerprint.  The loaded
        scene remains unchanged and explicit save writes the current revision.
        """

        expectedBase = expectedStep6.get("basePlacement")
        expectedEnvironment = expectedStep6.get("environment")
        base = parameterNode.robotBaseTransform
        if not isinstance(expectedBase, dict) or not isinstance(
            expectedEnvironment, dict
        ) or not self.isRobotBaseTransformNode(base):
            return False
        try:
            expectedRevision = int(expectedBase.get("sourceRevision"))
            actualRevision = int(parameterNode.step6BasePlacementRevision)
        except (TypeError, ValueError):
            return False
        if actualRevision != expectedRevision + 1:
            return False
        if (
            expectedBase.get("status") != "Unlocked"
            or expectedBase.get("source") != "operator-unlocked"
            or bool(parameterNode.robotBaseMountLocked)
            or str(parameterNode.step6BasePlacementStatus or "") != "Unlocked"
            or str(parameterNode.step6BasePlacementSource or "")
            != "operator-unlocked"
            or str(
                base.GetAttribute(self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE)
                or ""
            )
            != self.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY
        ):
            return False
        expectedFingerprint = str(expectedBase.get("fingerprint") or "")
        expectedEnvironmentFields = {
            "base_fingerprint": expectedFingerprint,
            "base_authority": "operator-unlocked",
            "base_revision": expectedRevision,
            "base_status": "Unlocked",
            "base_locked": False,
        }
        if any(
            expectedEnvironment.get(key) != value
            for key, value in expectedEnvironmentFields.items()
        ):
            return False
        currentMatrix = list(self._foundationMatrixValues(base))
        if not self._caseBundleValuesMatch(
            expectedEnvironment.get("base_matrix"),
            currentMatrix,
        ):
            return False
        currentFingerprint = fingerprint(
            {
                "poseFingerprint": self.robotBasePoseFingerprint(base),
                "status": "Unlocked",
                "source": "operator-unlocked",
                "sourceRevision": expectedRevision,
                "authority": self.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
            }
        )
        return currentFingerprint == expectedFingerprint

    def _caseBundleRegistryForAudit(self, expectedRegistry, *, postHydration):
        """Compare legacy bytes before migration, then its validated frozen result."""
        legacy = isinstance(expectedRegistry, dict) and REGISTRY_PROVENANCE_FRAME_KEY not in expectedRegistry
        if not legacy or not postHydration:
            return expectedRegistry, legacy
        migration = getattr(self, "_caseBundleRegistryMigrationAudit", None)
        if migration is None or migration[0] != canonical_json(expectedRegistry):
            raise CaseBundleError("No validated registry migration matches this package.")
        return parse_trajectory_registry(migration[1]), False

    def validateLoadedCaseBundleWorkflow(
        self,
        parameterNode,
        expected: dict[str, object],
        *,
        allowDerivedEnvironmentMismatch: bool = False,
    ) -> None:
        """Cross-check manifest lineage against the freshly loaded MRML scene."""

        schemaVersion = str(expected.get("schemaVersion") or "")
        if schemaVersion not in {
            *LEGACY_DENTOCASE_STATE_SCHEMA_VERSIONS,
            DENTOCASE_STATE_SCHEMA_VERSION,
        }:
            raise CaseBundleError(_("Unsupported workflow-lineage schema."))
        coordinate = expected.get("coordinateSystem")
        if coordinate != {"world": "SlicerRAS", "lengthUnit": "mm"}:
            raise CaseBundleError(
                _("The workflow lineage is not declared in Slicer world-RAS mm.")
            )
        if str(expected.get("caseLabel") or "") != str(parameterNode.caseName or ""):
            raise CaseBundleError(_("The loaded case label does not match the manifest."))
        expectedRecords = expected.get("nodes")
        if not isinstance(expectedRecords, list):
            raise CaseBundleError(_("The workflow-lineage node inventory is invalid."))
        for expectedRecord in expectedRecords:
            if not isinstance(expectedRecord, dict):
                raise CaseBundleError(_("A workflow-lineage node record is invalid."))
            fieldName = str(expectedRecord.get("field") or "")
            node = getattr(parameterNode, fieldName, None)
            if node is None:
                raise CaseBundleError(
                    _("The loaded scene is missing the manifest node reference: %1").replace(
                        "%1", fieldName
                    )
                )
            actualRecord = self._caseBundleNodeRecord(fieldName, node)
            # MRML IDs are recorded for traceability but may be remapped when a
            # process-owned singleton is retained across scene replacement.
            expectedComparable = dict(expectedRecord)
            actualComparable = dict(actualRecord)
            expectedComparable.pop("id", None)
            actualComparable.pop("id", None)
            if node.IsA("vtkMRMLMarkupsNode"):
                # Lock/selectability are interaction presentation. The
                # application temporarily changes them to enforce ownership
                # by workflow stage, so they are restored separately and are
                # not geometry-integrity evidence.
                expectedComparable.pop("locked", None)
                actualComparable.pop("locked", None)
                expectedComparable.pop("selectable", None)
                actualComparable.pop("selectable", None)
            actualComparable = self._caseBundleActualAtRecordedShape(
                expectedComparable,
                actualComparable,
            )
            if not self._caseBundleValuesMatch(expectedComparable, actualComparable):
                mismatchPath = lineage_snapshot_mismatch_path(
                    expectedComparable,
                    actualComparable,
                )
                mismatchField = fieldName
                if mismatchPath and not mismatchPath.startswith("<"):
                    mismatchField = f"{fieldName}.{mismatchPath}"
                raise CaseBundleError(
                    _("Loaded MRML geometry/lineage differs from the package: %1").replace(
                        "%1", mismatchField
                    )
                )
        expectedStep6 = expected.get("step6")
        if not isinstance(expectedStep6, dict):
            raise CaseBundleError(_("The Step 6 package-lineage record is invalid."))
        registryForAudit, legacyProvenance = self._caseBundleRegistryForAudit(
            expectedStep6.get("trajectoryRegistry"),
            postHydration=allowDerivedEnvironmentMismatch,
        )
        currentStep6 = self._caseBundleWorkflowSummary(
            parameterNode, legacyProvenance=legacyProvenance
        )["step6"]
        # Step 6 lineage extensions are optional for schema-V1 compatibility.
        # Compare every field that the package actually records, without making
        # old bundles invent the new placement/home/task records. Historical
        # readiness evidence is not persistent state: current software may add
        # prerequisites, so it is re-evaluated after integrity validation.
        expectedComparableStep6 = copy.deepcopy(expectedStep6)
        if "trajectoryRegistry" in expectedComparableStep6:
            expectedComparableStep6["trajectoryRegistry"] = registryForAudit
        expectedComparableStep6.pop("freshnessIssuesAtSave", None)
        # Hydration intentionally clears this transient runtime marker before
        # the post-bind audit; it is not package identity or lineage.
        expectedComparableStep6.pop("planningContextImportedAtSave", None)
        expectedJawOpening = expectedComparableStep6.get("jawOpening")
        if isinstance(expectedJawOpening, dict):
            # Derived readiness is re-evaluated after integrity validation.
            expectedJawOpening.pop("current", None)
            expectedJawOpening.pop("placementReady", None)
        actualComparableStep6 = {
            key: currentStep6.get(key)
            for key in expectedComparableStep6
        }
        currentJawOpening = actualComparableStep6.get("jawOpening")
        if isinstance(currentJawOpening, dict):
            currentJawOpening = dict(currentJawOpening)
            currentJawOpening.pop("current", None)
            currentJawOpening.pop("placementReady", None)
            actualComparableStep6["jawOpening"] = currentJawOpening
        if self._caseBundleUnlockedBaseRevisionDrift(
            parameterNode,
            expectedComparableStep6,
        ):
            actualBase = dict(actualComparableStep6["basePlacement"])
            actualBase["sourceRevision"] = int(
                expectedComparableStep6["basePlacement"]["sourceRevision"]
            )
            actualBase["fingerprint"] = str(
                expectedComparableStep6["basePlacement"]["fingerprint"]
            )
            actualComparableStep6["basePlacement"] = actualBase
            actualEnvironment = dict(actualComparableStep6["environment"])
            actualEnvironment["base_revision"] = int(
                expectedComparableStep6["basePlacement"]["sourceRevision"]
            )
            actualEnvironment["base_fingerprint"] = str(
                expectedComparableStep6["basePlacement"]["fingerprint"]
            )
            for field in (
                "base_setup_fingerprint",
                "foundation_fingerprint",
                "environment_fingerprint",
            ):
                actualEnvironment[field] = expectedComparableStep6[
                    "environment"
                ][field]
            actualComparableStep6["environment"] = actualEnvironment
        if allowDerivedEnvironmentMismatch:
            # step6EnvironmentJson is rebuilt from authoritative MRML during
            # hydration. Its persisted copy is redundant derived state; the
            # node, lineage, registry, and matrix checks above remain strict.
            expectedComparableStep6.pop("environment", None)
            actualComparableStep6.pop("environment", None)
        actualComparableStep6 = self._caseBundleActualAtRecordedShape(
            expectedComparableStep6,
            actualComparableStep6,
        )
        if not self._caseBundleValuesMatch(
            expectedComparableStep6,
            actualComparableStep6,
        ):
            mismatchPath = lineage_snapshot_mismatch_path(
                expectedComparableStep6,
                actualComparableStep6,
            )
            mismatchSuffix = (
                f": step6.{mismatchPath}"
                if mismatchPath and not mismatchPath.startswith("<")
                else ""
            )
            raise CaseBundleError(
                _("Loaded Step 6 state differs from the package lineage record")
                + mismatchSuffix
            )
