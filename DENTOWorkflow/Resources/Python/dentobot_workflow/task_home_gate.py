"""Explain why the 6.2 Task Home actions are unavailable (pure, no Slicer/Qt).

The widget enables Review / Accept / Plan + Apply from many independent
conditions. This module turns the same inputs into ordered, operator-readable
blockers so a disabled button always says what to do next. Rule: an action that
is disabled never has an empty explanation; when no named cause matches, a
generic line that carries the raw state is returned so the gap is visible and
reportable instead of a silent grey button.
"""

from __future__ import annotations

from collections.abc import Mapping

ACTIONS = ("review", "accept", "apply")
_ALLOWED_STATUSES = {
    "offline": {"review", "accepted", "rejected", "configuration_saved"},
    "connected": {"review", "accepted", "rejected"},
}


def _runtime_blockers(context: Mapping) -> list[str]:
    blockers: list[str] = []
    issues = [str(issue) for issue in (context.get("scene_issues") or ()) if issue]
    if issues:
        blockers.append("Case scene is not ready: " + " ".join(issues))
    elif not context.get("scene_prepared"):
        blockers.append("Prepare the case scene: complete Case Foundation / Open Mouth Setup.")
    if not context.get("robot_present"):
        blockers.append("Load the robot in 6.1.")
    if not context.get("base_locked"):
        blockers.append("Accept and lock the Base in 6.1.")
    if not context.get("ros2_active"):
        blockers.append("Connect ROS + MoveIt in 6.1.")
    if context.get("preview_running") or context.get("preview_active"):
        blockers.append("A motion preview is active; stop it first.")
    if context.get("away_from_home"):
        blockers.append(
            "The robot is flagged away from Home or has an incomplete preview; "
            "use Return Home or resolve the interrupted preview."
        )
    return blockers


def _busy_blockers(context: Mapping) -> list[str]:
    """Apply in every setup mode, including offline."""

    blockers: list[str] = []
    if context.get("action_busy"):
        blockers.append("Another Step 6 action is still running; wait for it to finish.")
    if context.get("unresolved_jog"):
        blockers.append(
            "A guarded jog outcome is unresolved; use Reconcile in 6.3 Manual."
        )
    return blockers


def _review_blockers(context: Mapping, details: Mapping, success: bool, message: str) -> list[str]:
    mode = str(details.get("setupMode") or "unknown")
    identity = str(details.get("identityStatus") or "unknown")
    status = str(details.get("acceptanceStatus") or "unknown")
    blockers: list[str] = _busy_blockers(context)
    if mode == "offline":
        if not context.get("offline_edit_ready"):
            blockers.append(
                "The offline Home draft is not editable yet: the saved placement "
                "identity must be current and the draft within mechanical limits."
            )
    elif mode == "connected":
        blockers.extend(_runtime_blockers(context))
    else:
        blockers.append("Task Home setup mode is unknown; reload 6.1 or reconnect.")
        blockers.extend(_runtime_blockers(context))
    if details.get("acceptanceUncertainty"):
        blockers.append(
            "A previous Home save outcome is uncertain: " + str(details["acceptanceUncertainty"])
            + " Use Reconcile Task Home State."
        )
    if not success or identity != "current":
        reason = message or "no façade review is available"
        blockers.append(f"Home review is {identity}: {reason}")
    elif status not in _ALLOWED_STATUSES.get(mode, set()):
        blockers.append(f"Home review status is '{status}', which cannot start a review.")
    if details.get("staged") is True:
        blockers.append("A candidate is already staged; accept it or go Back to Edit.")
    return blockers


def task_home_action_blockers(
    context: Mapping, details: Mapping, success: bool, message: str, enabled: Mapping
) -> dict[str, tuple[str, ...]]:
    """Return blockers for each disabled action in ``ACTIONS`` (empty if enabled).

    ``enabled`` holds the widget's actual enable decision per action; the result
    is derived for exactly those that are disabled, never for enabled ones.
    """

    details = details if isinstance(details, Mapping) else {}
    result: dict[str, tuple[str, ...]] = {}
    for action in ACTIONS:
        if enabled.get(action):
            result[action] = ()
            continue
        review = _review_blockers(context, details, success, message)
        staged = details.get("staged") is True
        blockers: list[str] = []
        if action == "review":
            blockers = review
        elif action == "accept":
            if not staged:
                blockers.append("Review the draft first; there is no staged candidate to accept.")
            else:
                blockers.extend(b for b in review if not b.startswith("A candidate is already"))
                status = str(details.get("acceptanceStatus") or "unknown")
                if status != "review":
                    blockers.append(
                        f"The staged candidate is '{status}', not awaiting acceptance; "
                        "go Back to Edit and review the draft again."
                    )
                if (
                    str(details.get("setupMode")) == "connected"
                    and not context.get("candidate_matches_accepted")
                ):
                    blockers.append(
                        "The staged candidate differs from the accepted robot state; "
                        "run Plan + Apply Home Draft first."
                    )
        else:
            if not context.get("anatomy_ready"):
                issues = [str(i) for i in (context.get("anatomy_issues") or ()) if i]
                blockers.append(
                    "Planning anatomy is not ready: " + (" ".join(issues) or "complete Case Foundation.")
                )
            # Planning and applying always need the live scene, even in offline setup.
            blockers.extend(_runtime_blockers(context))
            blockers.extend(b for b in review if not b.startswith("A candidate is already"))
            if staged:
                if str(details.get("setupMode")) != "connected":
                    blockers.append(
                        "A staged offline candidate is only saved as configuration; "
                        "connect ROS + MoveIt in 6.1 and review the draft again to apply it."
                    )
                status = str(details.get("acceptanceStatus") or "unknown")
                if status != "review":
                    blockers.append(
                        f"The staged candidate is '{status}', not awaiting acceptance; "
                        "go Back to Edit and review the draft again."
                    )
                if not context.get("candidate_matches_draft"):
                    blockers.append(
                        "The staged candidate differs from the current J1–J5 draft; "
                        "go Back to Edit, then review the draft again."
                    )
            if not context.get("scene_synchronized"):
                blockers.append("Complete the planning-scene audit in 6.1 (scene not synchronized).")
            if not context.get("draft_within_limits"):
                blockers.append(
                    "The J1–J5 draft is outside the command limits: "
                    + (str(context.get("draft_limit_note") or "check the draft limit message."))
                )
        deduped = tuple(dict.fromkeys(blockers))
        if not deduped:
            deduped = (
                "Unavailable in the current state (no specific prerequisite matched): "
                f"mode={details.get('setupMode', 'unknown')}, "
                f"review={details.get('acceptanceStatus', 'unknown')}, "
                f"identity={details.get('identityStatus', 'unknown')}, "
                f"staged={bool(staged)}. Please report this state.",
            )
        result[action] = deduped
    return result


def format_blockers(blockers: Mapping[str, tuple[str, ...]], labels: Mapping[str, str]) -> str:
    """One compact paragraph: shared causes once, per-action leftovers after."""

    disabled = {a: b for a, b in blockers.items() if b}
    if not disabled:
        return ""
    shared = [line for line in next(iter(disabled.values())) if all(line in b for b in disabled.values())]
    lines = ["Unavailable because:"]
    lines.extend("• " + line for line in shared)
    for action, items in disabled.items():
        own = [line for line in items if line not in shared]
        if own:
            lines.append(f"{labels.get(action, action)}:")
            lines.extend("  • " + line for line in own)
    return "\n".join(lines)
