"""Unit tests for the consent-gated Task Home revalidation helper (S6-ADVISOR-GUI-01, decision D1 option O4).

Direct tests of ``advisor_home`` with tiny fakes: no Slicer, ROS, MoveIt or advisor service. They pin the rules that
the session test (test_advisor_home_revalidation.py) reaches only indirectly: the exact joint tolerance, each
unreadable joint source, the owner calls each refusal makes or must not make, the ledger and summary text, the record
helpers, the stable identity and the operator pause file.
"""

import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PYTHON))

from dentobot_workflow import advisor_home as ah  # noqa: E402

SOURCES = ("accepted", "monitored", "displayed")
# j1 is exactly 0.0, so a perturbation of exactly 1e-12 is an exact float difference (no rounding at the edge)
SAVED = {"j1": 0.0, "j2": 0.25, "j3": -0.5, "j4": 1.0, "j5": 0.0}
TRIAL = {"kind": "trial", "index": 7, "label": "base lateral +5 mm", "active": True}
FROZEN = {"branch_revision": "branch-revision-1", "home_revision": "home-revision-1", "opening_mm": 40.5}
IDENTITY = {
    "saved_home": {"j1": 0.0},
    "confirmed_task_fingerprint": "task-fp-1",
    "base_fingerprint": "base-fp-1",
    "robot_profile": "dentobot-profile",
    "collision_audit_status": "current",
    "audited_scene_sources": {
        "objects": ["tooth-11"],
        "jaw_preparation_fingerprint": "jaw-fp-1",
        "world_to_base_fingerprint": "w2b-fp-1",
        "mesh_hash": "not part of the stable identity",
    },
}


def result(success, code="", message=""):
    return SimpleNamespace(success=success, code=code, message=message)


class TaskHome:
    """A plain attribute object standing in for a production Task Home record (no to_dict)."""

    def __init__(self, n=1, joints=SAVED):
        self.joint_names = list(joints)
        self.joint_positions_si = list(joints.values())
        self.revision = f"home-revision-{n}"
        self.runtime_validation_status = "validated"
        self.validated_at_utc = f"2026-10-08T00:00:{n:02d}Z"
        self.base_fingerprint = f"base-fp-{n}"
        self.collision_audit_fingerprint = f"audit-fp-{n}"


class FakeLogic:
    """The logic owner, reduced to the Task Home record it hands back."""

    def __init__(self, record):
        self.record = record

    def taskHomeRecord(self, node):
        return self.record


class FakeOwners:
    """The production Task Home owners, faked. Every call is logged so a test can see what was touched."""

    def __init__(self, logic):
        self.logic = logic
        self.calls = []
        self.identity = {source: dict(SAVED) for source in SOURCES}
        self.staged = False
        self.staged_joints = None
        self.gap = ""
        self.stage_result = result(True, "manual_task_home_review_staged", "staged")
        self.stage_error = None
        self.accept_result = result(True, "manual_task_home_review_accepted", "accepted")
        self.accept_error = None
        self.next_home = None  # what a successful accept leaves behind; None means the next revision with saved joints
        self.revision = 1

    def manualTaskHomeReview(self):
        self.calls.append("review")
        return SimpleNamespace(details={"staged": self.staged})

    def taskHomeJointIdentity(self):
        self.calls.append("identity")
        return self.identity

    def stageManualTaskHomeReview(self, joints):
        self.calls.append("stage")
        self.staged_joints = dict(joints)
        if self.stage_error is not None:
            raise self.stage_error
        self.staged = self.stage_result.success
        return self.stage_result

    def cancelManualTaskHomeReview(self):
        self.calls.append("cancel")
        self.staged = False
        return result(True)

    def acceptManualTaskHomeReview(self):
        self.calls.append("accept")
        if self.accept_error is not None:
            raise self.accept_error
        if self.accept_result.success:
            self.revision += 1
            self.logic.record = self.next_home or TaskHome(self.revision)
            self.staged = False
        return self.accept_result

    def taskHomeValidationGap(self, node):
        self.calls.append("gap")
        return self.gap


def make(root, record=None):
    logic = FakeLogic(TaskHome(1) if record is None else record)
    owners = FakeOwners(logic)
    return ah.HomeRevalidator(logic, owners, "node", SAVED, root), owners, logic


def attempt(revalidator, **overrides):
    return revalidator.revalidate(**{**TRIAL, **overrides})


# --- consent text, digest and constants -------------------------------------------------------------------------------
def test_consent_digest_is_a_stable_sixteen_hex_prefix_of_the_sha256_of_the_text():
    digest = ah.consent_digest()
    assert digest == hashlib.sha256(ah.CONSENT_TEXT.encode("utf-8")).hexdigest()[:16]
    assert re.fullmatch(r"[0-9a-f]{16}", digest)
    assert ah.consent_digest() == digest


def test_consent_digest_changes_with_any_change_to_the_text():
    assert ah.consent_digest("yes") != ah.consent_digest()
    assert ah.consent_digest(ah.CONSENT_TEXT + " ") != ah.consent_digest()


def test_consent_text_names_simulation_only_no_joint_movement_the_collision_guards_and_the_own_review():
    for phrase in ("SIMULATION ONLY", "no joint is moved", "collision guards", "own review"):
        assert phrase in ah.CONSENT_TEXT


def test_the_rejection_limit_and_the_joint_tolerance_are_the_documented_values():
    assert ah.MAX_CONSECUTIVE_REJECTIONS == 5
    assert ah.JOINT_TOLERANCE_SI == 1e-12


# --- joint identity before a candidate: accepted / monitored / displayed must equal the saved Home --------------------
def test_equal_joint_vectors_have_no_issues(tmp_path):
    revalidator, _, _ = make(tmp_path)
    assert revalidator.joint_issues() == []


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("offset", [1e-12, -1e-12])
def test_a_joint_exactly_at_the_tolerance_passes(tmp_path, source, offset):
    revalidator, owners, _ = make(tmp_path)
    owners.identity[source]["j1"] = offset
    assert revalidator.joint_issues() == []


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("offset", [1.1e-12, -1.1e-12])
def test_a_joint_just_over_the_tolerance_is_reported_for_its_own_source(tmp_path, source, offset):
    revalidator, owners, _ = make(tmp_path)
    owners.identity[source]["j1"] = offset
    assert revalidator.joint_issues() == [f"{source} J1–J5 differ from the saved Task Home by 1.1e-12 (SI)"]


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("damage", ["missing", "none", "one-joint-short", "one-joint-extra"])
def test_each_unreadable_joint_source_gets_its_own_issue_and_no_other(tmp_path, source, damage):
    revalidator, owners, _ = make(tmp_path)
    if damage == "missing":
        del owners.identity[source]
    elif damage == "none":
        owners.identity[source] = None
    elif damage == "one-joint-short":
        owners.identity[source] = {k: v for k, v in SAVED.items() if k != "j5"}
    else:
        owners.identity[source] = {**SAVED, "j6": 0.0}
    assert revalidator.joint_issues() == [f"{source} J1–J5 are unavailable"]


def test_with_no_identity_at_all_all_three_sources_are_reported_in_order(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.identity = None
    assert revalidator.joint_issues() == [f"{source} J1–J5 are unavailable" for source in SOURCES]


class NoReader:
    """A facade without the identity reader."""


class NonCallableReader:
    taskHomeJointIdentity = None


class RaisingReader:
    def taskHomeJointIdentity(self):
        raise RuntimeError("bridge " * 100)


@pytest.mark.parametrize("facade", [NoReader(), NonCallableReader()], ids=["no-reader", "reader-not-callable"])
def test_a_missing_identity_reader_is_one_issue(tmp_path, facade):
    revalidator = ah.HomeRevalidator(FakeLogic(TaskHome(1)), facade, "node", SAVED, tmp_path)
    assert revalidator.joint_issues() == ["the accepted/monitored/displayed joint identity cannot be read"]


def test_a_reader_that_raises_is_one_issue_with_its_text_bounded_to_240_characters(tmp_path):
    revalidator = ah.HomeRevalidator(FakeLogic(TaskHome(1)), RaisingReader(), "node", SAVED, tmp_path)
    [issue] = revalidator.joint_issues()
    assert issue.startswith("the accepted/monitored/displayed joint identity could not be read: bridge bridge")
    assert len(issue) == 240


# --- the identity the advisor expects ---------------------------------------------------------------------------------
def test_external_change_is_empty_for_the_unchanged_record_and_names_a_foreign_revision(tmp_path):
    revalidator, _, _ = make(tmp_path)
    assert revalidator.expected_identity == ah.record_identity(TaskHome(1))
    assert revalidator.external_change_issue(TaskHome(1)) == ""
    assert revalidator.external_change_issue(TaskHome(99)) == (
        "the saved Task Home changed outside the advisor's own recorded revalidations")


# --- refusals create no authority: each is ledgered and stops for the operator ----------------------------------------
def test_an_inactive_ros_refuses_before_any_owner_is_touched_and_writes_the_ledger(tmp_path):
    revalidator, owners, _ = make(tmp_path / "run")
    with pytest.raises(ah.HomeRevalidationRefused, match="ROS/MoveIt is not connected"):
        attempt(revalidator, active=False)
    assert owners.calls == []
    [entry] = revalidator.ledger
    assert (entry["sequence"], entry["outcome"], entry["code"]) == (1, "refused", "")
    assert json.loads((tmp_path / "run" / "home-revalidations.json").read_text(encoding="utf-8")) == revalidator.ledger
    assert revalidator.consecutive_rejections == 0


@pytest.mark.parametrize("flag", ["_manual_task_home_acceptance_in_progress",
                                  "_manual_task_home_reconciliation_in_progress"])
def test_an_acceptance_or_reconciliation_in_progress_refuses_before_anything_is_staged(tmp_path, flag):
    revalidator, owners, _ = make(tmp_path)
    setattr(owners, flag, True)
    with pytest.raises(ah.HomeRevalidationRefused, match="already in progress"):
        attempt(revalidator)
    assert owners.calls == []


def test_a_review_already_staged_is_refused_and_neither_overwritten_nor_cancelled(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.staged = True
    with pytest.raises(ah.HomeRevalidationRefused, match="already staged"):
        attempt(revalidator)
    assert owners.calls == ["review"]
    assert owners.staged


def test_joints_that_differ_from_the_saved_home_refuse_before_anything_is_staged(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.identity["monitored"]["j2"] = SAVED["j2"] + 1e-6
    with pytest.raises(ah.HomeRevalidationRefused) as info:
        attempt(revalidator)
    assert str(info.value) == ("saved-joint identity check failed: "
                               "monitored J1–J5 differ from the saved Task Home by 1e-06 (SI)")
    assert owners.calls == ["review", "identity"]


def test_a_stage_that_is_not_staged_is_cancelled_and_refused_without_accepting(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.stage_result = result(False, "manual_task_home_review_rejected", "setup identity unavailable")
    with pytest.raises(ah.HomeRevalidationRefused, match="Home review was not staged: setup identity unavailable"):
        attempt(revalidator)
    assert owners.calls == ["review", "identity", "stage", "cancel"]
    [entry] = revalidator.ledger
    assert (entry["outcome"], entry["code"]) == ("refused", "manual_task_home_review_rejected")
    assert revalidator.consecutive_rejections == 0


def test_a_stage_that_raises_is_refused_with_one_stage_call_and_no_accept(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.stage_error = RuntimeError("bridge down")
    with pytest.raises(ah.HomeRevalidationRefused, match="Home review could not be staged: bridge down"):
        attempt(revalidator)
    assert owners.calls == ["review", "identity", "stage"]
    assert revalidator.ledger[0]["outcome"] == "refused"


def test_an_accept_that_raises_is_refused_as_an_unknown_outcome_and_never_retried_or_cancelled(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.accept_error = RuntimeError("bridge dropped")
    with pytest.raises(ah.HomeRevalidationRefused, match="outcome is unknown and is not retried") as info:
        attempt(revalidator)
    assert "bridge dropped" in str(info.value)
    assert owners.calls == ["review", "identity", "stage", "accept"]  # one accept; the review is left staged
    assert owners.staged
    [entry] = revalidator.ledger
    assert (entry["outcome"], entry["code"]) == ("refused", "unknown")
    assert revalidator.consecutive_rejections == 0


def test_an_accept_reporting_unknown_is_refused_and_keeps_the_staged_review(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.accept_result = result(False, "manual_task_home_acceptance_unknown", "may have committed")
    with pytest.raises(ah.HomeRevalidationRefused, match="reported an unknown outcome: may have committed"):
        attempt(revalidator)
    assert owners.calls == ["review", "identity", "stage", "accept"]
    assert owners.staged
    [entry] = revalidator.ledger
    assert (entry["outcome"], entry["code"]) == ("refused", "manual_task_home_acceptance_unknown")
    assert revalidator.consecutive_rejections == 0


# --- production rejections and success --------------------------------------------------------------------------------
def test_a_guard_rejection_fails_the_candidate_cancels_the_staged_review_and_counts_it(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.accept_result = result(False, "manual_task_home_review_rejected", "strict collision guard rejected the pose")
    with pytest.raises(ah.HomeRevalidationRejected) as info:
        attempt(revalidator)
    assert str(info.value) == ("the production guard rejected the unchanged saved joints: "
                               "strict collision guard rejected the pose")
    assert owners.calls == ["review", "identity", "stage", "accept", "cancel"]
    assert not owners.staged
    [entry] = revalidator.ledger
    assert (entry["outcome"], entry["code"]) == ("rejected", "manual_task_home_review_rejected")
    assert revalidator.consecutive_rejections == 1


def test_rejections_accumulate_until_a_validated_revalidation_resets_them(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.accept_result = result(False, "manual_task_home_review_rejected", "strict collision guard rejected the pose")
    for _ in range(2):
        with pytest.raises(ah.HomeRevalidationRejected):
            attempt(revalidator)
    assert revalidator.consecutive_rejections == 2
    owners.accept_result = result(True, "manual_task_home_review_accepted", "accepted")
    attempt(revalidator)
    assert revalidator.consecutive_rejections == 0


def test_a_validated_revalidation_stages_exactly_the_saved_joints_and_expects_the_new_identity(tmp_path):
    revalidator, owners, logic = make(tmp_path)
    entry = attempt(revalidator)
    assert (entry["outcome"], entry["code"], entry["message"]) == (
        "validated", "manual_task_home_review_accepted", "accepted")
    assert owners.staged_joints == SAVED  # exactly the saved joints, never different ones
    assert owners.calls == ["review", "identity", "stage", "accept", "gap"]
    assert revalidator.expected_identity == ah.record_identity(logic.record)
    assert revalidator.expected_identity["revision"] == "home-revision-2"
    assert revalidator.external_change_issue(logic.record) == ""


def test_a_validated_home_with_a_validation_gap_is_rejected_and_counted(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.gap = "collision audit is stale"
    with pytest.raises(ah.HomeRevalidationRejected,
                       match="accepted but not runtime-validated: collision audit is stale"):
        attempt(revalidator)
    [entry] = revalidator.ledger
    assert (entry["outcome"], entry["after"]["revision"]) == ("rejected", "home-revision-2")
    assert revalidator.consecutive_rejections == 1


def test_an_accepted_home_whose_joints_differ_from_the_saved_ones_is_refused(tmp_path):
    revalidator, owners, _ = make(tmp_path)
    owners.next_home = TaskHome(2, joints={**SAVED, "j3": SAVED["j3"] + 1e-6})
    with pytest.raises(ah.HomeRevalidationRefused, match="the saved Task Home joints changed during acceptance"):
        attempt(revalidator)
    [entry] = revalidator.ledger
    assert (entry["outcome"], entry["after"]["revision"]) == ("refused", "home-revision-2")
    assert revalidator.consecutive_rejections == 0


# --- ledger and summary -----------------------------------------------------------------------------------------------
def test_the_ledger_entry_records_the_attempt_and_its_before_and_after_summaries(tmp_path):
    revalidator, _, _ = make(tmp_path)
    entry = attempt(revalidator)
    assert (entry["sequence"], entry["kind"], entry["candidate"], entry["label"]) == (
        1, "trial", 7, "base lateral +5 mm")
    assert entry["joints_si"] == SAVED
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", entry["utc"])
    assert entry["before"] == {"revision": "home-revision-1", "status": "validated",
                               "validated_at_utc": "2026-10-08T00:00:01Z", "base_fingerprint": "base-fp-1",
                               "audit": "audit-fp-1"}
    assert entry["after"] == {"revision": "home-revision-2", "status": "validated",
                              "validated_at_utc": "2026-10-08T00:00:02Z", "base_fingerprint": "base-fp-2",
                              "audit": "audit-fp-2"}
    assert (entry["code"], entry["message"]) == ("manual_task_home_review_accepted", "accepted")


def test_the_ledger_file_is_rewritten_on_every_attempt_and_equals_the_in_memory_ledger(tmp_path):
    revalidator, _, _ = make(tmp_path / "run")
    path = tmp_path / "run" / "home-revalidations.json"
    with pytest.raises(ah.HomeRevalidationRefused):
        attempt(revalidator, active=False)
    assert json.loads(path.read_text(encoding="utf-8")) == revalidator.ledger
    attempt(revalidator)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == revalidator.ledger
    assert [(e["sequence"], e["outcome"]) for e in saved] == [(1, "refused"), (2, "validated")]


def test_summary_lines_give_one_line_per_attempt_and_the_message_only_when_not_validated(tmp_path):
    revalidator, _, _ = make(tmp_path)
    attempt(revalidator)
    with pytest.raises(ah.HomeRevalidationRefused):
        attempt(revalidator, kind="restore", index=0, label="restore", active=False)
    assert revalidator.summary_lines() == [
        "#1 trial candidate 7 (base lateral +5 mm): validated; revision home-revision-1→home-revision-2; "
        "validated_at 2026-10-08T00:00:02Z",
        "#2 restore candidate 0 (restore): refused; revision home-revision-2→home-revision-2; "
        "validated_at 2026-10-08T00:00:02Z; ROS/MoveIt is not connected; the advisor never connects by itself",
    ]


def test_summary_lines_show_a_missing_record_as_none_and_a_missing_validation_time_as_a_dash(tmp_path):
    logic = FakeLogic(None)
    revalidator = ah.HomeRevalidator(logic, FakeOwners(logic), "node", SAVED, tmp_path)
    with pytest.raises(ah.HomeRevalidationRefused):
        attempt(revalidator, active=False)
    assert revalidator.summary_lines() == [
        "#1 trial candidate 7 (base lateral +5 mm): refused; revision None→None; validated_at -; "
        "ROS/MoveIt is not connected; the advisor never connects by itself"]


# --- record helpers ---------------------------------------------------------------------------------------------------
def test_no_record_has_an_empty_identity_and_a_blank_summary():
    assert ah.record_identity(None) == {}
    assert ah.record_summary(None) == {"revision": None, "status": "", "validated_at_utc": "",
                                       "base_fingerprint": "", "audit": ""}


def test_record_identity_uses_to_dict_as_a_copy_and_treats_a_non_mapping_as_empty():
    payload = {"revision": "home-revision-4", "joint_positions_si": [0.0, 0.25]}

    class WithToDict:
        def to_dict(self):
            return payload

    class NonMapping:
        def to_dict(self):
            return ["not", "a", "mapping"]

    identity = ah.record_identity(WithToDict())
    assert identity == payload and identity is not payload
    assert ah.record_identity(NonMapping()) == {}


def test_record_identity_of_a_plain_object_takes_only_the_fields_it_has():
    record = TaskHome(3)
    record.display_name = "not an identity field"
    assert ah.record_identity(record) == {
        "joint_names": ["j1", "j2", "j3", "j4", "j5"],
        "joint_positions_si": [0.0, 0.25, -0.5, 1.0, 0.0],
        "base_fingerprint": "base-fp-3",
        "revision": "home-revision-3",
        "runtime_validation_status": "validated",
        "collision_audit_fingerprint": "audit-fp-3",
        "validated_at_utc": "2026-10-08T00:00:03Z",
    }


def test_record_summary_of_a_plain_object_keeps_the_revision_raw_and_blanks_missing_fields():
    assert ah.record_summary(TaskHome(4)) == {
        "revision": "home-revision-4", "status": "validated", "validated_at_utc": "2026-10-08T00:00:04Z",
        "base_fingerprint": "base-fp-4", "audit": "audit-fp-4"}
    assert ah.record_summary(SimpleNamespace(revision=7)) == {
        "revision": 7, "status": "", "validated_at_utc": "", "base_fingerprint": "", "audit": ""}


# --- stable identity: what a search compares, without revision-bound authority ----------------------------------------
def test_stable_identity_drops_the_revision_bound_authority_and_keeps_the_rest():
    stable = ah.stable_identity(IDENTITY, SAVED)
    assert set(stable) == {"base_fingerprint", "robot_profile", "collision_audit_status",
                           "audited_scene_sources", "saved_home_joints"}
    assert stable["base_fingerprint"] == "base-fp-1"
    assert stable["robot_profile"] == "dentobot-profile"
    assert stable["collision_audit_status"] == "current"


def test_saved_joints_are_rounded_to_nine_decimals_sorted_by_name_and_none_is_empty():
    joints = ah.stable_identity(IDENTITY, {"j2": 0.1234567894, "j1": 1.0000000006, "j3": -0.0000000004})
    assert joints["saved_home_joints"] == {"j1": 1.000000001, "j2": 0.123456789, "j3": 0.0}
    assert list(joints["saved_home_joints"]) == ["j1", "j2", "j3"]
    assert ah.stable_identity(IDENTITY, None)["saved_home_joints"] == {}


def test_audited_scene_sources_reduce_to_three_fields_with_none_for_the_missing_ones():
    assert ah.stable_identity(IDENTITY, SAVED)["audited_scene_sources"] == {
        "objects": ["tooth-11"], "jaw_preparation_fingerprint": "jaw-fp-1", "world_to_base_fingerprint": "w2b-fp-1"}
    partial = ah.stable_identity({"audited_scene_sources": {"objects": []}}, SAVED)
    assert partial["audited_scene_sources"] == {
        "objects": [], "jaw_preparation_fingerprint": None, "world_to_base_fingerprint": None}
    absent = ah.stable_identity({}, SAVED)
    assert absent["audited_scene_sources"] == {
        "objects": None, "jaw_preparation_fingerprint": None, "world_to_base_fingerprint": None}


def test_source_only_also_drops_the_audited_scene_and_the_audit_status():
    stable = ah.stable_identity(IDENTITY, SAVED, source_only=True)
    assert set(stable) == {"base_fingerprint", "robot_profile", "saved_home_joints"}


def test_stable_identity_does_not_mutate_its_inputs():
    identity, saved = copy.deepcopy(IDENTITY), copy.deepcopy(SAVED)
    ah.stable_identity(identity, saved)
    ah.stable_identity(identity, saved, source_only=True)
    assert identity == IDENTITY and saved == SAVED


# --- operator pause: frozen identity and the attributed pause file ----------------------------------------------------
def fingerprint16(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def test_enter_writes_the_pause_record_with_the_frozen_fingerprint_and_keeps_its_own_copy(tmp_path):
    pause = ah.OperatorPause(tmp_path / "run")
    frozen = dict(FROZEN)
    pause.enter(candidate=3, stage="opening", step="connect", message="Use Connect (6.1)", frozen=frozen)
    frozen["home_revision"] = "changed after the pause"
    data = json.loads((tmp_path / "run" / "pause.json").read_text(encoding="utf-8"))
    assert {k: data[k] for k in ("candidate", "step", "message")} == {
        "candidate": 3, "step": "connect", "message": "Use Connect (6.1)"}
    assert data["frozen_identity_fingerprint"] == fingerprint16(FROZEN)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", data["paused_at"])
    assert pause.info == {"reason": "connect", "candidate": 3, "stage": "opening", "step": "connect",
                          "frozen": FROZEN}


def test_drift_lists_exactly_the_keys_whose_values_differ_across_the_union_of_keys(tmp_path):
    pause = ah.OperatorPause(tmp_path)
    pause.enter(candidate=3, stage="opening", step="connect", message="m", frozen={"a": 1, "b": 2, "c": 3})
    assert pause.drift({"a": 1, "b": 2, "c": 3}) == []
    assert pause.drift({"a": 1, "b": 5, "d": 4}) == ["b", "c", "d"]


def test_refused_and_resumed_merge_into_the_same_pause_file_and_keep_the_earlier_fields(tmp_path):
    pause = ah.OperatorPause(tmp_path / "run")
    path = tmp_path / "run" / "pause.json"
    pause.enter(candidate=3, stage="opening", step="connect", message="Use Connect (6.1)", frozen=FROZEN)
    entered = json.loads(path.read_text(encoding="utf-8"))
    pause.refused("Continue refused: still disconnected")
    refused = json.loads(path.read_text(encoding="utf-8"))
    assert {k: refused[k] for k in entered} == entered
    assert refused["last_refusal"] == "Continue refused: still disconnected"
    assert "refused_utc" in refused and "resumed_utc" not in refused
    pause.resumed()
    resumed = json.loads(path.read_text(encoding="utf-8"))
    assert {k: resumed[k] for k in refused} == refused
    assert "resumed_utc" in resumed


def test_a_refusal_keeps_the_pause_and_resumed_clears_the_frozen_info(tmp_path):
    pause = ah.OperatorPause(tmp_path)
    pause.enter(candidate=3, stage="opening", step="connect", message="m", frozen=FROZEN)
    pause.refused("no")
    assert pause.info is not None and pause.info["candidate"] == 3
    pause.resumed()
    assert pause.info is None
