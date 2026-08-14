# DENTOBOT ROS 2 description

This package is the first simulation-only integration of the supplied CAD
export. It publishes the URDF through `robot_state_publisher` and supplies
neutral and manual joint-state modes so the complete tree can be inspected and
articulated without a controller or robot connection.

## Source and normalization

The source bundle was received under the workspace-local
`data/ROS/assembly` directory on 2026-08-14. Its unmodified URDF SHA-256 is
`e04d644a85eaeb518507cbe991e2007e1f0194c7cc4b834fc608d9d6b1beda45`.
The seven copied binary STL checksums are enforced by the package test.

The initial integration made three URDF normalizations:

- the robot name changed from the generic `assembly` to `dentobot`;
- relative mesh paths changed to
  `package://dentobot_description/meshes/...`;
- a massless `base_link` and fixed joint were placed above `link-1`
  because KDL does not retain inertia on a URDF root link.

On 2026-08-14 the developer selected a photographed design pose as the new
draft zero configuration. The old manual values absorbed into the URDF joint
origins are J1 `25.38 deg`, J2 `0 mm`, J3 `62.46 deg`, J4 `0 mm`, J5
`1.08 deg`, and J6 `-35.28 deg`; the three finite revolute limits were shifted
by the same offsets so their original 360-degree spans remain available around
the new zero. The fixed root rotates link-1 by -90 degrees about X, placing its
thin Y-normal mounting face on the RViz XY plane with the articulated chain
above the grid. J4's axis is negated while retaining its positive `0–75 mm`
control range, so increasing J4 now moves primarily in negative `base_link` X.

The received source URDF remains unchanged under `data/ROS/assembly`. Mesh
bytes, link frames/geometries, masses, inertias, and the other joint axes are
unchanged in the tracked description.

## Build and inspect

From the DENTOBOT Jazzy container workspace:

```bash
source /opt/ros/jazzy/setup.bash
cd /workspace/ros2_ws
colcon build --symlink-install --packages-select dentobot_description
source install/setup.bash
ros2 launch dentobot_description description.launch.py
```

For a headless transport/TF check, omit RViz:

```bash
ros2 launch dentobot_description description.launch.py use_rviz:=false
```

## Manual joint articulation

From an Ubuntu graphical desktop terminal, use the workspace launcher:

```bash
cd /home/light-tarun/dentobot
./scripts/launch-dentobot-manual-rviz.bash
```

The launcher verifies the reusable container, rebuilds only this small
description package, refuses a duplicate description launch, grants temporary
X11 access, and opens RViz beside the package-owned manual slider window.

The six controls follow URDF order. Revolute values are displayed in degrees;
prismatic values are displayed in millimetres. Published
`sensor_msgs/msg/JointState` positions remain in ROS SI units (radians and
metres):

| Joint | Type | Manual display range |
| --- | --- | --- |
| `link-1_Revolute-1` | revolute | -25.38–334.62 deg |
| `link-2_Slider-2` | prismatic | 0–80 mm |
| `link-3_Revolute-3` | revolute | -62.46–297.54 deg |
| `link-4_Slider-4` | prismatic | 0–75 mm |
| `link-5_Revolute-5` | revolute | -1.08–358.92 deg |
| `pneumatic_spindle-Copy_Revolute-6` | continuous | -180–180 deg |

All six displayed values start at zero. **Reset all joints to zero** restores
the photographed pose, not the original CAD-export pose.

The direct ROS equivalent is:

```bash
ros2 launch dentobot_description manual.launch.py
```

### Draft 5 mm link-box clearance

Manual mode computes a base-frame axis-aligned bounding box (AABB) around each
transformed collision mesh. It compares every non-adjacent link pair and warns
when the Euclidean distance between their boxes is below 5 mm. Direct
parent-child pairs are ignored because connected joint geometry is expected to
touch or overlap. The manual window lists the closest warning pairs and shows
the current `burr` link origin in `base_link` millimetres. RViz subscribes to
`/dentobot/coarse_self_collision_boxes`; green outlines are clear and red
outlines participate in a warning.

This is intentionally conservative draft logic. Rotated axis-aligned boxes can
overlap even when the actual triangles do not, and the current collision meshes
are the unreduced visual STLs. At neutral, the draft checker reports
`link-3`/`link-5` and `link-3`/`pneumatic_spindle-Copy` AABB overlap. Do not
interpret those warnings as confirmed physical collision, and do not interpret
a clear result as continuous-path or patient/head clearance. The `burr` origin
is a CAD link origin, not a calibrated tool centre point.

The default can be made more conservative for an experiment, for example:

```bash
ros2 launch dentobot_description manual.launch.py coarse_clearance_mm:=10.0
```

`description.launch.py` also accepts `joint_state_mode:=neutral` (the default),
`joint_state_mode:=manual`, or `joint_state_mode:=external`. External mode
starts no joint-state source and exists for bounded TF tests or a future
simulator. Do not run more than one joint-state publisher for the model.

Both package-owned publishers write only `sensor_msgs/msg/JointState`
messages. Neither exposes command topics, controllers, transmissions,
`ros2_control`, a hardware plugin, or any robot motion path.

## Evidence boundary and open engineering work

Passing the package tests or displaying the model establishes only static and
synthetic description integrity. Before this model can support kinematics,
collision planning, calibration, or hardware integration, the team must verify:

- physical joint zero definitions, positive directions, usable ranges,
  velocity limits, effort limits, and units;
- link/joint naming and the intended `base_link`, end-effector, spindle, TCP,
  bur-tip, and docking frames;
- masses, centers of mass, and inertia tensors against the physical assembly;
- visual mesh alignment and scale against measured dimensions;
- simplified, conservative collision geometry instead of reusing every visual
  mesh verbatim;
- self-collision pairs, transmissions/actuators, controller interfaces, and
  the robot-control/safety boundary;
- the explicit transform chain from Slicer RAS through the physical docking
  and robot frames.

No powered motion, drilling, patient use, or safety claim is authorized by
this package.
