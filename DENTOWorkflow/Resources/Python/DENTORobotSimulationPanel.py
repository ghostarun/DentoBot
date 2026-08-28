"""Presentation-only controls added by the new Robot Simulation workspace."""

from __future__ import annotations

import qt


class DENTORobotSimulationPanel:
    """Build goal/IK and collision cards without calling robot services."""

    def __init__(self, parent, callbacks: dict[str, object]) -> None:
        self._callbacks = callbacks
        self.visualizationGroup = qt.QGroupBox("Placement Context", parent)
        self.visualizationGroup.objectName = "DENTOBOTPlacementContextGroupBox"
        visualization_layout = qt.QVBoxLayout(self.visualizationGroup)
        visualization_description = qt.QLabel(
            "CBCT rendering is opt-in and display-only: it reuses the source "
            "volume without resampling or changing IJK-to-RAS. The curved "
            "forehead proxy is unregistered, provisional, visualization-only, "
            "and excluded from collision and registration evidence.",
            self.visualizationGroup,
        )
        visualization_description.wordWrap = True
        visualization_layout.addWidget(visualization_description)
        render_actions = qt.QHBoxLayout()
        self.enableCbctRenderingButton = qt.QPushButton(
            "Enable CBCT 3D Context", self.visualizationGroup
        )
        self.cbctPresetCombo = qt.QComboBox(self.visualizationGroup)
        self.cbctPresetCombo.addItem("Current window/level", "current")
        self.cbctPresetCombo.addItem("CT-Bone intensity appearance", "CT-Bone")
        self.cbctPresetCombo.addItem("uCT-Skull intensity appearance", "uCT-Skull")
        self.createProxyButton = qt.QPushButton(
            "Create / Update Provisional Forehead Proxy", self.visualizationGroup
        )
        self.loadFallbackButton = qt.QPushButton(
            "Load / Reuse Local MRML Robot", self.visualizationGroup
        )
        self.loadFallbackButton.objectName = "DENTOBOTShellLoadFallbackRobotButton"
        render_actions.addWidget(self.loadFallbackButton)
        render_actions.addWidget(self.enableCbctRenderingButton)
        render_actions.addWidget(self.cbctPresetCombo)
        render_actions.addWidget(self.createProxyButton)
        visualization_layout.addLayout(render_actions)
        appearance_grid = qt.QGridLayout()
        appearance_grid.addWidget(qt.QLabel("Element"), 0, 0)
        appearance_grid.addWidget(qt.QLabel("Visible"), 0, 1)
        appearance_grid.addWidget(qt.QLabel("Opacity"), 0, 2)
        self.appearanceControls = {}
        appearance_rows = (
            ("cbct", "CBCT rendering", 18),
            ("masks", "Dental masks", 45),
            ("robot", "Current robot", 100),
            ("goal_robot", "Goal robot", 35),
            ("guides", "Guides / template", 65),
            ("mount_plane", "Mount plane", 35),
            ("trajectory", "Trajectory / corridor", 100),
            ("forehead_proxy", "Forehead proxy", 20),
        )
        for row, (key, label, default) in enumerate(appearance_rows, start=1):
            visible = qt.QCheckBox(self.visualizationGroup)
            visible.checked = key not in {"cbct", "goal_robot", "forehead_proxy"}
            opacity = qt.QSlider(qt.Qt.Horizontal, self.visualizationGroup)
            opacity.minimum = 0
            opacity.maximum = 100
            opacity.value = default
            opacity.toolTip = f"{label} opacity"
            appearance_grid.addWidget(qt.QLabel(label), row, 0)
            appearance_grid.addWidget(visible, row, 1)
            appearance_grid.addWidget(opacity, row, 2)
            self.appearanceControls[key] = (visible, opacity)
            visible.toggled.connect(
                lambda checked=False, item=key: self._invoke_appearance(item)
            )
            opacity.valueChanged.connect(
                lambda value=0, item=key: self._invoke_appearance(item)
            )
        visualization_layout.addLayout(appearance_grid)
        self.placementReviewButton = qt.QPushButton(
            "Robot + CBCT Placement Review", self.visualizationGroup
        )
        visualization_layout.addWidget(self.placementReviewButton)
        self.visualizationStatusLabel = qt.QLabel(
            "No CBCT renderer or provisional proxy is created automatically.",
            self.visualizationGroup,
        )
        self.visualizationStatusLabel.wordWrap = True
        self.visualizationStatusLabel.setProperty("dentobotRole", "status")
        visualization_layout.addWidget(self.visualizationStatusLabel)

        self.homeGroup = qt.QGroupBox("6.2 — Task Home", parent)
        self.homeGroup.objectName = "DENTOBOTTaskHomeGroupBox"
        home_layout = qt.QVBoxLayout(self.homeGroup)
        home_description = qt.QLabel(
            "Save the current six-joint vector as the case/base-specific Task "
            "Home. This is not physical actuator homing; hardware homing remains unavailable.",
            self.homeGroup,
        )
        home_description.wordWrap = True
        home_layout.addWidget(home_description)
        home_buttons = qt.QHBoxLayout()
        self.saveTaskHomeButton = qt.QPushButton("Save Current as Task Home", self.homeGroup)
        self.applyTaskHomeButton = qt.QPushButton("Apply Task Home (Strict Guard)", self.homeGroup)
        home_buttons.addWidget(self.saveTaskHomeButton)
        home_buttons.addWidget(self.applyTaskHomeButton)
        home_layout.addLayout(home_buttons)
        self.homeStatusLabel = qt.QLabel("Task Home has not been saved.", self.homeGroup)
        self.homeStatusLabel.wordWrap = True
        self.homeStatusLabel.setProperty("dentobotRole", "status")
        home_layout.addWidget(self.homeStatusLabel)

        self.workspaceReviewGroup = qt.QGroupBox("Assisted Limit Review", parent)
        self.workspaceReviewGroup.objectName = "DENTOBOTAssistedLimitReviewGroupBox"
        workspace_review_layout = qt.QVBoxLayout(self.workspaceReviewGroup)
        workspace_review_description = qt.QLabel(
            "Every accepted TCP sample retains its producing joint vector. "
            "Generate the workspace, inspect the suggested envelope, then explicitly review before applying.",
            self.workspaceReviewGroup,
        )
        workspace_review_description.wordWrap = True
        workspace_review_layout.addWidget(workspace_review_description)
        self.reviewLimitsButton = qt.QPushButton(
            "Review and Apply Suggested Limits", self.workspaceReviewGroup
        )
        workspace_review_layout.addWidget(self.reviewLimitsButton)
        self.workspaceReviewStatusLabel = qt.QLabel(
            "No reviewed assisted-limit proposal.", self.workspaceReviewGroup
        )
        self.workspaceReviewStatusLabel.wordWrap = True
        self.workspaceReviewStatusLabel.setProperty("dentobotRole", "status")
        workspace_review_layout.addWidget(self.workspaceReviewStatusLabel)

        self.runtimeGroup = qt.QGroupBox("6.4 — Runtime and Task Confirmation", parent)
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
        runtime_buttons.addWidget(self.connectButton)
        runtime_buttons.addWidget(self.disconnectButton)
        runtime_layout.addLayout(runtime_buttons)
        confirmation_buttons = qt.QHBoxLayout()
        self.confirmTaskButton = qt.QPushButton(
            "Confirm Immutable Task Snapshot", self.runtimeGroup
        )
        self.openExpertDiagnosticsButton = qt.QPushButton(
            "Expert ROS Diagnostics…", self.runtimeGroup
        )
        confirmation_buttons.addWidget(self.confirmTaskButton)
        confirmation_buttons.addWidget(self.openExpertDiagnosticsButton)
        runtime_layout.addLayout(confirmation_buttons)
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

        self.approachGroup = qt.QGroupBox("6.5 — Goal 1: Approach", parent)
        self.approachGroup.objectName = "DENTOBOTApproachPhaseGroupBox"
        approach_layout = qt.QVBoxLayout(self.approachGroup)
        approach_description = qt.QLabel(
            "Plan collision-free to the configured pre-entry standoff, then "
            "validate the short terminal move to exact Entry. The translucent "
            "goal robot shows the pre-entry IK solution only; it does not mean "
            "the terminal path has planned successfully. During exploratory "
            "terminal preview, only configured burr-to-task-object collisions "
            "may be suppressed and every suppression is reported. Goal 1 is "
            "enabled only after the complete Entry-to-Target line passes a "
            "bounded reachability preflight; otherwise reposition the base.",
            self.approachGroup,
        )
        approach_description.wordWrap = True
        approach_layout.addWidget(approach_description)
        approach_buttons = qt.QHBoxLayout()
        self.planApproachButton = qt.QPushButton("Plan Guarded Approach", self.approachGroup)
        self.previewApproachButton = qt.QPushButton("Preview Goal 1", self.approachGroup)
        approach_buttons.addWidget(self.planApproachButton)
        approach_buttons.addWidget(self.previewApproachButton)
        approach_layout.addLayout(approach_buttons)
        self.approachStatusLabel = qt.QLabel("No Goal 1 plan.", self.approachGroup)
        self.approachStatusLabel.wordWrap = True
        self.approachStatusLabel.setProperty("dentobotRole", "status")
        approach_layout.addWidget(self.approachStatusLabel)

        self.drillingGroup = qt.QGroupBox("6.6 — Goal 2: Drilling Preview", parent)
        self.drillingGroup.objectName = "DENTOBOTDrillingPhaseGroupBox"
        drilling_layout = qt.QVBoxLayout(self.drillingGroup)
        drilling_description = qt.QLabel(
            "Generate Entry-to-Target motion strictly inside the approved corridor. "
            "Goal 2 continues the same immutable task-guard session and starts "
            "from Goal 1's accepted Entry state. For exploratory simulation, "
            "configured burr-to-task-anatomy/guide collisions may be suppressed "
            "and reported. All non-tool contacts, overshoot, backward motion, "
            "duplicate commands, and joint violations remain rejected. This is "
            "not collision-safe or executable evidence.",
            self.drillingGroup,
        )
        drilling_description.wordWrap = True
        drilling_layout.addWidget(drilling_description)
        drilling_buttons = qt.QHBoxLayout()
        self.planDrillingButton = qt.QPushButton("Plan Guarded Drilling Preview", self.drillingGroup)
        self.previewDrillingButton = qt.QPushButton("Preview Goal 2", self.drillingGroup)
        drilling_buttons.addWidget(self.planDrillingButton)
        drilling_buttons.addWidget(self.previewDrillingButton)
        drilling_layout.addLayout(drilling_buttons)
        self.drillingStatusLabel = qt.QLabel("No Goal 2 plan.", self.drillingGroup)
        self.drillingStatusLabel.wordWrap = True
        self.drillingStatusLabel.setProperty("dentobotRole", "status")
        drilling_layout.addWidget(self.drillingStatusLabel)
        blocked = qt.QLabel(
            "EXECUTE DISABLED — guarded simulation preview only. Hardware homing, drilling, and controller execution are blocked.",
            self.drillingGroup,
        )
        blocked.wordWrap = True
        blocked.setProperty("dentobotRole", "warning")
        drilling_layout.addWidget(blocked)

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
        self.enableCbctRenderingButton.clicked.connect(
            lambda checked=False: self._invoke("enable_cbct_rendering")
        )
        self.cbctPresetCombo.currentIndexChanged.connect(
            lambda index=0: self._invoke("cbct_preset")
        )
        self.createProxyButton.clicked.connect(
            lambda checked=False: self._invoke("create_proxy")
        )
        self.placementReviewButton.clicked.connect(
            lambda checked=False: self._invoke("placement_review")
        )
        self.saveTaskHomeButton.clicked.connect(
            lambda checked=False: self._invoke("save_home")
        )
        self.applyTaskHomeButton.clicked.connect(
            lambda checked=False: self._invoke("apply_home")
        )
        self.reviewLimitsButton.clicked.connect(
            lambda checked=False: self._invoke("review_limits")
        )
        self.confirmTaskButton.clicked.connect(
            lambda checked=False: self._invoke("confirm_task")
        )
        self.openExpertDiagnosticsButton.clicked.connect(
            lambda checked=False: self._invoke("expert_diagnostics")
        )
        self.planApproachButton.clicked.connect(
            lambda checked=False: self._invoke("plan_approach")
        )
        self.previewApproachButton.clicked.connect(
            lambda checked=False: self._invoke("preview_approach")
        )
        self.planDrillingButton.clicked.connect(
            lambda checked=False: self._invoke("plan_drilling")
        )
        self.previewDrillingButton.clicked.connect(
            lambda checked=False: self._invoke("preview_drilling")
        )
        self.visualizationGroup.visible = False
        self.homeGroup.visible = False
        self.workspaceReviewGroup.visible = False
        self.runtimeGroup.visible = False
        self.goalGroup.visible = False
        self.collisionGroup.visible = False
        self.approachGroup.visible = False
        self.drillingGroup.visible = False

    def _invoke(self, name: str) -> None:
        callback = self._callbacks.get(name)
        if callback:
            callback()

    def _invoke_appearance(self, key: str) -> None:
        callback = self._callbacks.get("appearance_changed")
        if callback:
            visible, opacity = self.appearanceControls[key]
            callback(key, bool(visible.checked), float(opacity.value) / 100.0)

    def cbctPreset(self) -> str:
        return str(self.cbctPresetCombo.currentData or "current")

    def setAppearance(self, key: str, visible: bool, opacity: float) -> None:
        controls = self.appearanceControls.get(key)
        if not controls:
            return
        checkbox, slider = controls
        checkbox.blockSignals(True)
        slider.blockSignals(True)
        try:
            checkbox.checked = bool(visible)
            slider.value = max(0, min(100, round(float(opacity) * 100.0)))
        finally:
            checkbox.blockSignals(False)
            slider.blockSignals(False)

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
