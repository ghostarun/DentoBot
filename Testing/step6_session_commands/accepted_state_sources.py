# Which status message the bridge treats as "accepted" (r14 question).
import time as _time

bridge = mod("DENTOROS2Bridge")
now = _time.monotonic()


def _status(name, at_name):
    status = getattr(bridge, name, None)
    at = getattr(bridge, at_name, None)
    return {
        "present": status is not None,
        "received_sec_ago": (now - at) if isinstance(at, (int, float)) and at else None,
        "accepted_positions": list(getattr(status, "accepted_positions", ()) or ()),
        "phase": getattr(status, "phase", None),
        "sequence": getattr(status, "sequence", None),
        "validate_only": getattr(status, "validate_only", None),
    }


result = {
    "task": _status("_last_task_status", "_last_task_status_at"),
    "ordinary": _status("_last_joint_status", "_last_joint_status_at"),
    "manual": _status("_last_manual_joint_status", "_last_manual_joint_status_at"),
    "last_accepted_joint_positions_si": bridge.last_accepted_joint_positions_si(),
    "monitored_joint_positions_si": bridge.monitored_joint_positions_si(),
    "completed_phase": getattr(facade, "completedPhase", None),
}
