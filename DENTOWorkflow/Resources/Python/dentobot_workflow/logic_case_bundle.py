"""Extracted case-bundle robot profile and validation methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

import copy

from .runtime import *


class CaseBundleLogicMixin:
    REGISTRY_TARGET_ID_ATTRIBUTE = "DENTOBOT.RegistryTargetID"
    REGISTRY_TRAJECTORY_ID_ATTRIBUTE = "DENTOBOT.RegistryTrajectoryID"
    REGISTRY_TRAJECTORY_SLOT_ATTRIBUTE = "DENTOBOT.RegistryTrajectorySlot"
    REGISTRY_TRAJECTORY_FINGERPRINT_ATTRIBUTE = (
        "DENTOBOT.RegistryTrajectoryFingerprint"
    )
    REGISTRY_GUIDE_SET_ID_ATTRIBUTE = "DENTOBOT.RegistryGuideSetID"
    REGISTRY_BRANCH_REVISION_ATTRIBUTE = "DENTOBOT.PreparedBranchRevision"
    REGISTRY_TEMPLATE_ID_ATTRIBUTE = "DENTOBOT.RegistryTemplateID"
    REGISTRY_SHELL_ID_ATTRIBUTE = "DENTOBOT.RegistryShellID"

    @staticmethod
    def _stableDentoCaseId(prefix: str, *values: object) -> str:
        return f"{prefix}-{fingerprint([str(value) for value in values])[:20]}"

    def _trajectoryRegistryGeometryFingerprint(self, trajectoryNode) -> str:
        points = []
        for index in range(trajectoryNode.GetNumberOfDefinedControlPoints()):
            point = [0.0, 0.0, 0.0]
            trajectoryNode.GetNthControlPointPositionWorld(index, point)
            points.append([float(value) for value in point])
        return fingerprint(
            {
                "targetSegmentId": str(
                    trajectoryNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
                ),
                "pointsWorldRasMm": points,
                "creationMethod": str(
                    trajectoryNode.GetAttribute("DENTOBOT.TrajectoryCreationMethod")
                    or "manual"
                ),
            }
        )

    def ensureDentoCaseTrajectoryIdentity(
        self,
        trajectoryNode,
        segmentationNode,
        targetRecord: dict[str, object],
    ) -> tuple[str, int]:
        """Assign one stable slot/identity and reject a fourth trajectory."""

        fdiNumber = str(targetRecord.get("fdiNumber") or "")
        if not fdiNumber:
            return "", 0
        toothId = f"FDI{fdiNumber}"
        if toothId not in DENTAL_FDI_TOOTH_IDS:
            raise ValueError(_("Only permanent FDI teeth can enter the Step 6 registry."))
        others = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode")
            if node is not trajectoryNode
            and self.isDentobotTrajectoryNode(node)
            and str(node.GetAttribute("DENTOBOT.TargetFdiNumber") or "") == fdiNumber
        ]
        occupied = {
            int(value)
            for node in others
            for value in [node.GetAttribute(self.REGISTRY_TRAJECTORY_SLOT_ATTRIBUTE)]
            if str(value or "").isdigit() and 1 <= int(value) <= 3
        }
        existingSlot = trajectoryNode.GetAttribute(
            self.REGISTRY_TRAJECTORY_SLOT_ATTRIBUTE
        )
        slot = int(existingSlot) if str(existingSlot or "").isdigit() else 0
        if slot not in (1, 2, 3):
            available = [value for value in (1, 2, 3) if value not in occupied]
            if not available:
                raise ValueError(
                    _("%1 already has three trajectories; a fourth is not allowed.").replace(
                        "%1", toothId
                    )
                )
            slot = available[0]
        targetId = str(
            trajectoryNode.GetAttribute(self.REGISTRY_TARGET_ID_ATTRIBUTE)
            or self._stableDentoCaseId(
                "target",
                segmentationNode.GetAttribute("DENTOBOT.CaseIdentity") or "",
                targetRecord["segmentId"],
                toothId,
            )
        )
        trajectoryId = str(
            trajectoryNode.GetAttribute(self.REGISTRY_TRAJECTORY_ID_ATTRIBUTE)
            or self._stableDentoCaseId(
                "trajectory",
                targetId,
                slot,
                trajectoryNode.GetID(),
            )
        )
        trajectoryNode.SetAttribute(self.REGISTRY_TARGET_ID_ATTRIBUTE, targetId)
        trajectoryNode.SetAttribute(self.REGISTRY_TRAJECTORY_ID_ATTRIBUTE, trajectoryId)
        trajectoryNode.SetAttribute(
            self.REGISTRY_TRAJECTORY_SLOT_ATTRIBUTE, str(slot)
        )
        return trajectoryId, slot

    @staticmethod
    def _nodeReferences(node, role: str) -> list:
        return [
            node.GetNthNodeReference(role, index)
            for index in range(node.GetNumberOfNodeReferences(role))
            if node.GetNthNodeReference(role, index)
        ]

    def syncDentoCaseTrajectoryRegistry(self, parameterNode) -> dict[str, object]:
        """Reconcile portable identities with MRML, which remains geometry authority."""

        try:
            previous = parse_trajectory_registry(
                str(parameterNode.step6TrajectoryRegistryJson or "")
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            previous = empty_trajectory_registry()
        priorSlots = {
            str(slot.get("trajectory_id")): slot
            for tooth in previous["teeth"].values()
            for slot in tooth["trajectory_set"]["slots"]
            if slot.get("trajectory_id")
        }
        registry = empty_trajectory_registry()
        trajectories = [
            node
            for node in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode")
            if self.isDentobotTrajectoryNode(node)
            and str(node.GetAttribute("DENTOBOT.TargetFdiNumber") or "")
        ]
        grouped: dict[str, list] = {}
        for trajectoryNode in trajectories:
            association = self.getTrajectoryTargetAssociation(trajectoryNode)
            targetRecord = association["targetRecord"]
            toothId = f"FDI{targetRecord.get('fdiNumber') or ''}"
            if toothId not in DENTAL_FDI_TOOTH_IDS:
                continue
            grouped.setdefault(toothId, []).append(trajectoryNode)
        for toothId, nodes in grouped.items():
            if len(nodes) > 3:
                raise ValueError(
                    _("%1 already has more than three trajectories.").replace(
                        "%1", toothId
                    )
                )
            nodes.sort(
                key=lambda node: (
                    int(node.GetAttribute(self.REGISTRY_TRAJECTORY_SLOT_ATTRIBUTE))
                    if str(node.GetAttribute(self.REGISTRY_TRAJECTORY_SLOT_ATTRIBUTE) or "").isdigit()
                    else 99,
                    str(node.GetID()),
                )
            )
            for trajectoryNode in nodes:
                association = self.getTrajectoryTargetAssociation(trajectoryNode)
                trajectoryId, slot = self.ensureDentoCaseTrajectoryIdentity(
                    trajectoryNode,
                    association["segmentationNode"],
                    association["targetRecord"],
                )
                geometryFingerprint = self._trajectoryRegistryGeometryFingerprint(
                    trajectoryNode
                )
                trajectoryNode.SetAttribute(
                    self.REGISTRY_TRAJECTORY_FINGERPRINT_ATTRIBUTE,
                    geometryFingerprint,
                )
                registry = upsert_trajectory_record(
                    registry,
                    tooth_id=toothId,
                    target_id=trajectoryNode.GetAttribute(
                        self.REGISTRY_TARGET_ID_ATTRIBUTE
                    ),
                    segment_id=association["targetRecord"]["segmentId"],
                    trajectory_id=trajectoryId,
                    trajectory_node_id=trajectoryNode.GetID(),
                    trajectory_fingerprint=geometryFingerprint,
                    provenance=trajectoryNode.GetAttribute(
                        "DENTOBOT.TrajectoryCreationMethod"
                    )
                    or "manual",
                    slot=slot,
                )
                prior = priorSlots.get(trajectoryId)
                if prior and prior.get("trajectory_fingerprint") != geometryFingerprint:
                    registry = stale_trajectory_record(
                        registry,
                        trajectoryId,
                        "Trajectory geometry changed; dependent guide/evidence requires review.",
                    )

        finalModels = sorted(
            slicer.util.getNodesByClass("vtkMRMLModelNode"),
            key=lambda node: (
                str(node.GetAttribute("DENTOBOT.UpdatedUtc") or ""),
                str(node.GetID()),
            ),
        )
        for finalModel in finalModels:
            if not self.isFinalPrintableTemplateModelNode(finalModel):
                continue
            sourceTrajectories = self._nodeReferences(
                finalModel,
                self.TEMPLATE_FINAL_GUIDE_SOURCE_TRAJECTORY_REFERENCE_ROLE,
            )
            trajectoryIds = [
                str(node.GetAttribute(self.REGISTRY_TRAJECTORY_ID_ATTRIBUTE) or "")
                for node in sourceTrajectories
            ]
            if not 1 <= len(trajectoryIds) <= 2 or any(not value for value in trajectoryIds):
                continue
            targetIds = {
                str(node.GetAttribute(self.REGISTRY_TARGET_ID_ATTRIBUTE) or "")
                for node in sourceTrajectories
            }
            if len(targetIds) != 1:
                raise ValueError(_("One template cannot span multiple target teeth."))
            targetId = targetIds.pop()
            guideSetId = self._stableDentoCaseId(
                "guide",
                targetId,
                *trajectoryIds,
            )
            finalModel.SetAttribute(self.REGISTRY_GUIDE_SET_ID_ATTRIBUTE, guideSetId)
            shell = finalModel.GetNodeReference(
                self.TEMPLATE_FINAL_GUIDE_PATIENT_SHELL_REFERENCE_ROLE
            )
            targetDocking = finalModel.GetNodeReference(
                self.TEMPLATE_FINAL_GUIDE_TARGET_DOCKING_REFERENCE_ROLE
            )
            insertionDirection = None
            if shell and self.isPatientContactShellModelNode(shell):
                try:
                    insertionDirection = self.getPatientContactShellSummary(shell)[
                        "insertionDirection"
                    ]
                except (RuntimeError, ValueError, json.JSONDecodeError):
                    insertionDirection = None
            templateId = self._stableDentoCaseId(
                "template", targetId, *trajectoryIds
            )
            shellId = self._stableDentoCaseId(
                "shell", targetId, *trajectoryIds
            )
            finalModel.SetAttribute(self.REGISTRY_TEMPLATE_ID_ATTRIBUTE, templateId)
            if shell:
                shell.SetAttribute(self.REGISTRY_SHELL_ID_ATTRIBUTE, shellId)
            related = [
                finalModel,
                shell,
                targetDocking,
                insertionDirection,
                *[
                    finalModel.GetNodeReference(role)
                    for role in (
                        self.TEMPLATE_FINAL_GUIDE_DOCKING_REFERENCE_ROLE,
                        self.TEMPLATE_FINAL_GUIDE_CLEARANCE_REFERENCE_ROLE,
                        self.TEMPLATE_FINAL_GUIDE_REINFORCEMENT_REFERENCE_ROLE,
                        self.TEMPLATE_FINAL_GUIDE_CHANNELS_REFERENCE_ROLE,
                    )
                ],
            ]
            related = [node for node in related if node]
            primaryNodeId = str(
                finalModel.GetAttribute("DENTOBOT.PrimaryTrajectoryNodeID")
                or sourceTrajectories[0].GetID()
            )
            primaryTrajectoryId = next(
                (
                    value
                    for node, value in zip(sourceTrajectories, trajectoryIds)
                    if node.GetID() == primaryNodeId
                ),
                trajectoryIds[0],
            )
            pairingIntent = str(
                finalModel.GetAttribute("DENTOBOT.PairingIntent")
                or ("Single" if len(trajectoryIds) == 1 else "LegacyUnverified")
            )
            insertionGeometry = ""
            if insertionDirection:
                try:
                    insertionGeometry = self.getTemplateInsertionDirectionSummary(
                        insertionDirection
                    )["geometryJson"]
                except (RuntimeError, ValueError, json.JSONDecodeError):
                    pass
            branchRevision = fingerprint(
                [
                    {
                        "id": node.GetID(),
                        "role": node.GetAttribute("DENTOBOT.ModelRole") or "",
                        "state": node.GetAttribute("DENTOBOT.GeometryState") or "",
                        "orientation": node.GetAttribute("DENTOBOT.OrientationState") or "",
                        "updated": node.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                    }
                    for node in related
                ]
                + [
                    {
                        "trajectoryIds": trajectoryIds,
                        "trajectoryFingerprints": [
                            node.GetAttribute(self.REGISTRY_TRAJECTORY_FINGERPRINT_ATTRIBUTE)
                            or ""
                            for node in sourceTrajectories
                        ],
                        "primaryTrajectoryId": primaryTrajectoryId,
                        "pairingIntent": pairingIntent,
                        "insertionGeometry": insertionGeometry,
                    }
                ]
            )
            finalModel.SetAttribute(self.REGISTRY_BRANCH_REVISION_ATTRIBUTE, branchRevision)
            trajectoryStates = {
                slot.get("trajectory_id"): slot.get("state")
                for tooth in registry["teeth"].values()
                for slot in tooth["trajectory_set"]["slots"]
            }
            guideState = finalModel.GetAttribute("DENTOBOT.GeometryState") or "Stale"
            if any(trajectoryStates.get(value) == "Stale" for value in trajectoryIds):
                guideState = "Stale"
            try:
                verification = json.loads(
                    finalModel.GetAttribute("DENTOBOT.VerificationJson") or "{}"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                verification = {}
            verificationRevision = (
                fingerprint(verification)
                if verification.get("preparedBranchId") == guideSetId
                and verification.get("preparedBranchRevision") == branchRevision
                else ""
            )
            registry = upsert_guide_set(
                registry,
                guide_set_id=guideSetId,
                target_id=targetId,
                trajectory_ids=trajectoryIds,
                template_id=templateId,
                template_node_id=finalModel.GetID(),
                shell_id=shellId if shell else "",
                shell_node_id=shell.GetID() if shell else "",
                model_node_ids=[node.GetID() for node in related],
                guide_fingerprint=branchRevision,
                primary_trajectory_id=primaryTrajectoryId,
                pairing_intent=pairingIntent,
                target_docking_node_id=targetDocking.GetID() if targetDocking else "",
                insertion_direction_node_id=(
                    insertionDirection.GetID() if insertionDirection else ""
                ),
                verification_revision=verificationRevision,
                state=guideState,
            )
        selectedBranchId = str(previous.get("selected_branch_id") or "")
        if selectedBranchId in registry["prepared_branches"]:
            registry = select_prepared_branch(registry, selectedBranchId)
        parameterNode.step6TrajectoryRegistryJson = canonical_json(registry)
        return registry

    def evaluatePreparedBranchEligibility(
        self,
        parameterNode,
        branchId: str | None = None,
        *,
        registry: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Return the single fail-closed PreparedBranch decision used by 5C/load/6."""

        registry = registry or self.syncDentoCaseTrajectoryRegistry(parameterNode)
        branchId = str(branchId or registry.get("selected_branch_id") or "")

        def result(reason: str, message: str, branch=None) -> dict[str, object]:
            return {
                "eligible": reason == "VALID",
                "reason": reason,
                "message": str(message),
                "branch_id": branchId,
                "branch": branch,
            }

        branch = registry["prepared_branches"].get(branchId)
        if not branch:
            return result("LEGACY_UNVERIFIED", _("Select a verified PreparedBranch."))
        if branch.get("pairing_intent") == "LegacyUnverified":
            return result(
                "LEGACY_UNVERIFIED",
                _("Legacy branch pairing must be explicitly rebuilt and verified."),
                branch,
            )
        trajectoryIds = list(branch.get("trajectory_ids", []))
        expectedIntent = "Single" if len(trajectoryIds) == 1 else "ExplicitPair"
        if branch.get("pairing_intent") != expectedIntent:
            return result(
                "PAIRING_NOT_CONFIRMED",
                _("PreparedBranch pairing intent does not match its trajectory set."),
                branch,
            )
        trajectories = []
        for trajectoryId in trajectoryIds:
            node = next(
                (
                    candidate
                    for candidate in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode")
                    if candidate.GetAttribute(self.REGISTRY_TRAJECTORY_ID_ATTRIBUTE)
                    == trajectoryId
                ),
                None,
            )
            if not node:
                return result("MISSING_TRAJECTORY", _("A PreparedBranch trajectory is missing."), branch)
            try:
                summary = self.getTrajectorySummary(node)
            except ValueError as exc:
                return result("MISSING_TRAJECTORY", str(exc), branch)
            if not summary["isValid"] or summary["definedPointCount"] != 2 or not node.GetLocked():
                return result("MISSING_TRAJECTORY", _("A PreparedBranch trajectory is incomplete or unlocked."), branch)
            trajectories.append(node)
        docking = slicer.mrmlScene.GetNodeByID(str(branch.get("target_docking_node_id") or ""))
        try:
            dockingSummary = self.getTargetDockingAssemblySummary(docking)
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return result("STALE_4C", str(exc), branch)
        if (
            dockingSummary["geometryState"] != "Current"
            or dockingSummary["orientationState"] != "Confirmed"
            or dockingSummary["trajectories"] != trajectories
        ):
            return result("STALE_4C", _("Step 4C is stale or does not match this PreparedBranch."), branch)
        insertion = slicer.mrmlScene.GetNodeByID(
            str(branch.get("insertion_direction_node_id") or "")
        )
        try:
            self.getTemplateInsertionDirectionSummary(insertion)
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return result("UPSTREAM_CHANGED", str(exc), branch)
        shell = slicer.mrmlScene.GetNodeByID(str(branch.get("shell_node_id") or ""))
        try:
            shellSummary = self.getPatientContactShellSummary(shell)
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return result("UPSTREAM_CHANGED", str(exc), branch)
        if shellSummary["geometryState"] != "Current" or shellSummary["insertionDirection"] is not insertion:
            return result("UPSTREAM_CHANGED", _("Patient shell or insertion state changed."), branch)
        finalModel = slicer.mrmlScene.GetNodeByID(str(branch.get("template_node_id") or ""))
        try:
            finalSummary = self.getFinalPrintableTemplateSummary(finalModel)
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            return result("MISSING_TEMPLATE", str(exc), branch)
        if (
            branch.get("state") != "Current"
            or finalSummary["geometryState"] != "Current"
            or finalSummary["patientShell"] is not shell
            or finalSummary["targetDockingAssembly"] is not docking
            or finalSummary["trajectories"] != trajectories
        ):
            return result("UPSTREAM_CHANGED", _("PreparedBranch dependencies changed after build."), branch)
        verification = finalSummary["verification"]
        if (
            finalSummary["verificationState"] not in {"PASS", "WARNING"}
            or verification.get("overall") != finalSummary["verificationState"]
            or verification.get("preparedBranchId") != branchId
            or verification.get("preparedBranchRevision") != branch.get("revision")
            or not branch.get("verification_revision")
        ):
            return result("STEP5C_MISMATCH", _("Step 5C verification does not match this PreparedBranch revision."), branch)
        return result("VALID", _("PreparedBranch is current and verified."), branch)

    def buildDentoCaseRobotEnvironment(self, parameterNode):
        jaw = parameterNode.step6CaseJawTransform
        base = parameterNode.robotBaseTransform
        jawMatrix = vtk.vtkMatrix4x4()
        baseMatrix = vtk.vtkMatrix4x4()
        jawValues = []
        baseValues = []
        if self.isStep6CaseJawTransformNode(jaw):
            jaw.GetMatrixTransformToWorld(jawMatrix)
            jawValues = self._caseBundleMatrixValues(jawMatrix)
        if self.isRobotBaseTransformNode(base):
            base.GetMatrixTransformToWorld(baseMatrix)
            baseValues = self._caseBundleMatrixValues(baseMatrix)
        home = None
        if str(parameterNode.step6TaskHomeJson or "").strip():
            try:
                home = json.loads(parameterNode.step6TaskHomeJson)
            except (TypeError, ValueError, json.JSONDecodeError):
                home = None
        anatomy = (
            self._caseBundleNodeRecord("teethSegmentation", parameterNode.teethSegmentation)
            if parameterNode.teethSegmentation
            else {}
        )
        robotProfile = self.caseBundleRobotProfile()
        environment = build_robot_environment_snapshot(
            case_identity=self._stableDentoCaseId(
                "case", parameterNode.caseName, fingerprint(anatomy)
            ),
            anatomy_fingerprint=fingerprint(anatomy),
            jaw_source_fingerprint=(
                jaw.GetAttribute("DENTOBOT.SourceGeometryFingerprint") if jaw else ""
            ),
            jaw_landmarks_fingerprint=(
                jaw.GetAttribute("DENTOBOT.LandmarksFingerprint") if jaw else ""
            ),
            jaw_configuration_fingerprint=fingerprint(
                {
                    "preparation": str(parameterNode.step6CaseJawPreparationJson or ""),
                    "gapMm": float(parameterNode.step6CaseJawTargetGapMm),
                }
            ),
            jaw_transform_matrix=jawValues,
            mouth_gap_mm=(
                float(parameterNode.step6CaseJawTargetGapMm) if jawValues else None
            ),
            robot_profile_fingerprint=str(robotProfile.get("identitySha256") or ""),
            tool_identity=str(parameterNode.step6ToolFrame or ""),
            tool_fingerprint=fingerprint(
                {"toolFrame": str(parameterNode.step6ToolFrame or "")}
            ),
            base_matrix=baseValues,
            base_status=str(parameterNode.step6BasePlacementStatus),
            base_locked=bool(parameterNode.robotBaseMountLocked),
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            task_home_configuration=home,
            common_collision_fingerprint=fingerprint(
                {
                    "anatomy": fingerprint(anatomy),
                    "jaw": jawValues,
                    "robot": str(robotProfile.get("identitySha256") or ""),
                    "tool": str(parameterNode.step6ToolFrame or ""),
                }
            ),
            limits_fingerprint=self.step6TaskLimitsFingerprint(parameterNode),
            workspace_fingerprint=fingerprint(
                str(parameterNode.step6AssistedLimitProposalJson or "")
            ),
        )
        parameterNode.step6EnvironmentJson = canonical_json(environment.to_dict())
        return environment

    def prepareDentoCaseSchema2ForSave(self, parameterNode) -> None:
        self.syncDentoCaseTrajectoryRegistry(parameterNode)
        self.buildDentoCaseRobotEnvironment(parameterNode)
        if self.isStep6CaseJawTransformNode(parameterNode.step6CaseJawTransform):
            parameterNode.step6CaseJawTransform.RemoveAttribute("DENTOBOT.TargetSegmentID")
            parameterNode.step6CaseJawTransform.RemoveAttribute(
                "DENTOBOT.TargetAttachedGeometryFingerprint"
            )
        parameterNode.dentoCaseSchemaVersion = DENTOCASE_STATE_SCHEMA_VERSION
        parameterNode.step6SchemaMigrationPending = False

    def hydrateDentoCaseStateAfterLoad(
        self, parameterNode, packageSchemaVersion: str
    ) -> None:
        savedEnvironment = None
        savedRegistry = None
        if packageSchemaVersion == "1.0":
            parameterNode.step6SchemaMigrationPending = True
        elif packageSchemaVersion != DENTOCASE_STATE_SCHEMA_VERSION:
            raise CaseBundleError(_("Unsupported DentoCase state schema."))
        else:
            try:
                savedEnvironment = parse_robot_environment_snapshot(
                    str(parameterNode.step6EnvironmentJson)
                )
                savedRegistry = parse_trajectory_registry(
                    str(parameterNode.step6TrajectoryRegistryJson)
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise CaseBundleError(
                    _("The saved Step 6 environment or trajectory registry is invalid.")
                ) from exc
        rebuiltRegistry = self.syncDentoCaseTrajectoryRegistry(parameterNode)
        rebuiltEnvironment = self.buildDentoCaseRobotEnvironment(parameterNode)
        if savedRegistry is not None and canonical_json(savedRegistry) != canonical_json(
            rebuiltRegistry
        ):
            raise CaseBundleError(
                _("The saved trajectory registry does not match authoritative MRML geometry.")
            )
        if savedEnvironment is not None and canonical_json(
            savedEnvironment.to_dict()
        ) != canonical_json(rebuiltEnvironment.to_dict()):
            changedFields = sorted(
                key
                for key, value in savedEnvironment.to_dict().items()
                if canonical_json(value)
                != canonical_json(rebuiltEnvironment.to_dict().get(key))
            )
            logging.warning(
                "Rebuilt the derived Step 6 environment from validated MRML "
                "after restore mismatch in: %s",
                ", ".join(changedFields),
            )
            parameterNode.step6SchemaMigrationPending = True
        if self.isStep6CaseJawTransformNode(parameterNode.step6CaseJawTransform):
            parameterNode.step6CaseJawTransform.RemoveAttribute("DENTOBOT.TargetSegmentID")
            parameterNode.step6CaseJawTransform.RemoveAttribute(
                "DENTOBOT.TargetAttachedGeometryFingerprint"
            )
        selectedBranchId = str(rebuiltRegistry.get("selected_branch_id") or "")
        if selectedBranchId:
            eligibility = self.evaluatePreparedBranchEligibility(
                parameterNode,
                selectedBranchId,
                registry=rebuiltRegistry,
            )
            if eligibility["eligible"]:
                self.activateDentoCasePreparedBranch(
                    parameterNode,
                    selectedBranchId,
                    registry=rebuiltRegistry,
                    invalidateRuntime=False,
                )
                self.refreshStep6CaseTargetAttachedDisplay(parameterNode)

    def activateDentoCasePreparedBranch(
        self,
        parameterNode,
        branchId: str,
        *,
        registry: dict[str, object] | None = None,
        invalidateRuntime: bool = True,
    ) -> dict[str, object]:
        registry = registry or self.syncDentoCaseTrajectoryRegistry(parameterNode)
        eligibility = self.evaluatePreparedBranchEligibility(
            parameterNode, branchId, registry=registry
        )
        if not eligibility["eligible"]:
            raise ValueError(eligibility["message"])
        branch = eligibility["branch"]
        trajectoryById = {
            str(node.GetAttribute(self.REGISTRY_TRAJECTORY_ID_ATTRIBUTE) or ""): node
            for node in slicer.util.getNodesByClass("vtkMRMLMarkupsLineNode")
        }
        trajectories = [trajectoryById[value] for value in branch["trajectory_ids"]]
        primaryTrajectory = trajectoryById[branch["primary_trajectory_id"]]
        association = self.getTrajectoryTargetAssociation(primaryTrajectory)
        targetDocking = slicer.mrmlScene.GetNodeByID(branch["target_docking_node_id"])
        dockingSummary = self.getTargetDockingAssemblySummary(targetDocking)
        insertionDirection = slicer.mrmlScene.GetNodeByID(
            branch["insertion_direction_node_id"]
        )
        patientShell = slicer.mrmlScene.GetNodeByID(branch["shell_node_id"])
        finalModel = slicer.mrmlScene.GetNodeByID(branch["template_node_id"])
        finalSummary = self.getFinalPrintableTemplateSummary(finalModel)
        roleModels = finalSummary["roleModels"]
        selectedRegistry = select_prepared_branch(registry, branchId)
        parameterMrmlNode = parameterNode.parameterNode
        role = self.TEMPLATE_SELECTED_GUIDE_TRAJECTORY_REFERENCE_ROLE
        if (
            str(registry.get("selected_branch_id") or "") == branchId
            and parameterNode.trajectoryLine is primaryTrajectory
            and parameterNode.targetDockingReferencePlane is dockingSummary["plane"]
            and parameterNode.targetDockingAssemblyModel is targetDocking
            and bool(parameterNode.targetDockingYawConfirmed)
            and parameterNode.templateInsertionDirection is insertionDirection
            and parameterNode.patientContactShellModel is patientShell
            and parameterNode.finalPrintableTemplateModel is finalModel
            and parameterNode.templateDockingAssemblyModel is roleModels["docking"]
            and parameterNode.templateDockingClearanceModel is roleModels["clearance"]
            and parameterNode.templateDockingReinforcementModel is roleModels["reinforcement"]
            and parameterNode.templateDockingChannelsModel is roleModels["channels"]
            and self._nodeReferences(parameterMrmlNode, role) == trajectories
        ):
            return eligibility
        fields = (
            "teethSegmentation",
            "targetToothSegmentId",
            "targetToothBoundsRoi",
            "trajectoryLine",
            "targetDockingReferencePlane",
            "targetDockingAssemblyModel",
            "targetDockingYawConfirmed",
            "templateInsertionDirection",
            "patientContactShellModel",
            "templateDockingAssemblyModel",
            "templateDockingClearanceModel",
            "templateDockingReinforcementModel",
            "templateDockingChannelsModel",
            "finalPrintableTemplateModel",
            "step6PlanningContextImported",
            "step6ConfirmedTaskJson",
            "step6CollisionSceneAuditJson",
            "step6TrajectoryRegistryJson",
        )
        previous = {field: getattr(parameterNode, field) for field in fields}
        previousSelectedIds = [
            node.GetID()
            for node in self._nodeReferences(parameterMrmlNode, role)
        ]
        oldRoi = parameterNode.targetToothBoundsRoi
        wasModifying = parameterNode.StartModify()
        try:
            parameterNode.teethSegmentation = association["segmentationNode"]
            parameterNode.targetToothSegmentId = association["targetRecord"]["segmentId"]
            parameterNode.targetToothBoundsRoi = association["targetBoundsRoi"]
            parameterNode.trajectoryLine = primaryTrajectory
            parameterNode.targetDockingReferencePlane = dockingSummary["plane"]
            parameterNode.targetDockingAssemblyModel = targetDocking
            parameterNode.targetDockingYawConfirmed = True
            parameterNode.templateInsertionDirection = insertionDirection
            parameterNode.patientContactShellModel = patientShell
            parameterNode.finalPrintableTemplateModel = finalModel
            parameterNode.templateDockingAssemblyModel = roleModels["docking"]
            parameterNode.templateDockingClearanceModel = roleModels["clearance"]
            parameterNode.templateDockingReinforcementModel = roleModels["reinforcement"]
            parameterNode.templateDockingChannelsModel = roleModels["channels"]
            parameterMrmlNode.RemoveNodeReferenceIDs(role)
            for node in trajectories:
                parameterMrmlNode.AddNodeReferenceID(role, node.GetID())
            parameterNode.step6ConfirmedTaskJson = ""
            parameterNode.step6CollisionSceneAuditJson = ""
            if invalidateRuntime:
                parameterNode.step6PlanningContextImported = False
            parameterNode.step6TrajectoryRegistryJson = canonical_json(selectedRegistry)
        except Exception:
            for field, value in previous.items():
                setattr(parameterNode, field, value)
            parameterMrmlNode.RemoveNodeReferenceIDs(role)
            for nodeId in previousSelectedIds:
                parameterMrmlNode.AddNodeReferenceID(role, nodeId)
            raise
        finally:
            parameterNode.EndModify(wasModifying)
        if oldRoi and oldRoi is not parameterNode.targetToothBoundsRoi and oldRoi.GetDisplayNode():
            oldRoi.GetDisplayNode().SetVisibility(False)
        if invalidateRuntime:
            self.markStep6MotionDiagnosticStale(
                parameterNode, _("The active PreparedBranch changed.")
            )
        return eligibility

    def activateDentoCaseTrajectory(self, parameterNode, trajectoryNode) -> dict:
        """Resolve a prepared trajectory through its branch; otherwise select it for preparation."""

        registry = self.syncDentoCaseTrajectoryRegistry(parameterNode)
        trajectoryId = str(
            trajectoryNode.GetAttribute(self.REGISTRY_TRAJECTORY_ID_ATTRIBUTE) or ""
        )
        candidateIds = list(prepared_branch_ids_for_trajectory(registry, trajectoryId))
        selectedId = str(registry.get("selected_branch_id") or "")
        orderedIds = ([selectedId] if selectedId in candidateIds else []) + [
            value for value in candidateIds if value != selectedId
        ]
        eligible = [
            value
            for value in orderedIds
            if self.evaluatePreparedBranchEligibility(
                parameterNode, value, registry=registry
            )["eligible"]
        ]
        if selectedId in eligible:
            return self.activateDentoCasePreparedBranch(
                parameterNode, selectedId, registry=registry
            )
        if len(eligible) == 1:
            return self.activateDentoCasePreparedBranch(
                parameterNode, eligible[0], registry=registry
            )
        if len(eligible) > 1:
            raise ValueError(_("This trajectory belongs to multiple PreparedBranches; select a branch explicitly."))

        association = self.getTrajectoryTargetAssociation(trajectoryNode)
        oldRoi = parameterNode.targetToothBoundsRoi
        parameterMrmlNode = parameterNode.parameterNode
        role = self.TEMPLATE_SELECTED_GUIDE_TRAJECTORY_REFERENCE_ROLE
        wasModifying = parameterNode.StartModify()
        try:
            parameterNode.teethSegmentation = association["segmentationNode"]
            parameterNode.targetToothSegmentId = association["targetRecord"]["segmentId"]
            parameterNode.targetToothBoundsRoi = association["targetBoundsRoi"]
            parameterNode.trajectoryLine = trajectoryNode
            parameterNode.targetDockingReferencePlane = None
            parameterNode.targetDockingAssemblyModel = None
            parameterNode.targetDockingYawConfirmed = False
            parameterNode.templateInsertionDirection = None
            parameterNode.patientContactShellModel = None
            parameterNode.finalPrintableTemplateModel = None
            parameterNode.templateDockingAssemblyModel = None
            parameterNode.templateDockingClearanceModel = None
            parameterNode.templateDockingReinforcementModel = None
            parameterNode.templateDockingChannelsModel = None
            parameterNode.step6PlanningContextImported = False
            parameterMrmlNode.RemoveNodeReferenceIDs(role)
            parameterMrmlNode.AddNodeReferenceID(role, trajectoryNode.GetID())
        finally:
            parameterNode.EndModify(wasModifying)
        if oldRoi and oldRoi is not parameterNode.targetToothBoundsRoi and oldRoi.GetDisplayNode():
            oldRoi.GetDisplayNode().SetVisibility(False)
        return {
            "eligible": False,
            "reason": "STEP5C_MISMATCH",
            "message": _("Trajectory selected for preparation; no eligible PreparedBranch was activated."),
            "branch_id": "",
            "branch": None,
        }

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
                points.append([float(value) for value in point])
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
            "step6FixedUpperAnatomy",
            "step6MovingLowerAnatomy",
            "step6TargetJawFallbackAnatomy",
            "step6OpenedTargetGeometryModel",
            "step6OpenedTrajectoryLine",
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

    def validateLoadedCaseBundleWorkflow(
        self,
        parameterNode,
        expected: dict[str, object],
    ) -> None:
        """Cross-check manifest lineage against the freshly loaded MRML scene."""

        schemaVersion = str(expected.get("schemaVersion") or "")
        if schemaVersion not in {"1.0", DENTOCASE_STATE_SCHEMA_VERSION}:
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
        currentStep6 = self.caseBundleWorkflowSummary(parameterNode)["step6"]
        # Step 6 lineage extensions are optional for schema-V1 compatibility.
        # Compare every field that the package actually records, without making
        # old bundles invent the new placement/home/task records. Historical
        # readiness evidence is not persistent state: current software may add
        # prerequisites, so it is re-evaluated after integrity validation.
        expectedComparableStep6 = copy.deepcopy(expectedStep6)
        expectedComparableStep6.pop("freshnessIssuesAtSave", None)
        expectedJawOpening = expectedComparableStep6.get("jawOpening")
        if isinstance(expectedJawOpening, dict):
            expectedJawOpening.pop("current", None)
        actualComparableStep6 = {
            key: currentStep6.get(key)
            for key in expectedComparableStep6
        }
        currentJawOpening = actualComparableStep6.get("jawOpening")
        if isinstance(currentJawOpening, dict):
            currentJawOpening = dict(currentJawOpening)
            currentJawOpening.pop("current", None)
            actualComparableStep6["jawOpening"] = currentJawOpening
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
