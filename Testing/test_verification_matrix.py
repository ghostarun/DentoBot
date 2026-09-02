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
        }:
            assert not check["parallel_safe"]
            assert check["resources"]
    for profile in matrix["profiles"].values():
        assert set(profile) <= set(by_id)

