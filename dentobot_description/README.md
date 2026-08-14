# DENTOBOT ROS 2 description

This package is the first simulation-only integration of the supplied CAD
export. It publishes the URDF through `robot_state_publisher` and supplies a
neutral joint-state publisher so the complete tree can be inspected without a
controller or robot connection.

## Source and normalization

The source bundle was received under the workspace-local
`data/ROS/assembly` directory on 2026-08-14. Its unmodified URDF SHA-256 is
`e04d644a85eaeb518507cbe991e2007e1f0194c7cc4b834fc608d9d6b1beda45`.
The seven copied binary STL checksums are enforced by the package test.

Only three URDF normalizations were made:

- the robot name changed from the generic `assembly` to `dentobot`;
- relative mesh paths changed to
  `package://dentobot_description/meshes/...`;
- a massless `base_link` and identity fixed joint were placed above `link-1`
  because KDL does not retain inertia on a URDF root link.

All supplied link names, movable joint names/types, origins, axes, limits,
masses, inertias, mesh scales, and triangles otherwise remain unchanged.

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

The neutral publisher writes only `sensor_msgs/msg/JointState` messages. It
does not expose command topics, controllers, transmissions, `ros2_control`, a
hardware plugin, or any robot motion path.

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
