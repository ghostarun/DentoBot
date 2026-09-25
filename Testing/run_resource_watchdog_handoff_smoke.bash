#!/usr/bin/env bash
set -euo pipefail

temporary_dir="$(mktemp -d)"
trap 'rm -rf -- "${temporary_dir}"' EXIT
cat >"${temporary_dir}/ros2" <<'EOF'
#!/usr/bin/env bash
if [[ $1 == topic ]]; then
  printf '%s\n' '"ready":true'
else
  exec sleep 30
fi
EOF
chmod +x "${temporary_dir}/ros2"

PATH="${temporary_dir}:${PATH}" \
DENTOBOT_RUN_ARTIFACT_ROOT="${temporary_dir}/artifacts" \
bash /workspace/ros2_ws/src/DentoBot/Workspace/scripts/dentobot-simulation-slicer-handoff.bash \
  --stack-log "${temporary_dir}/stack.log" \
  --readiness-attempts 2 --readiness-interval 0.1 -- \
  sh -c 'sleep 6' >"${temporary_dir}/handoff.log"

resource_log="$(find "${temporary_dir}/artifacts/ui-watchdog" -name 'resources-*.jsonl' -print -quit)"
test -n "${resource_log}"
python3 - "${resource_log}" <<'PY'
import json
import sys
rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8")]
events = [row["event"] for row in rows]
assert "RESOURCE_SAMPLE" in events, events
assert "MONITOR_STOP" in events, events
assert "HANDOFF_EXIT" in events, events
assert rows[-1]["status"] == 0, rows[-1]
print("DENTOBOT_RESOURCE_HANDOFF_PASS", len(rows), flush=True)
PY
