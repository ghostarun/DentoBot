# Stage 6 target-matrix preflight — 2026-09-13

This is a read-only input audit. It is not planner, collision, runtime, or
operator acceptance evidence.

## Required target status

| Target | Available material | Current-case result | Blocking reason |
|---|---|---|---|
| FDI31 | `SampleStudy1/FDI31/run2-dentobot-case-step6x5.dentocase` | Blocked | Outer 2.0 is valid, but inner DentoCase state is 2.0, Case Foundation environment is 1.0, and the PreparedBranch registry is 2.0. It is a legacy branch package, not a current schema-3 package. |
| FDI32 | `dentobot-runs/case13sept-fdi32-repaired*` copies | Blocked | Every inspected copy is lineage-labelled FDI31. No lineage-valid FDI32 package exists. |
| FDI11 | `SampleStudy1/FDI11/*.dentocase` | Blocked | Available packages are outer/inner schema 1.0 and contain no current Case Foundation or PreparedBranch state. |
| FDI12 | none | Blocked | No reviewed `.dentocase` input exists. |
| FDI13 | none | Blocked | No reviewed `.dentocase` input exists. |
| FDI14 | `SampleStudy1/FDI14/*.dentocase` | Blocked | Available packages are outer/inner schema 1.0 and contain no current Case Foundation or PreparedBranch state. |

## Additional inspected material

`SampleStudy1/dentobot-case-13sept.dentocase` and its repaired diagnostic copies
do contain inner DentoCase state 3.0, environment 2.0, and registry 3.0, but the
registry contains zero PreparedBranches and the trajectory lineage is FDI31.
Those copies therefore cannot serve as FDI32, FDI12, or FDI13 inputs and cannot
pass the exact-case current-save contract.

FDI44 packages are present but are outside the requested six-target matrix.

## Acceptance consequence

The serialized matrix must not start. The required six-entry reviewed manifest
does not yet exist. Producing one by relabeling, duplicating, or synthesizing a
package would invalidate target identity and exact-package integrity.

The next valid input state is one regenerated/reviewed current package for each
FDI31, FDI32, FDI11, FDI12, FDI13, and FDI14, each with outer schema 2.0,
inner DentoCase schema 3.0, Case Foundation environment 2.0, registry schema
3.0, exactly one selected current PreparedBranch, current Step 5C schema 2.0
evidence, and a matching trajectory FDI identity.

Source of facts: read-only ZIP member inspection of every host
`/home/light-tarun/dentobot/**/*.dentocase` file on 2026-09-13. No archive was
modified, renamed, migrated, or opened in Slicer during this audit.
