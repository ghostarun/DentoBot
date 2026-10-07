# Personal development tools — ThinkStation P3 and Linux Legion only

This is Tarun's personal development check. It applies only to Linux ThinkStation
P3 (`100.104.44.67`) and Linux Legion (`100.95.7.78`). It is not a DentoBot lab-PC,
robotics-runtime, clinical, or release compatibility gate. It does not start,
stop, install, update, or restart anything.

From this DentoBot checkout:

```bash
python3 Workspace/scripts/personal-tools-check.py
python3 Workspace/scripts/personal-tools-check.py --latest
python3 Workspace/scripts/personal-tools-check.py --json
codex_switcher active
# Installed personal shortcut, from any directory:
personal-tools-check --latest
```

The check reads installed/running T3 Personal versions and Switcher's sanitized
activity/build metadata. The other PC is inspected using the configured private
SSH alias: `dentobot-a` from ThinkStation, `dentobot-b` from Legion. The destination
IP is fixed by the command; existing SSH users/keys are reused. Missing SSH,
offline Tailscale, unknown builds, stale activity and missing pairing produce an
inconclusive/action-needed result, never a compatibility PASS. Exit codes are
0 (supported matching pair), 1 (action needed/unverified), 2 (local check failed).
`--latest` additionally queries **only** `ghostarun/t3code-personal` and
`ghostarun/codex-switcher-personal`. Private repository metadata uses an existing
`gh` login if available; missing access is reported as unverified.

Required feature baseline: Switcher **0.7.16**, pairing protocol **1**, T3 Personal
**0.0.4503**. Matching versions and protocol establish tool interoperability,
not application/robotics acceptance. T3 Connect and Git handoff remain their own
workflows; this command does not transfer a branch, scene, session, or live
runtime authority.

## Switcher behavior

Pair exactly one other PC in Switcher Settings, using the other PC's Tailscale
IPv4 and the same secret of at least 32 characters. ThinkStation is the idle-start
tiebreak primary; existing active connections on either PC take precedence.

A new unbound thread prefers an account not selected/connected on the other PC.
Existing session affinity, explicit routes, HTTP streams and WebSocket connections
retain their account. Sharing is permitted when no other healthy, permitted
account with usable cached quota is available. Peer status expires after 20
seconds; offline PCs do not reserve an account. This is a preference with a
fail-open fallback, not a distributed exclusive lock. A simultaneous first
request during a network partition can share an account; it is not terminated
merely to enforce separation.

The app and `codex_switcher active` distinguish selected default, live connections,
and last completed request. A selected account is not proof of an in-flight
request. Live WebSocket connections include idle reusable sockets. Activity
contains account identity/name, PC identity, versions and timestamps; it contains
no prompts, account tokens, Git content or patient information. The listener is
bound only to the local Tailscale IPv4 on port 18082, accepts the single configured
peer IP, and requires the pairing secret. It never exposes the existing token API.

Activity pairing does not synchronize or refresh credentials. If both PCs share
copied OAuth grants, use Switcher's existing server/client token authority rather
than refreshing the same grant independently. Paired clients own their local
current, use direct upstream requests, and do not push their current onto the
server. Independently logged-in grants can remain standalone.

## Updates and handoff

```bash
t3code --status
t3code --update
# After saving work/handoff:
t3code --restart
```

Install the same reviewed personal Switcher build on both machines, then restart
Switcher only after the active work is handed off. Run the check again. The check
will flag an installed T3 update whose running process is still an older version.
Source-only changes do not establish an installed/running Switcher version;
`~/.codex-switcher/installed-build.json` is written by the personal installer and
includes the binary checksum. Do not manually claim an old binary is the new build.

The check also compares the running Switcher executable checksum with installer
metadata and requires authenticated peer activity. A new binary on disk while
an older process remains running cannot pass. Install using the reviewed
`codex-switcher-personal/scripts/install-personal-build.py` after safe handoff;
the installer refuses to terminate running processes itself.

New Codex threads must use the Switcher proxy for live connection telemetry and
account preference. The personal check verifies the managed top-level Codex
proxy setting at port 18080 and flags the temporary model-list-test bypass.
It also flags T3-owned Codex backends started before the config changed, or
using custom/home/environment overrides that need independent verification.
This conservative check may require a restart after an unrelated config edit;
it never treats the new file as proof of an old backend's routing.
Existing directly connected threads retain their original connection until
restarted/resumed; changing config does not migrate them into the proxy.
T3's named managed ChatGPT providers intentionally use T3-owned credentials;
use its native Codex provider for Switcher's account pool. The repaired personal
T3 installer retains routing on launches and detached restarts for this exact pair.

The check also verifies the running T3 process inherited the personal Switcher
launcher. If a future T3 update regenerates its launcher and loses those
environment overrides, it reports a repair/restart requirement.
