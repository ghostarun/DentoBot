# VERIFY-LEARN-01 — guided verification session and reusable checklist (2026-10-02)

Educational record, not proof that every DENTOBOT subsystem was tested. Canonical
rules: [AGENTIC_VERIFICATION_PROTOCOL.md](../AGENTIC_VERIFICATION_PROTOCOL.md) and
`Testing/verification_matrix.json` (checkout root). Nothing here authorizes runtime.

## 1. Worked example (real change from this session)

Checkout root: `ros2_ws/src/DentoBot-step6-5.10-integration`. Evidence dir:
`/tmp/dentobot-verification/verify-learn-01-20261002/`.

| Step | Question / choice |
|---|---|
| Changed subsystem | DentoCase browser (`dentobot_workflow/case_library.py`); `git diff --stat`: 14 insertions, 2 deletions |
| Question | Does the process/network-boundary test pass without weakening it? |
| Hypothesis | The `threading` import exists only for a cancel flag (`set`/`is_set`), so a local flag class removes the violation |
| Smallest sufficient check | Level 0 inspect → Level 1 isolated logic (host pytest). Slicer/ROS not needed: the change has no native behavior to prove |
| Expected result / stop | Both files pass; stop at the first causal failure, not a blind rerun |

| Check run | Command | Result |
|---|---|---|
| `static.git_diff_check` (matrix) | `git diff --check -- <file>` | exit 0 |
| py_compile (matrix pattern `static.*_pycompile`) | `PYTHONPYCACHEPREFIX=<evidence>/pycache python3 -m py_compile <file>` | exit 0 |
| Focused pytest | `python3 -m pytest -q -p no:cacheprovider Testing/test_modular_structure.py Testing/test_dentocase_browser.py` | 9 passed (before the fix: 1 failed, 4 passed) |

Skipped, and why: `pure.dentocase_integration` (broader than this change; run it at the
profile checkpoint), `build.*` colcon checks (no C++/package/install change), all
Slicer/ROS/MoveIt checks (not required to answer the question; runtime resources were
also held by another run). Matrix gap noted: no check ID covers `test_modular_structure.py`;
the command was a concrete bounded one, not a guessed invocation.

## 2. What each evidence level proves

| Level | Proves | Does not prove |
|---|---|---|
| Inspect (source/logs) | Where behavior comes from, first causal error | That it runs |
| `py_compile` + `git diff --check` | Syntax valid, no whitespace damage | Any behavior |
| Host pytest (pure) | Logic/geometry/serialization on fixtures | Slicer/ROS/native behavior |
| `colcon build` | Package compiles and installs (workspace → package → `install/` ownership); `colcon_install` is an exclusive resource, serialize it | Runtime correctness; only run when native/package source changed |
| Slicer / ROS / MoveIt runtime | One native path, node or guard behaves | GUI usability, planner success in general |
| Normal-window operator verdict | What Tarun sees and accepts | Anything outside what he exercised |

## 3. Reading results

- Find logs under the run's evidence dir (`/tmp/dentobot-verification/...` or `data/dentobot-runs/<run>/`: `campaign.log`, `inferior-status.json`, `diagnostics.md`).
- Read the first causal failure, then stop; later tracebacks (e.g. destroyed-widget callbacks after the PASS marker) are usually shutdown noise.
- PASS marker and process exit are separate facts. Example (2026-10-02 analysis): the headed runner exits 1 whenever its own verdict is `FAILED` (`run_dentobot_step6_headed_review.py:5139`); r22/r26 PASS and r29 PARTIAL exited 0, r30/r31/r14 FAILED exited 1 with no signal and no leak output. An exit 1 with a `FAILED` marker is a verdict, not a native shutdown defect. A different case: aggregate `runTest()` exit 1 after its PASS marker (Aug logbooks, VTK debug-leak report) remains `QA-U-01`.
- Retry rule: count failures against the same causal blocker across commands, workers and sessions; the ceiling is three, after which stop and propose a revised plan.

## 4. Reusable checklist

1. Check `git status`/`git diff --stat`; confirm checkout and that no other agent is editing or running.
2. Read backlog/task contract for the area before choosing work.
3. State question, hypothesis, inputs, smallest check, expected result, stop condition.
4. Pick the cheapest matrix check that answers it; explain why cheaper is insufficient before going up a level.
5. Make one `/tmp/dentobot-verification/<name>/` evidence dir; run `git diff --check`, `py_compile` (with `PYTHONPYCACHEPREFIX`), then one focused pytest.
6. Build with colcon only when native/package source changed; serialize `colcon_install` and runtime resources; keep each command's approval class.
7. On failure read the first causal error and evidence artifact; update the retry count; do not rerun blindly.
8. Record commands, exit codes/markers, evidence paths, skipped checks and why, cleanup, and open questions in today's logbook; label evidence level honestly.
9. GUI-visible results wait for Tarun's verdict.

## 5. Status

Agent-run, host-only walkthrough complete. The task's outcome (the operator executes or
supervises these steps himself) is not demonstrated by this record; suggested live
session: repeat §1 on the next small source change with Tarun driving, then close
`VERIFY-LEARN-01`.
