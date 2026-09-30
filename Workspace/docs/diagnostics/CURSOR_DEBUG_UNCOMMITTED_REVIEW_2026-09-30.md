# Cursor debug uncommitted review — 2026-09-30

Reviewed checkout: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`, branch
`cursor-agent/dentoworkflow-debug-20260918`, HEAD `1f072d6`.
Comparison checkout: `DentoBot-step6-renovation`, HEAD `0186410`, plus its
current source and dated controlled evidence. Review is source-only; neither
checkout was switched, committed, reset, merged or exercised in runtime.

## Findings

### High: raw status freshness cannot identify the manual jog request

`DENTORobotWorkflowFacade.py:2006` treats a new Python status object as fresh
and matches requested/accepted joint vectors. The called bridge uses the raw
compatibility command; `_wait_for_joint_command_result` checks arrival time
and vector, without a unique manual request/session ID. Every parsed status
message creates a new object. A delayed/repeated acknowledgement for an
identical vector is therefore indistinguishable from the current command's
reply. The added facade also does not bind its result to the guard's actual
ordinary policy identity. This is a latent acceptance defect if the currently
unwired method is called. Renovation's September 27 source gate records this
exact problem and its replacement with correlated request/session/policy IDs.
Do not transplant this older implementation into renovation.

### High: a submitted jog with unknown outcome does not latch reconciliation

`DENTORobotWorkflowFacade.py:2179` returns an unknown-acknowledgement failure;
the `finally` at line 2186 only clears the in-progress flag. The method has no
persistent uncertainty/reconciliation latch. Its bridge restarts the raw
heartbeat in `finally`, including after a timeout. If a command may have been
accepted before its response was lost, another jog can proceed without an
explicit reconciliation of accepted state. Current renovation records that
uncertainty and blocks further jogging until reconciliation. Retain the newer
implementation rather than promoting this older method.

### Medium: the added public method is an incomplete isolated source slice

The dirty facade adds 475 lines including an initializer flag and
`guardManualRobotJog`. Search across debug DENTOWorkflow and Testing found no
caller or direct test of that method. Its required confirmed task and
PreparedBranch also predate renovation's taskless draft workflow. Existing
facade tests cannot be treated as coverage for the new method. Renovation has
the newer UI/bridge/native protocol, taskless cases and focused regression
tests. This addition is superseded source, not a missing feature to recover.

## Disposition by change group

| Group | Evidence and proposed disposition |
|---|---|
| Dirty facade manual-jog addition | Superseded, unwired and deficient relative to current protocol. Preserve the original work pending explicit cleanup; do not carry it into renovation. |
| `widget_template_build.py` restore barrier (2 added / 1 removed lines) | Correctly skips stale mutation while case hydration is active. The same guard is already present in renovation, and performance has the equivalent direct restore-depth condition. No feature migration is needed. |
| `Testing/test_case_bundle.py` (12 added lines) | Adds a source assertion for the restore guard. The repair's September 29 local log records 13 passing host tests and compilation; no fresh runtime reopen verdict is recorded there. Keep this repair and its evidence together until the old checkout is retired. |
| Seven tracked instruction/controlled-record files | Preserve the September 25 operator override requiring two Luna Max execution workers and orchestrator reasoning. Renovation's current Workspace/AGENTS.md still has the September 23 solo/optional-worker text; its current decision/context files lack the corresponding dated update. Reconcile the scoped policy hunks into the newer records; replacing whole files would lose later work. |
| Untracked September 29 local logbook | Preserve: it explains that the restore traceback loaded the original DentoBot path and documents repair, checks, graph refresh failure and runtime boundary. |
| September 30 local logbook | Created by this conversation's branch audit/review; preserve as audit evidence, not recovered feature development. |
| Engineer-owned artifact listed by Git status | Content excluded from this review under repository rule 16. No content read, export or classification performed. |

## Verification and limits

Read all tracked diff groups, the complete added method, its bridge
publish/wait/status paths, the matching renovation source/tests and September
26/27 task evidence, and the September 29 restore log. `rg` established debug
caller/test absence. `git diff --check` exited 0; this proves whitespace only.
The verification matrix's pure Step 6/restore checks require approval; no new
test/build/runtime was needed to establish the superseded implementation and
duplicate repair. Prior 13-test evidence is attributed to September 29, not
this review. This review does not establish live jog, restore or GUI acceptance.

No implementation edits or policy synchronization were made. All dispositions
are review recommendations under existing S6-LIVE-01,
S6-REUSABLE-CASE-SETUP and S6-P2-03 ownership; the report is not a pending queue.
