"""Presentation-only controls added by the new Robot Simulation workspace."""

from __future__ import annotations

import json
import qt


class DENTORobotSimulationPanel:
    """Build goal/IK and collision cards without calling robot services."""

    # One state-changing owner per Step 6 action. This prevents a hidden or
    # reparented legacy button from silently reintroducing an older substep
    # order. A value of -1 means the retained expert-only control has no
    # routine Step 6 owner and cannot be invoked from this panel.
    ACTION_OWNER_SUBSTEP = {
        "connect": 1,
        "disconnect": 1,
        "load_fallback": 1,
        "refresh": 1,
        "sync_collision": 1,
        "check_state": 1,
        "enable_cbct_rendering": 1,
        "cbct_preset": 1,
        "create_proxy": 1,
        "placement_review": 1,
        "appearance_changed": 1,
        "expert_diagnostics": 1,
        "save_home": 2,
        "apply_home": 2,
        "revalidate_workspace": 3,
        "review_limits": 3,
        "confirm_task": 4,
        "plan_approach": 5,
        "preview_approach": 5,
        "show_motion_diagnostics": 5,
        "plan_drilling": 6,
        "preview_drilling": 6,
        "create_goal": -1,
        "solve_ik": -1,
        "plan_goal": -1,
    }

    def __init__(self, parent, callbacks: dict[str, object]) -> None:
        self._callbacks = callbacks
        self._activeSubstep = 0
        self._diagnosticDialog = None
        self.visualizationGroup = qt.QGroupBox("Placement Context", parent)
        self.visualizationGroup.objectName = "DENTOBOTPlacementContextGroupBox"
        visualization_layout = qt.QVBoxLayout(self.visualizationGroup)
        visualization_description = qt.QLabel(
            "CBCT rendering is opt-in and display-only: it reuses the source "
            "volume without resampling or changing IJK-to-RAS. Legacy mount-plane "
            "and forehead-proxy tools are quarantined because they were derived "
            "from the robot base rather than independent patient evidence.",
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
            "Forehead Proxy — Quarantined", self.visualizationGroup
        )
        self.createProxyButton.enabled = False
        self.createProxyButton.toolTip = (
            "Deferred until an independent forehead/mount reference exists."
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
            ("collision_audit", "Outgoing collision payload", 45),
        )
        for row, (key, label, default) in enumerate(appearance_rows, start=1):
            visible = qt.QCheckBox(self.visualizationGroup)
            visible.checked = key not in {
                "cbct",
                "goal_robot",
                "forehead_proxy",
                "collision_audit",
            }
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

        self.homeGroup = qt.QGroupBox("6.2 — Live-Validated Task Home", parent)
        self.homeGroup.objectName = "DENTOBOTTaskHomeGroupBox"
        home_layout = qt.QVBoxLayout(self.homeGroup)
        home_description = qt.QLabel(
            "With ROS/MoveIt and the audited collision scene active, save the "
            "current accepted six-joint vector as the case/base-specific Task "
            "Home. Applying a saved Home plans from the monitored current state "
            "in MoveIt, then sends every plan waypoint through the strict simulation "
            "guard. This is not physical actuator homing; hardware homing remains unavailable.",
            self.homeGroup,
        )
        home_description.wordWrap = True
        home_layout.addWidget(home_description)
        home_buttons = qt.QHBoxLayout()
        self.saveTaskHomeButton = qt.QPushButton("Save Current as Task Home", self.homeGroup)
        self.applyTaskHomeButton = qt.QPushButton(
            "Plan + Apply Task Home", self.homeGroup
        )
        home_buttons.addWidget(self.saveTaskHomeButton)
        home_buttons.addWidget(self.applyTaskHomeButton)
        home_layout.addLayout(home_buttons)
        self.homeStatusLabel = qt.QLabel("Task Home has not been saved.", self.homeGroup)
        self.homeStatusLabel.wordWrap = True
        self.homeStatusLabel.setProperty("dentobotRole", "status")
        home_layout.addWidget(self.homeStatusLabel)

        self.workspaceReviewGroup = qt.QGroupBox(
            "6.3 — ROS Workspace and Assisted-Limit Review", parent
        )
        self.workspaceReviewGroup.objectName = "DENTOBOTAssistedLimitReviewGroupBox"
        workspace_review_layout = qt.QVBoxLayout(self.workspaceReviewGroup)
        workspace_review_description = qt.QLabel(
            "Every accepted TCP sample must retain its producing joint vector. "
            "Generate the static-valid workspace from live Task Home; a bounded "
            "representative subset is also planned from Home to classify connectivity. "
            "Inspect the suggested envelope, then explicitly review before applying.",
            self.workspaceReviewGroup,
        )
        workspace_review_description.wordWrap = True
        workspace_review_layout.addWidget(workspace_review_description)
        workspace_buttons = qt.QHBoxLayout()
        self.revalidateWorkspaceButton = qt.QPushButton(
            "Revalidate Saved Workspace", self.workspaceReviewGroup
        )
        self.revalidateWorkspaceButton.toolTip = (
            "Replay the persisted states through the current MoveIt scene; "
            "do not regenerate samples or change reviewed limits."
        )
        self.reviewLimitsButton = qt.QPushButton(
            "Review and Apply Suggested Limits", self.workspaceReviewGroup
        )
        workspace_buttons.addWidget(self.revalidateWorkspaceButton)
        workspace_buttons.addWidget(self.reviewLimitsButton)
        workspace_review_layout.addLayout(workspace_buttons)
        self.workspaceReviewStatusLabel = qt.QLabel(
            "No reviewed assisted-limit proposal.", self.workspaceReviewGroup
        )
        self.workspaceReviewStatusLabel.wordWrap = True
        self.workspaceReviewStatusLabel.setProperty("dentobotRole", "status")
        workspace_review_layout.addWidget(self.workspaceReviewStatusLabel)

        self.runtimeGroup = qt.QGroupBox("6.1 — ROS/MoveIt Runtime", parent)
        self.runtimeGroup.objectName = "DENTOBOTRobotRuntimeGroupBox"
        runtime_layout = qt.QVBoxLayout(self.runtimeGroup)
        runtime_description = qt.QLabel(
            "The desktop launcher owns the simulation-only ROS 2 and MoveIt "
            "stack. Connect is performed in 6.1 before Task Home and workspace "
            "validation. It never starts hardware execution.",
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
        self.openExpertDiagnosticsButton = qt.QPushButton(
            "Expert ROS Diagnostics…", self.runtimeGroup
        )
        runtime_layout.addWidget(self.openExpertDiagnosticsButton)
        self.runtimeStatusLabel = qt.QLabel(
            "Choose a case or phantom, then connect the simulation stack.",
            self.runtimeGroup,
        )
        self.runtimeStatusLabel.objectName = "DENTOBOTRobotRuntimeStatusLabel"
        self.runtimeStatusLabel.wordWrap = True
        self.runtimeStatusLabel.setProperty("dentobotRole", "status")
        runtime_layout.addWidget(self.runtimeStatusLabel)

        self.confirmationGroup = qt.QGroupBox(
            "6.4 — Immutable Task Confirmation", parent
        )
        self.confirmationGroup.objectName = "DENTOBOTTaskConfirmationGroupBox"
        confirmation_layout = qt.QVBoxLayout(self.confirmationGroup)
        confirmation_description = qt.QLabel(
            "Review the already-active ROS/MoveIt runtime, acknowledged collision "
            "scene, live-validated Task Home, and reviewed workspace evidence. "
            "6.4 only freezes one immutable task snapshot; runtime connection and "
            "collision-scene repair belong exclusively to 6.1.",
            self.confirmationGroup,
        )
        confirmation_description.wordWrap = True
        confirmation_layout.addWidget(confirmation_description)
        self.confirmTaskButton = qt.QPushButton(
            "Confirm Immutable Task Snapshot", self.confirmationGroup
        )
        confirmation_layout.addWidget(self.confirmTaskButton)
        self.confirmationStatusLabel = qt.QLabel(
            "Complete and validate 6.1–6.3 before confirming the task.",
            self.confirmationGroup,
        )
        self.confirmationStatusLabel.objectName = (
            "DENTOBOTTaskConfirmationStatusLabel"
        )
        self.confirmationStatusLabel.wordWrap = True
        self.confirmationStatusLabel.setProperty("dentobotRole", "status")
        confirmation_layout.addWidget(self.confirmationStatusLabel)

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

        self.collisionGroup = qt.QGroupBox("6.1 — Planning-Scene Audit", parent)
        self.collisionGroup.objectName = "DENTOBOTCollisionSceneGroupBox"
        collision_layout = qt.QVBoxLayout(self.collisionGroup)
        collision_description = qt.QLabel(
            "Connection performs the authoritative case collision-scene audit. "
            "Use these 6.1 controls only to inspect or explicitly repeat that "
            "synchronization before Task Home and workspace validation. DENTOBOT "
            "records source and outgoing mesh fingerprints, transform counts, "
            "units, topology, IDs, poses, and bounds; the collision guard must "
            "read back matching objects from MoveIt's monitored PlanningScene. "
            "This does not visualize FCL's private acceleration structure.",
            self.collisionGroup,
        )
        collision_description.wordWrap = True
        collision_layout.addWidget(collision_description)
        collision_buttons = qt.QHBoxLayout()
        self.refreshButton = qt.QPushButton("Refresh Status", self.collisionGroup)
        self.refreshButton.objectName = "DENTOBOTRefreshRobotCapabilitiesButton"
        self.syncCollisionButton = qt.QPushButton(
            "Audit + Sync Collision Surfaces",
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
            "Stage 1 plans from the exact live-validated Task Home to the "
            "explicit PreEntry IK state. Stage 2 follows the "
            "trajectory axis strictly to the configured terminal tolerance, then "
            "validate only that short final contact move to exact Entry. The translucent "
            "goal robot and the orange TCP phase path show the planned waypoints; "
            "the goal robot endpoint alone does not mean "
            "the terminal path has planned successfully. During exploratory "
            "terminal preview, only configured burr-to-task-object collisions "
            "may be suppressed and every suppression is reported. Goal 1 is "
            "enabled only after the complete Entry-to-Target line passes a "
            "bounded reachability preflight. A failed preflight retains "
            "last-valid/first-invalid evidence without assigning its cause.",
            self.approachGroup,
        )
        approach_description.wordWrap = True
        approach_layout.addWidget(approach_description)
        approach_buttons = qt.QHBoxLayout()
        self.planApproachButton = qt.QPushButton("Plan Guarded Approach", self.approachGroup)
        self.previewApproachButton = qt.QPushButton("Preview Goal 1", self.approachGroup)
        self.motionDiagnosticsButton = qt.QPushButton(
            "Inspect Motion Diagnostics", self.approachGroup
        )
        self.motionDiagnosticsButton.enabled = False
        approach_buttons.addWidget(self.planApproachButton)
        approach_buttons.addWidget(self.previewApproachButton)
        approach_buttons.addWidget(self.motionDiagnosticsButton)
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
        self.revalidateWorkspaceButton.clicked.connect(
            lambda checked=False: self._invoke("revalidate_workspace")
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
        self.motionDiagnosticsButton.clicked.connect(
            lambda checked=False: self._invoke("show_motion_diagnostics")
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
        self.confirmationGroup.visible = False
        self.goalGroup.visible = False
        self.collisionGroup.visible = False
        self.approachGroup.visible = False
        self.drillingGroup.visible = False

    def _invoke(self, name: str) -> None:
        owner = self.ACTION_OWNER_SUBSTEP.get(name)
        if owner is not None and owner != self._activeSubstep:
            self.runtimeStatusLabel.text = (
                f"Blocked stale Step 6 action '{name}': owner is 6.{owner}, "
                f"active substep is 6.{self._activeSubstep}."
            )
            self.runtimeStatusLabel.setProperty("dentobotState", "error")
            return
        callback = self._callbacks.get(name)
        if callback:
            callback()

    def _invoke_appearance(self, key: str) -> None:
        if self._activeSubstep != self.ACTION_OWNER_SUBSTEP["appearance_changed"]:
            return
        callback = self._callbacks.get("appearance_changed")
        if callback:
            visible, opacity = self.appearanceControls[key]
            callback(key, bool(visible.checked), float(opacity.value) / 100.0)

    def setActiveSubstep(self, substep_index: int) -> None:
        self._activeSubstep = max(0, min(int(substep_index), 6))

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

    def showMotionDiagnostics(
        self,
        session,
        on_candidate_selected,
        on_review,
    ) -> None:
        """Open the bounded operator-facing diagnostic candidate inspector."""
        if self._diagnosticDialog is not None:
            try:
                self._diagnosticDialog.close()
            except RuntimeError:
                pass
        dialog = qt.QDialog(self.approachGroup)
        dialog.windowTitle = "DENTOBOT Step 6 Motion Diagnostics"
        dialog.resize(980, 560)
        layout = qt.QVBoxLayout(dialog)
        summary = qt.QLabel(
            "Diagnostic evidence is display-only and non-authorizing. Selecting "
            "a row shows its retained last-valid joints on the translucent goal "
            "robot; the partial path is never promoted to preview. "
            f"State: {session.state}; review: {session.operator_review_state}."
            + (
                f" Stale reason: {session.stale_reason}"
                if session.stale_reason
                else ""
            ),
            dialog,
        )
        summary.wordWrap = True
        layout.addWidget(summary)
        table = qt.QTableWidget(dialog)
        records = tuple(session.candidate_records)
        headers = (
            "Stage",
            "Roll",
            "Clearance",
            "Result",
            "Fraction",
            "Distance",
            "Waypoints",
            "Classification",
            "Min joint margin",
        )
        table.setColumnCount(len(headers))
        table.setRowCount(len(records))
        table.setHorizontalHeaderLabels(list(headers))
        for row, record in enumerate(records):
            values = (
                str(record.get("stage", "")),
                f"{float(record.get('axial_roll_deg', 0.0)):.1f}°",
                (
                    "direct"
                    if record.get("clearance_sample_index") is None
                    else f"sample {int(record['clearance_sample_index'])}"
                ),
                "PASS" if record.get("success") else "PARTIAL/FAIL",
                f"{float(record.get('completion_fraction', 0.0)) * 100.0:.2f}%",
                (
                    f"{float(record.get('completed_distance_mm', 0.0)):.3f} / "
                    f"{float(record.get('requested_distance_mm', 0.0)):.3f} mm"
                ),
                str(int(record.get("waypoint_count", 0))),
                str(record.get("failure_classification") or "unknown"),
                (
                    "—"
                    if record.get("minimum_joint_margin_display") is None
                    else f"{float(record['minimum_joint_margin_display']):.3f}"
                ),
            )
            for column, value in enumerate(values):
                table.setItem(row, column, qt.QTableWidgetItem(value))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        scrubber = qt.QSlider(qt.Qt.Horizontal, dialog)
        scrubber.minimum = 0
        scrubber.maximum = max(0, len(records) - 1)
        scrubber.value = int(session.selected_candidate_index)
        layout.addWidget(scrubber)
        details = qt.QPlainTextEdit(dialog)
        details.readOnly = True
        layout.addWidget(details)
        dialog_buttons = qt.QHBoxLayout()
        review_button = qt.QPushButton("Mark Current Evidence Reviewed", dialog)
        close_button = qt.QPushButton("Close", dialog)
        dialog_buttons.addWidget(review_button)
        dialog_buttons.addWidget(close_button)
        layout.addLayout(dialog_buttons)
        close_button.clicked.connect(dialog.close)

        def review_evidence() -> None:
            if on_review:
                result = on_review()
                details.appendPlainText("\n\nReview result: " + result.message)
                if result.success:
                    review_button.enabled = False

        review_button.clicked.connect(review_evidence)
        review_button.enabled = session.operator_review_state != "Reviewed"

        def select_candidate(index: int) -> None:
            index = max(0, min(len(records) - 1, int(index)))
            table.selectRow(index)
            scrubber.blockSignals(True)
            scrubber.value = index
            scrubber.blockSignals(False)
            record = records[index]
            details.plainText = json.dumps(record, indent=2, sort_keys=True)
            if on_candidate_selected:
                result = on_candidate_selected(index)
                details.appendPlainText("\n\nDisplay result: " + result.message)

        table.currentCellChanged.connect(
            lambda row, column, previous_row, previous_column: (
                select_candidate(row) if row >= 0 else None
            )
        )
        scrubber.valueChanged.connect(select_candidate)
        self._diagnosticDialog = dialog
        select_candidate(int(session.selected_candidate_index))
        dialog.show()

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
        # Step-aware enablement is owned by widget_robot._updateStep6PlanningUi.
        # A generic capability refresh must not bypass the case/base/runtime
        # prerequisites by re-enabling Connect on its own.
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

    def showConfirmationResult(self, result) -> None:
        self._show_result(self.confirmationStatusLabel, result)

    def showCollisionResult(self, result) -> None:
        self._show_result(self.collisionStatusLabel, result)
