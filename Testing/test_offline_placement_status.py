"""Unit tests for the Step 3B / 6.1 offline-placement mirror classifier."""

from __future__ import annotations

from dentobot_workflow.offline_placement_status import (
    PLACEMENT_MIRROR_MANUAL,
    PLACEMENT_MIRROR_MISSING,
    PLACEMENT_MIRROR_PASS,
    VIRTUAL_FOREHEAD_AUTHORITY,
    classify_offline_base_placement,
)


def test_pass_requires_matching_virtual_forehead_fingerprint() -> None:
    assert (
        classify_offline_base_placement(
            pose_eligible=True,
            robot_link_count=7,
            placement_authority=VIRTUAL_FOREHEAD_AUTHORITY,
            base_case_fingerprint="abc",
            pose_fingerprint="abc",
        )
        == PLACEMENT_MIRROR_PASS
    )


def test_fingerprint_mismatch_is_not_auto_pass() -> None:
    assert (
        classify_offline_base_placement(
            pose_eligible=True,
            robot_link_count=7,
            placement_authority=VIRTUAL_FOREHEAD_AUTHORITY,
            base_case_fingerprint="old",
            pose_fingerprint="new",
        )
        == PLACEMENT_MIRROR_MANUAL
    )


def test_manual_nudge_authority_is_manual_not_missing() -> None:
    assert (
        classify_offline_base_placement(
            pose_eligible=True,
            robot_link_count=7,
            placement_authority="ManualSimulationBaseUnreviewed",
            base_case_fingerprint="abc",
            pose_fingerprint="abc",
        )
        == PLACEMENT_MIRROR_MANUAL
    )


def test_skipped_3b_without_robot_is_missing() -> None:
    assert (
        classify_offline_base_placement(
            pose_eligible=True,
            robot_link_count=0,
            placement_authority="",
            base_case_fingerprint="",
            pose_fingerprint="abc",
        )
        == PLACEMENT_MIRROR_MISSING
    )


def test_ineligible_pose_is_missing_even_with_prior() -> None:
    assert (
        classify_offline_base_placement(
            pose_eligible=False,
            robot_link_count=7,
            placement_authority=VIRTUAL_FOREHEAD_AUTHORITY,
            base_case_fingerprint="abc",
            pose_fingerprint="abc",
        )
        == PLACEMENT_MIRROR_MISSING
    )
