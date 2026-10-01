# Project DentoCase — parallel foundation contract and evidence

## Current approved integration scope — 1 October

Tarun subsequently approved completing this integration with up to four GPT-6
Luna Max workers. The active destination is `DentoBot-step6-5.10-integration`,
branch `integration/step6-5.10-reviewed-20260927`; renovation is preserved source
provenance. This explicitly supersedes the earlier transfer hold and the earlier
renovation-only routing below. The coordinator owns integration, controlled
records and runtime; workers have disjoint implementation scopes. Available
concurrency is three workers plus the coordinator, so four worker scopes are
scheduled across released slots. The approved checks are combined host checks
and reserved offline persistence round trips; Tarun's browser/partial-case
continuation verdict remains required. Main promotion, publication, 5.12 and
robot/hardware operation are outside this scope.

## Historical foundation authorization and ownership

**Earlier operator integration hold (superseded above):** “imy not integrating further
implementation changes from step6checkout until they are fully implemented, tested
and verified.” Preserve this hold. The isolated foundation may continue; no merge,
installation or application wiring is authorized by its host-only evidence.

Tarun approved the revised five-phase plan on 1 October 2026. Existing owners remain
`DCP-09..10` (catalog/browser), `S6-REUSABLE-CASE-SETUP` (case semantics), and
`S6-P2-01` (integrity presentation). The later dated queue amendment received at
handoff sets their current priorities to 3, 1 and 3 respectively; the original
plan's 1/0/2 labels are historical. No priorities are changed by this implementation.
This is a
supporting specification and evidence record; `backlog.md` is the sole pending queue.

Develop in `DentoBot-step6-renovation`, preserving branch
`feature/step6-workflow-renovation-20260925` and all concurrent changes.
The first delivery is the independently invoked catalog and saved-lineage selector.
It cannot authorize a load, produce partial geometry, or confer live motion authority.

Coordinator owns `dentobot_case/contracts.py`, inert package initializer, this
record, design, review and acceptance. Exactly two GPT-6 Luna Max workers execute
disjoint contracts: lineage/checkpoint selection and its test; inspection/catalog/CLI
and its test. No worker edits existing production files or controlled records.

## Frozen interfaces

Plain immutable dataclass records describe checkpoints, artifacts, trajectory pairs,
case inventories and prefix selections. Semantic checkpoint IDs and definition
version are independent of archive schema and UI labels. Display order does not
replace prerequisite edges. Explicit artifact dependencies supplement checkpoint
dependencies. Unknown ownership/semantics blocks projection eligibility.

`select_prefix` checks target/branch ownership, predecessor closure and inseparable
pairs. Present stale/incomplete records remain present. A permitted selection gets
a new independent case ID and Fresh history policy; this is a selection preview,
not a saved package or an activated scene.

`inspect_package` is the only adapter importing `DENTOCaseBundle`. It reuses archive,
schema, checksum and runtime-separation validation. Every inventory has live freshness
Unverified. Legacy identity is package/content specific; file names never identify
teeth. Empty FDI registry placeholders do not establish available teeth.

SQLite stores rebuildable metadata and locations. Explicit folder scans never modify
source packages. Identical package copies share an entry; same package ID with
different bytes is a conflict. Missing/error locations remain visible. Opening must
revalidate the selected location independently of the catalog.

The verified explicit host entrypoint, from this checkout root, is:

```bash
PYTHONPATH=DENTOWorkflow/Resources/Python python3 -B -m dentobot_case inspect /chosen/case.dentocase
PYTHONPATH=DENTOWorkflow/Resources/Python python3 -B -m dentobot_case scan --database /chosen/library.sqlite /chosen/cases
PYTHONPATH=DENTOWorkflow/Resources/Python python3 -B -m dentobot_case list --database /chosen/library.sqlite
```

The database parent must already exist. Scans are explicit; there is no background
watcher or workflow startup scan. These examples use placeholders; the exact successful
synthetic commands and outputs are recorded below.

## Projection ownership audit — evidence boundary

Read-only source inspection covered `logic_case_bundle.py`, `widget_case_backend.py`,
`parameter_state.py`, `DENTOCaseBundle.py`, `DENTOStep6State.py` and existing branch
eligibility. The current workflow summary describes global node pointers and registry
records; it does not enumerate every persistent role or reference. It is insufficient
for safe partial MRB construction. Legacy inventories therefore remain ownership
incomplete, even when a tooth and prepared branch can be identified.

| Persistent group | Existing owner / required mapping before projection |
|---|---|
| Source volumes, reviewed teeth segmentation | Shared source/anatomy; preserve supporting segments and exact geometry |
| Case Foundation pose, landmarks, jaw gap, opened anatomy/volume proxies | `logic_case_foundation`; preserve exact transform graph and source references |
| Base placement, mount plane and forehead proxy | Shared placement owner; persisted configuration is not connected validation |
| Trajectories, target bounds and assisted entries | Stable registry target/trajectory IDs; never global-pointer or name-based deletion |
| Supports, boundary/plane/visible support and insertion direction | Branch geometry, support segment IDs and parameters; explicit pair ownership |
| Dock assemblies, channels, reinforcement and clearance models | Branch outputs, dimensions and orientation evidence; include all referenced auxiliaries |
| Contact shells, undercut/blockout, ROIs and research shell/sleeve models | Branch preparation; persistent auxiliary references need full MRML audit |
| Final printable model, trims, finalized shell, dynamic modeler state | Build artifacts versus verification evidence must have separate ownership |
| Home, workspace, task limits and planning diagnostics | Saved configuration/evidence only; live owner re-evaluates all restored state |
| Manual/study/planner/replay histories | Full load preserves compatible history; independent partial cases start fresh |
| Displays, view presets and volume rendering | Classify reconstructible display state separately from required geometry |
| Runtime bridge, guards, acknowledgements, preview authority | Excluded by existing persistence sanitation; never restore authority |

Checkpoint descriptors are conservative inventory labels, not an audited pruning map
or replacements for existing eligibility gates. In particular, final printable geometry
may be produced during 5B before 5C verification. No partial writer is released until
that distinction and every persistent parameter/reference have been audited.

## Shared-file handoff reservation

The Step 6 chat confirmed the new package/tests are disjoint and its persistence owners
are frozen during final regression. It retains Step 6 production files, tests, matrix
and shared records. Requests for later handoff have been sent; no shared handoff has
yet been accepted here.

| File group | Proposed bounded later change |
|---|---|
| `DENTOCaseBundle.py` | Stable case/package identity and versioned inventory; retain schema 1/2 reads/manual records |
| `logic_case_bundle.py`, `parameter_state.py` | Audited inventory, identity and owned persistent-state mapping |
| `widget_case_backend.py` | Recovery-backed full/partial activation, independent Save As, source preservation |
| `DENTOWorkflow.py`, CMake, bootstrap/UI resources | Explicit browser wiring and installation after core verification |
| Verification matrix | Focused entries after matrix ownership is released |
| Controlled records and Graphify | Serialized checkpoint after Step 6 coordinator freezes its writes |

Before any transfer, capture exact HEAD, current diff/hash, new owner and bounded edits.
One session writes each shared file at a time. No runtime reservation is active here.

## Implementation record

Coordinator created inert `__init__.py` and `contracts.py`; corrected the workspace
parameter descriptor to the actual persisted `step6AssistedLimitProposalJson` after
reading the full parameter state. Workers are implementing their assigned new files.
Read-only commands included `git status --short`, scoped `sed`/`rg` source and controlled
record reads, and compact chat inspection. No source package, existing production file,
installation, branch, runtime or shared graph was modified.

Verification results will be recorded below after files freeze. Foundation acceptance
requires focused host checks, actual diff review and the handoff list; overall browser,
projection, round trips and Tarun's continuation acceptance remain separate gates.

### Lineage worker evidence

Coordinator reviewed the actual new source and synthetic tests, requiring missing pair
member detection at trajectory and branch cutoffs, artifact dependency cycles/self edges,
later-checkpoint dependency rejection, and valid same-checkpoint acyclic references.
Worker froze `lineage.py` and `Testing/test_dentocase_lineage.py` and reported
`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider Testing/test_dentocase_lineage.py`
— **10 passed**, exit 0, 0.02 seconds. Synthetic host evidence only; coordinator combined
verification is recorded below.

### Synthetic command-line fixture preparation

A host-only fixture was prepared at `/tmp/dentocase-foundation-20261001-aypz31ru`
using existing `create_case_bundle` and `build_robot_profile`: a minimal `<MRML/>`
archive, synthetic robot description, one explicitly populated FDI11 registry record,
one empty FDI12 placeholder and saved Home Unreviewed. The preparation command used
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=DENTOWorkflow/Resources/Python python3` and
exited 0. This contains no patient data and establishes no Slicer restore/geometry
behavior. CLI demonstration remains pending until its implementation freezes.

## Shared production reservation snapshot

HEAD `e7cd29f8afec76a7f4ec37d72902beda0f6843d2`. Read-only snapshot; ownership is still reserved by Step 6.

| File | Current SHA256 | HEAD diff |
|---|---|---|
| `DENTOWorkflow/Resources/Python/DENTOCaseBundle.py` | `412b1f92fe0a37a13fb126d57520f1265c5b5ebb5cb0100af38a738559f66245` | clean |
| `DENTOWorkflow/Resources/Python/DENTOStep6State.py` | `c4b3be0f14e2966cc0541ed221669b0b07e61968e2b84eccfda67be802315975` | clean |
| `DENTOWorkflow/Resources/Python/dentobot_workflow/logic_case_bundle.py` | `acd24ce8859509773ebe7e0e8d5a7cf82358207a4405e9bb4a8e8824cf250ca4` | clean |
| `DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py` | `da95889126bc49f964f8b265adfff95e3499a1f578a81c9fe8f528556bbc056a` | clean |
| `DENTOWorkflow/Resources/Python/dentobot_workflow/parameter_state.py` | `0c0b5a931eb5972b87a010fbf8c637748d981099e363be693dc60d554e749ca7` | clean |
| `DENTOWorkflow/DENTOWorkflow.py` | `05d9032614e84605d05559b4c5a739066e763553e980f23c86c82ec74fc1c17d` | clean |
| `DENTOWorkflow/CMakeLists.txt` | `14240bfab1f72993ba0066c4465cb40d4e47113b50f7cfe11e59b6cc7d750ef3` | clean |

## Controlled-record handoff accepted

The Step 6 coordinator explicitly released these records for DentoCase append-only updates and existing DCP row state changes. Step 6 source/matrix remain excluded. Overlay Graphify refresh is released only after DentoCase source freezes.

| Record | Pre-edit SHA256 | HEAD diff SHA256 |
|---|---|---|
| `Workspace/docs/backlog.md` | `c0044a8cab372232c540fe74ff94930a2b8fe5899a286ec04af8b1914f461f42` | `bce7356d902637dee33a02891d3867147a87e585b182985ba314a8c573c582c7` |
| `Workspace/docs/TASKS.md` | `3c8c687d8e829d29509fd310e1d4d0d99e4b5a076c43f8aef07ac5bb1078f84b` | `3878e571f8360c6609bfdf2cee88ddd49863392a682e4028fc31ba710a9a693d` |
| `Workspace/docs/DEVELOPMENT_PLAN.md` | `40e8b945d2873ff4695181832033b919c2f83e8c452764d7c2bf0f53ef1eee4b` | `8a3f021df51f879a0ff70d6d442bc39f27b106a8f8805a7a5de63f8d17a4b786` |
| `Workspace/docs/DECISIONS.md` | `7fe1e411e68589dd8e1d5c604fb7a1cfee298cee44c248671931bf6839fc9636` | `b5bcaec004c6d3ecd42bfe9c6d64820904d39aca05384d29c23fca496a24678e` |
| `Workspace/docs/logbook/2026-10-01.md` | `e704918ce51bae5ba4a39875c632d5e18dc9e4b92e7b30956ce0b8cd930104f8` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |


## Foundation verification — 1 October 2026

Coordinator reviewed all six new package modules and three focused test files. Final combined command, from the renovation checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider Testing/test_dentocase_lineage.py Testing/test_dentocase_catalog.py Testing/test_dentocase_boundaries.py --junitxml=/tmp/dentocase-foundation-20261001-aypz31ru/foundation-tests.xml
```

**36 passed in 0.54 s, exit 0.** Coverage includes stable checkpoint renaming/insertion, dependency closure/cycles/later edges, same-checkpoint references, missing prerequisites, stale retention, explicit pairs, target/branch isolation, independent prefix IDs/Fresh policy, schema1/2 inspection/manual history, UUID identity/mismatch, two revisions grouped under one declared case, unknown semantics, source mutation, copies/conflicts/missing/changed/error scans, database compatibility and rollback, symlink exclusion and inert imports/no startup wiring. Fixtures are synthetic, including future identity fields inserted into test manifests; the production writer still does not emit stable case identity/inventory.

Catalog worker history: initial scoped run2 failed / 17 passed (assertion assumed only one unknown reason; wrong root-error group selected), second1 failed / 18 passed (unbound root-error group still selected). Assertions were corrected to locate the actual package row and accept concrete legacy unknown reasons; production source was unchanged for those failures. Raw regex removed SyntaxWarning. Third19 passed; after requested UUID/Home/history regressions, final23 passed in 0.20 s. Lineage worker10 passed. No extra runtime or broad test reruns.

CLI demonstration used only `/tmp/dentocase-foundation-20261001-aypz31ru/cases`: inspect synthetic.dentocase; scan with --database /tmp/dentocase-foundation-20261001-aypz31ru/library.sqlite; list the same database. Each subprocess was `python3 -B -m dentobot_case` with PYTHONPATH=DENTOWorkflow/Resources/Python. All three exited0 with strict JSON; two identical source copies grouped into1 case / 1 revision / 2 locations. Home remained Unreviewed/liveUnverified; original fixture SHA unchanged. Exact argument lists/output JSON are in cli-commands.json and inspect/scan/list-output.json at that fixture root.

Read-only representative inspection of the recorded r29 package at `/home/light-tarun/dentobot/data/Slicer_Saved/SampleStudy1/SEPT24/oct01_fdi11_offline_home_r29.dentocase` exited0: schema2.0, Valid integrity,3 populated targets,3 branches,15 known outer artifact records,0 manual records, saved Home revision 24/Unreviewed, liveUnverified. SHA256 remained 2b80f595f39d9e79d547bbfce1c7d61b0a1feef393175ab92f442cd9210b7c93. Ownership remained incomplete, so partial projection is blocked. No case geometry was loaded into Slicer and no real case folder was scanned or indexed.

Host compile/whitespace check on 9 new source/test files passed; seven reserved production SHA256s and exact branch/HEAD remained unchanged. `git diff --check` exited0. Source hashes, result scope and production-preservation counts are in source-evidence.json at the fixture root. Graph maintenance is recorded separately below.

**Accepted boundary:** catalog/lineage foundation is source/host verified and the file handoff list is ready. Overall DentoCase remains pending under the existing backlog row: audited projection, production identity/schema, browser, save/load transactions, fresh round trips and Tarun's continuation verdict are not implemented/accepted here. Integration hold remains active.


### Serialized graph and final checkpoint

`Workspace/scripts/graphify-update.bash` first exited 1: sandbox blocked extraction worker creation (`Operation not permitted`). Same command with authorized sandbox escalation exited 0 and printed `Code graph updated` / `graphify-update: OK under /home/light-tarun/dentobot`: 38,153 nodes, 62,527 edges, 2,464 communities, 68 uncached files extracted. Nine existing C++ parser limitations remain partial graph extraction warnings; nine new Python source/test files compiled successfully. Curated-node retention and community-label notices were preserved; no labeling, ignore-policy change or nested source graph was performed. This is graph maintenance, not a Slicer/runtime acceptance check.

Foundation source/tests and controlled records are frozen at this checkpoint. The existing DCP backlog row remains open for audited projection/application/round-trip/operator gates. No production schema/identity/writer/loader/startup/CMake/matrix edit, installation, runtime, merge, commit or push occurred. Tarun's integration hold is preserved.

## Integration authorization and file handoff — current operator supersession

Tarun states no other implementation is active and authorizes proceeding to complete integration, using up to four Luna Max workers. This supersedes the earlier implementation/integration hold within this checkout. Available concurrency is three workers plus coordinator; no branch/commit/push/main merge requested. Root owns production mapping, activation and controlled records; worker schema owns DENTOCaseBundle.py, browser owns new case_library.py, projection owns new pure projection.py. Runtime round trips are offline/no ROS, serialized, no operator-scene replacement; operator visual acceptance remains explicit.

HEAD e7cd29f8afec76a7f4ec37d72902beda0f6843d2

| Reserved file | Current bytes SHA256 | Diff SHA256 | New owner |
|---|---|---|---|
| DENTOWorkflow/Resources/Python/DENTOCaseBundle.py | f61fb164c3a9f5c33c83a2d2d4c0b39d0ad3c0aee64b6a4b52649e991ae0648d | e9eeaf91f36207a97c6f75e7811085157a3f33c2bf3cc62a0afcd414f2c764bd | schema worker |
| DENTOWorkflow/Resources/Python/dentobot_workflow/parameter_state.py | 0c0b5a931eb5972b87a010fbf8c637748d981099e363be693dc60d554e749ca7 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | coordinator |
| DENTOWorkflow/Resources/Python/dentobot_workflow/logic_case_bundle.py | acd24ce8859509773ebe7e0e8d5a7cf82358207a4405e9bb4a8e8824cf250ca4 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | coordinator |
| DENTOWorkflow/Resources/Python/dentobot_workflow/widget_case_backend.py | da95889126bc49f964f8b265adfff95e3499a1f578a81c9fe8f528556bbc056a | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | coordinator |
| DENTOWorkflow/Resources/Python/dentobot_workflow/widget_bootstrap.py | 263b6f3472f8338d178c0688c678afe716211609717454a525db7b3a6fb9ee84 | 7b24f6cbab20fffaf715a54c20a7e4f758683a4068627640a3963ef65bd0a5e8 | coordinator |
| DENTOWorkflow/DENTOWorkflow.py | 05d9032614e84605d05559b4c5a739066e763553e980f23c86c82ec74fc1c17d | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | coordinator |
| DENTOWorkflow/CMakeLists.txt | 14240bfab1f72993ba0066c4465cb40d4e47113b50f7cfe11e59b6cc7d750ef3 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | coordinator |
| Testing/verification_matrix.json | f19ac1c326df4c2c9ccbd0b8d6cf78f8915aff5a46820fbea33e74da58c4a92f | d2a0a80acc37bbeb7cb28cfc445f26c22fa160a62d67464e7c5b3969eeaa7da1 | coordinator |

## Integration preservation checkpoint — checkout consolidation requested

A coordination message from the Performance upgrades chat reports Tarun selected `/home/light-tarun/dentobot/ros2_ws/src/DentoBot-step6-5.10-integration` (`integration/step6-5.10-reviewed-20260927`) for future work to preserve accepted 5.10 performance changes. Further implementation writes in renovation are held. No files copied, branch/HEAD changed, staged, committed, reset or merged. The replacement ownership worker was told to stop before new edits; it had not created the inventory adapter at checkpoint inspection.

Implemented but not accepted: schema-3 stable case UUID metadata with schema1/2 reads and manual history; pure projection planning; asynchronous library browser; initial identity/backend/CMake wiring; offline projection executor draft. This is an incomplete source integration: `case_inventory.py` is absent and production saves currently reference it. Do not deploy this checkpoint. Offline executor draft still requires the probed launcher executable and python-code invocation correction; applicationFilePath is a Qt slot, not a string executable. No partial package has been produced or reopened.

Verification: schema worker 11 passed; browser worker final4 passed after1 fixture expectation correction; projection worker4 passed; combined host command covering six DentoCase suites plus existing test_case_bundle produced **76 passed, 3 failed** (schema-default fixture compatibility assumptions in test_dentocase_catalog). Fixes to those three fixtures were dispatched but interrupted before verified completion. Existing foundation36 passed remains historical evidence. `git diff --check` at preservation checkpoint exited0. Two initial disposable Slicer script invocations exited0 without script markers (not accepted evidence); final bounded python-code invocation printed API/wrapper/node evidence and exited0. No ROS initialization, robot operation, operator-scene replacement or shared installation rebuild occurred. Logs are `/home/light-tarun/dentobot/data/test-artifacts/dentocase-integration-20261001/probe*.log`; exact DentoCase source SHA256 list is `source-checkpoint.json` there.

Pending integration remains in the existing DCP-09..10 backlog contract. Reconciliation must preserve these unaccepted edits and the accepted performance checkout; then finish ownership mapping, invocation correction, host checks, offline full/partial round trips and Tarun browser/continuation review. No acceptance or completion is declared.


## Verified integration update — 2026-10-01

Source consolidation into `integration/step6-5.10-reviewed-20260927` and synthetic native persistence gate are complete. Offline attempt4: PASS, exit0, teardown clear; evidence `data/test-artifacts/dentocase-integration-20261001/integration-roundtrip-attempt4/result.json`. Final matrix host union:558 passed2.66s, exit0. This establishes software behavior for full/partial package identity, paired cutoff/reopen, independent continuation/Save As and failed-load recovery. It does not establish live motion authority or Tarun’s operator acceptance. Integration commit checkpoint and final browser/continuation verdict remain open under existing backlog owners.


**Local integrated source checkpoint:** `50ce2089342aeeac9a319bf6353809252cb70e23` (`50ce208`) on `integration/step6-5.10-reviewed-20260927` contains the55reviewed source/test files. Renovation commits were already ancestors; this checkpoint records the reconciled later dirty development delta and DentoCase integration. Accepted performance-owner files remain byte-identical to a795f89. Matrix host558PASS, offline persistence attempt4PASS/exit0/clear teardown, presentation4PASS and modular5PASS provide the bounded software evidence. No main merge or push. Overall Project DentoCase remains awaiting Tarun's library/independent continuation verdict under DCP-09..10; broader Step6 robotics/responsiveness acceptance remains in its existing owners.
