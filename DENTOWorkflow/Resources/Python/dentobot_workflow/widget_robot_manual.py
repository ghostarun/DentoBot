"""Extracted Step 6 manual robot controls and record handlers."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite

from .runtime import *
from .workflow_progress import WorkflowProgress

from DENTOROS2Bridge import (
    clear_manual_simulation_record_paths,
    clear_motion_diagnostic_display,
    show_goal_robot_joint_positions,
    show_manual_simulation_record_paths,
)
from DENTOStep6State import JOINT_NAMES, parse_manual_simulation_record


class RobotManualWidgetMixin:

    def _onShellSetTcpDragEnabled(self, enabled: bool) -> bool:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if panel is None:
            return False
        was_busy = bool(getattr(self, "_workflowActionBusy", False))
        if facade is None or (was_busy and enabled):
            panel.goalStatusLabel.text = (
                "TCP drag change rejected: the façade is unavailable or another "
                "Step 6 action is active."
            )
            panel.goalStatusLabel.setProperty("dentobotState", "error")
            return False
        if not was_busy:
            self._workflowActionBusy = True
        try:
            result = facade.setTcpDragEnabled(bool(enabled))
            panel.showGoalResult(result)
            return bool(result.success)
        except Exception as exc:
            panel.goalStatusLabel.text = f"TCP drag change failed: {exc}"
            panel.goalStatusLabel.setProperty("dentobotState", "error")
            return False
        finally:
            if not was_busy:
                self._workflowActionBusy = False

    def _onShellNudgeTcpGoal(self, payload) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if panel is None:
            return
        if facade is None or getattr(self, "_workflowActionBusy", False):
            panel.goalStatusLabel.text = (
                "TCP nudge rejected: the façade is unavailable or another "
                "Step 6 action is active."
            )
            panel.goalStatusLabel.setProperty("dentobotState", "error")
            return
        self._workflowActionBusy = True
        try:
            result = facade.nudgeTcpGoal(payload)
            panel.showGoalResult(result)
        except Exception as exc:
            panel.goalStatusLabel.text = f"TCP nudge failed: {exc}"
            panel.goalStatusLabel.setProperty("dentobotState", "error")
        finally:
            self._workflowActionBusy = False

    def _onShellResetManualJogDraft(self) -> None:
        if self._robotSimulationPanel:
            self._robotSimulationPanel.resetManualJogDraft()

    def _onShellManualJogDraftChanged(
        self, joint_positions_si: Mapping[str, float]
    ) -> None:
        panel = self._robotSimulationPanel
        if not panel:
            return
        if panel._taskHomeSetupMode == "offline":
            panel.setManualJogDraftDisplayResult(
                False,
                "live robot ghost visualization is unavailable offline. "
                "Connect ROS/MoveIt in 6.1 for live display.",
            )
            return
        if panel._taskHomeSetupMode != "connected":
            panel.setManualJogDraftDisplayResult(
                False,
                "no live robot display was updated.",
            )
            return
        ok, message = show_goal_robot_joint_positions(joint_positions_si)
        panel.setManualJogDraftDisplayResult(ok, message)

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
        self._updateStep6PlanningUi()

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
            self._workflowActionBusy = False
            panel.setManualJogRequestComplete()
            # Robot-state signals can refresh Step 6 while the action is busy;
            # recompute availability once completion has cleared that guard.
            self._updateStep6PlanningUi()

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
            self._workflowActionBusy = False
            panel.setManualJogRequestComplete()
            self._updateStep6PlanningUi()

    def _onShellSolveIk(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        panel = self._robotSimulationPanel
        try:
            result = self._robotWorkflowFacade.solveIk()
        except Exception as exc:
            message = (
                "TCP Solve IK could not complete; the prior J1–J5 draft and accepted "
                "robot state are retained. "
                + str(exc)
            )
            panel.goalStatusLabel.text = message
            panel.goalStatusLabel.setProperty("dentobotState", "error")
            panel.setManualJogDraftDisplayResult(False, message)
            panel.setManualJogStatus("blocked", message)
            return
        panel.showGoalResult(result)
        payload = getattr(result, "payload", None)
        failure = ""
        if result.success is not True:
            failure = str(result.message or "Collision-aware TCP IK was not accepted.")
        elif not isinstance(payload, Mapping) or set(payload) != set(JOINT_NAMES):
            failure = (
                "Successful TCP IK response did not contain exactly J1–J5; "
                "the existing draft is retained."
            )
        else:
            try:
                payload = {name: float(payload[name]) for name in JOINT_NAMES}
            except (TypeError, ValueError, OverflowError):
                payload = None
            if payload is None or not all(isfinite(value) for value in payload.values()):
                failure = (
                    "Successful TCP IK response contained invalid J1–J5 values; "
                    "the existing draft is retained."
                )
        details = result.details if isinstance(result.details, Mapping) else {}
        evidence = {
            key: details[key]
            for key in (
                "staticValidityEvidence",
                "failureEvidence",
                "candidateJointPositionsSi",
                "collisionAwareValidated",
                "authoritativeStaticValidity",
            )
            if key in details
        }
        if failure:
            if evidence:
                failure += " Evidence: " + repr(evidence)
            message = (
                "TCP IK result was not staged; the prior J1–J5 draft and accepted "
                "robot state are retained. "
                + failure
            )
            panel.setManualJogDraftDisplayResult(False, message)
            panel.setManualJogStatus("blocked", message)
            return
        try:
            staged = panel.stageTcpIkSolution(payload)
        except Exception as exc:
            staged = False
            stage_error = str(exc)
        else:
            stage_error = str(
                getattr(panel, "_tcpIkStageFailureText", "")
                or "the solution was rejected by the draft controls"
            )
        if not staged:
            message = (
                "MoveIt IK solved, but its result was not staged. The prior J1–J5 "
                "draft is retained; no accepted robot state or route changed: "
                + stage_error
            )
            panel.setManualJogDraftDisplayResult(False, message)
            panel.setManualJogStatus("blocked", message)

    def _onShellSyncCollisionScene(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.syncPlanningScene()
        self._refreshShellRobotCapabilities()
        self._updateStep6PlanningUi()
        self._robotSimulationPanel.showCollisionResult(result)
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
            if self._isStep6ManualBaseReviewActive():
                self._ensureStep61BaseEditCandidate()
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

    def _manualBaseReviewControlState(
        self, scene_prepared, robot_present, locked, review_result, ros2_active=False
    ) -> dict[str, bool]:
        details = getattr(review_result, "details", {}) or {}
        staged = bool(details.get("staged"))
        identity_current = str(details.get("identityStatus") or "unknown") == "current"
        acceptance_unknown = (
            str(details.get("acceptanceStatus") or "") == "unknown"
            or bool(details.get("acceptanceUncertainty"))
        )
        review_success = bool(getattr(review_result, "success", False))
        return {
            "group": staged or bool(scene_prepared and robot_present),
            "begin": bool(
                scene_prepared
                and robot_present
                and not locked
                and not staged
                and identity_current
                and not acceptance_unknown
                and review_success
            ),
            "accept": bool(
                scene_prepared
                and robot_present
                and not locked
                and staged
                and identity_current
                and not acceptance_unknown
                and review_success
            ),
            "cancel": staged and not acceptance_unknown,
            "acceptance_unknown": acceptance_unknown,
            "reconcile": bool(
                scene_prepared
                and robot_present
                and ros2_active
                and staged
                and identity_current
                and bool(getattr(review_result, "success", False))
                and acceptance_unknown
            ),
        }

    def _ensureStep61BaseEditCandidate(self) -> None:
        try:
            active = self._isStep6ManualBaseReviewActive()
        except (RuntimeError, ValueError):
            return
        if (
            not active
            or not self._parameterNode
            or self._parameterNode.robotBaseMountLocked
            or not self._robotWorkflowFacade
            or getattr(self, "_workflowActionBusy", False)
        ):
            return
        review = self._robotWorkflowFacade.manualBaseReview()
        details = getattr(review, "details", {}) or {}
        if (
            review.success
            and details.get("identityStatus") == "current"
            and not details.get("staged")
            and str(details.get("acceptanceStatus") or "") != "unknown"
            and not details.get("acceptanceUncertainty")
        ):
            self._onStep6BeginManualBaseReview()

    def _onStep6BeginManualBaseReview(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade:
            return
        review = facade.manualBaseReview()
        details = getattr(review, "details", {}) or {}
        if not review.success or details.get("staged"):
            self._updateStep6PlanningUi(review.message, error=not review.success)
            if not review.success:
                slicer.util.errorDisplay(review.message)
            return
        if details.get("identityStatus") != "current":
            message = (
                "Base review identity is stale or unknown; no new candidate was staged. "
                "Cancel the retained review only if you intend to discard its evidence."
            )
            panel.manualBaseReviewStatusLabel.text = message
            self._updateStep6PlanningUi(message, error=True)
            return
        accepted_matrix = details.get("acceptedMatrixWorldRasMm")
        try:
            accepted_matrix = tuple(float(value) for value in accepted_matrix)
            matrix_valid = len(accepted_matrix) == 16 and all(
                isfinite(value) for value in accepted_matrix
            )
        except (TypeError, ValueError, OverflowError):
            accepted_matrix = ()
            matrix_valid = False
        if not matrix_valid:
            message = "Accepted Base matrix evidence is invalid; no candidate was staged."
            panel.manualBaseReviewStatusLabel.text = message
            self._updateStep6PlanningUi(message, error=True)
            return
        result = facade.stageManualBaseReview(accepted_matrix)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6CancelManualBaseReview(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade:
            return
        result = facade.cancelManualBaseReview()
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6ReconcileManualBaseAcceptance(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade or self._workflowActionBusy:
            return
        self._workflowActionBusy = True
        result = None
        error_message = ""
        try:
            result = facade.reconcileManualBaseAcceptance()
        except Exception as exc:
            error_message = str(exc)
        finally:
            self._workflowActionBusy = False

        success = bool(getattr(result, "success", False))
        message = str(getattr(result, "message", "") or error_message).strip()
        details = getattr(result, "details", None)
        if not isinstance(details, Mapping):
            details = {}
        status = (
            "Reconcile Base State succeeded: the accepted Base/native scene was "
            "reconciled; the detached candidate remains staged and unaccepted."
            if success
            else "Reconcile Base State did not confirm the accepted Base/native scene; "
            "the state remains unresolved."
        )
        if message:
            status += " " + message
        candidate = details.get("candidateMatrixWorldRasMm")
        if candidate is not None:
            status += " Staged Base draft evidence: " + str(candidate)
        failure = details.get("failureEvidence")
        if failure is not None:
            status += " Preserved Base acceptance failure evidence: " + str(failure)
        uncertainty = details.get("acceptanceUncertainty")
        if uncertainty:
            status += " Acceptance uncertainty: " + str(uncertainty)

        self._updateStep6PlanningUi(status, error=not success)
        if hasattr(panel, "manualBaseReviewStatusLabel"):
            panel.manualBaseReviewStatusLabel.text = (
                str(panel.manualBaseReviewStatusLabel.text or "") + " " + status
            ).strip()
        if not success:
            slicer.util.errorDisplay(status)

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

    def _onStep6ReviewManualTaskHome(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade or getattr(self, "_workflowActionBusy", False):
            return
        action_error = None
        self._workflowActionBusy = True
        try:
            status = facade.manualTaskHomeReview()
            details = status.details if isinstance(status.details, Mapping) else {}
            if (
                status.success is not True
                or details.get("identityStatus") != "current"
                or details.get("staged") is True
            ):
                result = status
            else:
                draft = panel.manualJogJointPositionsSi()
                if not isinstance(draft, Mapping) or set(draft) != set(JOINT_NAMES):
                    raise ValueError("A Task Home review requires exactly J1–J5.")
                requested = {name: float(draft[name]) for name in JOINT_NAMES}
                if not all(isfinite(value) for value in requested.values()):
                    raise ValueError("Task Home draft joint values must be finite.")
                result = facade.stageManualTaskHomeReview(requested)
        except Exception as exc:
            action_error = str(exc)
        finally:
            self._workflowActionBusy = False
        if action_error is not None:
            self._updateStep6PlanningUi(action_error, error=True)
            panel.taskHomeReviewStatusLabel.text = (
                "Home review: unknown; no accepted state was changed. "
                + action_error
            )
            slicer.util.errorDisplay(action_error)
            return
        self._updateStep6PlanningUi(result.message, error=not result.success)
        panel.setManualTaskHomeReviewResult(result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6CancelManualTaskHomeReview(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade or getattr(self, "_workflowActionBusy", False):
            return
        action_error = None
        self._workflowActionBusy = True
        try:
            result = facade.cancelManualTaskHomeReview()
        except Exception as exc:
            action_error = str(exc)
        finally:
            self._workflowActionBusy = False
        if action_error is not None:
            self._updateStep6PlanningUi(action_error, error=True)
            panel.taskHomeReviewStatusLabel.text = (
                "Home review: unknown; retained state was not mirrored. "
                + action_error
            )
            slicer.util.errorDisplay(action_error)
            return
        self._updateStep6PlanningUi(result.message, error=not result.success)
        panel.setManualTaskHomeReviewResult(result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6AcceptManualTaskHomeReview(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade or getattr(self, "_workflowActionBusy", False):
            return
        action_error = None
        self._workflowActionBusy = True
        try:
            result = facade.acceptManualTaskHomeReview()
        except Exception as exc:
            action_error = str(exc)
        finally:
            self._workflowActionBusy = False
        if action_error is not None:
            self._updateStep6PlanningUi(action_error, error=True)
            panel.taskHomeReviewStatusLabel.text = (
                "Home review: unknown; current accepted state was not mirrored. "
                + action_error
            )
            slicer.util.errorDisplay(action_error)
            return
        self._updateStep6PlanningUi(result.message, error=not result.success)
        details = result.details if isinstance(result.details, Mapping) else {}
        accepted = details.get("acceptedJointPositionsSi")
        if (
            result.success is True
            and details.get("setupMode") == "connected"
            and details.get("identityStatus") == "current"
            and details.get("acceptanceStatus") == "accepted"
            and isinstance(accepted, Mapping)
            and set(accepted) == set(JOINT_NAMES)
        ):
            try:
                positions = {name: float(accepted[name]) for name in JOINT_NAMES}
            except (KeyError, TypeError, ValueError, OverflowError):
                positions = {}
            if len(positions) == len(JOINT_NAMES) and all(
                isfinite(value) for value in positions.values()
            ):
                panel.setManualJogAcceptedState(positions, preserve_draft=True)
        panel.setManualTaskHomeReviewResult(result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6ReconcileManualTaskHomeAcceptance(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade or getattr(self, "_workflowActionBusy", False):
            return
        self._workflowActionBusy = True
        result = None
        error_message = ""
        try:
            result = facade.reconcileManualTaskHomeAcceptance()
        except Exception as exc:
            error_message = str(exc)
        finally:
            self._workflowActionBusy = False

        success = getattr(result, "success", False) is True
        message = str(getattr(result, "message", "") or error_message).strip()
        status = (
            "Reconcile Task Home State succeeded; the displayed result reflects "
            "façade evidence. This action issued no Home save or jog."
            if success
            else "Reconcile Task Home State remains unresolved; the displayed "
            "result reflects façade evidence. This action issued no Home save or jog."
        )
        if result is None and message:
            status += " " + message
        self._updateStep6PlanningUi(status, error=not success)
        if result is not None:
            panel.setManualTaskHomeReviewResult(result)
        panel.taskHomeReviewStatusLabel.text = (
            str(panel.taskHomeReviewStatusLabel.text or "") + " " + status
        ).strip()
        if not success:
            slicer.util.errorDisplay(status + (" " + message if result is not None and message else ""))

    def _onStep6ExportManualRecord(self) -> None:
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade:
            return
        try:
            completed = facade.manualSimulationCompletedRecords()
            if not isinstance(completed, (tuple, list)):
                raise ValueError("The façade returned an invalid completed-record collection.")
            records = []
            completed_fingerprints = set()
            for record in completed:
                if not isinstance(record, Mapping):
                    raise ValueError("The façade returned an invalid manual simulation record.")
                parse_manual_simulation_record(record)
                fingerprint = record["record_fingerprint"]
                records.append(record)
                completed_fingerprints.add(fingerprint)
            active = facade.manualSimulationRecord()
            if not isinstance(active, Mapping):
                raise ValueError("The façade returned an invalid manual simulation record.")
            parse_manual_simulation_record(active)
            if active["record_fingerprint"] not in completed_fingerprints:
                records.append(active)
            if not records:
                raise ValueError("No available manual simulation records were returned.")
            serialized = json.dumps(records, indent=2, sort_keys=True, allow_nan=False)
            report = [
                "Step 6 Manual Simulation Records",
                "Historical/display-only evidence. It cannot restore live state or authorize a route or preview.",
                "Evidence values are shown as recorded; unknown and unavailable values remain explicit.",
                f"Records exported: {len(records)}",
                "",
            ]
            for index, record in enumerate(records, 1):
                events = record["events"]
                kind_counts = {}
                for event in events:
                    kind = event["kind"]
                    kind_counts[kind] = kind_counts.get(kind, 0) + 1
                report.extend(
                    (
                        f"Record {index}: schema={record['schema_version']}; "
                        f"status={record['record_status']}; "
                        f"fingerprint={record['record_fingerprint']}",
                        "  Identity: "
                        + json.dumps(record["identity"], sort_keys=True, allow_nan=False),
                        f"  Events ({len(events)}): "
                        + (", ".join(f"{kind}={count}" for kind, count in kind_counts.items()) or "none"),
                        "  Recorded status/evidence values (verbatim; unknown/unavailable values are retained):",
                        json.dumps(events, indent=2, sort_keys=True, allow_nan=False),
                    )
                )
                report.append("")
            report_text = "\n".join(report)
        except (RuntimeError, TypeError, ValueError, OverflowError) as exc:
            message = "Manual simulation records export unavailable: " + str(exc)
            panel.setManualRecordExportStatus("blocked", message)
            slicer.util.errorDisplay(message)
            return
        destination = qt.QFileDialog.getSaveFileName(
            slicer.util.mainWindow(),
            _("Export Step 6 manual simulation records"),
            "manual-simulation-records.json",
            _("JSON files (*.json)"),
        )
        if isinstance(destination, tuple):
            destination = destination[0]
        if not destination:
            return
        destination = Path(destination)
        report_path = destination.with_suffix(".report.txt")
        try:
            destination.write_text(serialized + "\n", encoding="utf-8")
            report_path.write_text(report_text + "\n", encoding="utf-8")
        except OSError as exc:
            message = (
                "Manual simulation records export failed; the JSON or companion "
                "report may be incomplete. The in-session record and its "
                "accepted/rejected evidence were not changed. "
                + str(exc)
            )
            panel.setManualRecordExportStatus("error", message)
            slicer.util.errorDisplay(message)
            return
        panel.setManualRecordExportStatus(
            "ok",
            f"Exported {len(records)} historical/display-only manual simulation records to "
            + str(destination)
            + " with companion report "
            + str(report_path)
            + ". It cannot restore live state or authorize a route or preview.",
        )

    def _onStep6ImportManualRecord(self) -> None:
        panel = self._robotSimulationPanel
        if not panel:
            return
        source = qt.QFileDialog.getOpenFileName(
            slicer.util.mainWindow(),
            _("Open Step 6 manual simulation records"),
            "",
            _("JSON files (*.json)"),
        )
        if isinstance(source, tuple):
            source = source[0]
        if not source:
            return
        maximum_file_bytes = 16 * 1024 * 1024
        maximum_records = 100
        maximum_events = 10_000
        try:
            with open(source, "rb") as stream:
                raw = stream.read(maximum_file_bytes + 1)
            if len(raw) > maximum_file_bytes:
                raise ValueError("JSON file exceeds the 16 MiB import limit.")
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, Mapping):
                raw_records = [payload]
            elif isinstance(payload, list):
                raw_records = payload
            else:
                raise ValueError("JSON must contain one record object or an array of records.")
            if not raw_records or len(raw_records) > maximum_records:
                raise ValueError("JSON must contain between 1 and 100 manual simulation records.")
            records = []
            event_count = 0
            for index, raw_record in enumerate(raw_records, start=1):
                if not isinstance(raw_record, Mapping):
                    raise ValueError(f"Record {index} must be a JSON object.")
                record = parse_manual_simulation_record(raw_record)
                records.append(record)
                event_count += len(record["events"])
                if event_count > maximum_events:
                    raise ValueError("Imported records exceed the 10,000 event limit.")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
            message = (
                "Manual simulation records import rejected; the previous historical "
                "selection and display remain unchanged: " + str(exc)
            )
            panel.setManualRecordImportStatus("blocked", message)
            slicer.util.errorDisplay(message)
            return
        try:
            clear_manual_simulation_record_paths()
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            message = (
                "Manual simulation records were validated but not loaded because "
                "the previous historical path could not be cleared: " + str(exc)
            )
            panel.setManualRecordImportStatus("error", message)
            slicer.util.errorDisplay(message)
            return
        panel.setManualRecordImportStatus(
            "ok",
            f"Validated {len(records)} historical/display-only record(s); "
            "identity remains historical and live state was not read or changed.",
        )
        panel.setManualSimulationRecords(records)

    def _onStep6ShowManualRecord(self, record) -> None:
        panel = self._robotSimulationPanel
        if not panel:
            return
        try:
            result = show_manual_simulation_record_paths(record)
            if not isinstance(result, tuple) or len(result) != 2:
                raise ValueError("historical path renderer returned an invalid result")
            success, message = result
            if not success:
                cleanup_message = ""
                try:
                    clear_manual_simulation_record_paths()
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
                    cleanup_message = " Previous historical path cleanup failed: " + str(exc)
                panel.setManualRecordImportStatus(
                    "unavailable",
                    "Historical TCP path unavailable: " + str(message) + cleanup_message,
                )
                if cleanup_message:
                    slicer.util.errorDisplay(cleanup_message.strip())
                return
            panel.setManualRecordImportStatus(
                "ok",
                str(message)
                + " This is historical display evidence; live robot state is unchanged.",
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            try:
                clear_manual_simulation_record_paths()
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                pass
            message = "Historical path display is unavailable: " + str(exc)
            panel.setManualRecordImportStatus("error", message)
            slicer.util.errorDisplay(message)

    def _onStep6ClearManualRecord(self) -> None:
        panel = self._robotSimulationPanel
        try:
            clear_manual_simulation_record_paths()
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            if panel:
                panel.setManualRecordImportStatus(
                    "error", "Historical paths could not be cleared: " + str(exc)
                )
            slicer.util.errorDisplay("Historical paths could not be cleared: " + str(exc))
            return
        if panel:
            panel.clearManualSimulationRecords()
            panel.setManualRecordImportStatus(
                "idle", "Historical paths and imported records were cleared; live state is unchanged."
            )

    def _clearStep6MotionDiagnosticDisplay(self) -> bool:
        self._step6DiagnosticDisplayContext = None
        clear_errors = []
        try:
            self._clearStep6TargetConditioningFiducials()
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            clear_errors.append(str(exc))
        facade = getattr(self, "_robotWorkflowFacade", None)
        clear_display = getattr(facade, "clearDiagnosticDisplay", None)
        try:
            if callable(clear_display):
                result = clear_display()
                success = bool(getattr(result, "success", False))
                message = str(getattr(result, "message", ""))
            else:
                success, message = clear_motion_diagnostic_display()
                success = bool(success)
                message = str(message)
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            success, message = False, str(exc)
        if clear_errors:
            success = False
            message = "; ".join(part for part in (message, *clear_errors) if part)
        if not success:
            report = "Motion diagnostic display cleanup failed: " + (
                message or "the display owner did not confirm cleanup."
            )
            panel = getattr(self, "_robotSimulationPanel", None)
            if panel is not None and hasattr(panel, "approachStatusLabel"):
                panel.approachStatusLabel.text = report
                panel.approachStatusLabel.setProperty("dentobotRole", "warning")
            slicer.util.errorDisplay(report)
        return success

    def _clearStep6MotionDiagnosticDisplayIfContextChanged(self) -> bool:
        context = getattr(self, "_step6DiagnosticDisplayContext", None)
        if not context:
            return False
        parameter_node, generation_identity = context
        current_node = getattr(self, "_parameterNode", None)
        current_payload = str(
            getattr(current_node, "step6MotionDiagnosticJson", "") or ""
        ).strip()
        stale = current_node is not parameter_node or not current_payload
        if not stale and current_payload:
            try:
                session = parse_motion_diagnostic_session(current_payload)
                stale = bool(
                    session.state != "Current"
                    or session.stale_reason
                    or self._step6MotionDiagnosticGenerationIdentity(session)
                    != generation_identity
                )
            except (TypeError, ValueError):
                stale = True
        logic = getattr(self, "logic", None)
        checker = getattr(logic, "motionDiagnosticFreshnessIssues", None)
        if not stale and callable(checker):
            try:
                stale = bool(checker(current_node))
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                stale = True
        if stale:
            self._clearStep6MotionDiagnosticDisplay()
            panel = getattr(self, "_robotSimulationPanel", None)
            dialog = getattr(panel, "_diagnosticDialog", None)
            if dialog is not None:
                try:
                    dialog.close()
                except RuntimeError:
                    pass
            return True
        return False

    def _step6ExactMotionDiagnosticDisplayFingerprint(
        self, session, expected_fingerprint: str = ""
    ) -> str:
        """Resolve only an exact-current fingerprint for diagnostic displays."""
        supplied_fingerprint = str(expected_fingerprint or "").strip()
        if supplied_fingerprint:
            candidate_fingerprint = supplied_fingerprint
        else:
            logic = getattr(self, "logic", None)
            checker = getattr(logic, "motionDiagnosticFreshnessIssues", None)
            parameter_node = getattr(self, "_parameterNode", None)
            if not callable(checker) or parameter_node is None:
                return ""
            try:
                issues = checker(parameter_node)
                if not isinstance(issues, (list, tuple)) or issues:
                    return ""
            except (
                AttributeError,
                OSError,
                OverflowError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                return ""
            candidate_fingerprint = str(
                getattr(session, "session_fingerprint", "") or ""
            )
        session_fingerprint = str(
            getattr(session, "session_fingerprint", "") or ""
        )
        return (
            candidate_fingerprint
            if candidate_fingerprint
            and candidate_fingerprint == session_fingerprint
            and getattr(session, "state", "") == "Current"
            and not getattr(session, "stale_reason", "")
            else ""
        )

    @staticmethod
    def _step6MotionDiagnosticGenerationIdentity(session) -> tuple[str, ...]:
        """Return the immutable inputs identifying one diagnostic generation."""
        return tuple(
            str(getattr(session, name, "") or "")
            for name in (
                "schema_version",
                "generated_at_utc",
                "task_fingerprint",
                "base_fingerprint",
                "trajectory_fingerprint",
                "robot_profile_fingerprint",
                "collision_audit_fingerprint",
                "planning_parameters_fingerprint",
            )
        )
