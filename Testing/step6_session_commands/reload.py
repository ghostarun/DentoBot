# Hot-reload changed Python modules and move live objects onto the new classes.
result = reload_changed()
if result.get("restart_required"):
    result["warning"] = "ROS-stateful modules changed; start a fresh session for them."
