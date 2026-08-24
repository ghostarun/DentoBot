"""Presentation-only controls added by the new Robot Simulation workspace."""

from __future__ import annotations

import qt


class DENTORobotSimulationPanel:
    """Build goal/IK and collision cards without calling robot services."""

    def __init__(self, parent, callbacks: dict[str, object]) -> None:
        self._callbacks = callbacks
        self.runtimeGroup = qt.QGroupBox("ROS 2 and MoveIt Runtime", parent)
        self.runtimeGroup.objectName = "DENTOBOTRobotRuntimeGroupBox"
        runtime_layout = qt.QVBoxLayout(self.runtimeGroup)
        runtime_description = qt.QLabel(
            "The desktop launcher owns the simulation-only ROS 2 and MoveIt "
            "stack. Connect loads the robot and detects its fixed planning "
            "group and provisional TCP; it never starts hardware execution.",
            self.runtimeGroup,
        )
        runtime_description.wordWrap = True
        runtime_layout.addWidget(runtime_description)
        runtime_buttons = qt.QHBoxLayout()
        self.connectButton = qt.QPushButton("Connect ROS + MoveIt", self.runtimeGroup)
        self.connectButton.objectName = "DENTOBOTShellConnectRobotButton"
        self.disconnectButton = qt.QPushButton("Disconnect", self.runtimeGroup)
        self.disconnectButton.objectName = "DENTOBOTShellDisconnectRobotButton"
        self.loadFallbackButton = qt.QPushButton("Load Local Fallback", self.runtimeGroup)
        self.loadFallbackButton.objectName = "DENTOBOTShellLoadFallbackRobotButton"
        runtime_buttons.addWidget(self.connectButton)
        runtime_buttons.addWidget(self.disconnectButton)
        runtime_buttons.addWidget(self.loadFallbackButton)
        runtime_layout.addLayout(runtime_buttons)
        self.runtimeStatusLabel = qt.QLabel(
            "Choose a case or phantom, then connect the simulation stack.",
            self.runtimeGroup,
        )
        self.runtimeStatusLabel.objectName = "DENTOBOTRobotRuntimeStatusLabel"
        self.runtimeStatusLabel.wordWrap = True
        self.runtimeStatusLabel.setProperty("dentobotRole", "status")
        runtime_layout.addWidget(self.runtimeStatusLabel)

        self.goalGroup = qt.QGroupBox("Goal and IK", parent)
        self.goalGroup.objectName = "DENTOBOTGoalIkGroupBox"
        goal_layout = qt.QVBoxLayout(self.goalGroup)
        goal_layout.setSpacing(6)
        description = qt.QLabel(
            "Move a provisional TCP probe to define the goal. MoveIt solves the "
            "configured URDF/SRDF chain; the translucent goal robot shares the "
            "locked base and never becomes the current /joint_states source.",
            self.goalGroup,
        )
        description.wordWrap = True
        goal_layout.addWidget(description)

        capability_grid = qt.QGridLayout()
        capability_grid.setHorizontalSpacing(8)
        capability_grid.setVerticalSpacing(3)
        self.capabilityLabels = {}
        rows = (
            ("runtime", "ROS runtime"),
            ("move_group", "Move group"),
            ("planning_group", "Planning group"),
            ("tcp", "End-effector / TCP"),
            ("ik", "MoveIt IK"),
            ("collision", "Collision checking"),
        )
        for row, (key, title) in enumerate(rows):
            title_label = qt.QLabel(f"{title}:", self.goalGroup)
            value_label = qt.QLabel("Not checked", self.goalGroup)
            value_label.wordWrap = True
            value_label.setProperty("dentobotRole", "muted")
            capability_grid.addWidget(title_label, row, 0)
            capability_grid.addWidget(value_label, row, 1)
            self.capabilityLabels[key] = value_label
        capability_grid.setColumnStretch(1, 1)
        goal_layout.addLayout(capability_grid)

        buttons = qt.QHBoxLayout()
        self.createGoalButton = qt.QPushButton("Create / Show TCP Goal", self.goalGroup)
        self.createGoalButton.objectName = "DENTOBOTCreateTcpGoalButton"
        self.solveIkButton = qt.QPushButton("Solve IK", self.goalGroup)
        self.solveIkButton.objectName = "DENTOBOTSolveIkButton"
        self.planGoalButton = qt.QPushButton("Plan to Goal", self.goalGroup)
        self.planGoalButton.objectName = "DENTOBOTPlanGoalButton"
        buttons.addWidget(self.createGoalButton)
        buttons.addWidget(self.solveIkButton)
        buttons.addWidget(self.planGoalButton)
        goal_layout.addLayout(buttons)
        self.goalStatusLabel = qt.QLabel(
            "Connect ROS + MoveIt and lock the base before creating a TCP goal.",
            self.goalGroup,
        )
        self.goalStatusLabel.objectName = "DENTOBOTGoalIkStatusLabel"
        self.goalStatusLabel.wordWrap = True
        self.goalStatusLabel.setProperty("dentobotRole", "status")
        goal_layout.addWidget(self.goalStatusLabel)

        self.collisionGroup = qt.QGroupBox("Scene and Collision", parent)
        self.collisionGroup.objectName = "DENTOBOTCollisionSceneGroupBox"
        collision_layout = qt.QVBoxLayout(self.collisionGroup)
        collision_description = qt.QLabel(
            "Synchronize the active skull/case, support anatomy, template, and "
            "docking surfaces with the MoveIt planning scene. MoveIt/FCL is "
            "authoritative; the separate Halton/FK/AABB cloud is only a draft "
            "design-space approximation.",
            self.collisionGroup,
        )
        collision_description.wordWrap = True
        collision_layout.addWidget(collision_description)
        collision_buttons = qt.QHBoxLayout()
        self.refreshButton = qt.QPushButton("Refresh Status", self.collisionGroup)
        self.refreshButton.objectName = "DENTOBOTRefreshRobotCapabilitiesButton"
        self.syncCollisionButton = qt.QPushButton(
            "Sync Collision Surfaces",
            self.collisionGroup,
        )
        self.syncCollisionButton.objectName = "DENTOBOTSyncCollisionSceneButton"
        self.checkStateButton = qt.QPushButton("Check Current State", self.collisionGroup)
        self.checkStateButton.objectName = "DENTOBOTCheckRobotStateButton"
        collision_buttons.addWidget(self.refreshButton)
        collision_buttons.addWidget(self.syncCollisionButton)
        collision_buttons.addWidget(self.checkStateButton)
        collision_layout.addLayout(collision_buttons)
        self.collisionStatusLabel = qt.QLabel(
            "No planning-scene synchronization has been requested in this session.",
            self.collisionGroup,
        )
        self.collisionStatusLabel.objectName = "DENTOBOTCollisionSceneStatusLabel"
        self.collisionStatusLabel.wordWrap = True
        self.collisionStatusLabel.setProperty("dentobotRole", "status")
        collision_layout.addWidget(self.collisionStatusLabel)

        self.createGoalButton.clicked.connect(
            lambda checked=False: self._invoke("create_goal")
        )
        self.solveIkButton.clicked.connect(
            lambda checked=False: self._invoke("solve_ik")
        )
        self.planGoalButton.clicked.connect(
            lambda checked=False: self._invoke("plan_goal")
        )
        self.refreshButton.clicked.connect(
            lambda checked=False: self._invoke("refresh")
        )
        self.syncCollisionButton.clicked.connect(
            lambda checked=False: self._invoke("sync_collision")
        )
        self.checkStateButton.clicked.connect(
            lambda checked=False: self._invoke("check_state")
        )
        self.connectButton.clicked.connect(
            lambda checked=False: self._invoke("connect")
        )
        self.disconnectButton.clicked.connect(
            lambda checked=False: self._invoke("disconnect")
        )
        self.loadFallbackButton.clicked.connect(
            lambda checked=False: self._invoke("load_fallback")
        )
        self.runtimeGroup.visible = False
        self.goalGroup.visible = False
        self.collisionGroup.visible = False

    def _invoke(self, name: str) -> None:
        callback = self._callbacks.get(name)
        if callback:
            callback()

    @staticmethod
    def _set_boolean(label, available: bool, yes: str = "Available", no: str = "Unavailable") -> None:
        label.text = yes if available else no
        label.setProperty("dentobotState", "ok" if available else "blocked")
        label.style().unpolish(label)
        label.style().polish(label)

    def updateCapabilities(self, capabilities) -> None:
        self._set_boolean(
            self.capabilityLabels["runtime"],
            capabilities.connected,
            "Connected (simulation only)",
            capabilities.reason or "Disconnected",
        )
        self._set_boolean(
            self.capabilityLabels["move_group"],
            capabilities.move_group_available,
            "Available",
            "Unavailable",
        )
        self.capabilityLabels["planning_group"].text = capabilities.planning_group
        self.capabilityLabels["tcp"].text = capabilities.tcp_link
        self._set_boolean(self.capabilityLabels["ik"], capabilities.ik_available)
        self._set_boolean(
            self.capabilityLabels["collision"],
            capabilities.collision_check_available,
        )
        self.createGoalButton.enabled = capabilities.ik_available
        self.solveIkButton.enabled = capabilities.ik_available
        self.planGoalButton.enabled = capabilities.ik_available
        self.syncCollisionButton.enabled = capabilities.collision_check_available
        self.checkStateButton.enabled = capabilities.connected
        self.connectButton.enabled = not capabilities.connected
        self.disconnectButton.enabled = capabilities.connected
        self.runtimeStatusLabel.text = (
            f"Runtime {capabilities.stack_state}; group {capabilities.planning_group}; "
            f"TCP {capabilities.tcp_link}. "
            + (capabilities.reason or "Simulation-only capability report is current.")
        )

    @staticmethod
    def _show_result(label, result) -> None:
        label.text = result.message
        label.setProperty("dentobotState", "ok" if result.success else "error")
        label.style().unpolish(label)
        label.style().polish(label)

    def showGoalResult(self, result) -> None:
        self._show_result(self.goalStatusLabel, result)

    def showRuntimeResult(self, result) -> None:
        self._show_result(self.runtimeStatusLabel, result)

    def showCollisionResult(self, result) -> None:
        self._show_result(self.collisionStatusLabel, result)
