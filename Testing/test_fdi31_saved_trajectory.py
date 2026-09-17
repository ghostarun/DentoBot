"""Pure checks for the opt-in 15-Sep FDI31 trajectory parser."""

import ast
import hashlib
import json
from pathlib import Path
import math
import zipfile

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPOSITORY_ROOT / "Testing" / "run_dentobot_stage6_target_generation.py"
ARCHIVE = (
    REPOSITORY_ROOT.parents[2]
    / "data/Slicer_Saved/SampleStudy1/FDI31/2026-09-15-Scene.mrb"
)


def _load_parser():
    source = ast.parse(RUNNER.read_text(encoding="utf-8"))
    selected = []
    names = {
        "require",
        "_parse_saved_fdi31_trajectory",
        "SAVED_FDI31_TRAJECTORY_MEMBER",
        "SAVED_FDI31_TRAJECTORY_MEMBER_SHA256",
        "SAVED_FDI31_TRAJECTORY_LENGTH_MM",
        "SAVED_FDI31_TRAJECTORY_FLOAT_TOLERANCE_MM",
    }
    for node in source.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            selected.append(node)
            continue
        if isinstance(node, ast.Assign):
            targets = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if targets & names:
                selected.append(node)
    namespace = {
        "Path": Path,
        "hashlib": hashlib,
        "json": json,
        "math": math,
        "zipfile": zipfile,
    }
    exec(compile(ast.fix_missing_locations(ast.Module(selected, [])), str(RUNNER), "exec"), namespace)
    return namespace["_parse_saved_fdi31_trajectory"], namespace


def _member_bytes() -> bytes:
    parser, namespace = _load_parser()
    with zipfile.ZipFile(ARCHIVE) as archive:
        return archive.read(namespace["SAVED_FDI31_TRAJECTORY_MEMBER"])


def _archive_with_member(tmp_path: Path, member_bytes: bytes) -> Path:
    _parser, namespace = _load_parser()
    path = tmp_path / "saved-scene.mrb"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(namespace["SAVED_FDI31_TRAJECTORY_MEMBER"], member_bytes)
    return path


def test_saved_fdi31_parser_converts_lps_to_ras_once(tmp_path: Path) -> None:
    parser, namespace = _load_parser()
    result = parser(_archive_with_member(tmp_path, _member_bytes()))

    assert result["entry_ras_mm"] == [
        -95.06119545332044,
        -36.948910276519285,
        55.86918917410314,
    ]
    assert result["target_ras_mm"] == [
        -94.63312182009788,
        -38.39889044842043,
        50.85265351160811,
    ]
    assert result["saved_length_mm"] == pytest.approx(5.239400689721231, abs=1.0e-12)
    assert result["source_member_sha256"] == namespace["SAVED_FDI31_TRAJECTORY_MEMBER_SHA256"]


def test_saved_fdi31_parser_rejects_undefined_control_point(tmp_path: Path) -> None:
    parser, _namespace = _load_parser()
    document = json.loads(_member_bytes())
    document["markups"][0]["controlPoints"][0]["positionStatus"] = "undefined"
    with pytest.raises(RuntimeError, match="control point must be defined"):
        parser(_archive_with_member(tmp_path, json.dumps(document).encode("utf-8")))


def test_saved_fdi31_parser_rejects_length_mismatch(tmp_path: Path) -> None:
    parser, _namespace = _load_parser()
    document = json.loads(_member_bytes())
    document["markups"][0]["measurements"][0]["value"] = 5.0
    with pytest.raises(RuntimeError, match="measured length does not match"):
        parser(_archive_with_member(tmp_path, json.dumps(document).encode("utf-8")))


def test_runner_opt_in_branch_records_saved_provenance_and_one_mm_dock_bore() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert 'SAVED_FDI31_TRAJECTORY_ARCHIVE_ENV = "DENTOBOT_STAGE6_FDI31_TRAJECTORY_MRB"' in source
    assert '"targetDockingBoreDiameterMm": 1.0' in source
    assert '"DENTOBOT.TrajectoryCreationMethod", "SavedStep4A15Sept"' in source
    assert "logic.createTrajectoryNode" in source
    assert "logic.configureTrajectoryTarget" in source
    assert "logic.getTargetPulpAssociation" in source
    saved_branch = source.split("if saved_trajectory is not None:", 1)[1].split("    else:", 1)[0]
    assert saved_branch.index("trajectory.SetLocked(False)") < saved_branch.index(
        "trajectory.AddControlPointWorld"
    )
    assert "saved FDI31 trajectory points were not accepted" in saved_branch
    assert 'saved_trajectory["planning_coordinate_system"] = "OpenedCaseFoundationWorldRAS"' in saved_branch
    assert "entry_ras = _map_point(jaw_matrix, entry_ras)" in saved_branch
    assert "target_ras = _map_point(jaw_matrix, target_ras)" in saved_branch
    assert "logic.TARGET_BOUNDS_ROI_REFERENCE_ROLE, roi.GetID()" in saved_branch
    assert "saved FDI31 planning-frame trajectory leaves target bounds" in saved_branch
    assert "trajectory_summary = logic.getTrajectorySummary(trajectory)" in source
    assert source.index("trajectory_summary = logic.getTrajectorySummary(trajectory)") < source.index(
        "trajectory.SetLocked(True)"
    )
