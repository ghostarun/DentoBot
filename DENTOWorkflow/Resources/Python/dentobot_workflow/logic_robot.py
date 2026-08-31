"""Extracted robot placement and simulation planning methods; public APIs remain on DENTOWorkflowLogic."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.logic_robot_placement import RobotPlacementLogicMixin


from dentobot_workflow.logic_robot_scene_sync import RobotSceneSyncLogicMixin


class RobotLogicMixin(RobotSceneSyncLogicMixin, RobotPlacementLogicMixin):







































    @staticmethod
    def step6TargetCollisionObjectName(parameterNode) -> str:
        segment_id = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            str(parameterNode.targetToothSegmentId or "unknown"),
        )
        return f"dentobot_target_tooth_{segment_id}"

    def step6TargetCollisionObjectId(self, parameterNode) -> str:
        segmentation = parameterNode.teethSegmentation
        target_id = str(parameterNode.targetToothSegmentId or "")
        if segmentation is None or not target_id:
            return ""
        source_id = f"{segmentation.GetID()}:target:{target_id}"
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if (
                node.GetAttribute("DENTOBOT.MoveItObstacleProxy") == "true"
                and node.GetAttribute("DENTOBOT.MoveItObstacleSource") == source_id
            ):
                # SlicerROS2 publishes CollisionObject.id from the model name,
                # not its MRML node ID.
                return str(node.GetName() or "")
        return ""

    @staticmethod
    def step6GuidanceCollisionObjectIds(parameterNode) -> tuple[str, ...]:
        """Return transient MoveIt IDs for approved guide/template geometry."""

        guidanceNodes = (
            [parameterNode.finalPrintableTemplateModel]
            if parameterNode.finalPrintableTemplateModel is not None
            else [
                parameterNode.draftTemplateSupportModel,
                parameterNode.targetDockingAssemblyModel,
            ]
        )
        sourceIds = {
            str(node.GetID()) for node in guidanceNodes if node is not None and node.GetID()
        }
        if not sourceIds:
            return ()
        result = []
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if (
                node.GetAttribute("DENTOBOT.MoveItObstacleProxy") == "true"
                and node.GetAttribute("DENTOBOT.MoveItObstacleSource") in sourceIds
                and node.GetName()
            ):
                result.append(str(node.GetName()))
        return tuple(sorted(dict.fromkeys(result)))

    def step6BurrProximityCollisionObjectIds(
        self,
        parameterNode,
    ) -> tuple[str, ...]:
        """Configured task objects eligible for tool-only exploratory relaxation.

        The task guard omits these burr-to-object pairs from the 1 mm research
        distance margin. Approach collision remains strict. Terminal/drilling
        preview may suppress only those configured burr pairs and reports each
        affected guard sample; all other collision checks remain authoritative.
        """

        guidanceSourceIds = {
            str(node.GetID())
            for node in (
                [parameterNode.finalPrintableTemplateModel]
                if parameterNode.finalPrintableTemplateModel is not None
                else [
                    parameterNode.draftTemplateSupportModel,
                    parameterNode.targetDockingAssemblyModel,
                ]
            )
            if node is not None and node.GetID()
        }
        segmentation = parameterNode.teethSegmentation
        segmentationPrefix = (
            f"{segmentation.GetID()}:" if segmentation is not None else ""
        )
        result = []
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if node.GetAttribute("DENTOBOT.MoveItObstacleProxy") != "true":
                continue
            sourceId = str(
                node.GetAttribute("DENTOBOT.MoveItObstacleSource") or ""
            )
            isGuidance = sourceId in guidanceSourceIds
            isCaseAnatomy = bool(
                segmentationPrefix
                and sourceId.startswith(segmentationPrefix)
                and (":target:" in sourceId or ":anatomy:" in sourceId)
            )
            if (isGuidance or isCaseAnatomy) and node.GetName():
                result.append(str(node.GetName()))
        return tuple(sorted(dict.fromkeys(result)))

    def importStep6PlanningContext(self, parameterNode) -> PlanningContextReport:
        report = validate_planning_context(
            self.buildPlanningContextNodeMap(parameterNode),
        )
        if not report.ready:
            raise ValueError(report.message)
        freshnessIssues = self.step6PlanningPackageFreshnessIssues(parameterNode)
        if freshnessIssues:
            raise ValueError(
                _(
                    "Planning package contains stale or unverified geometry: %1"
                ).replace("%1", " ".join(freshnessIssues))
            )
        base_transform = self.ensureRobotBaseTransform(
            parameterNode.robotBaseTransform,
        )
        parameterNode.robotBaseTransform = base_transform
        parameterNode.step6PlanningContextImported = True
        base_transform.SetAttribute(self.STEP6_PLANNING_CONTEXT_ATTRIBUTE, "true")
        jawIssues = self.step6CaseJawPlacementFreshnessIssues(parameterNode)
        if jawIssues and bool(parameterNode.robotBaseMountLocked):
            # A retained Step 6 base belongs to the anatomy pose/revision that
            # was saved.  Importing an unprepared or legacy case must expose
            # 6.0A instead of deadlocking it behind that old lock.
            self.setRobotBaseMountLocked(parameterNode, False)
            parameterNode.step6BasePlacementStatus = BasePlacementStatus.STALE.value
            parameterNode.step6BasePlacementSource = "restored-before-step6a-review"
            parameterNode.step6BasePlacementRevision = max(
                0,
                int(parameterNode.step6BasePlacementRevision),
            ) + 1
            self.invalidateStep6TaskConfirmation(
                parameterNode,
                _("Step 6A anatomy preparation is incomplete after package import."),
            )
        return report

    def step6PlanningPackageFreshnessIssues(self, parameterNode) -> list[str]:
        """Return upstream Steps 4A/4C/5C package-freshness failures.

        Case mouth opening is intentionally excluded.  It is a post-import
        Step 6 prerequisite: the case must remain active so the operator can
        place its four landmarks and derive the opened-jaw planning surface.
        """
        issues = []
        planning_report = validate_planning_context(
            self.buildPlanningContextNodeMap(parameterNode),
        )
        if not planning_report.ready:
            issues.append(planning_report.message)
        trajectory = parameterNode.trajectoryLine
        if trajectory is None or trajectory.GetNumberOfDefinedControlPoints() != 2:
            issues.append(_("Step 4A trajectory must contain exactly two points."))
        elif not trajectory.GetLocked():
            issues.append(_("Step 4A trajectory is not locked."))
        elif trajectory.GetAttribute("DENTOBOT.CoordinateSystem") != "SlicerRASmm":
            issues.append(_("Step 4A trajectory is not declared in Slicer RAS mm."))

        docking = parameterNode.targetDockingAssemblyModel
        if docking is None:
            issues.append(_("Step 4C docking assembly is missing."))
        else:
            state = docking.GetAttribute("DENTOBOT.GeometryState") or "Unknown"
            orientation = docking.GetAttribute("DENTOBOT.OrientationState") or "Unknown"
            if state != "Current" or orientation != "Confirmed":
                reason = docking.GetAttribute("DENTOBOT.StaleReason") or _(
                    "regenerate and confirm the docking assembly"
                )
                issues.append(
                    _("Step 4C docking assembly is %1/%2 (%3)")
                    .replace("%1", state)
                    .replace("%2", orientation)
                    .replace("%3", reason)
                )

        finalTemplate = parameterNode.finalPrintableTemplateModel
        if finalTemplate is None:
            issues.append(_("Step 5C printable template is missing."))
        else:
            state = finalTemplate.GetAttribute("DENTOBOT.GeometryState") or "Unknown"
            verification = (
                finalTemplate.GetAttribute("DENTOBOT.VerificationState") or "NotVerified"
            )
            if state != "Current" or verification not in {"PASS", "WARNING"}:
                reason = finalTemplate.GetAttribute("DENTOBOT.StaleReason") or _(
                    "regenerate and verify the printable template"
                )
                issues.append(
                    _("Step 5C printable template is %1/%2 (%3)")
                    .replace("%1", state)
                    .replace("%2", verification)
                    .replace("%3", reason)
                )
        return issues

    def step6PlanningContextFreshnessIssues(self, parameterNode) -> list[str]:
        """Return upstream and post-import Step 6 readiness failures."""
        issues = self.step6PlanningPackageFreshnessIssues(parameterNode)
        if bool(parameterNode.step6PlanningContextImported):
            issues.extend(self.step6CaseJawOpeningFreshnessIssues(parameterNode))
        return issues

    def _applyRobotBaseMountInteractionState(
        self,
        parameterNode,
        locked: bool,
    ) -> None:
        """Synchronize persistent lock evidence with editable MRML handles."""
        base_transform = parameterNode.robotBaseTransform
        plane_node = parameterNode.robotMountPlane
        if base_transform and self.isRobotBaseTransformNode(base_transform):
            base_transform.SetAttribute(
                "DENTOBOT.RobotBaseMountLocked",
                "true" if locked else "false",
            )
            display = base_transform.GetDisplayNode()
            if display:
                for method_name, value in (
                    ("SetEditorVisibility", not locked),
                    ("SetHandlesInteractive", not locked),
                    ("SetTranslationHandleVisibility", not locked),
                    ("SetRotationHandleVisibility", not locked),
                    ("SetScaleHandleVisibility", False),
                ):
                    method = getattr(display, method_name, None)
                    if method:
                        method(value)
        if plane_node and self.isRobotMountPlaneNode(plane_node):
            plane_node.SetLocked(True)
            plane_node.SetSelectable(False)
            display = plane_node.GetDisplayNode()
            if display:
                display.SetHandlesInteractive(False)
                display.SetTranslationHandleVisibility(False)
                display.SetRotationHandleVisibility(False)

    def step6BasePlacementFreshnessIssues(self, parameterNode) -> tuple[str, ...]:
        """Return fail-closed issues for the diagnostic Step 6 base contract."""
        base_transform = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base_transform):
            return (_("Load the local Step 6 robot before reviewing its base."),)
        issue = base_placement_source_issue(
            parameterNode.step6BasePlacementStatus,
            parameterNode.step6BasePlacementSource,
            bool(parameterNode.robotBaseMountLocked),
        )
        state = normalize_base_status(parameterNode.step6BasePlacementStatus)
        if (
            not parameterNode.robotBaseMountLocked
            or state
            not in {
                BasePlacementStatus.PROVISIONAL_LOCKED,
                BasePlacementStatus.REGISTERED_LOCKED,
            }
        ):
            issue = _(
                "Review Robot + CBCT placement and lock the Manual Simulation "
                "Base before continuing."
            )
        authority = str(
            base_transform.GetAttribute(
                self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE
            )
            or ""
        )
        issues = [issue] if issue else []
        if authority == self.ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY:
            issues.append(
                _(
                    "The base was copied from the quarantined circular mount plane. "
                    "Unlock it, reposition it manually in CBCT context, then review "
                    "and lock the Manual Simulation Base."
                )
            )
        return tuple(dict.fromkeys(item for item in issues if item))

    def quarantineLegacyRobotBasePlacement(self, parameterNode) -> str:
        """Reopen legacy/circular provisional placements for explicit review.

        The old mount plane was derived from the robot base and then copied back
        into that same base.  It therefore carries no independent forehead or
        registration evidence and cannot remain an accepted planning input.
        """
        base_transform = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base_transform):
            return ""
        status = normalize_base_status(parameterNode.step6BasePlacementStatus)
        source = str(parameterNode.step6BasePlacementSource or "")
        authority = str(
            base_transform.GetAttribute(
                self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE
            )
            or ""
        )
        already_quarantined = bool(
            not parameterNode.robotBaseMountLocked
            and status is BasePlacementStatus.STALE
            and source == QUARANTINED_CIRCULAR_BASE_SOURCE
        )
        legacy_locked = bool(
            (parameterNode.robotBaseMountLocked
             or status is BasePlacementStatus.PROVISIONAL_LOCKED)
            and source != MANUAL_SIMULATION_BASE_SOURCE
            and status is not BasePlacementStatus.REGISTERED_LOCKED
        )
        circular = authority == self.ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY
        if not (legacy_locked or circular):
            return ""
        message = _(
            "Restored Step 6 base placement predates the Manual Simulation Base "
            "contract or came from the circular mount-plane snap. It was reopened "
            "as Stale; reposition it manually in Robot + CBCT context and review "
            "it again before Task Home or planning."
        )
        if already_quarantined:
            return message
        was_modifying = parameterNode.StartModify()
        try:
            parameterNode.robotBaseMountLocked = False
            parameterNode.step6BasePlacementStatus = BasePlacementStatus.STALE.value
            parameterNode.step6BasePlacementSource = (
                QUARANTINED_CIRCULAR_BASE_SOURCE
            )
            parameterNode.step6BasePlacementRevision = max(
                0, int(parameterNode.step6BasePlacementRevision)
            ) + 1
        finally:
            parameterNode.EndModify(was_modifying)
        base_transform.SetAttribute("DENTOBOT.PlacementWarning", message)
        self.invalidateStep6TaskConfirmation(parameterNode, message)
        self._applyRobotBaseMountInteractionState(parameterNode, False)
        return message

    def setRobotBaseMountLocked(self, parameterNode, locked: bool) -> None:
        base_transform = parameterNode.robotBaseTransform
        if locked:
            if not self.isRobotBaseTransformNode(base_transform):
                raise ValueError(_("Load the local Step 6 robot before locking its base."))
            authority = str(
                base_transform.GetAttribute(
                    self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE
                )
                or ""
            )
            if authority == self.ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY:
                raise ValueError(
                    _(
                        "The legacy mount-plane snap is quarantined because the "
                        "plane was derived from this same base. Reposition the "
                        "Manual Simulation Base directly before reviewing it."
                    )
                )
        requested_status = (
            BasePlacementStatus.PROVISIONAL_LOCKED
            if locked
            else BasePlacementStatus.UNLOCKED
        )
        current_status = normalize_base_status(parameterNode.step6BasePlacementStatus)
        state_changed = bool(parameterNode.robotBaseMountLocked) != bool(locked) or (
            current_status is not requested_status
        )
        was_modifying = parameterNode.StartModify()
        try:
            parameterNode.robotBaseMountLocked = bool(locked)
            parameterNode.step6BasePlacementStatus = requested_status.value
            if state_changed:
                parameterNode.step6BasePlacementSource = (
                    MANUAL_SIMULATION_BASE_SOURCE if locked else "operator-unlocked"
                )
                parameterNode.step6BasePlacementRevision = max(
                    0, int(parameterNode.step6BasePlacementRevision)
                ) + 1
        finally:
            parameterNode.EndModify(was_modifying)
        if state_changed:
            self.invalidateStep6TaskConfirmation(
                parameterNode,
                _("Robot base lock state changed."),
            )
        if self.isRobotBaseTransformNode(base_transform):
            existing_authority = str(
                base_transform.GetAttribute(
                    self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE
                )
                or ""
            )
            if locked:
                base_transform.SetAttribute(
                    self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
                    self.ROBOT_BASE_MANUAL_REVIEWED_AUTHORITY,
                )
            elif existing_authority != self.ROBOT_BASE_CIRCULAR_SNAP_AUTHORITY:
                base_transform.SetAttribute(
                    self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
                    self.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
                )
                base_transform.SetAttribute("DENTOBOT.PlacementWarning", None)
        self._applyRobotBaseMountInteractionState(parameterNode, locked)

    def robotProfileFingerprint(self) -> str:
        return str(self.caseBundleRobotProfile().get("identitySha256") or "")

    def robotBaseFingerprint(self, parameterNode) -> str:
        base = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base):
            return ""
        pose_fingerprint = self.robotBasePoseFingerprint(base)
        return fingerprint(
            {
                "poseFingerprint": pose_fingerprint,
                "status": normalize_base_status(
                    parameterNode.step6BasePlacementStatus
                    or ("LegacyLocked" if parameterNode.robotBaseMountLocked else "Unlocked")
                ).value,
                "source": str(parameterNode.step6BasePlacementSource or "legacy-scene"),
                "sourceRevision": int(parameterNode.step6BasePlacementRevision),
                "authority": str(
                    base.GetAttribute(self.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE)
                    or ""
                ),
            }
        )

    def robotBasePoseFingerprint(self, base) -> str:
        if not self.isRobotBaseTransformNode(base):
            return ""
        matrix = self._worldMatrixFromTransform(base)
        elements = tuple(
            tuple(round(float(matrix.GetElement(row, column)), 9) for column in range(4))
            for row in range(4)
        )
        return fingerprint({"matrixToWorldRas": elements})

    def step6TrajectoryRevision(self, parameterNode) -> str:
        trajectory = parameterNode.trajectoryLine
        if trajectory is None:
            return ""
        summary = self.step6TrajectorySummary(parameterNode)
        if not summary.get("isValid"):
            return ""
        attributes = {}
        for name in (
            "DENTOBOT.CoordinateSystem",
            "DENTOBOT.LineageTargetSegmentID",
            "DENTOBOT.GeometryState",
            "DENTOBOT.SchemaVersion",
        ):
            value = trajectory.GetAttribute(name)
            if value is not None:
                attributes[name] = str(value)
        return fingerprint(
            {
                "entryRasMm": tuple(round(float(value), 9) for value in summary["entryRas"]),
                "targetRasMm": tuple(round(float(value), 9) for value in summary["targetRas"]),
                "locked": bool(trajectory.GetLocked()),
                "attributes": attributes,
            }
        )

    def step6TaskLimitsFingerprint(self, parameterNode) -> str:
        limits = self.getTaskJointLimits(parameterNode)
        return fingerprint(
            {
                "minimumDisplay": limits.as_display_vector(),
                "maximumDisplay": limits.as_display_max_vector(),
                "reviewedProposal": str(parameterNode.step6AssistedLimitProposalJson or ""),
            }
        )

    def taskHomeRecord(self, parameterNode):
        payload = str(parameterNode.step6TaskHomeJson or "").strip()
        return parse_task_home(payload) if payload else None

    def saveCurrentTaskHome(self, parameterNode, *, runtime_validation=None):
        base_issues = self.step6BasePlacementFreshnessIssues(parameterNode)
        if base_issues:
            raise ValueError(" ".join(base_issues))
        previous = self.taskHomeRecord(parameterNode)
        evidence = dict(runtime_validation or {})
        record = build_task_home(
            joint_positions_si_from_display(
                parameterNode.robotJoint1Deg,
                parameterNode.robotJoint2Mm,
                parameterNode.robotJoint3Deg,
                parameterNode.robotJoint4Mm,
                parameterNode.robotJoint5Deg,
                parameterNode.robotJoint6Deg,
            ),
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            robot_profile_fingerprint=self.robotProfileFingerprint(),
            revision=(previous.revision + 1 if previous else 1),
            runtime_validation_status=str(
                evidence.get("runtimeValidationStatus") or "Unreviewed"
            ),
            collision_audit_fingerprint=str(
                evidence.get("collisionAuditFingerprint") or ""
            ),
            guard_policy_fingerprint=str(
                evidence.get("guardPolicyFingerprint") or ""
            ),
            validated_at_utc=str(evidence.get("validatedAtUtc") or ""),
            minimum_clearance_mm=evidence.get("minimumClearanceMm"),
            world_object_count=int(evidence.get("worldObjectCount", 0)),
        )
        parameterNode.step6TaskHomeJson = canonical_json(record.to_dict())
        self.invalidateStep6TaskConfirmation(parameterNode, _("Task Home changed."))
        return record

    def recordTaskHomeRuntimeValidation(self, parameterNode, *, runtime_validation):
        """Upgrade a restored/unreviewed Home with live runtime evidence.

        Joint values and revision are preserved. A task confirmed against the
        prior unreviewed record is invalidated because its Home fingerprint did
        not contain the current collision-audit/guard provenance.
        """

        previous = self.taskHomeRecord(parameterNode)
        if previous is None:
            raise ValueError(_("Save Task Home before recording runtime validation."))
        evidence = dict(runtime_validation or {})
        record = build_task_home(
            dict(zip(previous.joint_names, previous.joint_positions_si)),
            base_fingerprint=previous.base_fingerprint,
            robot_profile_fingerprint=previous.robot_profile_fingerprint,
            revision=previous.revision,
            runtime_validation_status="Validated",
            collision_audit_fingerprint=str(
                evidence.get("collisionAuditFingerprint") or ""
            ),
            guard_policy_fingerprint=str(
                evidence.get("guardPolicyFingerprint") or ""
            ),
            validated_at_utc=str(evidence.get("validatedAtUtc") or ""),
            minimum_clearance_mm=evidence.get("minimumClearanceMm"),
            world_object_count=int(evidence.get("worldObjectCount", 0)),
        )
        parameterNode.step6TaskHomeJson = canonical_json(record.to_dict())
        self.invalidateStep6TaskConfirmation(
            parameterNode,
            _("Task Home runtime-validation evidence changed."),
        )
        return record

    def taskHomeFreshnessIssues(self, parameterNode) -> tuple[str, ...]:
        base_issues = self.step6BasePlacementFreshnessIssues(parameterNode)
        if base_issues:
            return base_issues
        try:
            record = self.taskHomeRecord(parameterNode)
        except (ValueError, json.JSONDecodeError):
            return (_("Saved Task Home record is invalid."),)
        if record is None:
            return (_("Save a case/base-specific Task Home."),)
        issues = []
        if record.base_fingerprint != self.robotBaseFingerprint(parameterNode):
            issues.append(_("Task Home belongs to a different base pose."))
        if record.robot_profile_fingerprint != self.robotProfileFingerprint():
            issues.append(_("Task Home belongs to different robot resources."))
        return tuple(issues)

    def proposeAssistedTaskLimits(self, parameterNode, workspaceResult):
        mechanical = default_task_joint_limits_from_urdf(self.robotDescriptionPaths()[0])
        previous_revision = 0
        try:
            previous = json.loads(parameterNode.step6AssistedLimitProposalJson or "{}")
            previous_revision = int(previous.get("revision", 0))
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
        proposal = build_assisted_limit_proposal(
            workspaceResult.accepted_joint_display_vectors,
            mechanical.as_display_vector(),
            mechanical.as_display_max_vector(),
            revision=previous_revision + 1,
            reviewed=False,
        )
        parameterNode.step6AssistedLimitProposalJson = canonical_json(proposal.to_dict())
        self.invalidateStep6TaskConfirmation(parameterNode, _("Workspace limit proposal changed."))
        return proposal

    def reviewAndApplyAssistedTaskLimits(self, parameterNode):
        try:
            data = json.loads(parameterNode.step6AssistedLimitProposalJson or "")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(_("Generate an assisted-limit proposal first.")) from exc
        minima = tuple(float(value) for value in data.get("minimum_display", ()))
        maxima = tuple(float(value) for value in data.get("maximum_display", ()))
        if len(minima) != 6 or len(maxima) != 6:
            raise ValueError(_("The assisted-limit proposal is invalid."))
        fields = (
            ("robotJoint1TaskMinDeg", "robotJoint1TaskMaxDeg"),
            ("robotJoint2TaskMinMm", "robotJoint2TaskMaxMm"),
            ("robotJoint3TaskMinDeg", "robotJoint3TaskMaxDeg"),
            ("robotJoint4TaskMinMm", "robotJoint4TaskMaxMm"),
            ("robotJoint5TaskMinDeg", "robotJoint5TaskMaxDeg"),
            ("robotJoint6TaskMinDeg", "robotJoint6TaskMaxDeg"),
        )
        for index, (minimum_field, maximum_field) in enumerate(fields):
            setattr(parameterNode, minimum_field, minima[index])
            setattr(parameterNode, maximum_field, maxima[index])
        data["reviewed"] = True
        parameterNode.step6AssistedLimitProposalJson = canonical_json(data)
        self.invalidateStep6TaskConfirmation(parameterNode, _("Reviewed task limits changed."))
        return data

    def assistedTaskLimitsReviewed(self, parameterNode) -> bool:
        try:
            data = json.loads(parameterNode.step6AssistedLimitProposalJson or "")
            return bool(data.get("reviewed"))
        except (ValueError, TypeError, json.JSONDecodeError):
            return False

    def confirmStep6Task(self, parameterNode):
        base_issues = self.step6BasePlacementFreshnessIssues(parameterNode)
        if base_issues:
            raise ValueError(" ".join(base_issues))
        home_issues = self.taskHomeFreshnessIssues(parameterNode)
        if home_issues:
            raise ValueError(" ".join(home_issues))
        if not self.assistedTaskLimitsReviewed(parameterNode):
            raise ValueError(_("Review and apply the assisted task-limit proposal first."))
        freshness = self.step6PlanningContextFreshnessIssues(parameterNode)
        if freshness:
            raise ValueError(" ".join(freshness))
        trajectory = self.step6TrajectorySummary(parameterNode)
        home = self.taskHomeRecord(parameterNode)
        record = build_task_snapshot(
            target_segment_id=str(parameterNode.targetToothSegmentId or ""),
            trajectory_revision=self.step6TrajectoryRevision(parameterNode),
            entry_ras_mm=trajectory["entryRas"],
            target_ras_mm=trajectory["targetRas"],
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            home_fingerprint=fingerprint(home.to_dict()),
            limits_fingerprint=self.step6TaskLimitsFingerprint(parameterNode),
            robot_profile_fingerprint=self.robotProfileFingerprint(),
            tool_frame=str(parameterNode.step6ToolFrame),
            tool_provenance="CAD-derived/provisional/un-calibrated",
            corridor_radius_mm=float(parameterNode.step6TrajectoryCorridorRadiusMm),
        )
        parameterNode.step6ConfirmedTaskJson = canonical_json(record.to_dict())
        return record

    def confirmedTaskRecord(self, parameterNode):
        payload = str(parameterNode.step6ConfirmedTaskJson or "").strip()
        return parse_task_snapshot(payload) if payload else None

    def motionDiagnosticRecord(self, parameterNode):
        payload = str(parameterNode.step6MotionDiagnosticJson or "").strip()
        return parse_motion_diagnostic_session(payload) if payload else None

    def markStep6MotionDiagnosticStale(self, parameterNode, reason: str) -> None:
        try:
            record = self.motionDiagnosticRecord(parameterNode)
        except (ValueError, json.JSONDecodeError):
            parameterNode.step6MotionDiagnosticJson = ""
            return
        if record is None or record.state == "Stale":
            return
        stale = build_motion_diagnostic_session(
            state="Stale",
            stale_reason=str(reason),
            task_fingerprint=record.task_fingerprint,
            base_fingerprint=record.base_fingerprint,
            trajectory_fingerprint=record.trajectory_fingerprint,
            robot_profile_fingerprint=record.robot_profile_fingerprint,
            collision_audit_fingerprint=record.collision_audit_fingerprint,
            planning_parameters_fingerprint=record.planning_parameters_fingerprint,
            candidate_records=record.candidate_records,
            selected_candidate_index=record.selected_candidate_index,
            failure_classification=record.failure_classification,
            operator_review_state=record.operator_review_state,
            generated_at_utc=record.generated_at_utc,
        )
        parameterNode.step6MotionDiagnosticJson = canonical_json(stale.to_dict())

    def motionDiagnosticFreshnessIssues(self, parameterNode) -> tuple[str, ...]:
        try:
            record = self.motionDiagnosticRecord(parameterNode)
        except (ValueError, json.JSONDecodeError):
            return (_("The saved motion-diagnostic record is invalid."),)
        if record is None:
            return (_("No Step 6 motion-diagnostic record is available."),)
        issues = []
        if record.state != "Current":
            issues.append(record.stale_reason or _("Motion diagnostic is Stale."))
        if record.base_fingerprint != self.robotBaseFingerprint(parameterNode):
            issues.append(_("Motion diagnostic belongs to a different base pose."))
        if record.trajectory_fingerprint != self.step6TrajectoryRevision(parameterNode):
            issues.append(_("Motion diagnostic belongs to a different trajectory."))
        if record.robot_profile_fingerprint != self.robotProfileFingerprint():
            issues.append(_("Motion diagnostic belongs to different robot resources."))
        try:
            collision_audit = self.collisionSceneAuditRecord(parameterNode)
        except (ValueError, json.JSONDecodeError):
            collision_audit = None
        if (
            collision_audit is None
            or record.collision_audit_fingerprint
            != collision_audit.audit_fingerprint
        ):
            issues.append(_("Motion diagnostic belongs to a different collision scene."))
        return tuple(dict.fromkeys(issues))

    def confirmedTaskFreshnessIssues(self, parameterNode) -> tuple[str, ...]:
        base_issues = self.step6BasePlacementFreshnessIssues(parameterNode)
        if base_issues:
            return base_issues
        try:
            snapshot = self.confirmedTaskRecord(parameterNode)
        except (ValueError, json.JSONDecodeError):
            return (_("Confirmed Step 6 task record is invalid."),)
        if snapshot is None:
            return (_("Confirm the immutable Step 6 task snapshot."),)
        home = self.taskHomeRecord(parameterNode)
        return task_snapshot_invalidation_reasons(
            snapshot,
            target_segment_id=str(parameterNode.targetToothSegmentId or ""),
            trajectory_revision=self.step6TrajectoryRevision(parameterNode),
            base_fingerprint=self.robotBaseFingerprint(parameterNode),
            home_fingerprint=fingerprint(home.to_dict()) if home else "",
            limits_fingerprint=self.step6TaskLimitsFingerprint(parameterNode),
            robot_profile_fingerprint=self.robotProfileFingerprint(),
            tool_frame=str(parameterNode.step6ToolFrame),
        )

    def invalidateStep6TaskConfirmation(
        self,
        parameterNode,
        reason: str,
        *,
        makeBaseStale: bool = False,
    ) -> None:
        had_confirmation = bool(str(parameterNode.step6ConfirmedTaskJson or "").strip())
        base_status = normalize_base_status(parameterNode.step6BasePlacementStatus)
        has_reviewed_base = bool(
            parameterNode.robotBaseMountLocked
            or base_status
            in {
                BasePlacementStatus.PROVISIONAL_LOCKED,
                BasePlacementStatus.REGISTERED_LOCKED,
                BasePlacementStatus.STALE,
            }
        )
        base_made_stale = bool(makeBaseStale and has_reviewed_base)
        was_modifying = parameterNode.StartModify()
        try:
            parameterNode.step6ConfirmedTaskJson = ""
            if base_made_stale:
                if (
                    parameterNode.robotBaseMountLocked
                    or base_status is not BasePlacementStatus.STALE
                ):
                    parameterNode.step6BasePlacementRevision = max(
                        0, int(parameterNode.step6BasePlacementRevision)
                    ) + 1
                parameterNode.step6BasePlacementStatus = BasePlacementStatus.STALE.value
                parameterNode.robotBaseMountLocked = False
        finally:
            parameterNode.EndModify(was_modifying)
        if base_made_stale:
            self._applyRobotBaseMountInteractionState(parameterNode, False)
        workspace = self.robotWorkspaceModelNode()
        if workspace is not None:
            workspace.SetAttribute("DENTOBOT.WorkspaceState", "Stale")
        if had_confirmation:
            logging.warning("Invalidated Step 6 task confirmation: %s", reason)
        self.markStep6MotionDiagnosticStale(parameterNode, reason)

    def getTaskJointLimits(self, parameterNode) -> TaskJointLimits:
        urdf_path, _package_root = self.robotDescriptionPaths()
        urdf_limits = default_task_joint_limits_from_urdf(urdf_path)
        task_limits = build_task_joint_limits_from_parameter_values(
            j1_min=parameterNode.robotJoint1TaskMinDeg,
            j1_max=parameterNode.robotJoint1TaskMaxDeg,
            j2_min=parameterNode.robotJoint2TaskMinMm,
            j2_max=parameterNode.robotJoint2TaskMaxMm,
            j3_min=parameterNode.robotJoint3TaskMinDeg,
            j3_max=parameterNode.robotJoint3TaskMaxDeg,
            j4_min=parameterNode.robotJoint4TaskMinMm,
            j4_max=parameterNode.robotJoint4TaskMaxMm,
            j5_min=parameterNode.robotJoint5TaskMinDeg,
            j5_max=parameterNode.robotJoint5TaskMaxDeg,
            j6_min=parameterNode.robotJoint6TaskMinDeg,
            j6_max=parameterNode.robotJoint6TaskMaxDeg,
        )
        return apply_task_joint_limits_to_display_ranges(task_limits, urdf_limits)

    def createOrUpdateRobotWorkspace(
        self,
        parameterNode,
    ) -> tuple[vtkMRMLModelNode, WorkspaceSampleResult]:
        """Create a base-parented, deterministic provisional-TCP reach cloud."""
        base_transform = parameterNode.robotBaseTransform
        if not self.isRobotBaseTransformNode(base_transform):
            raise ValueError(_("Load the Step 6 robot and place its base first."))
        sample_count = int(parameterNode.robotWorkspaceSampleCount)
        if sample_count < 50 or sample_count > 5000:
            raise ValueError(_("Workspace sample count must be between 50 and 5000."))
        urdf_path, package_root = self.robotDescriptionPaths()
        base_world = self._numpyFromVtkMatrix(
            self._worldMatrixFromTransform(base_transform),
        )
        result = sample_filtered_tcp_workspace(
            limits=self.getTaskJointLimits(parameterNode),
            sample_count=sample_count,
            current_display_joints=(
                parameterNode.robotJoint1Deg,
                parameterNode.robotJoint2Mm,
                parameterNode.robotJoint3Deg,
                parameterNode.robotJoint4Mm,
                parameterNode.robotJoint5Deg,
                parameterNode.robotJoint6Deg,
            ),
            urdf_path=urdf_path,
            package_root=package_root,
            base_world_matrix=base_world,
            coarse_self_clearance_mm=max(
                5.0,
                float(parameterNode.robotCoarseSelfClearanceMm),
            ),
            environment_points_mm=self.step6EnvironmentObstaclePointsMm(parameterNode),
            environment_clearance_mm=float(parameterNode.robotEnvironmentClearanceMm),
        )
        if not result.accepted_tcp_base_mm:
            raise RuntimeError(
                _(
                    "All sampled configurations were rejected. Widen valid task "
                    "limits or review the draft clearances/base placement."
                )
            )

        points = vtk.vtkPoints()
        vertices = vtk.vtkCellArray()
        for point in result.accepted_tcp_base_mm:
            point_id = points.InsertNextPoint(*point)
            vertices.InsertNextCell(1)
            vertices.InsertCellPoint(point_id)
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetVerts(vertices)

        model = self.robotWorkspaceModelNode()
        if not model:
            model = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLModelNode",
                "[Step 6] DENTO Filtered TCP Workspace",
            )
        model.SetName("[Step 6] DENTO Filtered TCP Workspace")
        model.SetAttribute("DENTOBOT.ModelRole", self.ROBOT_WORKSPACE_MODEL_ROLE)
        model.SetAttribute("DENTOBOT.Status", "SimulationOnly")
        model.SetAttribute("DENTOBOT.WorkspaceState", "Current")
        model.SetAttribute("DENTOBOT.WorkspaceAlgorithm", "Halton6D+URDFFK+AABB")
        model.SetAttribute("DENTOBOT.WorkspaceRequested", str(result.requested_count))
        model.SetAttribute("DENTOBOT.WorkspaceAccepted", str(result.accepted_count))
        model.SetAndObservePolyData(polydata)
        model.SetAndObserveTransformNodeID(base_transform.GetID())
        model.SetSaveWithScene(False)
        model.CreateDefaultDisplayNodes()
        display = model.GetDisplayNode()
        if display:
            display.SetVisibility(True)
            display.SetVisibility2D(False)
            display.SetVisibility3D(True)
            display.SetColor(0.10, 0.82, 0.95)
            display.SetOpacity(0.55)
            display.SetRepresentation(0)  # vtkMRMLDisplayNode::Points
            display.SetPointSize(3.0)
            display.SetLighting(False)
        model.SetSelectable(False)
        return model, result

    def deleteRobotWorkspaceModel(self) -> bool:
        model = self.robotWorkspaceModelNode()
        if not model:
            return False
        slicer.mrmlScene.RemoveNode(model)
        return True

    def applyTaskJointLimitsToJointControls(self, parameterNode) -> TaskJointLimits:
        limits = self.getTaskJointLimits(parameterNode)
        display_ranges = apply_task_joint_limits_to_display_ranges(
            limits,
            default_task_joint_limits_from_urdf(self.robotDescriptionPaths()[0]),
        )
        return display_ranges

    def resetTaskJointLimitsToUrdf(self, parameterNode) -> TaskJointLimits:
        urdf_path, _package_root = self.robotDescriptionPaths()
        limits = default_task_joint_limits_from_urdf(urdf_path)
        parameterNode.robotJoint1TaskMinDeg = limits.joint_1.minimum
        parameterNode.robotJoint1TaskMaxDeg = limits.joint_1.maximum
        parameterNode.robotJoint2TaskMinMm = limits.joint_2.minimum
        parameterNode.robotJoint2TaskMaxMm = limits.joint_2.maximum
        parameterNode.robotJoint3TaskMinDeg = limits.joint_3.minimum
        parameterNode.robotJoint3TaskMaxDeg = limits.joint_3.maximum
        parameterNode.robotJoint4TaskMinMm = limits.joint_4.minimum
        parameterNode.robotJoint4TaskMaxMm = limits.joint_4.maximum
        parameterNode.robotJoint5TaskMinDeg = limits.joint_5.minimum
        parameterNode.robotJoint5TaskMaxDeg = limits.joint_5.maximum
        parameterNode.robotJoint6TaskMinDeg = limits.joint_6.minimum
        parameterNode.robotJoint6TaskMaxDeg = limits.joint_6.maximum
        return limits

    def planStep6TrajectoryMotion(self, parameterNode) -> MotionPlanResult:
        if not parameterNode.step6PlanningContextImported:
            raise ValueError(
                _("Import the Step 6 planning package before motion planning.")
            )
        freshnessIssues = self.step6PlanningContextFreshnessIssues(parameterNode)
        if freshnessIssues:
            parameterNode.step6PlanningContextImported = False
            raise ValueError(
                _("Step 6 planning context became stale: %1").replace(
                    "%1", " ".join(freshnessIssues)
                )
            )
        base_issues = self.step6BasePlacementFreshnessIssues(parameterNode)
        if base_issues:
            raise ValueError(" ".join(base_issues))
        if not parameterNode.robotBaseTransform:
            raise ValueError(_("Load or create the Step 6 robot base first."))
        ros_active = self.isRos2MotionControlActive(parameterNode.robotBaseTransform)
        if not step6_motion_plan_robot_ready(
            ros_motion_active=ros_active,
            mrml_link_count=len(self.robotModelNodes()),
        ):
            raise ValueError(
                _("Load the ROS robot or MRML fallback before motion planning.")
            )
        summary = self.step6TrajectorySummary(parameterNode)
        if not summary.get("isValid"):
            raise ValueError(_("Select a valid Entry-to-Target trajectory first."))

        urdf_path, package_root = self.robotDescriptionPaths()
        base_world = self._numpyFromVtkMatrix(
            self._worldMatrixFromTransform(parameterNode.robotBaseTransform),
        )
        start_display = (
            parameterNode.robotJoint1Deg,
            parameterNode.robotJoint2Mm,
            parameterNode.robotJoint3Deg,
            parameterNode.robotJoint4Mm,
            parameterNode.robotJoint5Deg,
            parameterNode.robotJoint6Deg,
        )
        limits = self.getTaskJointLimits(parameterNode)
        if ros_active:
            obstacle_count = self.syncStep6MoveItPlanningScene(parameterNode)
            moveit_result = plan_moveit_cartesian_path(
                entry_ras_mm=summary["entryRas"],
                target_ras_mm=summary["targetRas"],
                sample_count=int(parameterNode.robotMotionPlanSampleCount),
                base_transform=parameterNode.robotBaseTransform,
                avoid_collisions=True,
                minimum_fraction=0.99,
            )
            return MotionPlanResult(
                success=moveit_result.success,
                message=(
                    f"{moveit_result.message} Planning scene contained "
                    f"{obstacle_count} Step 6 collision surface(s); the manual "
                    "command guard requires the 1 mm research self/world clearance."
                ),
                waypoint_joint_vectors_si=moveit_result.waypoint_joint_vectors_si,
                planner="moveit_cartesian",
                cartesian_fraction=moveit_result.fraction,
                waypoint_times_sec=moveit_result.waypoint_times_sec,
            )
        environment_points = self.step6EnvironmentObstaclePointsMm(parameterNode)
        return plan_trajectory_motion(
            entry_ras_mm=summary["entryRas"],
            target_ras_mm=summary["targetRas"],
            start_display_joints=start_display,
            limits=limits,
            urdf_path=urdf_path,
            package_root=package_root,
            base_world_matrix=base_world,
            sample_count=int(parameterNode.robotMotionPlanSampleCount),
            coarse_self_clearance_mm=max(
                5.0,
                float(parameterNode.robotCoarseSelfClearanceMm),
            ),
            environment_points_mm=environment_points,
            environment_clearance_mm=float(parameterNode.robotEnvironmentClearanceMm),
        )

    def step6ApproachPoints(self, parameterNode):
        summary = self.step6TrajectorySummary(parameterNode)
        if not summary.get("isValid"):
            raise ValueError(_("Select a valid Entry-to-Target trajectory first."))
        return approach_points(
            summary["entryRas"],
            summary["targetRas"],
            float(parameterNode.step6ApproachStandoffMm),
        )

    def _worldMatrixFromTransform(
        self,
        transform_node: vtkMRMLLinearTransformNode,
    ) -> vtk.vtkMatrix4x4:
        matrix = vtk.vtkMatrix4x4()
        transform_node.GetMatrixTransformToWorld(matrix)
        return matrix

    def deleteRobotPlacement(
        self,
        baseTransform: vtkMRMLLinearTransformNode | None,
        planeNode: vtkMRMLMarkupsPlaneNode | None,
    ) -> list[str]:
        nodes = [*self.robotModelNodes(), *self.robotLinkTransformNodes()]
        workspace = self.robotWorkspaceModelNode()
        if workspace:
            nodes.append(workspace)
        if self.isRobotBaseTransformNode(baseTransform):
            nodes.append(baseTransform)
        if self.isRobotMountPlaneNode(planeNode):
            nodes.append(planeNode)
        nodes.extend(self.step6ForeheadProxyNodes())
        removed = []
        for node in dict.fromkeys(nodes):
            if slicer.mrmlScene.IsNodePresent(node):
                removed.append(node.GetName())
                slicer.mrmlScene.RemoveNode(node)
        return removed
