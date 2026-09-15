# DENTOBOT pending work and backlog

Last reconciled: 2026-09-15. **Check this file before every plan or new task.**
This is the sole pending-work queue: active, blocked, planned, deferred and
unaccepted work, including every open DENTO-NOTE. Detailed contracts live in
[TASKS.md](TASKS.md) and [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md); process and
completion rules live in [AGENTS.md](../AGENTS.md#backlog-first-gate--mandatory).
No completed-task history or execution logs belong here.

**Reading rule:** scan every section before a major plan; search IDs, synonyms,
workflow steps and overlap notes before any scoped plan. Reuse existing owners
and accepted implementation. A row marked acceptance pending requires review,
not automatic reimplementation. Table order outside the active sequence is not
new execution authority. Numeric priorities retain their recorded values;
Unprioritized stays unassigned. Dependencies and runtime/hardware gates apply.

Sources: local controlled records through 11 September and the read-only
[Project Tracker](https://docs.google.com/spreadsheets/d/1W118Z6oDqfA6IOBXg3llCo6-IowoSAif1HxuTFK7NHU/edit)
reconciled through 3 September. Tracker-only work is captured below with source
IDs and provisional status; its old dates, allocations and case diagnostics do
not override later local decisions. Tracker priorities are source metadata,
not promotions into the current development sequence.

## Pending planned work — active correction and acceptance

**Latest FDI31 scope — 2026-09-15:** The operator accepted the causal review and
requested Astra architecture / Luna Max implementation orchestration. The
[Campaign 1 contract](diagnostics/FDI31_PLANNER_RECOVERY_CAMPAIGN_1.md) now
governs `S6-REUSABLE-CASE-SETUP` and `S6-LIVE-01..04`: scene/input review plus
diagnostic repair, bounded endpoint search, then conditional insertion evidence
and Astra review. This supersedes the geometry-correction-only prerequisite and
old stop-after-every-minor-failure interpretation for this scope. The operator
subsequently approved P1/P2 only for run `c1-p1p2-20260914-r1`; P1's
saved-input/machine checks PASS, but P1 overall scene correctness and operator
review are INCOMPLETE. The final bounded native diagnostic/evidence result is
`PASS_FOR_COMPLETED_DIAGNOSTIC_EVIDENCE`, with campaign gate
`USER_REVIEW_REQUIRED`: its packet contains separate phase-aware static,
generic-static and Home-to-endpoint transition records, trusted 31/31 scene
acknowledgement, and TCP/spindle/burr FK evidence. The earlier
`expected 31, observed 0` result and the container/launcher failures remain
historical. P3/P4, more full-planner retries, invariant changes and another
tooth remain unauthorized. The exact runtime logs, hashes and review limits
are in the canonical recovery report. Operator review and final
architectural/clinical acceptance remain separate.

The operator's current Step-4A–5B screenshots confirm the four Step-4B
support-neighbour IDs only; they raise a duplicate closed/opened display and
unreconciled Step-4C/5A plane state. New-case default and legacy Step-5B
preflight/status source corrections passed focused pure checks, but the frozen
r7 package/geometry were not changed. P1 overall remains INCOMPLETE, retained
P2 evidence remains PASS with USER_REVIEW_REQUIRED, and P3 is not entered.
See recovery report Section AK; Section AJ's grouped signoff questions are
superseded, not answered wholesale.

The operator separately saved `dentobot-case-15sept.dentocase` as an intended
reusable opening/robot-base test foundation after deleting the perceived FDI31
artifact. Read-only audit (report AL) found the opening, landmarks and base
matrix are saved, but the base is unlocked, Step-4A target ID/ROI and three old
supports remain, and closed/opened FDI31 are both saved 3D-visible; it is
`PartialOrInspectable`, not `FoundationOnly`. The separate current Step-5B
`2026-09-15-Scene.mrb` supplies the previously missing four-support, dock and
plane readback (report AM): its closed-source FDI31 is hidden, but its 5A
displayed plane normal is 42.45° from its recorded fit normal after jaw
reparenting. A minimal shared source repair and focused pure checks pass;
saved files/frozen Campaign-1 source/r7 are untouched. Next acceptance action
is a bounded offline Slicer plane-frame save/reopen check plus operator scene
review, not P3 or automatic reuse of the partial foundation case.

The source-only follow-up recovered the existing wrapper control flow but could
not prove the failed final2 branch because wrapper readiness/status and
Slicer-request evidence were not retained; that limitation is historical. The
focused handoff helper records those stages and preserves exit status. The
later explicit bounded recheck reached Slicer and produced the current packet;
its bounded native evidence is the current P2 result in report Section T,
while the campaign gate remains `USER_REVIEW_REQUIRED`. This does not
authorize operator acceptance or any P3/P4 action.

**2026-09-15 recapture review correction:** The operator-observed separation
is supported by read-only artifact evidence: the new FDI31 display copy omits
the mouth-opening transform, static labels use transition-sample centres,
and both exported MRBs omit the robot pose transforms referenced by their
models. See recovery report Section W. Under the existing
`S6-REUSABLE-CASE-SETUP` / `S6-LIVE-01..02` owners, the recapture now requires
technical frame/state/persistence correction before operator visual review.
The source-only correction is retained in
`Testing/run_dentobot_c1_display_only_recapture.py` with ten focused pure
tests passing; it now separates endpoint versus transition capture, uses
prepared world-frame copies, and verifies saved robot-pose persistence and
native FK before any future image. It consumes a future explicitly saved
evaluated-sample FK record but does not substitute endpoint/offline FK. No
second display runtime is authorized from that source result. The one approved
endpoint-only Slicer session loaded the retained MRB but stopped before
endpoint capture because this runtime lacks
`vtkMRMLModelDisplayNode.SetPropertiesLabelVisibility`; its manifest is
preserved separately and contains no image or review MRB. Endpoint parity was
therefore not established (this is not a geometry/FK parity failure), and the
transition remains `NOT_RUN` with missing saved native FK for sample 1/134.
Do not request blanket input acceptance or another camera-only/native retry.
The retained native P2 packet is not erased or superseded by these display
defects. No geometry/policy change, implementation or runtime authorization
is inferred from the operator's diagnostic question.

**2026-09-15 endpoint-only repair continuation:** The operator then authorized
source fixes and bounded reruns for Slicer-session blockers. The retained
driver now passes 12 focused pure tests after an optional display-label guard
and a model parent-transform world-matrix fallback. The final scoped display
attempt reached the endpoint parity gate and failed closed: final printable
template geometry matched, but the prepared FDI31 target fingerprint differed
and its maximum bound error was 40.74010467529297 mm versus the 0.05 mm
tolerance. Robot mesh/link transforms and native-vs-offline FK matched; burr
and spindle matched displayed native FK; displayed TCP remained unavailable
because no TCP model exists in the seven-model display set. Save/reopen was
not reached. Endpoint review is BLOCKED, transition is NOT_RUN, all three
runtime artifacts are preserved, and the display retry ceiling is reached.
No geometry/policy change or further runtime is authorized from this result;
the remaining next action is a new evidence/implementation decision for the
prepared-target frame and displayed-TCP contract, not operator acceptance.

**2026-09-15 revised endpoint parity repair authorization:** The operator
explicitly superseded that runtime stop for the two evidenced source defects:
reuse native one-time Case Foundation target preparation plus native
triangulation, and derive the legitimate meshless canonical TCP from the
displayed spindle mesh and fixed URDF relation with robot-profile identity
verification. The focused source suite passes 18 tests. The mounted driver
hash matches the host, the existing container is up with no matching
task-owned/native processes, and a separate repair3 output location is ready.
At most three targeted endpoint-only offline Slicer attempts are authorized;
the exact pre-execution record and command are in recovery report Section AE.
Transition remains NOT_RUN, operator acceptance remains NOT_RECORDED, and the
existing P1/P2 and P3/P4 gates are unchanged.

**2026-09-15 endpoint repair result:** The three authorized targeted
endpoint-only attempts are complete. Repair5 passed the full machine parity
gate after the driver persisted the exact retained J1-J5 vector through the
existing workflow parameter-node rehydration path: prepared target/template
fingerprints and bounds, one-time jaw preparation, robot identity, displayed
link/mesh transforms, derived meshless TCP/burr/spindle FK, save/reopen pose,
and nonblank context/close-up images all passed. The separate review MRB and
JSON packet are retained in recovery report Section AH. Transition remains
`NOT_RUN` because saved sample-1/134 native FK is unavailable; image label
placement/target scale and all operator acceptance remain for review. P1
overall scene correctness remains `INCOMPLETE`, the retained native P2 status
is unchanged, and P3/P4 plus later runtime/hardware actions remain
unauthorized.

**2026-09-15 operator review delta:** The operator accepts the corrected
repair5 endpoint screenshots and requests the next Luna prompt. That visual
review is no longer pending; all-input/clinical acceptance is not inferred.
Under the same owners, reconcile remaining P1 decision-critical inputs from
retained evidence before the proposed conditional P3 batch. Missing historical
transition imagery is deferred and does not itself block static endpoint
feasibility. See report Section AI. No P3 execution or P4 authority follows
from this prompt-preparation turn.

Current dependency sequence: `W5-U-04` → `S3-P0-DENTAL-SEMANTICS` for any
pulp-dependent target packet → `S6-REUSABLE-CASE-SETUP` per-target
4A–5C/STL/save/fresh-reopen gate → `S6-LIVE-01..04` per-target planner, guard,
repeat and playback evidence → normal-window acceptance. Run independent
central incisors FDI31 → FDI41 → FDI11 → FDI21. A target-specific failure
records `FIRST_INVALID` and proposes the next tooth only after operator
approval; shared source/package/runtime failures
stop for a bounded correction. Pairing, optional 32 × 3 testing and the
six-target batch remain downstream. Step 4A review stays in the preparation
review; Case Platform/Studio remains behind `S6-LIVE-05`.
Campaign execution uses operator-selected Luna Max; unresolved higher-reasoning
decisions return an evidence packet and pause the affected path, with no
automatic model switch or speculative workaround. See the campaign gate in
`DEVELOPMENT_PLAN.md`.
The generator STL/folder/diagnostic change is implemented. The operator then
explicitly approved the bounded offline Slicer/ROS/MoveIt check for the
current FDI31 semantic implementation (no robot motion or patient-facing
action). Its current-source run reached the exact target endpoint but stopped
at the first native Stage-3 guard collision; the full FDI31 Step 4→Step 6
simulation therefore remains open. Do not retry or advance to another tooth
under the older full-flow packet. Campaign 1 instead investigates the responsible
layer under its new diagnostic gates; execution approval remains pending.

**Reusable-case implementation handoff:** the Case Foundation/offline-base
revision and the opened-planning-frame correction are reconciled into this
checkout. The authoritative 13-September package was preserved, migrated
through the production serializer, and reopened as a current single-target
FDI31 package with one eligible PreparedBranch. The selected exact route
reaches the requested target endpoint kinematically, but the current native
guard rejects the final Stage-3 drilling waypoint because the spindle housing
contacts the selected tooth. A live-joint scene-sync correction and a native
world-evidence cache removed earlier runtime bottlenecks; the exact
current-source failure is now a diagnostic `FIRST_INVALID`, not a timeout. Do
not repeat source implementation, alter the base/depth/dimensions/guard
policy, or revive the retired phantom path.

**Current operator delta (2026-09-13; order superseded 2026-09-14):** bounded source-only Stage 6.5/6.6
planner interaction work is authorized in parallel with these open gates. The
existing diagnostics now carry selected/locked route intent and require a
fresh current re-plan after restore; this does not reorder the integrity,
geometry, PreparedBranch, normal-window or separate runtime-approval gates.
The operator additionally requires the trajectory-guide channel/hole to be at
least 2.0 mm and asks for distinct per-target diagnostics and a valid case-save
campaign. The six-target FDI31/32/11/12/13/14 matrix remains downstream. The
current 2026-09-14 acceptance delta fixes the order to
FDI31→FDI41→FDI11→FDI21. Each target gets an explicit folder under
`data/Slicer_Saved/SampleStudy1/` containing its `.dentocase`, exported STL,
diagnostics and screenshots. The source has all four tooth masks but lacks
FDI11/21 pulp masks; record missing required pulp as input-data failure and
continue. The bore-floor source gate is implemented below;
the current-case rebuild, per-target Step 5B/5C evidence, planner runtime,
Return-Home loop and saved-case reload remain acceptance work, not inferred
from the source change.

| ID | Priority | Remaining work / state | Dependency, next acceptance and overlap |
|---|---|---|---|
| `W5-U-04` | 0 | Current FDI31 regeneration passes the explicit geometry gate; the historical 5-voxel fragment is not reproduced in the current artifact. FDI11 remains the comparison pass. | Preserve the one-solid/zero-channel/four-open-bore gate and complete the normal-window Step 5B/5C review, including fragment classification evidence. Construction remains the `W5-U-03` fusion owner; do not raise the cleanup threshold. |
| `S3-P0-DENTAL-SEMANTICS` | 0 | DENTO-NOTE 2026-09-14: the installed class map, report/NIfTI/imported-package evidence, pure A-H semantic core, MRML/planning integration, current FDI31 spatial association and save/reopen evidence are captured; focused checks pass. The FDI31 target association is `HIGH`/`VALID`, while other unresolved pulp records remain fail-closed. | Preserve the current FDI31 semantic package and evidence. No new pulp-dependent target claim proceeds without the same canonical tooth+pulp+spatial gate. The remaining FDI31 acceptance is target-specific Stage-3 tool/geometry review and normal-window review, owned with `S6-REUSABLE-CASE-SETUP`; do not create an FDI11-only workaround. |
| `S6-REUSABLE-CASE-SETUP` | 0 | **Full workflow blocked; P1 saved-input/machine checks PASS, P1 overall scene correctness/operator review INCOMPLETE, P2 bounded native diagnostic/evidence PASS with USER_REVIEW_REQUIRED.** Step-4B support membership is operator-confirmed; live 4A duplicate-display and 4C/5A plane geometry remain unverified. New-case defaults and legacy 5B preflight/status were corrected source-only without changing frozen source/r7. Preserve r7 package/STL, r13 terminal spindle↔FDI31 rejection, r14 probe, 31-object native acknowledgement and unknown contact fields; historical failures/attempts remain history. Return Home and repeat remain open. | Follow [Campaign 1](diagnostics/FDI31_PLANNER_RECOVERY_CAMPAIGN_1.md) and report AK: obtain separate world-MRML readback of the operator's current plane/display scene, reconcile it against opened-world constructors and the frozen inputs, then complete remaining decision-critical review before conditional P3. No invariant change, automatic full-flow retry or next tooth. |
| `S4A-PULP-ENDPOINT` | 0 | Source/focused checks pass; anatomical review pending | Deliberately regenerate legacy FDI31 assisted line; review shared native/displayed pulp contact and non-projecting slice glyphs. `A-035` internal-target subset; crown Entry remains `W4-U-01`. |
| `W4-U-02` | 0 | Smooth-display correction verified; normal-window and broader representative acceptance pending | Confirm truthful smooth on/off, CBCT/mask changes, oblique exit restoration and backtracking; distinct from missing opacity controls `VIEW-U-02`. |
| `S6-P0-BASELINE-CLEANUP` | 0 | Cleanup verified; clean-case full-loop acceptance pending | Reuse `S6-LIVE-05` review and full guarded loop; do not repeat source cleanup or revive retired-case exceptions. |
| `S6-LIVE-01` | 0 | **Blocked at tested terminal collision; P1 saved-input/machine checks PASS, but overall scene correctness/operator review is INCOMPLETE. P2 bounded native diagnostic/evidence is PASS with USER_REVIEW_REQUIRED.** r6 and the final no-TTY recheck confirm two kinematically valid reconstructed target states. The final packet separates invalid static validity from the Home-to-endpoint corridor rejection, reconciles the 31-object scene acknowledgement and verifies TCP/spindle/burr FK; contact fields remain unknown. Campaign 1 remains stopped before endpoint/insertion tests. | Complete operator review of the saved scene/selections and native/display evidence; do not use this packet to infer acceptance or a Complete route. Preserve the exact target and independent guard. P5–P7 and production planner changes require evidence-backed later architecture/approval. |
| `S6-LIVE-02` | 0 | Implemented; synthetic phase-guard evidence and r13 forbidden spindle↔target rejection retained. The final native packet records static collision and validate-only guard evidence without changing policy; TaskJointStatus pair/depth fields remain explicitly unknown where not exposed. The additive static/transition/request-correlation correction and burr-transform alias repair are runtime-verified; the correlated 31-object acknowledgement and TCP/spindle/burr FK pass. Configured burr-target authorization and the separately bounded simulation spindle-guide warning remain distinct; neither authorizes spindle-tooth contact. | Preserve independent final guard, full-chain bounds/phase/identity checks, J1–J5 and J6-zero/external-spindle boundary. Any future source correction or native recheck requires operator review and must not change policy; no P3/P4 runtime follows automatically. |
| `S6-LIVE-03` | 0 | Implemented; repeat-loop acceptance is `NOT_RUN` for FDI31 because Packet E stopped at its first-invalid Stage-3 guard result. | Run Goal 1→Goal 2→guarded Return Home→replan/route choice only after a Complete target route; retain the FDI31 failure and await approval before another tooth. |
| `S6-LIVE-04` | 0 | Implemented; playback/restore acceptance is `NOT_RUN` for FDI31 because Packet E did not complete. | Confirm speed, ordered acknowledgements, visible stage paths, saved route intent and current re-plan only for an accepted Complete route. |
| `S6-LIVE-05` | 0 | Blocked by workflow integrity and reviewed clean-case selection | Require finalized guide/tool geometry, complete guarded approach/drilling-preview/withdrawal/Home and fresh repeat. Gates P1 Studio; no hardware authorization. |
| `S6-FDI11-DEPTH` | Unprioritized | Paused: FDI21 housing contact at final drilling waypoint | After integrity acceptance, reconcile exact case/tool/guide identity and propose smallest Stage-3 check. Old 91.7%/x4 values are historical; no automatic base/depth/margin tuning. |
| `S6A-CHANGED-TARGET-GEOMETRY` | Unprioritized | Clear/save guard checks pass; clean FDI44 full workflow review pending | Verify Step 6A geometry from clean session; regenerate cross-target chains if reported. Coordinate stale-proxy ownership with reusable-case restore; do not infer mesh identity from text. |
| `S6-RESTORE-ROBOT-ROS` | Unprioritized | Offline-load contract implemented; fresh/warm reconstruction review pending | Share load campaign with reusable-case acceptance: no auto-connect or duplicate objects; saved Home is configuration only. Includes old `S6-P0-02` restore work. |
| `S3-U-01` | Unprioritized | Scan/run inspection implemented; real-scene visual acceptance pending | Review source-paired preDental/postDental switching, context, compare, rename and Step 4 handoff. |
| `S6-U-04` | Unprioritized | Diagnostics Close fix implemented; visual acceptance pending | Verify Close before/after evidence review, reopen and callback state in an authorized Goal 1 session. |

## Pending planned work — queued milestones

Accepted design intent does not authorize execution. Contract and detailed
acceptance references: TASKS.md and DEVELOPMENT_PLAN.md, under these same IDs.

| ID | Priority | Remaining outcome | Entry condition / overlap |
|---|---|---|---|
| `DCP-00` | 1 | Freeze accepted Track-A backend handoff | `S6-LIVE-05` complete. |
| `DCP-02..08` | 1 | Remaining domain/session and cross-session proof | `DCP-00`; audit/reuse accepted PreparedBranch, registry, shared environment and persistence. Never rebuild the promoted P0 subset. |
| `DCP-09..10` | 1 | SQLite DentoLibrary and case browser | Case/platform foundation accepted. |
| `DSS-01..05` | 1 | Studio shell, Robot/Environment, Workspace, Trajectories, guarded-preview migration | Data foundation; frozen Track-A behavior; `S6-WORKSPACE-PURPOSE` before Workspace migration. |
| `DSS-06..12` | 1 | Studies, results, replay, Procedure/Research separation | Guarded Preview parity; replaces old F0/F1/F2 and separate `.dentostudy` proposal. |
| `DHW-01..02` | 1 | Hardware-session/digital-twin interface preparation | Explicit later architecture/safety approval; no hardware operation. Coordinate `A-004`/`A-013`. |
| `S6-P1-01` | 1 | Bilateral condylar/crown regions, source snapping, MPR/anatomical safeguards | Current P0 accepted; shared crown semantics with `W4-U-01`, not a second anatomy authority. |
| `S6-P2-01` | 2 | Post-load Steps 1–6 integrity panel | Understand restore matrix via `S6-RESTORE-ROBOT-ROS`; reuse existing eligibility/staleness backend. |
| `S6-P2-02` | 2 | Display-only incisor-gap preview and explicit commit | `S6-P1-01` accepted; reuse existing jaw transform. |
| `S6-P2-03` | 2 | Truthful shared busy/progress/result/cancel behavior | P0 correctness accepted; coordinate Step 5B interaction and later studies. |
| `UI-P3-01` | 3 | New GUI refinement with Legacy parity | Studio functional acceptance and P1–2 correctness; consume `W4B-P2-SUPPORT-AUTO`, `W5-U-05`, `VIEW-U-02` contracts rather than duplicate them. |
| `PLAT-U-06` | Unprioritized | Investigate isolated Slicer 5.12 candidate and compatibility/performance | Follow [upgrade plan](SLICERROS2_5_12_UPGRADE.md); preserve accepted 5.10 rollback, audit fork APIs, isolated branch/build, separately approved runtime gates. |
| `PLAT-U-07` | Unprioritized | Data folder created and initial pilot partially synced: 7 of 17 approved `.dentocase` bundles uploaded; 10 larger bundles remain pending browser upload | Use `IITM Dentobot/Data` with the preserved `SampleStudy1/FDI*` layout. Finish only the remaining individual synthetic or explicitly approved de-identified bundles, then verify Drive metadata and checksums. Never sync the whole `Slicer_Saved` tree, raw/non-anonymized bundles, engineer-owned records, or credentials. |

## Backlog — DENTO-NOTEs, design and remaining verification

These are retained obligations; they are not automatically the next major plan.
Source observations, risks and evidence remain under the matching TASKS.md ID.

| ID | Priority | Pending outcome / observation | Dependency / next bounded action |
|---|---|---|---|
| `W4B-P2-SUPPORT-AUTO` | 2 | DENTO-NOTE: narrow two-row support arch; four-nearest support suggestion and single-row jaw UI; source suggestion/pure checks complete 2026-09-15 | P0 integrity first; verify the current four-ID automatic suggestion in a normal window, preserve manual review/lock and edge/missing-tooth handling. UI layout integrates with `UI-P3-01`. |
| `S6-U-01` | 4 | DENTO-NOTE: non-clean native shutdown despite functional lifecycle pass | Preserve P0–3 ordering unless normal workflow regresses; release native wrappers and process group; require clean zero-exit lifecycle without leaks. Coordinate, do not assume same cause as `QA-U-01`. |
| `S6-WORKSPACE-PURPOSE` | Unprioritized | DENTO-NOTE: reported 5 mm clearance leaves no intraoral TCP workspace | Discuss 6.3 purpose; audit exact filter/consumers before any policy or value change; distinguish reach, whole-robot validity, Home connectivity and task feasibility. Prerequisite for Studio Workspace. Recommended P0 was never an assigned priority. |
| `VERIFY-LEARN-01` | Unprioritized | DENTO-NOTE: operator wants one guided, hands-on session to understand the DENTOBOT testing and verification workflow, including `py_compile`, focused `pytest`, conditional `colcon build`, evidence levels and result interpretation | Wait for the active reusable-case/Step 6 reposition implementation handoff and a stable diff. Then use one real, bounded matrix profile to teach inspect → smallest check → static compile/diff → focused pure tests → conditional package build → runtime/manual boundary. Explain each command before approval/execution, let the operator run or follow it, preserve logs/result, and finish with a short operator-readable checklist. No duplicate harness, blanket suite, robot motion or build while files/install tree are changing. |
| `W4-U-01` | Unprioritized | Reviewed crown Entry snapping/MPR contract | Define crown region, then source-fingerprinted snapping; remaining Entry subset of `A-035`. |
| `W5-U-01` | Unprioritized | Physical guide/burr fit provenance; optional export manifest | Verify actual dimensions and physical fit; decide manifest separately. Neither export nor STL becomes Step 6 authority. Includes tracker A-032 dimensional concern. |
| `IMG-U-01` | Unprioritized | Representative mask/display and uncertainty acceptance | Governed CBCT, acquisition/artifact/segmentation evidence; coordinate `VIEW-U-01` display campaign. |
| `W4C-U-01` | Unprioritized | Dock/rail mechanical design and representative acceptance | Agree registration vs load-bearing role, tolerances, channels/collisions and nonparallel trajectories vs one robot axis; overlaps `A-038` fiducial interfaces. |
| `W5-U-02` | Unprioritized | Physical/representative support, margin, undercut, shell seating/removal | Governed anatomy/phantom and criteria; includes remaining normal-window/manufacturing review after verified `S5B-TERMINAL-COLLAR`, without reopening its fixed defect. |
| `W5-U-03` | Unprioritized | DENTO-NOTE: detailed Step 5B/5C testing beyond smoke | After `W5-U-04`, review FDI11/FDI31 fusion, PASS/WARNING/FAIL, reopen, stale lineage, channels, one STL, visibility/printability. Shared construction fix stays under `W5-U-04`. |
| `W5-U-05` | Unprioritized | DENTO-NOTE: dimension coupling, missing Reset/interactive inspection; source now places primary dimensions in expanded section 2 and reports the legacy guide-hole preflight error | Verify live section-2 editability, then plan owned geometry/parameter/stale Reset, interactive sizing and upstream-lineage validation; coordinate GUI/progress plans. |
| `VIEW-U-01` | Unprioritized | Cross-workflow normal-window display acceptance | Review grouped anatomy, presets/toggles, frame/restore, opacity, labels, save/reopen and Legacy/New parity. Missing controls owned by `VIEW-U-02`. |
| `VIEW-U-02` | Unprioritized | DENTO-NOTE: lost mask 2D/3D opacity controls | Written UX plan acceptance first: map ownership, persistent stage-safe fill/outline/surface controls and CBCT parity, then implementation and normal-window trial. |
| `S6-U-02` | Unprioritized | Physical forehead/mount-frame truth unresolved | Obtain mount-face CAD/normal; patient-contact→base transform, review, offsets/persistence/invalidation. Manual Simulation Base acceptance is insufficient. Shares physical metrology lane with `A-001`/`A-038`. |
| `S6-U-03` | Unprioritized | Experimental observed oral-air representation | Suitable open-mouth/phantom data; confidence labels, unobserved space remains occupied/unknown; never planning authority. |
| `CASE-U-01` | Unprioritized | Offline migrator for ROS-contaminated historical MRML/MRB | Define isolated no-ROS migration; distinct from normal `.dentocase` offline restore. |
| `PLAT-U-01` | Unprioritized | Clean pinned inference-image reconstruction acceptance | Rebuild and verify dependencies/backend/Bridge/Slicer/persistence; reconcile A-026 residual tests and transitive lock against current Ubuntu baseline. |
| `PLAT-U-02` | Unprioritized | Native Windows Steps 0–5 fallback real-host regression | Windows host; verify hidden Step 6/no auto-restore, no native Windows ROS. A-034 residual fallback acceptance. |
| `PLAT-U-04` | Unprioritized | Second direct-Engine WSL machine acceptance and immutable lab release | Exact manifest plus approved check-only/GUI/segmentation/simulation; isolated release revision, stable/lab/tag/image publication within authorization. |
| `PLAT-U-05` | Unprioritized | IITM CPU workstation regression after NVIDIA launcher integration | Documented check-only on IITM host; keep CPU unless CUDA intentionally adopted. |
| `PLAT-U-03` | Unprioritized | CRD/GDM overnight stability observation | Approved reboot/observation; preserve work. A-033 renderer/FPS follow-up remains distinct evidence within this platform lane. |
| `QA-U-01` | Unprioritized | Aggregate Slicer wrapper exits nonzero despite isolated PASS | Diagnose first wrapper/lifecycle failure; isolated PASS is not aggregate closure. |
| `ROS-U-01` | Unprioritized | Medical-image/transform interoperability design | Frame requirements stable; geometry-preserving contract before wider ROS scope; coordinate `A-004`/`A-022`. |
| `POC-U-01` | Unprioritized | Representative software → printed Template V0 → seating/registration → error budget | Freeze narrow task/thresholds; reuse template acceptance and `A-001`/`A-003`/`A-038` metrology instead of starting separate implementations. |

## Backlog — tracker obligations missing from the local queue

All rows below are **captured pending reconciliation**, not freshly verified
status or newly authorized execution. Preserve original IDs and owners. P0/P1
values are tracker metadata; `%` suffixes were allocation, not task priority.
Obtain current inputs before scheduling; old target dates are not renewed.
Grouped alias IDs represent one deliverable owner, not parallel workstreams.

| Canonical ID / tracker aliases | Tracker priority / owner | Pending deliverable | Dependencies, acceptance and overlap |
|---|---|---|---|
| `A-001` / `A-015` | P0 / Tarun | Complete CBCT→template→robot-base→end-effector→tool/tooth frame contract | Planning coordinates and CAD frames; named transforms, RAS/LPS, units, calibration/uncertainty and landmark round-trip. Reuse bounded software transforms; remaining full physical chain links `S6-U-02`, `A-022`, `A-038`. |
| `A-002` / `A-028` | P0 / Tarun | Compare head-mounted and tooth-mounted registration/validation chains | Head/mount and bite-block geometry/FOV/compliance; option matrix, calibration, TRE/repeatability, remount/failure gates. Coordinate `A-001` and `A-038`. |
| `A-003` / `A-016` | P0 / Tarun | Measurable error budget and validation plan | Clinical tolerances, mechanics, metrology; imaging→printing→seating→docking→TCP→drilling errors, target/angular/depth/TRE metrics with justified uncertainty propagation. Error-budget owner for `POC-U-01`. |
| `A-004` / `A-017` | P0 / Tarun | Remaining planning/navigation/robot/tracker interface contract | Current planning/mechanics interfaces; data/frame/update-rate/ownership and gates. Reuse Slicer/ROS architecture; align future `ROS-U-01`/`DHW-01..02`, no new transport by default. |
| `A-005` | P0 / Tarun | Tooth/bite-block-mounted mechanism concepts | Open-mouth geometry and actuator/tool envelopes; 2–3 annotated concepts with datums, disposable split, access/removal. Coordinate `W4C-U-01`; physical design scope requires current team inputs. |
| `A-006` / `A-024` | P0 / P1 respectively; Tarun | Structured registration/dental robotics evidence matrix and referenced clinical-workflow papers | Paper access; auditable procedure, architecture, motion handling, autonomy, validation and status with lessons. One literature deliverable; source priority conflict must be resolved before scheduling. |
| `A-008` | P1 / Shared | Approved pneumatic POC procurement package | Specifications/quotes and professor approval; reviewed BOM/cost/vendor/owner/arrival. Overlaps `A-037` supplies; no order authorized. |
| `A-009` | P0 / Varun | Representative planning/open-mouth/full-head dataset handoff | Suitable permitted de-identified imaging, anatomy/bite-block/tool geometry; frame-labelled STL and entry/target handoff. Input for mechanics and `POC-U-01`; confirm what is already delivered. |
| `A-010` | P0 / Snekan | Head-mounted five-DoF mechanism down-selection | STL/tool/workspace/mass/force and registration inputs; 1–2 concepts with base frame. External dependency, not an agent coding assignment. |
| `A-011` | P1 / Tarun | Approved clinical observation and constraint notes | Clinic permission/consent and coordination; observation-only pen-and-paper access/irrigation/control/removal notes. No messaging, visit or recording authorized by capture. |
| `A-013` | P1 / Shared | Human-in-loop physical safety/enable/foot-pedal state machine | Clinical/registration/controller inputs and verified safety process; quality/alignment/drilling-enable/failure/retry/e-stop gates. Preserve existing simulation guards; coordinate `DHW-01..02`. |
| `A-018` | P0 / Shared | Confirm integrated demonstration scope | Team alignment on target tooth, imaging, template, autonomy and TRL-4 criteria; preserve settled software single-target contract. One scope decision set feeds `POC-U-01`; no new clinical threshold assumed. |
| `A-022` / `A-029` | P0 / Tarun | Remaining frame-aware planning-to-mechanics handoff | `A-001`, recipient CAD/controller needs; mesh/trajectory/transform package with frame metadata and round-trip landmark proof. Reuse existing callable modules and `.dentocase`; physical/export boundary overlaps `W5-U-01`, `ROS-U-01`. |
| `A-036` | P1 in register / P2 dashboard; Tarun | Internal sensing invention package | Team/ICSR input, prior-art questions and required experiment evidence; reviewable confidential outline. Resolve source-priority conflict before scheduling; no external disclosure. |
| `A-037` / `A-007` | P1 / Tarun | Pressure/acoustic transition POC and protocol | Existing datasets, sensor/plumbing/sample/ground-truth inputs; repeatable positive or negative transition evidence and preserved configuration. Includes pending live flash/Hz Config-tab acceptance of existing sensing tools; no duplicate tool build or automatic drilling/flash authorization. |
| `A-038` | P1 / Tarun | Registration fiducial concepts and physical TCP/base/TRE repeatability | Geometry/material/phantom/mechanical inputs; ≥3 concepts with frames/detection/seating risks, select a measurement experiment. Coordinate `W4C-U-01`, `S6-U-02`, `POC-U-01`; four registration features are not proof of load-bearing docking. |
| `PRODUCT-DEFERRED` | Unprioritized / owner to confirm | Tracker-deferred panoramic/curved views, camera/intraoral scan, NPU, full canal automation and extra sensing modalities | Capture only, no accepted implementation plan. Split a bounded item only if it is selected and no existing owner covers it; software UI goes through `UI-P3-01`, ROS through `ROS-U-01`. Core PoC and actual input need first. |

## Overlaps to resolve when selecting work

| Pending scope / source aliases | Single owner and reuse rule |
|---|---|
| Tracker `A-023`, `A-032` template automation | `W5-U-04` construction; `W5-U-03` fusion/export acceptance; `W5-U-02` shell/fit; `W5-U-01` physical dimensions; `W4C-U-01` mechanics. Treat as linked acceptance slices, not a fresh template generator. |
| Tracker `A-035` trajectory assistance | `S4A-PULP-ENDPOINT` internal target and `W4-U-01` crown Entry. Old instruction to queue all assistance is superseded by later P0 correction. |
| Tracker `A-012`, `A-014`, `A-027` software/workflow umbrella | Reuse accepted Slicer architecture and implemented Steps 0–6. Remaining integration gates belong to `S6-REUSABLE-CASE-SETUP`, `S6-LIVE-01..05`, `POC-U-01` and `A-004`/`A-022` physical handoff. No architecture restart. |
| Tracker `A-026` inference robustness | `PLAT-U-01`; confirm cancellation/descendant cleanup, five old tests and lock requirements against current evidence before scheduling residual checks. |
| Tracker `A-033`, `A-034` marked complete but containing follow-ups | Retain only renderer/FPS and platform-host acceptance under `PLAT-U-03`, `PLAT-U-02`, `PLAT-U-04`, `PLAT-U-05`; migration itself stays closed. |
| Restore, stale target geometry, integrity UI | `S6-REUSABLE-CASE-SETUP` owns branch semantics; `S6-RESTORE-ROBOT-ROS` reconstruction; `S6A-CHANGED-TARGET-GEOMETRY` target cleanup; `S6-P2-01` presentation. Reuse one eligibility/invalidation backend. |
| Active reusable-case / Step 6 reposition implementation | Remains one `S6-REUSABLE-CASE-SETUP` lane. Wait for its handoff, then reconcile the actual diff and evidence before selecting residual work; do not start a second reposition, case-foundation or branch-activation implementation. |
| Track-A loop, baseline cleanup and exact FDI11 blocker | One authorized acceptance campaign can serve multiple IDs only when each gate is explicitly observed and recorded. A case-specific failure does not create another planner workstream. |
| Crown regions, jaw opening, Step 4A assistance | Agree shared source-fingerprinted anatomy semantics between `S6-P1-01` and `W4-U-01`; retain distinct workflow acceptance. |
| Studio, studies, old F0/F1/F2 | Only `DCP-*`/`DSS-*` roadmap; `.dentocase` stays package authority. No parallel `.dentostudy` store. |
| Registration, frame graph, fit and error budget | `A-001` frames, `A-002` architecture, `A-003` error budget, `A-038` metrology feed `POC-U-01`. Shared fixtures/evidence do not erase separate physical acceptance gates. |

Remove or rewrite overlap rows when their pending scope closes. Historical alias
and completion evidence belongs in TASKS.md/logbook, not as closed queue rows.
