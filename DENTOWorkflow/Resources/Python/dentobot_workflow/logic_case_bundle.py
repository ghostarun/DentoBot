"""Extracted case-bundle robot profile and validation methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *
from . import jaw_frame
from . import step6_working_config
from .logic_case_validation import CaseValidationLogicMixin
from DENTOStep6State import REGISTRY_PROVENANCE_FRAME_KEY


class CaseBundleLogicMixin(CaseValidationLogicMixin):
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

    @staticmethod
    def _registryWorldPoint(point) -> list[float]:
        """Keep package identity coordinates stable across MRML transform round-trips."""

        return [round(float(value), 9) for value in point]

    def _trajectoryRegistryGeometryFingerprint(self, trajectoryNode, *, legacyWorld: bool = False) -> str:
        """Trajectory identity in its owning-jaw frame (opening-invariant).

        ``legacyWorld`` reproduces the pre-2026-10-07 world-RAS identity so a saved
        registry is recognised as unchanged on first load (no transient staleness).
        """

        parameterNode = self.getParameterNode()
        points = []
        for index in range(trajectoryNode.GetNumberOfDefinedControlPoints()):
            if legacyWorld:
                point = [0.0, 0.0, 0.0]
                trajectoryNode.GetNthControlPointPositionWorld(index, point)
            else:
                point = self.owningJawFrameControlPoint(parameterNode, trajectoryNode, index)
            points.append(self._registryWorldPoint(point))
        return fingerprint(
            {
                "targetSegmentId": str(
                    trajectoryNode.GetAttribute("DENTOBOT.TargetSegmentID") or ""
                ),
                ("pointsWorldRasMm" if legacyWorld else "pointsOwningJawRasMm"): points,
                "creationMethod": str(
                    trajectoryNode.GetAttribute("DENTOBOT.TrajectoryCreationMethod")
                    or "manual"
                ),
            }
        )

    def _migrateBranchProvenanceToOwningJawFrame(
        self,
        parameterNode,
        finalModel,
        trajectories: list,
        nodes: list,
        insertionDirection,
    ) -> list[str]:
        """Re-stamp legacy world-RAS provenance in the owning-jaw frame (S6-MULTI-JAW-STALE-01).

        A legacy record is converted only when it equals the CURRENT geometry under
        the legacy world-RAS rule, which proves it was recorded at the current
        mouth opening. Anything else is left untouched and stays stale, as before.
        """

        def dumps(value) -> str:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))

        migrated: list[str] = []
        try:
            jawJson = dumps(self.canonicalTrajectoryGeometry(trajectories))
            legacyJson = dumps(self.legacyWorldTrajectoryGeometry(trajectories))
        except (RuntimeError, ValueError, TypeError, KeyError):
            return migrated
        unique = []
        for node in nodes:
            if node is not None and node not in unique:
                unique.append(node)
        for node in list(unique):
            if self.isTargetDockingAssemblyModelNode(node):
                plane = node.GetNodeReference(self.TARGET_DOCKING_REFERENCE_PLANE_REFERENCE_ROLE)
                if plane is not None and plane not in unique:
                    unique.append(plane)
        for node in unique:
            stored = node.GetAttribute("DENTOBOT.TrajectoryGeometryJson")
            if stored and jawJson != legacyJson and stored == legacyJson:
                node.SetAttribute("DENTOBOT.TrajectoryGeometryJson", jawJson)
                migrated.append(f"{node.GetID()}:TrajectoryGeometryJson")
        for node in unique:
            frameJson = node.GetAttribute("DENTOBOT.FrameJson")
            if (
                frameJson
                and node.GetAttribute(jaw_frame.PROVENANCE_FRAME_ATTRIBUTE)
                != jaw_frame.OWNING_JAW_FRAME
                and node.GetAttribute("DENTOBOT.TrajectoryGeometryJson") == jawJson
            ):
                # Its trajectory record matches now, so the frame was captured at this pose.
                node.SetAttribute(
                    "DENTOBOT.FrameJson",
                    dumps(
                        jaw_frame.to_owning_jaw_frame(
                            json.loads(frameJson),
                            self.owningJawWorldMatrix(parameterNode, node),
                        )
                    ),
                )
                node.SetAttribute(
                    jaw_frame.PROVENANCE_FRAME_ATTRIBUTE, jaw_frame.OWNING_JAW_FRAME
                )
                migrated.append(f"{node.GetID()}:FrameJson")
        if insertionDirection is not None:
            try:
                insertion = self.getTemplateInsertionDirectionSummary(insertionDirection)
            except (RuntimeError, ValueError, json.JSONDecodeError):
                insertion = None
            if insertion and insertion["geometryJson"] != insertion["legacyWorldGeometryJson"]:
                for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
                    stored = node.GetAttribute("DENTOBOT.InsertionGeometryJson")
                    if not stored:
                        continue
                    try:
                        canonical = self.canonicalInsertionGeometryJson(stored)
                    except ValueError:
                        continue
                    if canonical == insertion["legacyWorldGeometryJson"]:
                        node.SetAttribute("DENTOBOT.InsertionGeometryJson", insertion["geometryJson"])
                        migrated.append(f"{node.GetID()}:InsertionGeometryJson")
        if not finalModel.GetAttribute(jaw_frame.BRANCH_FOUNDATION_ATTRIBUTE):
            foundation = self.evaluateCaseFoundationEligibility(parameterNode)
            if (
                foundation["pose"]["eligible"]
                and str(finalModel.GetAttribute("DENTOBOT.PlanningPoseFingerprint") or "")
                == foundation["planning_pose_fingerprint"]
            ):
                finalModel.SetAttribute(
                    jaw_frame.BRANCH_FOUNDATION_ATTRIBUTE,
                    foundation["branch_foundation_fingerprint"],
                )
                migrated.append(f"{finalModel.GetID()}:BranchFoundationFingerprint")
        if migrated:
            logging.info("DENTOBOT owning-jaw provenance migration: %s", ", ".join(migrated))
        return migrated

    @staticmethod
    def _upgradeLegacyStep5CVerification(
        finalModel,
        *,
        legacyRevision: str,
        branchRevision: str,
        planningPoseFingerprint: str,
        branchFoundationFingerprint: str,
    ) -> bool:
        """Carry a Step 5C verification over to the opening-independent binding.

        Only a verification that matched this branch under the legacy rules (same
        legacy revision and planning pose) is upgraded; nothing is re-verified or
        relaxed. The legacy identity is kept in ``provenanceUpgrade``.
        """

        try:
            verification = json.loads(finalModel.GetAttribute("DENTOBOT.VerificationJson") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if (
            not isinstance(verification, dict)
            or not verification
            or "branchFoundationFingerprint" in verification
            or not branchFoundationFingerprint
            or not planningPoseFingerprint
            or verification.get("preparedBranchRevision") != legacyRevision
            or verification.get("planningPoseFingerprint") != planningPoseFingerprint
        ):
            return False
        upgraded = dict(
            verification,
            preparedBranchRevision=branchRevision,
            branchFoundationFingerprint=branchFoundationFingerprint,
            provenanceUpgrade={
                "from": "WorldRASmm provenance + planning-pose binding",
                "to": jaw_frame.OWNING_JAW_FRAME + " provenance + Case Foundation binding",
                "legacyPreparedBranchRevision": legacyRevision,
                "upgradedUtc": datetime.now(timezone.utc).isoformat(),
            },
        )
        finalModel.SetAttribute(
            "DENTOBOT.VerificationJson",
            json.dumps(upgraded, sort_keys=True, separators=(",", ":")),
        )
        return True

    # ---- per-branch Step 6 working configuration (S6-MULTI-JAW-STALE-01) ------
    def preparedBranchFinalTemplate(self, parameterNode, branchId: str = ""):
        """(branch id, registry branch, final-template node) of ``branchId`` or the selected branch."""

        registry = parse_trajectory_registry(str(parameterNode.step6TrajectoryRegistryJson or ""))
        branchId = str(branchId or registry.get("selected_branch_id") or "")
        branch = registry["prepared_branches"].get(branchId)
        node = (
            slicer.mrmlScene.GetNodeByID(str(branch.get("template_node_id") or ""))
            if branch else None
        )
        return branchId, branch, node

    def step6WorkingConfiguration(self, parameterNode, branchId: str = "") -> dict | None:
        _branchId, _branch, node = self.preparedBranchFinalTemplate(parameterNode, branchId)
        if node is None:
            return None
        return step6_working_config.loads(node.GetAttribute(step6_working_config.ATTRIBUTE))

    def captureStep6WorkingConfiguration(
        self, parameterNode, *, plannerPolicy: dict, corridorMarginSamples: int
    ) -> dict:
        """The live Step 6 configuration of the active branch (not stored)."""

        matrix = vtk.vtkMatrix4x4()
        parameterNode.robotBaseTransform.GetMatrixTransformToWorld(matrix)
        home = self.taskHomeRecord(parameterNode)
        return step6_working_config.normalize(
            {
                "mouth_opening_mm": float(parameterNode.step6CaseJawTargetGapMm),
                "base_world_mm": [
                    [matrix.GetElement(row, column) for column in range(4)] for row in range(4)
                ],
                "task_home_si": (
                    dict(zip(home.joint_names, home.joint_positions_si)) if home else None
                ),
                "planner_id": str(plannerPolicy.get("planner_id") or ""),
                "planning_attempts": int(plannerPolicy.get("planning_attempts", 5)),
                "planning_time_sec": float(plannerPolicy.get("planning_time_sec", 5.0)),
                "corridor_margin_samples": int(corridorMarginSamples),
                "allow_spindle_guide_contact": bool(
                    getattr(parameterNode, "step6AllowSpindleGuideContact", False)
                ),
            }
        )

    def storeStep6WorkingConfiguration(self, parameterNode, record: dict) -> dict:
        """Store ``record`` on the active, VALID PreparedBranch's final template."""

        eligibility = self.evaluatePreparedBranchEligibility(parameterNode)
        if eligibility["reason"] != "VALID":
            raise ValueError(eligibility["message"])
        branchId, branch, node = self.preparedBranchFinalTemplate(
            parameterNode, eligibility["branch_id"]
        )
        if node is None:
            raise ValueError(_("The active PreparedBranch has no final template."))
        stored = step6_working_config.normalize(
            {
                **record,
                "branch_id": branchId,
                "branch_foundation_fingerprint": branch.get("branch_foundation_fingerprint", ""),
                "recorded_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        node.SetAttribute(step6_working_config.ATTRIBUTE, step6_working_config.dumps(stored))
        return stored

    def importResearchStep6WorkingConfigurations(self, parameterNode) -> list[str]:
        """Adopt pre-2026-10-07 research-store entries for branches that have none."""

        store = next(
            (
                node
                for node in slicer.util.getNodesByClass("vtkMRMLScriptedModuleNode")
                if node.GetName() == step6_working_config.RESEARCH_NODE_NAME
            ),
            None,
        )
        if store is None:
            return []
        imported = []
        prefix = step6_working_config.RESEARCH_ATTRIBUTE_PREFIX
        for name in store.GetAttributeNames() or ():
            if not name.startswith(prefix):
                continue
            branchId = name[len(prefix):]
            _branchId, branch, node = self.preparedBranchFinalTemplate(parameterNode, branchId)
            if node is None or node.GetAttribute(step6_working_config.ATTRIBUTE):
                continue
            try:
                record = step6_working_config.from_research_entry(
                    {**json.loads(store.GetAttribute(name)), "branch_id": branchId},
                    branch.get("branch_foundation_fingerprint", ""),
                )
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                continue
            node.SetAttribute(step6_working_config.ATTRIBUTE, step6_working_config.dumps(record))
            imported.append(branchId)
        return imported

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

    def syncDentoCaseTrajectoryRegistry(
        self, parameterNode, *, legacyProvenance: bool = False
    ) -> dict[str, object]:
        """Reconcile portable identities with MRML, which remains geometry authority.

        ``legacyProvenance`` rebuilds with the pre-2026-10-07 world-RAS semantics
        and planning-pose binding; it exists only to validate a saved legacy
        registry on load. Normal syncs record owning-jaw provenance, bind branches
        to the opening-independent Case Foundation identity and migrate legacy
        records that provably match the current geometry (S6-MULTI-JAW-STALE-01).
        """

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
        if legacyProvenance:
            registry.pop(REGISTRY_PROVENANCE_FRAME_KEY, None)
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
                    trajectoryNode, legacyWorld=legacyProvenance
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
                if (
                    prior
                    and prior.get("trajectory_fingerprint") != geometryFingerprint
                    and (
                        legacyProvenance
                        or prior.get("trajectory_fingerprint")
                        != self._trajectoryRegistryGeometryFingerprint(
                            trajectoryNode, legacyWorld=True
                        )
                    )
                ):
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
            shellSummary = None
            if shell and self.isPatientContactShellModelNode(shell):
                try:
                    shellSummary = self.getPatientContactShellSummary(shell)
                    insertionDirection = shellSummary["insertionDirection"]
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
                finalModel.GetNodeReference(
                    self.TEMPLATE_FINAL_GUIDE_RESEARCH_SHELL_REFERENCE_ROLE
                ),
                finalModel.GetNodeReference(
                    self.TEMPLATE_FINAL_GUIDE_RESEARCH_SLEEVE_REFERENCE_ROLE
                ),
                finalModel.GetNodeReference(
                    self.TEMPLATE_FINAL_GUIDE_FINALIZED_SHELL_REFERENCE_ROLE
                ),
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
            finalizedShell = finalModel.GetNodeReference(
                self.TEMPLATE_FINAL_GUIDE_FINALIZED_SHELL_REFERENCE_ROLE
            )
            if finalizedShell:
                try:
                    finalizedSummary = self.getFinalizedTemplateShellSummary(
                        finalizedShell
                    )
                    related.extend(
                        node
                        for node in (
                            finalizedSummary["editNode"],
                            finalizedSummary["dynamicModelerNode"],
                        )
                        if node and node not in related
                    )
                except (RuntimeError, ValueError, json.JSONDecodeError):
                    pass
            ownedNodes = list(related)
            if shellSummary:
                ownedNodes.extend(
                    node
                    for node in (
                        shellSummary["sourceModel"],
                        shellSummary["visibleSupport"],
                        shellSummary["boundary"],
                        shellSummary["blockoutModel"],
                    )
                    if node not in ownedNodes
                )
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
            if not legacyProvenance:
                self._migrateBranchProvenanceToOwningJawFrame(
                    parameterNode,
                    finalModel,
                    sourceTrajectories,
                    [*ownedNodes, *sourceTrajectories],
                    insertionDirection,
                )
            planningPoseFingerprint = str(
                finalModel.GetAttribute("DENTOBOT.PlanningPoseFingerprint") or ""
            )
            branchFoundationFingerprint = str(
                finalModel.GetAttribute(jaw_frame.BRANCH_FOUNDATION_ATTRIBUTE) or ""
            )
            insertionGeometry = legacyInsertionGeometry = ""
            if insertionDirection:
                try:
                    insertionSummary = self.getTemplateInsertionDirectionSummary(
                        insertionDirection
                    )
                    insertionGeometry = self.canonicalInsertionGeometryJson(
                        insertionSummary
                    )
                    legacyInsertionGeometry = insertionSummary["legacyWorldGeometryJson"]
                except (RuntimeError, ValueError, json.JSONDecodeError):
                    pass
            relatedRecords = [
                {
                    "id": node.GetID(),
                    "role": node.GetAttribute("DENTOBOT.ModelRole") or "",
                    "state": node.GetAttribute("DENTOBOT.GeometryState") or "",
                    "orientation": node.GetAttribute("DENTOBOT.OrientationState") or "",
                    "updated": node.GetAttribute("DENTOBOT.UpdatedUtc") or "",
                }
                for node in related
            ]

            def revisionOf(trajectoryFingerprints, insertion, poseKey, poseValue) -> str:
                return fingerprint(
                    relatedRecords
                    + [
                        {
                            "trajectoryIds": trajectoryIds,
                            "trajectoryFingerprints": trajectoryFingerprints,
                            "primaryTrajectoryId": primaryTrajectoryId,
                            "pairingIntent": pairingIntent,
                            "insertionGeometry": insertion,
                            poseKey: poseValue,
                        }
                    ]
                )

            legacyRevision = revisionOf(
                [
                    self._trajectoryRegistryGeometryFingerprint(node, legacyWorld=True)
                    for node in sourceTrajectories
                ],
                legacyInsertionGeometry,
                "planningPoseFingerprint",
                planningPoseFingerprint,
            )
            branchRevision = (
                legacyRevision
                if legacyProvenance
                else revisionOf(
                    [
                        node.GetAttribute(self.REGISTRY_TRAJECTORY_FINGERPRINT_ATTRIBUTE)
                        or ""
                        for node in sourceTrajectories
                    ],
                    insertionGeometry,
                    "branchFoundationFingerprint",
                    branchFoundationFingerprint,
                )
            )
            if not legacyProvenance:
                self._upgradeLegacyStep5CVerification(
                    finalModel,
                    legacyRevision=legacyRevision,
                    branchRevision=branchRevision,
                    planningPoseFingerprint=planningPoseFingerprint,
                    branchFoundationFingerprint=branchFoundationFingerprint,
                )
            finalModel.SetAttribute(self.REGISTRY_BRANCH_REVISION_ATTRIBUTE, branchRevision)
            trajectoryStates = {
                slot.get("trajectory_id"): slot.get("state")
                for tooth in registry["teeth"].values()
                for slot in tooth["trajectory_set"]["slots"]
            }
            guideState = finalModel.GetAttribute("DENTOBOT.GeometryState") or "Stale"
            if (
                not planningPoseFingerprint
                or (not legacyProvenance and not branchFoundationFingerprint)
                or any(trajectoryStates.get(value) == "Stale" for value in trajectoryIds)
            ):
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
                model_node_ids=[node.GetID() for node in ownedNodes],
                guide_fingerprint=branchRevision,
                primary_trajectory_id=primaryTrajectoryId,
                pairing_intent=pairingIntent,
                target_docking_node_id=targetDocking.GetID() if targetDocking else "",
                insertion_direction_node_id=(
                    insertionDirection.GetID() if insertionDirection else ""
                ),
                verification_revision=verificationRevision,
                planning_pose_fingerprint=planningPoseFingerprint,
                branch_foundation_fingerprint=(
                    None if legacyProvenance else branchFoundationFingerprint
                ),
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
        _forVerification: bool = False,
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
        foundation = self.evaluateCaseFoundationEligibility(parameterNode)
        if not foundation["pose"]["eligible"]:
            return result("FOUNDATION_MISMATCH", foundation["pose"]["message"], branch)
        # Bound to the opening-independent Case Foundation identity: a Step 6
        # mouth-opening change moves a branch rigidly with its jaw and never
        # invalidates it (S6-MULTI-JAW-STALE-01).
        if (
            not branch.get("branch_foundation_fingerprint")
            or branch.get("branch_foundation_fingerprint")
            != foundation["branch_foundation_fingerprint"]
        ):
            return result(
                "FOUNDATION_MISMATCH",
                _("PreparedBranch belongs to another Case Foundation."),
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
        if _forVerification:
            return result("VALID", _("PreparedBranch is ready for Step 5C verification."), branch)
        verification = finalSummary["verification"]
        if (
            finalSummary["verificationState"] not in {"PASS", "WARNING"}
            or verification.get("overall") != finalSummary["verificationState"]
            or verification.get("preparedBranchId") != branchId
            or verification.get("preparedBranchRevision") != branch.get("revision")
            or verification.get("branchFoundationFingerprint")
            != branch.get("branch_foundation_fingerprint")
            or not branch.get("verification_revision")
        ):
            return result("STEP5C_MISMATCH", _("Step 5C verification does not match this PreparedBranch revision."), branch)
        return result("VALID", _("PreparedBranch is current and verified."), branch)

    def evaluatePreparedBranchForVerification(
        self,
        parameterNode,
        branchId: str,
        *,
        registry: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Validate a complete branch through Step 5B without claiming Step 6 readiness."""

        return self.evaluatePreparedBranchEligibility(
            parameterNode,
            branchId,
            registry=registry,
            _forVerification=True,
        )

    def buildDentoCaseRobotEnvironment(self, parameterNode):
        environment = self.buildCaseFoundationSnapshot(parameterNode)
        parameterNode.step6EnvironmentJson = canonical_json(environment.to_dict())
        return environment

    def prepareDentoCaseSchema3ForSave(self, parameterNode) -> None:
        if bool(parameterNode.caseFoundationPreviewUncommitted):
            raise ValueError(_("Commit or revert the Case Foundation opening before saving."))
        self.syncDentoCaseTrajectoryRegistry(parameterNode)
        self.buildDentoCaseRobotEnvironment(parameterNode)
        if self.isStep6CaseJawTransformNode(parameterNode.step6CaseJawTransform):
            parameterNode.step6CaseJawTransform.RemoveAttribute("DENTOBOT.TargetSegmentID")
            parameterNode.step6CaseJawTransform.RemoveAttribute(
                "DENTOBOT.TargetAttachedGeometryFingerprint"
            )
        parameterNode.dentoCaseSchemaVersion = DENTOCASE_STATE_SCHEMA_VERSION
        parameterNode.step6SchemaMigrationPending = False

    # Compatibility entrypoint retained for callers shipped with schema 2.
    prepareDentoCaseSchema2ForSave = prepareDentoCaseSchema3ForSave

    def hydrateDentoCaseStateAfterLoad(
        self, parameterNode, packageSchemaVersion: str
    ) -> None:
        # A failed/new restore cannot reuse another case's migration proof.
        self._caseBundleRegistryMigrationAudit = None
        savedEnvironment = None
        savedRegistry = None
        environmentPayload = str(parameterNode.step6EnvironmentJson or "").strip()
        registryPayload = str(parameterNode.step6TrajectoryRegistryJson or "").strip()
        if packageSchemaVersion in LEGACY_DENTOCASE_STATE_SCHEMA_VERSIONS:
            parameterNode.step6SchemaMigrationPending = True
            try:
                savedEnvironment = (
                    parse_robot_environment_snapshot(environmentPayload)
                    if environmentPayload
                    else None
                )
                savedRegistry = (
                    parse_trajectory_registry(registryPayload)
                    if registryPayload
                    else None
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                # Legacy content remains inspectable; no migration is promoted
                # from an invalid or incomplete derived snapshot.
                savedEnvironment = None
                savedRegistry = None
        elif packageSchemaVersion != DENTOCASE_STATE_SCHEMA_VERSION:
            raise CaseBundleError(_("Unsupported DentoCase state schema."))
        else:
            try:
                savedEnvironment = parse_robot_environment_snapshot(
                    environmentPayload
                )
                savedRegistry = parse_trajectory_registry(
                    registryPayload
                )
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise CaseBundleError(
                    _("The saved Step 6 environment or trajectory registry is invalid.")
                ) from exc
        # A registry saved before 2026-10-07 carries world-RAS provenance and a
        # planning-pose binding. It is validated against a rebuild with those same
        # legacy semantics, then upgraded by a normal sync (S6-MULTI-JAW-STALE-01).
        legacySavedRegistry = bool(
            savedRegistry is not None
            and REGISTRY_PROVENANCE_FRAME_KEY not in savedRegistry
        )
        rebuiltRegistry = self.syncDentoCaseTrajectoryRegistry(
            parameterNode, legacyProvenance=legacySavedRegistry
        )
        rebuiltEnvironment = self.buildDentoCaseRobotEnvironment(parameterNode)
        if packageSchemaVersion == DENTOCASE_STATE_SCHEMA_VERSION and savedRegistry is not None and canonical_json(savedRegistry) != canonical_json(
            rebuiltRegistry
        ):
            raise CaseBundleError(
                _("The saved trajectory registry does not match authoritative MRML geometry.")
            )
        if legacySavedRegistry:
            rebuiltRegistry = self.syncDentoCaseTrajectoryRegistry(parameterNode)
            parameterNode.step6SchemaMigrationPending = True
            logging.info(
                "Upgraded the saved trajectory registry to owning-jaw provenance."
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
            transform = parameterNode.step6CaseJawTransform
            transform.RemoveAttribute("DENTOBOT.TargetSegmentID")
            transform.RemoveAttribute(
                "DENTOBOT.TargetAttachedGeometryFingerprint"
            )
            if packageSchemaVersion in LEGACY_DENTOCASE_STATE_SCHEMA_VERSIONS:
                currentVolume = self.caseFoundationSourceVolumeFingerprint(
                    parameterNode.inputVolume
                )
                currentSegmentation = self.caseFoundationSourceSegmentationFingerprint(
                    parameterNode.teethSegmentation
                )
                savedVolume = str(
                    transform.GetAttribute("DENTOBOT.SourceVolumeFingerprint")
                    or (savedEnvironment.source_volume_fingerprint if savedEnvironment else "")
                )
                savedSegmentation = str(
                    transform.GetAttribute("DENTOBOT.SourceSegmentationFingerprint")
                    or (
                        savedEnvironment.source_segmentation_fingerprint
                        if savedEnvironment
                        else ""
                    )
                )
                exactSources = bool(
                    savedVolume
                    and savedSegmentation
                    and savedVolume == currentVolume
                    and savedSegmentation == currentSegmentation
                )
                if exactSources:
                    hinge_schema = str(
                        transform.GetAttribute("DENTOBOT.HingeModelSchema") or ""
                    )
                    if hinge_schema == self.CASE_FOUNDATION_HINGE_SCHEMA:
                        transform.SetAttribute("DENTOBOT.GeometryState", "Current")
                        transform.SetAttribute("DENTOBOT.StaleReason", None)
                        parameterNode.step6CaseJawPreparationMode = "CaseFoundationCurrent"
                        self.rebuildCaseFoundationDisplayVolumes(parameterNode)
                        foundation = self.buildCaseFoundationSnapshot(parameterNode)
                        transform.SetAttribute(
                            "DENTOBOT.PlanningPoseFingerprint",
                            foundation.planning_pose_fingerprint,
                        )
                    else:
                        transform.SetAttribute("DENTOBOT.GeometryState", "Stale")
                        transform.SetAttribute(
                            "DENTOBOT.StaleReason",
                            "LEGACY_JAW_OPENING_UNSUPPORTED",
                        )
                        parameterNode.step6CaseJawPreparationMode = "LegacyUnverified"
                else:
                    transform.SetAttribute("DENTOBOT.GeometryState", "Stale")
                    transform.SetAttribute(
                        "DENTOBOT.StaleReason",
                        "LEGACY_UNVERIFIED",
                    )
                    parameterNode.step6CaseJawPreparationMode = "LegacyUnverified"
            elif str(parameterNode.step6CaseJawPreparationMode) == "CaseFoundationCurrent":
                self.rebuildCaseFoundationDisplayVolumes(parameterNode)
        for node in (
            parameterNode.step6TargetJawFallbackAnatomy,
            parameterNode.step6OpenedTargetGeometryModel,
            parameterNode.step6OpenedTrajectoryLine,
        ):
            if node and slicer.mrmlScene.IsNodePresent(node):
                slicer.mrmlScene.RemoveNode(node)
        parameterNode.step6TargetJawFallbackAnatomy = None
        parameterNode.step6OpenedTargetGeometryModel = None
        parameterNode.step6OpenedTrajectoryLine = None
        base = parameterNode.robotBaseTransform
        if (
            packageSchemaVersion in LEGACY_DENTOCASE_STATE_SCHEMA_VERSIONS
            and self.isRobotBaseTransformNode(base)
            and bool(parameterNode.robotBaseMountLocked)
        ):
            authority = str(
                base.GetAttribute(self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE) or ""
            )
            compatible = bool(
                authority == self.ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY
                and str(base.GetAttribute("DENTOBOT.RobotProfileFingerprint") or "")
                == self.robotProfileFingerprint()
                and self.evaluateCaseFoundationEligibility(parameterNode)["pose"]["eligible"]
            )
            if not compatible:
                parameterNode.robotBaseMountLocked = False
                parameterNode.step6BasePlacementStatus = BasePlacementStatus.STALE.value
                self._applyRobotBaseMountInteractionState(parameterNode, False)
            else:
                foundation = self.evaluateCaseFoundationEligibility(parameterNode)
                base.SetAttribute(
                    "DENTOBOT.CaseFoundationFingerprint",
                    foundation["planning_pose_fingerprint"],
                )
                base.SetAttribute(
                    "DENTOBOT.RobotProfileFingerprint",
                    self.robotProfileFingerprint(),
                )
                parameterNode.step6BasePlacementStatus = (
                    BasePlacementStatus.PROVISIONAL_LOCKED.value
                )
                parameterNode.step6BasePlacementSource = MANUAL_SIMULATION_BASE_SOURCE
        # Package load never restores an active Step 6 branch or live runtime.
        parameterNode.step6PlanningContextImported = False
        if legacySavedRegistry:
            # Freeze the output only after strict legacy equality and all
            # hydration checks succeed. The post-event audit compares against
            # this snapshot; it must not simply accept a freshly rebuilt registry.
            self._caseBundleRegistryMigrationAudit = (
                canonical_json(savedRegistry), canonical_json(rebuiltRegistry)
            )

    def activateDentoCasePreparedBranch(
        self,
        parameterNode,
        branchId: str,
        *,
        registry: dict[str, object] | None = None,
        invalidateRuntime: bool = True,
        _forVerification: bool = False,
    ) -> dict[str, object]:
        registry = registry or self.syncDentoCaseTrajectoryRegistry(parameterNode)
        eligibility = (
            self.evaluatePreparedBranchForVerification(
                parameterNode, branchId, registry=registry
            )
            if _forVerification
            else self.evaluatePreparedBranchEligibility(
                parameterNode, branchId, registry=registry
            )
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
        dockingParameters = json.loads(dockingSummary["parametersJson"])
        activeDockingParameters = normalize_target_docking_parameters(
            pattern_radius_mm=parameterNode.targetDockingPatternRadiusMm,
            outer_diameter_mm=parameterNode.targetDockingOuterDiameterMm,
            bore_diameter_mm=parameterNode.targetDockingBoreDiameterMm,
            connector_diameter_mm=parameterNode.targetDockingConnectorDiameterMm,
            connector_thickness_mm=parameterNode.targetDockingConnectorThicknessMm,
            shared_depth_mm=parameterNode.targetDockingSharedDepthMm,
            individual_depths_mm=(
                parameterNode.targetDockingDepth1Mm,
                parameterNode.targetDockingDepth2Mm,
                parameterNode.targetDockingDepth3Mm,
                parameterNode.targetDockingDepth4Mm,
            ),
            individual_depths_enabled=(
                parameterNode.targetDockingIndividualDepthsEnabled
            ),
            yaw_deg=parameterNode.targetDockingYawDeg,
            collision_clearance_mm=parameterNode.targetDockingCollisionClearanceMm,
            clearance_mm=parameterNode.templateDockingClearanceMm,
            reinforcement_radial_mm=parameterNode.templateReinforcementRadialMm,
            processing_resolution_mm=parameterNode.templateSamplingSpacingMm,
        )
        insertionDirection = slicer.mrmlScene.GetNodeByID(
            branch["insertion_direction_node_id"]
        )
        patientShell = slicer.mrmlScene.GetNodeByID(branch["shell_node_id"])
        shellSummary = self.getPatientContactShellSummary(patientShell)
        visibleSupport = shellSummary["visibleSupport"]
        draftSupport = shellSummary["sourceModel"]
        boundaryCurve = shellSummary["boundary"]
        boundaryPlane = next(
            (
                node
                for node in slicer.util.getNodesByClass("vtkMRMLMarkupsPlaneNode")
                if self.isTemplateSupportBoundaryPlaneNode(node)
                and node.GetNodeReference(
                    self.TEMPLATE_SUPPORT_PLANE_SOURCE_MODEL_REFERENCE_ROLE
                )
                is draftSupport
                and node.GetNodeReference(
                    self.TEMPLATE_SUPPORT_PLANE_SOURCE_TRAJECTORY_REFERENCE_ROLE
                )
                is primaryTrajectory
            ),
            None,
        )
        undercutSurface = next(
            (
                node
                for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
                if self.isTemplateUndercutSurfaceModelNode(node)
                and node.GetNodeReference(
                    self.TEMPLATE_UNDERCUT_SOURCE_ANATOMY_REFERENCE_ROLE
                )
                is draftSupport
                and node.GetNodeReference(
                    self.TEMPLATE_UNDERCUT_SOURCE_SURFACE_REFERENCE_ROLE
                )
                is visibleSupport
                and node.GetNodeReference(
                    self.TEMPLATE_UNDERCUT_INSERTION_DIRECTION_REFERENCE_ROLE
                )
                is insertionDirection
            ),
            None,
        )
        finalModel = slicer.mrmlScene.GetNodeByID(branch["template_node_id"])
        finalSummary = self.getFinalPrintableTemplateSummary(finalModel)
        researchModels = []
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if not self.isResearchTemplateModelNode(node):
                continue
            try:
                summary = self.getResearchTemplateModelSummary(
                    node, node.GetAttribute("DENTOBOT.ModelRole") or ""
                )
            except (RuntimeError, ValueError, json.JSONDecodeError):
                continue
            if (
                summary["sourceModel"] is draftSupport
                and summary["trajectory"] in trajectories
            ):
                researchModels.append(node)
        researchShell = finalSummary["researchShell"] or next(
            (
                node
                for node in researchModels
                if node.GetAttribute("DENTOBOT.ModelRole")
                == "ResearchTemplateShell"
            ),
            None,
        )
        researchSleeve = finalSummary["researchSleeve"] or next(
            (
                node
                for node in researchModels
                if node.GetAttribute("DENTOBOT.ModelRole")
                == "ResearchTemplateSleeve"
            ),
            None,
        )
        finalizedShell = finalSummary["finalizedShell"] or next(
            (
                node
                for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
                if self.isFinalizedTemplateShellModelNode(node)
                and self.getFinalizedTemplateShellSummary(node)["sourceShell"]
                is researchShell
            ),
            None,
        )
        finalizedSummary = (
            self.getFinalizedTemplateShellSummary(finalizedShell)
            if finalizedShell
            else None
        )
        trimNode = finalizedSummary["editNode"] if finalizedSummary else None
        trimPlane = (
            trimNode if trimNode and trimNode.IsA("vtkMRMLMarkupsPlaneNode") else None
        )
        trimCurve = (
            trimNode
            if trimNode and trimNode.IsA("vtkMRMLMarkupsClosedCurveNode")
            else None
        )
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
            and activeDockingParameters == dockingParameters
            and parameterNode.templateInsertionDirection is insertionDirection
            and parameterNode.draftTemplateSupportModel is draftSupport
            and parameterNode.visibleTemplateSupportModel is visibleSupport
            and parameterNode.templateSupportBoundaryCurve is boundaryCurve
            and parameterNode.researchTemplateShellModel is researchShell
            and parameterNode.researchTemplateSleeveModel is researchSleeve
            and parameterNode.finalizedTemplateShellModel is finalizedShell
            and parameterNode.templateTrimPlane is trimPlane
            and parameterNode.templateTrimCurve is trimCurve
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
            "targetDockingPatternRadiusMm",
            "targetDockingOuterDiameterMm",
            "targetDockingBoreDiameterMm",
            "targetDockingConnectorDiameterMm",
            "targetDockingConnectorThicknessMm",
            "targetDockingSharedDepthMm",
            "targetDockingIndividualDepthsEnabled",
            "targetDockingDepth1Mm",
            "targetDockingDepth2Mm",
            "targetDockingDepth3Mm",
            "targetDockingDepth4Mm",
            "targetDockingYawDeg",
            "targetDockingCollisionClearanceMm",
            "templateDockingClearanceMm",
            "templateReinforcementRadialMm",
            "templateSamplingSpacingMm",
            "draftTemplateSupportModel",
            "templateSupportBoundaryPlane",
            "templateSupportBoundaryCurve",
            "visibleTemplateSupportModel",
            "templateInsertionDirection",
            "templateUndercutSurfaceModel",
            "templateUndercutBlockoutModel",
            "templateSupportToothSegmentIdsJson",
            "researchTemplateShellModel",
            "researchTemplateSleeveModel",
            "finalizedTemplateShellModel",
            "templateTrimPlane",
            "templateTrimCurve",
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
            parameterNode.targetDockingPatternRadiusMm = dockingParameters[
                "patternRadiusMm"
            ]
            parameterNode.targetDockingOuterDiameterMm = dockingParameters[
                "outerDiameterMm"
            ]
            parameterNode.targetDockingBoreDiameterMm = dockingParameters[
                "boreDiameterMm"
            ]
            parameterNode.targetDockingConnectorDiameterMm = dockingParameters[
                "connectorDiameterMm"
            ]
            parameterNode.targetDockingConnectorThicknessMm = dockingParameters[
                "connectorThicknessMm"
            ]
            parameterNode.targetDockingSharedDepthMm = dockingParameters[
                "sharedDepthMm"
            ]
            parameterNode.targetDockingIndividualDepthsEnabled = dockingParameters[
                "individualDepthsEnabled"
            ]
            (
                parameterNode.targetDockingDepth1Mm,
                parameterNode.targetDockingDepth2Mm,
                parameterNode.targetDockingDepth3Mm,
                parameterNode.targetDockingDepth4Mm,
            ) = dockingParameters["configuredIndividualDepthsMm"]
            parameterNode.targetDockingYawDeg = dockingParameters["yawDeg"]
            parameterNode.targetDockingCollisionClearanceMm = dockingParameters[
                "collisionClearanceMm"
            ]
            parameterNode.templateDockingClearanceMm = dockingParameters[
                "clearanceMm"
            ]
            parameterNode.templateReinforcementRadialMm = dockingParameters[
                "reinforcementRadialMm"
            ]
            parameterNode.templateSamplingSpacingMm = dockingParameters[
                "processingResolutionMm"
            ]
            parameterNode.draftTemplateSupportModel = draftSupport
            parameterNode.templateSupportBoundaryPlane = boundaryPlane
            parameterNode.templateSupportBoundaryCurve = boundaryCurve
            parameterNode.visibleTemplateSupportModel = visibleSupport
            parameterNode.templateInsertionDirection = insertionDirection
            parameterNode.templateUndercutSurfaceModel = undercutSurface
            parameterNode.templateUndercutBlockoutModel = shellSummary["blockoutModel"]
            parameterNode.templateSupportToothSegmentIdsJson = json.dumps(
                self.getDraftTemplateSupportModelSummary(draftSupport)[
                    "supportSegmentIds"
                ],
                separators=(",", ":"),
            )
            parameterNode.researchTemplateShellModel = researchShell
            parameterNode.researchTemplateSleeveModel = researchSleeve
            parameterNode.finalizedTemplateShellModel = finalizedShell
            parameterNode.templateTrimPlane = trimPlane
            parameterNode.templateTrimCurve = trimCurve
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
        selectedNodeIds = set(branch.get("model_node_ids", ())) | {
            node.GetID() for node in trajectories
        }
        branchNodeIds = {
            nodeId
            for candidate in registry["prepared_branches"].values()
            for nodeId in candidate.get("model_node_ids", ())
        } | set(trajectoryById[value].GetID() for value in trajectoryById) | {
            node.GetID()
            for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
            if self.isTargetDockingAssemblyModelNode(node)
        }
        for nodeId in branchNodeIds:
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            if node and node.GetDisplayNode():
                node.GetDisplayNode().SetVisibility(nodeId in selectedNodeIds)
        if invalidateRuntime:
            self.markStep6MotionDiagnosticStale(
                parameterNode, _("The active PreparedBranch changed.")
            )
        return eligibility

    def activateDentoCasePreparedBranchForVerification(
        self,
        parameterNode,
        branchId: str,
        *,
        registry: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Atomically select a complete Step 5B branch for Step 5C review."""

        return self.activateDentoCasePreparedBranch(
            parameterNode,
            branchId,
            registry=registry,
            _forVerification=True,
        )

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
            parameterNode.draftTemplateSupportModel = None
            parameterNode.templateSupportBoundaryPlane = None
            parameterNode.templateSupportBoundaryCurve = None
            parameterNode.visibleTemplateSupportModel = None
            parameterNode.targetDockingReferencePlane = None
            parameterNode.targetDockingAssemblyModel = None
            parameterNode.targetDockingYawConfirmed = False
            parameterNode.templateInsertionDirection = None
            parameterNode.templateUndercutSurfaceModel = None
            parameterNode.templateUndercutBlockoutModel = None
            parameterNode.templateSupportToothSegmentIdsJson = "[]"
            parameterNode.researchTemplateShellModel = None
            parameterNode.researchTemplateSleeveModel = None
            parameterNode.finalizedTemplateShellModel = None
            parameterNode.templateTrimPlane = None
            parameterNode.templateTrimCurve = None
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
