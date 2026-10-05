"""Standard Step 6 case evidence package (operator request 2026-10-05).

Every planning case run (failure or success) captures the same set so cases can
be compared and presented side by side:

* ``summary.json`` / ``summary.md`` - case conditions, Diagnose This Base
  verdict, cause class, blocking pairs, approach corridor, drilling depth;
* ``diagnosis.png`` - the Diagnose This Base window;
* ``view-*.png`` - the 3D viewport from fixed patient-frame angles (anterior,
  right lateral, superior/occlusal) plus a close-up along the drill axis;
* ``pose-<pose>-<view>.png`` - the display-only goal ("ghost") robot placed at
  PreEntry, Entry and the drilling end (effective Target when shortened), and
  at the first invalid state of a failed stage, each from anterior, right
  lateral and drill-axis close-up.

Read-only: the camera is restored afterwards; no scene, Base, Home, guard or
planner state is changed except running the existing Diagnose This Base.
Simulation evidence only. Runs inside Slicer (session driver namespace).
"""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

# Patient RAS camera offsets (mm) and view-up vectors.
WIDE_DISTANCE_MM = 420.0
CLOSE_DISTANCE_MM = 95.0
VIEWS = (
    ("anterior", (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    ("right-lateral", (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    ("superior", (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
)
_CORRIDOR = re.compile(r"approach point ([0-9.]+) mm out")


def _matrix(transform_node):
    import vtk

    matrix = vtk.vtkMatrix4x4()
    transform_node.GetMatrixTransformToWorld(matrix)
    return [[matrix.GetElement(r, c) for c in range(4)] for r in range(4)]


def _unit(vector):
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return tuple(v / norm for v in vector)


def _robot_models(role="goal_model"):
    try:
        import DENTOROS2Bridge as bridge

        robot = bridge.find_ros2_robot_by_name(bridge.ROS2_ROBOT_NAME)
    except Exception:
        return []
    if robot is None:
        return []
    return [robot.GetNthNodeReference(role, i) for i in range(robot.GetNumberOfNodeReferences(role))]


def _goal_models():
    return _robot_models("goal_model")


def _goal_display_state():
    import DENTOROS2Bridge as bridge

    state = []
    for model in _goal_models():
        display = model.GetDisplayNode() if model is not None else None
        if display is not None:
            state.append((model, display.GetVisibility(), display.GetOpacity(),
                          model.GetAttribute(bridge.ROS2_MOTION_DIAGNOSTIC_GOAL_ATTRIBUTE)))
    return state


def _restore_goal_display(state):
    import DENTOROS2Bridge as bridge

    for model, visibility, opacity, attribute in state:
        display = model.GetDisplayNode()
        display.SetVisibility(visibility)
        display.SetOpacity(opacity)
        if attribute is None:
            model.RemoveAttribute(bridge.ROS2_MOTION_DIAGNOSTIC_GOAL_ATTRIBUTE)
        else:
            model.SetAttribute(bridge.ROS2_MOTION_DIAGNOSTIC_GOAL_ATTRIBUTE, attribute)


def corridor_mm_from_rows(rows) -> float | None:
    for row in rows or ():
        match = _CORRIDOR.search(str(row.get("detail", "")))
        if match:
            return float(match.group(1))
    return None


def drilling_from_rows(rows) -> dict | None:
    for row in rows or ():
        detail = str(row.get("detail", ""))
        match = re.search(r"([0-9.]+) of ([0-9.]+) mm reached; ([0-9.]+) mm not completed", detail)
        if match:
            return {
                "completed_mm": float(match.group(1)),
                "requested_mm": float(match.group(2)),
                "remaining_mm": float(match.group(3)),
            }
    return None


POSE_VIEWS = ("anterior", "right-lateral", "drill-axis-closeup")
POSE_GHOST_OPACITY = 0.85  # display only; restored after capture


def pose_states(chain, outcomes) -> dict:
    """Joint states to show: stage ends that passed, then failed stages' first invalid state."""
    poses = {}
    stages = (chain or {}).get("stages") if isinstance(chain, dict) else None
    for phase_id, name in (("P1", "preentry"), ("P2", "entry"), ("P3", "drilling-end")):
        end = (stages or {}).get(phase_id, {}).get("end") if isinstance(stages, dict) else None
        if isinstance(end, dict) and end:
            poses[name] = dict(end)
    for phase_id, outcome in (outcomes or {}).items():
        if not isinstance(outcome, dict) or outcome.get("diagnostic_status") == "passed":
            continue
        evidence = outcome.get("endpoint_evidence") or {}
        state = (evidence.get("first_invalid_requested_state") or {}).get("state")
        if isinstance(state, dict) and state:
            poses[f"first-invalid-{phase_id.lower()}"] = dict(state)
    return poses


def summary_markdown(summary: dict) -> str:
    c = summary["conditions"]
    d = summary["diagnosis"] or {}
    lines = [
        f"# {summary['label']}",
        "",
        f"Captured {summary['captured_utc']} · SIMULATION ONLY",
        "",
        "| Condition | Value |",
        "|---|---|",
        f"| Incisor gap (target / achieved) | {c['target_gap_mm']} mm / {c.get('opening_status', '')} |",
        f"| Spindle-housing ↔ template allowance | {'ON' if c['allow_spindle_guide_contact'] else 'OFF'} |",
        f"| Planner | {c['policy']} |",
        f"| Base origin (RAS mm) | {c['base_origin_ras_mm']} |",
        f"| Base rotation row 0 | {c['base_rotation_row0']} |",
        f"| Template verification | {c['template_state']} |",
        f"| Collision audit | {c['collision_audit'][:12]} |",
        "",
        f"**Diagnose This Base:** {d.get('status', 'NOT RUN')} — cause class "
        f"`{d.get('cause_class') or '-'}`",
        "",
        f"> {d.get('verdict', '')}",
        "",
        "| Check | Result | Cause class | Detail |",
        "|---|---|---|---|",
    ]
    for row in d.get("rows") or ():
        detail = str(row.get("detail", "")).replace("|", "/")[:220]
        lines.append(f"| {row['title']} | {row['status']} | {row.get('cause_class') or ''} | {detail} |")
    lines += [
        "",
        f"**Approach corridor:** {summary['corridor_mm']} mm · **Drilling:** {summary['drilling']}",
        f"**Blocking pairs:** {summary['blocking_pairs'] or 'none'}",
        f"**Suggested levers:** {d.get('suggested_levers') or 'none'}",
        f"**Poses shown (ghost robot):** {', '.join(summary.get('poses') or []) or 'none'}",
        "",
    ]
    for name in summary["images"]:
        lines.append(f"![{name}]({name})")
    return "\n".join(lines) + "\n"


def capture_case_evidence(namespace: dict, out_dir, label: str, *, run_diagnose: bool = True) -> dict:
    """Capture the standard evidence set for the current case state."""
    import slicer

    widget = namespace["widget"]
    panel = namespace["panel"]
    facade = namespace["facade"]
    logic = namespace["logic"]
    parameter_node = namespace["parameter_node"]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    images = []

    started = time.monotonic()
    if run_diagnose:
        panel.checkPreEntryIKButton.click()
        slicer.app.processEvents()
        panel.diagnoseBaseButton.click()
        deadline = time.monotonic() + 1200
        while getattr(widget, "_workflowActionBusy", False) and time.monotonic() < deadline:
            slicer.app.processEvents()
            time.sleep(0.05)
        for _ in range(10):
            slicer.app.processEvents()
            time.sleep(0.05)
    diagnosis = getattr(facade, "_last_base_diagnosis", None)
    dialog = getattr(panel, "_baseDiagnosisDialog", None)
    if dialog is not None and dialog.visible:
        dialog.grab().save(str(out / "diagnosis.png"))
        images.append("diagnosis.png")
        dialog.hide()

    snapshot = logic.confirmedTaskRecord(parameter_node)
    focal = tuple(snapshot.entry_ras_mm) if snapshot is not None else (0.0, 0.0, 0.0)
    target = tuple(snapshot.target_ras_mm) if snapshot is not None else focal
    axis = _unit(tuple(e - t for e, t in zip(focal, target)))

    view = slicer.app.layoutManager().threeDWidget(0)
    camera_node = slicer.modules.cameras.logic().GetViewActiveCameraNode(view.mrmlViewNode())
    camera = camera_node.GetCamera()
    saved = (camera.GetPosition(), camera.GetFocalPoint(), camera.GetViewUp())
    shots = [(name, direction, up, WIDE_DISTANCE_MM) for name, direction, up in VIEWS]
    shots.append(("drill-axis-closeup", axis, (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (0.0, 1.0, 0.0), CLOSE_DISTANCE_MM))

    def shoot(prefix, selected):
        for name, direction, up, distance in shots:
            if selected and name not in selected:
                continue
            camera.SetFocalPoint(*focal)
            camera.SetPosition(*(f + distance * d for f, d in zip(focal, direction)))
            camera.SetViewUp(*up)
            camera.OrthogonalizeViewUp()
            camera_node.ResetClippingRange()
            view.threeDView().forceRender()
            slicer.app.processEvents()
            filename = f"{prefix}-{name}.png"
            view.grab().save(str(out / filename))
            images.append(filename)

    bridge = facade._bridge
    poses = pose_states(
        getattr(facade, "_step6_stage_diagnostic_chain", None),
        getattr(facade, "_last_base_diagnosis_stage_outcomes", None),
    )
    shown = []
    goal_display = _goal_display_state()
    real_visibility = [
        (model, model.GetDisplayNode().GetVisibility())
        for model in _robot_models("model")
        if model is not None and model.GetDisplayNode() is not None
    ]
    try:
        shoot("view", ())
        for pose, state in poses.items():
            ok, _message = bridge.show_goal_robot_joint_positions(state, diagnostic=True)
            if ok:
                # The accepted robot stays where it is; hide it only so the ghost
                # pose is not occluded in the picture (restored below).
                for model, _visible in real_visibility:
                    model.GetDisplayNode().SetVisibility(False)
                for model in _goal_models():
                    if model is not None and model.GetDisplayNode() is not None:
                        model.GetDisplayNode().SetOpacity(POSE_GHOST_OPACITY)
                slicer.app.processEvents()
                shown.append(pose)
                shoot(f"pose-{pose}", POSE_VIEWS)
    finally:
        _restore_goal_display(goal_display)
        for model, visible in real_visibility:
            model.GetDisplayNode().SetVisibility(visible)
        camera.SetPosition(*saved[0])
        camera.SetFocalPoint(*saved[1])
        camera.SetViewUp(*saved[2])
        camera_node.ResetClippingRange()
        view.threeDView().forceRender()
    slicer.util.mainWindow().grab().save(str(out / "window.png"))
    images.append("window.png")

    base = _matrix(parameter_node.robotBaseTransform)
    audit = logic.collisionSceneAuditRecord(parameter_node)
    template = parameter_node.finalPrintableTemplateModel
    rows = list((diagnosis or {}).get("rows") or ())
    summary = {
        "label": label,
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_sec": round(time.monotonic() - started, 1),
        "conditions": {
            "target_gap_mm": float(parameter_node.step6CaseJawTargetGapMm),
            "opening_status": str(widget.ui.step6CaseJawOpeningStatusLabel.text)[:160],
            "allow_spindle_guide_contact": bool(parameter_node.step6AllowSpindleGuideContact),
            "policy": panel.planningPolicy(),
            "base_origin_ras_mm": [round(base[r][3], 3) for r in range(3)],
            "base_rotation_row0": [round(v, 5) for v in base[0][:3]],
            "template_state": template.GetAttribute("DENTOBOT.VerificationState") if template else None,
            "collision_audit": str(audit.audit_fingerprint) if audit is not None else "",
            "task_entry_ras_mm": list(focal),
            "task_target_ras_mm": list(target),
        },
        "diagnosis": diagnosis,
        "corridor_mm": corridor_mm_from_rows(rows),
        "drilling": drilling_from_rows(rows),
        "blocking_pairs": [
            f"{p['bodies'][0]} ↔ {p['bodies'][1]} ({p['cause_class']}, {p['tool_part']})"
            for p in (diagnosis or {}).get("blocking_pairs") or ()
        ],
        "poses": shown,
        "pose_joint_positions_si": {name: poses[name] for name in shown},
        "images": images,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (out / "summary.md").write_text(summary_markdown(summary), encoding="utf-8")
    return summary
