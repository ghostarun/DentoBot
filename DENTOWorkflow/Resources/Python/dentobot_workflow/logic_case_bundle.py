"""Extracted case-bundle robot profile and validation methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


class CaseBundleLogicMixin:
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
            "DENTOBOT.OrientationState",
            "DENTOBOT.SchemaVersion",
            "DENTOBOT.CoordinateSystem",
            "DENTOBOT.StaleReason",
            "DENTOBOT.RobotBaseMountLocked",
            "DENTOBOT.JawMotion",
            "DENTOBOT.TargetIncisorGapMm",
            "DENTOBOT.AchievedIncisorGapMm",
            "DENTOBOT.HingeAngleDeg",
            "DENTOBOT.SourceGeometryFingerprint",
            "DENTOBOT.LandmarksFingerprint",
            "DENTOBOT.TargetSegmentID",
            "DENTOBOT.TargetAttachedGeometryFingerprint",
            "DENTOBOT.MovingSegmentIdsJson",
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
                points.append([float(value) for value in point])
            record["controlPointsWorldRasMm"] = points
            record["locked"] = bool(node.GetLocked())
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
        """Describe persistent case state without duplicating its geometry."""

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
            "step6OpenedTargetGeometryModel",
            "step6OpenedTrajectoryLine",
        )
        records = []
        for fieldName in fields:
            node = getattr(parameterNode, fieldName, None)
            if node is not None and node.GetID():
                records.append(self._caseBundleNodeRecord(fieldName, node))
        return {
            "schemaVersion": "1.0",
            "caseLabel": str(parameterNode.caseName or ""),
            "coordinateSystem": {
                "world": "SlicerRAS",
                "lengthUnit": "mm",
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
                    "motionModel": "PureTMJHingeRotation",
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
                "freshnessIssuesAtSave": self.step6PlanningContextFreshnessIssues(
                    parameterNode
                ),
                "runtimeRestorePolicy": "never-auto-connect",
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

    def validateLoadedCaseBundleWorkflow(
        self,
        parameterNode,
        expected: dict[str, object],
    ) -> None:
        """Cross-check manifest lineage against the freshly loaded MRML scene."""

        if expected.get("schemaVersion") != "1.0":
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
        currentStep6 = self.caseBundleWorkflowSummary(parameterNode)["step6"]
        # Step 6 lineage extensions are optional for schema-V1 compatibility.
        # Compare every field that the package actually records, without making
        # old bundles invent the new placement/home/task records.
        actualStep6 = {
            key: currentStep6.get(key)
            for key in expectedStep6
        }
        if not self._caseBundleValuesMatch(expectedStep6, actualStep6):
            raise CaseBundleError(
                _("Loaded Step 6 state differs from the package lineage record.")
            )
