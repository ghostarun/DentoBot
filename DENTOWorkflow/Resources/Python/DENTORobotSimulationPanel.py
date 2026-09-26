"""Presentation-only controls added by the new Robot Simulation workspace."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from math import degrees, isfinite
import qt

from DENTORobotWorkflowFacade import STEP6_JOINT_PLANNER_ALGORITHMS
from DENTORobotPlacement import joint_positions_si_from_display
from DENTOStep6State import JOINT_NAMES


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
        "roi_from_incisors": 3,
        "revalidate_workspace": 3,
        "review_limits": 3,
        "confirm_task": 4,
        "reset_manual_draft": 5,
        "manual_draft_changed": 5,
        "check_manual_draft_state": 5,
        "guarded_manual_jog": 5,
        "export_manual_record": 5,
        "plan_approach": 5,
        "check_preentry_ik": 5,
        "check_planning_p1": 5,
        "check_planning_p2": 5,
        "check_planning_p3": 5,
        "compare_planners": 5,
        "cancel_planner_comparison": 5,
        "show_planner_comparison": 5,
        "template_collision_override": 5,
        "begin_anatomy_review": 5,
        "edit_anatomy_review": 5,
        "activate_anatomy_review": 5,
        "discard_anatomy_review": 5,
        "preview_approach": 5,
        "show_motion_diagnostics": 5,
        "plan_drilling": 6,
        "preview_drilling": 6,
        "stop_preview": (5, 6),
        "return_home": (5, 6),
        "create_goal": -1,
        "solve_ik": -1,
        "plan_goal": -1,
    }
    PLACEMENT_SURFACE_ACTIONS = frozenset(
        {
            "load_fallback",
            "enable_cbct_rendering",
            "cbct_preset",
            "create_proxy",
            "placement_review",
            "appearance_changed",
        }
    )

    def __init__(self, parent, callbacks: dict[str, object]) -> None:
        self._callbacks = callbacks
        self._activeSubstep = 0
        self._placementSurfaceActive = False
        self._diagnosticDialog = None
        self._manualJogLimits = {}
        self._manualJogLimitsValid = False
        self._manualJogAcceptedJointPositionsSi = None
        self._manualJogDraftInitialized = False
        self._manualJogBusy = False
        self._manualJogAvailable = False
        self._manualJogGuardAvailable = False
        self.manualJogReconciliationRequired = False
        self._manualJogEvidence = None
        self._manualDraftStateCheckEvidence = None
        self._manualDraftStateCheckRequested = None
        settings = qt.QSettings()
        self._plannerId = "RRTConnectkConfigDefault"
        self._planningAttempts = max(
            1, min(10, int(settings.value("DENTOBOT/Step6PlanningAttempts", 1)))
        )
        self._planningTimeSec = max(
            0.5, min(60.0, float(settings.value("DENTOBOT/Step6PlanningTimeSec", 5.0)))
        )
        self.visualizationGroup = qt.QGroupBox("Placement Context", parent)
        self.visualizationGroup.objectName = "DENTOBOTPlacementContextGroupBox"
        visualization_layout = qt.QVBoxLayout(self.visualizationGroup)
        visualization_description = qt.QLabel(
            "CBCT rendering is opt-in and display-only: it reuses the source "
            "volume without resampling or changing IJK-to-RAS. Propose a virtual "
            "forehead from the opened Case Foundation (not from the robot). "
            "That prior is visualization-only, not physical mount truth.",
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
            "Propose virtual forehead + base", self.visualizationGroup
        )
        self.createProxyButton.enabled = True
        self.createProxyButton.toolTip = (
            "Build an independent virtual forehead outside the CBCT FOV from "
            "the Case Foundation dental frame, then seat an unreviewed "
            "simulation base. Review and lock afterwards. Not S6-U-02."
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
            "Review the current accepted J1–J5 candidate below, then explicitly "
            "accept it as the case/base-specific Task Home. Acceptance uses the "
            "existing live guard, monitored-state, limit, and synchronized-scene "
            "checks. Applying a saved Home plans from the monitored current state "
            "in MoveIt, then sends every plan waypoint through the strict simulation "
            "guard. This is not physical actuator homing; hardware homing remains unavailable.",
            self.homeGroup,
        )
        home_description.wordWrap = True
        home_layout.addWidget(home_description)
        home_buttons = qt.QHBoxLayout()
        self.saveTaskHomeButton = qt.QPushButton("Accept Task Home", self.homeGroup)
        self.saveTaskHomeButton.toolTip = (
            "Accept the displayed current J1–J5 candidate through the existing "
            "saveTaskHome checks. A stale monitored state, failed live guard, "
            "limit conflict, or unsynchronized scene leaves Task Home unaccepted."
        )
        self.applyTaskHomeButton = qt.QPushButton(
            "Plan + Apply Task Home", self.homeGroup
        )
        home_buttons.addWidget(self.saveTaskHomeButton)
        home_buttons.addWidget(self.applyTaskHomeButton)
        home_layout.addLayout(home_buttons)
        self.taskHomeCandidateLabel = qt.QLabel(
            "Candidate Task Home: current accepted J1–J5 state unavailable; J6 is excluded.",
            self.homeGroup,
        )
        self.taskHomeCandidateLabel.objectName = "DENTOBOTTaskHomeCandidateLabel"
        self.taskHomeCandidateLabel.wordWrap = True
        home_layout.addWidget(self.taskHomeCandidateLabel)
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
        roi_description = qt.QLabel(
            "Task-space ROI draft (world RAS, mm). It bounds TCP candidate sampling only.",
            self.workspaceReviewGroup,
        )
        roi_description.wordWrap = True
        workspace_review_layout.addWidget(roi_description)
        self._loadingTaskSpaceRoi = False
        self._taskSpaceRoiStatusContext = "ROI source not loaded."
        self._taskSpaceRoiInitialized = False
        self._taskSpaceRoiOpeningRevision = None
        self._taskSpaceRoiGapLineNodeId = ""
        roi_center_row = qt.QHBoxLayout()
        roi_center_row.addWidget(qt.QLabel("Center RAS (mm):", self.workspaceReviewGroup))
        self.taskSpaceRoiCenterSpinBoxes = []
        for axis in "XYZ":
            roi_center_row.addWidget(qt.QLabel(axis, self.workspaceReviewGroup))
            spin = qt.QDoubleSpinBox(self.workspaceReviewGroup)
            spin.objectName = f"DENTOBOTTaskSpaceRoiCenter{axis}SpinBox"
            spin.minimum, spin.maximum = -1.0e9, 1.0e9
            spin.decimals, spin.singleStep = 6, 1.0
            spin.setSpecialValueText(" ")
            spin.value, spin.enabled = spin.minimum, False
            roi_center_row.addWidget(spin)
            self.taskSpaceRoiCenterSpinBoxes.append(spin)
        workspace_review_layout.addLayout(roi_center_row)
        roi_dimensions_row = qt.QHBoxLayout()
        roi_dimensions_row.addWidget(
            qt.QLabel("Dimensions XYZ (mm):", self.workspaceReviewGroup)
        )
        self.taskSpaceRoiDimensionsSpinBoxes = []
        for axis in "XYZ":
            roi_dimensions_row.addWidget(qt.QLabel(axis, self.workspaceReviewGroup))
            spin = qt.QDoubleSpinBox(self.workspaceReviewGroup)
            spin.objectName = f"DENTOBOTTaskSpaceRoiDimension{axis}SpinBox"
            spin.minimum, spin.maximum = 0.01, 1.0e9
            spin.decimals, spin.singleStep = 6, 1.0
            spin.setSpecialValueText(" ")
            spin.value, spin.enabled = spin.minimum, False
            roi_dimensions_row.addWidget(spin)
            self.taskSpaceRoiDimensionsSpinBoxes.append(spin)
        workspace_review_layout.addLayout(roi_dimensions_row)
        self.useCurrentIncisorMidpointButton = qt.QPushButton(
            "Use current incisor midpoint", self.workspaceReviewGroup
        )
        self.useCurrentIncisorMidpointButton.toolTip = (
            "Load the current Case Foundation upper/opened-lower incisor midpoint "
            "into this editable ROI draft; this does not generate or validate samples."
        )
        workspace_review_layout.addWidget(self.useCurrentIncisorMidpointButton)
        self.taskSpaceRoiStatusLabel = qt.QLabel(
            "ROI source not loaded. Samples are not generated or validated.",
            self.workspaceReviewGroup,
        )
        self.taskSpaceRoiStatusLabel.wordWrap = True
        self.taskSpaceRoiStatusLabel.setProperty("dentobotRole", "status")
        workspace_review_layout.addWidget(self.taskSpaceRoiStatusLabel)
        for spin in (
            self.taskSpaceRoiCenterSpinBoxes + self.taskSpaceRoiDimensionsSpinBoxes
        ):
            spin.valueChanged.connect(self._onTaskSpaceRoiEdited)
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
            "Activate a prepared case, then connect the simulation stack.",
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

        self.manualJogGroup = qt.QGroupBox(
            "6.3B — Manual Robot Simulation Solver: Joint Jog", parent
        )
        self.manualJogGroup.objectName = "DENTOBOTManualJogGroupBox"
        manual_jog_layout = qt.QVBoxLayout(self.manualJogGroup)
        manual_jog_description = qt.QLabel(
            "Edit a display-only J1–J5 draft, then request one exact guarded "
            "simulation jog. The accepted robot changes only after the guard "
            "acknowledges the requested state. This does not create a route or "
            "authorize preview.",
            self.manualJogGroup,
        )
        manual_jog_description.wordWrap = True
        manual_jog_layout.addWidget(manual_jog_description)
        self.manualJogAcceptedStateLabel = qt.QLabel(
            "Accepted state: unavailable", self.manualJogGroup
        )
        self.manualJogAcceptedStateLabel.objectName = (
            "DENTOBOTManualJogAcceptedStateLabel"
        )
        self.manualJogAcceptedStateLabel.wordWrap = True
        manual_jog_layout.addWidget(self.manualJogAcceptedStateLabel)
        self.manualJogDraftStateLabel = qt.QLabel(
            "Draft state: unavailable", self.manualJogGroup
        )
        self.manualJogDraftStateLabel.objectName = "DENTOBOTManualJogDraftStateLabel"
        self.manualJogDraftStateLabel.wordWrap = True
        manual_jog_layout.addWidget(self.manualJogDraftStateLabel)
        self.manualJogJointControls = {}
        self._manualJogDisplayValues = (0.0, 0.0, 0.0, 0.0, 0.0)
        units = ("deg", "mm", "deg", "mm", "deg")
        joint_labels = ("J1", "J2", "J3", "J4", "J5")
        joint_rows = qt.QGridLayout()
        for index, (joint, label, unit) in enumerate(
            zip(JOINT_NAMES, joint_labels, units, strict=True)
        ):
            joint_label = qt.QLabel(f"{label} ({unit})", self.manualJogGroup)
            joint_rows.addWidget(joint_label, index, 0)
            slider = qt.QSlider(qt.Qt.Horizontal, self.manualJogGroup)
            slider.objectName = f"DENTOBOTManualJog{label}Slider"
            slider.minimum = 0
            slider.maximum = 10000
            value = qt.QDoubleSpinBox(self.manualJogGroup)
            value.objectName = f"DENTOBOTManualJog{label}Value"
            value.decimals = 2
            value.singleStep = 0.1
            value.keyboardTracking = True
            self.manualJogJointControls[joint] = (slider, value, joint_label)
            slider.valueChanged.connect(
                lambda position=0, name=joint: self._onManualJogSliderChanged(
                    name, position
                )
            )
            value.valueChanged.connect(
                lambda current=0.0, name=joint: self._onManualJogNumericChanged(
                    name, current
                )
            )
            joint_rows.addWidget(slider, index, 1)
            joint_rows.addWidget(value, index, 2)
        manual_jog_layout.addLayout(joint_rows)
        self.manualJogJ6Label = qt.QLabel(
            "J6: fixed at 0° — external pneumatic spindle, unavailable to arm jogs.",
            self.manualJogGroup,
        )
        self.manualJogJ6Label.objectName = "DENTOBOTManualJogJ6FixedLabel"
        manual_jog_layout.addWidget(self.manualJogJ6Label)
        manual_jog_actions = qt.QHBoxLayout()
        self.resetManualJogDraftButton = qt.QPushButton(
            "Reset Draft to Accepted Current State", self.manualJogGroup
        )
        self.resetManualJogDraftButton.objectName = (
            "DENTOBOTResetManualJogDraftButton"
        )
        self.guardedManualJogButton = qt.QPushButton(
            "Guarded Jog", self.manualJogGroup
        )
        self.guardedManualJogButton.objectName = "DENTOBOTGuardedManualJogButton"
        self.checkManualDraftStateButton = qt.QPushButton(
            "Check Draft State", self.manualJogGroup
        )
        self.checkManualDraftStateButton.objectName = (
            "DENTOBOTCheckManualDraftStateButton"
        )
        self.checkManualDraftStateButton.toolTip = (
            "Run the read-only static state evaluator on the current J1–J5 draft. "
            "This does not jog, plan, or authorize a route or preview."
        )
        self.exportManualRecordButton = qt.QPushButton(
            "Export Historical Record…", self.manualJogGroup
        )
        self.exportManualRecordButton.objectName = (
            "DENTOBOTExportManualSimulationRecordButton"
        )
        self.exportManualRecordButton.toolTip = (
            "Export the validated manual simulation record as historical, "
            "display-only JSON. It cannot restore live state or authorize a route or preview."
        )
        manual_jog_actions.addWidget(self.resetManualJogDraftButton)
        manual_jog_actions.addWidget(self.checkManualDraftStateButton)
        manual_jog_actions.addWidget(self.guardedManualJogButton)
        manual_jog_actions.addWidget(self.exportManualRecordButton)
        manual_jog_layout.addLayout(manual_jog_actions)
        self.manualJogStatusLabel = qt.QLabel(
            "Guard status: unknown — no jog has been requested.",
            self.manualJogGroup,
        )
        self.manualJogStatusLabel.objectName = "DENTOBOTManualJogStatusLabel"
        self.manualJogStatusLabel.wordWrap = True
        self.manualJogStatusLabel.setProperty("dentobotRole", "status")
        manual_jog_layout.addWidget(self.manualJogStatusLabel)
        self.manualDraftStateCheckStatusLabel = qt.QLabel(
            "Draft-state check: not run.", self.manualJogGroup
        )
        self.manualDraftStateCheckStatusLabel.objectName = (
            "DENTOBOTManualDraftStateCheckStatusLabel"
        )
        self.manualDraftStateCheckStatusLabel.wordWrap = True
        self.manualDraftStateCheckStatusLabel.setProperty("dentobotRole", "status")
        manual_jog_layout.addWidget(self.manualDraftStateCheckStatusLabel)
        self.manualRecordExportStatusLabel = qt.QLabel(
            "Export status: no export requested.", self.manualJogGroup
        )
        self.manualRecordExportStatusLabel.objectName = (
            "DENTOBOTManualRecordExportStatusLabel"
        )
        self.manualRecordExportStatusLabel.wordWrap = True
        self.manualRecordExportStatusLabel.setProperty("dentobotRole", "status")
        manual_jog_layout.addWidget(self.manualRecordExportStatusLabel)

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

        self.approachGroup = qt.QGroupBox("6.5 — Approach", parent)
        self.approachGroup.objectName = "DENTOBOTApproachPhaseGroupBox"
        approach_layout = qt.QVBoxLayout(self.approachGroup)
        approach_description = qt.QLabel(
            "Stage 1 plans from the exact live-validated Task Home to the "
            "explicit PreEntry IK state and commits one complete tool frame. "
            "Its tool axis is the approved Entry-to-Target line; its arm-frame "
            "rotation is selected once at PreEntry, then remains fixed through "
            "Stages 2 and 3. Candidate branches are ranked by complete-chain "
            "acceptance and post-PreEntry arm motion, not PreEntry reach alone. "
            "Stage 2 follows the trajectory axis from PreEntry to exact Entry. "
            "MoveIt supplies the complete kinematic line and the independent "
            "phase guard validates every state, suppressing only configured "
            "burr-to-task contact while retaining every other collision rule. The translucent "
            "goal robot and the orange TCP phase path show the planned waypoints; "
            "the goal robot endpoint alone does not mean "
            "the terminal path has planned successfully. During exploratory "
            "terminal preview, only configured burr-to-task-object collisions "
            "may be suppressed and every suppression is reported. Approach planning is "
            "enabled only after the complete Entry-to-Target line passes a "
            "bounded reachability preflight. A failed preflight retains "
            "last-valid/first-invalid evidence without assigning its cause.",
            self.approachGroup,
        )
        approach_description.wordWrap = True
        approach_layout.addWidget(approach_description)
        spindle_policy = qt.QLabel(
            "Spindle locked — external pressure/RPM; not planned. Joint 6 remains "
            "in the compatibility vector at 0 rad.",
            self.approachGroup,
        )
        spindle_policy.wordWrap = True
        spindle_policy.setProperty("dentobotRole", "status")
        approach_layout.addWidget(spindle_policy)
        self.toolInsertionStatusLabel = qt.QLabel(
            "Tool insertion capacity will be checked before Approach planning.",
            self.approachGroup,
        )
        self.toolInsertionStatusLabel.wordWrap = True
        self.toolInsertionStatusLabel.setProperty("dentobotRole", "status")
        approach_layout.addWidget(self.toolInsertionStatusLabel)
        self.templateCollisionOverrideCheckBox = qt.QCheckBox(
            "Functional x4 override: exclude unresolved Step 5C final template from MoveIt collisions",
            self.approachGroup,
        )
        self.templateCollisionOverrideCheckBox.toolTip = (
            "Retired from the normal baseline. Enable "
            "DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE=1 only for a documented "
            "legacy diagnostic; it is non-persistent and non-authoritative."
        )
        self.templateCollisionOverrideCheckBox.enabled = (
            os.environ.get("DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE", "")
            == "1"
        )
        approach_layout.addWidget(self.templateCollisionOverrideCheckBox)
        self.templateCollisionOverrideStatusLabel = qt.QLabel(
            "Retired — the complete Step 5C template remains collision checked.",
            self.approachGroup,
        )
        self.templateCollisionOverrideStatusLabel.wordWrap = True
        self.templateCollisionOverrideStatusLabel.setProperty(
            "dentobotRole", "warning"
        )
        approach_layout.addWidget(self.templateCollisionOverrideStatusLabel)
        self.anatomyReviewGroup = qt.QGroupBox(
            "Manual non-target anatomy review (session only)", self.approachGroup
        )
        anatomy_review_layout = qt.QVBoxLayout(self.anatomyReviewGroup)
        anatomy_review_description = qt.QLabel(
            "Use this only after CBCT/segmentation review identifies a local "
            "artifact. It copies one non-target tooth into a disposable Segment "
            "Editor review node. The source segmentation is not edited. A reviewed "
            "proxy is never activated automatically and is not saved into MRML or a "
            "DentoCase.",
            self.anatomyReviewGroup,
        )
        anatomy_review_description.wordWrap = True
        anatomy_review_layout.addWidget(anatomy_review_description)
        anatomy_review_controls = qt.QHBoxLayout()
        self.anatomyReviewToothCombo = qt.QComboBox(self.anatomyReviewGroup)
        self.anatomyReviewToothCombo.objectName = "DENTOBOTAnatomyReviewToothCombo"
        self.createAnatomyReviewButton = qt.QPushButton(
            "Create review copy", self.anatomyReviewGroup
        )
        anatomy_review_controls.addWidget(self.anatomyReviewToothCombo, 1)
        anatomy_review_controls.addWidget(self.createAnatomyReviewButton)
        anatomy_review_layout.addLayout(anatomy_review_controls)
        anatomy_review_actions = qt.QHBoxLayout()
        self.editAnatomyReviewButton = qt.QPushButton(
            "Open review in Segment Editor", self.anatomyReviewGroup
        )
        self.anatomyReviewConfirmedCheckBox = qt.QCheckBox(
            "I confirm the edited local region is a segmentation artifact",
            self.anatomyReviewGroup,
        )
        self.applyAnatomyReviewButton = qt.QPushButton(
            "Use reviewed proxy for research simulation", self.anatomyReviewGroup
        )
        self.discardAnatomyReviewButton = qt.QPushButton(
            "Discard review", self.anatomyReviewGroup
        )
        anatomy_review_actions.addWidget(self.editAnatomyReviewButton)
        anatomy_review_actions.addWidget(self.anatomyReviewConfirmedCheckBox)
        anatomy_review_actions.addWidget(self.applyAnatomyReviewButton)
        anatomy_review_actions.addWidget(self.discardAnatomyReviewButton)
        anatomy_review_layout.addLayout(anatomy_review_actions)
        self.anatomyReviewStatusLabel = qt.QLabel(
            "No manual anatomy-review copy exists. Source anatomy remains authoritative.",
            self.anatomyReviewGroup,
        )
        self.anatomyReviewStatusLabel.wordWrap = True
        self.anatomyReviewStatusLabel.setProperty("dentobotRole", "warning")
        anatomy_review_layout.addWidget(self.anatomyReviewStatusLabel)
        approach_layout.addWidget(self.anatomyReviewGroup)
        approach_buttons = qt.QHBoxLayout()
        self.planApproachButton = qt.QPushButton("Plan Guarded Approach", self.approachGroup)
        self.checkPreEntryIKButton = qt.QPushButton(
            "Check PreEntry IK", self.approachGroup
        )
        self.checkPlanningP1Button = qt.QPushButton(
            "Check P1 Home→PreEntry", self.approachGroup
        )
        self.checkPlanningP1Button.objectName = "DENTOBOTCheckPlanningP1Button"
        self.checkPlanningP2Button = qt.QPushButton(
            "Check P2 PreEntry→Entry", self.approachGroup
        )
        self.checkPlanningP2Button.objectName = "DENTOBOTCheckPlanningP2Button"
        self.checkPlanningP3Button = qt.QPushButton(
            "Check P3 Entry→Target", self.approachGroup
        )
        self.checkPlanningP3Button.objectName = "DENTOBOTCheckPlanningP3Button"
        self.previewApproachButton = qt.QPushButton("Preview Approach", self.approachGroup)
        self.motionDiagnosticsButton = qt.QPushButton(
            "Inspect Motion Diagnostics", self.approachGroup
        )
        self.motionDiagnosticsButton.enabled = False
        approach_buttons.addWidget(self.planApproachButton)
        approach_buttons.addWidget(self.checkPreEntryIKButton)
        approach_buttons.addWidget(self.previewApproachButton)
        approach_buttons.addWidget(self.motionDiagnosticsButton)
        approach_layout.addLayout(approach_buttons)
        stage_diagnostic_buttons = qt.QHBoxLayout()
        for button in (
            self.checkPlanningP1Button,
            self.checkPlanningP2Button,
            self.checkPlanningP3Button,
        ):
            stage_diagnostic_buttons.addWidget(button)
        approach_layout.addLayout(stage_diagnostic_buttons)
        comparison_actions = qt.QHBoxLayout()
        self.comparePlannersButton = qt.QPushButton("Compare Three Planners", self.approachGroup)
        self.comparePlannersButton.objectName = "DENTOBOTCompareThreePlannersButton"
        self.cancelPlannerComparisonButton = qt.QPushButton("Cancel Comparison", self.approachGroup)
        self.cancelPlannerComparisonButton.enabled = False
        self.showPlannerComparisonButton = qt.QPushButton("View Planner Comparison", self.approachGroup)
        self.showPlannerComparisonButton.enabled = False
        for button in (self.comparePlannersButton, self.cancelPlannerComparisonButton,
                       self.showPlannerComparisonButton):
            comparison_actions.addWidget(button)
        approach_layout.addLayout(comparison_actions)
        self.plannerComparisonProgressLabel = qt.QLabel("No comparison running.", self.approachGroup)
        approach_layout.addWidget(self.plannerComparisonProgressLabel)
        self.approachPlanningPolicyButton = qt.QPushButton(
            "Planning Parameters…", self.approachGroup
        )
        approach_layout.addWidget(self.approachPlanningPolicyButton)
        preview_controls = qt.QHBoxLayout()
        self.stopPreviewButton = qt.QPushButton("Stop Preview", self.approachGroup)
        self.returnHomeButton = qt.QPushButton("Guarded Return Home", self.approachGroup)
        preview_controls.addWidget(self.stopPreviewButton)
        preview_controls.addWidget(self.returnHomeButton)
        approach_layout.addLayout(preview_controls)
        preview_settings = qt.QHBoxLayout()
        preview_settings.addWidget(qt.QLabel("Preview speed:", self.approachGroup))
        self.previewSpeedCombo = qt.QComboBox(self.approachGroup)
        for label, multiplier in (
            ("0.25×", 0.25),
            ("0.5×", 0.5),
            ("1×", 1.0),
            ("2×", 2.0),
            ("4×", 4.0),
            ("8×", 8.0),
        ):
            self.previewSpeedCombo.addItem(label, multiplier)
        saved_speed = float(qt.QSettings().value("DENTOBOT/Step6PreviewSpeed", 8.0))
        speed_index = min(
            range(self.previewSpeedCombo.count),
            key=lambda index: abs(float(self.previewSpeedCombo.itemData(index)) - saved_speed),
        )
        self.previewSpeedCombo.currentIndex = speed_index
        self.previewSpeedCombo.currentIndexChanged.connect(
            lambda _index=0: qt.QSettings().setValue(
                "DENTOBOT/Step6PreviewSpeed", self.previewSpeedMultiplier()
            )
        )
        preview_settings.addWidget(self.previewSpeedCombo)
        preview_settings.addStretch(1)
        approach_layout.addLayout(preview_settings)
        self.approachStatusLabel = qt.QLabel("No Approach plan.", self.approachGroup)
        self.approachStatusLabel.wordWrap = True
        self.approachStatusLabel.setProperty("dentobotRole", "status")
        approach_layout.addWidget(self.approachStatusLabel)
        self.previewProgressBar = qt.QProgressBar(self.approachGroup)
        self.previewProgressBar.minimum = 0
        self.previewProgressBar.maximum = 1
        self.previewProgressBar.value = 0
        self.previewProgressBar.format = "Preview: 0/0"
        approach_layout.addWidget(self.previewProgressBar)
        self.previewProgressLabel = qt.QLabel(
            "No guarded preview is running.", self.approachGroup
        )
        self.previewProgressLabel.wordWrap = True
        self.previewProgressLabel.setProperty("dentobotRole", "status")
        approach_layout.addWidget(self.previewProgressLabel)

        self.drillingGroup = qt.QGroupBox("6.6 — Drill Preview", parent)
        self.drillingGroup.objectName = "DENTOBOTDrillingPhaseGroupBox"
        drilling_layout = qt.QVBoxLayout(self.drillingGroup)
        drilling_description = qt.QLabel(
            "Use the prevalidated Entry-to-Target motion strictly inside the approved corridor. "
            "Drill preview continues the same immutable task-guard session and starts "
            "from the Approach preview's accepted Entry state. For exploratory simulation, "
            "configured burr-to-task-anatomy/guide collisions may be suppressed "
            "and reported. All non-tool contacts, overshoot, backward motion, "
            "duplicate commands, and joint violations remain rejected. This is "
            "not collision-safe or executable evidence.",
            self.drillingGroup,
        )
        drilling_description.wordWrap = True
        drilling_layout.addWidget(drilling_description)
        drilling_buttons = qt.QHBoxLayout()
        self.planDrillingButton = qt.QPushButton("Prepare Drill Preview", self.drillingGroup)
        self.previewDrillingButton = qt.QPushButton("Preview Drill", self.drillingGroup)
        drilling_buttons.addWidget(self.planDrillingButton)
        drilling_buttons.addWidget(self.previewDrillingButton)
        drilling_layout.addLayout(drilling_buttons)
        self.drillingPlanningPolicyButton = qt.QPushButton(
            "Planning Parameters…", self.drillingGroup
        )
        drilling_layout.addWidget(self.drillingPlanningPolicyButton)
        drilling_controls = qt.QHBoxLayout()
        self.stopPreviewDrillingButton = qt.QPushButton(
            "Stop Preview", self.drillingGroup
        )
        self.returnHomeDrillingButton = qt.QPushButton(
            "Guarded Return Home", self.drillingGroup
        )
        drilling_controls.addWidget(self.stopPreviewDrillingButton)
        drilling_controls.addWidget(self.returnHomeDrillingButton)
        drilling_layout.addLayout(drilling_controls)
        self.drillingStatusLabel = qt.QLabel("No Drill preview plan.", self.drillingGroup)
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
        self.useCurrentIncisorMidpointButton.clicked.connect(
            lambda checked=False: self._invoke("roi_from_incisors")
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
        self.checkPreEntryIKButton.clicked.connect(
            lambda checked=False: self._invoke("check_preentry_ik")
        )
        self.checkPlanningP1Button.clicked.connect(
            lambda checked=False: self._invoke("check_planning_p1")
        )
        self.checkPlanningP2Button.clicked.connect(
            lambda checked=False: self._invoke("check_planning_p2")
        )
        self.checkPlanningP3Button.clicked.connect(
            lambda checked=False: self._invoke("check_planning_p3")
        )
        self.resetManualJogDraftButton.clicked.connect(
            lambda checked=False: self._invoke("reset_manual_draft")
        )
        self.checkManualDraftStateButton.clicked.connect(
            lambda checked=False: self._invoke(
                "check_manual_draft_state", self.manualJogJointPositionsSi()
            )
        )
        self.guardedManualJogButton.clicked.connect(
            lambda checked=False: self._invoke(
                "guarded_manual_jog", self.manualJogJointPositionsSi()
            )
        )
        self.exportManualRecordButton.clicked.connect(
            lambda checked=False: self._invoke("export_manual_record")
        )
        self.comparePlannersButton.clicked.connect(
            lambda checked=False: self._invoke("compare_planners")
        )
        self.cancelPlannerComparisonButton.clicked.connect(
            lambda checked=False: self._invoke("cancel_planner_comparison")
        )
        self.showPlannerComparisonButton.clicked.connect(
            lambda checked=False: self._invoke("show_planner_comparison")
        )
        self.templateCollisionOverrideCheckBox.toggled.connect(
            lambda checked=False: self._invoke("template_collision_override")
        )
        self.createAnatomyReviewButton.clicked.connect(
            lambda checked=False: self._invoke("begin_anatomy_review")
        )
        self.editAnatomyReviewButton.clicked.connect(
            lambda checked=False: self._invoke("edit_anatomy_review")
        )
        self.applyAnatomyReviewButton.clicked.connect(
            lambda checked=False: self._invoke("activate_anatomy_review")
        )
        self.discardAnatomyReviewButton.clicked.connect(
            lambda checked=False: self._invoke("discard_anatomy_review")
        )
        self.previewApproachButton.clicked.connect(
            lambda checked=False: self._invoke("preview_approach")
        )
        self.motionDiagnosticsButton.clicked.connect(
            lambda checked=False: self._invoke("show_motion_diagnostics")
        )
        self.approachPlanningPolicyButton.clicked.connect(
            lambda checked=False: self.showPlanningPolicyDialog()
        )
        self.drillingPlanningPolicyButton.clicked.connect(
            lambda checked=False: self.showPlanningPolicyDialog()
        )
        self.planDrillingButton.clicked.connect(
            lambda checked=False: self._invoke("plan_drilling")
        )
        self.previewDrillingButton.clicked.connect(
            lambda checked=False: self._invoke("preview_drilling")
        )
        self.stopPreviewButton.clicked.connect(
            lambda checked=False: self._invoke("stop_preview")
        )
        self.returnHomeButton.clicked.connect(
            lambda checked=False: self._invoke("return_home")
        )
        self.stopPreviewDrillingButton.clicked.connect(
            lambda checked=False: self._invoke("stop_preview")
        )
        self.returnHomeDrillingButton.clicked.connect(
            lambda checked=False: self._invoke("return_home")
        )
        self.visualizationGroup.visible = False
        self.homeGroup.visible = False
        self.workspaceReviewGroup.visible = False
        self.runtimeGroup.visible = False
        self.confirmationGroup.visible = False
        self.goalGroup.visible = False
        self.manualJogGroup.visible = False
        self.collisionGroup.visible = False
        self.approachGroup.visible = False
        self.drillingGroup.visible = False

    def setAnatomyReviewCandidates(
        self,
        candidates: list[dict[str, object]] | tuple[dict[str, object], ...],
        state: dict[str, object] | None = None,
    ) -> None:
        """Refresh the small session-only anatomy-review control surface."""

        state = state or {}
        selected = str(self.anatomyReviewToothCombo.currentData or "")
        self.anatomyReviewToothCombo.blockSignals(True)
        self.anatomyReviewToothCombo.clear()
        for candidate in candidates:
            segment_id = str(candidate.get("segmentId") or "")
            if not segment_id:
                continue
            label = str(candidate.get("displayName") or segment_id)
            fdi = str(candidate.get("fdiNumber") or "")
            if fdi and fdi not in label:
                label = f"{label} — FDI {fdi}"
            self.anatomyReviewToothCombo.addItem(label, segment_id)
        for index in range(self.anatomyReviewToothCombo.count):
            if str(self.anatomyReviewToothCombo.itemData(index) or "") == selected:
                self.anatomyReviewToothCombo.currentIndex = index
                break
        self.anatomyReviewToothCombo.blockSignals(False)
        exists = bool(state.get("exists"))
        active = bool(state.get("active"))
        historical_enabled = bool(state.get("historicalOverrideEnabled", False))
        self.createAnatomyReviewButton.enabled = historical_enabled
        self.editAnatomyReviewButton.enabled = exists and not active
        self.anatomyReviewConfirmedCheckBox.enabled = exists and not active
        self.applyAnatomyReviewButton.enabled = exists and not active
        self.discardAnatomyReviewButton.enabled = exists
        if not historical_enabled:
            self.editAnatomyReviewButton.enabled = False
            self.anatomyReviewConfirmedCheckBox.enabled = False
            self.applyAnatomyReviewButton.enabled = False
            self.anatomyReviewStatusLabel.text = (
                "Retired from the normal baseline. Source CBCT segmentation remains "
                "authoritative; set DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW=1 "
                "only for a documented legacy diagnostic."
            )
            self.anatomyReviewStatusLabel.setProperty("dentobotRole", "warning")
        elif active:
            self.anatomyReviewStatusLabel.text = (
                "ACTIVE — RESEARCH SIMULATION ANATOMY OVERRIDE. Only this "
                "session uses the confirmed local proxy; source anatomy remains "
                "unchanged. Re-sync/reconfirm before planning."
            )
            self.anatomyReviewStatusLabel.setProperty("dentobotRole", "warning")
        elif exists:
            self.anatomyReviewStatusLabel.text = (
                "Review copy is inactive. Edit the local region, then explicitly "
                "confirm a segmentation artifact before using it for research simulation."
            )
            self.anatomyReviewStatusLabel.setProperty("dentobotRole", "warning")
        else:
            self.anatomyReviewStatusLabel.text = (
                "No manual anatomy-review copy exists. Source anatomy remains authoritative."
            )
            self.anatomyReviewStatusLabel.setProperty("dentobotRole", "status")

    def _invoke(self, name: str, *args) -> None:
        owner = self.ACTION_OWNER_SUBSTEP.get(name)
        owners = owner if isinstance(owner, tuple) else (owner,)
        placement_ok = (
            bool(self._placementSurfaceActive)
            and name in self.PLACEMENT_SURFACE_ACTIONS
        )
        if (
            owner is not None
            and self._activeSubstep not in owners
            and not placement_ok
        ):
            self.runtimeStatusLabel.text = (
                f"Blocked stale Step 6 action '{name}': owner is "
                f"{', '.join('6.' + str(value) for value in owners)}, "
                f"active substep is 6.{self._activeSubstep}."
            )
            self.runtimeStatusLabel.setProperty("dentobotState", "error")
            return
        callback = self._callbacks.get(name)
        if callback:
            callback(*args)

    def setManualJogLimits(self, mechanical_limits, reviewed_limits) -> None:
        mechanical = tuple(
            (float(pair.minimum), float(pair.maximum))
            for pair in (
                mechanical_limits.joint_1,
                mechanical_limits.joint_2,
                mechanical_limits.joint_3,
                mechanical_limits.joint_4,
                mechanical_limits.joint_5,
            )
        )
        reviewed = tuple(
            (float(pair.minimum), float(pair.maximum))
            for pair in (
                reviewed_limits.joint_1,
                reviewed_limits.joint_2,
                reviewed_limits.joint_3,
                reviewed_limits.joint_4,
                reviewed_limits.joint_5,
            )
        )
        allowed = []
        limits_valid = True
        for mechanical_pair, reviewed_pair in zip(mechanical, reviewed, strict=True):
            minimum = max(mechanical_pair[0], reviewed_pair[0])
            maximum = min(mechanical_pair[1], reviewed_pair[1])
            if not all(
                isfinite(bound)
                for bound in (*mechanical_pair, *reviewed_pair)
            ) or maximum < minimum:
                limits_valid = False
                minimum = maximum = 0.0
            allowed.append((minimum, maximum))
        limits = (tuple(allowed), reviewed)
        if self._manualJogLimits == limits:
            return
        self._manualJogLimits = limits
        self._manualJogLimitsValid = limits_valid
        for index, joint in enumerate(JOINT_NAMES):
            slider, value, _label = self.manualJogJointControls[joint]
            minimum, maximum = allowed[index]
            reviewed_minimum, reviewed_maximum = reviewed[index]
            slider.blockSignals(True)
            value.blockSignals(True)
            value.setRange(minimum, maximum)
            enabled = bool(
                maximum > minimum
                and self._manualJogAvailable
                and not self._manualJogBusy
            )
            slider.enabled = enabled
            value.enabled = enabled
            value.blockSignals(False)
            slider.blockSignals(False)
            label = ("J1", "J2", "J3", "J4", "J5")[index]
            unit = ("deg", "mm", "deg", "mm", "deg")[index]
            self.manualJogJointControls[joint][2].text = (
                f"{label} ({unit}); allowed: {minimum:.2f} to {maximum:.2f} {unit}; "
                f"reviewed: {reviewed_minimum:.2f} to {reviewed_maximum:.2f} {unit}"
            )
        if self._manualJogDraftInitialized:
            self._setManualJogDraftValues(self._manualJogDisplayValues, notify=True)

    def setManualJogAcceptedState(self, positions_si) -> None:
        try:
            values = {joint: float(positions_si[joint]) for joint in JOINT_NAMES}
        except (KeyError, TypeError, ValueError, OverflowError):
            values = {}
        if set(values) != set(JOINT_NAMES) or not all(
            isfinite(value) for value in values.values()
        ):
            self._manualJogAcceptedJointPositionsSi = None
            self.manualJogAcceptedStateLabel.text = "Accepted state: unavailable."
            self.taskHomeCandidateLabel.text = (
                "Candidate Task Home: current accepted J1–J5 state unavailable; "
                "J6 is excluded."
            )
            return
        self._manualJogAcceptedJointPositionsSi = values
        display = (
            degrees(values[JOINT_NAMES[0]]),
            values[JOINT_NAMES[1]] * 1000.0,
            degrees(values[JOINT_NAMES[2]]),
            values[JOINT_NAMES[3]] * 1000.0,
            degrees(values[JOINT_NAMES[4]]),
        )
        self.manualJogAcceptedStateLabel.text = (
            "Accepted state: " + self._formatManualJogDisplayValues(display)
        )
        self.taskHomeCandidateLabel.text = (
            "Candidate Task Home (current accepted J1–J5; J6 excluded): "
            + self._formatManualJogDisplayValues(display)
            + ". Review only until Accept Task Home passes the live checks."
        )
        if not self._manualJogDraftInitialized and self._manualJogLimits:
            self._setManualJogDraftValues(display, notify=False)

    def setManualJogAvailability(
        self, draft_available: bool, jog_available: bool
    ) -> None:
        limits_available = bool(self._manualJogLimits and self._manualJogLimitsValid)
        self._manualJogAvailable = bool(draft_available and limits_available)
        self._manualJogGuardAvailable = bool(
            self._manualJogAvailable and jog_available
        )
        for slider, value, _label in self.manualJogJointControls.values():
            slider.enabled = self._manualJogAvailable and not self._manualJogBusy
            value.enabled = self._manualJogAvailable and not self._manualJogBusy
        self.resetManualJogDraftButton.enabled = bool(
            self._manualJogAvailable
            and self._manualJogAcceptedJointPositionsSi
            and not self._manualJogBusy
        )
        self.guardedManualJogButton.enabled = bool(
            self._manualJogGuardAvailable
            and not self._manualJogBusy
            and not self.manualJogReconciliationRequired
        )
        self.checkManualDraftStateButton.enabled = bool(
            self._manualJogAvailable and not self._manualJogBusy
        )

    def setManualJogLimitsUnavailable(self, message: str) -> None:
        self._manualJogLimits = {}
        self._manualJogLimitsValid = False
        self.setManualJogAvailability(False, False)
        self._setManualJogStatus(
            "blocked",
            "Manual jog unavailable because mechanical URDF limits could not be read: "
            + str(message),
        )

    def setManualJogRequestPending(self) -> None:
        self._manualJogBusy = True
        self.setManualJogAvailability(
            self._manualJogAvailable, self._manualJogGuardAvailable
        )
        self._setManualJogStatus(
            "pending", "Guard status: pending — waiting for the simulation guard."
        )

    def setManualJogRequestComplete(self) -> None:
        self._manualJogBusy = False
        self.setManualJogAvailability(
            self._manualJogAvailable, self._manualJogGuardAvailable
        )

    def setManualJogStatus(self, state: str, message: str, evidence=None) -> None:
        if evidence is not None:
            self._manualJogEvidence = dict(evidence)
            if evidence.get("manualJogReconciliationRequired") is True:
                self.manualJogReconciliationRequired = True
            native_summary = self._formatManualJogNativeEvidence(evidence)
            if native_summary:
                message = f"{message} {native_summary}"
        self._setManualJogStatus(state, message)

    def setManualDraftStateCheckResult(
        self, result=None, *, requested=None, stale=False, error=""
    ) -> None:
        details = getattr(result, "details", None)
        details = details if isinstance(details, Mapping) else {}
        self._manualDraftStateCheckEvidence = dict(details)
        if error:
            self._manualDraftStateCheckEvidence["error"] = str(error)
        self._manualDraftStateCheckRequested = (
            dict(requested) if isinstance(requested, Mapping) else None
        )

        evaluation = details.get("manual_state_evaluation")
        evaluation = evaluation if isinstance(evaluation, Mapping) else {}
        endpoint = evaluation.get("endpoint_evaluation")
        endpoint = endpoint if isinstance(endpoint, Mapping) else {}
        static = endpoint.get("static_state_validity")
        static = static if isinstance(static, Mapping) else {}
        native = details.get("nativeGuardEvidence")
        native = native if isinstance(native, Mapping) else {}

        verdict = evaluation.get("status")
        if verdict not in {"passed", "failed", "unknown", "not_reached"}:
            verdict = "unknown"
        identity = evaluation.get("identity_status")
        target_status = evaluation.get("target_endpoint_status")

        def status_text(value):
            return value.strip() if isinstance(value, str) and value.strip() else "unknown"

        def metric_text(value, unit):
            try:
                number = float(value) if not isinstance(value, bool) else float("nan")
            except (TypeError, ValueError, OverflowError):
                number = float("nan")
            return f"{number:.6g} {unit}" if isfinite(number) else "unavailable"

        reasons = []
        seen_reasons = set()
        for label, value in (
            ("Static validity", static.get("message")),
            ("Evaluator", evaluation.get("reason")),
            ("Native", native.get("reason")),
        ):
            if isinstance(value, str) and value.strip():
                value = value.strip()
                if value not in seen_reasons:
                    rendered = f"{label}: {value}"
                    reasons.append(rendered)
                    seen_reasons.add(value)
        if error:
            reasons.append(f"Check error: {str(error)}")
        if not reasons:
            result_message = getattr(result, "message", "")
            if isinstance(result_message, str) and result_message.strip():
                reasons.append(f"Result: {result_message.strip()}")
        reason = "; ".join(reasons) or (
            "none reported" if verdict == "passed" else "unavailable"
        )

        if stale:
            marker = (
                "Draft-state check: stale — the draft changed after this check; "
                "the result is for the captured J1–J5 draft."
            )
        elif error or result is None:
            marker = "Draft-state check: unknown — no evaluator result was received."
        else:
            marker = "Draft-state check: complete."
        self.manualDraftStateCheckStatusLabel.text = "\n".join(
            (
                marker,
                f"Static verdict: {verdict}; identity status: {status_text(identity)}.",
                "Target diagnostics: endpoint status "
                + status_text(target_status)
                + "; position residual "
                + metric_text(endpoint.get("position_residual_mm"), "mm")
                + "; drilling-axis residual "
                + metric_text(endpoint.get("drilling_axis_residual_deg"), "deg")
                + ".",
                "Evaluator/native reason: " + reason,
            )
        )
        visual_state = (
            "ok" if verdict == "passed" else "error" if verdict == "failed" else "blocked"
        )
        self.manualDraftStateCheckStatusLabel.setProperty(
            "dentobotState", "blocked" if stale else visual_state
        )
        self.manualDraftStateCheckStatusLabel.style().unpolish(
            self.manualDraftStateCheckStatusLabel
        )
        self.manualDraftStateCheckStatusLabel.style().polish(
            self.manualDraftStateCheckStatusLabel
        )

    @staticmethod
    def _formatManualJogNativeEvidence(details) -> str:
        details = details if isinstance(details, Mapping) else {}
        native_evidence = details.get("nativeGuardEvidence")
        monitored = details.get("monitoredStateStatus")
        monitored_available = (
            isinstance(monitored, str)
            and monitored.strip()
            and monitored.strip().lower()
            not in {"unavailable", "unavailable/unknown"}
        )
        if not isinstance(native_evidence, Mapping) and not monitored_available:
            return ""
        native = native_evidence if isinstance(native_evidence, Mapping) else {}

        def body_name(key):
            value = native.get(key)
            return value.strip() if isinstance(value, str) and value.strip() else "unavailable"

        def distance_text(key):
            value = native.get(key)
            try:
                value = float(value) if not isinstance(value, bool) else float("nan")
            except (TypeError, ValueError, OverflowError):
                value = float("nan")
            return f"{value:.6g} m" if isfinite(value) else "unavailable"

        monitored = monitored or native.get("monitoredStateStatus")
        monitored_text = (
            monitored.strip()
            if isinstance(monitored, str) and monitored.strip()
            else "unavailable"
        )
        return (
            "Native guard evidence — first body: "
            + body_name("firstBody")
            + "; second body: "
            + body_name("secondBody")
            + "; required clearance: "
            + distance_text("minimumClearanceM")
            + "; measured self distance: "
            + distance_text("minimumSelfDistanceM")
            + "; measured world distance: "
            + distance_text("minimumWorldDistanceM")
            + "; monitored state: "
            + monitored_text
            + "."
        )

    def setManualRecordExportStatus(self, state: str, message: str) -> None:
        self.manualRecordExportStatusLabel.text = message
        self.manualRecordExportStatusLabel.setProperty("dentobotState", state)
        self.manualRecordExportStatusLabel.style().unpolish(
            self.manualRecordExportStatusLabel
        )
        self.manualRecordExportStatusLabel.style().polish(
            self.manualRecordExportStatusLabel
        )

    def setManualJogDraftDisplayResult(self, success: bool, message: str) -> None:
        if success:
            self.manualJogDraftStateLabel.text = (
                "Draft state: "
                + self._formatManualJogDisplayValues(self._manualJogDisplayValues)
                + " — display-only candidate shown."
            )
        else:
            self.manualJogDraftStateLabel.text = (
                "Draft state: "
                + self._formatManualJogDisplayValues(self._manualJogDisplayValues)
                + " — retained; display update unavailable: "
                + str(message)
            )

    def resetManualJogDraft(self) -> None:
        if not self._manualJogAcceptedJointPositionsSi:
            self._setManualJogStatus(
                "unknown", "Guard status: unknown — accepted current state is unavailable."
            )
            return
        state = self._manualJogAcceptedJointPositionsSi
        display = (
            degrees(state[JOINT_NAMES[0]]),
            state[JOINT_NAMES[1]] * 1000.0,
            degrees(state[JOINT_NAMES[2]]),
            state[JOINT_NAMES[3]] * 1000.0,
            degrees(state[JOINT_NAMES[4]]),
        )
        self._setManualJogDraftValues(display, notify=True)

    def manualJogJointPositionsSi(self) -> dict[str, float]:
        positions = joint_positions_si_from_display(
            *self._manualJogDisplayValues, 0.0
        )
        return {joint: float(positions[joint]) for joint in JOINT_NAMES}

    def _onManualJogSliderChanged(self, joint: str, position: int) -> None:
        if not self._manualJogLimits:
            return
        index = JOINT_NAMES.index(joint)
        minimum, maximum = self._manualJogLimits[0][index]
        value = (
            minimum + (maximum - minimum) * int(position) / 10000.0
            if maximum > minimum
            else minimum
        )
        slider, spinbox, _label = self.manualJogJointControls[joint]
        spinbox.blockSignals(True)
        spinbox.setValue(value)
        spinbox.blockSignals(False)
        self._updateManualJogDraftFromControls()

    def _onManualJogNumericChanged(self, joint: str, value: float) -> None:
        if not self._manualJogLimits:
            return
        index = JOINT_NAMES.index(joint)
        minimum, maximum = self._manualJogLimits[0][index]
        slider, spinbox, _label = self.manualJogJointControls[joint]
        slider.blockSignals(True)
        slider.value = round(
            min(1.0, max(0.0, (float(value) - minimum) / (maximum - minimum)))
            * 10000
        ) if maximum > minimum else 0
        slider.blockSignals(False)
        self._updateManualJogDraftFromControls()

    def _updateManualJogDraftFromControls(self) -> None:
        values = tuple(
            float(self.manualJogJointControls[joint][1].value)
            for joint in JOINT_NAMES
        )
        self._manualJogDisplayValues = values
        self._manualJogDraftInitialized = True
        self.manualJogDraftStateLabel.text = (
            "Draft state: " + self._formatManualJogDisplayValues(values)
        )
        self._setManualJogStatus(
            "unknown",
            "Guard status: unknown for this draft — no request has been sent.",
        )
        self._invoke("manual_draft_changed", self.manualJogJointPositionsSi())

    def _setManualJogDraftValues(self, values, *, notify: bool) -> None:
        if not self._manualJogLimits:
            return
        for index, joint in enumerate(JOINT_NAMES):
            slider, spinbox, _label = self.manualJogJointControls[joint]
            minimum, maximum = self._manualJogLimits[0][index]
            spinbox.blockSignals(True)
            slider.blockSignals(True)
            spinbox.setValue(float(values[index]))
            current = float(spinbox.value)
            slider.value = round(
                min(1.0, max(0.0, (current - minimum) / (maximum - minimum)))
                * 10000
            ) if maximum > minimum else 0
            spinbox.blockSignals(False)
            slider.blockSignals(False)
        self._manualJogDisplayValues = tuple(
            float(self.manualJogJointControls[joint][1].value)
            for joint in JOINT_NAMES
        )
        self._manualJogDraftInitialized = True
        self.manualJogDraftStateLabel.text = (
            "Draft state: "
            + self._formatManualJogDisplayValues(self._manualJogDisplayValues)
        )
        if notify:
            self._setManualJogStatus(
                "unknown",
                "Guard status: unknown for this draft — no request has been sent.",
            )
            self._invoke("manual_draft_changed", self.manualJogJointPositionsSi())

    @staticmethod
    def _formatManualJogDisplayValues(values) -> str:
        return ", ".join(
            f"J{index + 1} {float(value):.2f} {unit}"
            for index, (value, unit) in enumerate(
                zip(values, ("deg", "mm", "deg", "mm", "deg"), strict=True)
            )
        )

    def _setManualJogStatus(self, state: str, message: str) -> None:
        self.manualJogStatusLabel.text = message
        self.manualJogStatusLabel.setProperty("dentobotState", state)
        self.manualJogStatusLabel.style().unpolish(self.manualJogStatusLabel)
        self.manualJogStatusLabel.style().polish(self.manualJogStatusLabel)

    def _onTaskSpaceRoiEdited(self, _value=0.0) -> None:
        if self._loadingTaskSpaceRoi:
            return
        self.taskSpaceRoiStatusLabel.text = (
            "Edited ROI draft; samples not generated/validated. "
            + self._taskSpaceRoiStatusContext
        )
        self.taskSpaceRoiStatusLabel.setProperty("dentobotState", "blocked")
        self.taskSpaceRoiStatusLabel.style().unpolish(self.taskSpaceRoiStatusLabel)
        self.taskSpaceRoiStatusLabel.style().polish(self.taskSpaceRoiStatusLabel)
        callback = self._callbacks.get("roi_edited")
        if callback:
            callback()

    def _invoke_appearance(self, key: str) -> None:
        placement_ok = bool(self._placementSurfaceActive)
        if (
            self._activeSubstep != self.ACTION_OWNER_SUBSTEP["appearance_changed"]
            and not placement_ok
        ):
            return
        callback = self._callbacks.get("appearance_changed")
        if callback:
            visible, opacity = self.appearanceControls[key]
            callback(key, bool(visible.checked), float(opacity.value) / 100.0)

    def setActiveSubstep(self, substep_index: int) -> None:
        self._activeSubstep = max(0, min(int(substep_index), 6))

    def setPlacementSurfaceActive(self, active: bool) -> None:
        self._placementSurfaceActive = bool(active)

    def cbctPreset(self) -> str:
        return str(self.cbctPresetCombo.currentData or "current")

    def previewSpeedMultiplier(self) -> float:
        return min(8.0, max(0.25, float(self.previewSpeedCombo.currentData or 1.0)))

    def planningPolicy(self) -> dict[str, object]:
        return {
            "planner_id": self._plannerId,
            "planning_attempts": self._planningAttempts,
            "planning_time_sec": self._planningTimeSec,
        }

    def showPlanningPolicyDialog(self) -> None:
        if self._activeSubstep not in (5, 6):
            return
        dialog = qt.QDialog(self.approachGroup)
        dialog.windowTitle = "DENTOBOT Step 6 Planning Parameters"
        layout = qt.QFormLayout(dialog)
        planner = qt.QComboBox(dialog)
        for planner_id, algorithm in STEP6_JOINT_PLANNER_ALGORITHMS.items():
            planner.addItem(f"{planner_id} — {algorithm}", planner_id)
            if planner_id == self._plannerId:
                planner.currentIndex = planner.count - 1
        planner.toolTip = (
            "Select a configured joint-space planner for Home→PreEntry. "
            "This does not change Stage 2/3 or relax the independent phase guard."
        )
        attempts = qt.QSpinBox(dialog)
        attempts.minimum, attempts.maximum, attempts.value = 1, 10, self._planningAttempts
        attempts.toolTip = (
            "Number of independent joint-plan computations; MoveIt returns the shortest "
            "solution found. Start with this workflow's 1-attempt baseline; more attempts "
            "cost time and do not resolve an invalid goal or collision."
        )
        planning_time = qt.QDoubleSpinBox(dialog)
        planning_time.minimum, planning_time.maximum = 0.5, 60.0
        planning_time.decimals, planning_time.singleStep = 1, 0.5
        planning_time.value = self._planningTimeSec
        planning_time.toolTip = (
            "Maximum joint-planning allowance in seconds, not expected runtime. "
            "Start with this workflow's 5.0 s baseline; increase only for a reviewed "
            "time-limited search, changing one control at a time. No value guarantees a path."
        )
        approximate_ik = qt.QCheckBox("Enabled", dialog)
        approximate_ik.checked, approximate_ik.enabled = False, False
        approximate_ik.toolTip = (
            "Locked off: the current PreEntry solver accepts only tolerance-valid "
            "position-and-axis endpoints. An approximate path has not been reviewed "
            "against the canonical FK, residual, collision and guard gates."
        )
        cartesian = qt.QCheckBox("Enabled", dialog)
        cartesian.checked, cartesian.enabled = True, False
        cartesian.toolTip = (
            "Locked on: Stage 2/3 still use MoveIt Cartesian planning. Turning it off "
            "requires a separately verified exact-pose sequential-IK path with the "
            "same endpoint, collision, corridor and phase-guard checks."
        )
        layout.addRow("Joint planner:", planner)
        layout.addRow("Planning attempts:", attempts)
        layout.addRow("Planning time (s):", planning_time)
        layout.addRow("Approximate IK:", approximate_ik)
        layout.addRow("Cartesian Stage 2/3:", cartesian)
        for field in (planner, attempts, planning_time, approximate_ik, cartesian):
            layout.labelForField(field).toolTip = field.toolTip
        buttons = qt.QDialogButtonBox(
            qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel, dialog
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != qt.QDialog.Accepted:
            return
        self._plannerId = str(planner.currentData)
        self._planningAttempts = int(attempts.value)
        self._planningTimeSec = float(planning_time.value)
        settings = qt.QSettings()
        settings.setValue("DENTOBOT/Step6PlanningAttempts", self._planningAttempts)
        settings.setValue("DENTOBOT/Step6PlanningTimeSec", self._planningTimeSec)

    def showPlannerComparison(self, entry, *, current: bool, on_replay) -> None:
        """Inspect three saved outcomes; replay never applies a guarded plan."""

        dialog = qt.QDialog(self.approachGroup)
        dialog.windowTitle = "DENTOBOT Three-Planner Comparison"
        dialog.resize(980, 560)
        layout = qt.QVBoxLayout(dialog)
        notice = qt.QLabel(
            ("Current case identity. " if current else "STALE case identity — replay disabled. ")
            + "Saved paths are display-only evidence, not ROS/MoveIt or guard-valid plans. "
            "Use a fresh single-planner replan before guarded preview.", dialog
        )
        notice.wordWrap = True
        layout.addWidget(notice)
        attempts = entry["attempts"]
        table = qt.QTableWidget(3, 5, dialog)
        table.setHorizontalHeaderLabels(
            ["Planner", "Result", "Full task", "First blocker", "Waypoints"]
        )
        for row, attempt in enumerate(attempts):
            session = attempt.get("session") or {}
            outcome = session.get("full_task_outcome") or {}
            stages = session.get("stage_outcomes") or []
            first = next((stage for stage in stages if stage.get("status") == "Failed"), {})
            cells = (
                attempt["planner_id"], attempt["status"],
                str(outcome.get("status") or "NotRun"),
                str(first.get("reason") or attempt.get("message") or "")[:160],
                str(sum(len(values) for values in attempt.get("paths", {}).values())),
            )
            for column, value in enumerate(cells):
                table.setItem(row, column, qt.QTableWidgetItem(value))
        layout.addWidget(table)
        details = qt.QPlainTextEdit(dialog)
        details.readOnly = True
        layout.addWidget(details)
        actions = qt.QHBoxLayout()
        replay = qt.QPushButton("Replay Saved Path (display only)", dialog)
        choose = qt.QPushButton("Use Planner for Next Fresh Replan", dialog)
        close = qt.QPushButton("Close", dialog)
        for button in (replay, choose, close):
            actions.addWidget(button)
        layout.addLayout(actions)

        def selected(row):
            if row < 0:
                return
            attempt = attempts[row]
            details.plainText = json.dumps(attempt, indent=2, sort_keys=True)
            replay.enabled = bool(current and any(attempt["paths"].values()))
            choose.enabled = attempt["status"] != "NotRun"

        def replay_selected():
            row = int(table.currentRow())
            if row >= 0 and current:
                details.appendPlainText("\n\nReplay: " + str(on_replay(attempts[row])))

        def choose_selected():
            row = int(table.currentRow())
            if row >= 0:
                self._plannerId = attempts[row]["planner_id"]
                details.appendPlainText(
                    "\n\nPlanner selected for a NEW live plan; saved paths remain non-authorizing."
                )

        table.currentCellChanged.connect(
            lambda row, _column, _old_row, _old_column: selected(row)
        )
        replay.clicked.connect(lambda checked=False: replay_selected())
        choose.clicked.connect(lambda checked=False: choose_selected())
        close.clicked.connect(dialog.close)
        table.selectRow(0)
        selected(0)
        dialog.show()
        self._plannerComparisonDialog = dialog

    def previewIntervalMs(self) -> int:
        # Retained for expert/diagnostic preview callers; guarded previews use
        # planned timestamps and previewSpeedMultiplier().
        return max(20, round(250.0 / self.previewSpeedMultiplier()))

    def setPreviewProgress(self, current: int, total: int, phase: str = "") -> None:
        current = max(0, int(current))
        total = max(0, int(total))
        self.previewProgressBar.maximum = max(1, total)
        self.previewProgressBar.value = min(current, max(1, total))
        self.previewProgressBar.format = f"Preview: {current}/{total}"
        self.previewProgressLabel.text = (
            f"Guarded preview progress: {current}/{total}"
            + (f" — {str(phase).replace('_', ' ').title()}" if phase else ".")
        )

    def resetPreviewProgress(self, message: str = "No guarded preview is running.") -> None:
        self.previewProgressBar.maximum = 1
        self.previewProgressBar.value = 0
        self.previewProgressBar.format = "Preview: 0/0"
        self.previewProgressLabel.text = str(message)

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
    def _motionPlannerFeedback(session, candidate_index=None) -> str:
        """Explain the retained three-stage evidence without authorizing it."""

        records = tuple(session.candidate_records)
        if not records:
            return "No bounded planner attempt is retained."
        index = (
            int(session.selected_candidate_index)
            if candidate_index is None
            else max(0, min(len(records) - 1, int(candidate_index)))
        )
        record = records[index]
        chain_status = str(
            record.get("full_chain_candidate_status")
            or session.full_task_outcome.get("status")
            or "NotRun"
        )
        failure_stage = str(
            record.get("full_chain_failure_stage")
            or session.full_task_outcome.get("blocked_stage")
            or ""
        )
        cause = str(
            record.get("full_chain_failure_reason")
            or session.full_task_outcome.get("first_invalid_cause")
            or record.get("message")
            or "No failure cause was returned."
        )
        invalid_composed = int(
            record.get(
                "full_chain_first_invalid_index",
                session.full_task_outcome.get(
                    "first_invalid_composed_waypoint", -1
                ),
            )
        )
        invalid_stage = int(
            record.get(
                "full_chain_first_invalid_stage_index",
                session.full_task_outcome.get("first_invalid_stage_waypoint", -1),
            )
        )
        route = str(record.get("route_type") or "direct")
        seed = record.get("ik_seed_sample_index")
        seed_text = "Task Home" if seed is None else f"6.3 sample {int(seed)}"
        lines = [
            f"Planner attempt {index + 1}: {route}, IK seed {seed_text}; "
            f"full chain {chain_status}.",
            (
                "PreEntry IK search: failed (no collision-aware endpoint)."
                if failure_stage == "preentry_ik"
                else "Stage 1 Home→PreEntry: "
                + ("passed" if record.get("success") else "failed")
                + f" ({int(record.get('waypoint_count', 0))} waypoint(s))."
            ),
            (
                "Stage 2 PreEntry→Entry: "
                f"{float(record.get('stage2_fraction', 0.0)) * 100.0:.1f}% "
                f"({int(record.get('stage2_waypoint_count', 0))} waypoint(s))."
            ),
            (
                "Stage 3 Entry→Target: "
                f"{float(record.get('stage3_fraction', 0.0)) * 100.0:.1f}% "
                f"({int(record.get('stage3_waypoint_count', 0))} waypoint(s))."
            ),
        ]
        if chain_status == "Complete":
            lines.append(
                "Next: the fixed-frame three-stage preflight passed; inspect and "
                "preview it as simulation evidence only."
            )
            return "\n".join(lines)
        location = failure_stage or "unclassified planner stage"
        if invalid_composed >= 0:
            location += f", composed waypoint {invalid_composed}"
        if invalid_stage >= 0:
            location += f" (stage-local {invalid_stage})"
        lines.append(f"First block: {location}. Cause: {cause}")
        if failure_stage == "preentry_ik":
            lines.append(
                "Next: compare this task, trajectory, and robot-base identity with "
                "a passing run. This is endpoint reachability, not a Home→PreEntry "
                "connection failure."
            )
        elif failure_stage == "stage1_free_space":
            lines.append(
                "Next: inspect the reported self/world collision pair, then adjust "
                "Task Home/base placement or use a distinct Home-connected 6.3 route. "
                "A valid PreEntry endpoint alone is not a connecting path."
            )
        elif failure_stage == "stage2_fixed_axis_terminal":
            lines.append(
                "Next: revise the committed Stage-1 tool frame, base, or trajectory "
                "for any non-tool/self/world/corridor failure. Configured burr-to-task "
                "contact is already handled by the independent phase guard."
            )
        elif failure_stage == "stage3_drilling":
            lines.append(
                "Next: revise the Stage-1 fixed frame, base, or approved trajectory; "
                "a partial Entry→Target result is never promoted as drilling preview."
            )
        elif failure_stage == "phase_guard_setup":
            lines.append(
                "Next: reconnect/resynchronize the simulation guard and collision "
                "scene before replanning; do not interpret this as a geometric failure."
            )
        else:
            lines.append(
                "Next: inspect this bounded attempt's raw evidence; no collision "
                "relaxation or hardware action is authorized by this diagnostic."
            )
        return "\n".join(lines)

    def showMotionDiagnostics(
        self,
        session,
        on_candidate_selected,
        on_review,
        on_candidate_path=None,
        on_candidate_preview=None,
        on_candidate_apply=None,
        on_candidate_unlock=None,
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
            )
            + " Equal waypoint counts are only MoveIt sampling counts; they do not "
            "mean equal joint routes. Compare the IK seed, fixed frame, arm travel, "
            "and display-only path.",
            dialog,
        )
        summary.wordWrap = True
        layout.addWidget(summary)
        identity_label = qt.QLabel(
            "Evidence identity — "
            f"task {session.task_fingerprint[:12]}; "
            f"trajectory {session.trajectory_fingerprint[:12]}; "
            f"robot base {session.base_fingerprint[:12]}.",
            dialog,
        )
        identity_label.wordWrap = True
        layout.addWidget(identity_label)
        if str(session.full_task_outcome.get("diagnostic_kind") or "") == "preentry_ik":
            outcome = session.full_task_outcome
            summary.text = (
                "PreEntry IK endpoint diagnostic only. P1/Stage 1, Stage 2, Stage 3, "
                "route planning, guard, preview, and motion application were not run. "
                "It is display-only and can never be route authority; a saved/reopened "
                "report requires fresh live checks before any later planning. "
                f"Endpoint status: {outcome.get('diagnostic_status', 'Unknown')}."
            )
            summary.setProperty("dentobotRole", "warning")
            layout.addWidget(qt.QLabel(
                "Endpoint conditioning: task-Jacobian singular-value ratio is "
                "tolerance-scaled (0≈singular; 1 better conditioned). Unknown values "
                "are shown as — and are not a feasibility verdict. For collision "
                "checks, only status 'clear' means the endpoint scene check ran and "
                "accepted; every other status is unverified.",
                dialog,
            ))
            identity_notes = qt.QLabel(
                "Historical workspace seeds are labelled hints only. The record "
                "shows its Task Home/base/profile/scene/policy match fields below; "
                "its saved Home connectivity is historical and current connectivity "
                "was not evaluated. Existing workspace evidence has no independent "
                "case ID; any case match is based on its association with the active "
                "case parameter node.",
                dialog,
            )
            identity_notes.wordWrap = True
            layout.addWidget(identity_notes)
            records = tuple(session.candidate_records)
            headers = (
                "Seed",
                "Provenance",
                "Solver",
                "Termination / iterations / condition",
                "Position / axis residual",
                "Collision check",
                "Static / FK",
                "Best J1–J5",
                "Mechanical / task worst margin by unit",
            )
            table = qt.QTableWidget(dialog)
            table.setColumnCount(len(headers))
            table.setRowCount(len(records))
            table.setHorizontalHeaderLabels(list(headers))

            def format_margin(record, field):
                margins = record.get(field)
                if not isinstance(margins, dict):
                    return "—"
                key = (
                    "mechanical_minimum_margin"
                    if field == "mechanical_joint_limit_margins"
                    else "reviewed_task_minimum_margin"
                )
                by_unit = {"deg": [], "mm": []}
                for joint in margins.values():
                    if isinstance(joint, dict) and joint.get(key) is not None:
                        unit = str(joint.get("unit") or "")
                        if unit in by_unit:
                            by_unit[unit].append(float(joint[key]))
                return ", ".join(
                    f"{min(values):.4g} {unit}"
                    for unit, values in by_unit.items()
                    if values
                ) or "—"

            def format_best_joints(record):
                values = record.get("best_joint_positions_display")
                if not isinstance(values, dict):
                    return "—"
                return ", ".join(
                    f"{joint}: {float(value['value']):.4g} {value['unit']}"
                    for joint, value in values.items()
                    if isinstance(value, dict)
                    and value.get("value") is not None
                    and value.get("unit")
                ) or "—"

            for row, record in enumerate(records):
                ratio = record.get("task_jacobian_condition_ratio")
                ratio_text = "—" if ratio is None else f"{float(ratio):.4g}"
                iterations = record.get("iteration_count")
                diagnostics = (
                    f"{record.get('termination_reason') or 'unknown'} / "
                    f"{iterations if iterations is not None else '—'} / {ratio_text}"
                )
                position = record.get("position_residual_mm")
                axis = record.get("drilling_axis_residual_deg")
                residuals = (
                    f"{float(position):.4g} mm / {float(axis):.4g}°"
                    if position is not None and axis is not None
                    else f"{position if position is not None else '—'} / "
                    f"{axis if axis is not None else '—'}"
                )
                values = (
                    str(record.get("candidate_index", row) + 1),
                    str(record.get("seed_provenance") or "unknown"),
                    "solver success" if record.get("solver_success") else "failed",
                    diagnostics,
                    residuals,
                    str(record.get("collision_check_status") or "unknown"),
                    (
                        f"{record.get('static_state_validity_status', 'unknown')} / "
                        f"{record.get('authoritative_fk_status', 'unknown')}"
                    ),
                    format_best_joints(record),
                    (
                        f"{format_margin(record, 'mechanical_joint_limit_margins')} / "
                        f"{format_margin(record, 'reviewed_task_joint_limit_margins')}"
                    ),
                )
                for column, value in enumerate(values):
                    table.setItem(row, column, qt.QTableWidgetItem(value))
            table.resizeColumnsToContents()
            layout.addWidget(table)
            details = qt.QPlainTextEdit(dialog)
            details.readOnly = True
            details.plainText = json.dumps(
                {
                    "full_task_outcome": outcome,
                    "seed": records[0] if records else {},
                },
                indent=2,
                sort_keys=True,
            )
            layout.addWidget(details)

            def show_seed(row: int, *_args) -> None:
                if 0 <= int(row) < len(records):
                    details.plainText = json.dumps(
                        {
                            "full_task_outcome": outcome,
                            "seed": records[int(row)],
                        },
                        indent=2,
                        sort_keys=True,
                    )

            table.currentCellChanged.connect(show_seed)
            close_button = qt.QPushButton("Close", dialog)
            close_button.clicked.connect(lambda checked=False: dialog.accept())
            close_row = qt.QHBoxLayout()
            close_row.addStretch(1)
            close_row.addWidget(close_button)
            layout.addLayout(close_row)
            self._diagnosticDialog = dialog
            dialog.show()
            return
        requested_planner_id = str(
            session.full_task_outcome.get("requested_joint_planner_id") or "unreported"
        )
        planner_id = str(session.full_task_outcome.get("joint_planner_id") or "unreported")
        planner_algorithm = str(
            session.full_task_outcome.get("joint_planner_algorithm") or "unreported"
        )
        planner_policy_label = qt.QLabel(
            "Planning policy — "
            f"requested joint planner {requested_planner_id} ({planner_algorithm}); "
            f"MoveGroup configured ID {planner_id} (execution algorithm unverified); "
            f"attempts {int(session.full_task_outcome.get('joint_planning_attempts', 1))}; "
            f"time {float(session.full_task_outcome.get('joint_planning_time_sec', 0.0)):.1f} s; "
            "approximate IK "
            + (
                "enabled"
                if session.full_task_outcome.get("approximate_ik_enabled")
                else "disabled"
            )
            + "; MoveIt Cartesian Stage 2/3 "
            + (
                "enabled"
                if session.full_task_outcome.get("cartesian_planning_enabled")
                else "disabled"
            )
            + ".",
            dialog,
        )
        planner_policy_label.wordWrap = True
        layout.addWidget(planner_policy_label)
        full_status = str(session.full_task_outcome.get("status") or "Unknown")
        template_excluded = bool(
            session.full_task_outcome.get("template_collision_exclusion_active")
        )
        orientation_id = str(
            session.full_task_outcome.get("tool_orientation_fingerprint") or ""
        )
        full_task_label = qt.QLabel(
            f"Full task: {full_status}. Spindle locked at 0 rad; external RPM is not planned."
            + (
                f" Stage-1 fixed tool frame: {orientation_id[:12]}."
                if orientation_id
                else " Stage-1 tool frame is not yet committed."
            ),
            dialog,
        )
        full_task_label.wordWrap = True
        layout.addWidget(full_task_label)
        plan_selection = session.full_task_outcome.get("plan_selection")
        if not isinstance(plan_selection, dict):
            plan_selection = {}
        plan_selection_state = str(plan_selection.get("state") or "auto")
        try:
            plan_selection_index = int(
                plan_selection.get("candidate_index", session.selected_candidate_index)
            )
        except (TypeError, ValueError):
            plan_selection_index = int(session.selected_candidate_index)
        selection_label = qt.QLabel(
            "Saved route intent: "
            + (
                f"{plan_selection_state} (route {plan_selection_index + 1}). "
                "Case save stores this identity only; reopening requires a current re-plan."
                if plan_selection_state in {"selected", "locked"}
                else "automatic planner choice. Select an eligible complete route to save an alternate."
            ),
            dialog,
        )
        selection_label.wordWrap = True
        selection_label.setProperty(
            "dentobotRole", "warning" if plan_selection_state == "locked" else "status"
        )
        layout.addWidget(selection_label)
        if template_excluded:
            collision_scope_label = qt.QLabel(
                "FUNCTIONAL SIMULATION ONLY — the unresolved Step 5C final "
                "template was visible but excluded from authoritative MoveIt "
                "collision evaluation. This is not physical collision-valid evidence.",
                dialog,
            )
            collision_scope_label.wordWrap = True
            collision_scope_label.setProperty("dentobotRole", "warning")
            layout.addWidget(collision_scope_label)
        anatomy_override = session.full_task_outcome.get(
            "session_anatomy_review_override"
        )
        if isinstance(anatomy_override, dict) and anatomy_override.get("active"):
            anatomy_scope_label = qt.QLabel(
                "RESEARCH SIMULATION ANATOMY OVERRIDE — a manually reviewed, "
                "session-only local proxy was used. Source segmentation remains "
                "unchanged; this is not physical collision-valid evidence.",
                dialog,
            )
            anatomy_scope_label.wordWrap = True
            anatomy_scope_label.setProperty("dentobotRole", "warning")
            layout.addWidget(anatomy_scope_label)
        feedback_label = qt.QLabel(
            self._motionPlannerFeedback(session),
            dialog,
        )
        feedback_label.wordWrap = True
        feedback_label.setProperty("dentobotRole", "status")
        layout.addWidget(feedback_label)
        operator_error = str(session.full_task_outcome.get("operator_error_message") or "")
        if operator_error:
            error_text = qt.QPlainTextEdit(dialog)
            error_text.readOnly = True
            error_text.plainText = operator_error
            error_text.toolTip = "Exact error-dialog text from this planner attempt; copyable after the dialog closes."
            layout.addWidget(qt.QLabel("Planner error-dialog text (retained):", dialog))
            layout.addWidget(error_text)
        stage_table = qt.QTableWidget(dialog)
        stages = tuple(session.stage_outcomes)
        stage_table.setColumnCount(5)
        stage_table.setRowCount(len(stages))
        stage_table.setHorizontalHeaderLabels(
            ["Task stage", "Status", "Progress", "First invalid", "First cause"]
        )
        stage_labels = {
            "stage1_free_space": "Stage 1 — Home→PreEntry",
            "stage2_strict_axis": "Stage 2 — PreEntry→Entry",
            "stage2_fixed_axis_terminal": "Stage 2 — PreEntry→Entry",
            "stage3_drilling": "Stage 3 — Entry→Target",
        }
        for row, stage in enumerate(stages):
            values = (
                stage_labels.get(str(stage.get("stage") or ""), str(stage.get("stage") or "")),
                str(stage.get("status") or "Unknown"),
                f"{float(stage.get('completion_fraction', 0.0)) * 100.0:.1f}%",
                (
                    "—"
                    if int(stage.get("first_invalid_waypoint", -1)) < 0
                    else str(int(stage["first_invalid_waypoint"]))
                ),
                str(stage.get("failure_classification") or stage.get("reason") or "—"),
            )
            for column, value in enumerate(values):
                stage_table.setItem(row, column, qt.QTableWidgetItem(value))
        stage_table.resizeColumnsToContents()
        layout.addWidget(stage_table)
        table = qt.QTableWidget(dialog)
        records = tuple(session.candidate_records)
        headers = (
            "Planner leg",
            "Route",
            "Fixed frame",
            "Chain",
            "IK seed",
            "Clearance",
            "Result",
            "Fraction",
            "Distance",
            "Waypoints",
            "Arm travel",
            "Classification",
            "Min joint margin",
        )
        table.setColumnCount(len(headers))
        table.setRowCount(len(records))
        table.setHorizontalHeaderLabels(list(headers))
        for row, record in enumerate(records):
            values = (
                str(record.get("planner_leg") or record.get("stage", "")),
                str(record.get("route_type") or "legacy-roll"),
                (
                    str(record.get("tool_orientation_fingerprint"))[:12]
                    if record.get("tool_orientation_fingerprint")
                    else "legacy"
                ),
                str(record.get("full_chain_candidate_status") or "NotRun"),
                (
                    "Task Home"
                    if record.get("ik_seed_sample_index") is None
                    else f"6.3 sample {int(record['ik_seed_sample_index'])}"
                ),
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
                f"{float(record.get('path_length_joint_si', 0.0)):.4f}",
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
        path_button = qt.QPushButton("Show Selected Paths", dialog)
        preview_button = qt.QPushButton("Preview Selected Leg", dialog)
        apply_button = qt.QPushButton("Use Selected Route (replan)", dialog)
        lock_button = qt.QPushButton("Lock + Replan Selected Route", dialog)
        unlock_button = qt.QPushButton("Unlock Saved Route", dialog)
        review_button = qt.QPushButton("Mark Current Evidence Reviewed", dialog)
        close_button = qt.QPushButton("Close", dialog)
        dialog_buttons.addWidget(path_button)
        dialog_buttons.addWidget(preview_button)
        dialog_buttons.addWidget(apply_button)
        dialog_buttons.addWidget(lock_button)
        dialog_buttons.addWidget(unlock_button)
        dialog_buttons.addWidget(review_button)
        dialog_buttons.addWidget(close_button)
        layout.addLayout(dialog_buttons)
        close_button.clicked.connect(lambda checked=False: dialog.accept())

        def review_evidence() -> None:
            if on_review:
                result = on_review()
                details.appendPlainText("\n\nReview result: " + result.message)
                if result.success:
                    review_button.enabled = False

        review_button.clicked.connect(review_evidence)
        review_button.enabled = session.operator_review_state != "Reviewed"

        def show_selected_path() -> None:
            if on_candidate_path:
                result = on_candidate_path(int(table.currentRow))
                details.appendPlainText("\n\nPath display: " + result.message)

        def preview_selected_leg() -> None:
            if on_candidate_preview:
                result = on_candidate_preview(
                    int(table.currentRow), self.previewIntervalMs()
                )
                details.appendPlainText("\n\nDiagnostic preview: " + result.message)

        path_button.clicked.connect(show_selected_path)
        preview_button.clicked.connect(preview_selected_leg)
        path_button.enabled = bool(on_candidate_path)
        preview_button.enabled = bool(on_candidate_preview)

        def update_plan_buttons(index: int) -> None:
            record = records[index]
            complete = str(record.get("full_chain_candidate_status") or "") == "Complete"
            locked = plan_selection_state == "locked"
            apply_button.enabled = bool(on_candidate_apply and complete and not locked)
            lock_button.enabled = bool(on_candidate_apply and complete and not locked)
            unlock_button.enabled = bool(on_candidate_unlock and locked)

        def select_candidate(index: int) -> None:
            index = max(0, min(len(records) - 1, int(index)))
            table.selectRow(index)
            scrubber.blockSignals(True)
            scrubber.value = index
            scrubber.blockSignals(False)
            record = records[index]
            feedback_label.text = self._motionPlannerFeedback(session, index)
            details.plainText = json.dumps(record, indent=2, sort_keys=True)
            update_plan_buttons(index)
            if on_candidate_selected:
                result = on_candidate_selected(index)
                details.appendPlainText("\n\nDisplay result: " + result.message)

        def apply_selected(lock: bool) -> None:
            nonlocal plan_selection_state
            if on_candidate_apply:
                result = on_candidate_apply(int(table.currentRow()), lock)
                details.appendPlainText("\n\nRoute plan result: " + result.message)
                if result.success:
                    plan_selection_state = "locked" if lock else "selected"
                    selection_label.text = (
                        "Saved route intent: "
                        + ("locked" if lock else "selected")
                        + f" (route {int(table.currentRow()) + 1}). Reopen the dialog after the current re-plan to review updated evidence."
                    )
                    if lock:
                        apply_button.enabled = False
                        lock_button.enabled = False
                        unlock_button.enabled = bool(on_candidate_unlock)

        def unlock_selected() -> None:
            nonlocal plan_selection_state
            if on_candidate_unlock:
                result = on_candidate_unlock()
                details.appendPlainText("\n\nRoute lock result: " + result.message)
                if result.success:
                    plan_selection_state = "selected"
                    update_plan_buttons(int(table.currentRow))

        apply_button.clicked.connect(lambda checked=False: apply_selected(False))
        lock_button.clicked.connect(lambda checked=False: apply_selected(True))
        unlock_button.clicked.connect(lambda checked=False: unlock_selected())

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
