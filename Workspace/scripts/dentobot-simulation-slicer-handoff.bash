#!/usr/bin/env bash

# Own the simulation stack and make the readiness-to-Slicer boundary
# observable without tracing command arguments or changing the ROS contract.
set -euo pipefail

stack_log=/tmp/dentobot-simulation-stack.log
readiness_timeout=2s
readiness_attempts=60
readiness_interval=0.5

usage() {
  printf '%s\n' \
    'Usage: dentobot-simulation-slicer-handoff.bash [options] -- diagnostic-command [args...]' \
    '  --stack-log PATH' \
    '  --readiness-timeout DURATION' \
    '  --readiness-attempts COUNT' \
    '  --readiness-interval DURATION' >&2
}

while (($# > 0)); do
  case $1 in
    --stack-log)
      if (($# < 2)); then
        usage
        exit 64
      fi
      stack_log=$2
      shift 2
      ;;
    --readiness-timeout)
      if (($# < 2)); then
        usage
        exit 64
      fi
      readiness_timeout=$2
      shift 2
      ;;
    --readiness-attempts)
      if (($# < 2)); then
        usage
        exit 64
      fi
      readiness_attempts=$2
      shift 2
      ;;
    --readiness-interval)
      if (($# < 2)); then
        usage
        exit 64
      fi
      readiness_interval=$2
      shift 2
      ;;
    --)
      shift
      break
      ;;
    *)
      usage
      exit 64
      ;;
  esac
done

if (($# == 0)); then
  usage
  exit 64
fi
if [[ ! ${readiness_attempts} =~ ^[1-9][0-9]*$ ]]; then
  printf 'Invalid --readiness-attempts value: %s\n' "${readiness_attempts}" >&2
  exit 64
fi

handoff_reason=not_started
stack_pid=

handoff_log() {
  local stage=$1
  shift
  printf 'DENTOBOT_HANDOFF stage=%s' "${stage}"
  if (($# > 0)); then
    printf ' %s' "$@"
  fi
  printf '\n'
}

stack_group_alive() {
  [[ -n ${stack_pid} ]] && kill -0 -- "-${stack_pid}" >/dev/null 2>&1
}

cleanup_stack() {
  local initiating_status=${1:-0}
  local cleanup_reason=${handoff_reason:-unknown}

  trap - EXIT INT TERM
  handoff_log cleanup_begin \
    "reason=${cleanup_reason}" \
    "initiating_status=${initiating_status}" \
    "stack_pid=${stack_pid:-none}"

  if stack_group_alive; then
    handoff_log cleanup_signal signal=INT reason=graceful
    kill -INT -- "-${stack_pid}" >/dev/null 2>&1 || true
    for _attempt in $(seq 1 20); do
      stack_group_alive || break
      sleep 0.25
    done
  fi
  if stack_group_alive; then
    handoff_log cleanup_signal signal=TERM reason=escalation
    kill -TERM -- "-${stack_pid}" >/dev/null 2>&1 || true
    for _attempt in $(seq 1 20); do
      stack_group_alive || break
      sleep 0.25
    done
  fi
  if stack_group_alive; then
    handoff_log cleanup_signal signal=KILL reason=final_escalation
    kill -KILL -- "-${stack_pid}" >/dev/null 2>&1 || true
  fi
  if [[ -n ${stack_pid} ]]; then
    wait "${stack_pid}" >/dev/null 2>&1 || true
  fi

  handoff_log cleanup_complete \
    "reason=${cleanup_reason}" \
    "initiating_status=${initiating_status}"
  exit "${initiating_status}"
}

handle_signal() {
  local signal=$1
  handoff_reason=signal_${signal}
  handoff_log signal signal="${signal}" reason="${handoff_reason}"
  if [[ ${signal} == INT ]]; then
    exit 130
  fi
  exit 143
}

trap 'cleanup_stack "$?"' EXIT
trap 'handle_signal INT' INT
trap 'handle_signal TERM' TERM

if ! : >"${stack_log}"; then
  handoff_reason=stack_log_open_failed
  handoff_log stack_start_failed reason="${handoff_reason}" log="${stack_log}"
  exit 2
fi

handoff_reason=stack_start_requested
handoff_log stack_start log="${stack_log}"
setsid ros2 launch dentobot_moveit_config simulation.launch.py >"${stack_log}" 2>&1 &
stack_pid=$!
handoff_reason=stack_started
handoff_log stack_started pid="${stack_pid}"

stack_ready=false
for _attempt in $(seq 1 "${readiness_attempts}"); do
  if ! kill -0 "${stack_pid}" >/dev/null 2>&1; then
    stack_exit_status=0
    if wait "${stack_pid}"; then
      :
    else
      stack_exit_status=$?
    fi
    handoff_reason=stack_start_failed
    handoff_log stack_start_failed \
      reason="${handoff_reason}" \
      exit_status="${stack_exit_status}"
    tail -n 80 "${stack_log}" >&2 || true
    exit 2
  fi

  status=
  readiness_rc=0
  if status="$(timeout "${readiness_timeout}" ros2 topic echo \
    /dentobot/simulation_status std_msgs/msg/String \
    --once --field data 2>/dev/null)"; then
    :
  else
    readiness_rc=$?
  fi
  ready=false
  if [[ ${status} == *'"ready":true'* ]]; then
    ready=true
  fi
  handoff_log readiness_observation \
    attempt="${_attempt}" \
    rc="${readiness_rc}" \
    ready="${ready}" \
    bytes="${#status}"
  if [[ ${ready} == true ]]; then
    stack_ready=true
    handoff_reason=readiness_accepted
    handoff_log readiness_accepted attempt="${_attempt}"
    break
  fi
  if ((_attempt < readiness_attempts)); then
    sleep "${readiness_interval}"
  fi
done

if [[ ${stack_ready} != true ]]; then
  handoff_reason=readiness_failed
  handoff_log readiness_failed \
    reason="${handoff_reason}" \
    attempts="${readiness_attempts}" \
    timeout="${readiness_timeout}"
  tail -n 80 "${stack_log}" >&2 || true
  exit 2
fi

handoff_reason=slicer_launch_requested
handoff_log slicer_launch_request argc="$#"
handoff_reason=diagnostic_entry
handoff_log diagnostic_entry

diagnostic_status=0
if "$@"; then
  :
else
  diagnostic_status=$?
fi
handoff_reason=diagnostic_exit
handoff_log diagnostic_exit status="${diagnostic_status}"
exit "${diagnostic_status}"
