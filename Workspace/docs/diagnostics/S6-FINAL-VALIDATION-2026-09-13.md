# Stage 6 final validation and diagnostics report — 2026-09-13

## Executive result

The source and synthetic reusable-case validation is green. The supplied
FDI31 package is not accepted for live planning: all three allowed FDI31
save/reopen remediation cycles failed at a required integrity or
PreparedBranch gate. The six-target live matrix and the ten-point normal-window
review remain blocked and were not represented as successes.

This report separates implementation/unit/runtime evidence from package,
operator, and full-cycle acceptance. It is simulation/research evidence only;
it does not authorize robot motion, powered drilling, patient use, or clinical
deployment.

## Validation identity and boundary

- Date: 2026-09-13, Asia/Kolkata.
- Checkout: `/home/light-tarun/dentobot/ros2_ws/src/DentoBot`.
- Git HEAD when checked: `a4ec2c877c3862aa0520ea4c11f9c22ff9ced064`.
- Working tree: intentionally dirty; existing user changes and failed-run
  artifacts were preserved.
- Current planner contract: exact target depth, current PreparedBranch and
  Step 5C evidence, atomic route activation, post-hydration package audit,
  four open bores, zero channel occupancy, one connected printable solid, and
  no duplicate closed-jaw dock.
- No physical robot, hardware, powered drilling, patient-facing operation, or
  clinical acceptance was attempted.

## Current validation metrics

| Check | Result | Metric | Evidence level |
|---|---:|---:|---|
| Host Stage 6 focused tests | PASS | 88/88; 100% | Unit verified |
| Container planning contracts | PASS | 78/78; 100% | Unit verified |
| Container restore/package contracts | PASS | 44/44; 100% | Unit verified |
| Touched Python production/runner compilation | PASS | 25/25 files; 100% | Static verified |
| Retired phantom production-surface check | PASS | 1/1 | Static verified |
| Git whitespace/diff check | PASS | 1/1 | Static verified |
| Synthetic reusable-case Slicer check | PASS | exit 0; marker `DENTOBOT_REUSABLE_CASE_PASS` | Runtime verified |
| FDI32 retained offline visual/trajectory run | PARTIAL | valid trajectory 1/1; 24 screenshots; Case Foundation pose `VALID`; base locked 0/1; PreparedBranch count 0 | Saved-case diagnostic |
| FDI31 remediation cycle 1 | FAIL | 0/1 package reopen acceptance | Saved-case runtime |
| FDI31 remediation cycle 2 | FAIL | 0/1 package reopen acceptance | Saved-case runtime |
| FDI31 remediation cycle 3 | FAIL | 0/1 package reopen acceptance | Saved-case runtime |
| FDI31 three-cycle campaign | FAIL | 0/3 accepted; retry ceiling reached | Acceptance gate |
| Six-target Stage 6 matrix | BLOCKED / NOT RUN | 0/6 started; current reviewed packages unavailable | Upstream gate |
| Ten normal-window observations | NOT RUN | 0/10 operator verified | Manual gate |
| Full guarded target loop and fresh repeat | NOT VERIFIED | no current eligible package | Full-cycle gate |

The test counts are reported independently; overlapping tests are not added
into one misleading total.

## Commands and outcomes

### Host unit and static checks

```text
python3 -m pytest -q -p no:cacheprovider \
  Testing/test_step6_state.py \
  Testing/test_robot_workflow_facade.py \
  Testing/test_case_bundle.py \
  Testing/test_step6_planning.py
→ 88 passed in 0.29s
```

```text
PYTHONPYCACHEPREFIX=/tmp/dentobot-verification/final-validation-20260913/pycache \
  python3 -m py_compile [19 touched production modules] [6 Stage 6 runners]
→ exit 0; 25/25 compiled
```

```text
git diff --check
→ exit 0
```

The production surface check also passed: no active draft-phantom module,
control, callback, or Step 6 target-jaw fallback was found.

### Container pure checks

```text
docker exec dentobot-slicerros2 bash -lc \
  'cd /workspace/ros2_ws/src/DentoBot && python3 -m pytest -q -p no:cacheprovider \
   Testing/test_step6_state.py Testing/test_robot_workflow_facade.py \
   Testing/test_step6_planning.py'
→ 78 passed in 0.50s
```

```text
docker exec dentobot-slicerros2 bash -lc \
  'cd /workspace/ros2_ws/src/DentoBot && python3 -m pytest -q -p no:cacheprovider \
   Testing/test_case_bundle.py Testing/test_robot_placement.py \
   Testing/test_step6_state.py'
→ 44 passed in 0.51s
```

### Synthetic Slicer reusable-case check

The matrix-routed `runtime.s6_reusable_case` command was run once after its
static and pure dependencies passed:

```text
timeout 300s docker exec dentobot-slicerros2 sh -lc \
  'timeout 300s xvfb-run -a \
   /opt/slicer/Slicer-SuperBuild/Slicer-build/Slicer --no-splash \
   --additional-module-paths /workspace/ros2_ws/src/DentoBot/DENTOWorkflow \
   --python-script /workspace/ros2_ws/src/DentoBot/Testing/run_dentobot_reusable_case_smoke.py'
→ exit 0
→ marker: DENTOBOT_REUSABLE_CASE_PASS
```

The check covered the synthetic Case Foundation ownership/save-reopen path and
the PreparedBranch activation path. It did not start ROS/MoveIt motion and did
not operate hardware. A post-run process inspection found no remaining Slicer,
inference, bridge, or nnUNet worker process.

## Retained case evidence

### FDI32 offline foundation and assisted trajectory evidence — PARTIAL

Source artifact:
`/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired17/result.json`

Measured results:

- target FDI: 32;
- planning coordinate system: `OpenedCaseFoundationWorldRAS`;
- Case Foundation pose: `VALID`;
- assisted trajectory: valid, two defined points;
- trajectory length: `5.487854799733802 mm`;
- source segmentation: `Post_surgery_seg`;
- source volume: `PostDentalSurgery`;
- screenshot count: 24;
- ROS active: false;
- base state: `Unlocked`, therefore not eligible for live planning;
- PreparedBranch count: 0, therefore no current branch can be selected;
- diagnostic repair was applied to reconcile the saved base revision, so this
  is evidence of the repair/visual path, not current package acceptance.

The images show a coherent Case Foundation and assisted FDI32 line, but the
later Step 5C view explicitly reports that the integrated Step 5B template must
be generated first. This is a challenge/partial result, not a Step 6 success.

![FDI32 Case Foundation setup — visual evidence of the reviewed foundation, not operator acceptance](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired17/stage3-case-foundation-ui.png)

![FDI32 assisted trajectory — valid two-point 5.488 mm trajectory shown in the opened planning frame](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired17/step4a-fdi32-assisted-generated-viewport.png)

![FDI32 Step 5C challenge — final template is not available because integrated Step 5B must be generated first](/home/light-tarun/dentobot/data/dentobot-runs/case13sept-fdi32-repaired17/stage9-ui.png)

### FDI31 remediation cycle 1 — FAIL: stale Step 4C after reopen

Artifact folder:
`/home/light-tarun/dentobot/data/dentobot-runs/stage6-target-generation-fdi31-registered-ros2-cycle1-20260913/FDI31`

First causal failure:

```text
FDI31 reopened PreparedBranch is not eligible:
reason = STALE_4C
message = Step 4C is stale or does not match this PreparedBranch.
```

The branch was saved as a single-target branch but reopened as `Stale` with an
empty verification revision. It was correctly not promoted. Two screenshots
were captured; the UI image shows the small target/dock scene and the viewport
image shows the retained dock/label overlap.

![FDI31 cycle 1 failure UI — reopened branch rejected as STALE_4C](/home/light-tarun/dentobot/data/dentobot-runs/stage6-target-generation-fdi31-registered-ros2-cycle1-20260913/FDI31/evidence/failure-ui.png)

![FDI31 cycle 1 viewport — retained scene and dock-label overlap at the failure boundary](/home/light-tarun/dentobot/data/dentobot-runs/stage6-target-generation-fdi31-registered-ros2-cycle1-20260913/FDI31/evidence/failure-viewport.png)

### FDI31 remediation cycle 2 — FAIL: package/MRML orientation mismatch

Artifact folder:
`/home/light-tarun/dentobot/data/dentobot-runs/stage6-target-generation-fdi31-registered-ros2-cycle2-20260913/FDI31`

First causal failure:

```text
Pre-bind package validation failed:
Loaded MRML geometry/lineage differs from the package:
targetDockingReferencePlane.attributes.DENTOBOT.OrientationState
```

The saved workflow lineage reported confirmed orientation while the raw MRML
inspection showed draft orientation. The load was rejected before bind could
promote the package. The UI screenshot is retained. The viewport screenshot is
blank and is explicitly not treated as geometry evidence.

![FDI31 cycle 2 failure UI — pre-bind orientation/lineage mismatch](/home/light-tarun/dentobot/data/dentobot-runs/stage6-target-generation-fdi31-registered-ros2-cycle2-20260913/FDI31/evidence/failure-ui.png)

![FDI31 cycle 2 viewport — blank capture; not valid visual geometry evidence](/home/light-tarun/dentobot/data/dentobot-runs/stage6-target-generation-fdi31-registered-ros2-cycle2-20260913/FDI31/evidence/failure-viewport.png)

### FDI31 remediation cycle 3 — FAIL: upstream shell/insertion changed

Artifact folder:
`/home/light-tarun/dentobot/data/dentobot-runs/stage6-target-generation-fdi31-registered-ros2-cycle3-20260913/FDI31`

First causal failure:

```text
FDI31 reopened PreparedBranch is not eligible:
reason = UPSTREAM_CHANGED
message = Patient shell or insertion state changed.
```

This cycle passed the earlier orientation boundary but still failed the
mandatory reopened PreparedBranch eligibility gate. The screenshot capture
also recorded:

```text
viewport: TypeError: 'QSize' object is not callable
```

Therefore only the UI screenshot is usable for this cycle; the missing viewport
image is not silently reconstructed or counted as visual success.

![FDI31 cycle 3 failure UI — Step 5C load state with the PreparedBranch rejected as UPSTREAM_CHANGED](/home/light-tarun/dentobot/data/dentobot-runs/stage6-target-generation-fdi31-registered-ros2-cycle3-20260913/FDI31/evidence/failure-ui.png)

## Evidence hashes

| Artifact | SHA-256 |
|---|---|
| FDI31 cycle 1 failure UI | `53033062af5f7a929110005cfea2f4541b6ca04f869f69481548d8fbcfc029f0` |
| FDI31 cycle 1 failure viewport | `75fcaef18cee5b85f27b718d5ec80538f5c6d7357e2c4f27acd23919eb4517ee` |
| FDI31 cycle 2 failure UI | `77590f1ebd209291aea65c1f1df63bd646e68136e994945c152929653e64c6a5` |
| FDI31 cycle 2 failure viewport | `a4a09e76b748e217450f68c399be27933ada224cca9d0a94771e60d1d8d87354` |
| FDI31 cycle 3 failure UI | `4495352374dee8f34ef62b76ca323f93a80b2fc8f0b53791b4fea165ba6cab6a` |
| FDI32 diagnostic result JSON | `c4bb3bc76fb32be8b238882e4087852473bbbfaf12df33f5fcd85c08c85e9ca5` |

The cycle-3 saved case SHA-256 remains recorded in the dated logbook as
`c8053112e15f43c77c3eb3b1a7229a7fbfdcff6ca003fd409789fae599efe1c6`.

## Acceptance status by evidence level

| Evidence level | Status | Scope |
|---|---|---|
| Implemented | PASS | Stage 6 exact-target, freshness, atomic activation, restore-audit and geometry hard-stop source constraints |
| Unit Verified | PASS | Current focused host/container suites and static checks above |
| Runtime Verified | PASS | Synthetic reusable-case Slicer test, marker and exit code |
| Integration Verified | NOT ACCEPTED | Current FDI31 package reopen/integrity path failed in all three allowed cycles |
| Full-Cycle Verified | NOT VERIFIED | No current eligible package completed guarded approach, exact target, withdrawal, Home, and fresh repeat |
| Operator Verified | NOT VERIFIED | Ten normal-window observations remain 0/10 |

## Blockers and next action

The report does not close the backlog. The required order remains:

1. Resolve and classify the `W5-U-04` / `W5-U-03` FDI31 residual fragment;
   regenerate Step 5B/5C with four open bores, zero residual channel
   occupancy, one connected printable solid, and no duplicate closed-jaw dock.
2. Perform an explicit current save or reviewed migration of the supplied
   case, then reopen and verify source, segmentation, Case Foundation, base,
   registry, lineage, and checksum identities.
3. Create exactly one current eligible PreparedBranch and current schema-3
   Step 5C evidence through `4A → 4B → 4C → 5A → 5B → 5C`.
4. Record the ten normal-window observations.
5. Only after those gates, run the explicitly approved `S6-LIVE-01` through
   `S6-LIVE-04` runtime campaign and the six-target matrix when six valid
   current packages exist.

The planner must not be used to synthesize missing packages, waive stale
identity, shorten target depth, relax collisions, or replace the normal-window
review.

## Source records

- [Backlog](/home/light-tarun/dentobot/ros2_ws/src/DentoBot/Workspace/docs/backlog.md)
- [Task contract](/home/light-tarun/dentobot/ros2_ws/src/DentoBot/Workspace/docs/TASKS.md)
- [Decisions](/home/light-tarun/dentobot/ros2_ws/src/DentoBot/Workspace/docs/DECISIONS.md)
- [2026-09-13 logbook](/home/light-tarun/dentobot/ros2_ws/src/DentoBot/Workspace/docs/logbook/2026-09-13.md)
