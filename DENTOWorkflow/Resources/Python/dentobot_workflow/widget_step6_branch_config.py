"""Per-PreparedBranch Step 6 working configuration UI (S6-MULTI-JAW-STALE-01).

Save / restore of each branch's mouth opening, robot Base, Task Home and planning
policy through the normal Step 6 owners; public APIs remain on DENTOWorkflowWidget.
"""

from __future__ import annotations

from .runtime import *
from . import step6_working_config


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

    def onRestoreStep6WorkingConfiguration(self, checked: bool = False) -> list:
        """Re-apply the active branch's saved Step 6 configuration through the normal owners.

        Opening, Base and planning policy are applied; the saved Task Home is only
        staged as the 6.2 jog draft. Nothing moves without the operator.
        """

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
            if not diffs:
                panel.showBranchConfigStatus(_("Step 6 already matches this branch's saved configuration."))
                return steps
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
            if "base_world_mm" in diffs or not self._parameterNode.robotBaseMountLocked:
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
            if "task_home_si" in diffs and config["task_home_si"]:
                for joint, value in config["task_home_si"].items():
                    control = panel.manualJogJointControls.get(joint)
                    if control is not None:
                        control[1].setValue(
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
        self._updateStep6PlanningUi()
        panel.showBranchConfigStatus(
            _("Restored: ") + self._step6WorkingConfigurationSummary(record)
            + (
                _(" Saved Task Home is staged in 6.2 — Connect, then Review and Accept it.")
                if "home_staged" in steps
                else ""
            )
        )
        return steps

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
        if diffs and slicer.util.confirmYesNoDisplay(
            _("This PreparedBranch has a saved Step 6 working configuration:\n\n%1\n\n"
              "Restore it now? The saved Task Home is only staged; nothing moves.")
            .replace("%1", self._step6WorkingConfigurationSummary(record)),
            windowTitle=_("Restore branch Step 6 configuration"),
        ):
            self.onRestoreStep6WorkingConfiguration()
