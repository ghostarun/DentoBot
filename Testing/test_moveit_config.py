"""Static acceptance tests for the DENTOBOT MoveIt/frame contract."""

from pathlib import Path
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_urdf_has_provisional_tcp_after_burr():
    robot = ElementTree.parse(
        ROOT / "dentobot_description/urdf/dentobot.urdf"
    ).getroot()
    assert robot.find("link[@name='dentobot_tool_tcp']") is not None
    assert robot.find("link[@name='dentobot_drill_tip_provisional']") is not None
    joint = robot.find("joint[@name='burr_to_dentobot_tool_tcp']")
    assert joint is not None
    assert joint.get("type") == "fixed"
    assert joint.find("parent").get("link") == "burr"
    assert joint.find("child").get("link") == "dentobot_tool_tcp"


def test_srdf_group_is_base_to_tcp_chain_and_only_adjacent_pairs_are_disabled():
    robot = ElementTree.parse(
        ROOT / "dentobot_moveit_config/config/dentobot.srdf"
    ).getroot()
    chain = robot.find("group[@name='dentobot_arm']/chain")
    assert chain is not None
    assert chain.get("base_link") == "base_link"
    assert chain.get("tip_link") == "dentobot_drill_tip_provisional"
    for collision in robot.findall("disable_collisions"):
        assert collision.get("reason") == "Adjacent"


def test_ompl_and_conservative_joint_limits_are_configured():
    ompl = yaml.safe_load(
        (ROOT / "dentobot_moveit_config/config/ompl_planning.yaml").read_text()
    )
    assert ompl["planning_plugins"] == ["ompl_interface/OMPLPlanner"]
    assert "RRTConnectkConfigDefault" in ompl["dentobot_arm"]["planner_configs"]
    limits = yaml.safe_load(
        (ROOT / "dentobot_moveit_config/config/joint_limits.yaml").read_text()
    )["joint_limits"]
    assert set(limits) == {
        "link-1_Revolute-1",
        "link-2_Slider-2",
        "link-3_Revolute-3",
        "link-4_Slider-4",
        "link-5_Revolute-5",
        "pneumatic_spindle-Copy_Revolute-6",
    }
    assert limits["link-4_Slider-4"]["max_velocity"] == 0.02


def test_collision_guard_gates_raw_commands_before_joint_states():
    launch = (
        ROOT / "dentobot_moveit_config/launch/simulation.launch.py"
    ).read_text(encoding="utf-8")
    guard = (
        ROOT / "dentobot_moveit_config/src/collision_guard.cpp"
    ).read_text(encoding="utf-8")
    assert 'executable="collision_guard"' in launch
    assert '"minimum_clearance_m": 0.005' in launch
    assert '"command_topic": "/dentobot/validated_joint_positions"' in launch
    assert "distanceSelf" in guard
    assert "distanceRobot" in guard
    assert "start.interpolate" in guard
    assert "maximum_prismatic_step_m" in guard
    assert "pad_self_collisions = false" in guard


def test_collision_guard_has_fingerprinted_simulation_phase_channel():
    launch = (
        ROOT / "dentobot_moveit_config/launch/simulation.launch.py"
    ).read_text(encoding="utf-8")
    guard = (
        ROOT / "dentobot_moveit_config/src/collision_guard.cpp"
    ).read_text(encoding="utf-8")
    for topic in (
        "/dentobot/task_guard_config",
        "/dentobot/task_joint_command",
        "/dentobot/task_joint_status",
    ):
        assert topic in launch
    assert "dentobot.task_guard_config.v1" in guard
    assert "dentobot.task_joint_command.v1" in guard
    assert "dentobot.task_joint_status.v1" in guard
    assert "Command task fingerprint does not match" in guard
    assert "only_allowed_target_contact" in guard
    assert "left the approved Entry-to-Target corridor" in guard
    assert "overshot or preceded" in guard
    assert "satisfiesBounds" in guard
    assert "distanceSelf" in guard
    assert "distanceRobot" in guard


def test_ik_is_runtime_urdf_srdf_kdl_not_hard_coded():
    kinematics = yaml.safe_load(
        (ROOT / "dentobot_moveit_config/config/kinematics.yaml").read_text()
    )
    assert kinematics["dentobot_arm"]["kinematics_solver"] == (
        "kdl_kinematics_plugin/KDLKinematicsPlugin"
    )
    guard = (ROOT / "dentobot_moveit_config/src/collision_guard.cpp").read_text()
    assert 'getJointModelGroup(group_name_)' in guard
    assert "getVariableNames()" in guard
