#!/usr/bin/env bash

set -euo pipefail

container_name="dentobot-slicerros2"
warning_count=0

warn() {
  printf 'WARNING: %s\n' "$*" >&2
  warning_count=$((warning_count + 1))
}

printf 'DENTOBOT workstation health — %s\n' "$(date --iso-8601=seconds)"
printf '\nHost uptime/load\n'
uptime

printf '\nMemory and swap\n'
free -h
memory_available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
swap_total_kib="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
swap_free_kib="$(awk '/^SwapFree:/ {print $2}' /proc/meminfo)"
swap_used_kib=$((swap_total_kib - swap_free_kib))
if (( memory_available_kib < 2097152 )); then
  warn "available memory is below 2 GiB"
fi
if (( swap_used_kib > 1048576 )); then
  warn "swap use exceeds 1 GiB; this workstation uses a rotational system disk"
fi

printf '\nChrome Remote Desktop\n'
if command -v systemctl >/dev/null 2>&1; then
  crd_status="$(
    systemctl is-active "chrome-remote-desktop@${USER}.service" 2>/dev/null || true
  )"
  printf 'host service: %s\n' "${crd_status:-unavailable}"
  if [[ -n ${crd_status} && ${crd_status} != "active" ]]; then
    warn "Chrome Remote Desktop user service is ${crd_status}"
  fi
fi
pgrep -af 'chrome-remote-desktop-host|chrome-remote-desktop' || \
  warn "no Chrome Remote Desktop host process is visible"

printf '\nDENTOBOT container\n'
if ! command -v docker >/dev/null 2>&1; then
  warn "docker command is unavailable"
elif ! docker inspect "${container_name}" >/dev/null 2>&1; then
  printf 'container: absent (safe while DENTOBOT is not in use)\n'
else
  container_status="$(docker inspect --format '{{.State.Status}}' "${container_name}")"
  runtime_safeguards="$(
    docker inspect --format \
      '{{.HostConfig.Init}} {{.HostConfig.PidsLimit}} {{.HostConfig.CpuShares}} {{.HostConfig.OomScoreAdj}}' \
      "${container_name}"
  )"
  printf 'status: %s\n' "${container_status}"
  printf 'init/PID-limit/CPU-shares/OOM-score: %s\n' "${runtime_safeguards}"
  if [[ ${runtime_safeguards} != "true 512 512 500" ]]; then
    warn "container is missing one or more stability safeguards"
  fi
  if [[ ${container_status} == "running" ]]; then
    docker stats --no-stream \
      --format 'cpu={{.CPUPerc}} memory={{.MemUsage}} pids={{.PIDs}}' \
      "${container_name}"
    zombie_count="$(
      docker exec "${container_name}" ps -eo stat= 2>/dev/null \
        | awk '$1 ~ /^Z/ {count++} END {print count+0}'
    )"
    relevant_processes="$(
      docker exec "${container_name}" ps -eo pid=,ppid=,stat=,etime=,comm=,args= 2>/dev/null \
        | awk '
            $3 !~ /^Z/ &&
            ($5 == "SlicerApp-real" ||
             $5 == "Slicer" ||
             $5 == "Xvfb" ||
             $5 == "ros2" ||
             ($5 ~ /^python/ && $7 == "-m" && $8 == "dentobot_inference"))
          '
    )"
    printf 'zombies: %s\n' "${zombie_count}"
    if (( zombie_count > 0 )); then
      warn "container has ${zombie_count} zombie process(es); recreate it after saving and closing Slicer"
    fi
    if [[ -n ${relevant_processes} ]]; then
      printf 'active Slicer/Xvfb/backend processes:\n%s\n' "${relevant_processes}"
    else
      printf 'active Slicer/Xvfb/backend processes: none\n'
    fi
  fi
fi

printf '\nHighest host CPU users\n'
ps -eo pid=,stat=,ni=,%cpu=,%mem=,rss=,comm= --sort=-%cpu | head -12
gdm_shell_cpu="$(
  ps -eo user=,%cpu=,comm=,args= \
    | awk '$1 ~ /^gdm-/ && $3 == "gnome-shell" && $0 ~ /--mode=gdm/ {print int($2); exit}'
)"
if [[ -n ${gdm_shell_cpu} && ${gdm_shell_cpu} -ge 50 ]]; then
  warn "the idle GDM greeter is using ${gdm_shell_cpu}% CPU; restart gdm.service from a local sudo terminal"
fi

if (( warning_count == 0 )); then
  printf '\nResult: no stability warning detected.\n'
else
  printf '\nResult: %s warning(s) detected.\n' "${warning_count}" >&2
  exit 1
fi
