"""Consent-gated Task Home revalidation (S6-ADVISOR-GUI-01, decision D1 option O4; Tarun "do it", 2026-10-08).

Fakes only (no Slicer/ROS/MoveIt). They prove the consent, identity, ledger, restore and pause/resume rules of the
service; whether the production guards accept a real Home under a trial Base is runtime evidence these tests do
not provide. The production Home owners are faked; the service must never create authority any other way.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PYTHON))
sys.path.insert(0, str(ROOT / "Testing"))

from test_advisor_service import HOME, World, drive, fail, ok, session, svc  # noqa: E402

from dentobot_workflow import advisor_home as ah  # noqa: E402
from dentobot_workflow import feasibility_advisor as fa  # noqa: E402

BLOCKED_P1 = {"diagnose_P1": "blocked"}


class _Proxy:
    def __init__(self, inner, world):
        self._inner, self._w = inner, world

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _Facade(_Proxy):
    def taskHomeJointIdentity(self):
        w = self._w
        return {"accepted": w.accepted, "monitored": w.monitored, "displayed": w.displayed}

    def manualTaskHomeReview(self):
        return SimpleNamespace(details={"staged": self._w.home_staged})

    def stageManualTaskHomeReview(self, joints):
        w = self._w
        w._log("home_stage")
        w.stage_args.append(dict(joints))
        if w.stage_fails:
            return fail("manual_task_home_review_rejected", "setup identity unavailable")
        w.home_staged = True
        return ok("manual_task_home_review_staged")

    def cancelManualTaskHomeReview(self):
        self._w._log("home_cancel")
        self._w.home_staged = False
        return ok()

    def acceptManualTaskHomeReview(self):
        w = self._w
        w._log("home_accept")
        w.accept_calls += 1
        if w.accept_raises:
            raise RuntimeError("bridge dropped")
        if w.reject_home(w.view(), w.accept_calls):
            return fail("manual_task_home_review_rejected", "strict collision guard rejected the pose",
                        details={"failureEvidence": {"code": "task_home_collision_rejected"}})
        if w.accept_unknown:
            return fail("manual_task_home_acceptance_unknown", "may have committed")
        n = int(str(w.home.revision).rsplit("-", 1)[-1]) + 1
        w.home.revision = f"home-revision-{n}"
        w.home.validated_at_utc = f"2026-10-08T00:00:{n:02d}Z"
        w.home.base_fingerprint = f"base-fp-{n}"
        w.home_stale = False
        w.home_staged = False
        return ok("manual_task_home_review_accepted")

    def acceptManualBaseReview(self):
        result = self._inner.acceptManualBaseReview()
        self._w.home_stale = True  # a production Base accept always stales the Base-bound Home (new Base revision)
        return result


class HomeWorld(World):
    def __init__(self, *, reject_home=None, **kwargs):
        kwargs.setdefault("stale_home_on_opening", True)
        super().__init__(**kwargs)
        self.reject_home = reject_home or (lambda view, call: False)
        self.accepted, self.monitored, self.displayed = dict(HOME), dict(HOME), dict(HOME)
        self.home_staged = False
        self.stage_fails = self.accept_raises = self.accept_unknown = False
        self.stage_args, self.accept_calls = [], 0
        self.facade = _Facade(self.facade, self)


def u5_passes(view):
    return {} if view["u"] == 5.0 else BLOCKED_P1


def consent_session(world, tmp_path, **kwargs):
    s = session(world, tmp_path, **kwargs)
    s.grant_home_revalidation_consent(ah.CONSENT_TEXT)
    return s


def ledger(s):
    return s.home_ledger


# --- consent is explicit, exact and default-off ---------------------------------------------------
def test_without_consent_no_home_owner_is_ever_called_and_the_search_stops_at_the_stale_home(tmp_path):
    world = HomeWorld(oracle=u5_passes)
    s = session(world, tmp_path)
    s.prepare()
    drive(s)
    assert s.home_consent is None and s.home_ledger == []
    assert s.outcome == svc.BLOCKED and any(r.get("operator_review_required") for r in s.records)
    assert not {"home_stage", "home_accept", "home_cancel"}.intersection(world.calls)


def test_consent_needs_the_exact_shown_text_and_is_only_possible_before_prepare(tmp_path):
    world = HomeWorld()
    s = session(world, tmp_path)
    with pytest.raises(ValueError):
        s.grant_home_revalidation_consent("yes")
    s.prepare()
    with pytest.raises(PermissionError):
        s.grant_home_revalidation_consent(ah.CONSENT_TEXT)
    assert s.home_consent is None
    other = consent_session(HomeWorld(), tmp_path / "other")
    gates = json.loads((tmp_path / "other" / "run" / "review-gates.json").read_text())
    assert gates[0]["stage"] == ah.CONSENT_GATE and gates[0]["answer"] == "approved"
    assert gates[0]["text_sha256_16"] == ah.consent_digest() and other.home_consent["text_sha256_16"] == ah.consent_digest()
    assert "SIMULATION ONLY" in ah.CONSENT_TEXT and "no joint is moved" in ah.CONSENT_TEXT


# --- the happy path through the production owners, with attributed revisions -------------------------
def test_a_consented_base_trial_revalidates_the_unchanged_saved_joints_and_restores_with_a_fresh_validation(tmp_path):
    world = HomeWorld(oracle=u5_passes)
    s = consent_session(world, tmp_path)
    s.prepare()
    drive(s)
    assert s.outcome == svc.FOUND and s.restore_issues == []
    assert world.view()["u"] == 0.0  # Base restored through the normal owners
    assert [e["kind"] for e in ledger(s)] == ["trial", "restore"] and all(e["outcome"] == "validated" for e in ledger(s))
    assert world.stage_args == [HOME, HOME]  # exactly the saved joints, never different ones
    trial, restore = ledger(s)
    assert (trial["before"]["revision"], trial["after"]["revision"]) == ("home-revision-1", "home-revision-2")
    assert (restore["before"]["revision"], restore["after"]["revision"]) == ("home-revision-2", "home-revision-3")
    assert trial["after"]["validated_at_utc"] != restore["after"]["validated_at_utc"]
    candidate = next(r for r in s.records if r["stage"] == "base_lateral")
    assert candidate["result"] == fa.PASSED and [e["sequence"] for e in candidate["home_revalidation"]] == [1]
    saved = json.loads((tmp_path / "run" / "home-revalidations.json").read_text())
    assert [e["outcome"] for e in saved] == ["validated", "validated"]
    assert "re-validated 2 time(s)" in s.message and "original joint values re-validated: yes" in s.message
    assert "store" not in world.calls and "connect" not in world.calls
    assert not {"jog", "manual_robot_draft"}.intersection(world.calls)


def test_apply_and_save_after_a_consented_search_needs_the_acknowledgements_and_carries_the_ledger(tmp_path):
    world = HomeWorld(oracle=u5_passes)
    s = consent_session(world, tmp_path)
    s.prepare()
    drive(s)
    config = svc.working_configuration_record(s.best_candidate(), s.saved_home, s.original, s.home_ledger)
    assert [e["outcome"] for e in config["diagnostics"]["home_revalidations"]] == ["validated", "validated"]
    s.apply_and_save(acknowledged=())
    assert world.calls.count("store") == 1


# --- identity before any trial ------------------------------------------------------------------------
@pytest.mark.parametrize("source", ["accepted", "monitored", "displayed"])
def test_any_joint_vector_that_differs_from_the_saved_home_blocks_before_any_trial(tmp_path, source):
    world = HomeWorld(oracle=u5_passes)
    getattr(world, source)["j2"] += 1e-6
    s = consent_session(world, tmp_path)
    issues = s.prepare()
    assert s.finished and s.outcome == svc.BLOCKED
    assert any(i.severity == "blocking" and f"{source} J1–J5 differ" in i.message for i in issues)
    assert not {"home_stage", "home_accept", "home_cancel"}.intersection(world.calls) and world.view()["u"] == 0.0


def test_an_unavailable_joint_source_blocks_and_an_invalid_current_home_is_never_repaired_at_start(tmp_path):
    world = HomeWorld()
    world.monitored = None
    s = consent_session(world, tmp_path)
    s.prepare()
    assert s.outcome == svc.BLOCKED and "monitored J1–J5 are unavailable" in s.message
    stale = HomeWorld(oracle=u5_passes)
    stale.home_stale = True
    s2 = consent_session(stale, tmp_path / "stale")
    issues = s2.prepare()
    assert s2.outcome == svc.BLOCKED and any("Task Home needs explicit 6.2 review" in i.message for i in issues)
    assert not {"home_stage", "home_accept"}.intersection(stale.calls)  # consent does not authorise fixing a bad start


def test_a_review_already_staged_by_the_operator_is_never_overwritten(tmp_path):
    world = HomeWorld()
    world.home_staged = True
    s = consent_session(world, tmp_path)
    issues = s.prepare()
    assert s.outcome == svc.BLOCKED and any("already staged" in i.message for i in issues)
    assert not {"home_stage", "home_accept"}.intersection(world.calls)


def test_joint_drift_between_trials_stops_for_operator_review_and_nothing_is_substituted(tmp_path):
    world = HomeWorld(oracle=u5_passes)
    s = consent_session(world, tmp_path)
    s.prepare()

    def drift_after_baseline(sess, event):
        if len(sess.records) == 1:
            world.monitored["j3"] += 1e-6  # someone moved the robot behind the advisor's back

    drive(s, on_step=drift_after_baseline)
    assert s.outcome == svc.BLOCKED
    blocked = next(r for r in s.records if r.get("operator_review_required"))
    assert "joint identity" in blocked["reason"] and "monitored" in blocked["reason"]
    assert "home_stage" not in world.calls and "home_accept" not in world.calls and ledger(s) == []
    assert s.restore_issues and any("joint identity" in i for i in s.restore_issues)  # restore proves the joints too


def test_joint_drift_before_the_baseline_ends_stops_the_baseline_and_blocks_apply_and_save(tmp_path):
    """W1 F2: the baseline and any trial that needs no revalidation are checked too, not only revalidating steps."""

    world = HomeWorld()
    s = consent_session(world, tmp_path)
    s.prepare()

    def drift_during_baseline(sess, event):
        if event.step == "preentry":
            world.monitored["j3"] += 1e-6

    drive(s, on_step=drift_during_baseline)
    assert s.outcome == svc.BLOCKED and s.records[0]["result"] != fa.PASSED
    assert any("joint identity" in r["reason"] for r in s.records)
    with pytest.raises(PermissionError):
        s.apply_and_save(acknowledged=())
    assert "store" not in world.calls and "home_stage" not in world.calls


# --- per-trial production collision validation ------------------------------------------------------------------
def test_a_production_guard_rejection_fails_only_that_candidate_without_forging_authority(tmp_path):
    world = HomeWorld(oracle=lambda v: {} if v["u"] == 10.0 else BLOCKED_P1,
                      reject_home=lambda view, call: view["u"] in (5.0, -5.0))
    s = consent_session(world, tmp_path)
    s.prepare()
    drive(s)
    rejected = [r for r in s.records if r.get("home_rejected")]
    assert [r["change"].get(fa.BASE_U_MM) for r in rejected] == [5.0, -5.0]
    assert all(r["result"] == fa.SETUP_ERROR and r["failed_step"] == "prerequisites"
               and "production guard" in r["reason"] and set(r["steps"]) == {"prerequisites"} for r in rejected)
    assert world.calls.count("home_cancel") == 2  # the detached staged review is cleared through its owner
    assert s.outcome == svc.FOUND and next(r for r in s.records if r["result"] == fa.PASSED)["change"] == {fa.BASE_U_MM: 10.0}
    outcomes = [(e["kind"], e["outcome"]) for e in ledger(s)]
    assert outcomes == [("trial", "rejected"), ("trial", "rejected"), ("trial", "validated"), ("restore", "validated")]
    assert world.calls.count("preentry") == 4  # baseline + the passing candidate (step and Diagnose row); none on a rejected Home
    assert s.restore_issues == []


def test_repeated_rejections_stop_the_search_for_review_instead_of_trying_everything(tmp_path):
    world = HomeWorld(oracle=lambda v: BLOCKED_P1, reject_home=lambda view, call: view["u"] != 0.0 or view["v"] != 0.0)
    s = consent_session(world, tmp_path)
    s.prepare()
    drive(s)
    assert s.outcome == svc.BLOCKED
    assert [e["outcome"] for e in ledger(s)].count("rejected") == ah.MAX_CONSECUTIVE_REJECTIONS
    assert "rejected 5 times in a row" in s.message


def test_an_unknown_acceptance_outcome_or_an_exception_stops_and_is_never_retried(tmp_path):
    for flag in ("accept_unknown", "accept_raises"):
        world = HomeWorld(oracle=u5_passes)
        setattr(world, flag, True)
        s = consent_session(world, tmp_path / flag)
        s.prepare()
        drive(s)
        assert s.outcome == svc.BLOCKED
        assert world.accept_calls == 1  # one attempt only: the unknown outcome is never retried, not even by restore
        assert [e["outcome"] for e in ledger(s)] == ["refused", "refused"]
        assert "unknown" in ledger(s)[0]["message"] or "raised" in ledger(s)[0]["message"]
        assert s.restore_issues and "previous Task Home acceptance outcome is unknown" in " ".join(s.restore_issues)
        with pytest.raises(PermissionError):
            s.apply_and_save(acknowledged=())


def test_a_post_accept_validation_read_error_blocks_restore_without_retrying_the_committed_accept(tmp_path):
    world = HomeWorld(oracle=u5_passes)
    s = consent_session(world, tmp_path)
    s.prepare()
    original_gap = world.facade._inner.taskHomeValidationGap

    def fail_after_commit(node):
        if world.accept_calls:
            raise RuntimeError("post-accept validation read failed")
        return original_gap(node)

    world.facade.taskHomeValidationGap = fail_after_commit
    drive(s)

    assert s.outcome == svc.BLOCKED
    assert world.accept_calls == 1 and world.calls.count("home_stage") == 1
    assert [(entry["kind"], entry["outcome"]) for entry in ledger(s)] == [
        ("trial", "refused"), ("restore", "refused")]
    assert "unknown" in ledger(s)[0]["message"].lower()
    assert s.restore_issues and "unknown" in " ".join(s.restore_issues).lower()
    with pytest.raises(PermissionError):
        s.apply_and_save(acknowledged=())


# --- restore: report and block, never PASS -----------------------------------------------------------------------
def test_a_rejected_restore_revalidation_is_reported_and_blocks_apply_and_save(tmp_path):
    world = HomeWorld(oracle=u5_passes, reject_home=lambda view, call: call == 2)  # the trial passes, the restore is refused
    s = consent_session(world, tmp_path)
    s.prepare()
    drive(s)
    assert s.restore_issues and "rejected" in " ".join(s.restore_issues)
    assert "could NOT be fully restored" in s.message and "original joint values re-validated: NO" in s.message
    with pytest.raises(PermissionError):
        s.apply_and_save(acknowledged=())


def test_cancel_after_a_consented_trial_restores_the_base_and_revalidates_the_original_joints(tmp_path):
    world = HomeWorld(oracle=lambda v: BLOCKED_P1)
    s = consent_session(world, tmp_path)
    s.prepare()

    def cancel_after_first_revalidation(sess, event):
        if event.step == "apply_confirm" and world.accept_calls == 1:
            sess.cancel()

    drive(s, on_step=cancel_after_first_revalidation)
    assert s.outcome == svc.CANCELLED and s.restore_issues == [] and world.view()["u"] == 0.0
    assert [(e["kind"], e["outcome"]) for e in ledger(s)] == [("trial", "validated"), ("restore", "validated")]
    assert world.stage_args == [HOME, HOME]


def test_a_change_to_the_saved_home_outside_the_advisor_is_detected_by_the_attributed_identity(tmp_path):
    world = HomeWorld(oracle=lambda v: BLOCKED_P1)
    s = consent_session(world, tmp_path)
    s.prepare()

    def foreign_revision(sess, event):
        if event.step == "apply_confirm" and world.accept_calls == 1:
            world.home.revision = "home-revision-99"  # not one of the advisor's own revalidations

    drive(s, on_step=foreign_revision)
    assert s.outcome == svc.BLOCKED
    assert any(r.get("operator_review_required") and "changed outside the advisor" in r["reason"] for r in s.records)
    assert world.accept_calls == 1 and world.calls.count("home_stage") == 1
    assert ledger(s)[-1]["kind"] == "restore" and ledger(s)[-1]["outcome"] == "refused"
    assert s.restore_issues and any("changed outside the advisor" in issue for issue in s.restore_issues)
    assert "foreign" not in json.dumps(ledger(s))


# --- opening: Connect is the operator's; Continue never rebases -----------------------------------------------------
def _run_to_pause(world, tmp_path):
    s = consent_session(world, tmp_path)
    s.prepare()
    events = []
    for _ in range(100000):
        event = s.step()
        events.append(event)
        if event.kind == "gate":
            (s.approve_stage if event.stage == "opening" else s.decline_stage)(event.stage)
        if event.kind == "pause":
            return s, events
        if s.finished:
            break
    raise AssertionError("no pause was reached")


def opening_world():
    return HomeWorld(oracle=lambda v: {} if v["opening"] == 40.5 else BLOCKED_P1, disconnect_drops_connection=True)


def test_an_opening_trial_pauses_for_the_operators_connect_and_does_no_work_while_paused(tmp_path):
    world = opening_world()
    s, events = _run_to_pause(world, tmp_path)
    assert s.phase == svc.PAUSED and events[-1].kind == "pause" and "Use Connect (6.1)" in events[-1].message
    assert "connect" not in world.calls and not world.connected  # the advisor never connects
    calls = list(world.calls)
    assert s.step().kind == "pause" and s.step().kind == "pause" and world.calls == calls
    assert (tmp_path / "run" / "pause.json").exists()


def test_continue_refuses_while_disconnected_on_joint_drift_and_on_identity_drift_and_changes_nothing(tmp_path):
    world = opening_world()
    s, _ = _run_to_pause(world, tmp_path)
    calls = list(world.calls)
    assert any("still disconnected" in i for i in s.resume_issues())
    assert s.resume().kind == "pause" and s.phase == svc.PAUSED
    world.connected = True
    world.accepted["j1"] += 1e-6  # Connect re-seeded the accepted pose
    event = s.resume()
    assert event.kind == "pause" and "joint identity: accepted J1–J5 differ" in event.message and s.phase == svc.PAUSED
    world.accepted["j1"] = HOME["j1"]
    world.branch_revision = "branch-revision-2"
    event = s.resume()
    assert event.kind == "pause" and "frozen identity changed" in event.message and "branch_revision" in event.message
    assert world.calls == calls  # no Home call, no re-plan, nothing substituted or rebased
    pause = json.loads((tmp_path / "run" / "pause.json").read_text())
    assert "Continue refused" in pause["last_refusal"] and "resumed_utc" not in pause


def _finish_with_operator(s, world, *, connect_unchanged=True, max_pauses=4):
    """Drive like the dialog: on every pause the operator connects (their own action) and presses Continue."""

    pauses = 0
    for _ in range(100000):
        event = s.step()
        if event.kind == "gate":
            (s.approve_stage if event.stage == "opening" else s.decline_stage)(event.stage)
        if event.kind == "pause":
            pauses += 1
            assert pauses <= max_pauses, "the search paused too often"
            world.connected = True  # the operator's own Connect through the production owner
            if not connect_unchanged:
                world.accepted["j1"] += 1e-6
            resumed = s.resume()
            if resumed.kind == "pause":
                return pauses
        if s.finished:
            return pauses
    raise AssertionError("session did not finish")


def test_continue_after_an_unchanged_connect_resumes_the_same_candidate_and_revalidates_through_the_owners(tmp_path):
    world = opening_world()
    s, _ = _run_to_pause(world, tmp_path)
    world.connected = True
    event = s.resume()
    assert event.kind == "step" and s.phase == svc.EVALUATING and s.resume_issues() == ["the search is not paused for an operator action"]
    pauses = _finish_with_operator(s, world)
    candidate = next(r for r in s.records if r["stage"] == "opening")
    assert candidate["result"] == fa.PASSED and candidate["change"] == {fa.MOUTH_OPENING_MM: 40.5}
    assert ledger(s)[0]["kind"] == "trial" and ledger(s)[0]["outcome"] == "validated"
    assert "resumed_utc" in json.loads((tmp_path / "run" / "pause.json").read_text())
    # restoring the opening disconnects again: the advisor pauses for the operator's Connect, never connects itself
    assert pauses == 1 and "connect" not in world.calls
    assert s.outcome == svc.FOUND and s.restore_issues == [] and world.opening == 40.0
    assert (ledger(s)[-1]["kind"], ledger(s)[-1]["outcome"]) == ("restore", "validated")
    assert all(e["outcome"] == "validated" for e in ledger(s)) and all(a == HOME for a in world.stage_args)
    assert "original joint values re-validated: yes" in s.message


def test_a_restore_pause_that_meets_joint_drift_refuses_continue_and_never_reports_a_restored_state(tmp_path):
    world = opening_world()
    s, _ = _run_to_pause(world, tmp_path)
    world.connected = True
    assert s.resume().kind == "step"
    for _ in range(100000):  # run the candidate to the restore pause
        event = s.step()
        if event.kind == "pause":
            break
        if event.kind == "gate":
            (s.approve_stage if event.stage == "opening" else s.decline_stage)(event.stage)
    assert s.phase == svc.PAUSED and s._pause.info["stage"] == "restore"
    world.connected = True
    world.accepted["j1"] += 1e-6  # Connect re-seeded the accepted pose
    assert s.resume().kind == "pause" and s.phase == svc.PAUSED and "joint identity" in s.message
    accepts = world.accept_calls
    s.cancel()  # the operator gives up instead: restoration restarts, still never revalidating drifted joints
    for _ in range(100000):
        event = s.step()
        if event.kind == "pause" or s.finished:
            break
    assert world.accept_calls == accepts  # nothing was validated on drifted joints
    assert not s.finished or s.restore_issues


def test_cancel_while_paused_for_a_trial_connect_goes_to_restore_and_never_continues_the_trial(tmp_path):
    world = opening_world()
    s, _ = _run_to_pause(world, tmp_path)
    s.cancel()
    _finish_with_operator(s, world)
    assert s.outcome == svc.CANCELLED and s._pause is None
    assert not [r for r in s.records if r["stage"] == "opening" and r["result"] == fa.PASSED]
    assert s.restore_issues == [] and world.opening == 40.0 and ledger(s)[-1]["kind"] == "restore"


# --- the facade accessor and the revalidator contract ------------------------------------------------------------------
def test_the_facade_joint_identity_accessor_is_read_only_and_mirrors_the_accept_path():
    source = (PYTHON / "DENTORobotWorkflowFacade.py").read_text(encoding="utf-8")
    body = source[source.index("def taskHomeJointIdentity"):]
    body = body[:body.index("    @staticmethod")]
    for needed in ("_manual_task_home_accepted_positions()", "monitored_joint_positions_si", "currentRobotState().joint_positions_si"):
        assert needed in body
    for forbidden in ("self._apply_positions_si", "saveTaskHome", "stageManualTaskHomeReview", "setBasePose"):
        assert forbidden not in body


# --- findings of the W1 review (F1 foreign change in the apply window / restore / Continue, F5, F7) ------------------
def test_a_foreign_home_change_inside_the_apply_window_stops_before_any_home_owner_is_called(tmp_path):
    world = HomeWorld(oracle=u5_passes)
    s = consent_session(world, tmp_path)
    s.prepare()

    def foreign_write_after_base(sess, event):
        if event.step == "apply_base":
            world.home.revision = "home-revision-99"

    drive(s, on_step=foreign_write_after_base)
    assert s.outcome == svc.BLOCKED and world.accept_calls == 0 and "home_stage" not in world.calls
    assert any(r.get("operator_review_required") and "changed outside the advisor" in r["reason"] for r in s.records)
    assert s.restore_issues and any("changed outside the advisor" in i for i in s.restore_issues)
    assert all(e["outcome"] == "refused" for e in ledger(s))  # nothing was revalidated over the foreign revision


def test_continue_refuses_a_foreign_home_change_made_while_paused(tmp_path):
    world = opening_world()
    s, _ = _run_to_pause(world, tmp_path)
    world.connected = True
    world.home.revision = "home-revision-77"
    assert any("changed outside the advisor" in i for i in s.resume_issues())
    assert s.resume().kind == "pause" and s.phase == svc.PAUSED


@pytest.mark.parametrize("mutation", ["source", "scene"])
def test_continue_refuses_foreign_source_or_scene_drift_without_rebasing(tmp_path, mutation):
    world = opening_world()
    s, _ = _run_to_pause(world, tmp_path)
    world.connected = True
    if mutation == "source":
        world.source_volume_fingerprint = "volume-foreign"
    else:
        world.scene_object["source_fingerprint"] = "source-geometry-foreign"
    calls = list(world.calls)

    issues = s.resume_issues()
    assert any(mutation in issue.lower() or "source" in issue.lower() or "scene" in issue.lower()
               for issue in issues)
    event = s.resume()
    assert event.kind == "pause" and s.phase == svc.PAUSED and world.calls == calls


@pytest.mark.parametrize("mutation", ["source", "scene"])
def test_foreign_source_or_scene_drift_after_base_apply_stops_before_home_stage_and_restore_revalidation(
        tmp_path, mutation):
    world = HomeWorld(oracle=u5_passes)
    s = consent_session(world, tmp_path)
    s.prepare()

    def foreign_write_after_trial_base(_session, event):
        if event.stage != "base_lateral" or event.step != "apply_base":
            return
        if mutation == "source":
            world.source_volume_fingerprint = "volume-foreign"
        else:
            world.scene_object["source_fingerprint"] = "source-geometry-foreign"

    drive(s, on_step=foreign_write_after_trial_base)
    reasons = " ".join([r.get("reason", "") for r in s.records] + list(s.restore_issues)).lower()
    assert s.outcome == svc.BLOCKED
    assert "source" in reasons or "scene" in reasons or "identity" in reasons
    assert world.calls.count("home_stage") == 0 and world.accept_calls == 0
    assert s.restore_issues  # the restore is reported incomplete instead of absorbing foreign input identity
    assert all(entry["outcome"] != "validated" for entry in ledger(s))


def test_consent_needs_a_complete_input_identity_instead_of_failing_later_at_the_pause(tmp_path):
    world = HomeWorld(full_identity=False)
    s = consent_session(world, tmp_path)
    s.prepare()
    assert s.finished and s.outcome == svc.BLOCKED and "complete input identity" in s.message


def test_a_runtime_acknowledgement_that_is_lost_is_not_hidden_by_the_stable_identity(tmp_path):
    world = HomeWorld(oracle=lambda v: {})
    s = consent_session(world, tmp_path)
    s.prepare()
    ok_before, _ = s._identity_matches_baseline()
    inner = world.logic.collisionSceneAuditRecord

    def lost_ack(node):
        record = inner(node)
        record.runtime_acknowledgement = {"status": "NotAcknowledged"}
        return record

    world.logic.collisionSceneAuditRecord = lost_ack
    ok_after, reason = s._identity_matches_baseline()
    assert ok_before and not ok_after and "audited scene" in reason


def test_a_changed_audit_base_binding_is_not_hidden_by_the_stable_identity(tmp_path):
    world = HomeWorld(oracle=lambda v: {})
    s = consent_session(world, tmp_path)
    s.prepare()
    ok_before, _ = s._identity_matches_baseline()
    inner = world.logic.collisionSceneAuditRecord

    def changed_base_binding(node):
        record = inner(node)
        record.base_fingerprint = "base-fp-foreign"
        return record

    world.logic.collisionSceneAuditRecord = changed_base_binding
    ok_after, reason = s._identity_matches_baseline()
    assert ok_before and not ok_after and ("scene" in reason.lower() or "base" in reason.lower())


@pytest.mark.parametrize("source", ["accepted", "monitored", "displayed"])
@pytest.mark.parametrize(("offset", "blocked"), [(1.0e-12, False), (1.1e-12, True)],
                         ids=["at-tolerance", "over-tolerance"])
def test_apply_and_save_checks_exact_joint_identity_tolerance_for_each_source(tmp_path, source, offset, blocked):
    world = HomeWorld(oracle=u5_passes)
    s = consent_session(world, tmp_path)
    s.prepare()
    drive(s)
    assert s.outcome == svc.FOUND and s.restore_issues == []
    getattr(world, source)["j4"] += offset  # j4 starts at 0.0, so the exact edge is representable

    if blocked:
        with pytest.raises(PermissionError, match="joint identity"):
            s.apply_and_save(acknowledged=())
        assert "store" not in world.calls
    else:
        s.apply_and_save(acknowledged=())
        assert world.calls.count("store") == 1
