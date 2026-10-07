"""Pure contract check for the shared agentic verification matrix."""

import json
from pathlib import Path


def test_verification_matrix_references_are_closed_and_runtime_is_exclusive():
    matrix = json.loads(
        (Path(__file__).with_name("verification_matrix.json")).read_text(
            encoding="utf-8"
        )
    )
    checks = matrix["checks"]
    by_id = {check["id"]: check for check in checks}
    assert len(by_id) == len(checks)
    assert matrix["schema_version"] == "1.0"
    for check in checks:
        assert set(check["depends_on"]) <= set(by_id)
        if check["execution_kind"] in {
            "slicer_headless",
            "slicer_ros_moveit",
            "ros_python",
            "container_colcon",
            "slicer_ros_moveit_headed",
        }:
            assert not check["parallel_safe"]
            assert check["resources"]
    for profile in matrix["profiles"].values():
        assert set(profile) <= set(by_id)



def test_frame_sync_runtime_keeps_pure_dependency_and_explicit_resource_gate():
    matrix = json.loads(Path(__file__).with_name("verification_matrix.json").read_text())
    checks = {check["id"]: check for check in matrix["checks"]}
    runtime = checks["runtime.step6_frame_sync"]
    assert runtime["approval"] == "explicit_runtime_approval"
    assert not runtime["parallel_safe"]
    assert set(runtime["resources"]) == {
        "docker:dentobot-slicerros2", "ros_domain:73", "slicer_process", "mrml_scene", "display"
    }
    assert "pure.frame_sync" in runtime["depends_on"]
    pure = checks["pure.frame_sync"]
    assert pure["execution_kind"] == "container_pytest"
    assert pure["parallel_safe"] and pure["resources"] == []
    # Prevent the profile becoming a runtime-only shortcut around isolated checks.
    profile = matrix["profiles"]["step6-frame-sync"]
    assert profile.index("pure.frame_sync") < profile.index("runtime.step6_frame_sync")
