"""Extracted robot application shell methods; public APIs remain on RobotWidgetMixin."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite

from .runtime import *
from .workflow_progress import WorkflowProgress

from DENTOStep6Planning import TaskSpaceRoi
from DENTOROS2Bridge import show_goal_robot_joint_positions
from DENTOStep6State import JOINT_NAMES


class RobotShellWidgetMixin:
    def _setupRobotSimulationShellPanel(self) -> None:
        if self._robotSimulationPanel is not None:
            return
        self._robotSimulationPanel = DENTORobotSimulationPanel(
            self.ui.robotPlacementCollapsibleButton,
            {
                "connect": self._onShellConnectRobot,
                "disconnect": self._onShellDisconnectRobot,
                "load_fallback": self._onShellLoadFallbackRobot,
                "create_goal": self._onShellCreateTcpGoal,
                "solve_ik": self._onShellSolveIk,
                "plan_goal": self._onShellPlanGoal,
                "refresh": self._refreshShellRobotCapabilities,
                "sync_collision": self._onShellSyncCollisionScene,
                "check_state": self._onShellCheckRobotState,
                "enable_cbct_rendering": self._onStep6EnableCbctRendering,
                "cbct_preset": self._onStep6CbctPresetChanged,
                "create_proxy": self._onStep6CreateForeheadProxy,
                "placement_review": self._onStep6PlacementReview,
                "appearance_changed": self._onStep6AppearanceChanged,
                "save_home": self._onStep6SaveTaskHome,
                "apply_home": self._onStep6ApplyTaskHome,
                "roi_from_incisors": self._onStep6UseCurrentIncisorMidpoint,
                "roi_edited": self._onStep6TaskSpaceRoiEdited,
                "revalidate_workspace": self._onStep6RevalidateWorkspace,
                "review_limits": self._onStep6ReviewAssistedLimits,
                "confirm_task": self._onStep6ConfirmTask,
                "reset_manual_draft": self._onShellResetManualJogDraft,
                "manual_draft_changed": self._onShellManualJogDraftChanged,
                "check_manual_draft_state": self._onShellCheckManualRobotDraftState,
                "reconcile_manual_jog": self._onShellReconcileManualRobotJog,
                "guarded_manual_jog": self._onShellGuardedManualJog,
                "export_manual_record": self._onStep6ExportManualRecord,
                "expert_diagnostics": self._onStep6OpenExpertDiagnostics,
                "plan_approach": self._onStep6PlanApproach,
                "check_preentry_ik": self._onStep6CheckPreEntryIK,
                "check_planning_p1": lambda: self._onStep6CheckPlanningStage("P1"),
                "check_planning_p2": lambda: self._onStep6CheckPlanningStage("P2"),
                "check_planning_p3": lambda: self._onStep6CheckPlanningStage("P3"),
                "compare_planners": self._onStep6ComparePlanners,
                "cancel_planner_comparison": self._onStep6CancelPlannerComparison,
                "show_planner_comparison": self._onStep6ShowPlannerComparison,
                "template_collision_override": (
                    self._onStep6TemplateCollisionOverride
                ),
                "begin_anatomy_review": self._onStep6BeginAnatomyReview,
                "edit_anatomy_review": self._onStep6EditAnatomyReview,
                "activate_anatomy_review": self._onStep6ActivateAnatomyReview,
                "discard_anatomy_review": self._onStep6DiscardAnatomyReview,
                "preview_approach": self._onStep6PreviewApproach,
                "show_motion_diagnostics": self._onStep6ShowMotionDiagnostics,
                "plan_drilling": self._onStep6PlanDrilling,
                "preview_drilling": self._onStep6PreviewDrilling,
                "stop_preview": self._onStep6StopPreview,
                "return_home": self._onStep6ReturnHome,
            },
        )
        self._setupStep6SubstepNavigator()
        self._setupStep3SubstepNavigator()
        self._step61PlacementMirrorStatusLabel = qt.QLabel(
            _("Complete Step 3B offline placement, then review it here."),
            self.ui.robotPlacementCollapsibleButton,
        )
        self._step61PlacementMirrorStatusLabel.objectName = (
            "DENTOBOTStep61PlacementMirrorStatusLabel"
        )
        self._step61PlacementMirrorStatusLabel.wordWrap = True
        self._step61PlacementMirrorStatusLabel.styleSheet = (
            "color: #b36b00; font-weight: 600;"
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._step61PlacementMirrorStatusLabel
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.visualizationGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.homeGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.workspaceReviewGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.runtimeGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.confirmationGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.goalGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.manualJogGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.collisionGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.approachGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.drillingGroup
        )
        self.ui.robotPlacementCollapsibleButton.text = _(
            "Step 6 — Native Placement-to-Task Simulation"
        )
        self.ui.robotPlacementDescriptionLabel.text = _(
            "Validate the case, place the local robot in CBCT context, connect "
            "ROS/MoveIt, save a live-validated Task Home, review workspace-assisted limits, confirm "
            "one immutable task, then preview guarded approach and drilling phases."
        )
        self.ui.step6MountLockGroupBox.title = _(
            "6.1A — Offline Robot Preview and Manual Simulation Base"
        )
        self.ui.step6MountLockDescriptionLabel.text = _(
            "Adjust the existing Manual Simulation Base controls and review its "
            "world-RAS pose below. The candidate stays unaccepted until you "
            "choose Accept Base; that action uses the existing base lock and "
            "collision-scene resynchronization path. This is diagnostic "
            "placement, not physical mount or registration truth."
        )
        self.ui.lockRobotBaseMountButton.text = _("Accept Base")
        self.ui.lockRobotBaseMountButton.toolTip = _(
            "Accept the reviewed current Base candidate through the existing "
            "lockBase path. Failed scene or placement checks leave it unaccepted."
        )
        self.ui.unlockRobotBaseMountButton.text = _("Unlock Accepted Base")
        self._robotSimulationPanel.runtimeGroup.title = _(
            "6.1B — Connect ROS + MoveIt"
        )
        self.ui.step6TaskJointLimitsGroupBox.title = _(
            "6.2 — Live Joint State for Task Home"
        )
        self.ui.step6WorkspaceGroupBox.title = _("6.3 — Workspace and Assisted Limits")
        self.ui.step6TrajectoryPlanningGroupBox.visible = False
        self.ui.ros2MotionControlGroupBox.visible = False
        self.ui.ros2MotionControlGroupBox.enabled = False

    def _setupStep6SubstepNavigator(self) -> None:
        """Add one shared Step 6 navigator to the normal module panel."""
        if self._step6SubstepNavigator is not None:
            return
        navigator = qt.QGroupBox(
            _("Step 6 workflow — one task at a time"),
            self.ui.robotPlacementCollapsibleButton,
        )
        navigator.objectName = "DENTOBOTStep6SubstepNavigator"
        layout = qt.QGridLayout(navigator)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(4)
        previousButton = qt.QPushButton(_("‹ Back"), navigator)
        previousButton.objectName = "DENTOBOTStep6PreviousSubstepButton"
        comboBox = qt.QComboBox(navigator)
        comboBox.objectName = "DENTOBOTStep6SubstepComboBox"
        for title in workspace_for_stage(10).substep_titles:
            comboBox.addItem(_(title))
        nextButton = qt.QPushButton(_("Next ›"), navigator)
        nextButton.objectName = "DENTOBOTStep6NextSubstepButton"
        hint = qt.QLabel(
            _(
                "Only the selected substep is shown. Earlier state stays in "
                "MRML; later actions remain gated until their prerequisites are current."
            ),
            navigator,
        )
        hint.wordWrap = True
        hint.styleSheet = "color: #5f6368;"
        layout.addWidget(previousButton, 0, 0)
        layout.addWidget(comboBox, 0, 1)
        layout.addWidget(nextButton, 0, 2)
        layout.addWidget(hint, 1, 0, 1, 3)
        layout.setColumnStretch(1, 1)
        self.ui.robotPlacementVerticalLayout.insertWidget(1, navigator)
        comboBox.connect(
            "currentIndexChanged(int)",
            self._onStep6SubstepChanged,
        )
        previousButton.connect(
            "clicked(bool)",
            self._onPreviousStep6Substep,
        )
        nextButton.connect(
            "clicked(bool)",
            self._onNextStep6Substep,
        )
        self._step6SubstepNavigator = navigator
        self._step6SubstepComboBox = comboBox
        self._step6PreviousSubstepButton = previousButton
        self._step6NextSubstepButton = nextButton
        self._configureRobotSimulationShellSubstep(0)

    def _onStep6SubstepChanged(self, substep_index: int) -> None:
        if self._updatingStep6SubstepNavigation:
            return
        self._configureRobotSimulationShellSubstep(substep_index)

    def _onPreviousStep6Substep(self, checked: bool = False) -> None:
        del checked
        self._configureRobotSimulationShellSubstep(self._step6SubstepIndex - 1)

    def _onNextStep6Substep(self, checked: bool = False) -> None:
        del checked
        self._configureRobotSimulationShellSubstep(self._step6SubstepIndex + 1)

    def _refreshShellRobotCapabilities(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        self._robotSimulationPanel.updateCapabilities(
            self._robotWorkflowFacade.capabilities()
        )

    def _onShellConnectRobot(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        if getattr(self, "_workflowActionBusy", False):
            return
        self._workflowActionBusy = True
        progress = WorkflowProgress("Step 6.1 connect ROS + MoveIt")
        try:
            result = self._robotWorkflowFacade.connect(
                open_motion_module=False,
                progress=lambda phase, done=None, total=None: progress.update(
                    phase, done, total, can_cancel=False
                ),
            )
            progress.update("Refreshing connected workflow", can_cancel=False)
            remediationConnected = bool(result.details.get("runtimeConnected", False))
            if result.success or remediationConnected:
                self._updateRobotPlacement()
                self._applyStep6RecommendedView()
            self._refreshShellRobotCapabilities()
            # Capability refresh writes a generic runtime summary. Restore the
            # action-specific result after it.
            self._robotSimulationPanel.showRuntimeResult(result)
        finally:
            progress.close()
            self._workflowActionBusy = False
        if remediationConnected:
            slicer.util.warningDisplay(result.message)
        elif not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellDisconnectRobot(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        if getattr(self, "_workflowActionBusy", False):
            return
        self._workflowActionBusy = True
        progress = WorkflowProgress("Step 6.1 disconnect ROS + MoveIt")
        try:
            result = self._robotWorkflowFacade.disconnect(
                progress=lambda phase, done=None, total=None: progress.update(
                    phase, done, total, can_cancel=False
                )
            )
            progress.update("Refreshing disconnected workflow", can_cancel=False)
            if result.success:
                self._updateRobotPlacement()
            self._refreshShellRobotCapabilities()
            self._robotSimulationPanel.showRuntimeResult(result)
        finally:
            progress.close()
            self._workflowActionBusy = False
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellLoadFallbackRobot(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.loadRobot()
        self._robotSimulationPanel.showRuntimeResult(result)
        if result.success:
            self._updateRobotPlacement()
            if self._isStep3BActive():
                self._applyStep3BRecommendedView()
                self._ensureOfflinePlacementSceneVisible()
            else:
                self.onFrameStep6ResearchWorkspace()
        else:
            slicer.util.errorDisplay(result.message)
        self._refreshShellRobotCapabilities()

    def _onShellCreateTcpGoal(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.ensureTcpGoal()
        self._robotSimulationPanel.showGoalResult(result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellResetManualJogDraft(self) -> None:
        if self._robotSimulationPanel:
            self._robotSimulationPanel.resetManualJogDraft()

    def _onShellManualJogDraftChanged(
        self, joint_positions_si: Mapping[str, float]
    ) -> None:
        if not self._robotSimulationPanel:
            return
        ok, message = show_goal_robot_joint_positions(joint_positions_si)
        self._robotSimulationPanel.setManualJogDraftDisplayResult(ok, message)

    def _onShellCheckManualRobotDraftState(
        self, joint_positions_si: Mapping[str, float]
    ) -> None:
        panel = self._robotSimulationPanel
        if not panel:
            return
        facade = self._robotWorkflowFacade
        if not facade or getattr(self, "_workflowActionBusy", False):
            panel.setManualDraftStateCheckResult(
                None,
                requested=joint_positions_si,
                error=(
                    "The façade is unavailable."
                    if not facade
                    else "Another Step 6 action is active."
                ),
            )
            return
        try:
            if not isinstance(joint_positions_si, Mapping) or set(
                joint_positions_si
            ) != set(JOINT_NAMES):
                raise ValueError("A draft state check must contain exactly J1–J5.")
            requested = {
                name: float(joint_positions_si[name]) for name in JOINT_NAMES
            }
            if not all(isfinite(value) for value in requested.values()):
                raise ValueError("Draft joint values must be finite.")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            panel.setManualDraftStateCheckResult(
                None, requested=joint_positions_si, error=str(exc)
            )
            return

        self._workflowActionBusy = True
        try:
            result = facade.checkManualRobotDraftState(requested)
            try:
                current = panel.manualJogJointPositionsSi()
                stale = not isinstance(current, Mapping) or set(current) != set(
                    JOINT_NAMES
                ) or any(
                    float(current[name]) != requested[name] for name in JOINT_NAMES
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                stale = True
            panel.setManualDraftStateCheckResult(
                result, requested=requested, stale=stale
            )
        except Exception as exc:
            panel.setManualDraftStateCheckResult(
                None, requested=requested, error=str(exc)
            )
        finally:
            self._workflowActionBusy = False

    def _onShellGuardedManualJog(
        self, joint_positions_si: Mapping[str, float]
    ) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade or getattr(self, "_workflowActionBusy", False):
            if panel:
                panel.setManualJogStatus(
                    "blocked",
                    "Guard status: unavailable — no jog was submitted; the draft is retained because another Step 6 action is active or the façade is unavailable.",
                )
            return
        if getattr(panel, "manualJogReconciliationRequired", False):
            panel.setManualJogStatus(
                "blocked",
                "Guard status: blocked — manual jog reconciliation is required. "
                "Last confirmed accepted state shown; simulated robot may have "
                "advanced; stop jogging until reconciled.",
                getattr(panel, "_manualJogEvidence", None),
            )
            return
        try:
            if set(joint_positions_si) != set(JOINT_NAMES):
                raise ValueError("A manual jog must contain exactly J1–J5.")
            requested = {
                name: float(joint_positions_si[name]) for name in JOINT_NAMES
            }
            if not all(isfinite(value) for value in requested.values()):
                raise ValueError("Manual jog values must be finite.")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            panel.setManualJogStatus(
                "blocked",
                "Guard status: invalid local request — no jog was submitted; "
                "the draft is retained. "
                + str(exc),
            )
            return
        panel.setManualJogRequestPending()
        self._workflowActionBusy = True
        try:
            result = facade.guardManualRobotJog(requested)
            details = result.details if isinstance(result.details, Mapping) else {}
            result_code = str(getattr(result, "code", "") or "")
            reconciliation_required = bool(
                details.get("manualJogReconciliationRequired") is True
                or result_code == "manual_jog_reconciliation_required"
            )
            status_details = details
            if reconciliation_required and details.get(
                "manualJogReconciliationRequired"
            ) is not True:
                status_details = dict(details)
                status_details["manualJogReconciliationRequired"] = True
            guard_accepted = details.get("guardAccepted")
            identity_status = details.get("identityStatus", "unknown")
            monitored_status = str(
                details.get("monitoredStateStatus") or "unavailable/unknown"
            )
            monitoring = f"Monitored-state status: {monitored_status}."
            accepted_positions = details.get("acceptedJointPositionsSi")
            accepted = None
            if (
                isinstance(accepted_positions, Mapping)
                and set(accepted_positions) == set(JOINT_NAMES)
            ):
                try:
                    candidate = {
                        name: float(accepted_positions[name]) for name in JOINT_NAMES
                    }
                    if all(
                        isfinite(value) and value == requested[name]
                        for name, value in candidate.items()
                    ):
                        accepted = candidate
                except (TypeError, ValueError, OverflowError):
                    pass
            acknowledged = bool(
                result.success is True
                and identity_status == "current"
                and guard_accepted is True
                and accepted is not None
            )
            if reconciliation_required:
                panel.setManualJogStatus(
                    "blocked",
                    "Guard status: blocked — reconciliation is required. Last "
                    "confirmed accepted state shown; simulated robot may have "
                    "advanced; stop jogging until reconciled. "
                    + monitoring
                    + " "
                    + result.message,
                    status_details,
                )
            elif acknowledged:
                ok, mirror_message = self._setRobotJointsFromSi(
                    accepted, publish_to_ros=False
                )
                if ok:
                    panel.setManualJogAcceptedState(accepted)
                status = (
                    "Guard status: acknowledged — the accepted state was mirrored. "
                    if ok
                    else "Guard status: acknowledged — accepted state mirroring failed: "
                    + mirror_message
                    + " "
                )
                panel.setManualJogStatus(
                    "ok",
                    status + monitoring + " " + result.message,
                    details,
                )
            elif (
                result.success is False
                and identity_status == "current"
                and guard_accepted is False
            ):
                panel.setManualJogStatus(
                    "error",
                    "Guard status: rejected — the accepted robot is unchanged and the draft is retained. "
                    + monitoring
                    + " "
                    + result.message,
                    details,
                )
            elif (
                details.get("rawGuardOutcome") == "not_submitted"
                and not reconciliation_required
            ):
                panel.setManualJogStatus(
                    "blocked",
                    "Guard status: unknown — no jog was submitted; the accepted "
                    "state was not changed by this request. The draft is retained; "
                    "retry is available.",
                    status_details,
                )
            else:
                panel.setManualJogStatus(
                    "blocked",
                    "Guard status: unknown — last confirmed accepted state "
                    "shown; simulated robot may have advanced; stop jogging "
                    "until reconciled. The draft is retained. "
                    + monitoring
                    + " "
                    + result.message,
                    status_details,
                )
        except Exception as exc:
            panel.setManualJogStatus(
                "blocked",
                "Guard status: unknown — last confirmed accepted state shown; "
                "simulated robot may have advanced; stop jogging until "
                "reconciled. The draft is retained. "
                + str(exc),
                {
                    "identityStatus": "unknown",
                    "guardAccepted": None,
                    "manualJogReconciliationRequired": True,
                    "error": str(exc),
                },
            )
        finally:
            panel.setManualJogRequestComplete()
            self._workflowActionBusy = False

    def _onShellReconcileManualRobotJog(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade or getattr(self, "_workflowActionBusy", False):
            if panel:
                panel.setManualJogStatus(
                    "blocked",
                    "Reconciliation unavailable — no query was sent; the draft is retained while another Step 6 action is active or the façade is unavailable.",
                )
            return
        if not getattr(panel, "manualJogReconciliationRequired", False):
            panel.setManualJogStatus(
                "blocked", "Reconciliation is available only after a submitted jog has unknown state."
            )
            return

        panel.setManualJogRequestPending()
        self._workflowActionBusy = True
        try:
            result = facade.reconcileManualRobotJog()
            details = result.details if isinstance(result.details, Mapping) else {}
            accepted_positions = details.get("acceptedJointPositionsSi")
            accepted = None
            if (
                isinstance(accepted_positions, Mapping)
                and set(accepted_positions) == set(JOINT_NAMES)
            ):
                try:
                    candidate = {
                        name: float(accepted_positions[name]) for name in JOINT_NAMES
                    }
                    if all(isfinite(value) for value in candidate.values()):
                        accepted = candidate
                except (TypeError, ValueError, OverflowError):
                    pass
            evidence = details.get("nativeGuardEvidence")
            correlated = bool(
                isinstance(evidence, Mapping)
                and evidence.get("responseCorrelated") is True
                and evidence.get("operation") == "state_query"
                and evidence.get("queryOnly") is True
            )
            reconciled = bool(
                result.success is True
                and getattr(result, "code", "") == "manual_jog_reconciled"
                and details.get("identityStatus") == "current"
                and details.get("monitoredStateStatus") == "matched"
                and details.get("manualJogReconciliationRequired") is False
                and accepted is not None
                and correlated
            )
            if reconciled:
                ok, mirror_message = self._setRobotJointsFromSi(
                    accepted, publish_to_ros=False
                )
                if ok:
                    panel.setManualJogAcceptedState(accepted, preserve_draft=True)
                    status = (
                        "Reconciled native accepted J1–J5 state and mirrored the simulation. "
                    )
                else:
                    status = (
                        "Native state was reconciled, but the application mirror failed: "
                        + str(mirror_message)
                        + ". "
                    )
                collision = str(details.get("collisionStatus") or "unknown")
                panel.setManualJogStatus(
                    "ok",
                    status
                    + f"Static collision validity: {collision}. "
                    + str(result.message),
                    details,
                )
            else:
                failed_details = dict(details)
                failed_details["manualJogReconciliationRequired"] = True
                panel.setManualJogStatus(
                    "blocked",
                    "Reconciliation did not complete; the accepted state remains unresolved and the draft is retained. "
                    + str(getattr(result, "message", "")),
                    failed_details,
                )
        except Exception as exc:
            panel.setManualJogStatus(
                "blocked",
                "Reconciliation failed; the accepted state remains unresolved and the draft is retained. "
                + str(exc),
                {"manualJogReconciliationRequired": True, "error": str(exc)},
            )
        finally:
            panel.setManualJogRequestComplete()
            self._workflowActionBusy = False

    def _onShellSolveIk(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.solveIk()
        self._robotSimulationPanel.showGoalResult(result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellPlanGoal(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.planToGoal()
        self._robotSimulationPanel.showGoalResult(result)
        self._step6MotionPlan = result.payload if result.success else None
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellSyncCollisionScene(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.syncPlanningScene()
        self._robotSimulationPanel.showCollisionResult(result)
        self._refreshShellRobotCapabilities()
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellCheckRobotState(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.checkStateValidity()
        self._robotSimulationPanel.showCollisionResult(result)
        if not result.success and result.code != "state_invalid":
            slicer.util.errorDisplay(result.message)

    def _setStep6PanelResult(self, label, result) -> None:
        if label is None:
            return
        label.text = result.message
        label.setProperty("dentobotState", "ok" if result.success else "error")
        label.style().unpolish(label)
        label.style().polish(label)

    def _onStep6EnableCbctRendering(self) -> None:
        if not self._parameterNode or not self.logic or not self._robotSimulationPanel:
            return
        try:
            node = self.logic.enableStep6CbctVolumeRendering(
                self._parameterNode,
                self._robotSimulationPanel.cbctPreset(),
            )
            self._robotSimulationPanel.setAppearance(
                "cbct", True, self._parameterNode.step6CbctOpacity
            )
            self._robotSimulationPanel.visualizationStatusLabel.text = _(
                "Enabled one display-only CBCT renderer (%1); source voxel geometry is unchanged."
            ).replace("%1", node.GetName())
            self._applyStep6RecommendedView()
        except (RuntimeError, ValueError) as exc:
            self._robotSimulationPanel.visualizationStatusLabel.text = str(exc)
            slicer.util.errorDisplay(str(exc))

    def _onStep6CbctPresetChanged(self) -> None:
        if not self._parameterNode or not self.logic or not self._robotSimulationPanel:
            return
        try:
            changed = self.logic.applyStep6CbctRenderingPreset(
                self._parameterNode,
                self._robotSimulationPanel.cbctPreset(),
                createIfMissing=False,
            )
            self._robotSimulationPanel.visualizationStatusLabel.text = (
                _("Updated CBCT intensity appearance; geometry was not changed.")
                if changed
                else _("Enable CBCT 3D Context before selecting an appearance preset.")
            )
        except (RuntimeError, ValueError) as exc:
            self._robotSimulationPanel.visualizationStatusLabel.text = str(exc)

    def _onStep6CreateForeheadProxy(self) -> None:
        if not self._parameterNode or not self.logic or not self._robotSimulationPanel:
            return
        progress = WorkflowProgress("Step 3B / 6.1 forehead and base")
        try:
            progress.update("Proposing virtual forehead and base", can_cancel=False)
            summary = self.logic.proposeVirtualForeheadAndBase(self._parameterNode)
            progress.update("Refreshing robot placement", can_cancel=False)
            error_mm = summary.get("tcpErrorMm")
            error_text = (
                f"{float(error_mm):.1f} mm"
                if error_mm == error_mm
                else "n/a"
            )
            slide_note = (
                "TCP slide on"
                if summary.get("tcpSlideApplied")
                else "extraoral seat, no TCP slide"
            )
            message = _(
                "Proposed virtual forehead + unreviewed base "
                "(authority=%1, FOV-push=%2, %3, unslid TCP error %4). "
                "Review in Robot + CBCT and lock. Not physical mount truth."
            ).replace("%1", str(summary.get("placementAuthority"))).replace(
                "%2", str(summary.get("pushedForFov"))
            ).replace("%3", slide_note).replace("%4", error_text)
            self._robotSimulationPanel.visualizationStatusLabel.text = message
            self._updateRobotPlacement()
            if self._isStep3BActive():
                self._applyStep3BRecommendedView()
            else:
                self._applyStep6RecommendedView()
            self._ensureOfflinePlacementSceneVisible()
        except (RuntimeError, ValueError) as exc:
            self._robotSimulationPanel.visualizationStatusLabel.text = str(exc)
            slicer.util.errorDisplay(str(exc))
        finally:
            progress.close()

    def _onStep6PlacementReview(self) -> None:
        if not self._robotSimulationPanel:
            return
        self._applyStep6RecommendedView()
        self.onFrameWorkflowView()
        self._robotSimulationPanel.visualizationStatusLabel.text = _(
            "Applied Robot + CBCT Placement Review and framed the union of visible case, robot, goal, mount, and proxy bounds."
        )

    def _onStep6AppearanceChanged(
        self,
        key: str,
        visible: bool,
        opacity: float,
    ) -> None:
        if not self._parameterNode or not self.logic:
            return
        self.logic.setStep6Appearance(
            self._parameterNode,
            key,
            visible=visible,
            opacity=opacity,
        )
        self._updateWorkflowViewControls()

    def _onStep6SaveTaskHome(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.saveTaskHome()
        self._setStep6PanelResult(self._robotSimulationPanel.homeStatusLabel, result)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6ExportManualRecord(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade:
            return
        try:
            record = facade.manualSimulationRecord()
            if (
                not isinstance(record, dict)
                or record.get("record_status") != "historical_display_only"
            ):
                raise ValueError(
                    "The façade did not provide a historical, display-only record."
                )
            serialized = json.dumps(record, indent=2, sort_keys=True, allow_nan=False)
        except (RuntimeError, TypeError, ValueError) as exc:
            message = "Manual simulation record export unavailable: " + str(exc)
            panel.setManualRecordExportStatus("blocked", message)
            slicer.util.errorDisplay(message)
            return
        destination = qt.QFileDialog.getSaveFileName(
            slicer.util.mainWindow(),
            _("Export Step 6 manual simulation record"),
            "manual-simulation-record.json",
            _("JSON files (*.json)"),
        )
        if isinstance(destination, tuple):
            destination = destination[0]
        if not destination:
            return
        try:
            Path(destination).write_text(serialized + "\n", encoding="utf-8")
        except OSError as exc:
            message = (
                "Manual simulation record export failed; the in-session record "
                "and its accepted/rejected evidence were not changed. "
                + str(exc)
            )
            panel.setManualRecordExportStatus("error", message)
            slicer.util.errorDisplay(message)
            return
        panel.setManualRecordExportStatus(
            "ok",
            "Exported historical/display-only manual simulation evidence to "
            + str(destination)
            + ". It cannot restore live state or authorize a route or preview.",
        )

    def _onStep6ShowMotionDiagnostics(self) -> None:
        if not self._parameterNode or not self._robotSimulationPanel:
            return
        payload = str(self._parameterNode.step6MotionDiagnosticJson or "").strip()
        if not payload:
            slicer.util.errorDisplay(_("No retained Step 6 motion diagnostic is available."))
            return
        try:
            session = parse_motion_diagnostic_session(payload)
            self._robotSimulationPanel.showMotionDiagnostics(
                session,
                self._robotWorkflowFacade.showDiagnosticCandidate
                if self._robotWorkflowFacade
                else None,
                self._robotWorkflowFacade.reviewMotionDiagnostic
                if self._robotWorkflowFacade
                else None,
                self._robotWorkflowFacade.showDiagnosticCandidatePaths
                if self._robotWorkflowFacade
                else None,
                self._robotWorkflowFacade.previewDiagnosticCandidate
                if self._robotWorkflowFacade
                else None,
                self._onStep6ApplyDiagnosticCandidate
                if self._robotWorkflowFacade
                else None,
                self._onStep6UnlockDiagnosticCandidate
                if self._robotWorkflowFacade
                else None,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            slicer.util.errorDisplay(str(exc))

    def _onStep6ApplyDiagnosticCandidate(
        self,
        candidate_index: int,
        lock: bool = False,
    ):
        if not self._robotWorkflowFacade:
            return None
        result = self._robotWorkflowFacade.applyDiagnosticCandidate(
            candidate_index,
            lock=lock,
        )
        self._setStep6PanelResult(
            self._robotSimulationPanel.approachStatusLabel,
            result,
        )
        self._updateWorkflowViewControls()
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)
        return result

    def _onStep6UnlockDiagnosticCandidate(self):
        if not self._robotWorkflowFacade:
            return None
        result = self._robotWorkflowFacade.unlockDiagnosticCandidate()
        if self._robotSimulationPanel:
            self._setStep6PanelResult(
                self._robotSimulationPanel.approachStatusLabel,
                result,
            )
            self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)
        return result

    def _onStep6ApplyTaskHome(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.applyTaskHome()
        self._setStep6PanelResult(self._robotSimulationPanel.homeStatusLabel, result)
        if result.success:
            self._updateRobotPlacement()
            self._updateStep6PlanningUi(result.message)
            # Placement/UI refresh derives the generic Home state and can
            # overwrite the action-specific outcome. Restore the full result
            # so the operator can see whether MoveIt planned a transition or
            # merely revalidated an already-matching monitored state.
            self._setStep6PanelResult(
                self._robotSimulationPanel.homeStatusLabel,
                result,
            )
            main_window = slicer.util.mainWindow()
            if main_window is not None:
                main_window.statusBar().showMessage(result.message, 8000)
            slicer.util.infoDisplay(
                _(
                    "Task Home is now live-validated in the active ROS/MoveIt "
                    "session.\n\n%1"
                ).replace("%1", result.message),
                windowTitle=_("Task Home applied"),
            )
        else:
            slicer.util.errorDisplay(result.message)
            self._updateStep6PlanningUi(result.message, error=True)

    def _onStep6ReviewAssistedLimits(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.reviewAssistedLimits()
        self._setStep6PanelResult(
            self._robotSimulationPanel.workspaceReviewStatusLabel, result
        )
        if result.success:
            self._updatingRobotPlacementUI = True
            try:
                self._applyTaskJointLimitsToJointSpinboxes()
            finally:
                self._updatingRobotPlacementUI = False
        else:
            slicer.util.errorDisplay(result.message)
        self._updateStep6PlanningUi(result.message, error=not result.success)

    def _onStep6UseCurrentIncisorMidpoint(self) -> bool:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return False
        result = self._robotWorkflowFacade.defaultTaskSpaceRoi()
        panel = self._robotSimulationPanel
        source_issue = (
            str(result.message or "Current incisor midpoint is unavailable.")
            if not result.success
            else ""
        )
        roi = result.payload
        if result.success:
            try:
                if not isinstance(roi, Mapping):
                    raise ValueError("ROI source did not return the required payload")
                center_raw = roi["centerWorldRasMm"]
                dimensions_raw = roi["dimensionsMm"]
                if any(
                    isinstance(values, (str, bytes, Mapping))
                    or not isinstance(values, Sequence)
                    or len(values) != 3
                    for values in (center_raw, dimensions_raw)
                ):
                    raise ValueError("ROI center and dimensions must each contain three values")
                center = tuple(float(value) for value in center_raw)
                dimensions = tuple(float(value) for value in dimensions_raw)
                if not all(isfinite(value) for value in center + dimensions):
                    raise ValueError("ROI center and dimensions must be finite")
                if not all(value > 0.0 for value in dimensions):
                    raise ValueError("ROI dimensions must be positive")
                opening_revision = roi["openingRevision"]
                if type(opening_revision) is not int or opening_revision < 0:
                    raise ValueError("ROI opening revision must be a non-negative integer")
                gap_line_node_id = roi["gapLineNodeId"]
                if not isinstance(gap_line_node_id, str) or not gap_line_node_id.strip():
                    raise ValueError("ROI source gap-line ID is missing")
                spin_values = tuple(
                    zip(panel.taskSpaceRoiCenterSpinBoxes, center)
                ) + tuple(zip(panel.taskSpaceRoiDimensionsSpinBoxes, dimensions))
                display_values = []
                rounded_decimals = []
                for spin, value in spin_values:
                    if not float(spin.minimum) <= value <= float(spin.maximum):
                        raise ValueError(
                            f"ROI value {value:g} is outside the spinbox range"
                        )
                    decimals = int(spin.decimals)
                    display_value = round(value, decimals)
                    if not float(spin.minimum) <= display_value <= float(spin.maximum):
                        raise ValueError(
                            f"ROI value {value!r} cannot be displayed within the spinbox range"
                        )
                    display_values.append((spin, display_value))
                    if display_value != value:
                        rounded_decimals.append(decimals)
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                source_issue = str(exc)
            else:
                panel._loadingTaskSpaceRoi = True
                try:
                    for spin, display_value in display_values:
                        spin.value = display_value
                        spin.enabled = True
                finally:
                    panel._loadingTaskSpaceRoi = False
                panel._taskSpaceRoiStatusContext = (
                    f"Source opening revision {opening_revision}, gap line "
                    f"{gap_line_node_id}."
                )
                panel._taskSpaceRoiOpeningRevision = opening_revision
                panel._taskSpaceRoiGapLineNodeId = gap_line_node_id
                panel._taskSpaceRoiInitialized = True
                if rounded_decimals:
                    panel._taskSpaceRoiStatusContext += (
                        " Display draft rounded to "
                        f"{max(rounded_decimals)} decimal places."
                    )
                panel.taskSpaceRoiStatusLabel.text = (
                    panel._taskSpaceRoiStatusContext
                    + " Editable local display draft; TCP samples have not been "
                    "generated or validated."
                )
                panel.taskSpaceRoiStatusLabel.setProperty("dentobotState", "blocked")
        if source_issue:
            panel._taskSpaceRoiStatusContext = (
                f"Source issue: {source_issue}. Existing ROI draft is stale/unverified."
            )
            panel.taskSpaceRoiStatusLabel.text = (
                panel._taskSpaceRoiStatusContext + " "
                "TCP samples have not been generated or validated."
            )
            panel.taskSpaceRoiStatusLabel.setProperty("dentobotState", "error")
        panel.taskSpaceRoiStatusLabel.style().unpolish(panel.taskSpaceRoiStatusLabel)
        panel.taskSpaceRoiStatusLabel.style().polish(panel.taskSpaceRoiStatusLabel)
        if not source_issue:
            self._onStep6TaskSpaceRoiEdited()
        return not source_issue

    def _onStep6TaskSpaceRoiEdited(self) -> None:
        if not self._robotWorkflowFacade or not self.logic:
            return
        self._robotWorkflowFacade.invalidateWorkspaceRuntimeValidation(
            invalidate_motion_plan=False
        )
        model = self.logic.robotWorkspaceModelNode()
        if model is None:
            return
        self.ui.robotWorkspaceStatusLabel.text = _(
            "ROI draft changed; existing workspace samples are stale."
        )
        self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #b36b00;"
        self._updateStep6PlanningUi()

    def _step6TaskSpaceRoiDraft(self):
        panel = self._robotSimulationPanel
        if panel is None:
            return None
        if not panel._taskSpaceRoiInitialized:
            if not self._onStep6UseCurrentIncisorMidpoint():
                return None
        try:
            roi = TaskSpaceRoi(
                center_world_ras_mm=tuple(
                    float(spin.value) for spin in panel.taskSpaceRoiCenterSpinBoxes
                ),
                dimensions_mm=tuple(
                    float(spin.value)
                    for spin in panel.taskSpaceRoiDimensionsSpinBoxes
                ),
            )
            opening_revision = panel._taskSpaceRoiOpeningRevision
            gap_line_node_id = panel._taskSpaceRoiGapLineNodeId
            if type(opening_revision) is not int or opening_revision < 0:
                raise ValueError("ROI source opening revision is missing")
            if not isinstance(gap_line_node_id, str) or not gap_line_node_id.strip():
                raise ValueError("ROI source gap-line identity is missing")
        except (TypeError, ValueError, OverflowError) as exc:
            panel.taskSpaceRoiStatusLabel.text = (
                f"ROI draft cannot be used: {exc}. TCP samples were not generated."
            )
            panel.taskSpaceRoiStatusLabel.setProperty("dentobotState", "error")
            panel.taskSpaceRoiStatusLabel.style().unpolish(
                panel.taskSpaceRoiStatusLabel
            )
            panel.taskSpaceRoiStatusLabel.style().polish(
                panel.taskSpaceRoiStatusLabel
            )
            return None
        return roi, {
            "openingRevision": opening_revision,
            "gapLineNodeId": gap_line_node_id,
        }

    def _onStep6RevalidateWorkspace(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.revalidateSavedWorkspace()
        self._setStep6PanelResult(
            self._robotSimulationPanel.workspaceReviewStatusLabel,
            result,
        )
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)
        self._updateRobotPlacement()
        self._setStep6PanelResult(
            self._robotSimulationPanel.workspaceReviewStatusLabel,
            result,
        )

    def _onStep6ConfirmTask(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.confirmTask()
        self._robotSimulationPanel.showConfirmationResult(result)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        # The generic planning refresh writes the current prerequisite summary.
        # Restore the action-specific confirmation outcome afterward.
        self._robotSimulationPanel.showConfirmationResult(result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6OpenExpertDiagnostics(self) -> None:
        ready, message = prepare_dentobot_motion_diagnostics()
        if not ready:
            slicer.util.errorDisplay(message)
            return
        self.onOpenViewControlsPalette()
        self._ensureStep6ExpertReturnToolbar()
        if self._applicationShell and self._applicationShell.active:
            self._applicationShell.setExpertMode(True)
        self._step6ExpertDiagnosticHandoffActive = True
        slicer.util.selectModule("ROS2MotionControl")

    def _ensureStep6ExpertReturnToolbar(self) -> None:
        mainWindow = slicer.util.mainWindow()
        if mainWindow is None:
            return
        toolbar = mainWindow.findChild("QToolBar", "DENTOBOTExpertReturnToolbar")
        if toolbar is None:
            toolbar = qt.QToolBar(_("DENTOBOT Expert Diagnostics"), mainWindow)
            toolbar.objectName = "DENTOBOTExpertReturnToolbar"
            action = toolbar.addAction(_("Return to Robot Simulation"))
            action.objectName = "DENTOBOTReturnToRobotSimulationAction"
            action.connect("triggered(bool)", self._onReturnFromStep6ExpertDiagnostics)
            mainWindow.addToolBar(qt.Qt.TopToolBarArea, toolbar)
        self._step6ExpertReturnToolbar = toolbar
        toolbar.show()
        toolbar.raise_()

    def _onReturnFromStep6ExpertDiagnostics(self, checked: bool = False) -> None:
        del checked
        self._step6ExpertDiagnosticHandoffActive = False
        if self._step6ExpertReturnToolbar:
            self._step6ExpertReturnToolbar.hide()
        slicer.util.selectModule("DENTOWorkflow")
        qt.QTimer.singleShot(0, lambda: self._setWorkflowStage(10))
        qt.QTimer.singleShot(0, self.onOpenViewControlsPalette)

    def _onStep6PlanApproach(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        if getattr(self, "_workflowActionBusy", False):
            return
        self._workflowActionBusy = True
        progress = None
        try:
            progress = WorkflowProgress("Step 6.4 guarded approach")
            progress.update("Starting planner", can_cancel=False)
            result = self._robotWorkflowFacade.planApproachPhase(
                **self._robotSimulationPanel.planningPolicy(),
                progress=lambda phase, done=None, total=None: progress.update(
                    phase, done, total, can_cancel=False
                ),
            )
        finally:
            if progress:
                progress.close()
            self._workflowActionBusy = False
        self._setStep6PanelResult(self._robotSimulationPanel.approachStatusLabel, result)
        insertion = result.details.get("toolInsertion")
        if isinstance(insertion, dict):
            self._robotSimulationPanel.toolInsertionStatusLabel.text = str(
                insertion.get("message") or ""
            )
            self._robotSimulationPanel.toolInsertionStatusLabel.setProperty(
                "dentobotRole",
                "status" if insertion.get("status") == "Pass" else "warning",
            )
        self._updateStep6PlanningUi(result.message, error=not result.success)
        # The façade creates one transient TCP path model from the accepted
        # MoveIt waypoints. Refresh the shared View catalog so it is available
        # to the operator's trajectory visibility/Frame controls immediately.
        self._updateWorkflowViewControls()
        # View refreshes may process parameter/display observers. Re-derive the
        # action gate last so a complete plan cannot leave stale grey controls.
        self._updateStep6PlanningUi(result.message, error=not result.success)
        diagnostic_fingerprint = result.details.get("motionDiagnosticSessionFingerprint")
        if not result.success and diagnostic_fingerprint and self._parameterNode:
            try:
                session = parse_motion_diagnostic_session(
                    str(self._parameterNode.step6MotionDiagnosticJson or "")
                )
            except ValueError:
                session = None
            if session and session.session_fingerprint == diagnostic_fingerprint:
                retained = retain_motion_diagnostic_error_message(session, result.message)
                self._parameterNode.step6MotionDiagnosticJson = canonical_json(
                    retained.to_dict()
                )
        if not result.success:
            slicer.util.errorDisplay(result.message)
        if (
            result.details.get("motionDiagnosticSessionFingerprint")
            and self._parameterNode
            and str(self._parameterNode.step6MotionDiagnosticJson or "").strip()
        ):
            qt.QTimer.singleShot(0, self._onStep6ShowMotionDiagnostics)

    def _onStep6CheckPreEntryIK(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        if getattr(self, "_workflowActionBusy", False):
            return
        self._workflowActionBusy = True
        progress = None
        try:
            progress = WorkflowProgress("Step 6.5 PreEntry IK diagnostic")
            progress.update("Starting endpoint diagnostic", can_cancel=False)
            result = self._robotWorkflowFacade.checkPreEntryIK(
                progress=lambda phase, done=None, total=None: progress.update(
                    phase, done, total, can_cancel=False
                ),
            )
        finally:
            if progress:
                progress.close()
            self._workflowActionBusy = False
        self._setStep6PanelResult(
            self._robotSimulationPanel.approachStatusLabel, result
        )
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if result.success and result.details.get("motionDiagnosticSessionFingerprint"):
            self._onStep6ShowMotionDiagnostics()

    def _onStep6CheckPlanningStage(self, stage: str) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        if getattr(self, "_workflowActionBusy", False):
            return
        self._workflowActionBusy = True
        progress = None
        try:
            progress = WorkflowProgress(f"Step 6.5 {stage} diagnostic")
            progress.update(f"Starting {stage} check", can_cancel=False)
            result = self._robotWorkflowFacade.checkPlanningStage(
                stage,
                progress=lambda phase, done=None, total=None: progress.update(
                    phase, done, total, can_cancel=False
                ),
            )
        finally:
            if progress:
                progress.close()
            self._workflowActionBusy = False
        self._setStep6PanelResult(
            self._robotSimulationPanel.approachStatusLabel, result
        )
        self._updateStep6PlanningUi(result.message, error=not result.success)
        fingerprint = result.details.get("motionDiagnosticSessionFingerprint")
        if fingerprint and self._parameterNode:
            try:
                session = parse_motion_diagnostic_session(
                    str(self._parameterNode.step6MotionDiagnosticJson or "")
                )
            except ValueError:
                session = None
            if session and session.session_fingerprint == fingerprint:
                self._onStep6ShowMotionDiagnostics()

    def _onStep6ComparePlanners(self) -> None:
        if getattr(self, "_plannerComparisonState", None):
            return
        if not self._robotWorkflowFacade or not self._parameterNode:
            return
        panel = self._robotSimulationPanel
        if not panel or not panel.planApproachButton.enabled:
            slicer.util.errorDisplay("Complete the current Step 6.5 prerequisites first.")
            return
        try:
            identity = self._robotWorkflowFacade.plannerComparisonIdentity()
            attempts = [
                {"planner_id": planner_id, "status": "NotRun", "message": "", "session": None, "paths": {}}
                for planner_id in PLANNER_COMPARISON_IDS
            ]
            self._plannerComparisonState = {
                "identity": identity,
                "parameter_node": self._parameterNode,
                "attempts": attempts,
                "policy": panel.planningPolicy(),
                "index": 0,
                "cancel": False,
            }
            panel.cancelPlannerComparisonButton.enabled = True
            panel.comparePlannersButton.enabled = False
            panel.planApproachButton.enabled = False
            self._savePlannerComparisonProgress()
            qt.QTimer.singleShot(0, self._runNextPlannerComparisonTrial)
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            self._plannerComparisonState = None
            panel.cancelPlannerComparisonButton.enabled = False
            self._updateStep6PlanningUi()
            slicer.util.errorDisplay(str(exc))

    def _savePlannerComparisonProgress(self) -> None:
        state = self._plannerComparisonState
        if self._parameterNode is not state["parameter_node"]:
            raise RuntimeError("The case changed; comparison evidence was not written to another case.")
        payload = str(self._parameterNode.step6PlannerComparisonJson or "").strip()
        existing = parse_planner_comparison(payload) if payload else build_planner_comparison({})
        branches = dict(existing["branches"])
        branches[state["identity"]["branch_id"]] = {
            "identity": state["identity"],
            "attempts": state["attempts"],
        }
        self._parameterNode.step6PlannerComparisonJson = canonical_json(
            build_planner_comparison(branches)
        )

    def _onStep6CancelPlannerComparison(self) -> None:
        state = getattr(self, "_plannerComparisonState", None)
        if state:
            state["cancel"] = True
            self._robotSimulationPanel.plannerComparisonProgressLabel.text = (
                "Cancellation requested; the current planner call must finish first."
            )

    def _runNextPlannerComparisonTrial(self) -> None:
        state = getattr(self, "_plannerComparisonState", None)
        if not state:
            return
        panel = self._robotSimulationPanel
        index = state["index"]
        if state["cancel"] or index >= len(PLANNER_COMPARISON_IDS):
            identity_changed = self._parameterNode is not state["parameter_node"]
            panel.plannerComparisonProgressLabel.text = (
                "Three-planner comparison cancelled; remaining rows are NotRun."
                if state["cancel"] else "Three-planner comparison complete; review all three rows."
            )
            self._robotWorkflowFacade.invalidateMotionPlan()
            self._plannerComparisonState = None
            panel.cancelPlannerComparisonButton.enabled = False
            self._updateStep6PlanningUi()
            if identity_changed:
                slicer.util.errorDisplay("Comparison stopped because the case changed; no result was written to the new case.")
            else:
                self._onStep6ShowPlannerComparison()
            return
        planner_id = PLANNER_COMPARISON_IDS[index]
        try:
            if self._robotWorkflowFacade.plannerComparisonIdentity() != state["identity"]:
                raise RuntimeError("The case/task identity changed during comparison.")
            panel.plannerComparisonProgressLabel.text = (
                f"Comparing planner {index + 1}/3: {planner_id}."
            )
            self._robotWorkflowFacade.invalidateMotionPlan()
            policy = dict(state["policy"])
            policy["planner_id"] = planner_id
            progress = WorkflowProgress(f"Step 6.4 planner {index + 1}/3: {planner_id}")
            try:
                progress.update("Starting planner", can_cancel=False)
                result = self._robotWorkflowFacade.planApproachPhase(
                    **policy,
                    progress=lambda phase, done=None, total=None: progress.update(
                        phase, done, total, can_cancel=False
                    ),
                )
            finally:
                progress.close()
            if self._robotWorkflowFacade.plannerComparisonIdentity() != state["identity"]:
                raise RuntimeError("The case/task identity changed during planner execution.")
            state["attempts"][index] = (
                self._robotWorkflowFacade.capturePlannerComparisonAttempt(planner_id, result)
            )
            self._robotWorkflowFacade.invalidateMotionPlan()
            self._savePlannerComparisonProgress()
            state["index"] += 1
            qt.QTimer.singleShot(0, self._runNextPlannerComparisonTrial)
        except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
            state["attempts"][index]["message"] = "Fatal comparison stop: " + str(exc)
            state["cancel"] = True
            self._robotWorkflowFacade.invalidateMotionPlan()
            try:
                self._savePlannerComparisonProgress()
            except (ValueError, RuntimeError, json.JSONDecodeError):
                pass
            qt.QTimer.singleShot(0, self._runNextPlannerComparisonTrial)

    def _onStep6ShowPlannerComparison(self) -> None:
        if not self._parameterNode or not self._robotSimulationPanel:
            return
        try:
            payload = str(self._parameterNode.step6PlannerComparisonJson or "").strip()
            comparison = parse_planner_comparison(payload)
            registry = json.loads(str(self._parameterNode.step6TrajectoryRegistryJson or "{}"))
            branch_id = str(registry.get("selected_branch_id") or "")
            entry = comparison["branches"].get(branch_id)
            if not entry:
                raise ValueError("No saved planner comparison belongs to this PreparedBranch.")
            try:
                current = entry["identity"] == self._robotWorkflowFacade.plannerComparisonIdentity()
            except (ValueError, RuntimeError):
                current = False
            self._plannerComparisonReplayIdentity = entry["identity"]
            self._robotSimulationPanel.showPlannerComparison(
                entry, current=current, on_replay=self._replaySavedPlannerComparisonPath
            )
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            slicer.util.errorDisplay(str(exc))

    def _clearPlannerComparisonReplay(self) -> None:
        timer = getattr(self, "_plannerComparisonReplayTimer", None)
        if timer:
            timer.stop()
            self._plannerComparisonReplayTimer = None
        for node in getattr(self, "_plannerComparisonReplayNodes", ()):
            if slicer.mrmlScene.IsNodePresent(node):
                slicer.mrmlScene.RemoveNode(node)
        self._plannerComparisonReplayNodes = []

    def _replaySavedPlannerComparisonPath(self, attempt) -> str:
        """Offline, display-only ghost animation; never touches robot/guard state."""

        self._clearPlannerComparisonReplay()
        try:
            if self._robotWorkflowFacade.plannerComparisonIdentity() != self._plannerComparisonReplayIdentity:
                return "Replay blocked: case/task identity is stale."
            base = self._parameterNode.robotBaseTransform
            if not base:
                return "Replay blocked: saved robot base is unavailable."
            waypoints = [
                point for stage in ("stage1", "stage2", "stage3")
                for point in attempt["paths"].get(stage, ())
            ]
            if not waypoints:
                return "This planner has no saved path waypoints."
            urdf_path, package_root = self.logic.robotDescriptionPaths()
            poses = robot_link_mesh_poses_mm(urdf_path, package_root, waypoints[0])
            transforms = {}
            nodes = []
            for pose in poses:
                model = slicer.modules.models.logic().AddModel(
                    str(pose.mesh_path), slicer.vtkMRMLStorageNode.CoordinateSystemRAS
                )
                transform = slicer.mrmlScene.AddNewNodeByClass(
                    "vtkMRMLLinearTransformNode", "[Diagnostic] Planner Replay Pose"
                )
                transform.SetAndObserveTransformNodeID(base.GetID())
                model.SetAndObserveTransformNodeID(transform.GetID())
                model.SetName("[Diagnostic] Planner Replay " + pose.link_name)
                model.SetAttribute("DENTOBOT.PlannerComparisonReplay", "display-only")
                model.SetSaveWithScene(False)
                transform.SetSaveWithScene(False)
                model.CreateDefaultDisplayNodes()
                model.GetDisplayNode().SetOpacity(0.35)
                model.GetDisplayNode().SetSaveWithScene(False)
                if model.GetStorageNode():
                    model.GetStorageNode().SetSaveWithScene(False)
                nodes.extend((model, transform))
                self._plannerComparisonReplayNodes = nodes
                transforms[pose.link_name] = transform
            timer = qt.QTimer()
            timer.setInterval(self._robotSimulationPanel.previewIntervalMs())
            position = 0

            def advance():
                nonlocal position
                try:
                    if (position >= len(waypoints) or
                            self._robotWorkflowFacade.plannerComparisonIdentity()
                            != self._plannerComparisonReplayIdentity):
                        self._clearPlannerComparisonReplay()
                        return
                    for pose in robot_link_mesh_poses_mm(
                        urdf_path, package_root, waypoints[position]
                    ):
                        transforms[pose.link_name].SetMatrixTransformToParent(
                            self.logic._vtkFromNumpyMatrix(pose.matrix_base_from_mesh_mm)
                        )
                    position += 1
                except (ValueError, RuntimeError, OSError, KeyError):
                    self._clearPlannerComparisonReplay()

            timer.timeout.connect(advance)
            self._plannerComparisonReplayTimer = timer
            timer.start()
            return f"Display-only replay started for {len(waypoints)} exact saved joint waypoints."
        except (ValueError, RuntimeError, OSError, KeyError) as exc:
            self._clearPlannerComparisonReplay()
            return "Replay unavailable: " + str(exc)

    def _onStep6TemplateCollisionOverride(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        enabled = bool(
            self._robotSimulationPanel.templateCollisionOverrideCheckBox.checked
        )
        result = (
            self._robotWorkflowFacade
            .setTemplateCollisionExclusionForFunctionalSimulation(enabled)
        )
        if not result.success:
            checkbox = self._robotSimulationPanel.templateCollisionOverrideCheckBox
            checkbox.blockSignals(True)
            checkbox.checked = bool(
                self._robotWorkflowFacade.templateCollisionExclusionActive
            )
            checkbox.blockSignals(False)
        self._setStep6PanelResult(
            self._robotSimulationPanel.templateCollisionOverrideStatusLabel,
            result,
        )
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _refreshStep6AnatomyReviewControls(self) -> None:
        if not self._robotSimulationPanel or not self.logic or not self._parameterNode:
            return
        self._robotSimulationPanel.setAnatomyReviewCandidates(
            self.logic.step6AnatomyReviewCandidates(self._parameterNode),
            self._robotWorkflowFacade.anatomyReviewState
            if self._robotWorkflowFacade
            else self.logic.step6AnatomyReviewState(self._parameterNode),
        )

    def _onStep6BeginAnatomyReview(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        segment_id = str(
            self._robotSimulationPanel.anatomyReviewToothCombo.currentData or ""
        )
        result = self._robotWorkflowFacade.beginSessionAnatomyReview(segment_id)
        self._setStep6PanelResult(self._robotSimulationPanel.anatomyReviewStatusLabel, result)
        self._refreshStep6AnatomyReviewControls()
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6EditAnatomyReview(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel or not self.logic:
            return
        state = self._robotWorkflowFacade.anatomyReviewState
        if not state.get("exists"):
            slicer.util.errorDisplay(_("Create a session anatomy-review copy first."))
            return
        if state.get("active"):
            slicer.util.errorDisplay(
                _("Discard the active reviewed proxy before editing a new local revision.")
            )
            return
        proxy = self.logic.step6AnatomyReviewProxyNode(self._parameterNode)
        segment_id = str(state.get("proxySegmentId") or "")
        try:
            module = getattr(slicer.modules, "segmenteditor", None)
            if not module:
                raise RuntimeError(_("The built-in Segment Editor module is unavailable."))
            module_widget = module.widgetRepresentation().self()
            if not module_widget or not module_widget.editor:
                raise RuntimeError(_("The built-in Segment Editor widget is unavailable."))
            source_volume = self.logic.getSegmentationSourceVolume(proxy)
            slicer.util.setSliceViewerLayers(background=source_volume, fit=False)
            module_widget.editor.setSegmentationNode(proxy)
            module_widget.editor.setSourceVolumeNode(source_volume)
            module_widget.editor.setCurrentSegmentID(segment_id)
            module_widget.editor.setActiveEffect(None)
            slicer.util.selectModule("SegmentEditor")
            self._robotSimulationPanel.anatomyReviewStatusLabel.text = (
                "Editing the session-only copy in Segment Editor. Remove only the "
                "reviewed local artifact; source anatomy remains unchanged."
            )
        except (RuntimeError, ValueError, TypeError, OSError) as exc:
            slicer.util.errorDisplay(str(exc))

    def _onStep6ActivateAnatomyReview(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        if not self._robotSimulationPanel.anatomyReviewConfirmedCheckBox.checked:
            message = _(
                "Confirm that the local edited region is a segmentation artifact before "
                "using a research simulation proxy."
            )
            self._robotSimulationPanel.anatomyReviewStatusLabel.text = message
            slicer.util.errorDisplay(message)
            return
        result = self._robotWorkflowFacade.activateSessionAnatomyReviewProxy(True)
        self._setStep6PanelResult(self._robotSimulationPanel.anatomyReviewStatusLabel, result)
        self._refreshStep6AnatomyReviewControls()
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6DiscardAnatomyReview(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.discardSessionAnatomyReview()
        self._setStep6PanelResult(self._robotSimulationPanel.anatomyReviewStatusLabel, result)
        self._robotSimulationPanel.anatomyReviewConfirmedCheckBox.checked = False
        self._refreshStep6AnatomyReviewControls()
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6PhasePreviewFinished(self, label, result) -> None:
        self._setStep6PanelResult(label, result)
        if self._robotSimulationPanel:
            if result.success:
                self._robotSimulationPanel.previewProgressLabel.text = (
                    "Guarded preview complete; endpoint verified."
                )
            else:
                self._robotSimulationPanel.resetPreviewProgress("Preview stopped or rejected.")
        self._updateStep6PlanningUi(result.message, error=not result.success)

    def _onStep6PreviewApproach(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        self._robotSimulationPanel.resetPreviewProgress("Starting guarded Approach preview...")
        result = self._robotWorkflowFacade.previewPhase(
            MotionPhase.APPROACH.value,
            speed_multiplier=self._robotSimulationPanel.previewSpeedMultiplier(),
            on_progress=lambda index, count: self._onStep6PreviewProgress(index, count),
            on_finished=lambda outcome: self._onStep6PhasePreviewFinished(
                self._robotSimulationPanel.approachStatusLabel, outcome
            ),
        )
        self._setStep6PanelResult(self._robotSimulationPanel.approachStatusLabel, result)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6PlanDrilling(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.planDrillingPhase()
        self._setStep6PanelResult(self._robotSimulationPanel.drillingStatusLabel, result)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6PreviewDrilling(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        self._robotSimulationPanel.resetPreviewProgress("Starting guarded Drill preview...")
        result = self._robotWorkflowFacade.previewPhase(
            MotionPhase.DRILLING.value,
            speed_multiplier=self._robotSimulationPanel.previewSpeedMultiplier(),
            on_progress=lambda index, count: self._onStep6PreviewProgress(index, count),
            on_finished=lambda outcome: self._onStep6PhasePreviewFinished(
                self._robotSimulationPanel.drillingStatusLabel, outcome
            ),
        )
        self._setStep6PanelResult(self._robotSimulationPanel.drillingStatusLabel, result)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6PreviewProgress(self, index: int, count: int) -> None:
        if self._robotSimulationPanel and self._robotWorkflowFacade:
            self._robotSimulationPanel.setPreviewProgress(
                index,
                count,
                self._robotWorkflowFacade.currentPreviewPhase,
            )

    def _onStep6StopPreview(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.stopGuardedPreview()
        self._robotSimulationPanel.resetPreviewProgress(result.message)
        self._robotSimulationPanel.approachStatusLabel.text = result.message
        self._updateStep6PlanningUi(result.message, error=not result.success)

    def _onStep6ReturnHome(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.returnToTaskHome()
        self._robotSimulationPanel.resetPreviewProgress(result.message)
        self._robotSimulationPanel.runtimeStatusLabel.text = result.message
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onApplicationShellSubstepSelected(
        self,
        workspace_id: str,
        substep_index: int,
    ) -> None:
        if workspace_id != "robot_simulation":
            return
        self._configureRobotSimulationShellSubstep(substep_index)

    def _configureRobotSimulationShellSubstep(self, substep_index: int) -> None:
        if not self._robotSimulationPanel:
            return
        index = max(0, min(int(substep_index), 6))
        self._step6SubstepIndex = index
        self._robotSimulationPanel.setActiveSubstep(index)
        self._updatingStep6SubstepNavigation = True
        try:
            if self._step6SubstepComboBox is not None:
                self._step6SubstepComboBox.currentIndex = index
            if self._step6PreviousSubstepButton is not None:
                self._step6PreviousSubstepButton.enabled = index > 0
            if self._step6NextSubstepButton is not None:
                self._step6NextSubstepButton.enabled = index < 6
        finally:
            self._updatingStep6SubstepNavigation = False
        groups = (
            self.ui.step6PlanningContextGroupBox,
            self.ui.step6MountLockGroupBox,
            self.ui.step6TaskJointLimitsGroupBox,
            self.ui.step6WorkspaceGroupBox,
            self.ui.step6TrajectoryPlanningGroupBox,
            self._robotSimulationPanel.runtimeGroup,
            self._robotSimulationPanel.confirmationGroup,
            self._robotSimulationPanel.goalGroup,
            self._robotSimulationPanel.manualJogGroup,
            self._robotSimulationPanel.collisionGroup,
            self._robotSimulationPanel.visualizationGroup,
            self._robotSimulationPanel.homeGroup,
            self._robotSimulationPanel.workspaceReviewGroup,
            self._robotSimulationPanel.approachGroup,
            self._robotSimulationPanel.drillingGroup,
        )
        for group in groups:
            group.visible = False
        visible_by_substep = {
            0: (self.ui.step6PlanningContextGroupBox,),
            1: (
                self._robotSimulationPanel.visualizationGroup,
                self.ui.step6MountLockGroupBox,
                self._robotSimulationPanel.runtimeGroup,
                self._robotSimulationPanel.collisionGroup,
            ),
            2: (
                self.ui.step6TaskJointLimitsGroupBox,
                self._robotSimulationPanel.homeGroup,
            ),
            3: (
                self.ui.step6WorkspaceGroupBox,
                self._robotSimulationPanel.workspaceReviewGroup,
            ),
            4: (self._robotSimulationPanel.confirmationGroup,),
            5: (
                self._robotSimulationPanel.manualJogGroup,
                self._robotSimulationPanel.approachGroup,
            ),
            6: (self._robotSimulationPanel.drillingGroup,),
        }
        for group in visible_by_substep[index]:
            group.visible = True
        self.ui.ros2MotionControlGroupBox.visible = False
        self.ui.robotPlacementDescriptionLabel.visible = index == 0
        if self._step61PlacementMirrorStatusLabel is not None:
            self._step61PlacementMirrorStatusLabel.visible = index == 1
        self._syncOfflinePlacementHost()
        shellActive = bool(self._applicationShell and self._applicationShell.active)
        if self._step6SubstepNavigator is not None:
            self._step6SubstepNavigator.visible = not shellActive
        if index in {4, 5, 6}:
            self._refreshShellRobotCapabilities()
        if (
            not shellActive
            and self._workflowContentScrollArea is not None
            and int(self.ui.workflowStageComboBox.currentIndex)
            == len(self._workflowStageEntries()) - 1
        ):
            qt.QTimer.singleShot(
                0,
                lambda: self._workflowContentScrollArea.ensureWidgetVisible(
                    self._step6SubstepNavigator,
                    0,
                    20,
                ),
            )

    def _restoreLegacyRobotSimulationGroups(self) -> None:
        if not self._robotSimulationPanel:
            return
        self._configureRobotSimulationShellSubstep(self._step6SubstepIndex)

    def _offlinePlacementWidgets(self) -> tuple:
        if not self._robotSimulationPanel:
            return ()
        return (
            self._robotSimulationPanel.visualizationGroup,
            self.ui.step6MountLockGroupBox,
        )

    def _reparentOfflinePlacementWidgets(self, layout, *, visible: bool) -> None:
        for widget in self._offlinePlacementWidgets():
            if widget is None:
                continue
            layout.addWidget(widget)
            widget.visible = bool(visible)
        self.ui.ros2MotionControlGroupBox.visible = False

    def _syncOfflinePlacementHost(self) -> None:
        if not self._robotSimulationPanel:
            return
        attach_to_3b = self._isStep3BActive() and self._step3BPlacementHost is not None
        show_surface = attach_to_3b or self._isStep61Active()
        if attach_to_3b:
            host_layout = self._step3BPlacementHost.layout()
            self._reparentOfflinePlacementWidgets(host_layout, visible=True)
            if self._step3BContinueButton is not None:
                host_layout.addWidget(self._step3BContinueButton)
            self._robotSimulationPanel.setPlacementSurfaceActive(True)
            self._offlinePlacementAttachedToStep3B = True
        else:
            layout = self.ui.robotPlacementVerticalLayout
            self._reparentOfflinePlacementWidgets(layout, visible=self._isStep61Active())
            self._robotSimulationPanel.setPlacementSurfaceActive(self._isStep61Active())
            self._offlinePlacementAttachedToStep3B = False
            if self._step61PlacementMirrorStatusLabel is not None:
                self._step61PlacementMirrorStatusLabel.visible = self._isStep61Active()
        if show_surface:
            self._updateOfflinePlacementMirrorStatus()
            self._ensureOfflinePlacementSceneVisible()

    def _ensureOfflinePlacementSceneVisible(self) -> None:
        """Keep loaded MRML robot and placement aids visible on Step 3B / 6.1."""
        if not self._parameterNode or not self.logic or not self._robotSimulationPanel:
            return
        if not self._isOfflinePlacementSurfaceActive():
            return
        from dentobot_workflow.offline_placement_status import (
            EXPECTED_ROBOT_LINK_COUNT,
        )

        if len(self.logic.robotModelNodes()) == EXPECTED_ROBOT_LINK_COUNT:
            robot_opacity = float(
                getattr(self._parameterNode, "step6RobotOpacity", 1.0) or 1.0
            )
            self._robotSimulationPanel.setAppearance("robot", True, robot_opacity)
            self.logic.setStep6Appearance(
                self._parameterNode,
                "robot",
                visible=True,
                opacity=robot_opacity,
            )
        plane_node = self._parameterNode.robotMountPlane
        if self.logic.isRobotMountPlaneNode(plane_node):
            plane_opacity = float(
                getattr(self._parameterNode, "step6MountPlaneOpacity", 0.35) or 0.35
            )
            self._robotSimulationPanel.setAppearance(
                "mount_plane", True, plane_opacity
            )
            self.logic.setStep6Appearance(
                self._parameterNode,
                "mount_plane",
                visible=True,
                opacity=plane_opacity,
            )
        proxy_node = self._parameterNode.robotForeheadProxyModel
        if proxy_node:
            opacity = float(
                getattr(self._parameterNode, "step6ForeheadProxyOpacity", 0.2) or 0.2
            )
            self._robotSimulationPanel.setAppearance("forehead_proxy", True, opacity)
            self.logic.setStep6Appearance(
                self._parameterNode,
                "forehead_proxy",
                visible=True,
                opacity=opacity,
            )
