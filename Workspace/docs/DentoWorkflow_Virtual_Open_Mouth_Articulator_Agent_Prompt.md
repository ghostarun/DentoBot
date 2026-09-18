# DentoWorkflow Virtual Open-Mouth Articulator
## Implementation Prompt / Algorithm Specification for Agent

### Context

This task belongs to the DentoBot / DentoWorkflow TRL-4 prototype.

The purpose of this feature is **not** to reconstruct exact patient-specific TMJ biomechanics. The purpose is to generate a **repeatable, anatomically plausible open-mouth mandibular pose** from a closed-mouth pre-operative CBCT so that robot workspace, gross collision, reachability, trajectory access, and simulation can be evaluated.

The system must work best when both mandibular condyles are available in the CBCT, but it must degrade gracefully when the CBCT FOV excludes the condyles and only the dentition / dental arch and incisors are available.

The desired architecture is therefore:

> **One open-mouth transform solver with two possible sources for the virtual condylar axis.**

Do **not** implement separate “anatomical TMJ” and “mean-value TMJ” motion engines.

Instead:

1. Prefer **patient-specific condylar geometry** when bilateral condyles are visible.
2. Otherwise infer a **virtual condylar axis** from dental anatomy using mean-value articulator geometry.
3. Feed either axis into the **same mean-value kinematic opening solver**.
4. Produce the same downstream output: a rigid `MandibleOpenTransform`.

The algorithm is a **simulation prior only**. It must never be treated as surgical registration truth.

---

# 1. Primary Design Principle

The feature should have one public conceptual model:

```text
Virtual Open-Mouth Articulator
```

Internally:

```text
Closed-mouth CBCT
        |
        v
Dental / jaw segmentation
        |
        v
Determine virtual condylar axis
        |
        +--> bilateral condyles available
        |        |
        |        v
        |   patient-derived axis
        |
        +--> condyles unavailable / unreliable
                 |
                 v
          arch-derived virtual axis
                 |
                 v
        SAME opening kinematics
                 |
                 v
      requested opening distance
                 |
                 v
       MandibleOpenTransform
```

The downstream planning pipeline must not care which hinge-source mode produced the transform.

---

# 2. Scope

## In scope

- Closed-mouth CBCT input.
- Full-FOV or partial-FOV dentition.
- Segmented mandible / teeth and, where available, bilateral condyles.
- Automatic extraction of useful dental landmarks where deterministic geometry is sufficient.
- Manual correction / override of derived landmarks.
- Patient-derived condylar axis when bilateral condyles are usable.
- Mean-value arch-derived axis when condyles are absent.
- Rigid-body opening transform of the entire mandibular assembly.
- Rotation + coupled anterior/inferior translation.
- User-specified target mouth opening.
- Explicit provenance / confidence metadata.
- Repeatable deterministic output.
- Visual QA support in 3D Slicer.
- Save/load through `.dentocase`.

## Out of scope for TRL-4

Do NOT implement:

- FEM TMJ mechanics.
- Articular disc modelling.
- Muscle force simulation.
- Ligament mechanics.
- Patient-specific functional jaw tracking.
- Prediction of the patient's true maximum opening from CBCT.
- Dynamic occlusal-contact modelling.
- Realtime perception.
- Surgical registration based on this transform.
- Exact clinical reproduction of TMJ trajectory.
- Automatic learning / ML landmark detection unless already available and trivial to integrate.

Avoid expanding scope unless required to make the core algorithm correct.

---

# 3. Scene-State Rule

DentoWorkflow must distinguish three classes of information:

```text
OBSERVED
DERIVED
SIMULATED
```

## Observed

Immutable source data from the scan:

- CBCT volume.
- Original segmentation.
- Maxilla.
- Mandible.
- Individual teeth.
- Pulps if available.

Observed data must never be silently modified by the open-mouth operation.

## Derived

Computed geometry:

- Dental arch.
- Occlusal plane.
- Incisor midpoint.
- Left-right axis.
- Anterior-posterior axis.
- Condylar centres if visible.
- Virtual condylar centres if inferred.
- Virtual condylar axis.
- Solver parameters.

All derived geometry must be inspectable and reproducible.

## Simulated

Only the simulated open-mouth state:

- `MandibleOpenTransform`
- cloned / transformed visualization objects if required
- robot-world simulation using the open-mouth pose

Never overwrite the original CBCT-space anatomy.

---

# 4. Required Inputs

At minimum, the fallback mode requires:

- lower central incisors OR a stable approximation of the mandibular incisor midpoint;
- enough mandibular dental-arch geometry to estimate left-right and anterior-posterior directions;
- an estimate of mandibular occlusal orientation;
- rigid mandibular geometry to transform.

Preferred inputs:

- segmented mandible;
- labeled mandibular teeth;
- maxillary teeth / arch;
- maxillary central incisors;
- left condyle;
- right condyle.

Optional:

- manually entered interincisal opening;
- manually corrected landmarks;
- manually selected condylar centres;
- manually specified motion parameters.

---

# 5. Coordinate Conventions

Create an explicit mandibular dental coordinate frame.

Recommended notation:

```text
x_hat = left-right axis
y_hat = anterior direction
z_hat = superior direction
```

The exact sign convention may follow the existing Slicer / RAS conventions, but the implementation must convert consistently and document it.

The algorithm should derive a local frame from dental anatomy rather than rely on raw world axes.

Recommended construction:

1. Determine the mandibular central-incisor midpoint `I_m`.
2. Fit a mandibular arch curve or use labeled tooth centroids.
3. Estimate the left-right direction from bilateral teeth / arch width.
4. Estimate the anterior direction from posterior arch centroid toward `I_m`.
5. Build an orthonormal basis.
6. Use the mandibular occlusal plane normal to stabilize the superior direction.
7. Correct signs using known anterior tooth positions.

Result:

```text
F_dental = {origin, x_hat, y_hat, z_hat}
```

Store it as derived data.

---

# 6. Landmark Extraction

## 6.1 Mandibular incisor midpoint

Preferred:

- use FDI 31 and FDI 41 crown geometry if both are available;
- determine an approximate crown centroid or mesial-incisal reference;
- take midpoint between the two.

Fallback:

- derive midpoint from the anterior extreme of the mandibular arch;
- allow manual correction.

Name:

```text
I_m
```

## 6.2 Maxillary incisor midpoint

Equivalent operation using FDI 11 and FDI 21 where available.

Name:

```text
I_u
```

This is primarily useful for measuring simulated interincisal opening and sanity checking midline deviation.

## 6.3 Occlusal plane

Do not derive the plane from only three arbitrary points if more dental geometry is available.

Preferred approach:

- use crown-centre / occlusal-surface representative points from multiple teeth;
- robustly fit a plane;
- exclude obvious outliers / missing teeth;
- use anterior and posterior teeth where possible.

Store:

```text
P_m = mandibular occlusal plane
P_u = maxillary occlusal plane
```

The two-plane intersection is **NOT** the hinge axis.

The planes are used for:

- frame orientation;
- sanity checks;
- opening direction;
- visualization;
- fallback geometry.

---

# 7. Hinge Source Selection

The open-mouth solver must accept one unified representation:

```text
VirtualCondylarAxis
    left_point
    right_point
    midpoint
    axis_direction
    source
    confidence
```

Valid source values:

```text
PATIENT_CONDYLES
ARCH_INFERRED
MANUAL
```

## 7.1 Patient-derived axis

Use this when bilateral condyles are sufficiently visible and reliable.

Inputs:

```text
C_L
C_R
```

Compute:

```text
H = (C_L + C_R) / 2

x_axis = normalize(C_R - C_L)
```

Do not attempt advanced patient-specific fossa / eminence motion modelling for TRL-4.

Patient anatomy is used primarily to anchor:

- axis location;
- intercondylar distance;
- transverse orientation.

The motion itself still uses the shared mean-value kinematic model.

### Condyle centre extraction

If condyle segmentation exists:

- identify left and right condylar head regions;
- estimate a robust geometric centre;
- avoid taking the centroid of the entire ramus / mandible;
- use a local condylar ROI if needed.

If automated extraction is uncertain, display candidate centres and allow manual correction.

### Validity checks

Patient-derived axis is accepted only if:

- both sides are present;
- intercondylar distance is within a broad plausible range;
- axis orientation is roughly transverse relative to the dental frame;
- neither point is obviously inside dental / anterior regions;
- segmentation quality is not obviously broken.

If any gate fails, fall back to `ARCH_INFERRED`.

Do not force the anatomical mode when inputs are unreliable.

---

# 8. Arch-Inferred Virtual Condylar Axis

This is the reduced-FOV fallback.

The algorithm should behave like a digital mean-value articulator.

It should use:

- mandibular incisor midpoint;
- dental coordinate frame;
- patient arch scale;
- configurable Bonwill-like side length prior;
- configurable intercondylar-distance prior;
- configurable Balkwill-like elevation angle prior.

The values must be treated as **simulation priors**, not anatomical truth.

---

## 8.1 Reference priors

Use configurable defaults rather than hard-coded magic numbers.

Suggested initial defaults for experimentation:

```text
reference Bonwill side length:       ~100-105 mm
reference intercondylar distance:    ~95-105 mm
reference Balkwill elevation angle:  ~20-25 degrees
```

Keep these in a configuration structure.

Example:

```python
VirtualArticulatorConfig:
    bonwill_side_mm
    intercondylar_distance_mm
    balkwill_angle_deg
    condylar_guidance_angle_deg
    max_translation_mm
    rotation_translation_profile
```

All values must be editable centrally.

---

## 8.2 Patient arch scaling

Do not blindly use a 100 mm mean-value geometry for every patient.

Estimate a scalar from the observed mandibular arch.

Possible arch metric:

- inter-molar width if molars exist;
- inter-premolar width;
- total arch span;
- fitted arch width;
- combination of multiple tooth centroid distances.

Let:

```text
A_patient = measured patient arch metric
A_reference = reference population arch metric
```

Then:

```text
s_raw = A_patient / A_reference
```

Clamp to a conservative range:

```text
s = clamp(s_raw, s_min, s_max)
```

Example initial bounds might be approximately:

```text
0.85 <= s <= 1.15
```

but the actual range should be configurable and validated experimentally.

Then:

```text
L_B = s * L_B0
B   = s * B0
```

where:

```text
L_B0 = reference Bonwill side length
B0   = reference intercondylar distance
```

If the available FOV is too small to estimate arch scale reliably, use `s = 1.0`.

Record that reduced confidence.

---

## 8.3 Virtual axis construction

Let:

```text
I = mandibular incisor midpoint
x_hat = left-right
y_hat = anterior
z_hat = superior
beta = Balkwill-like angle
L_B = Bonwill-like side length
B = intercondylar distance
```

The sagittal distance from the incisor point to the virtual condylar-axis midpoint is:

```text
r = sqrt(L_B^2 - (B/2)^2)
```

Require:

```text
L_B > B/2
```

Otherwise configuration is invalid.

Construct the virtual midpoint:

```text
H* = I - r*cos(beta)*y_hat + r*sin(beta)*z_hat
```

Then:

```text
C_L* = H* - (B/2)*x_hat
C_R* = H* + (B/2)*x_hat
```

Signs may need to be swapped depending on the established coordinate convention.

The essential geometry is:

- posterior to incisors;
- superior to occlusal plane;
- transverse axis;
- scaled approximately to patient dental size.

Store:

```text
left_point  = C_L*
right_point = C_R*
midpoint    = H*
axis        = normalize(C_R* - C_L*)
source      = ARCH_INFERRED
```

Visualize these points and the axis in Slicer.

---

# 9. Unified Mean-Value Opening Kinematics

Both hinge-source modes feed this exact same solver.

Inputs:

```text
mandibular rigid-body nodes
virtual condylar axis
upper incisor reference
lower incisor reference
target opening_mm
kinematic config
```

Output:

```text
MandibleOpenTransform
```

Do not implement pure hinge rotation.

The motion must contain:

1. mandibular rotation around the transverse axis;
2. coupled anterior/inferior translation of the virtual condylar axis.

---

# 10. Opening Parameterization

Use a normalized opening parameter:

```text
q in [0, 1]
```

where:

```text
q = 0 -> closed
q = 1 -> configured maximum simulated opening
```

Do not assume that `q = 1` is the patient's true biological maximum.

It is only the current simulation profile maximum.

Define:

```text
theta(q) = mandibular rotation
d(q)     = condylar translation magnitude
```

Initially, a simple smooth monotonic coupling is sufficient.

Examples:

```text
theta(q) = theta_max * f_rot(q)
d(q)     = d_max * f_trans(q)
```

where `f_rot` and `f_trans` are smooth monotonic functions.

A simple first implementation may use:

```text
f_rot(q)   = q
f_trans(q) = q^p
```

with configurable `p`, or a piecewise curve where early opening is more rotation-dominant and later opening includes more translation.

Do not overfit this for TRL-4.

The objective is plausibility and repeatability.

---

# 11. Condylar Guidance Direction

Construct an anterior/inferior translation direction in the dental frame.

Let:

```text
gamma = configurable condylar-guidance angle
```

A generic guidance vector can be represented as:

```text
g_hat = cos(gamma)*y_hat - sin(gamma)*z_hat
```

depending on coordinate sign convention.

Normalize it.

Then:

```text
translation(q) = d(q) * g_hat
```

This moves the virtual axis anteriorly and inferiorly during opening.

Patient-specific guidance from glenoid fossa / articular eminence geometry is **not required** for TRL-4.

---

# 12. Rigid Transform Construction

Let:

```text
H0 = initial virtual condylar-axis midpoint
A  = unit transverse axis
```

For state `q`:

```text
t_condyle = d(q) * g_hat
Hq = H0 + t_condyle
```

Conceptually construct:

```text
T(q) =
    Translate(Hq)
    * Rotate(A, theta(q))
    * Translate(-H0)
```

Carefully verify transform-order semantics in VTK / MRML because pre-multiplication vs post-multiplication can invert the intended operation.

The whole mandibular assembly must receive the exact same rigid transform:

- mandible;
- mandibular teeth;
- mandibular pulp;
- any mandibular-attached guides / child geometry intended to move with the jaw.

Never transform maxillary anatomy.

---

# 13. Solve by Requested Interincisal Opening

The user-facing parameter should preferably be:

```text
target interincisal opening in mm
```

rather than direct rotation angle.

Example:

```text
30 mm
35 mm
40 mm
45 mm
```

The solver must search for `q` such that:

```text
distance_between_upper_and_lower_incisor_references(T(q))
    ~= target_opening_mm
```

Use a deterministic 1D numerical search:

- bisection;
- bounded scalar solve;
- or another stable monotonic solver.

Do not use a high-dimensional optimizer unless necessary.

Suggested:

```text
q_low = 0
q_high = 1

while error > tolerance:
    q_mid = (q_low + q_high) / 2
    evaluate opening(q_mid)
    update interval
```

If requested opening is outside the configured achievable range:

- clamp only if explicitly allowed;
- otherwise return a clear validation warning;
- never silently fabricate a transform.

Store:

```text
requested_opening_mm
achieved_opening_mm
q
theta_deg
translation_mm
```

---

# 14. Optional Midline Constraint

For TRL-4, symmetrical opening is acceptable as the default.

The lower-incisor midpoint should remain approximately in the sagittal midline during the simulated opening.

Do not introduce yaw or lateral translation unless specifically required.

Future extension:

```text
opening_deviation_mm
opening_deviation_direction
```

can perturb the motion, but it is not required now.

---

# 15. Automatic Landmark Placement Strategy

The intended workflow is:

```text
AUTO PROPOSE
    |
    v
VISUALIZE
    |
    v
USER ACCEPT / CORRECT
    |
    v
LOCK
    |
    v
SOLVE
```

Do not make automated landmarks an uninspectable hidden operation.

Every landmark used by the transform must be represented visibly and/or inspectably in the scene.

Required manual override capability:

- upper incisor midpoint;
- lower incisor midpoint;
- left condylar centre;
- right condylar centre;
- occlusal plane;
- arch frame.

Once corrected, save the corrected state into `.dentocase`.

The solver must never recompute and overwrite a locked manual correction without an explicit reset.

---

# 16. Confidence / Provenance

The transform must store how it was produced.

Example:

```json
{
  "solver": "virtual_open_mouth_articulator",
  "hinge_source": "PATIENT_CONDYLES",
  "axis_confidence": 0.92,
  "kinematics_source": "MEAN_VALUE_PRIOR",
  "target_opening_mm": 40.0,
  "achieved_opening_mm": 39.98
}
```

Fallback example:

```json
{
  "solver": "virtual_open_mouth_articulator",
  "hinge_source": "ARCH_INFERRED",
  "axis_confidence": 0.62,
  "kinematics_source": "MEAN_VALUE_PRIOR",
  "arch_scale_used": true,
  "target_opening_mm": 40.0
}
```

The confidence number does not need to be statistically calibrated at TRL-4.

It can initially be a deterministic QA score based on available anatomy and geometry checks.

More important than the number is the provenance.

---

# 17. Suggested UI

Possible user-facing concept:

```text
VIRTUAL OPEN-MOUTH ARTICULATOR

Hinge source:
[AUTO]

AUTO result:
✓ Bilateral condyles detected
Axis source: Patient anatomy

or

⚠ Condyles unavailable
Axis source: Arch-inferred mean-value geometry

Opening target:
[ 40.0 ] mm

Advanced:
Bonwill side:        AUTO / 102 mm
Intercondylar span:  AUTO / 100 mm
Balkwill angle:      22 deg
Guidance angle:      <config>
Translation profile: Default

[Show Landmarks]
[Edit Landmarks]
[Generate Open-Mouth Pose]
[Reset]
```

Keep expert parameters hidden under an advanced panel.

---

# 18. Required Validation Gates

The algorithm must fail loudly or fall back when geometric prerequisites are invalid.

## Before solving

Check:

- mandibular transformable assembly exists;
- lower-incisor reference exists;
- dental frame exists;
- transverse axis is valid;
- virtual condylar points are finite;
- intercondylar span is not zero;
- axis orientation is reasonable;
- target opening is positive and within configured range.

## For patient-derived mode

Check:

- both condyles present;
- axis roughly left-right;
- intercondylar distance plausible;
- points posterior to incisors;
- points superior relative to dental frame.

## For arch-inferred mode

Check:

- incisor midpoint valid;
- arch AP direction valid;
- occlusal plane valid or fallback orientation available;
- `L_B > B/2`;
- scale factor bounded.

---

# 19. Output Invariants

After transform:

### Invariant 1 — Maxilla does not move

All maxillary nodes must retain their original transforms.

### Invariant 2 — Mandible stays rigid

For any two points `p1`, `p2` on the mandible:

```text
||p1 - p2|| before == ||p1 - p2|| after
```

within numerical tolerance.

### Invariant 3 — Child anatomy remains rigidly attached

All mandibular teeth and pulps must preserve their relative transform to the mandible.

### Invariant 4 — Determinism

Same inputs + same config must produce exactly the same output transform.

### Invariant 5 — Requested opening

Achieved interincisal opening must be within an explicit tolerance, e.g.:

```text
<= 0.1 mm
```

or another project-defined tolerance.

### Invariant 6 — Plausible direction

Opening must move the mandibular incisors inferiorly and generally posteriorly / rotationally as expected, while virtual condyles translate anterior-inferiorly.

### Invariant 7 — No silent scene corruption

Generating the open-mouth pose must not modify:

- source CBCT;
- original segmentation geometry;
- trajectory records;
- unrelated transforms;
- robot state.

---

# 20. Visualization / Diagnostics

Provide optional debug visualization for:

- `I_u`
- `I_m`
- dental frame axes
- mandibular occlusal plane
- maxillary occlusal plane
- actual / virtual condylar centres
- condylar axis
- condylar guidance vector
- closed mandible
- simulated open mandible

Recommended scene naming:

```text
DW_Observed_*
DW_Derived_*
DW_Sim_OpenMouth_*
```

Avoid stale unnamed nodes.

Debug output should state:

```text
hinge source
axis points
axis span
arch scale
target opening
solved q
rotation
translation
achieved opening
validation status
```

---

# 21. Saving to `.dentocase`

Persist:

```text
open_mouth_model_version
hinge_source
landmark_source
landmark coordinates
manual overrides
dental frame
axis points
axis midpoint
axis direction
arch scale
kinematic config
target opening
achieved opening
q
theta
translation
final transform matrix
validation status
```

On reload:

- restore the exact accepted solution;
- do not recompute automatically unless requested;
- mark stale only if source anatomy changed.

---

# 22. Recommended Implementation Order

## Phase 1 — manual oracle

Implement the solver independent of automation.

Allow manual placement of:

- left virtual / actual condyle;
- right virtual / actual condyle;
- upper incisor midpoint;
- lower incisor midpoint.

Goal:

```text
manual landmarks -> open-mouth transform
```

Validate transform mathematics first.

## Phase 2 — patient condyle extraction

If bilateral condyles are present:

```text
segmentation -> centres -> axis -> same solver
```

Compare with manually selected condylar centres.

## Phase 3 — arch-derived axis

Implement:

```text
incisors
+ arch
+ dental frame
+ mean-value priors
-> virtual condylar axis
-> same solver
```

## Phase 4 — AUTO selection

```text
if bilateral condyles pass QA:
    PATIENT_CONDYLES
else:
    ARCH_INFERRED
```

## Phase 5 — workflow integration

Integrate with DentoWorkflow without modifying downstream robot logic.

Downstream code should consume only:

```text
MandibleOpenTransform
```

plus provenance metadata if needed.

---

# 23. Tests

Create unit / logic tests before full Slicer workflow testing where possible.

## Geometry tests

1. Known synthetic axis and known mandible.
2. Zero opening returns identity.
3. Increasing opening produces monotonic interincisal distance.
4. Rotation preserves rigid distances.
5. Translation moves condylar axis in configured guidance direction.
6. Same input gives identical matrix.
7. Invalid Bonwill geometry fails.
8. Parallel / noisy occlusal planes do not affect hinge via plane intersection because plane intersection is not used.

## Patient-axis tests

1. Two valid synthetic condyles -> patient mode.
2. Missing one condyle -> fallback.
3. Implausible intercondylar span -> fallback.
4. Swapped L/R detection -> corrected or rejected.

## Arch fallback tests

1. Normal synthetic arch -> sensible virtual axis.
2. Arch scale 0.9 / 1.0 / 1.1 -> smoothly scaled axis.
3. Tiny FOV without enough arch -> explicit unavailable / low-confidence state.
4. Manual landmarks override automatic values.

## Scene tests

1. Original anatomy unchanged.
2. Only mandibular assembly moves.
3. Reloaded `.dentocase` reproduces the accepted transform.
4. Reset removes simulation transform without deleting observed anatomy.
5. Re-run does not accumulate transforms.

---

# 24. Acceptance Criteria for TRL-4

The feature is complete enough for TRL-4 when:

1. Full-FOV CBCT with bilateral condyles:
   - condylar axis is derived;
   - user can inspect / correct it;
   - requested opening generates a repeatable plausible pose.

2. Reduced-FOV CBCT without condyles but with usable dental arch:
   - virtual axis is inferred;
   - the same solver runs;
   - output provenance clearly states `ARCH_INFERRED`.

3. Original anatomy is preserved.

4. The entire mandibular assembly moves rigidly.

5. Maxilla remains fixed.

6. Requested interincisal opening is achieved within tolerance.

7. Downstream Stage 6 simulation receives only the resulting transform and does not care about hinge-source mode.

8. Scene reload / restart preserves the accepted solution.

9. Manual override exists for all critical landmarks.

10. No unsupported claim is made that the output is the patient's true functional mandibular pose.

---

# 25. Important Non-Goals / Guardrails for the Agent

Do not:

- over-engineer exact TMJ mechanics;
- introduce FEM;
- introduce realtime tracking;
- introduce ML unless absolutely necessary;
- rework unrelated DentoWorkflow stages;
- silently modify source anatomy;
- make open-mouth transform part of surgical registration;
- use the intersection of upper/lower occlusal planes as the hinge;
- create two independent motion engines;
- invent patient-specific biomechanics from static CBCT;
- spend large effort on visual polish before transform correctness is verified.

Prefer:

- deterministic geometry;
- inspectable landmarks;
- simple math;
- one code path;
- explicit fallback;
- strong scene-state discipline;
- manual oracle before automation;
- cheap unit tests before Slicer runtime tests.

---

# 26. Final Intended Mental Model

The implementation should behave as:

```text
Observed CBCT anatomy
        |
        v
Derived dental frame + landmarks
        |
        v
Choose hinge source
        |
        +--> actual bilateral condyles
        |
        +--> arch-derived virtual condyles
        |
        v
Shared mean-value opening kinematics
        |
        v
Solve requested interincisal opening
        |
        v
Rigid MandibleOpenTransform
        |
        v
Robot workspace / reach / collision simulation
```

The most important architectural rule is:

> **Patient-specific geometry when available; mean-value geometry when unavailable; mean-value motion prior in both cases; one shared solver.**

The feature is a controlled TRL-4 simulation aid, not a substitute for future real patient registration or functional jaw tracking.

---

# 27. Agent Execution Instruction

Before implementation:

1. Inspect the current DentoWorkflow transform / scene architecture.
2. Identify where mandibular anatomy is currently parented and transformed.
3. Identify existing landmark / trajectory / `.dentocase` data structures that can be reused.
4. Produce a concise implementation plan mapping this specification onto the existing code.
5. Do not redesign unrelated workflow stages.
6. Implement the manual-oracle transform path first.
7. Add patient-condyle and arch-fallback axis generation only after transform correctness is verified.
8. Use lightweight logic tests before expensive Slicer / container tests.
9. Report blockers with exact evidence rather than guessing.
10. Preserve this specification's separation of Observed / Derived / Simulated state.

If an existing implementation conflicts with this specification, explain the conflict before changing architecture.
