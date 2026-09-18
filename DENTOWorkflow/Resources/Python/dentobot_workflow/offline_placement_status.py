"""Pure classifier for the shared Step 3B / 6.1 offline-placement mirror."""

from __future__ import annotations

PLACEMENT_MIRROR_PASS = "pass"
PLACEMENT_MIRROR_MANUAL = "manual"
PLACEMENT_MIRROR_MISSING = "missing"
VIRTUAL_FOREHEAD_AUTHORITY = "VirtualForeheadPriorV1"
EXPECTED_ROBOT_LINK_COUNT = 7


def classify_offline_base_placement(
    *,
    pose_eligible: bool,
    robot_link_count: int,
    placement_authority: str,
    base_case_fingerprint: str,
    pose_fingerprint: str,
) -> str:
    """Classify auto-placement for the 3B / 6.1 mirror banner.

    ``pass`` is only VirtualForeheadPriorV1 whose Case Foundation fingerprint
    still matches. Seven loaded links without that prior are ``manual``.
    Missing pose, robot, or prior is ``missing`` (do not auto-propose).
    """

    if not pose_eligible or int(robot_link_count) != EXPECTED_ROBOT_LINK_COUNT:
        return PLACEMENT_MIRROR_MISSING
    authority = str(placement_authority or "").strip()
    base_fp = str(base_case_fingerprint or "").strip()
    pose_fp = str(pose_fingerprint or "").strip()
    if (
        authority == VIRTUAL_FOREHEAD_AUTHORITY
        and base_fp
        and pose_fp
        and base_fp == pose_fp
    ):
        return PLACEMENT_MIRROR_PASS
    if authority or int(robot_link_count) == EXPECTED_ROBOT_LINK_COUNT:
        return PLACEMENT_MIRROR_MANUAL
    return PLACEMENT_MIRROR_MISSING
