import json
import os
import tempfile
import types
import unittest
from pathlib import Path

from Testing import step6_historical_record_probe as probe


JOINT_NAMES = ("J1", "J2", "J3", "J4", "J5")
qt = types.SimpleNamespace(QFileDialog=object(), QThread=None)


class _Plan:
    success = True
    task_fingerprint = "task-fingerprint"
    waypoint_phases = ("Approach",)


class _Facade:
    motionPlan = _Plan()
    currentPreviewPhase = ""
    previewActive = False
    _guarded_preview_active = False
    previewIndex = 0
    returnHomeRequired = False


class _Selector:
    def __init__(self):
        self.currentIndex = -1

    def setCurrentIndex(self, value):
        self.currentIndex = int(value)


class _EventList:
    def __init__(self):
        self.currentRow = -1

    def setCurrentRow(self, value):
        self.currentRow = int(value)


class _StatusLabel:
    def __init__(self):
        self.state = ""

    def property(self, name):
        return self.state if name == "dentobotState" else None

    def setProperty(self, name, value):
        if name == "dentobotState":
            self.state = value


class _EventDetails:
    def __init__(self):
        self.value = ""

    def setPlainText(self, value):
        self.value = str(value)

    def toPlainText(self):
        return self.value


class _Panel:
    def __init__(self):
        self._manualJogAcceptedJointPositionsSi = dict(zip(JOINT_NAMES, (0, 1, 2, 3, 4)))
        self._manualSimulationRecords = ()
        self.manualSimulationRecordComboBox = _Selector()
        self.manualSimulationEventList = _EventList()
        self.manualRecordImportStatusLabel = _StatusLabel()
        self.manualSimulationEventDetailsText = _EventDetails()

    def setManualSimulationRecords(self, records):
        self._manualSimulationRecords = tuple(records)
        self.manualRecordImportStatusLabel.setProperty("dentobotState", "ok")
        self.manualSimulationRecordComboBox.setCurrentIndex(0 if records else -1)
        row = 0 if records and records[0]["events"] else -1
        self.manualSimulationEventList.setCurrentRow(row)
        if row >= 0:
            self._show_event(row)

    def _stepManualSimulationEvent(self, step):
        record_index = self.manualSimulationRecordComboBox.currentIndex
        if record_index < 0:
            return
        count = len(self._manualSimulationRecords[record_index]["events"])
        if count:
            row = min(count - 1, max(0, self.manualSimulationEventList.currentRow + int(step)))
            self.manualSimulationEventList.setCurrentRow(row)
            self._show_event(row)

    def _show_event(self, row):
        count = len(self._manualSimulationRecords[self.manualSimulationRecordComboBox.currentIndex]["events"])
        self.manualSimulationEventDetailsText.setPlainText(
            "Historical event {} of {}\nStep-through selection only; no motion, guard, FK, or preview call.".format(
                row + 1, count
            )
        )


class _SlicerApp:
    def thread(self):
        return "ui-thread"


slicer = types.SimpleNamespace(app=_SlicerApp())
qt.QThread = types.SimpleNamespace(currentThread=lambda: "ui-thread")


def _record(events=None):
    return {
        "schema_version": "1.0",
        "record_status": "historical_display_only",
        "record_fingerprint": "fingerprint-001",
        "identity": {"task_fingerprint": "task-001", "prepared_branch_id": "branch-001"},
        "events": list(events if events is not None else (
            {"kind": "guard_accepted", "monotonic_ns": 100, "tcp_point_ras_mm": [1.0, 2.0, 3.0]},
            {"kind": "diagnostic", "monotonic_ns": 200},
        )),
    }


class _Widget:
    def __init__(self, panel, record=None):
        self._robotSimulationPanel = panel
        self._robotWorkflowFacade = _Facade()
        self.record = _record() if record is None else record

    def _onStep6ExportManualRecord(self):
        destination = qt.QFileDialog.getSaveFileName(None, "", "", "")
        json_path = Path(destination)
        json_path.write_text(json.dumps(self.record if isinstance(self.record, list) else [self.record]), encoding="utf-8")
        json_path.with_suffix(".report.txt").write_text("Readable record report\n", encoding="utf-8")

    def _onStep6ImportManualRecord(self):
        source = qt.QFileDialog.getOpenFileName(None, "", "", "")
        self._robotSimulationPanel.setManualSimulationRecords(
            json.loads(Path(source).read_text(encoding="utf-8"))
        )


class HistoricalRecordProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temp.name) / "run"
        self.run_dir.mkdir(mode=0o700)
        self.old_dialogs = qt.QFileDialog
        qt.QFileDialog = object()

    def tearDown(self):
        qt.QFileDialog = self.old_dialogs
        self.temp.cleanup()

    def _run(self, record=None, capture=None):
        panel = _Panel()
        widget = _Widget(panel, record)
        stages = []

        def capture_stage(stage):
            stages.append(stage)
            if capture:
                return capture(stage, panel, widget._robotWorkflowFacade)
            return stage + ".png"

        result = probe.run_step6_historical_record_probe(
            widget, panel, self.run_dir, capture_stage
        )
        return result, stages, panel, widget

    def test_complete_export_reopen_and_event_step(self):
        original_dialogs = qt.QFileDialog
        result, stages, panel, _widget = self._run()

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["record"]["schema_fingerprint"], "fingerprint-001")
        self.assertEqual(result["record"]["event_order"], [
            {"index": 0, "kind": "guard_accepted", "monotonic_ns": 100},
            {"index": 1, "kind": "diagnostic", "monotonic_ns": 200},
        ])
        self.assertEqual(result["replay"]["event_index"], 0)
        self.assertTrue(result["accepted_j1_j5"]["unchanged"])
        self.assertTrue(result["route_preview_authority"]["unchanged"])
        self.assertEqual(stages, ["before_export", "after_export", "after_import", "after_event_step"])
        self.assertIs(qt.QFileDialog, original_dialogs)
        self.assertTrue(Path(result["record_json"]).is_file())
        self.assertTrue(Path(result["record_report"]).is_file())
        self.assertEqual(panel.manualSimulationEventList.currentRow, 0)

    def test_no_event_bearing_record_fails_closed_and_restores_dialogs(self):
        original_dialogs = qt.QFileDialog
        with self.assertRaisesRegex(probe.HistoricalRecordProbeError, "no manual record with a TCP sample"):
            self._run(_record(events=[]))
        self.assertIs(qt.QFileDialog, original_dialogs)

    def test_selects_jog_record_after_task_home_record_without_tcp(self):
        review = _record(events=[{"kind": "accept_task_home", "monotonic_ns": 50}])
        review["record_fingerprint"] = "review-only"
        result, _, panel, _ = self._run([review, _record()])
        self.assertEqual(result["record"]["schema_fingerprint"], "fingerprint-001")
        self.assertEqual(panel.manualSimulationRecordComboBox.currentIndex, 1)

    def test_accepted_joint_change_fails_closed(self):
        def mutate(stage, panel, _facade):
            if stage == "after_import":
                panel._manualJogAcceptedJointPositionsSi["J1"] = 99.0

        with self.assertRaisesRegex(probe.HistoricalRecordProbeError, "changed accepted"):
            self._run(capture=mutate)

    def test_route_or_preview_authority_change_fails_closed(self):
        def mutate(stage, _panel, facade):
            if stage == "after_import":
                facade.previewActive = True

        with self.assertRaisesRegex(probe.HistoricalRecordProbeError, "changed route/preview"):
            self._run(capture=mutate)

    def test_refuses_symlink_run_directory_before_owner_calls(self):
        link = Path(self.temp.name) / "run-link"
        link.symlink_to(self.run_dir, target_is_directory=True)
        panel = _Panel()
        widget = _Widget(panel)
        with self.assertRaisesRegex(probe.HistoricalRecordProbeError, "symlink"):
            probe.run_step6_historical_record_probe(widget, panel, link, lambda _stage: None)

    def test_refuses_overwrite(self):
        (self.run_dir / "step6-manual-record-probe.json").write_text("existing", encoding="utf-8")
        panel = _Panel()
        widget = _Widget(panel)
        with self.assertRaisesRegex(probe.HistoricalRecordProbeError, "overwrite"):
            probe.run_step6_historical_record_probe(widget, panel, self.run_dir, lambda _stage: None)


if __name__ == "__main__":
    unittest.main()
