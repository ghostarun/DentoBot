from types import SimpleNamespace

import pytest

from Testing.step6_base_home_uncertainty_probe import (
    BaseHomeUncertaintyProbeError,
    run_base_home_uncertainty_probe,
)


JOINTS = ("J1", "J2", "J3", "J4", "J5")
MATRIX = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
          0.0, 0.0, 1.0, 0.0, 10.0, 20.0, 30.0, 1.0)


class _Button:
    def __init__(self, action=None, enabled=True, text=""):
        self.action, self.enabled, self.text = action, enabled, text
        self.clicks = 0

    def click(self):
        if self.enabled:
            self.clicks += 1
            if self.action:
                self.action()


class _Bridge:
    def __init__(self):
        self.accepted = dict.fromkeys(JOINTS, 0.0)
        self.monitored = dict(self.accepted)

    def last_accepted_joint_positions_si(self):
        return dict(self.accepted)

    def monitored_joint_positions_si(self):
        return dict(self.monitored)


class _Facade:
    def __init__(
        self, *, fail_lock=False, fail_save=False, stale_after_stage=False,
        disable_home_accept=False,
        home_failure_message="headed test: Home save acknowledgement lost",
    ):
        self._bridge = _Bridge()
        self.fail_lock = fail_lock
        self.fail_save = fail_save
        self.stale_after_stage = stale_after_stage
        self.disable_home_accept = disable_home_accept
        self.home_failure_message = home_failure_message
        self.base_locked = False
        self.base_staged = False
        self.base_unknown = False
        self.base_candidate = None
        self.home_candidate = None
        self.home_unknown = False
        self.home_revision = 3
        self.home_json = "saved-home-3"
        self.home_runtime_validated = True
        self.real_lock_calls = 0
        self.real_save_calls = 0
        self.events = []
        self.motionPlan = None
        self.previewActive = False
        self.currentPreviewPhase = ""
        self.previewIndex = 0
        self.returnHomeRequired = False
        self.incompletePreviewEvidence = None
        self._planning_scene_synchronized = True
        self._planning_scene_object_count = 2
        self.dialog_text = ""

    def capabilities(self):
        return SimpleNamespace(simulation_only=True, connected=True)

    def currentRobotState(self):
        return SimpleNamespace(
            scene_kind="case", base_locked=self.base_locked, base_node_id="base-1",
            joint_positions_si=dict(self._bridge.accepted), has_motion_plan=False,
        )

    def taskHomeRuntimeValidated(self, _node):
        return self.home_runtime_validated

    def lockBase(self):
        self.real_lock_calls += 1
        self.events.append(f"lockBase_{self.real_lock_calls}")
        if self.fail_lock:
            return SimpleNamespace(success=False, code="base_lock_failed", message="Base lock rejected")
        self.base_locked = True
        self.home_runtime_validated = False
        self._planning_scene_synchronized = True
        self._planning_scene_object_count = 2
        return SimpleNamespace(success=True, code="base_locked", message="Base locked", details={})

    def manualBaseReview(self):
        staged = self.base_staged
        details = {
            "acceptedMatrixWorldRasMm": list(MATRIX),
            "candidateMatrixWorldRasMm": list(self.base_candidate) if staged else None,
            "staged": staged,
            "identityStatus": "stale" if staged and self.stale_after_stage else "current",
        }
        if self.base_unknown:
            details.update(
                acceptanceStatus="unknown",
                acceptanceUncertainty="lock acknowledgement was lost",
                failureEvidence={"message": "Base acknowledgement failure"},
            )
        return SimpleNamespace(
            success=not (staged and self.stale_after_stage), code="base_review", message="Base review", details=details,
        )

    def stage_base(self):
        self.base_staged = True
        self.base_candidate = MATRIX

    def acceptManualBaseReview(self):
        try:
            result = self.lockBase()
        except Exception as exc:
            self.base_unknown = True
            return SimpleNamespace(
                success=False, code="manual_base_acceptance_unknown",
                message=f"{exc} Base rollback: native scene uncertain",
                details={"acceptanceStatus": "unknown"},
            )
        if result.success is not True:
            self.base_unknown = True
            return SimpleNamespace(
                success=False, code="manual_base_acceptance_unknown",
                message=f"{result.message} Base rollback: native scene uncertain",
                details={"acceptanceStatus": "unknown"},
            )
        self.base_staged = False
        self.base_candidate = None
        self.base_unknown = False
        return SimpleNamespace(
            success=True, code="manual_base_review_accepted", message="Accepted",
            details={"acceptanceStatus": "accepted"},
        )

    def reconcileManualBaseAcceptance(self):
        self.base_unknown = False
        self._planning_scene_synchronized = True
        return SimpleNamespace(
            success=True, code="manual_base_acceptance_reconciled", message="Reconciled",
            details={
                "reconciliationStatus": "acknowledged", "staged": True,
                "candidateMatrixWorldRasMm": list(self.base_candidate),
                "acceptedMatrixWorldRasMm": list(MATRIX), "acknowledgedObjectIds": ["obj-a", "obj-b"],
            },
        )

    def manualTaskHomeReview(self):
        details = {
            "identityStatus": "current", "staged": self.home_candidate is not None,
            "candidateJointPositionsSi": dict(self.home_candidate) if self.home_candidate else None,
            "acceptedJointPositionsSi": dict(self._bridge.accepted),
            "acceptanceStatus": "unknown" if self.home_unknown else "review" if self.home_candidate else "accepted",
        }
        if self.home_unknown:
            failure_evidence = {
                "ownerDetails": {},
                "reconciliationFreeze": {"expectedRevision": self.home_revision},
            }
            if self.home_failure_message is not None:
                failure_evidence["message"] = self.home_failure_message
            details.update(
                acceptanceUncertainty="save acknowledgement was lost",
                failureEvidence=failure_evidence,
            )
        return SimpleNamespace(success=True, code="manual_task_home_review", message="Home review", details=details)

    def stageManualTaskHomeReview(self, positions):
        self.home_candidate = dict(positions)
        return self.manualTaskHomeReview()

    def saveTaskHome(self):
        self.real_save_calls += 1
        self.events.append(f"saveTaskHome_{self.real_save_calls}")
        if self.fail_save and self.real_save_calls == 2:
            return SimpleNamespace(success=False, code="task_home_failed", message="Task Home original save failed")
        self.home_revision += 1
        self.home_json = f"saved-home-{self.home_revision}"
        self.parameter_node.step6TaskHomeJson = self.home_json
        self.home_runtime_validated = True
        return SimpleNamespace(
            success=True, code="task_home_saved", message="Task Home saved",
            details={"runtimeValidated": True},
        )

    def acceptManualTaskHomeReview(self):
        try:
            result = self.saveTaskHome()
        except Exception as exc:
            self.home_unknown = True
            review = self.manualTaskHomeReview()
            return SimpleNamespace(
                success=False, code="manual_task_home_acceptance_unknown",
                message=f"Task Home save did not return an acknowledgement: {exc}",
                details=review.details,
            )
        if result.success is not True:
            return SimpleNamespace(success=False, code=result.code, message=result.message, details=self.manualTaskHomeReview().details)
        self.home_candidate = None
        self.home_runtime_validated = True
        return SimpleNamespace(success=True, code="manual_task_home_review_accepted", message="Accepted", details={})

    def reconcileManualTaskHomeAcceptance(self):
        self.events.append("reconcileTaskHome")
        self.home_unknown = False
        self.home_candidate = None
        return SimpleNamespace(
            success=True, code="manual_task_home_reconciled", message="Reconciled",
            details={
                "requestId": "query-1", "sessionId": "session-1", "homeRevision": self.home_revision,
                "acceptedJointPositionsSi": dict(self._bridge.accepted),
                "monitoredJointPositionsSi": dict(self._bridge.monitored),
                "nativeGuardEvidence": {
                    "operation": "state_query", "queryOnly": True,
                    "requestId": "query-1", "sessionId": "session-1",
                    "acceptedPositionsSi": dict(self._bridge.accepted),
                },
            },
        )

    def guardManualRobotJog(self, _positions):
        raise AssertionError("The uncertainty probe must not jog")


class _Logic:
    def __init__(self, facade):
        self.facade = facade
        self.saved = SimpleNamespace(revision=3)
        self.audit = SimpleNamespace(
            status="Acknowledged", audit_fingerprint="audit-1",
            runtime_acknowledgement={"status": "Acknowledged", "acknowledged_object_ids": ["obj-a", "obj-b"]},
            object_records=({"outgoing_collision_object_id": "obj-a"}, {"outgoing_collision_object_id": "obj-b"}),
        )

    def taskHomeRecord(self, _node):
        self.saved = SimpleNamespace(revision=self.facade.home_revision)
        return self.saved

    def collisionSceneAuditRecord(self, _node):
        return self.audit


class _RestoreFailureFacade(_Facade):
    def __delattr__(self, name):
        if name == "lockBase":
            raise RuntimeError("injected restoration failure")
        super().__delattr__(name)


class _Panel:
    def __init__(self, widget):
        self._activeSubstep = 0
        self.draft = dict.fromkeys(JOINTS, 0.0)
        self.beginManualBaseReviewButton = _Button(widget.stage_base)
        self.cancelManualBaseReviewButton = _Button(enabled=False)
        self.reconcileManualBaseStateButton = _Button(lambda: widget.reconcile_base(), enabled=False)
        self.resetManualJogDraftButton = _Button(lambda: setattr(self, "draft", dict(widget.facade._bridge.accepted)))
        self.reviewTaskHomeButton = _Button(widget.review_home)
        self.acceptTaskHomeButton = _Button(lambda: widget.accept_home(), enabled=False)
        self.cancelTaskHomeReviewButton = _Button(enabled=False)
        self.reconcileTaskHomeButton = _Button(lambda: widget.reconcile_home(), enabled=False)

    def manualJogJointPositionsSi(self):
        return dict(self.draft)


class _Widget:
    def __init__(self, facade):
        self.facade = facade
        self.home_accept_attempts = 0
        self._parameterNode = SimpleNamespace(step6TaskHomeJson="saved-home-3")
        self.logic = _Logic(facade)
        self.pending_dialog = ""
        self.ui = SimpleNamespace()
        self._robotSimulationPanel = None
        self._robotWorkflowFacade = facade
        facade.parameter_node = self._parameterNode
        self.ui.unlockRobotBaseMountButton = _Button(enabled=False, text="Unlock Accepted Base")
        self.ui.lockRobotBaseMountButton = _Button(self.accept_base, text="Accept Base")
        self.panel = _Panel(self)
        self._robotSimulationPanel = self.panel
        self.ui.lockRobotBaseMountButton.action = self.accept_base
        self._updateStep6PlanningUi()

    def accept_base(self):
        self.facade.events.append("base_accept_owner")
        result = self.facade.acceptManualBaseReview()
        if not result.success:
            self.pending_dialog = result.message
        self._updateStep6PlanningUi()

    def stage_base(self):
        self.facade.stage_base()
        self._updateStep6PlanningUi()

    def accept_home(self):
        self.home_accept_attempts += 1
        self.facade.events.append(f"home_accept_owner_{self.home_accept_attempts}")
        result = self.facade.acceptManualTaskHomeReview()
        if not result.success:
            self.pending_dialog = result.message or "Task Home save rejected"
        self._updateStep6PlanningUi()

    def review_home(self):
        self.facade.stageManualTaskHomeReview(self.panel.draft)
        self._updateStep6PlanningUi()

    def reconcile_base(self):
        self.facade.reconcileManualBaseAcceptance()
        self._updateStep6PlanningUi()

    def reconcile_home(self):
        self.facade.reconcileManualTaskHomeAcceptance()
        self._updateStep6PlanningUi()

    def _configureRobotSimulationShellSubstep(self, index):
        self.panel._activeSubstep = index

    def _updateStep6PlanningUi(self):
        f, p = self.facade, self.panel
        p.beginManualBaseReviewButton.enabled = not f.base_staged and not f.base_locked
        p.cancelManualBaseReviewButton.enabled = f.base_staged and not f.base_unknown
        p.reconcileManualBaseStateButton.enabled = f.base_staged and f.base_unknown
        self.ui.lockRobotBaseMountButton.enabled = f.base_staged and not f.base_unknown
        self.ui.lockRobotBaseMountButton.text = "Reconcile Base State" if f.base_unknown else "Accept Base"
        if not f.base_staged and not f.base_locked:
            p.beginManualBaseReviewButton.enabled = True
        p.resetManualJogDraftButton.enabled = p._activeSubstep == 3
        p.reviewTaskHomeButton.enabled = p._activeSubstep in (2, 3) and f.home_candidate is None
        p.acceptTaskHomeButton.enabled = p._activeSubstep in (2, 3) and f.home_candidate is not None and not f.home_unknown
        if f.disable_home_accept:
            p.acceptTaskHomeButton.enabled = False
        p.cancelTaskHomeReviewButton.enabled = f.home_candidate is not None and not f.home_unknown
        p.reconcileTaskHomeButton.enabled = f.home_candidate is not None and f.home_unknown


def _harness(**kwargs):
    facade = _Facade(**kwargs)
    widget = _Widget(facade)
    return widget, widget.panel, facade


def _run(widget, panel, facade, *, modal_calls):
    def modal_callback(button, expected_text, capture_stage):
        assert isinstance(capture_stage, str)
        assert capture_stage in ("base-unknown-modal", "home-unknown-modal")
        button.click()
        assert expected_text in widget.pending_dialog
        reference = f"screenshot://{capture_stage}"
        text = widget.pending_dialog
        widget.pending_dialog = ""
        modal_calls.append(expected_text)
        return {
            "button_clicked": True, "dialog_captured": True,
            "dialog_dismissed": True, "dialog_text": text,
            "capture_reference": reference,
        }

    return run_base_home_uncertainty_probe(
        widget, panel, facade,
        process_events=lambda _seconds: None,
        capture_callback=lambda stage: f"capture:{stage}",
        joint_names=JOINTS,
        expected_error_dialog_callback=modal_callback,
    )


def test_success_reconciles_lost_ack_through_both_gui_owners_and_restores_methods():
    widget, panel, facade = _harness()
    modal_calls = []
    result = _run(widget, panel, facade, modal_calls=modal_calls)

    assert result["status"] == "probe_complete"
    assert modal_calls == ["Base", "Task Home"]
    assert result["calls"]["lockBase"] == 2
    assert result["calls"]["reconcileManualBaseAcceptance"] == 1
    assert result["calls"]["baselineSaveTaskHome"] == 1
    assert result["calls"]["saveTaskHome"] == 1
    assert result["calls"]["reconcileManualTaskHomeAcceptance"] == 1
    assert result["calls"]["guardManualRobotJog"] == 0
    baseline = result["home"]["baseline_revalidation"]
    assert baseline["status"] == "complete"
    assert baseline["saved_revision_before"] == 3
    assert baseline["saved_revision_after"] == 4
    assert baseline["runtime_validated_before_base"] is True
    assert baseline["runtime_validated_after_base"] is False
    assert baseline["runtime_validated_after_reaccept"] is True
    assert baseline["identity_status_before"] == "current"
    assert baseline["identity_status_after"] == "current"
    assert baseline["joints_before"] == baseline["joints_after"]
    assert baseline["staged_review"]["success"] is True
    assert baseline["normal_save_result"]["details"]["runtimeValidated"] is True
    accepted_review = baseline["accepted_review"]
    assert accepted_review["success"] is True
    assert accepted_review["details"]["identityStatus"] == "current"
    assert accepted_review["details"]["staged"] is False
    assert accepted_review["details"]["acceptanceStatus"] == "accepted"
    assert set(baseline["captures"]) == {"before", "draft", "staged", "accepted"}
    assert all(baseline["captures"].values())
    assert baseline["draft_joint_positions_si"] == baseline["candidate_joint_positions_si"]
    assert baseline["draft_joint_positions_si"] == dict.fromkeys(JOINTS, 0.0)
    assert widget.home_accept_attempts == 2
    assert facade.real_save_calls == 2
    assert facade.events.index("home_accept_owner_1") < facade.events.index("saveTaskHome_1")
    assert facade.events.index("saveTaskHome_1") < facade.events.index("home_accept_owner_2")
    assert facade.events.index("home_accept_owner_2") < facade.events.index("saveTaskHome_2")
    assert facade.events.index("saveTaskHome_2") < facade.events.index("reconcileTaskHome")
    assert "lockBase" in result["restored_methods"] and "saveTaskHome" in result["restored_methods"]
    assert result["base"]["dialog_capture_stages"] == [
        {"stage": "base-unknown-modal", "reference": "screenshot://base-unknown-modal"}
    ]
    assert result["home"]["dialog_capture_stages"] == [
        {"stage": "home-unknown-modal", "reference": "screenshot://home-unknown-modal"}
    ]
    home_failure = result["home"]["unknown_review"]["details"]["failureEvidence"]
    assert home_failure["message"] == "headed test: Home save acknowledgement lost"
    assert home_failure["ownerDetails"] == {}
    assert home_failure["reconciliationFreeze"]["expectedRevision"] == 5
    assert result["home"]["saved_revision_after_lost_ack"] == 5
    assert "lockBase" not in facade.__dict__ and "saveTaskHome" not in facade.__dict__
    assert len(result["captures"]) >= 8
    home_start = result["joint_snapshots"]["before_home_review"]
    home_end = result["joint_snapshots"]["after_home_reconciliation"]
    assert home_start["accepted"] == home_end["accepted"]
    assert home_start["monitored"] == home_end["monitored"]
    assert home_start["displayed"] == home_end["displayed"]


def test_disabled_baseline_home_reaccept_stops_before_uncertain_save():
    widget, panel, facade = _harness(disable_home_accept=True)
    modal_calls = []

    with pytest.raises(BaseHomeUncertaintyProbeError) as caught:
        _run(widget, panel, facade, modal_calls=modal_calls)

    evidence = caught.value.evidence
    assert evidence["status"] == "pending_home_prerequisite"
    assert evidence["home"]["pending_prerequisite"]
    baseline = evidence["home"]["baseline_revalidation"]
    assert baseline["status"] != "complete"
    assert baseline["runtime_validated_before_base"] is True
    assert baseline["runtime_validated_after_base"] is False
    assert evidence["calls"]["baselineSaveTaskHome"] == 0
    assert evidence["calls"]["saveTaskHome"] == 0
    assert facade.real_save_calls == 0
    assert widget.home_accept_attempts == 0
    assert modal_calls == ["Base"]


@pytest.mark.parametrize(
    "failure_message",
    ["wrong top-level failure message", None],
)
def test_invalid_home_failure_message_stops_before_reconcile_and_retains_evidence(
    failure_message,
):
    widget, panel, facade = _harness(home_failure_message=failure_message)
    modal_calls = []

    with pytest.raises(BaseHomeUncertaintyProbeError) as caught:
        _run(widget, panel, facade, modal_calls=modal_calls)

    evidence = caught.value.evidence
    assert evidence["status"] == "blocked"
    assert modal_calls == ["Base", "Task Home"]
    assert evidence["home"]["unknown_review"]["details"]["acceptanceStatus"] == "unknown"
    failure = evidence["home"]["unknown_review"]["details"]["failureEvidence"]
    assert failure.get("message") == failure_message
    assert failure["ownerDetails"] == {}
    assert failure["reconciliationFreeze"]["expectedRevision"] == 5
    assert evidence["home"]["saved_revision_after_lost_ack"] == 5
    assert evidence["calls"]["baselineSaveTaskHome"] == 1
    assert evidence["calls"]["saveTaskHome"] == 1
    assert evidence["calls"]["reconcileManualTaskHomeAcceptance"] == 0
    assert facade.real_save_calls == 2
    assert facade.home_unknown is True
    assert facade.home_candidate == dict.fromkeys(JOINTS, 0.0)
    assert "reconcileTaskHome" not in facade.events


def test_original_lock_failure_is_reported_without_synthetic_ack_loss():
    widget, panel, facade = _harness(fail_lock=True)
    modal_calls = []

    with pytest.raises(BaseHomeUncertaintyProbeError) as caught:
        _run(widget, panel, facade, modal_calls=modal_calls)

    evidence = caught.value.evidence
    assert evidence["status"] == "original_failure"
    assert evidence["base"]["underlying_lock_result"]["success"] is False
    assert "acknowledgement lost" not in evidence["base"]["underlying_lock_result"]["message"]
    assert modal_calls == ["Base"]
    assert facade.real_lock_calls == 1
    assert "lockBase" not in facade.__dict__


def test_stale_staged_base_stops_before_commit_or_dialog():
    widget, panel, facade = _harness(stale_after_stage=True)
    modal_calls = []

    with pytest.raises(BaseHomeUncertaintyProbeError) as caught:
        _run(widget, panel, facade, modal_calls=modal_calls)

    assert caught.value.evidence["status"] == "blocked"
    assert facade.real_lock_calls == 0
    assert modal_calls == []
    assert "lockBase" not in facade.__dict__


def test_original_home_save_failure_is_not_mislabeled_as_lost_ack():
    widget, panel, facade = _harness(fail_save=True)
    modal_calls = []

    with pytest.raises(BaseHomeUncertaintyProbeError) as caught:
        _run(widget, panel, facade, modal_calls=modal_calls)

    assert caught.value.evidence["status"] == "original_failure"
    assert caught.value.evidence["home"]["underlying_save_result"]["success"] is False
    assert modal_calls == ["Base", "Task Home"]
    assert facade.real_save_calls == 2
    assert caught.value.evidence["calls"]["baselineSaveTaskHome"] == 1
    assert caught.value.evidence["calls"]["saveTaskHome"] == 1
    assert "saveTaskHome" not in facade.__dict__


def test_restoration_failure_is_reported_instead_of_returning_probe_complete():
    facade = _RestoreFailureFacade()
    widget = _Widget(facade)
    modal_calls = []

    with pytest.raises(BaseHomeUncertaintyProbeError) as caught:
        _run(widget, widget.panel, facade, modal_calls=modal_calls)

    assert caught.value.evidence["status"] == "restoration_failed"
    assert any("injected restoration failure" in item for item in caught.value.evidence["restoration_errors"])
    assert "lockBase" in facade.__dict__
    assert "saveTaskHome" not in facade.__dict__
