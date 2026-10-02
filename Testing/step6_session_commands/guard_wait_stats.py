# Cumulative guard round-trip timing since the last reset (operator 2026-10-03, option B).
stats = mod("DENTOROS2Bridge").task_command_wait_stats(reset=True)
calls = max(1, int(stats.get("calls", 0)))
result = {
    **stats,
    "mean_wait_ms": 1000.0 * float(stats.get("wait_sec", 0.0)) / calls,
    "mean_spin_ms": 1000.0 * float(stats.get("spin_sec", 0.0)) / calls,
    "mean_events_ms_per_call": 1000.0 * float(stats.get("events_sec", 0.0)) / calls,
}
