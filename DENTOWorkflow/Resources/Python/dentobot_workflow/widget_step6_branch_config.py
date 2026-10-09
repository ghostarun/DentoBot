"""Per-PreparedBranch Step 6 working configuration UI (S6-MULTI-JAW-STALE-01).

Save / restore of each branch's mouth opening, robot Base, Task Home and planning
policy through the normal Step 6 owners; public APIs remain on DENTOWorkflowWidget.
"""

from __future__ import annotations

from .runtime import *
from . import step6_working_config
from .mouth_portal import DEFAULT_BARRIER_TUNING


def _barrierTuningSummary(config: dict) -> str:
    """Non-default mouth-barrier lip tuning only (the approved defaults stay silent)."""

    tuning = config.get("barrier_tuning") or {}
    if all(abs(tuning.get(k, v) - v) < 1e-9 for k, v in DEFAULT_BARRIER_TUNING.items()):
        return ""
    return (
        _(" Mouth barrier variant: lip margin %1 mm, lip slab %2 mm, portal enlargement %3 mm.")
        .replace("%1", f"{tuning['lip_margin_mm']:g}")
        .replace("%2", f"{tuning['lip_slab_mm']:g}")
        .replace("%3", f"{tuning['portal_enlarge_mm']:g}")
    )


class Step6BranchConfigWidgetMixin:
    def onImportStep6PlanningContext(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            if self._caseBundleRobotProfileCompatible is False:
                raise ValueError(
                    _(
                        "The installed URDF/SRDF/mesh/MoveIt resources do not "
                        "match this case package. Reconcile the robot profile "
                        "before importing the case into Step 6."
                    )
                )
            if not self._confirmStep6SceneSwitch("case"):
                return
            report = self.logic.importStep6PlanningContext(self._parameterNode)
            try:
                self._applyTaskJointLimitsToJointSpinboxes()
            except ValueError:
                pass
            self._applyStep6RecommendedView()
            self.onFrameStep6CaseScene()
            self._updateStep6PlanningUi(report.message)
        except (RuntimeError, ValueError) as exc:
            self._updateStep6PlanningUi(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))
            return
        self._offerStep6WorkingConfigurationRestore()

    def _currentStep6WorkingConfiguration(self) -> dict:
        return self.logic.captureStep6WorkingConfiguration(
            self._parameterNode,
            plannerPolicy=self._robotWorkflowFacade.jointPlanningPolicy(),
            corridorMarginSamples=self._robotWorkflowFacade.approachCorridorMarginSamples(),
        )

    @staticmethod
    def _step6WorkingConfigurationSummary(record: dict) -> str:
        config = record["config"]
        base = config["base_world_mm"]
        return (
            _("Opening %1 mm; Base origin (%2, %3, %4) mm; %5, %6 attempt(s) / %7 s; Task Home %8.")
            .replace("%1", f"{config['mouth_opening_mm']:.1f}")
            .replace("%2", f"{base[0][3]:.1f}")
            .replace("%3", f"{base[1][3]:.1f}")
            .replace("%4", f"{base[2][3]:.1f}")
            .replace("%5", config["planner_id"] or _("default planner"))
            .replace("%6", str(config["planning_attempts"]))
            .replace("%7", f"{config['planning_time_sec']:.1f}")
            .replace("%8", _("saved") if config["task_home_si"] else _("not saved"))
            + _barrierTuningSummary(config)
        )

    def _refreshStep6WorkingConfigurationStatus(self) -> None:
        panel = self._robotSimulationPanel
        if not panel or not self._parameterNode or not self.logic:
            return
        try:
            record = self.logic.step6WorkingConfiguration(self._parameterNode)
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            panel.showBranchConfigStatus(str(exc), "warning")
            return
        panel.showBranchConfigStatus(
            _("Saved for this branch: ") + self._step6WorkingConfigurationSummary(record)
            if record
            else _("No saved Step 6 configuration for this branch.")
        )

    def onSaveStep6WorkingConfiguration(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        try:
            record = self.logic.storeStep6WorkingConfiguration(
                self._parameterNode, self._currentStep6WorkingConfiguration()
            )
        except (RuntimeError, ValueError) as exc:
            self._robotSimulationPanel.showBranchConfigStatus(str(exc), "error")
            return
        self._robotSimulationPanel.showBranchConfigStatus(
            _("Saved for this branch: ") + self._step6WorkingConfigurationSummary(record)
        )

    def _step6RobotPresentForBaseLock(self) -> bool:
        """The robot presence that the Base accept and lock owners require (DENTORobotWorkflowFacade)."""

        return bool(self.logic.robotModelNodes()) or bool(
            self.logic.isRos2MotionControlActive(self._parameterNode.robotBaseTransform)
        )

    def onRestoreStep6WorkingConfiguration(self, checked: bool = False) -> list:
        """Re-apply the active branch's saved Step 6 configuration through the normal owners.

        Opening, Base and planning policy are applied; the saved Task Home is only
        staged as the 6.2 jog draft. Nothing moves without the operator. The Base is
        accepted only with the ROS robot or local fallback loaded; without one it stays
        pending (nothing unlocked or staged) and the rest of the configuration still applies.
        """

        self._step6WorkingConfigurationRestoreSucceeded = False
        del checked
        panel, facade = self._robotSimulationPanel, self._robotWorkflowFacade
        if not self._parameterNode or not self.logic or not facade or not panel:
            return []
        steps: list = []
        try:
            record = self.logic.step6WorkingConfiguration(self._parameterNode)
            if not record:
                raise ValueError(_("This branch has no saved Step 6 configuration."))
            eligibility = self.logic.evaluatePreparedBranchEligibility(self._parameterNode)
            if eligibility["reason"] != "VALID":
                raise ValueError(eligibility["message"])
            issue = step6_working_config.binding_issue(
                record,
                eligibility["branch_id"],
                (eligibility.get("branch") or {}).get("branch_foundation_fingerprint", ""),
            )
            if issue:
                raise ValueError(issue)
            config = record["config"]
            diffs = step6_working_config.differences(
                record, self._currentStep6WorkingConfiguration()
            )
            if diffs:
                if {"mouth_opening_mm", "base_world_mm"} & set(diffs) and self.logic.isRos2MotionControlActive(
                    self._parameterNode.robotBaseTransform
                ):
                    result = facade.disconnect()
                    if not result.success:
                        raise ValueError(result.message)
                    steps.append("disconnect")
                if "mouth_opening_mm" in diffs:
                    self._parameterNode.step6CaseJawTargetGapMm = float(config["mouth_opening_mm"])
                    wasUpdating = self._updatingFromParameterNode
                    self._updatingFromParameterNode = True
                    try:
                        self.logic.createOrUpdateStep6CaseJawOpening(self._parameterNode)
                    finally:
                        self._updatingFromParameterNode = wasUpdating
                    facade.clearTransientState()
                    self._updateStep6CaseJawOpeningControls()
                    steps.append(("opening", float(config["mouth_opening_mm"])))
                    if not self._parameterNode.step6PlanningContextImported:
                        self.logic.importStep6PlanningContext(self._parameterNode)
                        steps.append("import")
                baseNeeded = "base_world_mm" in diffs or not self._parameterNode.robotBaseMountLocked
                if baseNeeded and not self._step6RobotPresentForBaseLock():
                    # Accept Base locks the Base through the robot owners, which need a loaded robot, and
                    # the restore can run before one is loaded. Leave the Base pending: nothing is unlocked
                    # or staged, and the planning policy and Task Home below still apply.
                    steps.append("base_pending")
                elif baseNeeded:
                    flat = tuple(float(value) for row in config["base_world_mm"] for value in row)
                    if self._parameterNode.robotBaseMountLocked:
                        result = facade.unlockBase()
                        if not result.success:
                            raise ValueError(result.message)
                    result = facade.stageManualBaseReview(flat)
                    if not result.success:
                        facade.cancelManualBaseReview()
                        result = facade.stageManualBaseReview(flat)
                    if result.success:
                        result = facade.acceptManualBaseReview()
                    if not result.success:
                        raise ValueError(result.message)
                    steps.append("base")
                policy = facade.jointPlanningPolicy()
                plannerId = config["planner_id"] or policy["planner_id"]
                facade.setJointPlanningPolicy(
                    plannerId, config["planning_attempts"], config["planning_time_sec"]
                )
                panel.setPlanningPolicy(
                    plannerId, config["planning_attempts"], config["planning_time_sec"]
                )
                facade.setApproachCorridorMarginSamples(config["corridor_margin_samples"])
                if bool(self._parameterNode.step6AllowSpindleGuideContact) != config["allow_spindle_guide_contact"]:
                    self._onSetSpindleGuideContact(config["allow_spindle_guide_contact"])
                steps.append("policy")
                if "barrier_tuning" in diffs:
                    self.logic.setStep6MouthBarrierTuning(self._parameterNode, **config["barrier_tuning"])
                    facade.clearTransientState()
                    steps.append("barrier")
            if config["task_home_si"]:
                controls = {
                    joint: panel.manualJogJointControls.get(joint)
                    for joint in config["task_home_si"]
                }
                missingControls = [joint for joint, control in controls.items() if control is None]
                if missingControls:
                    raise ValueError(
                        _("Saved Task Home controls are unavailable for: %1")
                        .replace("%1", ", ".join(missingControls))
                    )
                for joint, value in config["task_home_si"].items():
                    controls[joint][1].setValue(
                        value * 1000.0 if "Slider" in joint else math.degrees(value)
                    )
                steps.append("home_staged")
        except (RuntimeError, ValueError) as exc:
            panel.showBranchConfigStatus(
                _("Restore stopped: ") + str(exc), "error"
            )
            self._updateStep6PlanningUi(str(exc), error=True)
            return steps
        self._updateRobotPlacement()
        basePending = "base_pending" in steps or (not diffs and not self._parameterNode.robotBaseMountLocked)
        pendingText = ""
        if basePending:
            pendingText = (
                _("Saved Base is NOT applied yet: load the ROS robot or local fallback, then press "
                  "Restore Branch Step 6 Config again.")
                if "base_world_mm" in diffs
                else _("The Base is not accepted yet: press Accept Base (it needs the ROS robot or "
                       "local fallback loaded).")
            )
        self._updateStep6PlanningUi(pendingText)
        panel.showBranchConfigStatus(
            (
                _("Partly restored: ") if "base_pending" in steps
                else _("Step 6 already matches this branch's saved configuration: ") if not diffs
                else _("Restored: ")
            ) + self._step6WorkingConfigurationSummary(record)
            + (
                _(" Saved Task Home is staged in 6.2 pending operator review and acceptance.")
                if "home_staged" in steps
                else ""
            )
            + (
                _(" The mouth barrier changed: synchronize the planning scene (6.1) before planning.")
                if "barrier" in steps
                else ""
            )
            + (" " + pendingText if basePending else ""),
            "warning" if basePending else "status",
        )
        if basePending:
            self._step6WorkingConfigurationRestoreSucceeded = False
        else:
            self._step6WorkingConfigurationRestoreSucceeded = True
        return steps

    def _restoreBranchConfigurationOnCaseLoad(self) -> bool:
        """Restore a saved branch configuration only when case load lands in Step 6."""

        self._step6WorkingConfigurationRestoreSucceeded = False
        ui = getattr(self, "ui", None)
        stageCombo = getattr(ui, "workflowStageComboBox", None)
        entries = self._workflowStageEntries() if stageCombo is not None else []
        if (
            stageCombo is None
            or not entries
            or int(stageCombo.currentIndex) != len(entries) - 1
            or getattr(self, "_caseBundleRobotProfileCompatible", None) is not True
        ):
            return False

        node = getattr(self, "_parameterNode", None)
        logic = getattr(self, "logic", None)
        facade = getattr(self, "_robotWorkflowFacade", None)
        panel = getattr(self, "_robotSimulationPanel", None)
        if not node or not logic or not facade or not panel:
            return False

        try:
            record = logic.step6WorkingConfiguration(node)
            if not record:
                return False
            eligibility = logic.evaluatePreparedBranchEligibility(node)
            if eligibility.get("reason") != "VALID":
                panel.showBranchConfigStatus(
                    _("Saved Step 6 configuration was not restored because the selected branch is not valid: %1")
                    .replace("%1", str(eligibility.get("message") or "")),
                    "warning",
                )
                return False
            if getattr(self, "_workflowActionBusy", False):
                panel.showBranchConfigStatus(
                    _("Saved Step 6 configuration was not restored because a Step 6 action is already in progress."),
                    "warning",
                )
                return False
            if not node.step6PlanningContextImported:
                report = logic.importStep6PlanningContext(node)
                try:
                    self._applyTaskJointLimitsToJointSpinboxes()
                except ValueError:
                    pass
                self._applyStep6RecommendedView()
                self.onFrameStep6CaseScene()
                self._updateStep6PlanningUi(report.message)
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            panel.showBranchConfigStatus(
                _("Case-load Step 6 restore stopped: ") + str(exc), "error"
            )
            self._updateStep6PlanningUi(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))
            return False

        try:
            self.onRestoreStep6WorkingConfiguration()
        except (RuntimeError, ValueError, TypeError, KeyError) as exc:
            panel.showBranchConfigStatus(
                _("Case-load Step 6 restore stopped: ") + str(exc), "error"
            )
            self._updateStep6PlanningUi(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))
            return False
        if not getattr(self, "_step6WorkingConfigurationRestoreSucceeded", False):
            return False
        self._onShellConnectRobot()
        return True

    def _offerStep6WorkingConfigurationRestore(self) -> None:
        """After activating a branch, offer its saved Step 6 configuration (never silent)."""

        self._refreshStep6WorkingConfigurationStatus()
        if not self._robotWorkflowFacade:
            return
        try:
            record = self.logic.step6WorkingConfiguration(self._parameterNode)
            diffs = (
                step6_working_config.differences(record, self._currentStep6WorkingConfiguration())
                if record
                else []
            )
        except (RuntimeError, ValueError, json.JSONDecodeError):
            return
        robotNote = ""
        if diffs and ("base_world_mm" in diffs or not self._parameterNode.robotBaseMountLocked) \
                and not self._step6RobotPresentForBaseLock():
            robotNote = _(" No robot is loaded yet, so the saved Base stays pending until you load it and restore again.")
        if diffs and slicer.util.confirmYesNoDisplay(
            _("This PreparedBranch has a saved Step 6 working configuration:\n\n%1\n\n"
              "Restore it now? The saved Task Home is only staged; nothing moves.")
            .replace("%1", self._step6WorkingConfigurationSummary(record) + robotNote),
            windowTitle=_("Restore branch Step 6 configuration"),
        ):
            self.onRestoreStep6WorkingConfiguration()
