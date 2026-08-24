# DENTOBOT GUI Action Parity Inventory

Status: active migration inventory, 2026-08-24

This inventory classifies the interactive action surfaces during the Legacy to
six-workspace shell migration. Child controls inherit the classification of
their owning action group. The shell reparents the single authoritative
`DENTOWorkflow.ui` tree, so no existing action is omitted or copied while its
presentation is pending migration.

| Action surface | Internal stages | Current classification | Backend authority | Migration state |
|---|---:|---|---|---|
| Fixed developer header, reload, case/runtime warning | all | New Advanced UI | Workflow lifecycle | Shared and visible |
| Legacy Previous/Next and eleven-stage selector | 0–10 | Temporary Legacy UI | Stage controller only | Hidden in shell; restored exactly |
| Six-workspace navigation, task header and substeps | 0–10 | New routine UI | Stage controller only | Implemented |
| Theme and Focus/Expert controls | all | New Advanced UI | `QSettings` presentation only | Implemented |
| Case identity, reset, MRB and `.dentocase` save/open | 0 | New routine UI via authoritative existing controls | Case transaction/MRML | Shell vertical slice |
| Case validation, Current/Stale and lineage details | 0 | New routine + Advanced detail | Parameter node/case bundle | Shell vertical slice |
| DICOM import, volume selection, metadata/display | 1 | Temporary Legacy UI | Slicer DICOM/MRML | Visual migration pending |
| AI inference, progress/cancel and backend details | 2 | Temporary Legacy UI; backend details Advanced | External adapter/MRML | Visual migration pending |
| Segmentation review/correction/display | 3 | Temporary Legacy UI | Segmentation MRML | Visual migration pending |
| Manual/assisted trajectory, locking and metrics | 4 | Temporary Legacy UI | Markups/parameter node | Visual migration pending |
| Support anatomy and docking (4B/4C) | 5–6 | Temporary Legacy UI | Existing geometry logic | Visual migration pending |
| Visible support, shell/fusion, verify/export (5A–5C) | 7–9 | Temporary Legacy UI | Existing geometry/lineage logic | Visual migration pending |
| Elements viewer and view presets | all | New routine UI through shared existing controls | MRML display only | Shared; drawer redesign pending |
| Robot scene/runtime capability and connection | 10 | New routine UI | Robot workflow façade | Implemented |
| Robot mount plane, base snap/nudge/lock | 10 | New routine UI through authoritative existing controls | Façade/placement logic | Implemented |
| Six manual joint controls and task limits | 10 | New routine UI through authoritative existing controls | Façade/parameter node | Implemented |
| TCP goal, MoveIt IK and goal plan | 10 | New routine UI | Façade/MoveIt KDL | Implemented |
| Planning-scene sync and state validity | 10 | New routine UI | Façade/MoveIt PlanningScene/FCL | Implemented |
| Draft Halton/FK/AABB workspace cloud | 10 | New Advanced UI | Existing workflow logic via façade | Implemented and labelled approximate |
| Entry-to-Target plan, preview and Stop | 10 | New routine UI through authoritative existing controls | Façade/MoveIt | Implemented |
| Generic SlicerROS2 Parameters/Topics/TF2/Robots | 10 | Temporary Legacy diagnostic | SlicerROS2 | Expert access only; not duplicated |
| Generic Motion Control Execute | 10 | Confirmed duplicate/removal | None authorized | Hidden and disabled |

Parity rules for each later migration are: compare cloned scenes for MRML node
roles/references, parameter values, Current/Stale state, geometry bounds and
hashes, lineage, exported files, error behavior, scene reopen, and module
reload. Presentation navigation and theme changes must produce no geometry or
lineage mutation. A row moves out of Temporary Legacy only after those checks
are recorded.
