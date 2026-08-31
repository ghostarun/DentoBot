# Manual ROS / MoveIt Verification Guide

Last updated: 2026-08-28

This guide is a **minimal operator map** for continuing the Step 6 simulation
verification loop **without AI assistance**. It lists only the launch scripts,
configuration files, Python seams, and headless smokes you need to adjust
parameters and exercise the motion planner.

Simulation only. No hardware execution, drilling, or patient-facing operation.

## Where to start

### 1. Bring up the stack

Do **not** launch MoveIt from inside Slicer. Use the repository launcher:

```bash
cd /home/light-tarun/dentobot/ros2_ws/src/DentoBot
Workspace/scripts/launch-dentoworkflow.bash --check-only   # optional preflight
Workspace/scripts/launch-dentoworkflow.bash
```

What this does:

- Builds `dentobot_description` and `dentobot_moveit_config`
- Starts one simulation process group via `simulation.launch.py`
- Waits for `/dentobot/simulation_status`
- Opens SlicerROS2 with DENTOWorkflow loaded

The stack stops when that Slicer session exits. A normal GUI launch restarts the
`dentobot-slicerros2` container when it is already running, so save open scenes
first.

### 2. Optional: ROS stack without Slicer GUI

Use this when you only want the external description + MoveIt + collision guard
running, and will connect from Slicer separately:

```bash
Workspace/scripts/launch-dentobot-description-for-slicer.bash
```

Requires the `dentobot-slicerros2` container to already be running.

### 3. Step 6 operator sequence in Slicer

| Step | Action |
|------|--------|
| 6.0 | Import `.dentocase`; complete required case jaw opening if prompted |
| 6.1 | Load MRML robot; place and provisionally lock base |
| 6.2 | Save Task Home (six-joint simulation pose) |
| 6.3 | Generate FK workspace; **Review & Apply** assisted task limits |
| 6.4 | **Connect ROS + MoveIt (Simulation)**; sync obstacles; confirm task |
| 6.5 | Plan/preview Goal 1 (approach + terminal Entry contact) |
| 6.6 | Plan/preview Goal 2 (Entry-to-Target drilling preview) |

Routine operation stays in DENTOWorkflow. **Open Expert ROS Diagnostics** is
optional. Do not press or script Execute; `move_group` has no controller.

After Python edits in DENTOWorkflow, use **Reload Module (Dev)** instead of
restarting the whole container unless C++ or YAML changed.

## Essential files only

Ignore the rest of the repository for this loop unless your case package or
upstream geometry is wrong.

### A. Launch / lifecycle

| File | Role |
|------|------|
| `Workspace/scripts/launch-dentoworkflow.bash` | Primary entry: Docker, build, simulation stack, Slicer |
| `Workspace/scripts/launch-dentobot-description-for-slicer.bash` | External stack only, no Slicer window |

### B. ROS / MoveIt stack

| File | What you tune |
|------|----------------|
| `dentobot_moveit_config/launch/simulation.launch.py` | Node wiring, topics, guard margins, interpolation |
| `dentobot_moveit_config/config/joint_limits.yaml` | Hard joint bounds |
| `dentobot_moveit_config/config/kinematics.yaml` | KDL IK solver settings |
| `dentobot_moveit_config/config/ompl_planning.yaml` | OMPL planner (RRTConnect, segment fraction) |
| `dentobot_moveit_config/config/dentobot.srdf` | Planning group, collision pairs |
| `dentobot_moveit_config/src/collision_guard.cpp` | Strict vs phased guard, task JSON schema, contact rules |

Robot model:

- `dentobot_description/urdf/dentobot.urdf`
- `dentobot_description/meshes/`

Joint bridge scripts:

- `dentobot_description/scripts/slicer_joint_state_publisher`
- `dentobot_description/scripts/simulation_status_publisher.py`

### C. Slicer ↔ ROS planning glue

| File | Role |
|------|------|
| `DENTOWorkflow/Resources/Python/DENTOROS2Bridge.py` | Connect/disconnect, MoveIt Cartesian plans, guard config publish, clearance constants |
| `DENTOWorkflow/Resources/Python/DENTORobotWorkflowFacade.py` | Step 6 orchestration: connect, sync scene, Goal 1/2 preview |
| `DENTOWorkflow/Resources/Python/DENTOStep6State.py` | Task snapshot, motion phases, standoff and limit envelopes |

### D. Headless verification scripts

Run inside the `dentobot-slicerros2` container with ROS sourced.

| Script | Use when |
|--------|----------|
| `Testing/run_dentobot_phase_guard_smoke.py` | Collision guard + phased task JSON without Slicer GUI |
| `Testing/run_dentobot_slicer_moveit_smoke.py` | Slicer + phantom + connect + Cartesian plan smoke |
| `Testing/run_dentobot_step65_exact_case_smoke.py` | Exact saved case reachability / Goal 1 diagnostic |
| `Testing/run_dentobot_step66_roll_diagnostic.py` | Entry-to-Target axial roll probe only |
| `Testing/run_dentobot_moveit_smoke.py` | Lighter MoveIt package smoke |

## Rebuild after C++ / MoveIt config changes

Inside the container:

```bash
cd /workspace/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --base-paths src/DentoBot/dentobot_moveit_config \
  --packages-select dentobot_moveit_config --symlink-install
```

Then restart the launcher or only the simulation process group.

The collision guard uses JsonCpp for versioned phase JSON. Do not replace that
with delimiter-based string parsing.

## Data flow

```text
launch-dentoworkflow.bash
  → simulation.launch.py
      → robot_state_publisher
      → slicer_joint_state_publisher   (/dentobot/validated_joint_positions)
      → move_group
      → collision_guard                (/dentobot/task_guard_config, task_joint_command)
      → simulation_status_publisher    (/dentobot/simulation_status)
  → DENTOWorkflow Step 6 UI
      → DENTORobotWorkflowFacade
          → DENTOROS2Bridge
              → MoveIt Cartesian planning + guard publish
              → collision_guard accept/reject
```

## Parameter knobs you will actually touch

| Concern | Where |
|---------|--------|
| Planner quality / speed | `ompl_planning.yaml`, `kinematics.yaml` |
| Joint envelope | `joint_limits.yaml` + Step 6 task limits (UI 6.3) |
| Clearance / interpolation | `simulation.launch.py` guard params; `DENTOROS2Bridge.py` (`ROS2_RESEARCH_MINIMUM_CLEARANCE_M = 0.001`) |
| Approach standoff | `DENTOStep6State.py` default `standoff_mm = 2.0`; restored cases keep recorded value |
| Roll reachability policy | façade / bridge Goal 1 preflight (`0, ±45, ±90, ±135, 180` deg probes) |
| Base placement when case fails reachability | Step 6 UI 6.1; re-save Task Home and reconfirm task after moving base |

## What to ignore for this loop

- Steps 0–5 geometry unless the imported case package is wrong upstream
- `graphify-out/`, inference, EndoPlanner, most `dentobot_workflow/widget_*` except what Step 6 exposes
- `ROS2MotionControl` expert panel for routine verification
- Host `Testing/test_*.py` unless you want fast unit regressions before a live run

## Quick verification checklist

1. `launch-dentoworkflow.bash --check-only` passes
2. Full launch reports `ready:true` on `/dentobot/simulation_status`
3. Import case, complete 6.0A if required, lock base, save Task Home
4. Connect ROS + MoveIt; confirm task snapshot
5. Goal 1 plans; roll preflight passes or clearly reports base-placement failure
6. Goal 2 preview runs only after Goal 1 is accepted
7. Optional headless: `run_dentobot_phase_guard_smoke.py` or case-specific smoke

## Related controlled docs

- `SETUP.md` — Step 6 native placement-to-task simulation (authoritative environment contract)
- `ARCHITECTURE.md` — Step 6 ROS/MoveIt simulation architecture
- `REPRODUCIBILITY_AND_TRACEABILITY.md` — evidence and traceability boundaries
