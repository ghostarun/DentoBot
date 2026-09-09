# DENTOBOT Tasks

Last reconciled: 2026-09-09

## Sol routing correction — 2026-09-09

- **ID:** `AGENT-SOL-RESTORE`; **Priority:** Unprioritized; **State:** Agent policy updated; saved-default outcome recorded in today's logbook.
- **Requested:** Restore recommended Sol use, approximately 90% High-or-lower and 10% Extra High as needed; confirm visual debugging/user-expertise requirements.
- **Changed:** Sol replaces Astra as preferred coordinator; old avoid-Sol rule superseded, Luna Max/Terra High auxiliaries retained. Canonical protocol confirms collision visuals and now explicitly names UI screenshots.
- **Evidence/next:** Policy readback and saved-default result in today's logbook. Apply the routing and visual escalation contract to the next development task; no model benchmark or runtime verification authorized by this correction.

## Agent verification policy integration — 2026-09-09

- **ID:** `AGENT-VERIFY-ECONOMY`; **Priority:** Unprioritized; **State:** Completed — instruction integration and documentation readback; runtime effectiveness unmeasured.
- **Requested:** Adopt the supplied SlicerROS testing policy and current OpenAI Astra prompting guidance for future development.
- **Changed:** Canonical verification protocol now owns evidence-cost selection, bounded retries, visual escalation, build/regression scope, simulation assumptions and completion labels. Agent entrypoints route to it; removed broad-suite default from compact context and clarified checkout-relative matrix resolution.
- **Evidence:** Attachment hash and fetched official sources in DECISIONS.md; actions/readback in today's logbook. Existing model/approval/resource policies preserved; no test, build or simulation executed for this documentation change.
- **Next:** Apply the compact question/check/stop contract to the next authorized investigation, including Step 6 restore or workspace-purpose work. Earlier recommended task priorities remain proposals.

## DENTO-NOTE triage and recommended work order — 2026-09-09

This is a navigation/order view of the stable tasks below, not a second task
registry. New notes remain **Unprioritized**; the recommended priorities are
agent proposals requested by the operator, not operator-assigned changes.
Existing P0/P1/P3/P4 assignments and the Track-A acceptance gate remain active.

| Recommended order | Existing task / bounded increment | Assigned → recommended priority | Dependency and disposition |
|---:|---|---|---|
| 1 | `S6-RESTORE-ROBOT-ROS`: reliable Step 6 case restore | Unprioritized → **0** | Investigate first; deterministic robot reconstruction/runtime ordering supports repeatable setup and later acceptance. |
| 2 | `S6-REUSABLE-CASE-SETUP`: shared setup retention and save/reopen | **0**, retain | Reuse the corrected restore boundary; preserve opening landmarks/configuration, base and Home without retaining live validity. |
| 3 | `S6-WORKSPACE-PURPOSE`: discuss/freeze 6.3 purpose and clearance meaning | Unprioritized → **0** | Review against current five-DOF TCP, phase policy and shared environment before specifying workspace changes or Studio migration. Discussion may precede implementation of rows 1–2. |
| 4 | `S6-REUSABLE-CASE-SETUP`: target/trajectory/shell registry and selection | **0**, retain | Depends on shared retention/invalidation contract; incorporate the agreed workspace ownership. Same foundation must support 96 records. |
| 5 | `S6-LIVE-01..05`, including current `S6-FDI11-DEPTH` blocker | LIVE tasks **0**, retain; FDI11 Unprioritized → **0** recommended | Resolve reviewed adjacent-anatomy/tool/trajectory constraints, then complete guarded Target→axial retract→Home and repeat. Independent geometry review can proceed earlier; this gate is not deferred behind optional foundation work. |
| 6 | Remaining `DCP-*`, `DSS-*` Studio and batch runner | **1**, retain | Track A accepted, promoted P0 foundation accepted, and 6.3 purpose settled; no duplicate registry or separate temporary setup store. |
| 7 | `UI-P3-01`, `S6-U-01` | **3**, **4**, retain | Visual polish after functional Studio acceptance; shutdown hygiene remains deferred unless it again disrupts normal use. |

Backlog cross-check: `S4A-PULP-ENDPOINT` and `S5B-TERMINAL-COLLAR` are
development-complete and are not reopened by these notes. The pending real-case
acceptance of `S6A-CHANGED-TARGET-GEOMETRY` belongs in the reusable-setup/target
switch checks; preserving shared inputs must not reintroduce old target geometry.
`S6-U-02` mount-frame truth and `W5-U-01` tool/guide fit remain distinct physical
prerequisites where applicable; software restore/workspace changes cannot resolve
them. Other unprioritized inspection/view/platform/POC work retains its status.

## Step 6 DentoCase restores ROS before a usable local robot — 2026-09-09

- **ID:** `S6-RESTORE-ROBOT-ROS`; **Priority:** Unprioritized; **Recommended priority:** 0; **Triage:** Backlog, ready for scoped investigation.
- **Affected workflow:** Step 6 `.dentocase` load, local robot reconstruction, 6.1 ROS/MoveIt connection and continuation to Home/workspace/task validation.
- **Operator observation:** Loading a Step 6 DentoCase does not load the robot and connects ROS directly. Operator must manually load the robot and connect ROS again to proceed.
- **Evidence available:** Operator report only for this incident; no exact package, session log or reproduction collected in this turn. AGENT_CONTEXT documents intended local-robot reconstruction before automatic checkpoint reconnect, with normal-window acceptance pending. This is a reported violation of that intended sequence; root cause is not established.
- **Risk/impact:** Repeated manual recovery defeats reproducible restore and can leave local display/runtime readiness inconsistent. A connection indicator alone must not establish task readiness.
- **Bounded task:** Trace post-load reconstruction, deferred callbacks, prerequisite checks and reconnect callers; correct the shared restore sequence so reconstruction completes before the current Step 6 reconnect path proceeds, or stop at the first failed prerequisite with an actionable reason. Repeated load/retry must not duplicate robot/runtime objects. Coordinate with `S6-REUSABLE-CASE-SETUP`, not a separate persistence workaround.
- **Policy boundary:** Current Step 6 checkpoint auto-resume and future schema-2 Studio offline load are different contracts. Do not silently introduce automatic ROS connection into the future Studio load path, whose planned behavior is offline hydration followed by explicit runtime activation.
- **Next verification action:** After caller audit and the prescribed execution approval, reproduce a fresh-session Step 6 load and a warm repeated load; observe local robot/base/Home restoration before runtime readiness, no manual second connection, and truthful stopping when robot resources or ROS are unavailable. Saved workspace/task evidence still requires fresh validation. No fix or runtime acceptance claimed.

## Step 6.3 workspace purpose and clearance review before Studio — 2026-09-09

- **ID:** `S6-WORKSPACE-PURPOSE`; **Priority:** Unprioritized; **Recommended priority:** 0 for purpose/clearance review and any demonstrated current-workflow defect; **Triage:** Backlog, discussion/design prerequisite for Studio workspace migration. Broader Studio presentation remains P1.
- **Affected workflow:** Step 6.3 Generate Workspace, reviewed exploration limits, retained joint/TCP samples and Home-connectivity evidence; downstream planning seeds and future Studio workspace/study eligibility.
- **Operator observation and request:** The 5 mm clearance leaves no TCP workspace in the intraoral space. Step 6.3 needs updating for the latest developments, and its purpose must be discussed and revamped before the Simulation Studio revamp.
- **Evidence available:** Operator observation; the exact 5 mm parameter, its geometric reference and rejection path have not been inspected or reproduced in this turn. Existing context describes 6.3 as retained static-valid MoveIt-FK TCP/joint samples plus a bounded Home-connectivity classification; reviewed min/max limits are an exploration envelope, not a collision-free box.
- **Risk/impact:** An unsuitable exclusion may discard useful intraoral candidates or present misleading feasibility evidence. Conversely, removing clearance without distinguishing TCP location, complete tool/robot geometry and phase-specific contact could admit invalid states. An empty sampled set is not proof that no task path exists.
- **Discussion deliverable:** Agree whether 6.3 supplies an exploratory reachability display, reusable Home-connected planner seeds, task-specific feasibility evidence, or separately labelled combinations; specify what is mandatory for a single trajectory and what is reusable across the 96-record registry. Separate joint/FK reach, whole-robot static collision validity, Home connectivity and full oriented task-path acceptance.
- **Bounded follow-up:** Locate every consumer of the reported 5 mm setting and determine whether it is an ROI inset, TCP exclusion, tool-envelope allowance or collision policy. Compare it with the current five-DOF canonical TCP, actual tool/guide geometry and phase-specific rules. Propose the smallest justified 6.3 behavior/UI/invalidation change after discussion; no replacement clearance value is selected here.
- **Dependencies:** This purpose/ownership decision precedes Studio Workspace migration and workspace-related shared-environment fingerprints. Current restore readiness and freshly validated Home are prerequisites for live generation checks; existing `S6-LIVE-05` still gates the wider Studio implementation.
- **Next verification action:** First perform a scoped source/settings audit and document the contract. Then, under the prescribed approval, use a reviewed intraoral case to attribute sample rejection to the exact filter, distinguish static-valid/Home-connected/untested samples, and check reconnect/target-change invalidation. Full-task guards remain authoritative; no collision margin, joint limit, anatomy authority or live-validity requirement is relaxed by this note.

## P0 reusable Step 6 setup and multi-target DentoCase — 2026-09-09

- **ID:** `S6-REUSABLE-CASE-SETUP`; **Priority:** 0; **Triage:** Active investigation; implementation and verification pending.
- **Operator observation:** Testing another target/trajectory on the same CBCT requires repeating through Step 5 and repeating Step 6 mouth opening, robot base placement and Task Home. Operator reports this repetition is tiring and requests reusable saved setup.
- **Requested behavior:** Save/load mouth-opening configuration including placed landmarks, robot base placement and Task Home configuration. Resetting the Step 6 package must retain these reusable inputs. Store multiple target teeth, their trajectories and their respective shells in the same `.dentocase`, and select/import the desired target record in Step 6 without overwriting the others.
- **Operator clarification — Studio foundation:** This must be implemented as the framework foundation for the major Robotics Simulation Studio revamp, whose required scale is one-click planning/simulation across **96 trajectories**. Reset retention must use the same shared environment and target registry that the future runner consumes; a separate temporary persistence mechanism is not sufficient. The existing roadmap's three slots per tooth accommodates 32 × 3 = 96 records; absent or unprepared teeth/slots must remain explicit, not fabricated. Actual case eligibility determines the runnable subset.
- **Foundation acceptance requirement:** One persisted common setup; stable tooth/trajectory/shell associations; target selection without redoing unchanged setup; per-trajectory dependency invalidation; legacy-case migration; and save/reopen preservation of a 96-record registry. The eventual single-click runner uses a frozen eligible selection, serialized planning, visible per-trajectory outcomes/progress and cancellation, and saved attempt provenance. These are required design constraints, not implemented or verified capabilities. Retained shells remain associated with their trajectory; research versus guarded-preview collision inclusion remains an explicit mode under the existing policy.
- **Affected workflow:** Steps 4–5 target/trajectory/shell preparation; Step 6 package reset/import, 6.0A mouth opening, base placement and 6.2 Task Home; case save/reopen.
- **Evidence available:** Operator report, existing saved-checkpoint documentation and initial Graphify/source routing. No reproduction of this reported reset has been run. Existing changed-target cleanup deliberately removes transient opened/target-attached geometry; preserving inputs must not resurrect another tooth's shell or bypass lineage checks.
- **Required boundary (agent interpretation):** Retain reusable configuration when its actual CBCT/anatomy/frame/landmark/robot-model dependencies are unchanged. Target selection alone must not erase shared setup. Dependency changes may mark affected configuration stale with a reason while preserving recoverable values. Saved configuration is not live collision validity: reconnect, scene acknowledgement, Home validity, workspace/task confirmation and motion plans require appropriate fresh validation. Rebuild target-dependent opened geometry from the selected record.
- **Risk/impact:** Repeated manual placement slows planner testing and introduces setup variation; indiscriminate retention could attach the wrong shell or falsely restore planning validity.
- **Work order:** First isolate reset/invalidation from reusable setup retention and round-trip persistence; then implement the multiple-target/trajectory/shell registry and Step 6 selection on that foundation. Both requested increments are P0, ahead of unrelated P1 work. Existing safety gates and same-priority prerequisites remain. This promotes the requested subset of `DCP-02..08` for investigation; it does not promote the entire Studio roadmap or claim Track A acceptance.
- **Next bounded action:** Trace all callers of package reset, target change, jaw reset and bundle hydration; specify exact ownership/fingerprints and migration behavior; implement the smallest retention change with a focused regression. Then propose approval-gated checks: reset retains landmarks/opening/base/Home values; two target records round-trip with their own trajectories/shells; switching cannot retain old target geometry or live plan validity; changed source dependencies report staleness; legacy single-target cases still load.

## FDI11 Goal 1 insertion preflight — 2026-09-08

- **Current operator authorization:** Resume the exact full simulation with a
  bounded guide-contact rule. The stationary `pneumatic_spindle-Copy` housing
  may contact only the configured guide/template, only during terminal contact,
  drilling and retraction, and by at most 0.5 mm. Approach contact, rotating
  burr contact, concealed/other collisions, joint/corridor/endpoint failures
  and non-monotonic drilling or retraction remain rejected. Burr-guide clearance
  stays at 0.1 mm. Persist contact diagnostics and require the complete guarded
  cycle and fresh repeat cycle.

- **State:** Active implementation and approved simulation verification. The
  preceding 0.026243 mm housing/template failure is now expected warning input
  under the superseding policy; acceptance still depends on native re-checking
  for other contacts and both exact cycles completing. No hardware action is
  authorized.

- **Superseding operator decision:** Resume implementation and full simulation.
  Keep the 6 mm Target; include a provisional 0.5 mm guide/shell traversal in a
  6.5 mm combined allowance, leaving 0.5 mm from the modeled 7 mm protrusion.
  Accept positive non-contact sub-1 mm non-burr-link-to-configured-guide
  clearance as a persistent diagnostic warning. Actual collision, burr-guide
  0.1 mm, self and unrelated-object 1 mm checks remain hard gates. Implement
  guarded axial retraction before Home and repeat the complete cycle.

- **Latest operator direction:** Record all diagnostics and address hard physical constraints; no further temporary geometry/margin manipulation. Authoritative consolidated constraint table and evidence boundaries: `docs/logbook/2026-09-08.md`, “FDI11 hard-constraint diagnostic checkpoint”. Full6mm acceptance requires reviewed tool protrusion and guide/housing geometry; endpoint anatomy and explicit guarded retraction remain separate requirements.

- **Current verified blocker:** The combined insertion preflight passes exactly at
  6.000 + 0.500 = 6.500 mm, and the native guide-warning path accepts four
  positive spindle/template distances. The exact case then rejects actual
  `pneumatic_spindle-Copy`↔final-template penetration of 0.026243 mm at Stage 3
  drilling checkpoint 16. A second exact attempt selected a different route and
  rejected burr/template clearance of 0.012463 mm before Stage 3. Offline exact
  saved-mesh sweep independently intersects the housing at 4–6 mm for 12/12
  sampled axial rolls. Burr diameter alone cannot resolve this. Guarded axial
  retraction/reverse-approach/Home source and pure/native regressions are
  implemented, but exact execution cannot begin while the 6 mm preflight is
  correctly blocked by actual collision.

- **Latest authorization:** Operator approved 0.1 mm simulation burr–guide clearance only; actual collisions and other 1 mm margins remain enforced. Pair-margin implementation and native verification completed; exact-case run ended in a geometry failure. No runtime is active. Measured-geometry replacement requirements are in DECISIONS.md (2026-09-08 provisional simulation tool and guide clearance).

- **ID:** `S6-FDI11-DEPTH`; **Priority:** Unprioritized; **State:** Blocked pending measured/reviewed tool protrusion and guide/housing geometry, or an explicit new decision to admit actual configured guide contact as simulation-only warning evidence. The provisional 1 mm burr/6 mm cap passes combined insertion and nominal bore fit, but full-task preflight rejects signed housing/template penetration. Diagnostics are recorded; no runtime is active. Full testing approval remains available once the geometry prerequisite changes.
- **Historical 2 mm runtime blocker:** Saved final-template metrics confirm trajectory guide inner diameter 1.5 mm versus then-configured 2.0 mm burr; 2.2 mm docking bores are a separate structure. Converged PreEntry candidates collide burr↔final printable template. Requires reviewed compatible guide/tool dimensions and regeneration; do not suppress the template collision to claim completion. Full axial retract/Home remains unverified.
- **Superseding operator action:** Requested 1 mm modeled burr remotely. Separate simulation mesh created, URDF visual/collision references updated, fit reporting aligned; original CAD mesh retained. Mesh dimensional readback and 47 focused tests pass; description package rebuild passed. Runtime retry active with unchanged collision/1 mm research-margin policy. Historical 2 mm result above remains evidence for the former model.
- **Latest bounded outcome:** Baseline 1 mm/6 mm case reaches Stage3 fraction0.56 then J2 lower bound. In-memory -5 mm local-Z base trial yields three candidates with Stage3 fraction1.0, but independent guard rejects approach clearance (selected0.630296 mm) between burr and final template against 1 mm requirement. No preview/full cycle accepted. Saved package unchanged. Next decision is explicit simulation-only burr/guide clearance policy (proposed0.1 mm, actual collisions and all other1 mm margins retained), or redesigned guide; merely shrinking diameter cannot satisfy1 mm clearance inside1.5 mm bore.
- **Superseding request:** Operator supplied a manual 7.977 mm trajectory, initially requested 10 mm clipping/removal of depth constraints, then explicitly corrected the cap to 6 mm due to spindle reach. Apply the cap to the confirmed simulation Target, preserve shorter trajectories, retain physical insertion/collision guards. Pulp identification is no longer a prerequisite for this manually specified bounded simulation, but no capped endpoint is claimed to be pulp.
- **2026-09-09 endpoint clarification:** The absent FDI11 pulp label is treated as a segmentation-output defect. For this constrained run the operator explicitly retains the 6 mm capped, non-pulp endpoint; special-case logic for a reviewed unlabelled pulp region is follow-up work and must not be inferred silently. The full-cycle harness is aligned with this temporary endpoint policy.
- **Current exact blocker:** The latest `-4 mm` in-memory local-Z base run reaches the 6 mm Stage-3 endpoint kinematically and records configured non-rotating housing/template warnings, then correctly rejects `pneumatic_spindle-Copy` contact with adjacent FDI21 at the final drilling waypoint. No complete preview, retraction, Home or repeat cycle has passed. Do not relax adjacent-anatomy authority to turn this into a passing test.
- **Blocker visualization:** Three isolated 3D views and the exact retained state are saved under `data/dentobot-runs/fdi21-blocker-20260909/`. Red is the FDI21 MoveIt proxy, green is FDI11, orange is `pneumatic_spindle-Copy`, and the marker is the first-invalid TCP. The views show the spindle housing intersecting the lower crown-side FDI21 proxy in the rendered orientation. This is diagnostic evidence for operator intervention, not approval to suppress the anatomy collision.
- **Current exact input located:** `data/Slicer_Saved/SampleStudy1/FDI11/dentobot-case-step6x4x2.dentocase` contains a confirmed task and a 7.977207292891484 mm trajectory, matching the latest screenshot. Preserve original file. Full-cycle acceptance must separately establish axial withdrawal before free-space Home; current returnToTaskHome uses strict current-to-Home MoveIt planning without an explicit retract phase.
- **Operator observation:** Completed preceding workflow; Plan Guarded Approach immediately reports 17.922 mm requested depth versus 6.900 mm capacity. Supplied backend terminal excerpt and identified FDI11 `dentobot-case-step6x4.dentocase` for testing.
- **Evidence:** Read-only nested package inspection found the FDI11 complete trajectory and matching Step 5B insertion line. Source uses a global CAD-derived 7.0 mm protrusion minus 0.1 mm reserve and returns before Goal 1 planning. Terminal has successful requests and two generic MoveIt 99999 failures; no evidence ties these to this preflight rejection. Saved lineage `step6.confirmedTask` is null, so this package is not a persisted copy of the current confirmed live task.
- **Follow-up evidence:** Operator confirms this is the older trajectory and was not regenerated. Nested MRB contains one segmentation file, `Post_surgery_seg.seg.nrrd`; its 54 segment names include FDI11 tooth but no matching FDI11 pulp. Existing upper pulp labels are FDI16/17/26/27 only; lower pulp labels cover FDI31–37 and FDI41–47. Current generator explicitly requires exactly one FDI-matched pulp mask.
- **Alternate input checked:** The FDI11 folder contains only step5b, step6x4 and printable STL; step5b also has no FDI11 pulp segment. No suitable replacement mask found in that folder.
- **Operator correction:** Reports visible unlabeled pulp inside FDI11 and supplies screenshot. Header inspection establishes absence of a recognized label, not absence of internal pulp geometry. Determine whether the visible region is a separate selectable segment or a tooth-mask cavity/internal surface. Existing naming parser accepts `pulp_fdi11`; assigning that name to the identified, reviewed pulp segment in the source segmentation is sufficient for matching, without a code fallback. Do not relabel the tooth or infer a pulp mask from appearance alone.
- **Next:** Obtain the reviewed FDI11 pulp mask or a newer package containing it before generating the requested first-pulp-entry Target. Then invalidate/rebuild dependent geometry and task evidence through existing workflow, check insertion capacity, and run the approved full simulation cycle through Target, retract and Home. Preserve limits and existing source package. Any Slicer reproduction needs a scoped approved runtime plan; no full-loop acceptance claimed.

## Assisted access endpoint — 2026-09-07

- **ID:** `S4A-PULP-ENDPOINT`; **Priority:** Unprioritized; **State:** Completed: source, host checks and isolated Slicer single/dual endpoint integration passed (2026-09-08).
- **Requested:** For single and dual assisted generation, preserve Entry and direction and stop Target at the first intersection with the selected tooth's pulp segmentation mask.
- **Scope:** Binary-mask clipping in the shared generation path; clear failure on unavailable or missed pulp; atomic dual generation. No existing/manual trajectory edits or Step 6 policy changes.
- **Next:** Reload the module before generating new assisted trajectories; existing/manual trajectories remain unchanged. Host and isolated Slicer checks passed. Operator anatomical review and full Track A acceptance remain separate.

## Immediate P0 — terminal coverage disconnects shell collar

- **ID:** `S5B-TERMINAL-COLLAR`; **Priority:** 0; **State:** Completed: approved host regression and exact FDI11 saved-loop/fresh-auto-loop preview→shell→unified builds passed, both exit 0 (2026-09-08).
- **Operator observation:** Automatic Step 5A boundary and manual backside adjustments both leave Step 5B unable to generate the shell/unified template. Screenshot reports two remaining components; target FDI11, four support teeth, terminal coverage 50%.
- **Source finding:** The bridge previously used the full boundary, then terminal half-planes clipped the completed union. This can remove both end connections and split a collar into two rails. This is a concrete failure mechanism, not yet proof of the exact screenshot's cause.
- **Implementation:** Clip and close the boundary at the existing terminal planes before collar construction. Retain the same anatomy exclusion, final coverage clipping and one-component gate. Error text no longer implies that redrawing alone necessarily resolves the failure.
- **Verification:** Old collar produced two regions; corrected collar produced one watertight region in original and rotated frames. Combined host run: 3 passed; compilation and diff check exit 0. Evidence: `/tmp/dentobot-verification/pulp-shell-20260908/`.
- **Exact-case evidence:** FDI11 `dentobot-case-step5b.dentocase`; saved and freshly regenerated automatic boundary both have 50 points, address all five teeth, and produce 3,363-point/6,028-triangle previews. Both shells have one surface region and zero invalid edges; both unified outputs have 74,988 triangles, one occupied volume region and zero invalid edges. Source package checksum unchanged; logs in the evidence directory.
- **Next:** Operator reload and normal-window build/inspection. Development defect is verified; anatomical/manufacturing and Track A acceptance remain separate.
- **Sequencing:** Operator requested completion of pulp-endpoint and P0 prompts one after another; endpoint source work precedes this correction. Approved host checks passed; runtime resources remain serialized.

## Agent model policy — 2026-09-07

- **ID:** `AGENT-ASTRA-LOW`; **Priority:** Unprioritized; **State:** Completed (instruction/config readback).
- **Requested:** Reconsider model/delegation routing after Astra release without exceeding Astra light or wasting quota.
- **Implemented:** Corrected Astra-only light ceiling; avoid Sol; Luna Max for fully specified scoped coding; Terra High for approved testing/read-heavy support; solo for trivial work, one normal auxiliary. Assigned implementation edits are permitted; verification workers remain read-only.
- **Evidence:** Saved default is already `gpt-6-astra` / `low`; project policy read back after editing. No model runs or quota benchmarks were launched.
- **Next:** Apply the policy on the next authorized task; keep an unavailable worker preset with Astra light instead of silently substituting or escalating. Existing runtime/clinical acceptance tasks remain unchanged.

Last reconciled: 2026-09-07

This is the single actionable queue. `DEVELOPMENT_PLAN.md` defines the full
behavior and acceptance contract; this file records only work order and state.

## Immediate P0 baseline cleanup — retired pre-surgery workarounds

- **ID:** `S6-P0-BASELINE-CLEANUP`; **Priority:** 0; **State:** Source cleanup, 63 focused Python tests, native guard build, and 14-check synthetic ROS phase-guard test passed. Clean-case full-loop acceptance remains pending.
- **Reason:** The retired pre-surgery/x4 fixture exposed collision and guide-fit problems. It must not drive production exceptions or planner tuning. New baseline cases must use reviewed post-surgery/clean anatomy and a finalized Step 5C guide/tool model.
- **Implemented:** The production burr-proximity helper now returns only the selected target-tooth object. Adjacent teeth, jaw anatomy, and guide/template objects remain authoritative for collision and the research clearance margin. The façade no longer sends guide/template IDs as clearance exemptions, and the ROS bridge rejects non-empty guide-clearance exemptions.
- **Quarantined:** The historical Step 5C template-collision bypass is unavailable by default and requires the explicit process variable `DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE=1`. Session anatomy-review proxies are ignored by collision publication unless `DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW=1`. Neither override is saved into a case or treated as baseline evidence.
- **Preserved:** J1–J5 canonical-TCP planning, J6-outside-planning policy, strict self/world/anatomy checks, the selected-target terminal-contact policy, endpoint/guard checks, and retained diagnostics remain unchanged.
- **Next:** Review/select one clean post-surgery case and complete its guarded approach, drilling, Return Home and repeat gate. Native guard evidence: `/tmp/dentobot-verification/cleanup-guard-20260907/`. Do not revive the retired x4 override or tune tolerances/base placement to make that fixture pass.

## Active operator interruption — Step 6A changed-target geometry

- **ID:** `S6A-CHANGED-TARGET-GEOMETRY`; **Priority:** Unprioritized (operator requests immediate cleanup); **State:** Source guard implemented; focused host verification and authorized Slicer clear/save round-trip passed; clean FDI44 end-to-end rerun remains pending.
- **Observed:** Operator completed the workflow on a different target tooth and reports FD14-like remnants attached/fused after applying the open-mouth transform. Screenshot is evidence of unexpected visible geometry; its source and actual fusion are unconfirmed.
- **Impact:** Step 6A preview and any derived planning geometry need an ownership audit before acceptance. Do not remove anatomical components based on appearance alone.
- **Evidence:** Source proxy reconstruction clears prior segments, while mandibular template display is copied separately from referenced Steps 0–5 models. The readable historical FD14 MRB contains explicit FD14 Step 5C template and Step 6 obstacle lineage. The relocated FDI44 archive was read-only audited through the authorized container path and showed FDI44 text/lineage with no FD14 strings; the authorized FD14 load → New Empty Case → save regression then reported zero FD14 hits in the saved MRML and lineage.
- **Implementation:** Target changes now clear Step 6A transient jaw/target-attached geometry before downstream deletion; authoritative segmentation changes do the same. The target-attached display builder filters models by persisted target lineage and hides/marks mismatched stale models. This closes the stale-proxy path that allowed a previous target's opened geometry to survive into the next target.
- **Implementation:** Target changes now clear Step 6A transient jaw/target-attached geometry before downstream deletion; authoritative segmentation changes do the same. The target-attached display builder filters models by persisted target lineage and hides/marks mismatched stale models. Restore validation now rejects mismatched trajectory/ROI/docking/template target chains, clears disposable opened-jaw proxies when deactivating a stale package, keeps mismatched source visibility suppressed, refuses to let a saved trajectory silently overwrite the active target during UI hydration, and keeps Reset reachable for stale transient refs while ROS is disconnected.
- **Verification:** Temporary-cache compile and `git diff --check` passed; the focused pure Step 6 suite passed `58 tests` including the modular/context budget; Graphify refreshed. The authorized pinned-container Slicer round-trip loaded FD14, cleared it with New Empty Case, saved a validated bundle, and reported `mrml_FDI14=0` and `lineage_FDI14=0`; no motion or hardware operation was performed.
- **Next action:** Repeat the complete FDI44 workflow from a clean session and visually verify Step 6A. The clear/save regression now supports session carry-over as the cause when New Empty Case is used successfully, while the separate FDI44 archive audit remains text/lineage-only and cannot establish binary mesh identity. Regenerate FDI44 Step 4A/4C/5C if the package reports a cross-target chain; only then repeat 6.0A. See `logbook/2026-09-07.md`.

## Now — Track A priority 0 gate

| Order | ID | Priority | State | Next bounded action |
|---:|---|---:|---|---|
| 1 | `S6-LIVE-00` | 0 | Documentation checkpoint recorded; source baseline `ea504349f99f` preserved; scoped static/pure checks, rebuild, runtime marker, and graph refresh recorded | Keep the checkpoint boundary explicit while reconciling the remaining Stage-3 reachability issue |
| 2 | `S6-LIVE-01` | 0 | Implemented: five-DOF canonical TCP model, exact sequential fixed-axis IK evidence, and full-path-only promotion; runtime confirms first unsolved pose `60/64` | Reconcile the exact Stage-3 geometry/branch boundary; 100% FK-verified recovery is still required before acceptance |
| 3 | `S6-LIVE-02` | 0 | Implemented: independent guard remains authoritative for J1–J5; legacy six-value spindle motion is rejected | Runtime trial must confirm every Stage 1/2/3 waypoint, narrow burr exception, and external-spindle boundary |
| 4 | `S6-LIVE-03` | 0 | Implemented: endpoint checks, consumed stop state, guarded Return Home/replan loop, and diagnostic/live-preview overlap guard | Runtime trial must complete Goal 1→Goal 2→Return Home→replan without Slicer restart |
| 5 | `S6-LIVE-04` | 0 | Implemented: timestamp/speed playback, 30 Hz display coalescing, progress UI, static phase paths | Runtime trial must confirm selectable speed preserves ordered acknowledgements and visible paths |
| 6 | `S6-LIVE-05` | 0 | Historical x4 Goal-1 evidence is retained only as a negative diagnostic; clean-case acceptance is not yet run | Select a reviewed post-surgery/clean case with finalized guide/tool geometry, then complete the full guarded loop |

### Historical pre-reset correction record — not current work order

The following investigation and its task table are retained as history only.
FDI15 editing, x4 base optimization, and x4 acceptance are superseded by
`S6-P0-BASELINE-CLEANUP`; none is a prerequisite for the clean-case run.

2026-09-07 continuation: anatomy-review copies now retain source transform and
reference geometry; source/accepted-proxy fingerprints gate activation and
publication, and collision changes invalidate live Home/workspace validation.
Host compile and 58 scoped tests pass. The native regression remains unrun
because the shared runtime contains an existing Slicer/ROS session.
`S6-P0-ANATOMY-REVIEW` remains **in progress**: session reload/preview freshness,
local-edit review and package-roundtrip evidence are not yet accepted.

Follow-up: module-session identity and shared task/preview freshness checks are
now source implemented, including the final completion tick. Host tests remain
58/58. Native lifecycle and package-roundtrip acceptance remain pending.

Native follow-up: the focused synthetic anatomy-review regression now **passes
with exit 0**, including transformed-source alignment, stale-input rejection,
source preservation, discard and actual MRB proxy/display exclusion. Full
reload/live collision publication and operator-local artifact review remain
unaccepted. The x4 physical insertion/contact prerequisites still block LIVE-05.

| Order | ID | Priority | State | Next bounded action |
|---:|---|---:|---|---|
| 1 | `S6-P0-DEPTH` | 0 | Implemented; focused pure gate passed | Goal 1 preflight enforces CAD-derived `7.0 mm - 0.1 mm = 6.9 mm`; x4 is intentionally blocked pending an upstream tool/access or trajectory revision |
| 2 | `S6-P0-CLEARANCE` | 0 | Classified | Best housing/FDI15 separation is `0.998041065511 mm`, a margin-only violation at that inspected point; separately, all six auditable branches show actual non-target FDI15↔burr contact at Stage 2 waypoint 14 and Stage 3 waypoint 0 |
| 3 | `S6-P0-ANATOMY-REVIEW` | 0 | Source implemented; operator review required | Step 6.5 now creates an inactive `SaveWithSceneOff` copy of one selected non-target tooth and opens it in Segment Editor. Only an explicit artifact confirmation can activate the local session proxy, re-sync collision geometry, and stale the task. Determine whether FDI15 is valid anatomy; no proxy is active by default and runtime verification remains pending |
| 4 | `S6-LIVE-05` | 0 | Blocked by the preceding gates | With valid depth and resolved/reviewed actual FDI15 collision evidence, complete Goal 1 → Goal 2 → exact Target → Return Home → fresh second run |

### Historical Track-A correction checkpoint — 2026-09-04

The bounded kinematic-model correction is implemented across the DentoBot
Step 6 façade/bridge and the canonical non-spinning TCP path. `dentobot_arm`
plans J1–J5 to `dentobot_drill_tcp`; J6 remains visual/collision-only and is
canonicalized to neutral `0 rad` in compatibility records. Stage 2 and Stage 3
now constrain exact XYZ plus the approved drilling axis, retain authoritative FK
endpoint evidence, and reject partial drilling paths. If local continuity IK
reaches a bounded joint limit, only the deterministic Home-connected 6.3
postures are tried as branch seeds; no tolerance, target, collision, or depth
relaxation is made.

The focused x4 runtime evidence is truthful but not yet acceptance-complete:
Stage 1 Home→PreEntry and Stage 2 PreEntry→Entry pass, while Stage 3
Entry→Target stalls at requested pose 60/64 near the J2 lower bound at about
0.251 mm position residual and 0° drill-axis residual. No named collision pair
was reported, and the 2.0 mm burr versus 1.5 mm guide bore remains a separate
physical-fit incompatibility. The fixed fraction accounting and authoritative
final-Target FK checks now report this boundary without promoting a partial
path. Goal-1-only preview still passes as a provisional demonstration; the
full chain remains blocked until exact Stage-3 reachability is resolved and the
normal-window x4 Home→PreEntry→Entry→Target→Home repeat gate passes.
Track B remains blocked.

The focused FK follow-up confirms this is a mechanical reach boundary rather
than a burr/template collision: all 40 deterministic seeds pin J2 at its
lower limit with `0.2510335 mm` position residual and `0°` drill-axis residual;
an out-of-range J2 probe reaches the point but is not valid. The planner now
records `sequential_position_axis_joint_limit` and the limiting joint in the
diagnostic. Next action: operator-adjust the provisional base or revise case
placement, then repeat the normal 6.2/6.3/6.4 validation. Do not change the
URDF limit, exact Target, residual thresholds, collision policy, or partial-path
promotion rules.

## P1 Case Platform / Simulation Studio — blocked by `S6-LIVE-05`

| Order | ID | Priority | State | Entry condition |
|---:|---|---:|---|---|
| 1 | `DCP-00` | 1 | Planned | Track A full loop accepted; freeze façade/backend handoff |
| 2 | `DCP-01` | 1 | Complete as planning record | This 2026-09-05 supersession; no implementation work beyond controlled docs |
| 3 | `DCP-02..08` | 1 | Planned | `DCP-00`; domain, provenance, schema, 3-slot registry, environment, sessions, restore proof |
| 4 | `DCP-09..10` | 1 | Planned | Case/platform foundations accepted |
| 5 | `DSS-01..05` | 1 | Planned | Data/platform foundation accepted; migrate Track-A behavior without changes |
| 6 | `DSS-06..12` | 1 | Planned | Guarded Preview parity accepted |
| 7 | `DHW-01..02` | 1 | Planned | Explicit later safety/architecture approval |

## Other active work

| ID | Priority | State | Next bounded action |
|---|---:|---|---|
| `S3-U-01` | Unprioritized | Scan/run inspection workflow implemented; focused Slicer PASS | Operator reload and visual check on the real preDental/postDental scene; confirm Step 0–3 context bar, source-paired switching, compare, rename, and Step 4 handoff |
| `S6-U-01` | 4 | Deferred reliability | Close retained SlicerROS2/MoveIt shutdown objects only after priorities 0-3 or if lifecycle failure again blocks routine work |
| `S6-U-02` | Unprioritized | Physical mount-frame truth unresolved | Obtain mount-face CAD/contact normal; keep the robot-derived forehead plane quarantined |
| `W5-U-01` | Unprioritized | Physical-fit provenance unresolved | Correct/verify guide bore versus burr and never gate Step 6 simulation on STL export alone |
| `VIEW-U-01` | Unprioritized | Representative acceptance pending | Exercise grouped anatomy, presets, toggles, frame/restore, opacity, and repeated load without view side effects |
| `PLAT-U-04` | Unprioritized | Direct Docker Engine inside WSL2 is the approved default and `WINDOWS_SETUP.md` is canonical; Docker Desktop WSL integration is an exclusive alternative. One Desktop install passed recorded WSLg/CUDA startup; the direct-Engine machine still lacks exact acceptance evidence | Capture the second machine manifest and approved check-only, GUI, segmentation, and simulation evidence; reconcile an isolated release revision, create/advance `stable/lab`, and publish a new immutable lab tag and image identity |
| `POC-U-01` | Unprioritized | Strategic parallel lane | Freeze the bounded task and physical acceptance thresholds |
| `UI-P3-01` | 3 | Deferred | Begin only after Studio functional acceptance |

The former `S6R-*` Studio roadmap and separate `.dentostudy` sequence are
historical. P1 uses the approved `DCP-*`, `DSS-*`, and `DHW-*` roadmap only.
Historical evidence remains in dated logbooks, decisions, traceability, and
the task archive.

## Maintenance rules

- Priority is numeric and ascending; recorded prerequisites may execute first.
- Update one stable row instead of duplicating the same task elsewhere.
- No item is successful without recorded verification at the stated evidence
  level.
- Testing/build/runtime work follows `AGENTIC_VERIFICATION_PROTOCOL.md` and
  requires the prescribed explanation and approval.
- No task authorizes hardware motion, powered drilling, patient-facing work,
  collision-policy relaxation, Git publication, or Drive synchronization.
| 1 | `S6-P0-01` | 0 | Operator trial passed Stage 1 (328 waypoints) and Stage 2 (18); Stage 3 remains blocked at 91.7%/42 partial waypoints. Source now adds bounded fixed-frame sequential IK recovery after a partial collision-off Cartesian response; `py_compile`, restore (28/28), and planning (50 passed with the known unrelated neutral-pose baseline failure) checks are recorded | Reload and re-run Goal 1 once with the recovery path, inspect the exact Stage 3 result, and accept only a 100% independently guarded Stage 3; keep 6.6 blocked otherwise |
| 2 | `S6-P0-02` | 0 | Operator trial proved transient reconstruction, but x4 stopped truthfully at 6.3 and initially displayed 5C. Direct Step 6 landing passed compilation and restore tests 28/28; normal-window behavior is unverified | Reload x4 and confirm Step 6 appears immediately, then verify saved workspace replay either reaches 6.5 or explains the exact 6.3 prerequisite without duplicate runtime ownership |
| 3 | `S6-P1-01` | 1 | Partially implemented; laterality, inferior direction, and retry flow corrected; anatomical subregions/MPR review missing | Add bilateral condylar and incisal/crown interaction regions, guide metrics, exact-source/MPR gates, and a representative operator trial |

## Next — queued by priority

| ID | Priority | State | Entry condition | Next acceptance action |
|---|---:|---|---|---|
| `S6-P2-01` | 2 | Planned | `S6-P0-02` checkpoint matrix understood | Implement one post-load visual integrity panel for Steps 1–6 with Current, Needs attention, Stale, Blocked upstream, and Rejected states |
| `S6-P2-02` | 2 | Planned | `S6-P1-01` accepted | Add smooth display-only incisor-gap preview and one explicit commit action |
| `S6-P2-03` | 2 | Planned | Priority-0 correctness accepted | Add shared truthful busy/progress/result/cancel behavior to long-running actions without fake percentages |
| `UI-P3-01` | 3 | Planned | Priority 1–2 correctness and interaction contracts accepted | Refine the New GUI while proving Legacy parity and zero MRML/ROS side effects |
| `S6-U-01` | 4 | Deferred reliability DENTO-NOTE. Functional connect/reload/reconnect/New Case/reconnect/save-reopen passes after the native ownership repair; only application shutdown still reports retained SlicerROS2/MoveIt VTK objects and class-loader warnings | Priority 0–3 work or an observed runtime regression no longer blocks it | Centralize native shutdown, release robot/parameter/pub-sub/MoveIt wrappers before library unload, correct test process-group cleanup, then require a zero-exit lifecycle run with no SlicerROS2 leaks |

## Unprioritized active and backlog

| ID | State | Next bounded action |
|---|---|---|
| `S6-U-04` | Fix implemented; normal-window acceptance pending. Goal 1 diagnostics **Close** did not dismiss the window before or after evidence review, forcing use of the title-bar X | Run Goal 1, open diagnostics, verify **Close** dismisses it both before and after **Mark Current Evidence Reviewed**, then reopen it and confirm no stale callback/window state |
| `S6-U-02` | Manual Simulation Base containment accepted; physical forehead/mount relationship unresolved | Obtain mount-face CAD/contact normal and define patient-contact-to-base transform, offsets, review, persistence, and invalidation |
| `W4-U-01` | Active design | Define reviewed crown region and MPR contract, then implement source-fingerprinted Entry snapping |
| `W5-U-01` | Backlog | Decide whether an optional path-independent STL export manifest is needed; never make STL Step 6 geometry authority |
| `IMG-U-01` | Representative acceptance pending | Compare authoritative masks and optional display previews on governed CBCT; define acquisition/artifact/segmentation uncertainty evidence |
| `W4-U-02` | Representative acceptance pending | Exercise trajectory selection, assisted/manual placement, oblique MPR, Step 4B support ownership/locking, save/reopen, and reference-linked backtracking on governed anatomy |
| `W4C-U-01` | Design and representative acceptance pending | Validate support-aware docks, collisions, channels, rail roles, tolerances, and the non-parallel-trajectory versus one robot-axis constraint |
| `W5-U-02` | Representative and physical acceptance pending | Validate the read-only Step 4B support pack in Step 5A, editable margin, undercut/removability, shell contact, seating, and terminal support on governed anatomy/phantom |
| `W5-U-03` | Representative acceptance pending. **DENTO-NOTE 2026-09-07:** Step 5B unified-template creation needs detailed operator testing beyond smoke | Run current Step 5B fusion and Step 5C PASS/WARNING/FAIL, reopen, stale-lineage, channel-preservation, and one-STL flow; include dock/rail visibility and printability review |
| `W5-U-04` | **DENTO-NOTE 2026-09-07 (major).** Unified-template branch connectors / dock guiderails occlude the dock **bore holes** themselves — connectors cover the clearance the docks are meant to expose. Workflow must become smarter/optimal (geometry + fusion order), not a cosmetic hide | Diagnose connector↔dock boolean/offset path in `DENTOGuideGeometry` / Step 5B fusion; preserve open bore lumen and rail approach; add an explicit acceptance check that each dock bore remains a through/open cylinder after unified fusion; then re-run representative 5B→5C |
| `W5-U-05` | **DENTO-NOTE 2026-09-07 (UX / workflow).** Step 5B template dimensions interact badly with upstream steps; **no clear Reset** for the unified-template path; **no interactive viewing** while sizing/fusing; the **Advanced** collapsible must be collapsed manually every entry even though 5B is a **required** stage, not an optional advanced detour | Redesign Step 5B panel: promote primary unified-template controls out of “Advanced”; add owned Reset (geometry + params + stale markers); add interactive 3D inspection while adjusting dimensions; gate/validate dimension coupling against Step 4A/4C/5A lineage so bad upstream combos fail closed with an explicit message |
| `VIEW-U-01` | Cross-workflow normal-window acceptance pending. **DENTO-NOTE 2026-09-07:** mask 2D/3D opacity sliders no longer reachable in the viewer path the operator uses — see `VIEW-U-02` | Exercise grouped anatomy, stage presets, manual toggles, frame/restore, opacity, CBCT rendering labels, save/reopen, and Legacy/New parity without renderer or geometry side effects |
| `VIEW-U-02` | **DENTO-NOTE 2026-09-07.** Viewer no longer exposes **2D / 3D opacity sliders for masks**. Legacy still wires `segmentation2DOpacitySlider` / `segmentation3DOpacitySlider` in segmentation UI; operator path (likely New GUI / View Controls) lost them. Needs a **deeper UI/UX plan**, not a one-off restore | Map Legacy vs New GUI vs View Composition ownership of mask opacity; design always-available 2D fill/outline + 3D surface opacity controls (stage-safe, display-only, scene-persistent); plan parity with CBCT opacity and group visibility; implement after written UX plan acceptance, then close with normal-window trial |
| `S6-U-03` | Experimental design; not planning authority | Derive only confidence-labelled observed oral-air surfaces when suitable open-mouth/phantom data exists; keep unobserved space occupied/unknown |
| `CASE-U-01` | Backlog | Define and implement an offline no-ROS migrator for contaminated historical MRML/MRB scenes; never load them into a live ROS process |
| `PLAT-U-01` | Blocked by clean-image acceptance | Rebuild the pinned Ubuntu inference image and accept dependency, backend, Bridge, Slicer import, and persistence behavior without mutable-container repair |
| `PLAT-U-02` | Retired as a primary install; retained as an explicit native Windows Steps 0–5 fallback. Source hides Step 6 and blocks its automatic runtime restore; real-host regression pending | On a Windows workstation, run the renamed fallback check and verify Steps 0–5 plus absence of Robot Simulation; keep native Windows ROS out of scope |
| `PLAT-U-04` | Windows 11 WSLg+CUDA first installation passed check-only, CUDA health, and GUI startup with the MoveIt simulation stack; setup source integrated, hardware/rendering acceptance excluded | Repeat the documented installer and model-cache check on the next lab PC; record its revision and check-only result before use. No hardware motion. |
| `PLAT-U-05` | Ubuntu NVIDIA dual-GPU setup and launcher support integrated; laptop `--check-only` and in-container CUDA passed, while IITM CPU regression remains pending | Run the documented check-only gate on the IITM CPU workstation after updating to the integration commit; retain CPU configuration unless CUDA is intentionally adopted |
| `PLAT-U-06` | Active investigation: the fork base already includes upstream's Slicer 5.12 test commit, current upstream is only three non-runtime-code commits ahead, while the accepted derivative image still uses Slicer 5.10.0 | Preserve the 5.10 rollback; create an isolated 5.12.0 upgrade branch, merge upstream, capture/audit the uncommitted fork APIs, build from the upstream 5.12 digest, then request approval for the staged compatibility and performance gates in `SLICERROS2_5_12_UPGRADE.md` |
| `PLAT-U-03` | Deferred observation | After an approved reboot, record overnight CRD/GDM availability and resource behavior before closing workstation stability |
| `QA-U-01` | Unresolved | Diagnose why the aggregate Slicer test wrapper returns nonzero although isolated members reach PASS; do not treat isolated PASS as aggregate closure |
| `ROS-U-01` | Future design | Define geometry-preserving medical-image and transform semantics before broadening ROS scope beyond current bounded simulation interfaces |
| `POC-U-01` | Strategic parallel lane | Freeze one narrow task and acceptance thresholds, then run representative software, print/seating, registration, and error-budget work |

## Future track

| Track | State | Gate |
|---|---|---|
| F0 evidence ledger | Planned | One reviewed V2 planning attempt and accepted Priority-0 diagnostic schema |
| F1 current-case plan-only study | Planned | F0 and truthful long-running action behavior accepted |
| E stable virtual mount/base | Planned | Physical mount-frame contract and review criteria defined |
| F2 trajectory × base study | Planned | Tracks E and F1 accepted |
| A canonical frame contract | Later | Current bounded transform contracts stable |
| G physical robot integration | Blocked by design | Registration/TRE, calibrated TCP, controller ownership, force/stop logic, and verified safety procedure |

## Recently closed or superseded

These are pointers only; complete evidence remains in the archive, decisions,
reproducibility record, changelog, and dated logbook.

| Item | Disposition |
|---|---|
| Cross-tool agentic verification protocol | V1 source/pure-contract complete 2026-09-02: one canonical protocol and resource-aware matrix serve Codex, Cursor, and Claude; runtime execution remains approval-gated and serialized |
| GitHub default / overlay / Windows-lab conversion docs | `main` is authoritative; the pinned lab release and private Linux/amd64 GHCR image are published. First Windows WSLg/CUDA functional startup passed on 2026-09-07; repeatability on the next clean lab PC remains `PLAT-U-04` |
| Overlay Drive/MCP temps and nested `DentoBot/graphify-out/` | Deleted 2026-09-02; live graph stays at overlay `graphify-out/`. Launch scripts kept |
| Portable overlay `arduino-pressure/` package | Superseded; live bench is `tools/arduino-pressure/` in the DentoBot git tree |
| Host Arduino pressure fs / pipeline Config tab | Source complete 2026-09-02; `py_compile` and `--no-gui` verified; live flash/Hz click pending. Sensing-only |
| Step 6 action ownership/runtime-first ordering | Accepted and moved to the Development Plan ownership contract; no longer an active task |
| Collision object identity/audit | Runtime-accepted for the exact x4 scene; recheck only when its fingerprint changes |
| Viewer showing only internal tooth anatomy | Source-fixed and exact-package verified; remaining normal-window restore/toggle acceptance is owned by `S6-P0-02`, not a duplicate Priority-0 workstream |
| Step 6 substep split/restore deadlock | Fixed; superseded by `S6-P0-02` for checkpoint reconstruction acceptance |
| Schema-v1 bundle compatibility and orientation replay | Implemented and verified; retained as migration history |
| Goal 1 world/base Cartesian conversion defect | Diagnosed/fixed; remaining full-chain work belongs only to `S6-P0-01` |
| Earlier spindle-roll candidate planning | Superseded by spindle-locked arm-route planning; old evidence is historical only |
| Economical workflow modularization | Completed; the active ROS scene-clear abort remains only under `S6-U-01` |

## DENTO-NOTE triage and maintenance rules

- Record every new `DENTO-NOTE` once with a stable ID, affected workflow,
  evidence, impact, priority (or `Unprioritized`), and next acceptance action.
- Priority order is numeric and ascending: 0, 1, 2, 3. A documented dependency
  may execute earlier without acquiring a fabricated priority.
- Update the existing row when state changes; do not create a second active
  section, dated `Next` list, or repeated prose copy.
- Put implementation chronology in today's logbook and durable rationale in
  `DECISIONS.md`. Put exact hashes, schemas, and verification results in
  `REPRODUCIBILITY_AND_TRACEABILITY.md`.
- Move completed/superseded detail to an archive at a controlled documentation
  checkpoint. Do not delete historical evidence.
- No task is successful without recorded verification. Current approval covers
  `py_compile`, scoped pure `pytest`, and necessary production SlicerROS builds;
  Slicer/ROS/MoveIt runtime checks remain operator-led unless separately approved.
- No hardware motion, drilling, patient-facing action, or clinical/safety claim
  is authorized by this queue.
