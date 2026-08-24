"""Pure graph-contract tests for the external status publisher."""

import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "dentobot_description/scripts/simulation_status_publisher.py"
)
SPEC = importlib.util.spec_from_file_location("simulation_status_publisher", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_graph_name_normalization():
    assert MODULE.normalized_graph_names(
        [("move_group", "/"), ("worker", "/dentobot")]
    ) == {"/move_group", "/dentobot/worker"}


def test_ready_requires_nodes_service_and_exactly_one_joint_publisher():
    assert MODULE.REQUIRED_PLANNING_SERVICES == {
        "/check_state_validity",
        "/compute_cartesian_path",
        "/compute_ik",
    }
    status = MODULE.build_status(
        node_names=set(MODULE.REQUIRED_DESCRIPTION_NODES | MODULE.REQUIRED_PLANNING_NODES),
        service_names=set(MODULE.REQUIRED_PLANNING_SERVICES),
        joint_state_publishers=1,
    )
    assert status["ready"] is True
    duplicate = MODULE.build_status(
        node_names=set(MODULE.REQUIRED_DESCRIPTION_NODES | MODULE.REQUIRED_PLANNING_NODES),
        service_names=set(MODULE.REQUIRED_PLANNING_SERVICES),
        joint_state_publishers=2,
    )
    assert duplicate["ready"] is False
    assert "exactly one" in duplicate["reason"]
