# DENTOBOT Agentic Verification Protocol

This is the canonical verification and subagent contract for Codex, Cursor,
Claude, and future agentic tools. Tool-specific instruction files must point
here instead of copying these rules.

## Safety and authority

- Verification is simulation/research evidence only. It never authorizes robot
  motion, powered drilling, patient use, collision-policy relaxation, deletion,
  Git publication, or Google Drive synchronization.
- `DENTO-VERIFY PLAN <profile>` selects checks from
  `Testing/verification_matrix.json`, explains commands, dependencies,
  resources, expected evidence, and the next action, but executes nothing.
- `DENTO-VERIFY <profile>` also starts with the plan. Execution begins only
  after the operator explicitly approves that proposed plan in the current
  task. A keyword alone does not bypass approval.
- `DENTO-VERIFY STATUS <run-id>` reads existing evidence only.
- `DENTO-VERIFY RESUME <run-id>` proposes the smallest continuation after the
  failed or interrupted gate; newly introduced resources require approval.
- The operator may narrow or withdraw approval at any time. The latest scope
  wins immediately.

## Coordinator and workers

The coordinator is the sole production-code and controlled-document editor.
Verification workers are read-only. A worker that discovers a defect reports
it; it does not patch source, change parameters, relax collision rules, or
silently retry with different inputs.

Use at most three workers alongside the coordinator:

1. **Static worker** — Python compilation, Git diff checks, contracts.
2. **Pure-test/package worker** — scoped pytest and read-only package/schema
   inspection.
3. **Runtime worker** — the sole owner of Docker, ROS domain 73, Slicer,
   MoveIt, display, install tree, and the active MRML scene.

A diagnostic worker is created or resumed only after a runtime failure and
uses the runtime worker's saved evidence. It remains read-only and does not
re-plan unless the approved check explicitly requires a reproduction.

Use the tool's native isolated subagent mechanism:

- **Codex:** spawn with no inherited chat history where supported; send a
  self-contained bounded prompt and reuse the same agent for retries.
- **Cursor:** use a self-contained read-only subagent/custom-agent task and
  resume it for retries.
- **Claude:** use a fresh read-only subagent prompt and resume the same task for
  follow-up diagnosis.

Do not depend on a tool-specific API name in shared prompts. Every worker gets
only the repository path, compact context path, matrix check IDs, approved
commands, expected PASS condition, forbidden actions, evidence directory, and
the result contract below.

## Parallel and sequential execution

Only checks whose matrix entry says `parallel_safe: true` may overlap. Runtime
resources are exclusive even when two commands appear independent.

```text
static/pure/package checks (parallel-safe)
                 |
                 v
conditional colcon build (exclusive install tree)
                 |
                 v
one Slicer/ROS/MoveIt runtime check at a time
                 |
          pass --+-- fail -> read-only diagnostic worker
                 |
                 v
manual normal-window operator acceptance
```

Exclusive resources are:

- `docker:dentobot-slicerros2`
- `ros_domain:73`
- `slicer_process`
- `mrml_scene`
- `display`
- `colcon_install`

Do not run two Slicer processes, two ROS/MoveIt campaigns, a build and runtime,
or two scene-lifecycle checks concurrently against those resources. Creating
extra containers or ROS domains merely to gain parallelism is deferred until a
measured need justifies the added isolation.

## Runtime transaction

For every approved runtime check, the runtime worker must:

1. acquire all declared exclusive resources;
2. record container/image, source revision/diff identity, ROS domain, case
   checksum, build identity, exact command, and start time;
3. inspect for a pre-existing operator-owned Slicer/ROS process and stop rather
   than killing or replacing it without approval;
4. start only the required stack and run one matrix check;
5. capture the declared PASS/FAIL marker, exit code, first failure, and bounded
   tail while writing full output to the evidence directory;
6. terminate only processes started by that worker and verify teardown; and
7. release resources before another runtime check starts.

A PASS marker followed by a non-zero shutdown must be reported as two pieces of
evidence, not collapsed into PASS or FAIL. Scene-clear, VTK leak, or native
abort evidence remains visible.

## Evidence and token budget

Use `/tmp/dentobot-verification/<run-id>/`. Each check writes its complete log
there and a compact `result.json`. Do not paste full logs into agent chat or
controlled documents.

Each worker returns at most 12 lines containing:

- check ID and status: `PASS`, `FAIL`, `BLOCKED`, or `NOT_RUN`;
- exact command and exit code;
- PASS/FAIL marker;
- first causal failure, not every downstream error;
- evidence paths;
- cleanup status; and
- one recommended next action.

Use a self-contained prompt instead of copying the parent conversation. Read
`Workspace/docs/AGENT_CONTEXT.md` plus only the matrix-routed source/docs.
Reuse a worker for retries. Within one run, a successful unchanged check may be
skipped; persistent cross-run caching is deferred.

## Failure routing

| Failure | Read-only diagnosis owner | Required first evidence |
|---|---|---|
| Python/contract | Static worker | file, line, exception/assertion |
| Package/schema | Package worker | package checksum, schema, first mismatch |
| Colcon/C++ | Runtime/build worker | package, first compiler/linker error |
| Slicer startup/reload/clear | Runtime worker | process exit, terminal tail, lifecycle phase |
| ROS ownership/readiness | Runtime worker | node/topic/service snapshot and owner |
| MoveIt Stage 1/2/3 | Diagnostic worker | structured motion report below |

The coordinator and operator decide whether to start a separate implementation
turn. A verification worker never converts diagnosis into a source change.

## Three-stage MoveIt failure report

Read `MotionDiagnosticSession` evidence first. Do not infer collision merely
from an IK endpoint or partial fraction. Report:

- failed stage: Home→PreEntry, PreEntry→Entry, or Entry→Target;
- task, trajectory, base, Home, robot, tool/frame, and collision-scene
  fingerprints;
- direct, seeded, or clearance-detour route and IK seed identity;
- planner error/status, fraction, distance, and waypoint counts;
- first invalid composed and stage-local waypoint;
- last-valid and first-invalid joint vectors where retained;
- first collision pair, bounds/corridor/backtrack/overshoot/identity cause, or
  explicit `unknown`;
- fixed-frame fingerprint and J6 lock state; and
- whether only a provisional Stage-1 preview remains.

Diagnostics are explanatory only. They cannot authorize a partial drilling
path, non-tool contact, new collision exemption, hardware action, or a clinical
claim.

## Matrix maintenance

- The matrix inventories existing checks; it is not a second test harness.
- Add a row when a reusable check already exists or a new acceptance gate is
  deliberately introduced.
- Every row declares dependencies, resources, approval class, timeout, evidence
  level, command/entrypoint, and PASS condition.
- Builds run only when their owned production sources changed or the operator
  requests a clean rebuild.
- Manual gates have no executable command and are never delegated.

