"""Lip/mouth-barrier variants through the production owners (S6-ADVISOR-GUI-01, contract C-LIP).

Fakes only (no Slicer/ROS/MoveIt). They prove the wiring, the approved-value restriction, the
attributed-evidence eligibility rule, restore and the silent-false-evidence guard; whether a
variant actually clears a collision is runtime evidence that these tests do not provide.
"""

import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow" / "Resources" / "Python"
sys.path.insert(0, str(PYTHON))
sys.path.insert(0, str(ROOT / "Testing"))

from test_advisor_service import World, drive, fail, ok, session, svc  # noqa: E402

from dentobot_workflow import feasibility_advisor as fa  # noqa: E402
from dentobot_workflow import mouth_portal as mp  # noqa: E402

PACKAGE = PYTHON / "dentobot_workflow"
DEFAULTS = dict(mp.DEFAULT_BARRIER_TUNING)
LIP_ACK = "lip/mouth barrier variant"


class _Proxy:
    def __init__(self, inner, world):
        self._inner, self._w = inner, world

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _Logic(_Proxy):
    def step6MouthBarrierTuning(self, node):
        return dict(self._w.tuning)

    def setStep6MouthBarrierTuning(self, node, lip_margin_mm, lip_slab_mm, portal_enlarge_mm):
        tuning = mp.validated_barrier_tuning(lip_margin_mm, lip_slab_mm, portal_enlarge_mm)
        self._w._log("barrier_set")
        self._w.tuning = tuning
        return dict(tuning)

    def collisionSceneAuditRecord(self, node):
        record = self._inner.collisionSceneAuditRecord(node)
        digest = json.dumps(self._w.audited_tuning, sort_keys=True)
        record.object_records.append(dict(
            self._w.scene_object, source_name="dentobot_mouth_barrier_slab", source_role="mouth-barrier",
            classification="virtual-barrier", prepared_world_fingerprint="barrier-" + digest,
            outgoing_fingerprint="barrier-out-" + digest))
        return record


LIP = fa.LIP_SLAB_OBJECT_ID
SPINDLE = "pneumatic_spindle-Copy"


class _Facade(_Proxy):
    def checkPreEntryIK(self, *, progress=None):
        pair = self._w.blocking_pair(self._w.view())
        if pair is None:
            return self._inner.checkPreEntryIK(progress=progress)
        seed = {"candidate_index": 0, "static_state_validity_status": "Invalid", "endpoint_check_status": "Failed",
                "collision_pairs": [list(pair)] if pair else []}
        return SimpleNamespace(success=True, code="x", message="", details={"diagnosticStatus": "NoIk"},
                               payload=SimpleNamespace(to_dict=lambda: {"candidate_records": [seed]}))

    def syncPlanningScene(self):
        self._w._log("sync_scene")
        if not self._w.connected:
            return fail("ros_required", "Connect first.")
        if self._w.sync_changes_geometry:
            self._w.audited_tuning = dict(self._w.tuning)
        return ok("planning_scene_synced", details={"runtimeAcknowledged": self._w.acknowledge})


def _lip_blocks_at_default_margin(view):
    """PreEntry collides with the lip slab until the margin is the approved 0 mm."""

    return None if view["lip_margin"] == 0.0 else (LIP, SPINDLE)


class BarrierWorld(World):
    def __init__(self, *, tuning=None, sync_changes_geometry=True, acknowledge=True, blocking_pair=None, **kwargs):
        super().__init__(**kwargs)
        self.blocking_pair = blocking_pair or _lip_blocks_at_default_margin
        self.tuning = dict(tuning or DEFAULTS)
        self.audited_tuning = dict(self.tuning)
        self.sync_changes_geometry = sync_changes_geometry
        self.acknowledge = acknowledge
        self.logic = _Logic(self.logic, self)
        self.facade = _Facade(self.facade, self)

    def view(self):
        view = super().view()
        view.update(lip_margin=self.tuning["lip_margin_mm"], lip_slab=self.tuning["lip_slab_mm"],
                    portal=self.tuning["portal_enlarge_mm"])
        return view


def _lip_search(tmp_path, **world_kwargs):
    world = BarrierWorld(**world_kwargs)
    s = session(world, tmp_path)
    s.prepare()
    drive(s, approve=("lip_variant",))
    return world, s


# --- bounds, defaults and the single truth store --------------------------------------------
def test_tuning_validation_accepts_only_the_approved_values_and_never_rounds_or_clamps():
    assert mp.validated_barrier_tuning(2.0, 8.0, 5.0) == DEFAULTS
    assert mp.validated_barrier_tuning(0.0, 4.0, 10.0) == {"lip_margin_mm": 0.0, "lip_slab_mm": 4.0, "portal_enlarge_mm": 10.0}
    assert mp.validated_barrier_tuning(0, 8, 10)["lip_slab_mm"] == 8.0  # ints are exact values too
    for bad in ((1.0, 8.0, 5.0), (0.5, 8.0, 5.0), (-0.1, 8.0, 5.0), (2.1, 8.0, 5.0), (2.0, 6.0, 5.0), (2.0, 3.9, 5.0),
                (2.0, 8.1, 5.0), (2.0, 8.0, 7.5), (2.0, 8.0, 4.9), (2.0, 8.0, 10.1), (float("nan"), 8.0, 5.0),
                (float("inf"), 8.0, 5.0), (True, 8.0, 5.0), ("2", 8.0, 5.0), (None, 8.0, 5.0)):
        with pytest.raises(ValueError):
            mp.validated_barrier_tuning(*bad)


def test_production_approved_values_the_advisor_table_and_generated_variants_agree():
    assert fa.LIP_APPROVED_VALUES == {fa.LIP_MARGIN_MM: mp.BARRIER_APPROVED_VALUES["lip_margin_mm"],
                                      fa.LIP_SLAB_MM: mp.BARRIER_APPROVED_VALUES["lip_slab_mm"],
                                      fa.PORTAL_ENLARGE_MM: mp.BARRIER_APPROVED_VALUES["portal_enlarge_mm"]}
    for key, (default, variant) in fa.LIP_APPROVED_VALUES.items():
        assert fa.LIP_VARIANT_BOUNDS[key] == (min(default, variant), max(default, variant))  # hull only
        assert fa.DEFAULT_BARRIER[key] == default
    assert (mp.LIP_LINE_MARGIN_MM, mp.BARRIER_LIP_THICKNESS_MM, mp.PORTAL_ENLARGE_MM) == (2.0, 8.0, 5.0)
    assert len(fa.LIP_VARIANTS) == 7  # every non-default combination of the three endpoints, nothing between
    combos = {tuple(sorted(v.items())) for v in fa.LIP_VARIANTS}
    for variant in fa.LIP_VARIANTS:
        assert variant and all(value == fa.LIP_APPROVED_VALUES[key][1] for key, value in variant.items())
    assert len(combos) == 7
    base = fa.baseline_state(40.0)
    assert fa.state_violations({**base, fa.LIP_MARGIN_MM: 1.0}, 40.0)  # intermediate values are not approved
    assert fa.state_violations({**base, fa.LIP_SLAB_MM: 6.0}, 40.0) and fa.state_violations({**base, fa.PORTAL_ENLARGE_MM: 7.5}, 40.0)


def test_node_defaults_and_ownership_registry_match_the_production_constants():
    fields = {}
    for node in ast.parse((PACKAGE / "parameter_state.py").read_text(encoding="utf-8")).body:
        for child in ast.walk(node):
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                fields[child.target.id] = ast.literal_eval(child.value) if child.value is not None else None
    from dentobot_case.ownership import DEFAULTS as CASE_DEFAULTS, PARAMETER_OWNERS

    for field, key in (("step6MouthBarrierLipMarginMm", "lip_margin_mm"), ("step6MouthBarrierLipSlabMm", "lip_slab_mm"),
                       ("step6MouthBarrierPortalEnlargeMm", "portal_enlarge_mm")):
        assert fields[field] == DEFAULTS[key]
        assert PARAMETER_OWNERS[field] == PARAMETER_OWNERS["step6MouthBarrierEdgeMode"] == "simulation.planning"
        assert float(CASE_DEFAULTS[field]) == DEFAULTS[key]


def test_scene_sync_is_the_only_writer_and_every_consumer_reads_the_node_tuning():
    source = (PACKAGE / "logic_robot_scene_sync.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if name in {"shift_portal_to_lip_line", "enlarge_portal", "build_mouth_barrier"}:
                calls[name] = {kw.arg for kw in node.keywords}
    assert "margin_mm" in calls["shift_portal_to_lip_line"] and "margin_mm" in calls["enlarge_portal"]
    assert "lip_thickness_mm" in calls["build_mouth_barrier"]
    assert "tuple(tuning.values())" in source  # portal cache key follows the tuning
    fields = {"step6MouthBarrierLipMarginMm", "step6MouthBarrierLipSlabMm", "step6MouthBarrierPortalEnlargeMm"}
    writers = set()
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in fields and isinstance(node.ctx, ast.Store):
                writers.add(path.name)
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "setattr" and path.name != "logic_robot_scene_sync.py":
                assert not (node.args and isinstance(node.args[1], ast.Constant) and node.args[1].value in fields)
    assert writers == set()  # the only writer is the validated setattr loop in the logic owner
    assert "def setStep6MouthBarrierTuning" in source and "setattr(parameterNode, field_name" in source


# --- advisor behaviour -------------------------------------------------------------------------
def test_lip_variant_runs_through_the_production_owner_then_restores_the_defaults(tmp_path):
    world, s = _lip_search(tmp_path)
    lip = [r for r in s.records if r["stage"] == "lip_variant"]
    assert lip and lip[0]["result"] == fa.PASSED and lip[0]["change"] == {fa.LIP_MARGIN_MM: 0.0}
    evidence = lip[0]["steps"]["prerequisites"]["observed"]["lip_slab_evidence"]
    assert evidence and evidence[0]["pair"] == sorted([LIP, SPINDLE]) and evidence[0]["step"] == "preentry"
    assert evidence[0]["sequence"] == 1  # attributed to the baseline candidate
    assert s.outcome == "found" and s.restore_issues == [] and world.tuning == DEFAULTS
    assert world.audited_tuning == DEFAULTS  # restore re-published the default barrier
    assert world.calls.count("barrier_set") == 2 and world.calls.count("sync_scene") == 2  # apply + restore
    assert "store" not in world.calls  # never saved by the search
    assert "UNTESTED" not in s.message.upper()


def test_non_lip_candidates_never_touch_the_barrier(tmp_path):
    world = BarrierWorld(oracle=lambda view: {} if view["u"] == 5.0 else {"diagnose_P1": "blocked"},
                         blocking_pair=lambda view: None)
    s = session(world, tmp_path)
    s.prepare()
    drive(s)
    assert s.outcome == "found" and [r["stage"] for r in s.records][-1] == "base_lateral"
    assert "barrier_set" not in world.calls and "sync_scene" not in world.calls


def test_a_declined_lip_gate_never_changes_the_barrier(tmp_path):
    world = BarrierWorld()
    s = session(world, tmp_path)
    s.prepare()
    events = drive(s, decline=("lip_variant", "opening", "base_yaw"))
    gate = next(e for e in events if e.kind == "gate" and e.stage == "lip_variant")
    assert "Baseline evidence" in gate.message and LIP in gate.message
    assert "barrier_set" not in world.calls and world.tuning == DEFAULTS
    assert not [r for r in s.records if r["stage"] == "lip_variant"]


def test_a_lip_winner_is_stored_with_its_barrier_only_after_the_operator_acknowledges_it(tmp_path):
    world, s = _lip_search(tmp_path)
    best = s.best_candidate()
    assert s.required_acknowledgements(best) == [LIP_ACK]
    with pytest.raises(PermissionError):
        s.apply_and_save(acknowledged=(), record=best)
    assert "store" not in world.calls
    s.apply_and_save(acknowledged=(LIP_ACK,), record=best)
    assert world.stored[-1]["barrier_tuning"] == {"lip_margin_mm": 0.0, "lip_slab_mm": 8.0, "portal_enlarge_mm": 5.0}
    assert "lip_margin_mm" in world.stored[-1]["notes"]


def test_a_scene_that_did_not_change_is_never_accepted_as_evidence_for_a_variant(tmp_path):
    world, s = _lip_search(tmp_path, sync_changes_geometry=False)
    lip = [r for r in s.records if r["stage"] == "lip_variant"]
    assert lip and lip[0]["result"] == fa.SETUP_ERROR and "did not change" in json.dumps(lip[0])
    assert not [r for r in s.records if r["result"] == fa.PASSED and r["stage"] == "lip_variant"]


def test_an_unacknowledged_scene_sync_stops_the_variant(tmp_path):
    world, s = _lip_search(tmp_path, acknowledge=False)
    lip = [r for r in s.records if r["stage"] == "lip_variant"]
    assert lip and lip[0]["result"] == fa.SETUP_ERROR and "did not acknowledge" in json.dumps(lip[0])


def test_a_branch_that_already_carries_a_variant_is_never_searched_or_altered(tmp_path):
    saved = {"lip_margin_mm": 0.0, "lip_slab_mm": 4.0, "portal_enlarge_mm": 5.0}
    world = BarrierWorld(tuning=saved, blocking_pair=lambda view: (LIP, SPINDLE))
    s = session(world, tmp_path)
    s.prepare()
    assert "lip_variant" in s.unavailable_stages and "non-default" in s.unavailable_stages["lip_variant"]
    drive(s, approve=("lip_variant",))
    assert "barrier_set" not in world.calls and world.tuning == saved
    lip = [r for r in s.records if r["stage"] == "lip_variant"]
    assert lip and all(r["result"] == fa.UNTESTED for r in lip)


def test_restore_without_ros_stores_the_values_and_leaves_publication_to_connect(tmp_path):
    world = BarrierWorld(disconnect_drops_connection=False)
    s = session(world, tmp_path)
    s.prepare()

    def drop_ros_when_restoring(sess, event):
        if sess.phase == svc.RESTORING:  # before the first restore step runs
            world.connected = False

    drive(s, approve=("lip_variant",), on_step=drop_ros_when_restoring)
    assert world.tuning == DEFAULTS  # values restored through the production owner
    assert world.calls.count("sync_scene") == 1  # no sync attempted while ROS was disconnected
    assert s.finished  # the remaining restore steps report their own ROS-dependent issues, not the barrier


def test_the_default_service_has_no_barrier_applier_without_the_production_owner(tmp_path):
    world = World(oracle=lambda view: {"diagnose_P1": "blocked"})
    s = session(world, tmp_path)
    assert "lip_variant" in s.unavailable_stages


# --- eligibility: attributed current baseline evidence --------------------------------------------
def _skipped_lip_run(tmp_path, blocking_pair):
    world = BarrierWorld(blocking_pair=blocking_pair)
    s = session(world, tmp_path)
    s.prepare()
    events = drive(s, approve=("lip_variant", "opening", "base_yaw"))
    return world, s, events


@pytest.mark.parametrize("pair_for_view", [
    lambda view: ("[Step 5C] DENTO Final Printable Template", "burr"),  # baseline blocked by something else
    lambda view: (),  # failure without any named contact: unknown, never assumed
])
def test_without_baseline_lip_slab_evidence_the_stage_is_skipped_untested_and_never_asked(tmp_path, pair_for_view):
    world, s, events = _skipped_lip_run(tmp_path, pair_for_view)
    lip = [r for r in s.records if r["stage"] == "lip_variant"]
    assert len(lip) == len(fa.LIP_VARIANTS) and all(r["result"] == fa.UNTESTED for r in lip)
    assert all("no attributed current baseline evidence" in r["reason"] for r in lip)
    assert not [e for e in events if e.kind == "gate" and e.stage == "lip_variant"]  # consent is not requested
    assert [g for g in s.gate_log if g["stage"] == "lip_variant"] == []
    assert "barrier_set" not in world.calls and world.tuning == DEFAULTS


def test_lip_slab_contact_in_a_later_candidate_is_not_baseline_evidence(tmp_path):
    def pair(view):
        return (LIP, SPINDLE) if view["u"] != 0.0 else ("burr", "[Step 5C] DENTO Final Printable Template")

    world, s, events = _skipped_lip_run(tmp_path, pair)
    lip = [r for r in s.records if r["stage"] == "lip_variant"]
    assert lip and all(r["result"] == fa.UNTESTED for r in lip) and "barrier_set" not in world.calls


def test_evidence_helper_reads_only_recorded_contacts_and_attributes_them():
    record = {"sequence": 3, "state_key": "k", "evidence_dir": "d", "reused_from": "",
              "steps": {"corridor": {"pairs": [[LIP, "burr"]]},
                        "diagnose": {"pairs": [], "raw": {"rows": [{"check": "p1_route", "blocking_pairs": [[SPINDLE, LIP]]}]}}}}
    found = fa.lip_slab_blocker_evidence(record)
    assert [(e["step"], e["sequence"]) for e in found] == [("corridor", 3), ("diagnose:p1_route", 3)]
    assert fa.lip_slab_blocker_evidence({"steps": {"preentry": {"pairs": [["burr", "FDI24"]]}}}) == []
    assert fa.lip_slab_blocker_evidence({"steps": {"diagnose": {"reason": "mentions the lip slab"}}}) == []  # text alone is not evidence
    assert fa.lip_slab_blocker_evidence(None) == [] and fa.lip_slab_blocker_evidence({}) == []
