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
        "begin_manual_base_review": 1,
        "cancel_manual_base_review": 1,
        "reconcile_manual_base": 1,
        "appearance_changed": 1,
        "reset_base": 1,
        "delete_setup": 1,
        "expert_diagnostics": 1,
        "review_task_home": (2, 3),
        "cancel_task_home_review": (2, 3),
        "accept_task_home_review": (2, 3),
        "reconcile_task_home": (2, 3),
        "apply_home": 2,
        "roi_from_incisors": 3,
        "revalidate_workspace": 3,
        "review_limits": 3,
        "confirm_task": 3,
        "reset_manual_draft": (2, 3),
        "manual_draft_changed": (2, 3),
        "check_manual_draft_state": 3,
        "reconcile_manual_jog": 3,
        "guarded_manual_jog": 3,
        "export_manual_record": 3,
        "import_manual_record": 3,
        "show_manual_record": 3,
        "clear_manual_record": 3,
        "plan_approach": 3,
        "check_preentry_ik": 3,
        "check_planning_p1": 3,
        "check_planning_p2": 3,
        "check_planning_p3": 3,
        "diagnose_base": 3,
        "compare_planners": 3,
        "cancel_planner_comparison": 3,
        "show_planner_comparison": 3,
        "template_collision_override": 3,
        "begin_anatomy_review": 3,
        "edit_anatomy_review": 3,
        "activate_anatomy_review": 3,
        "discard_anatomy_review": 3,
        "preview_approach": 4,
        "show_motion_diagnostics": 3,
        "plan_drilling": 3,
        "preview_drilling": 4,
        "stop_preview": 4,
        "return_home": 4,
        "create_goal": -1,
        "solve_ik": 3,
        "set_tcp_drag_enabled": 3,
        "nudge_tcp_goal": 3,
        "plan_goal": -1,
    }
    TCP_KEY_BINDINGS = (
        ("Left", 0, None, -1.0),
        ("Right", 0, None, 1.0),
        ("Down", 1, None, -1.0),
        ("Up", 1, None, 1.0),
        ("PgDown", 2, None, -1.0),
        ("PgUp", 2, None, 1.0),
        ("Ctrl+Down", None, 1, -1.0),
        ("Ctrl+Up", None, 1, 1.0),
        ("Shift+Left", None, 2, -1.0),
        ("Shift+Right", None, 2, 1.0),
    )
    MANUAL_JOG_KEY_BINDINGS = (
        ("Q", 0, 1.0),
        ("A", 0, -1.0),
        ("W", 1, 1.0),
        ("S", 1, -1.0),
        ("E", 2, 1.0),
        ("D", 2, -1.0),
        ("R", 3, 1.0),
        ("F", 3, -1.0),
        ("T", 4, 1.0),
        ("G", 4, -1.0),
    )
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
        self._displayDialog = None
        self._setupToolsDialog = None
        self._taskHomeDetailsDialog = None
        self._manualRecordsDialog = None
        self._planningToolsDialog = None
        self._baseDiagnosisDialog = None
        self._anatomyReviewDialog = None
        self._step63Navigate = None
        self._step63ReturnTab = 0
        self._manualJogLimits = {}
        self._manualJogSliderRanges = ()
        self._manualJogMechanicalLimits = None
        self._manualJogLimitsValid = False
        self._manualJogCommandLimitsValid = False
        self._manualJogAcceptedJointPositionsSi = None
        self._manualJogLocalJointPositionsSi = None
        self._manualJogJointPresentation = {}
        self._taskHomeSetupMode = "unknown"
        self._taskHomeConfigurationReady = False
        self._taskHomeConfiguredJointPositionsSi = None
        self._taskHomeRuntimeValidated = False
        self._manualJogControlsInHomeGroup = False
        self._manualJogDraftInitialized = False
        self._manualJogBusy = False
        self._manualJogAvailable = False
        self._manualJogGuardAvailable = False
        self._manualJogGuardContextAvailable = False
        self._manualJogDraftWithinCommandLimits = False
        self._manualJogLimitViolations = ()
        self.manualJogReconciliationRequired = False
        self._manualJogEvidence = None
        self._manualDraftStateCheckEvidence = None
        self._manualDraftStateCheckRequested = None
        self._manualSimulationRecords = ()
        self._tcpDragEnabled = False
        self._tcpIkStageFailureText = ""
        self._tcpIkAvailable = False
        self._tcpKeyboardShortcuts = []
        self._manualJogKeyboardShortcuts = []
        self._manualJogKeyboardFocusSlot = None
        settings = qt.QSettings()
        self._plannerId = "RRTConnectkConfigDefault"
        self._planningAttempts = max(
            1, min(10, int(settings.value("DENTOBOT/Step6PlanningAttempts", 1)))
        )
        self._planningTimeSec = max(
            0.5, min(60.0, float(settings.value("DENTOBOT/Step6PlanningTimeSec", 5.0)))
        )
        self.visualizationGroup = qt.QGroupBox("6.1 — Robot Setup", parent)
        self.visualizationGroup.objectName = "DENTOBOTPlacementContextGroupBox"
        visualization_layout = qt.QVBoxLayout(self.visualizationGroup)
        visualization_description = qt.QLabel(
            "Load or reuse the robot, propose the virtual forehead and Base, then "
            "adjust one detached candidate before explicit acceptance. Display "
            "controls do not change geometry or runtime authority.",
            self.visualizationGroup,
        )
        visualization_description.wordWrap = True
        visualization_layout.addWidget(visualization_description)

        self.step61TabWidget = qt.QTabWidget(self.visualizationGroup)
        self.step61TabWidget.objectName = "DENTOBOTStep61TabWidget"
        self.step61PlacementPage = qt.QWidget(self.step61TabWidget)
        self.step61PlacementPage.objectName = "DENTOBOTStep61PlacementPage"
        self.step61PlacementLayout = qt.QVBoxLayout(self.step61PlacementPage)
        self.step61PlacementLayout.setContentsMargins(6, 6, 6, 6)
        self.step61PlacementLayout.setSpacing(6)
        self.step61ScenePage = qt.QWidget(self.step61TabWidget)
        self.step61ScenePage.objectName = "DENTOBOTStep61ScenePage"
        self.step61SceneLayout = qt.QVBoxLayout(self.step61ScenePage)
        self.step61SceneLayout.setContentsMargins(6, 6, 6, 6)
        self.step61SceneLayout.setSpacing(6)
        self.step61TabWidget.addTab(self.step61PlacementPage, "Placement")
        self.step61TabWidget.addTab(self.step61ScenePage, "Scene")

        placement_actions = qt.QGridLayout()
        placement_actions.setHorizontalSpacing(6)
        placement_actions.setVerticalSpacing(4)
        self.loadFallbackButton = qt.QPushButton(
            "Load / Reuse Robot", self.step61PlacementPage
        )
        self.loadFallbackButton.objectName = "DENTOBOTShellLoadFallbackRobotButton"
        self.createProxyButton = qt.QPushButton(
            "Propose Virtual Forehead + Auto Base", self.step61PlacementPage
        )
        self.createProxyButton.enabled = True
        self.createProxyButton.toolTip = (
            "Build an independent virtual forehead outside the CBCT FOV from "
            "the Case Foundation dental frame, then seat an unreviewed "
            "simulation Base. Review and accept it separately."
        )
        self.placementReviewButton = qt.QPushButton(
            "Frame Robot + CBCT", self.step61PlacementPage
        )
        self.displayButton = qt.QPushButton("Display…", self.step61PlacementPage)
        self.displayButton.objectName = "DENTOBOTStep61DisplayButton"
        self.setupToolsButton = qt.QPushButton("Setup Tools…", self.step61PlacementPage)
        self.setupToolsButton.objectName = "DENTOBOTStep61SetupToolsButton"
        placement_actions.addWidget(self.loadFallbackButton, 0, 0)
        placement_actions.addWidget(self.createProxyButton, 0, 1)
        placement_actions.addWidget(self.placementReviewButton, 1, 0)
        placement_actions.addWidget(self.displayButton, 1, 1)
        placement_actions.addWidget(self.setupToolsButton, 2, 0, 1, 2)
        placement_actions.setColumnStretch(0, 1)
        placement_actions.setColumnStretch(1, 1)
        self.step61PlacementLayout.addLayout(placement_actions)

        self.visualizationStatusLabel = qt.QLabel(
            "No CBCT renderer or provisional proxy is created automatically.",
            self.step61PlacementPage,
        )
        self.visualizationStatusLabel.wordWrap = True
        self.visualizationStatusLabel.setProperty("dentobotRole", "status")
        self.step61PlacementLayout.addWidget(self.visualizationStatusLabel)

        self.baseInteractionStatusLabel = qt.QLabel(
            "Base interaction unavailable until a current unlocked candidate exists.",
            self.step61PlacementPage,
        )
        self.baseInteractionStatusLabel.objectName = (
            "DENTOBOTBaseInteractionStatusLabel"
        )
        self.baseInteractionStatusLabel.wordWrap = True
        self.baseInteractionStatusLabel.setProperty("dentobotRole", "status")
        self.step61PlacementLayout.addWidget(self.baseInteractionStatusLabel)

        self.manualBaseReviewGroup = qt.QGroupBox(
            "Base decision", self.step61PlacementPage
        )
        base_review_layout = qt.QVBoxLayout(self.manualBaseReviewGroup)
        self.manualBaseReviewStatusLabel = qt.QLabel(
            "No detached Base candidate is staged.",
            self.manualBaseReviewGroup,
        )
        self.manualBaseReviewStatusLabel.objectName = (
            "DENTOBOTManualBaseReviewStatusLabel"
        )
        self.manualBaseReviewStatusLabel.wordWrap = True
        self.manualBaseReviewStatusLabel.toolTip = (
            "The cyan translucent ghost is the detached candidate. The solid robot "
            "is the accepted Base unless an uncertain native outcome is reported."
        )
        base_review_layout.addWidget(self.manualBaseReviewStatusLabel)
        self.manualBaseReviewButtonsLayout = qt.QHBoxLayout()
        self.beginManualBaseReviewButton = qt.QPushButton(
            "Review Base", self.manualBaseReviewGroup
        )
        self.beginManualBaseReviewButton.toolTip = (
            "Stage the current accepted Base as a detached review candidate. "
            "This does not change the accepted robot or ROS scene."
        )
        self.cancelManualBaseReviewButton = qt.QPushButton(
            "Back to Edit / Cancel Review", self.manualBaseReviewGroup
        )
        self.cancelManualBaseReviewButton.enabled = False
        self.cancelManualBaseReviewButton.toolTip = (
            "Discard a known staged Base candidate. Reconcile an uncertain "
            "acceptance before another state-changing action."
        )
        self.reconcileManualBaseStateButton = qt.QPushButton(
            "Reconcile Base State", self.manualBaseReviewGroup
        )
        self.reconcileManualBaseStateButton.toolTip = (
            "Reconcile the accepted Base with the live ROS scene without accepting "
            "the detached candidate."
        )
        self.reconcileManualBaseStateButton.enabled = False
        self.searchBasePlacementButton = qt.QPushButton(
            "Find Reachable Base", self.manualBaseReviewGroup
        )
        self.searchBasePlacementButton.toolTip = (
            "Level 1: IK preflight over the virtual forehead plane (+-30 mm in-plane, "
            "depth fallback +-10 mm, orientation locked) plus a mouth-barrier check; "
            "stages the nearest clear Base for Review/Accept. If it fails, offers level 2: "
            "a deep search moving the current Base (+-30 mm, +-20 mm depth, +-40 deg yaw). "
            "MoveIt checks anatomy, template and planning after acceptance."
        )
        self.manualBaseReviewButtonsLayout.addWidget(self.beginManualBaseReviewButton)
        self.manualBaseReviewButtonsLayout.addWidget(self.searchBasePlacementButton)
        self.manualBaseReviewButtonsLayout.addWidget(self.cancelManualBaseReviewButton)
        self.manualBaseReviewButtonsLayout.addWidget(self.reconcileManualBaseStateButton)
        base_review_layout.addLayout(self.manualBaseReviewButtonsLayout)
        self.step61PlacementLayout.addWidget(self.manualBaseReviewGroup)
        self.step61PlacementLayout.addStretch(1)

        visualization_layout.addWidget(self.step61TabWidget)

        self._displayDialog = qt.QDialog(parent)
        self._displayDialog.objectName = "DENTOBOTStep61DisplayDialog"
        self._displayDialog.windowTitle = "DENTOBOT Step 6.1 Display"
        self._displayDialog.setModal(False)
        display_layout = qt.QVBoxLayout(self._displayDialog)
        display_hint = qt.QLabel(
            "Modeless display controls; viewport interaction remains available.",
            self._displayDialog,
        )
        display_hint.wordWrap = True
        display_layout.addWidget(display_hint)
        render_actions = qt.QHBoxLayout()
        self.enableCbctRenderingButton = qt.QPushButton(
            "Enable CBCT 3D Context", self._displayDialog
        )
        self.cbctPresetCombo = qt.QComboBox(self._displayDialog)
        self.cbctPresetCombo.addItem("Current window/level", "current")
        self.cbctPresetCombo.addItem("CT-Bone intensity appearance", "CT-Bone")
        self.cbctPresetCombo.addItem("uCT-Skull intensity appearance", "uCT-Skull")
        render_actions.addWidget(self.enableCbctRenderingButton)
        render_actions.addWidget(self.cbctPresetCombo)
        display_layout.addLayout(render_actions)
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
            visible = qt.QCheckBox(self._displayDialog)
            visible.checked = key not in {
                "cbct",
                "goal_robot",
                "forehead_proxy",
                "collision_audit",
            }
            opacity = qt.QSlider(qt.Qt.Horizontal, self._displayDialog)
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
        display_layout.addLayout(appearance_grid)
        # Planning-aid toggles mirrored from 6.3 Plan so they are reachable in
        # 6.1/6.2 too (operator 2026-10-04); the 6.3 checkboxes stay the owners.
        self.displayShowMouthBarrierCheckBox = qt.QCheckBox(
            "Show mouth barrier (virtual lips/cheeks)", self._displayDialog
        )
        self.displayShowMouthBarrierCheckBox.checked = True
        self.displayShowTaskSpaceBoxCheckBox = qt.QCheckBox(
            "Show task-space box (incisor-centred)", self._displayDialog
        )
        display_layout.addWidget(self.displayShowMouthBarrierCheckBox)
        display_layout.addWidget(self.displayShowTaskSpaceBoxCheckBox)
        close_display = qt.QPushButton("Close", self._displayDialog)
        close_display.clicked.connect(self._displayDialog.hide)
        display_layout.addWidget(close_display)
        self.displayButton.clicked.connect(self._displayDialog.show)

        self.homeGroup = qt.QGroupBox("6.2 — Task Home", parent)
        self.homeGroup.objectName = "DENTOBOTTaskHomeGroupBox"
        home_layout = qt.QVBoxLayout(self.homeGroup)
        home_description = qt.QLabel(
            "Edit all five joints and review the exact draft. Offline: save its "
            "configuration. Connected: Plan + Apply Home Draft, then Accept and "
            "Validate. Review and save send no motion.",
            self.homeGroup,
        )
        home_description.wordWrap = True
        home_layout.addWidget(home_description)
        review_buttons = qt.QHBoxLayout()
        self.reviewTaskHomeButton = qt.QPushButton(
            "Review Draft as Task Home", self.homeGroup
        )
        self.reviewTaskHomeButton.toolTip = (
            "Stage the exact typed J1–J5 draft for review. Offline setup requires "
            "a current saved Home configuration; connected setup requires the "
            "prepared case, accepted Base, loaded robot, and live ROS + MoveIt."
        )
        self.cancelTaskHomeReviewButton = qt.QPushButton(
            "Back to Edit / Cancel Review", self.homeGroup
        )
        self.cancelTaskHomeReviewButton.enabled = False
        self.cancelTaskHomeReviewButton.visible = False
        self.cancelTaskHomeReviewButton.toolTip = (
            "Cancel a known staged Home review. Reconcile an uncertain save result "
            "before another state-changing action."
        )
        review_buttons.addWidget(self.cancelTaskHomeReviewButton)
        review_buttons.addWidget(self.reviewTaskHomeButton)
        home_layout.addLayout(review_buttons)
        home_buttons = qt.QHBoxLayout()
        self.acceptTaskHomeButton = qt.QPushButton(
            "Task Home Mode Unknown", self.homeGroup
        )
        self.acceptTaskHomeButton.enabled = False
        self.acceptTaskHomeButton.visible = False
        self.acceptTaskHomeButton.toolTip = (
            "Save or accept only the exact current staged J1–J5 candidate. Offline "
            "save records an unreviewed configuration; connected acceptance requires "
            "live ROS + MoveIt validation. Reconcile an uncertain result first."
        )
        self.reconcileTaskHomeButton = qt.QPushButton(
            "Reconcile Task Home State", self.homeGroup
        )
        self.reconcileTaskHomeButton.toolTip = (
            "Reconcile the live Task Home after an uncertain save outcome. The "
            "result reflects façade evidence; this action issues no Home save or jog."
        )
        self.reconcileTaskHomeButton.enabled = False
        self.reconcileTaskHomeButton.visible = False
        home_buttons.addWidget(self.acceptTaskHomeButton)
        home_buttons.addWidget(self.reconcileTaskHomeButton)
        home_layout.addLayout(home_buttons)
        self.taskHomeCurrentStateLabel = qt.QLabel(
            "Current accepted five-joint state: unavailable.",
            self.homeGroup,
        )
        self.taskHomeCurrentStateLabel.objectName = (
            "DENTOBOTTaskHomeCurrentStateLabel"
        )
        self.taskHomeCurrentStateLabel.wordWrap = True
        self.taskHomeCurrentStateLabel.hide()
        home_layout.addWidget(self.taskHomeCurrentStateLabel)
        self.taskHomeConfiguredStateLabel = qt.QLabel(
            "Configured Home: not saved.", self.homeGroup
        )
        self.taskHomeConfiguredStateLabel.objectName = (
            "DENTOBOTTaskHomeConfiguredStateLabel"
        )
        self.taskHomeConfiguredStateLabel.wordWrap = True
        self.taskHomeConfiguredStateLabel.hide()
        home_layout.addWidget(self.taskHomeConfiguredStateLabel)
        self.taskHomeCandidateLabel = qt.QLabel(
            "Staged Task Home candidate: none.",
            self.homeGroup,
        )
        self.taskHomeCandidateLabel.objectName = "DENTOBOTTaskHomeCandidateLabel"
        self.taskHomeCandidateLabel.wordWrap = True
        self.taskHomeCandidateLabel.hide()
        home_layout.addWidget(self.taskHomeCandidateLabel)
        self.taskHomeReviewStatusLabel = qt.QLabel(
            "Home review status: unknown; no facade review is available.",
            self.homeGroup,
        )
        self.taskHomeReviewStatusLabel.objectName = (
            "DENTOBOTTaskHomeReviewStatusLabel"
        )
        self.taskHomeReviewStatusLabel.wordWrap = True
        self.taskHomeReviewStatusLabel.setProperty("dentobotRole", "status")
        home_layout.addWidget(self.taskHomeReviewStatusLabel)
        home_secondary_actions = qt.QHBoxLayout()
        self.taskHomeDetailsButton = qt.QPushButton("Home Details…", self.homeGroup)
        self.taskHomeDetailsButton.objectName = "DENTOBOTTaskHomeDetailsButton"
        self.applyTaskHomeButton = qt.QPushButton(
            "Plan + Apply Home Draft", self.homeGroup
        )
        self.applyTaskHomeButton.toolTip = (
            "Plan from the monitored robot state to the current J1–J5 draft and "
            "apply every waypoint through the strict simulation guard. "
            "This does not save Home; review and accept the applied draft afterward."
        )
        home_secondary_actions.addWidget(self.taskHomeDetailsButton)
        home_secondary_actions.addWidget(self.applyTaskHomeButton)
        home_layout.addLayout(home_secondary_actions)
        self.homeStatusLabel = qt.QLabel(
            "Saved Task Home: not accepted.", self.homeGroup
        )
        self.homeStatusLabel.wordWrap = True
        self.homeStatusLabel.setProperty("dentobotRole", "status")
        home_layout.addWidget(self.homeStatusLabel)
        self.taskHomeDetailsButton.clicked.connect(self.showTaskHomeDetailsDialog)

        self.workspaceReviewGroup = qt.QGroupBox(
            "Workspace and Assisted-Limit Review", parent
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
            "Simulation-only ROS 2 / MoveIt connection. Connecting does not accept "
            "the Base, validate Home, plan motion, or start hardware.",
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
            "Task Confirmation", parent
        )
        self.confirmationGroup.objectName = "DENTOBOTTaskConfirmationGroupBox"
        confirmation_layout = qt.QVBoxLayout(self.confirmationGroup)
        confirmation_description = qt.QLabel(
            "Review the already-active ROS/MoveIt runtime, acknowledged collision "
            "scene, live-validated Task Home, and reviewed workspace evidence. "
            "Confirmation freezes one immutable task snapshot; runtime connection and "
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
            "Complete runtime, Task Home, and workspace validation before confirming the task.",
            self.confirmationGroup,
        )
        self.confirmationStatusLabel.objectName = (
            "DENTOBOTTaskConfirmationStatusLabel"
        )
        self.confirmationStatusLabel.wordWrap = True
        self.confirmationStatusLabel.setProperty("dentobotRole", "status")
        confirmation_layout.addWidget(self.confirmationStatusLabel)

        self.goalGroup = qt.QGroupBox(
            "Cartesian TCP Exploration — Display Only", parent
        )
        self.goalGroup.objectName = "DENTOBOTGoalIkGroupBox"
        goal_layout = qt.QVBoxLayout(self.goalGroup)
        goal_layout.setSpacing(6)
        description = qt.QLabel(
            "Enable TCP Drag before using the native MoveIt probe. Viewport dragging "
            "and Cartesian nudges run exact J1–J5 MoveIt kinematic IK for responsive "
            "ghost review only; they do not check collision validity. Solve IK runs "
            "collision-aware evaluation and stages its J1–J5 result as a draft. A "
            "failed or missing live IK pose remains visual/rejected review. Only "
            "Guarded Jog after authoritative guard acknowledgement advances accepted "
            "simulated state. Manual exploration grants no route or preview authority. "
            "Translation steps use parent/world RAS. Pitch and yaw tilt the TCP/drill "
            "axis about local TCP axes; axial roll is unconstrained by the five-DOF arm.",
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
        self.solveIkButton = qt.QPushButton("Solve IK", self.goalGroup)
        self.solveIkButton.objectName = "DENTOBOTSolveIkButton"
        self.solveIkButton.toolTip = (
            "Run collision-aware MoveIt evaluation for the current TCP pose and stage "
            "the resulting J1–J5 values as a display-only manual draft. This does not "
            "advance accepted state; use Guarded Jog and wait for authoritative guard "
            "acknowledgement."
        )
        self.planGoalButton = qt.QPushButton("Plan to Goal", self.goalGroup)
        self.planGoalButton.objectName = "DENTOBOTPlanGoalButton"
        self.planGoalButton.enabled = False
        self.planGoalButton.toolTip = (
            "Disabled for Step 6.3 manual exploration. A manual TCP path has no "
            "route or preview authority."
        )
        buttons.addWidget(self.solveIkButton)
        buttons.addWidget(self.planGoalButton)
        goal_layout.addLayout(buttons)
        self.tcpDragEnabledCheckBox = qt.QCheckBox(
            "Enable TCP Drag", self.goalGroup
        )
        self.tcpDragEnabledCheckBox.objectName = "DENTOBOTEnableTcpDragCheckBox"
        self.tcpDragEnabledCheckBox.checked = False
        self.tcpDragEnabledCheckBox.toolTip = (
            "Explicitly enable the native MoveIt TCP transform handles. Unchecking "
            "disables viewport dragging and all Cartesian nudge controls."
        )
        goal_layout.addWidget(self.tcpDragEnabledCheckBox)
        self.tcpCartesianGroup = qt.QGroupBox(
            "Cartesian TCP Draft Controls", self.goalGroup
        )
        self.tcpCartesianGroup.objectName = "DENTOBOTTcpCartesianControlsGroupBox"
        tcp_layout = qt.QVBoxLayout(self.tcpCartesianGroup)
        tcp_layout.setContentsMargins(4, 4, 4, 4)
        tcp_steps = qt.QHBoxLayout()
        linear_step_label = qt.QLabel("Linear step (mm):", self.tcpCartesianGroup)
        linear_step_label.wordWrap = True
        linear_step_label.setMinimumWidth(0)
        linear_step_label.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        tcp_steps.addWidget(linear_step_label)
        self.tcpTranslationStepMm = qt.QDoubleSpinBox(self.tcpCartesianGroup)
        self.tcpTranslationStepMm.objectName = "DENTOBOTTcpTranslationStepMm"
        self.tcpTranslationStepMm.setMinimumWidth(0)
        self.tcpTranslationStepMm.minimum = 0.01
        self.tcpTranslationStepMm.maximum = 100.0
        self.tcpTranslationStepMm.decimals = 2
        self.tcpTranslationStepMm.singleStep = 0.1
        self.tcpTranslationStepMm.value = 1.0
        tcp_steps.addWidget(self.tcpTranslationStepMm)
        angular_step_label = qt.QLabel("Angular step (deg):", self.tcpCartesianGroup)
        angular_step_label.wordWrap = True
        angular_step_label.setMinimumWidth(0)
        angular_step_label.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        tcp_steps.addWidget(angular_step_label)
        self.tcpRotationStepDeg = qt.QDoubleSpinBox(self.tcpCartesianGroup)
        self.tcpRotationStepDeg.objectName = "DENTOBOTTcpRotationStepDeg"
        self.tcpRotationStepDeg.setMinimumWidth(0)
        self.tcpRotationStepDeg.minimum = 0.1
        self.tcpRotationStepDeg.maximum = 90.0
        self.tcpRotationStepDeg.decimals = 1
        self.tcpRotationStepDeg.singleStep = 1.0
        self.tcpRotationStepDeg.value = 5.0
        tcp_steps.addWidget(self.tcpRotationStepDeg)
        tcp_layout.addLayout(tcp_steps)
        tcp_controls = qt.QGridLayout()
        tcp_controls.addWidget(qt.QLabel("Axis", self.tcpCartesianGroup), 0, 0)
        tcp_controls.addWidget(qt.QLabel("−", self.tcpCartesianGroup), 0, 1)
        tcp_controls.addWidget(qt.QLabel("+", self.tcpCartesianGroup), 0, 2)
        self.tcpCartesianNudgeButtons = {}
        for row, axis, label, is_rotation in (
            (1, 0, "X (world RAS, mm)", False),
            (2, 1, "Y (world RAS, mm)", False),
            (3, 2, "Z (world RAS, mm)", False),
            (5, 1, "Pitch (local TCP, deg)", True),
            (6, 2, "Yaw (local TCP, deg)", True),
        ):
            label_widget = qt.QLabel(label, self.tcpCartesianGroup)
            label_widget.wordWrap = True
            label_widget.setMinimumWidth(0)
            label_widget.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            tcp_controls.addWidget(label_widget, row, 0)
            for column, direction, sign in ((1, "−", -1.0), (2, "+", 1.0)):
                button = qt.QPushButton(direction, self.tcpCartesianGroup)
                button.objectName = (
                    f"DENTOBOTTcp{'Rotation' if is_rotation else 'Translation'}"
                    f"{axis}{'Minus' if sign < 0 else 'Plus'}Button"
                )
                button.toolTip = (
                    f"Nudge {'local TCP rotation' if is_rotation else 'world RAS translation'} "
                    f"axis {axis} by one configured step. This edits only the review draft."
                )
                button.clicked.connect(
                    lambda _checked=False, ta=None if is_rotation else axis,
                    ra=axis if is_rotation else None, d=sign:
                        self._onTcpCartesianNudge(ta, ra, d)
                )
                self.tcpCartesianNudgeButtons[(is_rotation, axis, sign)] = button
                tcp_controls.addWidget(button, row, column)
        axial_roll_label = qt.QLabel(
            "Axial roll is unconstrained by the five-DOF arm.", self.tcpCartesianGroup
        )
        axial_roll_label.objectName = "DENTOBOTTcpAxialRollUnconstrainedLabel"
        axial_roll_label.wordWrap = True
        axial_roll_label.setMinimumWidth(0)
        axial_roll_label.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        tcp_controls.addWidget(axial_roll_label, 4, 0, 1, 3)
        tcp_controls.setColumnStretch(1, 1)
        tcp_controls.setColumnStretch(2, 1)
        tcp_layout.addLayout(tcp_controls)
        self.tcpKeyboardEnabledCheckBox = qt.QCheckBox(
            "Enable TCP keyboard nudges", self.tcpCartesianGroup
        )
        self.tcpKeyboardEnabledCheckBox.objectName = (
            "DENTOBOTEnableTcpKeyboardNudgesCheckBox"
        )
        self.tcpKeyboardEnabledCheckBox.checked = False
        self.tcpKeyboardEnabledCheckBox.toolTip = (
            "Arrow keys move X/Y, Page Up/Down move Z; Shift+Left/Right rotates yaw, "
            "and Ctrl+Up/Down rotates pitch. Axial roll is unconstrained by the "
            "five-DOF arm. Shortcuts are active only while this "
            "workbench is visible and enabled, and no text or numeric editor has focus."
        )
        tcp_layout.addWidget(self.tcpKeyboardEnabledCheckBox)
        self.tcpKeyboardHelpLabel = qt.QLabel(
            "Keyboard: ←/→ X, ↓/↑ Y, PgDn/PgUp Z; Ctrl+↓/↑ pitch; "
            "Shift+←/→ yaw. Axial roll is unconstrained by the five-DOF arm. J1–J5 "
            "numeric fields accept typing and focused arrow-key adjustment.",
            self.tcpCartesianGroup,
        )
        self.tcpKeyboardHelpLabel.wordWrap = True
        tcp_layout.addWidget(self.tcpKeyboardHelpLabel)
        goal_layout.addWidget(self.tcpCartesianGroup)
        self._setupTcpKeyboardShortcuts()
        self.goalStatusLabel = qt.QLabel(
            "TCP review: connect ROS + MoveIt and lock the base before checking Enable "
            "TCP Drag. Live drag/nudge IK is kinematic-only, not collision validity; "
            "Solve IK is collision-aware and stages a J1–J5 draft. Guarded Jog is "
            "required for accepted simulated state. Failed/missing live IK stays "
            "visual/rejected, with no route or preview authority.",
            self.goalGroup,
        )
        self.goalStatusLabel.objectName = "DENTOBOTGoalIkStatusLabel"
        self.goalStatusLabel.wordWrap = True
        self.goalStatusLabel.setProperty("dentobotRole", "status")
        goal_layout.addWidget(self.goalStatusLabel)

        self.manualJogGroup = qt.QGroupBox(
            "Manual Robot Simulation Solver: Joint Jog", parent
        )
        self.manualJogGroup.objectName = "DENTOBOTManualJogGroupBox"
        manual_jog_layout = qt.QVBoxLayout(self.manualJogGroup)
        manual_jog_description = qt.QLabel(
            "Edit a display-only J1–J5 draft, then request one exact guarded "
            "simulation jog. The accepted robot changes only after the guard "
            "acknowledges the requested state. This does not create a route or "
            "authorize preview. Use each slider or type a value in its numeric "
            "field; focused numeric fields also support arrow-key adjustment.",
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
        self.manualJogAcceptedStateLabel.setMinimumWidth(0)
        self.manualJogAcceptedStateLabel.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        manual_jog_layout.addWidget(self.manualJogAcceptedStateLabel)
        self.manualJogControlsGroup = qt.QGroupBox(
            "Joint draft (J1–J5)", self.manualJogGroup
        )
        self.manualJogControlsGroup.objectName = "DENTOBOTManualJogDraftControlsGroup"
        self.manualJogControlsGroup.setSizePolicy(
            qt.QSizePolicy.Preferred, qt.QSizePolicy.Maximum
        )
        self._manualJogControlsLayout = qt.QVBoxLayout(self.manualJogControlsGroup)
        self.manualJogDraftIntroLabel = qt.QLabel(
            "Draft — display only; no command sent by editing.",
            self.manualJogControlsGroup,
        )
        self.manualJogDraftIntroLabel.wordWrap = True
        self.manualJogDraftIntroLabel.setMinimumWidth(0)
        self.manualJogDraftIntroLabel.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        self._manualJogControlsLayout.addWidget(self.manualJogDraftIntroLabel)
        self.manualJogDraftStateLabel = qt.QLabel(
            "Draft state: unavailable", self.manualJogControlsGroup
        )
        self.manualJogDraftStateLabel.objectName = "DENTOBOTManualJogDraftStateLabel"
        self.manualJogDraftStateLabel.wordWrap = True
        self.manualJogDraftStateLabel.setMinimumWidth(0)
        self.manualJogDraftStateLabel.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        self.manualJogDraftLimitLabel = qt.QLabel(
            "Draft limits: unavailable.", self.manualJogControlsGroup
        )
        self.manualJogDraftLimitLabel.objectName = "DENTOBOTManualJogDraftLimitLabel"
        self.manualJogDraftLimitLabel.wordWrap = True
        self.manualJogDraftLimitLabel.setMinimumWidth(0)
        self.manualJogDraftLimitLabel.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        self.manualJogDraftLimitLabel.setProperty("dentobotRole", "status")
        self._manualJogControlsLayout.addWidget(self.manualJogDraftLimitLabel)
        self.manualJogJointControls = {}
        self._manualJogDisplayValues = (0.0, 0.0, 0.0, 0.0, 0.0)
        units = ("deg", "mm", "deg", "mm", "deg")
        joint_labels = ("J1", "J2", "J3", "J4", "J5")
        self._manualJogJointPresentation = {}
        joint_rows = qt.QVBoxLayout()
        joint_rows.setContentsMargins(0, 0, 0, 0)
        joint_rows.setSpacing(6)
        for index, (joint, label, unit) in enumerate(
            zip(JOINT_NAMES, joint_labels, units, strict=True)
        ):
            row = qt.QWidget(self.manualJogControlsGroup)
            row_layout = qt.QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)
            header = qt.QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(6)
            joint_label = qt.QLabel(f"{label} ({unit})", row)
            joint_label.objectName = f"DENTOBOTManualJog{label}Label"
            joint_label.wordWrap = False
            joint_label.toolTip = f"{label} display-only joint draft in {unit}."
            joint_label.setMinimumWidth(56)
            joint_label.setSizePolicy(
                qt.QSizePolicy.Minimum, qt.QSizePolicy.Fixed
            )
            header.addWidget(joint_label)
            comparison = qt.QLabel("Accepted/delta unavailable.", row)
            comparison.objectName = f"DENTOBOTManualJog{label}Comparison"
            comparison.wordWrap = True
            comparison.setMinimumWidth(0)
            comparison.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            header.addWidget(comparison, 1)
            slider = qt.QSlider(qt.Qt.Horizontal, row)
            slider.objectName = f"DENTOBOTManualJog{label}Slider"
            slider.toolTip = f"Adjust the display-only {label} joint draft."
            slider.minimum = 0
            slider.maximum = 10000
            slider.setMinimumWidth(0)
            slider.setSizePolicy(
                qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed
            )
            value = qt.QDoubleSpinBox(row)
            value.objectName = f"DENTOBOTManualJog{label}Value"
            value.setMinimumWidth(95)
            value.setSizePolicy(
                qt.QSizePolicy.Preferred, qt.QSizePolicy.Fixed
            )
            value.decimals = 2
            value.singleStep = 0.1
            value.keyboardTracking = True
            value.toolTip = (
                f"Type a {label} draft value or focus this numeric control and use "
                "the arrow keys. This changes only the display-only draft."
            )
            self.manualJogJointControls[joint] = (slider, value, joint_label)
            header.addWidget(value)
            row_layout.addLayout(header)
            row_layout.addWidget(slider)
            endpoints = qt.QHBoxLayout()
            endpoints.setContentsMargins(0, 0, 0, 0)
            endpoints.setSpacing(6)
            lower = qt.QLabel("--", row)
            lower.setMinimumWidth(0)
            notice = qt.QLabel("", row)
            notice.wordWrap = True
            notice.setMinimumWidth(0)
            notice.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            notice.hide()
            upper = qt.QLabel("--", row)
            upper.setMinimumWidth(0)
            lower.setToolTip("Lower numeric endpoint of the slider range.")
            upper.setToolTip("Upper numeric endpoint of the slider range.")
            endpoints.addWidget(lower)
            endpoints.addStretch(1)
            endpoints.addWidget(upper)
            row_layout.addLayout(endpoints)
            row_layout.addWidget(notice)
            self._manualJogJointPresentation[joint] = {
                "comparison": comparison,
                "lower": lower,
                "upper": upper,
                "notice": notice,
                "details": None,
            }
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
            joint_rows.addWidget(row)
        self._manualJogControlsLayout.addLayout(joint_rows)
        self.resetManualJogDraftButton = qt.QPushButton(
            "Reset Draft Unavailable", self.manualJogControlsGroup
        )
        self.resetManualJogDraftButton.objectName = (
            "DENTOBOTResetManualJogDraftButton"
        )
        self._manualJogControlsLayout.addWidget(self.resetManualJogDraftButton)
        self.manualJogDetailsToggle = qt.QToolButton(self.manualJogControlsGroup)
        self.manualJogDetailsToggle.objectName = "DENTOBOTManualJogDetailsToggle"
        self.manualJogDetailsToggle.text = "Limits and state details"
        self.manualJogDetailsToggle.setCheckable(True)
        self.manualJogDetailsToggle.setChecked(False)
        self._manualJogControlsLayout.addWidget(self.manualJogDetailsToggle)
        self._manualJogDetailsWidget = qt.QWidget(self.manualJogControlsGroup)
        self._manualJogDetailsWidget.objectName = "DENTOBOTManualJogDetails"
        details_layout = qt.QVBoxLayout(self._manualJogDetailsWidget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(4)
        for joint in JOINT_NAMES:
            details = qt.QLabel("Limits unavailable.", self._manualJogDetailsWidget)
            details.objectName = (
                f"DENTOBOTManualJog{joint}LimitDetails"
            )
            details.wordWrap = True
            details.setMinimumWidth(0)
            details.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            details_layout.addWidget(details)
            self._manualJogJointPresentation[joint]["details"] = details
        self.manualJogDraftStateLabel.setParent(self._manualJogDetailsWidget)
        details_layout.addWidget(self.manualJogDraftStateLabel)
        self._manualJogControlsLayout.addWidget(self._manualJogDetailsWidget)
        self._manualJogDetailsWidget.hide()
        self.manualJogDetailsToggle.toggled.connect(
            self._manualJogDetailsWidget.setVisible
        )
        self.taskHomeJointEditor = qt.QGroupBox(
            "Home configuration draft (J1–J5)", self.homeGroup
        )
        self.taskHomeJointEditor.objectName = "DENTOBOTTaskHomeJointEditor"
        home_joint_layout = qt.QGridLayout(self.taskHomeJointEditor)
        home_joint_layout.setContentsMargins(6, 6, 6, 6)
        home_joint_layout.setHorizontalSpacing(5)
        home_joint_layout.setVerticalSpacing(3)
        self.taskHomeJointControls = {}
        for index, (joint, label, unit) in enumerate(
            zip(JOINT_NAMES, joint_labels, units, strict=True)
        ):
            identity = qt.QLabel(label, self.taskHomeJointEditor)
            identity.objectName = f"DENTOBOTTaskHome{label}Label"
            identity.setMinimumWidth(22)
            unit_label = qt.QLabel(unit, self.taskHomeJointEditor)
            unit_label.setMinimumWidth(26)
            unit_label.setProperty("dentobotRole", "muted")
            slider = qt.QSlider(qt.Qt.Horizontal, self.taskHomeJointEditor)
            slider.objectName = f"DENTOBOTTaskHome{label}Slider"
            slider.minimum = 0
            slider.maximum = 10000
            slider.setMinimumWidth(0)
            slider.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Fixed)
            value = qt.QDoubleSpinBox(self.taskHomeJointEditor)
            value.objectName = f"DENTOBOTTaskHome{label}Value"
            value.setMinimumWidth(78)
            value.decimals = 2
            value.singleStep = 0.1
            value.keyboardTracking = True
            state = qt.QLabel("Draft unavailable", self.taskHomeJointEditor)
            state.objectName = f"DENTOBOTTaskHome{label}State"
            state.setMinimumWidth(0)
            state.setSizePolicy(qt.QSizePolicy.Ignored, qt.QSizePolicy.Fixed)
            state.setProperty("dentobotRole", "muted")
            self.taskHomeJointControls[joint] = (slider, value, state)
            slider.valueChanged.connect(
                lambda position=0, name=joint: self._onTaskHomeSliderChanged(
                    name, position
                )
            )
            value.valueChanged.connect(
                lambda current=0.0, name=joint: self._onTaskHomeNumericChanged(
                    name, current
                )
            )
            home_joint_layout.addWidget(identity, index * 2, 0)
            home_joint_layout.addWidget(unit_label, index * 2, 1)
            home_joint_layout.addWidget(slider, index * 2, 2)
            home_joint_layout.addWidget(value, index * 2, 3)
            home_joint_layout.addWidget(state, index * 2 + 1, 0, 1, 4)
        home_joint_layout.setColumnStretch(2, 1)
        self.homeGroup.layout().insertWidget(1, self.taskHomeJointEditor)
        manual_jog_layout.addWidget(self.manualJogControlsGroup)
        manual_jog_keyboard_layout = qt.QHBoxLayout()
        self.manualJogKeyboardEnabledCheckBox = qt.QCheckBox(
            "Enable joint keyboard nudges", self.manualJogGroup
        )
        self.manualJogKeyboardEnabledCheckBox.objectName = (
            "DENTOBOTManualJogKeyboardEnabledCheckBox"
        )
        self.manualJogKeyboardEnabledCheckBox.checked = False
        self.manualJogKeyboardEnabledCheckBox.toolTip = (
            "Explicitly enable draft-only J1–J5 keyboard nudges. Shortcuts are "
            "inactive outside visible Step 6.3 or while draft controls are blocked."
        )
        manual_jog_keyboard_layout.addWidget(self.manualJogKeyboardEnabledCheckBox)
        manual_jog_keyboard_layout.addWidget(qt.QLabel("Step:", self.manualJogGroup))
        self.manualJogKeyboardStepComboBox = qt.QComboBox(self.manualJogGroup)
        self.manualJogKeyboardStepComboBox.objectName = (
            "DENTOBOTManualJogKeyboardStepComboBox"
        )
        for degrees_step, millimeters_step in (
            (0.1, 0.1),
            (0.5, 0.5),
            (1.0, 1.0),
        ):
            self.manualJogKeyboardStepComboBox.addItem(
                f"{degrees_step:g}° / {millimeters_step:g} mm",
                (degrees_step, millimeters_step),
            )
        manual_jog_keyboard_layout.addWidget(self.manualJogKeyboardStepComboBox)
        manual_jog_layout.addLayout(manual_jog_keyboard_layout)
        self.manualJogKeyboardHelpLabel = qt.QLabel(
            "Keyboard nudges: J1 Q/A, J2 W/S, J3 E/D, J4 R/F, J5 T/G "
            "(positive/negative). Each key changes only that joint's display-only draft.",
            self.manualJogGroup,
        )
        self.manualJogKeyboardHelpLabel.objectName = (
            "DENTOBOTManualJogKeyboardHelpLabel"
        )
        self.manualJogKeyboardHelpLabel.wordWrap = True
        manual_jog_layout.addWidget(self.manualJogKeyboardHelpLabel)
        self._setupManualJogKeyboardShortcuts()
        manual_jog_primary_actions = qt.QHBoxLayout()
        manual_jog_secondary_actions = qt.QHBoxLayout()
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
        self.reconcileManualJogButton = qt.QPushButton(
            "Reconcile State", self.manualJogGroup
        )
        self.reconcileManualJogButton.objectName = "DENTOBOTReconcileManualJogButton"
        self.reconcileManualJogButton.toolTip = (
            "Read and verify the native accepted J1–J5 state. This does not issue motion."
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
        manual_jog_primary_actions.addWidget(self.checkManualDraftStateButton)
        manual_jog_primary_actions.addWidget(self.reconcileManualJogButton)
        manual_jog_secondary_actions.addWidget(self.guardedManualJogButton)
        manual_jog_secondary_actions.addWidget(self.exportManualRecordButton)
        manual_jog_layout.addLayout(manual_jog_primary_actions)
        manual_jog_layout.addLayout(manual_jog_secondary_actions)
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
        history_group = qt.QGroupBox(
            "Historical Manual Simulation Records — Display Only", self.manualJogGroup
        )
        self.manualHistoryGroup = history_group
        history_layout = qt.QVBoxLayout(history_group)
        history_description = qt.QLabel(
            "Open a validated JSON record to inspect its saved identity and ordered "
            "events. Selecting a record may draw its historical TCP path; stepping "
            "events only changes this display. No imported evidence restores live "
            "state or authorizes motion or preview.",
            history_group,
        )
        history_description.wordWrap = True
        history_layout.addWidget(history_description)
        history_controls = qt.QHBoxLayout()
        self.importManualRecordButton = qt.QPushButton(
            "Open Historical Record…", history_group
        )
        self.importManualRecordButton.objectName = (
            "DENTOBOTImportManualSimulationRecordButton"
        )
        self.clearManualRecordButton = qt.QPushButton(
            "Clear Historical Display", history_group
        )
        self.clearManualRecordButton.objectName = (
            "DENTOBOTClearManualSimulationRecordButton"
        )
        self.clearManualRecordButton.enabled = False
        self.manualSimulationRecordComboBox = qt.QComboBox(history_group)
        self.manualSimulationRecordComboBox.objectName = (
            "DENTOBOTManualSimulationRecordSelector"
        )
        self.manualSimulationRecordComboBox.enabled = False
        history_controls.addWidget(self.importManualRecordButton)
        history_controls.addWidget(self.manualSimulationRecordComboBox, 1)
        history_controls.addWidget(self.clearManualRecordButton)
        history_layout.addLayout(history_controls)
        self.manualSimulationRecordIdentityLabel = qt.QLabel(
            "No historical record loaded.", history_group
        )
        self.manualSimulationRecordIdentityLabel.objectName = (
            "DENTOBOTManualSimulationRecordIdentityLabel"
        )
        self.manualSimulationRecordIdentityLabel.wordWrap = True
        history_layout.addWidget(self.manualSimulationRecordIdentityLabel)
        self.manualSimulationEventList = qt.QListWidget(history_group)
        self.manualSimulationEventList.objectName = (
            "DENTOBOTManualSimulationEventList"
        )
        self.manualSimulationEventList.setMinimumHeight(110)
        history_layout.addWidget(self.manualSimulationEventList)
        event_controls = qt.QHBoxLayout()
        self.previousManualSimulationEventButton = qt.QPushButton(
            "‹ Previous Event", history_group
        )
        self.nextManualSimulationEventButton = qt.QPushButton(
            "Next Event ›", history_group
        )
        self.previousManualSimulationEventButton.enabled = False
        self.nextManualSimulationEventButton.enabled = False
        event_controls.addWidget(self.previousManualSimulationEventButton)
        event_controls.addWidget(self.nextManualSimulationEventButton)
        history_layout.addLayout(event_controls)
        self.manualSimulationEventDetailsText = qt.QPlainTextEdit(history_group)
        self.manualSimulationEventDetailsText.objectName = (
            "DENTOBOTManualSimulationEventDetails"
        )
        self.manualSimulationEventDetailsText.readOnly = True
        self.manualSimulationEventDetailsText.setMaximumHeight(220)
        self.manualSimulationEventDetailsText.setPlainText(
            "Select a record event to inspect its saved evidence."
        )
        history_layout.addWidget(self.manualSimulationEventDetailsText)
        self.manualRecordImportStatusLabel = qt.QLabel(
            "Import status: no historical record loaded.", history_group
        )
        self.manualRecordImportStatusLabel.objectName = (
            "DENTOBOTManualRecordImportStatusLabel"
        )
        self.manualRecordImportStatusLabel.wordWrap = True
        self.manualRecordImportStatusLabel.setProperty("dentobotRole", "status")
        history_layout.addWidget(self.manualRecordImportStatusLabel)
        manual_jog_layout.addWidget(history_group)

        self.collisionGroup = qt.QGroupBox("6.1 — Planning-Scene Audit", parent)
        self.collisionGroup.objectName = "DENTOBOTCollisionSceneGroupBox"
        collision_layout = qt.QVBoxLayout(self.collisionGroup)
        collision_description = qt.QLabel(
            "Inspect or repeat the authoritative collision-scene synchronization. "
            "Full fingerprints, transforms, bounds and acknowledgement evidence "
            "remain available in diagnostics.",
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

        self.previewControlGroup = qt.QGroupBox("Preview & Control", parent)
        self.previewControlGroup.objectName = "DENTOBOTPreviewControlGroupBox"
        preview_layout = qt.QVBoxLayout(self.previewControlGroup)
        preview_description = qt.QLabel(
            "Run only the current complete guarded plan in simulation. Stop and "
            "guarded Return Home stay here with the preview lock status.",
            self.previewControlGroup,
        )
        preview_description.wordWrap = True
        preview_layout.addWidget(preview_description)
        preview_actions = qt.QHBoxLayout()
        self.previewApproachButton = qt.QPushButton(
            "Preview Approach", self.previewControlGroup
        )
        self.previewDrillingButton = qt.QPushButton(
            "Preview Drill", self.previewControlGroup
        )
        preview_actions.addWidget(self.previewApproachButton)
        preview_actions.addWidget(self.previewDrillingButton)
        preview_layout.addLayout(preview_actions)
        preview_controls = qt.QHBoxLayout()
        self.stopPreviewButton = qt.QPushButton(
            "Stop Preview", self.previewControlGroup
        )
        self.returnHomeButton = qt.QPushButton(
            "Guarded Return Home", self.previewControlGroup
        )
        self.stopPreviewDrillingButton = self.stopPreviewButton
        self.returnHomeDrillingButton = self.returnHomeButton
        preview_controls.addWidget(self.stopPreviewButton)
        preview_controls.addWidget(self.returnHomeButton)
        preview_layout.addLayout(preview_controls)
        preview_settings = qt.QHBoxLayout()
        preview_settings.addWidget(
            qt.QLabel("Preview speed:", self.previewControlGroup)
        )
        self.previewSpeedCombo = qt.QComboBox(self.previewControlGroup)
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
        preview_layout.addLayout(preview_settings)
        self.previewProgressBar = qt.QProgressBar(self.previewControlGroup)
        self.previewProgressBar.minimum = 0
        self.previewProgressBar.maximum = 1
        self.previewProgressBar.value = 0
        self.previewProgressBar.format = "Preview: 0/0"
        preview_layout.addWidget(self.previewProgressBar)
        self.previewProgressLabel = qt.QLabel(
            "No guarded preview is running.", self.previewControlGroup
        )
        self.previewProgressLabel.wordWrap = True
        self.previewProgressLabel.setProperty("dentobotRole", "status")
        preview_layout.addWidget(self.previewProgressLabel)
        execution_disabled = qt.QLabel(
            "EXECUTE DISABLED — guarded simulation preview only. Hardware homing, "
            "drilling, and controller execution are blocked.",
            self.previewControlGroup,
        )
        execution_disabled.wordWrap = True
        execution_disabled.setProperty("dentobotRole", "warning")
        preview_layout.addWidget(execution_disabled)

        self.approachGroup = qt.QGroupBox("Approach Planning & Diagnostics", parent)
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
            "the terminal path has planned successfully. "
            "Partial diagnostic paths remain display-only. Preview Approach and "
            "Preview Drill require the current complete guarded plan. Approach "
            "planning is enabled only after the complete Entry-to-Target line "
            "passes a bounded reachability preflight. A failed preflight retains "
            "last-valid/first-invalid evidence without assigning its cause.",
            self.approachGroup,
        )
        approach_description.wordWrap = True
        approach_layout.addWidget(approach_description)
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
        # Advanced options (operator 2026-10-02). Default off: spindle-template
        # contact truncates drilling at the last collision-free state.
        self.planningAdvancedGroup = qt.QGroupBox("Advanced options", self.approachGroup)
        planning_advanced_layout = qt.QVBoxLayout(self.planningAdvancedGroup)
        self.allowSpindleGuideContactCheckBox = qt.QCheckBox(
            "Allow spindle-housing contact with template (\u2264 0.5 mm)", self.planningAdvancedGroup
        )
        self.allowSpindleGuideContactCheckBox.objectName = "DENTOBOTAllowSpindleGuideContact63"
        self.allowSpindleGuideContactCheckBox.toolTip = (
            "Off (default): any spindle-housing/template contact is a collision and the "
            "drilling route ends at the last collision-free state. On: the guard tolerates "
            "contact up to 0.5 mm as a warning. Shared with the Step 4C advanced option; "
            "re-plan after changing it."
        )
        planning_advanced_layout.addWidget(self.allowSpindleGuideContactCheckBox)
        mouth_barrier_row = qt.QHBoxLayout()
        mouth_barrier_row.addWidget(qt.QLabel("Mouth barrier edges:", self.planningAdvancedGroup))
        self.mouthBarrierEdgeModeComboBox = qt.QComboBox(self.planningAdvancedGroup)
        self.mouthBarrierEdgeModeComboBox.objectName = "DENTOBOTMouthBarrierEdgeMode63"
        for label, mode in (
            ("Gum line (lips retracted)", "gum_line"),
            ("Tooth biting edges (lips relaxed)", "biting_edge"),
            ("Off (no barrier; diagnosis only)", "off"),
        ):
            self.mouthBarrierEdgeModeComboBox.addItem(label, mode)
        self.mouthBarrierEdgeModeComboBox.toolTip = (
            "3D mouth barrier: virtual lips and cheeks that the whole robot must avoid; "
            "the tool enters through the opening. Gum line (default): opening edges at "
            "the anterior gum line + 5 mm. Biting edges: at the canine cusp tips + 5 mm. "
            "Re-plan after changing it."
        )
        mouth_barrier_row.addWidget(self.mouthBarrierEdgeModeComboBox, 1)
        planning_advanced_layout.addLayout(mouth_barrier_row)
        self.showMouthBarrierCheckBox = qt.QCheckBox("Show mouth barrier", self.planningAdvancedGroup)
        self.showMouthBarrierCheckBox.objectName = "DENTOBOTShowMouthBarrier63"
        self.showMouthBarrierCheckBox.checked = True
        self.showMouthBarrierCheckBox.toolTip = (
            "Show or hide the pink virtual lips/cheeks in the 3D view. Display only: "
            "the planner still avoids the barrier unless its edges are set to Off."
        )
        planning_advanced_layout.addWidget(self.showMouthBarrierCheckBox)
        # Operator 2026-10-03: low default opacities, explicit opacity controls and
        # an optional incisor-centred task-space box (display only, off by default).
        barrier_opacity_row = qt.QHBoxLayout()
        barrier_opacity_row.addWidget(qt.QLabel("Mouth barrier opacity:", self.planningAdvancedGroup))
        self.mouthBarrierOpacitySlider = qt.QSlider(qt.Qt.Horizontal, self.planningAdvancedGroup)
        self.mouthBarrierOpacitySlider.objectName = "DENTOBOTMouthBarrierOpacity63"
        self.mouthBarrierOpacitySlider.minimum, self.mouthBarrierOpacitySlider.maximum = 0, 100
        self.mouthBarrierOpacitySlider.value = 12
        self.mouthBarrierOpacitySlider.toolTip = "Mouth barrier opacity (display only)."
        barrier_opacity_row.addWidget(self.mouthBarrierOpacitySlider, 1)
        planning_advanced_layout.addLayout(barrier_opacity_row)
        self.showTaskSpaceBoxCheckBox = qt.QCheckBox(
            "Show task-space box (incisor-centred)", self.planningAdvancedGroup
        )
        self.showTaskSpaceBoxCheckBox.objectName = "DENTOBOTShowTaskSpaceBox63"
        self.showTaskSpaceBoxCheckBox.checked = False
        self.showTaskSpaceBoxCheckBox.toolTip = (
            "Blue cube centred between the upper and opened-lower incisors (the "
            "workspace ROI draft centre when loaded). Display only: it does not "
            "change workspace sampling, the MoveIt scene or any planning gate."
        )
        planning_advanced_layout.addWidget(self.showTaskSpaceBoxCheckBox)
        task_box_row = qt.QHBoxLayout()
        task_box_row.addWidget(qt.QLabel("Side:", self.planningAdvancedGroup))
        self.taskSpaceBoxSideSpinBox = qt.QDoubleSpinBox(self.planningAdvancedGroup)
        self.taskSpaceBoxSideSpinBox.objectName = "DENTOBOTTaskSpaceBoxSide63"
        self.taskSpaceBoxSideSpinBox.minimum, self.taskSpaceBoxSideSpinBox.maximum = 10.0, 400.0
        self.taskSpaceBoxSideSpinBox.decimals, self.taskSpaceBoxSideSpinBox.singleStep = 1, 5.0
        self.taskSpaceBoxSideSpinBox.suffix = " mm"
        self.taskSpaceBoxSideSpinBox.value = 200.0
        self.taskSpaceBoxSideSpinBox.toolTip = "Task-space box side length (display only)."
        task_box_row.addWidget(self.taskSpaceBoxSideSpinBox)
        task_box_row.addWidget(qt.QLabel("Opacity:", self.planningAdvancedGroup))
        self.taskSpaceBoxOpacitySlider = qt.QSlider(qt.Qt.Horizontal, self.planningAdvancedGroup)
        self.taskSpaceBoxOpacitySlider.objectName = "DENTOBOTTaskSpaceBoxOpacity63"
        self.taskSpaceBoxOpacitySlider.minimum, self.taskSpaceBoxOpacitySlider.maximum = 0, 100
        self.taskSpaceBoxOpacitySlider.value = 10
        self.taskSpaceBoxOpacitySlider.toolTip = "Task-space box opacity (display only)."
        task_box_row.addWidget(self.taskSpaceBoxOpacitySlider, 1)
        planning_advanced_layout.addLayout(task_box_row)
        self.taskSpaceBoxStatusLabel = qt.QLabel("", self.planningAdvancedGroup)
        self.taskSpaceBoxStatusLabel.wordWrap = True
        self.taskSpaceBoxStatusLabel.setProperty("dentobotRole", "status")
        planning_advanced_layout.addWidget(self.taskSpaceBoxStatusLabel)
        approach_layout.addWidget(self.planningAdvancedGroup)
        # Run options set before planning (operator 2026-10-03): development fast
        # mode and 3D depth peeling. Neither changes collision or guard results.
        self.planningRunOptionsGroup = qt.QGroupBox("Run options", self.approachGroup)
        run_options_layout = qt.QVBoxLayout(self.planningRunOptionsGroup)
        self.devFastModeCheckBox = qt.QCheckBox(
            "Development fast mode: stop at the first Complete route", self.planningRunOptionsGroup
        )
        self.devFastModeCheckBox.objectName = "DENTOBOTDevFastMode63"
        self.devFastModeCheckBox.checked = False
        self.devFastModeCheckBox.toolTip = (
            "Off (default): Plan Approach plans and guards every IK candidate before "
            "choosing; required for any recorded, accepted or case-comparison result. "
            "On: planning stops at the first Complete route. The plan message is "
            "stamped DEVELOPMENT FAST MODE and the result is not for acceptance. "
            "Takes effect at the next Plan Approach."
        )
        run_options_layout.addWidget(self.devFastModeCheckBox)
        self.depthPeelingCheckBox = qt.QCheckBox(
            "Depth peeling: exact transparency, slower 3D redraws", self.planningRunOptionsGroup
        )
        self.depthPeelingCheckBox.objectName = "DENTOBOTDepthPeeling63"
        self.depthPeelingCheckBox.checked = True
        self.depthPeelingCheckBox.toolTip = (
            "On (Slicer default): see-through models (mouth barrier, envelope, robot "
            "ghosts) are layered exactly. Off: faster 3D redraws (r19 software "
            "rendering: 46 ms vs 204 ms per frame) but overlapping see-through "
            "surfaces may blend in the wrong order. Applies to all 3D views. Display "
            "only: no effect on planning, collision or guard results."
        )
        run_options_layout.addWidget(self.depthPeelingCheckBox)
        approach_layout.addWidget(self.planningRunOptionsGroup)
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
        self.diagnoseBaseButton = qt.QPushButton("Diagnose This Base", self.approachGroup)
        self.diagnoseBaseButton.objectName = "DENTOBOTDiagnoseBaseButton"
        self.diagnoseBaseButton.toolTip = (
            "Run stroke reach, PreEntry endpoint, P1, P2 and P3 in order and stop at "
            "the first failure, naming its cause (Base placement, collision, planner "
            "or tool geometry). Diagnostic only; no route or preview authority."
        )
        self.motionDiagnosticsButton = qt.QPushButton(
            "Inspect Motion Diagnostics", self.approachGroup
        )
        self.motionDiagnosticsButton.enabled = False
        approach_buttons.addWidget(self.planApproachButton)
        approach_buttons.addWidget(self.checkPreEntryIKButton)
        approach_buttons.addWidget(self.motionDiagnosticsButton)
        approach_layout.addLayout(approach_buttons)
        approach_layout.addWidget(self.diagnoseBaseButton)
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
        self.approachStatusLabel = qt.QLabel("No Approach plan.", self.approachGroup)
        self.approachStatusLabel.wordWrap = True
        self.approachStatusLabel.setProperty("dentobotRole", "status")
        approach_layout.addWidget(self.approachStatusLabel)
        self.drillingGroup = qt.QGroupBox("Drill Planning Diagnostics", parent)
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
        drilling_buttons.addWidget(self.planDrillingButton)
        drilling_layout.addLayout(drilling_buttons)
        self.drillingPlanningPolicyButton = qt.QPushButton(
            "Planning Parameters…", self.drillingGroup
        )
        drilling_layout.addWidget(self.drillingPlanningPolicyButton)
        self.drillingStatusLabel = qt.QLabel("No Drill preview plan.", self.drillingGroup)
        self.drillingStatusLabel.wordWrap = True
        self.drillingStatusLabel.setProperty("dentobotRole", "status")
        drilling_layout.addWidget(self.drillingStatusLabel)
        self.solveIkButton.clicked.connect(
            lambda checked=False: self._invoke("solve_ik")
        )
        self.planGoalButton.clicked.connect(
            lambda checked=False: self._invoke("plan_goal")
        )
        self.tcpDragEnabledCheckBox.toggled.connect(
            self._onTcpDragEnabledToggled
        )
        self.tcpKeyboardEnabledCheckBox.toggled.connect(
            lambda _checked=False: self._updateTcpCartesianControlState()
        )
        self.manualJogKeyboardEnabledCheckBox.toggled.connect(
            lambda _checked=False: self._updateManualJogKeyboardControlState()
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
        self.setupToolsButton.clicked.connect(self.showSetupToolsDialog)
        self.beginManualBaseReviewButton.clicked.connect(
            lambda checked=False: self._invoke("begin_manual_base_review")
        )
        self.allowSpindleGuideContactCheckBox.toggled.connect(
            lambda checked: self._invoke("set_spindle_guide_contact", bool(checked))
        )
        self.mouthBarrierOpacitySlider.valueChanged.connect(
            lambda value: self._invoke("set_mouth_barrier_opacity", float(value) / 100.0)
        )
        self.showTaskSpaceBoxCheckBox.toggled.connect(lambda _checked: self._invoke_task_space_box())
        self.taskSpaceBoxSideSpinBox.valueChanged.connect(lambda _value: self._invoke_task_space_box())
        self.taskSpaceBoxOpacitySlider.valueChanged.connect(lambda _value: self._invoke_task_space_box())
        self.devFastModeCheckBox.toggled.connect(
            lambda checked: self._invoke("set_dev_fast_mode", bool(checked))
        )
        self.depthPeelingCheckBox.toggled.connect(
            lambda checked: self._invoke("set_depth_peeling", bool(checked))
        )
        self.showMouthBarrierCheckBox.toggled.connect(
            lambda checked: self._invoke("set_show_mouth_barrier", bool(checked))
        )
        for owner, mirror in (
            (self.showMouthBarrierCheckBox, self.displayShowMouthBarrierCheckBox),
            (self.showTaskSpaceBoxCheckBox, self.displayShowTaskSpaceBoxCheckBox),
        ):
            mirror.toggled.connect(
                lambda checked, owner=owner: setattr(owner, "checked", bool(checked))
            )
            owner.toggled.connect(lambda _checked: self.syncPlanningAidMirrors())
        self.displayButton.clicked.connect(lambda _checked=False: self.syncPlanningAidMirrors())
        self.mouthBarrierEdgeModeComboBox.currentIndexChanged.connect(
            lambda index: self._invoke(
                "set_mouth_barrier_edge_mode",
                str(self.mouthBarrierEdgeModeComboBox.itemData(int(index)) or "gum_line"),
            )
        )
        self.searchBasePlacementButton.clicked.connect(
            lambda checked=False: self._invoke("search_base_placement")
        )
        self.cancelManualBaseReviewButton.clicked.connect(
            lambda checked=False: self._invoke("cancel_manual_base_review")
        )
        self.reconcileManualBaseStateButton.clicked.connect(
            lambda checked=False: self._invoke("reconcile_manual_base")
        )
        self.reviewTaskHomeButton.clicked.connect(
            lambda checked=False: self._invoke("review_task_home")
        )
        self.cancelTaskHomeReviewButton.clicked.connect(
            lambda checked=False: self._invoke("cancel_task_home_review")
        )
        self.acceptTaskHomeButton.clicked.connect(
            lambda checked=False: self._invoke("accept_task_home_review")
        )
        self.reconcileTaskHomeButton.clicked.connect(
            lambda checked=False: self._invoke("reconcile_task_home")
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
        self.diagnoseBaseButton.clicked.connect(
            lambda checked=False: self._invoke("diagnose_base")
        )
        self.resetManualJogDraftButton.clicked.connect(
            lambda checked=False: self._invoke("reset_manual_draft")
        )
        self.checkManualDraftStateButton.clicked.connect(
            lambda checked=False: self._invoke(
                "check_manual_draft_state", self.manualJogJointPositionsSi()
            )
        )
        self.reconcileManualJogButton.clicked.connect(
            lambda checked=False: self._invoke("reconcile_manual_jog")
        )
        self.guardedManualJogButton.clicked.connect(
            lambda checked=False: self._invoke(
                "guarded_manual_jog", self.manualJogJointPositionsSi()
            )
        )
        self.exportManualRecordButton.clicked.connect(
            lambda checked=False: self._invoke("export_manual_record")
        )
        self.importManualRecordButton.clicked.connect(
            lambda checked=False: self._invoke("import_manual_record")
        )
        self.clearManualRecordButton.clicked.connect(
            lambda checked=False: self._invoke("clear_manual_record")
        )
        self.manualSimulationRecordComboBox.currentIndexChanged.connect(
            self._onManualSimulationRecordChanged
        )
        self.manualSimulationEventList.currentRowChanged.connect(
            self._onManualSimulationEventChanged
        )
        self.previousManualSimulationEventButton.clicked.connect(
            lambda checked=False: self._stepManualSimulationEvent(-1)
        )
        self.nextManualSimulationEventButton.clicked.connect(
            lambda checked=False: self._stepManualSimulationEvent(1)
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
        self.previewControlGroup.visible = False
        self._updateTcpCartesianControlState()
        self._updateManualJogKeyboardControlState()
        self._connectManualJogKeyboardFocusUpdates()

    def configureStep63Workbench(
        self, parent, task_limits_group, workspace_group, navigate
    ) -> None:
        """Place existing 6.3 controls in focused views without changing owners."""

        self._step63Navigate = navigate
        self.workbenchGroup = qt.QGroupBox("6.3 — Workbench & Planning", parent)
        self.workbenchGroup.objectName = "DENTOBOTStep63WorkbenchGroupBox"
        layout = qt.QVBoxLayout(self.workbenchGroup)
        self.step63ContextLabel = qt.QLabel(
            "Base setup is owned by 6.1; Task Home is owned by 6.2. "
            "Changing either may stale workspace, task, and route evidence.",
            self.workbenchGroup,
        )
        self.step63ContextLabel.wordWrap = True
        self.step63ContextLabel.setProperty("dentobotRole", "status")
        layout.addWidget(self.step63ContextLabel)
        owner_actions = qt.QHBoxLayout()
        self.step63EditBaseButton = qt.QPushButton(
            "Edit Base in 6.1", self.workbenchGroup
        )
        self.step63ReviewHomeButton = qt.QPushButton(
            "Review Home in 6.2", self.workbenchGroup
        )
        owner_actions.addWidget(self.step63EditBaseButton)
        owner_actions.addWidget(self.step63ReviewHomeButton)
        layout.addLayout(owner_actions)

        self.step63TabWidget = qt.QTabWidget(self.workbenchGroup)
        self.step63TabWidget.objectName = "DENTOBOTStep63TabWidget"
        self.step63ManualPage = qt.QWidget(self.step63TabWidget)
        self.step63WorkspacePage = qt.QWidget(self.step63TabWidget)
        self.step63PlanPage = qt.QWidget(self.step63TabWidget)
        self.step63TabWidget.addTab(self.step63ManualPage, "Manual")
        self.step63TabWidget.addTab(self.step63WorkspacePage, "Workspace")
        self.step63TabWidget.addTab(self.step63PlanPage, "Plan")
        layout.addWidget(self.step63TabWidget)

        manual_layout = qt.QVBoxLayout(self.step63ManualPage)
        self.step63ManualTabWidget = qt.QTabWidget(self.step63ManualPage)
        self.step63ManualTabWidget.objectName = "DENTOBOTStep63ManualTabWidget"
        self.step63ManualTabWidget.addTab(self.manualJogGroup, "Joints")
        self.step63ManualTabWidget.addTab(self.goalGroup, "TCP")
        manual_layout.addWidget(self.step63ManualTabWidget)
        self.step63RecordsButton = qt.QPushButton(
            "Records & Replay…", self.step63ManualPage
        )
        manual_layout.addWidget(self.step63RecordsButton)

        workspace_layout = qt.QVBoxLayout(self.step63WorkspacePage)
        self.step63WorkspaceTabWidget = qt.QTabWidget(self.step63WorkspacePage)
        self.step63WorkspaceTabWidget.objectName = "DENTOBOTStep63WorkspaceTabWidget"
        self.step63WorkspaceTabWidget.addTab(workspace_group, "Samples")
        self.step63WorkspaceTabWidget.addTab(
            self.workspaceReviewGroup, "ROI & Assisted Limits"
        )
        self.step63WorkspaceTabWidget.addTab(task_limits_group, "Joint Limits")
        workspace_layout.addWidget(self.step63WorkspaceTabWidget)

        plan_layout = qt.QVBoxLayout(self.step63PlanPage)
        plan_layout.addWidget(self.confirmationGroup)
        self.step63PlanTabWidget = qt.QTabWidget(self.step63PlanPage)
        self.step63PlanTabWidget.objectName = "DENTOBOTStep63PlanTabWidget"
        self.step63PlanTabWidget.addTab(self.approachGroup, "Approach")
        self.step63PlanTabWidget.addTab(self.drillingGroup, "Drill")
        plan_layout.addWidget(self.step63PlanTabWidget)
        plan_tools = qt.QHBoxLayout()
        self.step63PlanningToolsButton = qt.QPushButton(
            "Planner Comparison…", self.step63PlanPage
        )
        self.step63AnatomyReviewButton = qt.QPushButton(
            "Anatomy Review…", self.step63PlanPage
        )
        plan_tools.addWidget(self.step63PlanningToolsButton)
        plan_tools.addWidget(self.step63AnatomyReviewButton)
        plan_layout.addLayout(plan_tools)

        self.returnFromBaseButton = qt.QPushButton(
            "Return to Workbench", self.visualizationGroup
        )
        self.returnFromHomeButton = qt.QPushButton(
            "Return to Workbench", self.homeGroup
        )
        self.visualizationGroup.layout().addWidget(self.returnFromBaseButton)
        self.homeGroup.layout().addWidget(self.returnFromHomeButton)
        self.returnFromBaseButton.hide()
        self.returnFromHomeButton.hide()

        self.step63EditBaseButton.clicked.connect(
            lambda checked=False: self._openStep63Owner(1)
        )
        self.step63ReviewHomeButton.clicked.connect(
            lambda checked=False: self._openStep63Owner(2)
        )
        self.returnFromBaseButton.clicked.connect(
            lambda checked=False: self._returnToStep63()
        )
        self.returnFromHomeButton.clicked.connect(
            lambda checked=False: self._returnToStep63()
        )
        self.step63RecordsButton.clicked.connect(self.showManualRecordsDialog)
        self.step63PlanningToolsButton.clicked.connect(self.showPlanningToolsDialog)
        self.step63AnatomyReviewButton.clicked.connect(self.showAnatomyReviewDialog)
        self.step63TabWidget.currentChanged.connect(self._onStep63ViewChanged)
        self.step63ManualTabWidget.currentChanged.connect(
            self._onStep63ManualViewChanged
        )
        for group in (
            self.manualJogGroup,
            self.goalGroup,
            workspace_group,
            self.workspaceReviewGroup,
            task_limits_group,
            self.confirmationGroup,
            self.approachGroup,
            self.drillingGroup,
        ):
            group.show()
        self.manualHistoryGroup.hide()
        self.anatomyReviewGroup.hide()
        for widget in (
            self.comparePlannersButton,
            self.cancelPlannerComparisonButton,
            self.showPlannerComparisonButton,
            self.plannerComparisonProgressLabel,
        ):
            widget.hide()
        self.workbenchGroup.hide()

    def _onStep63ViewChanged(self, index: int) -> None:
        if int(index) != 0:
            self._disableTcpDragForSubstepChange()
        self._updateManualJogKeyboardControlState()
        self._updateTcpCartesianControlState()

    def _onStep63ManualViewChanged(self, index: int) -> None:
        if int(index) != 1:
            self._disableTcpDragForSubstepChange()
        self._updateManualJogKeyboardControlState()
        self._updateTcpCartesianControlState()

    def _openStep63Owner(self, substep: int) -> None:
        if self._activeSubstep != 3 or not callable(self._step63Navigate):
            return
        self._step63ReturnTab = int(self.step63TabWidget.currentIndex)
        self.returnFromBaseButton.visible = substep == 1
        self.returnFromHomeButton.visible = substep == 2
        self._step63Navigate(substep)

    def _returnToStep63(self) -> None:
        if not callable(self._step63Navigate):
            return
        self.returnFromBaseButton.hide()
        self.returnFromHomeButton.hide()
        self._step63Navigate(3)
        self.step63TabWidget.currentIndex = self._step63ReturnTab

    def showManualRecordsDialog(self, checked: bool = False) -> None:
        del checked
        if self._activeSubstep != 3:
            return
        if self._manualRecordsDialog is None:
            dialog = qt.QDialog(self.workbenchGroup)
            dialog.windowTitle = "DENTOBOT Records & Replay"
            dialog.setModal(False)
            qt.QVBoxLayout(dialog).addWidget(self.manualHistoryGroup)
            self._manualRecordsDialog = dialog
        self.manualHistoryGroup.show()
        self._manualRecordsDialog.show()
        self._manualRecordsDialog.raise_()

    def showPlanningToolsDialog(self, checked: bool = False) -> None:
        del checked
        if self._activeSubstep != 3:
            return
        if self._planningToolsDialog is None:
            dialog = qt.QDialog(self.workbenchGroup)
            dialog.windowTitle = "DENTOBOT Planner Comparison"
            dialog.setModal(False)
            layout = qt.QVBoxLayout(dialog)
            for widget in (
                self.comparePlannersButton,
                self.cancelPlannerComparisonButton,
                self.showPlannerComparisonButton,
                self.plannerComparisonProgressLabel,
            ):
                layout.addWidget(widget)
            self._planningToolsDialog = dialog
        for widget in (
            self.comparePlannersButton,
            self.cancelPlannerComparisonButton,
            self.showPlannerComparisonButton,
            self.plannerComparisonProgressLabel,
        ):
            widget.show()
        self._planningToolsDialog.show()
        self._planningToolsDialog.raise_()

    def showAnatomyReviewDialog(self, checked: bool = False) -> None:
        del checked
        if self._activeSubstep != 3:
            return
        if self._anatomyReviewDialog is None:
            dialog = qt.QDialog(self.workbenchGroup)
            dialog.windowTitle = "DENTOBOT Anatomy Review"
            dialog.setModal(False)
            qt.QVBoxLayout(dialog).addWidget(self.anatomyReviewGroup)
            self._anatomyReviewDialog = dialog
        self.anatomyReviewGroup.show()
        self._anatomyReviewDialog.show()
        self._anatomyReviewDialog.raise_()

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

    def _invoke(self, name: str, *args) -> object:
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
            return False
        callback = self._callbacks.get(name)
        if callback:
            return callback(*args)
        return False

    def _setupTcpKeyboardShortcuts(self) -> None:
        for key, translation_axis, rotation_axis, direction in self.TCP_KEY_BINDINGS:
            shortcut = qt.QShortcut(qt.QKeySequence(key), self.goalGroup)
            shortcut.objectName = f"DENTOBOTTcpNudgeShortcut{key.replace('+', '')}"
            shortcut.context = qt.Qt.WidgetWithChildrenShortcut
            shortcut.autoRepeat = False
            shortcut.enabled = False
            shortcut.activated.connect(
                lambda ta=translation_axis, ra=rotation_axis, d=direction:
                    self._onTcpKeyboardNudge(ta, ra, d)
            )
            self._tcpKeyboardShortcuts.append(shortcut)

    def _setupManualJogKeyboardShortcuts(self) -> None:
        for key, joint_index, direction in self.MANUAL_JOG_KEY_BINDINGS:
            shortcut = qt.QShortcut(
                qt.QKeySequence(key), self.manualJogGroup
            )
            shortcut.objectName = f"DENTOBOTManualJogNudgeShortcut{key}"
            shortcut.context = qt.Qt.WidgetWithChildrenShortcut
            shortcut.autoRepeat = False
            shortcut.enabled = False
            shortcut.activated.connect(
                lambda index=joint_index, sign=direction:
                    self._onManualJogKeyboardNudge(index, sign)
            )
            self._manualJogKeyboardShortcuts.append(shortcut)

    def _connectManualJogKeyboardFocusUpdates(self) -> None:
        application = qt.QApplication.instance()
        if application is None:
            return
        slot = lambda *_args: self._updateManualJogKeyboardControlState()
        self._manualJogKeyboardFocusSlot = slot
        application.focusChanged.connect(slot)
        self.manualJogGroup.destroyed.connect(
            lambda *_args: application.focusChanged.disconnect(slot)
        )

    def _manualJogKeyboardControlsAllowed(self) -> bool:
        return bool(
            self._activeSubstep == 3
            and self.manualJogGroup.visible
            and self._manualJogAvailable
            and not self._manualJogBusy
            and not self.manualJogReconciliationRequired
        )

    def _updateManualJogKeyboardControlState(self) -> None:
        if not hasattr(self, "manualJogKeyboardEnabledCheckBox"):
            return
        allowed = self._manualJogKeyboardControlsAllowed()
        if not allowed:
            self.manualJogKeyboardEnabledCheckBox.blockSignals(True)
            self.manualJogKeyboardEnabledCheckBox.checked = False
            self.manualJogKeyboardEnabledCheckBox.blockSignals(False)
        self.manualJogKeyboardEnabledCheckBox.enabled = allowed
        self.manualJogKeyboardStepComboBox.enabled = allowed
        shortcuts_enabled = bool(
            allowed
            and self.manualJogKeyboardEnabledCheckBox.checked
            and not self._hasTcpTextEditorFocus()
        )
        for shortcut in self._manualJogKeyboardShortcuts:
            shortcut.enabled = shortcuts_enabled

    def _onManualJogKeyboardNudge(self, joint_index: int, direction: float) -> None:
        if (
            not self._manualJogKeyboardControlsAllowed()
            or not self.manualJogKeyboardEnabledCheckBox.checked
            or self._hasTcpTextEditorFocus()
        ):
            return
        if joint_index not in range(len(JOINT_NAMES)) or direction not in (
            -1.0,
            1.0,
        ):
            return
        try:
            degrees_step, millimeters_step = (
                self.manualJogKeyboardStepComboBox.currentData
            )
            step = float(
                degrees_step if joint_index in (0, 2, 4) else millimeters_step
            )
            control = self.manualJogJointControls[JOINT_NAMES[joint_index]][1]
            current = float(control.value)
        except (KeyError, TypeError, ValueError, OverflowError):
            return
        amount = float(direction) * step
        if not isfinite(amount) or amount == 0.0:
            return
        control.setValue(current + amount)

    def _tcpCartesianControlsAllowed(self) -> bool:
        return bool(
            self._activeSubstep == 3
            and self._taskHomeSetupMode == "connected"
            and self.goalGroup.visible
            and self._tcpDragEnabled
            and self.tcpDragEnabledCheckBox.checked
        )

    def _updateTcpCartesianControlState(self) -> None:
        active = bool(self._activeSubstep == 3)
        connected = self._taskHomeSetupMode == "connected"
        allowed = self._tcpCartesianControlsAllowed()
        self.tcpDragEnabledCheckBox.enabled = active and connected
        self.tcpKeyboardEnabledCheckBox.enabled = allowed
        self.solveIkButton.enabled = bool(self._tcpIkAvailable and allowed)
        for button in self.tcpCartesianNudgeButtons.values():
            button.enabled = allowed
        self.tcpTranslationStepMm.enabled = allowed
        self.tcpRotationStepDeg.enabled = allowed
        keyboard_allowed = bool(
            allowed and self.tcpKeyboardEnabledCheckBox.checked
        )
        for shortcut in self._tcpKeyboardShortcuts:
            shortcut.enabled = keyboard_allowed

    def _onTcpDragEnabledToggled(self, checked: bool) -> None:
        enabled = bool(checked)
        callback = self._callbacks.get("set_tcp_drag_enabled")
        if enabled and not (
            self._taskHomeSetupMode == "connected"
            and self._activeSubstep == 3
            and self.goalGroup.visible
            and callable(callback)
        ):
            self.tcpDragEnabledCheckBox.blockSignals(True)
            self.tcpDragEnabledCheckBox.checked = False
            self.tcpDragEnabledCheckBox.blockSignals(False)
            self._tcpDragEnabled = False
            self.runtimeStatusLabel.text = (
                "TCP drag enable is available only in visible Step 6.3 and requires "
                "the guarded native callback."
            )
            self.runtimeStatusLabel.setProperty("dentobotState", "blocked")
            self._updateTcpCartesianControlState()
            return
        if enabled == self._tcpDragEnabled:
            self._updateTcpCartesianControlState()
            return
        if enabled:
            acknowledged = bool(self._invoke("set_tcp_drag_enabled", True))
            if not acknowledged:
                self._tcpDragEnabled = False
                self.tcpDragEnabledCheckBox.blockSignals(True)
                self.tcpDragEnabledCheckBox.checked = False
                self.tcpDragEnabledCheckBox.blockSignals(False)
                self._setTcpKeyboardChecked(False)
                self._invoke("set_tcp_drag_enabled", False)
                self.runtimeStatusLabel.text = (
                    "TCP drag remains disabled because the native MoveIt interface "
                    "did not acknowledge activation."
                )
                self.runtimeStatusLabel.setProperty("dentobotState", "blocked")
                self._updateTcpCartesianControlState()
                return
            self._tcpDragEnabled = True
        else:
            was_enabled = self._tcpDragEnabled
            self._tcpDragEnabled = False
            self._setTcpKeyboardChecked(False)
            if was_enabled:
                self._invoke("set_tcp_drag_enabled", False)
        self._updateTcpCartesianControlState()

    def _setTcpKeyboardChecked(self, checked: bool) -> None:
        self.tcpKeyboardEnabledCheckBox.blockSignals(True)
        self.tcpKeyboardEnabledCheckBox.checked = bool(checked)
        self.tcpKeyboardEnabledCheckBox.blockSignals(False)

    def _disableTcpDragForSubstepChange(self) -> None:
        if not self._tcpDragEnabled:
            return
        self._tcpDragEnabled = False
        self.tcpDragEnabledCheckBox.blockSignals(True)
        self.tcpDragEnabledCheckBox.checked = False
        self.tcpDragEnabledCheckBox.blockSignals(False)
        self._setTcpKeyboardChecked(False)
        callback = self._callbacks.get("set_tcp_drag_enabled")
        if callable(callback):
            callback(False)
        self._updateTcpCartesianControlState()

    def _hasTcpTextEditorFocus(self) -> bool:
        focus_widget = qt.QApplication.focusWidget()
        return bool(
            focus_widget
            and any(
                focus_widget.inherits(class_name)
                for class_name in (
                    "QLineEdit",
                    "QAbstractSpinBox",
                    "QTextEdit",
                    "QPlainTextEdit",
                )
            )
        )

    def _onTcpCartesianNudge(
        self,
        translation_axis: int | None,
        rotation_axis: int | None,
        direction: float,
        *,
        source: str = "button",
    ) -> None:
        if not self._tcpCartesianControlsAllowed():
            return
        if source not in {"button", "keyboard"}:
            return
        if source == "keyboard" and (
            not self.tcpKeyboardEnabledCheckBox.checked
            or self._hasTcpTextEditorFocus()
        ):
            return
        if (translation_axis is None) == (rotation_axis is None):
            return
        axis = translation_axis if translation_axis is not None else rotation_axis
        if not isinstance(axis, int) or axis not in (0, 1, 2):
            return
        try:
            step = float(
                self.tcpTranslationStepMm.value
                if translation_axis is not None
                else self.tcpRotationStepDeg.value
            )
            amount = float(direction) * step
        except (TypeError, ValueError, OverflowError):
            return
        if not isfinite(amount) or amount == 0.0:
            return
        translation = [0.0, 0.0, 0.0]
        rotation = [0.0, 0.0, 0.0]
        if translation_axis is not None:
            translation[axis] = amount
        else:
            rotation[axis] = amount
        self._invoke(
            "nudge_tcp_goal",
            {
                "translation_ras_mm": translation,
                "rotation_local_rpy_deg": rotation,
                "source": source,
            },
        )

    def _onTcpKeyboardNudge(
        self,
        translation_axis: int | None,
        rotation_axis: int | None,
        direction: float,
    ) -> None:
        self._onTcpCartesianNudge(
            translation_axis, rotation_axis, direction, source="keyboard"
        )

    def stageTcpIkSolution(self, payload) -> bool:
        """Stage a complete current TCP IK solution as a display-only J1–J5 draft."""

        def reject(reason: str) -> bool:
            self._tcpIkStageFailureText = str(reason)
            current = self._formatManualJogDisplayValues(
                self._manualJogDisplayValues
            )
            self.manualJogDraftStateLabel.text = (
                f"Draft state: {current} — retained; TCP IK solution not staged: "
                f"{reason}"
            )
            self._setManualJogStatus(
                "error", f"TCP IK result rejected; draft retained. {reason}"
            )
            return False

        if not isinstance(payload, Mapping):
            return reject("joint solution payload is unavailable or not a mapping")
        if set(payload) != set(JOINT_NAMES):
            return reject("joint solution must contain exactly the five canonical J1–J5 values")
        try:
            positions = {joint: float(payload[joint]) for joint in JOINT_NAMES}
        except (TypeError, ValueError, OverflowError):
            return reject("joint solution contains a non-numeric value")
        if not all(isfinite(value) for value in positions.values()):
            return reject("joint solution contains a non-finite value")
        if (
            not self._manualJogLimits
            or not self._manualJogMechanicalLimits
        ):
            return reject("manual J1–J5 draft controls or mechanical limits are unavailable")
        display = (
            degrees(positions[JOINT_NAMES[0]]),
            positions[JOINT_NAMES[1]] * 1000.0,
            degrees(positions[JOINT_NAMES[2]]),
            positions[JOINT_NAMES[3]] * 1000.0,
            degrees(positions[JOINT_NAMES[4]]),
        )
        for index, value in enumerate(display):
            minimum, maximum = self._manualJogMechanicalLimits[index]
            if not isfinite(value) or value < minimum or value > maximum:
                return reject(
                    f"J{index + 1} IK solution is outside mechanical limits; draft retained"
                )
        self._tcpIkStageFailureText = ""
        self._setManualJogDraftValues(display, notify=True)
        self.manualJogDraftStateLabel.text = (
            "Draft state: "
            + self._formatManualJogDisplayValues(self._manualJogDisplayValues)
            + " — TCP IK solution staged for review; not accepted robot state."
        )
        self._setManualJogStatus(
            "unknown",
            "Guard status: unknown for the staged TCP IK draft — run Check Draft State "
            "or request Guarded Jog.",
        )
        return True

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
        mechanical_ranges = []
        mechanical_limits_valid = True
        command_limits_valid = True
        for mechanical_pair, reviewed_pair in zip(mechanical, reviewed, strict=True):
            mechanical_valid = bool(
                all(isfinite(bound) for bound in mechanical_pair)
                and mechanical_pair[1] >= mechanical_pair[0]
            )
            reviewed_valid = bool(
                all(isfinite(bound) for bound in reviewed_pair)
                and reviewed_pair[1] >= reviewed_pair[0]
            )
            if not mechanical_valid:
                mechanical_limits_valid = False
                command_limits_valid = False
                mechanical_range = (0.0, 0.0)
                minimum = maximum = 0.0
            elif not reviewed_valid:
                command_limits_valid = False
                mechanical_range = mechanical_pair
                minimum = maximum = mechanical_pair[0]
            else:
                mechanical_range = mechanical_pair
                minimum = max(mechanical_pair[0], reviewed_pair[0])
                maximum = min(mechanical_pair[1], reviewed_pair[1])
                if maximum < minimum:
                    command_limits_valid = False
                    minimum = maximum = mechanical_pair[0]
            allowed.append((minimum, maximum))
            mechanical_ranges.append(mechanical_range)
        limits = (tuple(allowed), reviewed)
        mechanical_ranges = tuple(mechanical_ranges)
        slider_ranges = tuple(
            mechanical_ranges
            if self._taskHomeSetupMode == "offline"
            else allowed
        )
        if (
            self._manualJogLimits == limits
            and getattr(self, "_manualJogMechanicalLimits", None)
            == mechanical_ranges
            and self._manualJogSliderRanges == slider_ranges
        ):
            return
        self._manualJogLimits = limits
        self._manualJogSliderRanges = slider_ranges
        self._manualJogMechanicalLimits = mechanical_ranges
        self._manualJogLimitsValid = mechanical_limits_valid
        self._manualJogCommandLimitsValid = command_limits_valid
        for index, joint in enumerate(JOINT_NAMES):
            slider, value, _label = self.manualJogJointControls[joint]
            slider_minimum, slider_maximum = slider_ranges[index]
            mechanical_minimum, mechanical_maximum = mechanical_ranges[index]
            slider.blockSignals(True)
            value.blockSignals(True)
            value.setRange(mechanical_minimum, mechanical_maximum)
            slider.enabled = bool(
                slider_maximum > slider_minimum
                and self._manualJogAvailable
                and not self._manualJogBusy
            )
            value.enabled = bool(
                self._manualJogAvailable and not self._manualJogBusy
            )
            value.blockSignals(False)
            slider.blockSignals(False)
        if self._manualJogDraftInitialized:
            self._setManualJogDraftValues(self._manualJogDisplayValues, notify=True)
        else:
            self.setManualJogAvailability(
                self._manualJogAvailable, self._manualJogGuardContextAvailable
            )

    def _updateManualJogResetLabel(self) -> None:
        controls = getattr(self, "manualJogControlsGroup", None)
        if controls is not None:
            controls.title = (
                "Home configuration draft (J1–J5)"
                if getattr(self, "_manualJogControlsInHomeGroup", False)
                else "Joint draft (J1–J5)"
            )
        button = getattr(self, "resetManualJogDraftButton", None)
        if button is None:
            return
        if self._taskHomeSetupMode == "connected":
            home_configuration = bool(
                getattr(self, "_manualJogControlsInHomeGroup", False)
                and self._taskHomeConfigurationReady
                and self._taskHomeConfiguredJointPositionsSi
            )
            if home_configuration:
                button.text = "Reset Draft to Saved Home Configuration"
            elif self._manualJogAcceptedJointPositionsSi:
                button.text = "Reset Draft to Accepted Current State"
            else:
                button.text = "Reset Draft Unavailable"
        elif self._taskHomeSetupMode == "offline":
            button.text = (
                "Reset Draft to Saved Home Configuration"
                if self._taskHomeConfigurationReady
                and self._taskHomeConfiguredJointPositionsSi
                else "Reset Draft to Local Robot Pose"
                if self._manualJogLocalJointPositionsSi
                else "Reset Draft Unavailable"
            )
        else:
            button.text = "Reset Draft Unavailable"

    def _updateManualJogJointPresentation(self) -> None:
        rows = getattr(self, "_manualJogJointPresentation", {})
        if not rows:
            return
        units = ("deg", "mm", "deg", "mm", "deg")
        mode = getattr(self, "_taskHomeSetupMode", "unknown")
        busy = bool(getattr(self, "_manualJogBusy", False))
        uncertain = bool(getattr(self, "manualJogReconciliationRequired", False))
        limits = getattr(self, "_manualJogLimits", None)
        allowed, reviewed = (
            limits if isinstance(limits, (tuple, list)) and len(limits) == 2
            else ((), ())
        )
        mechanical = getattr(self, "_manualJogMechanicalLimits", None)
        mechanical_valid = bool(
            limits and mechanical and getattr(self, "_manualJogLimitsValid", False)
        )
        command_valid = bool(getattr(self, "_manualJogCommandLimitsValid", False))
        slider_ranges = getattr(self, "_manualJogSliderRanges", ())
        accepted = getattr(self, "_manualJogAcceptedJointPositionsSi", None)
        accepted_display = None
        if (
            mode == "connected" and not busy and not uncertain
            and isinstance(accepted, Mapping) and set(accepted) == set(JOINT_NAMES)
        ):
            try:
                values = tuple(float(accepted[joint]) for joint in JOINT_NAMES)
                accepted_display = tuple(
                    degrees(value) if index in (0, 2, 4) else value * 1000.0
                    for index, value in enumerate(values)
                )
                if not all(isfinite(value) for value in (*values, *accepted_display)):
                    accepted_display = None
            except (TypeError, ValueError, OverflowError):
                pass

        def bounds(source, index, valid=True):
            if not valid or not isinstance(source, (tuple, list)):
                return None
            try:
                minimum, maximum = map(float, source[index])
            except (IndexError, KeyError, TypeError, ValueError, OverflowError):
                return None
            return (
                (minimum, maximum)
                if isfinite(minimum) and isfinite(maximum) and maximum >= minimum
                else None
            )

        def shown(pair, unit):
            return f"{pair[0]:.2f} to {pair[1]:.2f} {unit}" if pair else "--"

        controls = getattr(self, "manualJogJointControls", {})
        for index, joint in enumerate(JOINT_NAMES):
            labels = rows.get(joint, {})
            if not isinstance(labels, Mapping):
                continue
            unit = units[index]
            draft = None
            if getattr(self, "_manualJogDraftInitialized", False):
                try:
                    draft = float(self._manualJogDisplayValues[index])
                    if not isfinite(draft):
                        draft = None
                except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
                    pass
            if draft is None:
                draft_unavailable = (
                    "Draft unavailable",
                    "Numeric draft has not been initialized or is unavailable.",
                )
            else:
                draft_unavailable = None

            unavailable = (
                ("Accepted — pending", "Accepted/delta pending during guarded jog.")
                if busy else
                ("Accepted — uncertain", "Accepted/delta withheld until reconciliation.")
                if uncertain else
                ("Accepted — offline", "Accepted/delta unavailable while offline.")
                if mode == "offline" else
                ("Accepted unavailable", "Setup mode is unknown.")
                if mode != "connected" else
                ("Accepted unavailable", "Current accepted state is unavailable or invalid.")
                if accepted_display is None else
                draft_unavailable
            )
            if unavailable:
                comparison_text, comparison_tooltip = unavailable
            else:
                accepted_value = accepted_display[index]
                delta = draft - accepted_value
                comparison_text = (
                    f"Accepted {accepted_value:.2f} {unit} · Δ {delta:+.2f} {unit}"
                    if isfinite(delta)
                    else f"Accepted {accepted_value:.2f} {unit} · Δ unavailable"
                )
                comparison_tooltip = (
                    comparison_text if isfinite(delta)
                    else "Accepted/draft difference is non-finite."
                )
            comparison = labels.get("comparison")
            if comparison is not None:
                comparison.text = comparison_text
                comparison.setToolTip(comparison_tooltip)

            mechanical_pair = bounds(mechanical, index, mechanical_valid)
            reviewed_pair = bounds(reviewed, index, bool(limits))
            allowed_pair = bounds(allowed, index, command_valid)
            slider_valid = bool(
                mechanical_valid and mode in {"offline", "connected"}
                and (mode == "offline" or command_valid)
            )
            slider_pair = bounds(slider_ranges, index, slider_valid)
            for key, text in (
                ("lower", f"{slider_pair[0]:.2f} {unit}" if slider_pair else "--"),
                ("upper", f"{slider_pair[1]:.2f} {unit}" if slider_pair else "--"),
            ):
                label = labels.get(key)
                if label is not None:
                    label.text = text
                    label.setToolTip(
                        f"Slider {'minimum' if key == 'lower' else 'maximum'}: {text}"
                    )

            if slider_pair is None:
                notice_text = "Slider range unavailable; limits unavailable."
                if mechanical_valid and mode not in {"offline", "connected"}:
                    notice_text = "Slider range unavailable; setup mode unknown."
                elif mechanical_valid and mode == "connected" and not command_valid:
                    notice_text = "Slider range unavailable; reviewed limits invalid."
                elif mechanical_valid:
                    notice_text = "Slider range unavailable."
            elif draft is not None and not slider_pair[0] <= draft <= slider_pair[1]:
                notice_text = "Outside slider range; draft retained."
            else:
                notice_text = ""
            notice = labels.get("notice")
            if notice is not None:
                notice.text = notice_text
                notice.setToolTip(notice_text)
                notice.setVisible(bool(notice_text))

            details_text = (
                f"J{index + 1} — Mechanical range: {shown(mechanical_pair, unit)}\n"
                f"Reviewed guard limits: {shown(reviewed_pair, unit)}\n"
                f"Connected command allowed: {shown(allowed_pair, unit)}\n"
                f"Slider range: {shown(slider_pair, unit)}"
            )
            details = labels.get("details")
            if details is not None:
                details.text = details_text
                details.setToolTip(details_text)
            control = controls.get(joint) if isinstance(controls, Mapping) else None
            if isinstance(control, (tuple, list)) and len(control) == 3:
                control[2].toolTip = details_text
        sync_home = getattr(self, "_syncTaskHomeJointEditor", None)
        if callable(sync_home):
            sync_home()

    def setManualJogAcceptedState(self, positions_si, *, preserve_draft=False) -> None:
        try:
            values = {joint: float(positions_si[joint]) for joint in JOINT_NAMES}
        except (KeyError, TypeError, ValueError, OverflowError):
            values = {}
        if set(values) != set(JOINT_NAMES) or not all(
            isfinite(value) for value in values.values()
        ):
            self._manualJogAcceptedJointPositionsSi = None
            self.manualJogAcceptedStateLabel.text = (
                "Current accepted robot state: unavailable."
            )
            self.taskHomeCurrentStateLabel.text = (
                "Current accepted five-joint state: unavailable."
            )
            self._updateManualJogJointPresentation()
            return
        self._manualJogAcceptedJointPositionsSi = values
        self._manualJogLocalJointPositionsSi = dict(values)
        self._updateManualJogResetLabel()
        display = (
            degrees(values[JOINT_NAMES[0]]),
            values[JOINT_NAMES[1]] * 1000.0,
            degrees(values[JOINT_NAMES[2]]),
            values[JOINT_NAMES[3]] * 1000.0,
            degrees(values[JOINT_NAMES[4]]),
        )
        self.manualJogAcceptedStateLabel.text = (
            "Current accepted robot state: "
            + self._formatManualJogDisplayValues(display)
        )
        self.taskHomeCurrentStateLabel.text = (
            "Current accepted robot J1–J5 (five-DOF arm): "
            + self._formatManualJogDisplayValues(display)
        )
        if (
            not preserve_draft
            and not self._manualJogDraftInitialized
            and self._manualJogLimitsValid
        ):
            self._setManualJogDraftValues(display, notify=False)
        self._updateManualJogJointPresentation()

    def setManualJogLocalJointPositions(self, positions_si) -> None:
        """Update the visible local robot pose without treating it as accepted state."""
        try:
            values = {joint: float(positions_si[joint]) for joint in JOINT_NAMES}
        except (KeyError, TypeError, ValueError, OverflowError):
            values = {}
        if set(values) != set(JOINT_NAMES) or not all(
            isfinite(value) for value in values.values()
        ):
            self._manualJogLocalJointPositionsSi = None
        else:
            self._manualJogLocalJointPositionsSi = values
            display = (
                degrees(values[JOINT_NAMES[0]]),
                values[JOINT_NAMES[1]] * 1000.0,
                degrees(values[JOINT_NAMES[2]]),
                values[JOINT_NAMES[3]] * 1000.0,
                degrees(values[JOINT_NAMES[4]]),
            )
            if (
                not self._manualJogDraftInitialized
                and self._manualJogLimitsValid
            ):
                self._setManualJogDraftValues(display, notify=False)
        self._updateManualJogResetLabel()
        self._manualJogAcceptedJointPositionsSi = None
        self.manualJogAcceptedStateLabel.text = (
            "Accepted robot state: unavailable while offline."
        )
        self.taskHomeCurrentStateLabel.text = (
            "Current accepted five-joint state: unavailable while offline."
        )
        self._updateManualJogJointPresentation()

    def setManualTaskHomeReviewResult(self, result) -> None:
        details = getattr(result, "details", None)
        if not isinstance(details, Mapping):
            details = {}
        staged = details.get("staged") is True
        identity_status = str(details.get("identityStatus") or "unknown")
        acceptance_status = str(details.get("acceptanceStatus") or "unknown")
        setup_mode = str(details.get("setupMode") or "unknown")
        if setup_mode not in {"offline", "connected"}:
            setup_mode = "unknown"
        configuration_ready = details.get("configurationReady") is True
        self._taskHomeRuntimeValidated = details.get("runtimeValidated") is True
        configured = details.get("configuredJointPositionsSi")
        self._taskHomeSetupMode = setup_mode
        self._taskHomeConfigurationReady = configuration_ready
        try:
            configured_values = {
                joint: float(configured[joint]) for joint in JOINT_NAMES
            }
        except (KeyError, TypeError, ValueError, OverflowError):
            configured_values = {}
        if set(configured_values) != set(JOINT_NAMES) or not all(
            isfinite(value) for value in configured_values.values()
        ):
            configured_values = None
        self._taskHomeConfiguredJointPositionsSi = configured_values
        if setup_mode != "connected":
            self._manualJogAcceptedJointPositionsSi = None
        self.acceptTaskHomeButton.text = {
            "offline": "Save Home Configuration",
            "connected": "Accept and Validate Task Home",
            "unknown": "Task Home Mode Unknown",
        }[setup_mode]
        self._updateManualJogResetLabel()

        def positions_text(label, positions):
            if (
                not isinstance(positions, Mapping)
                or set(positions) != set(JOINT_NAMES)
            ):
                return f"{label}: unavailable; five canonical joint values are required."
            try:
                values = {joint: float(positions[joint]) for joint in JOINT_NAMES}
            except (TypeError, ValueError, OverflowError):
                return f"{label}: unavailable; five canonical joint values are required."
            if not all(isfinite(value) for value in values.values()):
                return f"{label}: unavailable; five canonical joint values are required."
            display = (
                degrees(values[JOINT_NAMES[0]]),
                values[JOINT_NAMES[1]] * 1000.0,
                degrees(values[JOINT_NAMES[2]]),
                values[JOINT_NAMES[3]] * 1000.0,
                degrees(values[JOINT_NAMES[4]]),
            )
            return (
                f"{label} (five-DOF arm): "
                + self._formatManualJogDisplayValues(display)
            )

        accepted = details.get("acceptedJointPositionsSi")
        candidate = details.get("candidateJointPositionsSi")
        if setup_mode == "connected":
            self.taskHomeCurrentStateLabel.text = positions_text(
                "Current accepted robot J1–J5", accepted
            )
        elif setup_mode == "offline":
            self.taskHomeCurrentStateLabel.text = (
                "Current accepted robot J1–J5: unavailable while offline; "
                "saved configuration is not live-validated."
            )
            accepted_label = getattr(self, "manualJogAcceptedStateLabel", None)
            if accepted_label is not None:
                accepted_label.text = "Accepted robot state: unavailable while offline."
        else:
            self.taskHomeCurrentStateLabel.text = (
                "Current accepted robot J1–J5: unavailable; setup mode is unknown."
            )
            self._manualJogAcceptedJointPositionsSi = None
            accepted_label = getattr(self, "manualJogAcceptedStateLabel", None)
            if accepted_label is not None:
                accepted_label.text = (
                    "Accepted robot state: unavailable while setup mode is unknown."
                )
        self.taskHomeConfiguredStateLabel.text = (
            positions_text("Configured Home J1–J5", configured_values)
            if configuration_ready and configured_values
            else "Configured Home: saved vector unavailable."
            if configuration_ready
            else "Configured Home: not saved."
        )
        if setup_mode == "offline" and configuration_ready:
            self.taskHomeConfiguredStateLabel.text += (
                " Saved as configuration only; not live-validated."
            )
        self.taskHomeCandidateLabel.text = (
            positions_text("Staged Task Home candidate", candidate)
            if staged
            else "Staged Task Home candidate: none."
        )
        success = bool(getattr(result, "success", False))
        message = str(getattr(result, "message", "") or "").strip()
        status = (
            f"Home review: {acceptance_status}; identity: {identity_status}."
        )
        if message:
            status += " " + message
        failure = details.get("failureEvidence")
        if not success and failure:
            status += " Failure evidence: " + str(failure)
        elif not success and not message:
            status += " Review failed or is unavailable."
        uncertainty = details.get("acceptanceUncertainty")
        if uncertainty:
            status += " Acceptance uncertainty: " + str(uncertainty)

        if staged:
            try:
                matches = (
                    setup_mode == "connected"
                    and isinstance(accepted, Mapping)
                    and isinstance(candidate, Mapping)
                    and set(accepted) == set(JOINT_NAMES)
                    and set(candidate) == set(JOINT_NAMES)
                    and all(
                        isfinite(float(accepted[joint]))
                        and isfinite(float(candidate[joint]))
                        and abs(
                            float(accepted[joint]) - float(candidate[joint])
                        ) <= 1.0e-12
                        for joint in JOINT_NAMES
                    )
                )
            except (TypeError, ValueError, OverflowError):
                matches = False
            if setup_mode == "connected" and not matches:
                status += (
                    " Candidate differs from the current accepted robot state; "
                    "use Plan + Apply Home Draft, then accept and validate it. Home review sends no motion."
                )
        allowed_statuses = (
            {"review", "accepted", "configuration_saved"}
            if setup_mode == "offline"
            else {"review", "accepted"}
        )
        review_current = bool(
            success
            and identity_status == "current"
            and acceptance_status in allowed_statuses
        )
        if setup_mode == "offline":
            if configuration_ready:
                status += (
                    " Offline configuration is saved only; connect ROS/MoveIt in "
                    "6.1, then return to 6.2 to accept and validate the live Home."
                )
            else:
                status += (
                    " Offline setup stores a Home configuration only; connect "
                    "ROS/MoveIt in 6.1 to validate it live."
                )
        elif setup_mode == "unknown":
            status += " Setup mode is unknown; live state was not mirrored."
        self._taskHomeStatusBase = status
        self.taskHomeReviewStatusLabel.text = status
        self.taskHomeReviewStatusLabel.setProperty(
            "dentobotState",
            "ok" if review_current and (
                setup_mode == "connected"
                or (
                    setup_mode == "offline"
                    and acceptance_status == "configuration_saved"
                )
            ) else (
                "error" if acceptance_status == "rejected" else "blocked"
            ),
        )
        self.taskHomeReviewStatusLabel.style().unpolish(
            self.taskHomeReviewStatusLabel
        )
        self.taskHomeReviewStatusLabel.style().polish(
            self.taskHomeReviewStatusLabel
        )
        uncertain = bool(uncertainty) or (
            staged and acceptance_status == "unknown"
        )
        for name, visible in (
            ("reviewTaskHomeButton", not staged and not uncertain),
            ("cancelTaskHomeReviewButton", staged and not uncertain),
            ("acceptTaskHomeButton", staged and not uncertain),
            ("reconcileTaskHomeButton", uncertain),
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.visible = visible
        self._updateManualJogJointPresentation()

    def setTaskHomeActionBlockers(self, blockers, summary: str) -> None:
        """Show why Review / Accept / Plan + Apply are unavailable.

        ``blockers`` maps action -> tuple of reasons (empty when enabled);
        reasons go into each button's tooltip and ``summary`` under the status.
        """

        buttons = {
            "review": self.reviewTaskHomeButton,
            "accept": self.acceptTaskHomeButton,
            "apply": self.applyTaskHomeButton,
        }
        base_tips = self.__dict__.setdefault("_taskHomeButtonBaseTips", {})
        for action, button in buttons.items():
            base_tips.setdefault(action, str(button.toolTip))
            reasons = blockers.get(action) or ()
            button.toolTip = base_tips[action] + (
                "\n\nUnavailable: " + " ".join(reasons) if reasons else ""
            )
        base = getattr(self, "_taskHomeStatusBase", None)
        if base is None:
            base = str(self.taskHomeReviewStatusLabel.text)
        self.taskHomeReviewStatusLabel.text = base + ("\n" + summary if summary else "")

    def setManualJogAvailability(
        self, draft_available: bool, jog_available: bool
    ) -> None:
        limits_available = bool(
            self._manualJogMechanicalLimits and self._manualJogLimitsValid
        )
        mode_available = self._taskHomeSetupMode in {"offline", "connected"}
        offline = self._taskHomeSetupMode == "offline"
        connected = self._taskHomeSetupMode == "connected"
        self._manualJogAvailable = bool(
            draft_available and limits_available and mode_available
        )
        self._manualJogGuardContextAvailable = bool(jog_available)
        violations = []
        if self._manualJogAvailable:
            reviewed = self._manualJogLimits[1]
            for index, joint in enumerate(JOINT_NAMES):
                label = ("J1", "J2", "J3", "J4", "J5")[index]
                unit = ("deg", "mm", "deg", "mm", "deg")[index]
                value = float(self._manualJogDisplayValues[index])
                mechanical_minimum, mechanical_maximum = (
                    self._manualJogMechanicalLimits[index]
                )
                reviewed_minimum, reviewed_maximum = reviewed[index]
                if not isfinite(value):
                    violations.append(f"{label}: numeric draft is unavailable")
                elif value < mechanical_minimum:
                    violations.append(
                        f"{label} {value:.2f} {unit} is below mechanical minimum "
                        f"{mechanical_minimum:.2f} {unit}"
                    )
                elif value > mechanical_maximum:
                    violations.append(
                        f"{label} {value:.2f} {unit} exceeds mechanical maximum "
                        f"{mechanical_maximum:.2f} {unit}"
                    )
                elif not offline and (
                    not all(
                        isfinite(bound)
                        for bound in (reviewed_minimum, reviewed_maximum)
                    )
                    or reviewed_maximum < reviewed_minimum
                ):
                    violations.append(
                        f"{label}: reviewed task limits are unavailable or invalid"
                    )
                elif not offline and value < reviewed_minimum:
                    violations.append(
                        f"{label} {value:.2f} {unit} is below reviewed task minimum "
                        f"{reviewed_minimum:.2f} {unit}"
                    )
                elif not offline and value > reviewed_maximum:
                    violations.append(
                        f"{label} {value:.2f} {unit} exceeds reviewed task maximum "
                        f"{reviewed_maximum:.2f} {unit}"
                    )
        self._manualJogLimitViolations = tuple(violations)
        self._manualJogDraftWithinCommandLimits = bool(
            self._manualJogAvailable
            and (offline or self._manualJogCommandLimitsValid)
            and not violations
        )
        if not self._manualJogAvailable:
            limit_message = "Draft limits: unavailable."
        elif offline and self._manualJogDraftWithinCommandLimits:
            limit_message = (
                "Home configuration is within mechanical limits. Reviewed guard "
                "limits apply only to connected jog commands."
            )
        elif offline and violations:
            limit_message = (
                "Home configuration mechanical-limit violation: "
                + "; ".join(violations)
                + ". Edit within mechanical limits to save."
            )
        elif self._manualJogDraftWithinCommandLimits:
            limit_message = "Draft limits: within mechanical and reviewed task limits."
        elif violations:
            limit_message = (
                "Draft limit violation: "
                + "; ".join(violations)
                + ". Guarded Jog is disabled; Check Draft State remains available."
            )
        else:
            limit_message = (
                "Draft limits: reviewed task limits do not form a valid command range "
                "within the mechanical bounds. Guarded Jog is disabled; Check Draft "
                "State remains available."
            )
        self.manualJogDraftLimitLabel.text = limit_message
        self.manualJogDraftLimitLabel.setProperty(
            "dentobotState",
            "ok" if self._manualJogDraftWithinCommandLimits else "blocked",
        )
        self.manualJogDraftLimitLabel.style().unpolish(self.manualJogDraftLimitLabel)
        self.manualJogDraftLimitLabel.style().polish(self.manualJogDraftLimitLabel)
        self._manualJogGuardAvailable = bool(
            connected
            and self._manualJogAvailable
            and self._manualJogGuardContextAvailable
            and self._manualJogCommandLimitsValid
            and self._manualJogDraftWithinCommandLimits
        )
        for joint, (slider, value, _label) in self.manualJogJointControls.items():
            index = JOINT_NAMES.index(joint)
            minimum, maximum = (
                self._manualJogSliderRanges[index]
                if index < len(self._manualJogSliderRanges)
                else (0.0, 0.0)
            )
            slider.enabled = bool(
                self._manualJogAvailable
                and maximum > minimum
                and not self._manualJogBusy
            )
            value.enabled = self._manualJogAvailable and not self._manualJogBusy
        reset_state_available = bool(
            connected and self._manualJogAcceptedJointPositionsSi
        )
        saved_home_available = bool(
            self._taskHomeConfigurationReady
            and self._taskHomeConfiguredJointPositionsSi
        )
        in_home_group = bool(
            getattr(self, "_manualJogControlsInHomeGroup", False)
        )
        if offline:
            reset_state_available = bool(
                saved_home_available or self._manualJogLocalJointPositionsSi
            )
        elif connected and in_home_group and saved_home_available:
            reset_state_available = True
        self.resetManualJogDraftButton.enabled = bool(
            self._manualJogAvailable
            and reset_state_available
            and not self._manualJogBusy
        )
        self.guardedManualJogButton.enabled = bool(
            self._manualJogGuardAvailable
            and not self._manualJogBusy
            and not self.manualJogReconciliationRequired
        )
        self.checkManualDraftStateButton.enabled = bool(
            connected and self._manualJogAvailable and not self._manualJogBusy
        )
        self.reconcileManualJogButton.enabled = bool(
            connected
            and self._manualJogAvailable
            and self.manualJogReconciliationRequired
            and not self._manualJogBusy
        )
        self._updateManualJogKeyboardControlState()
        self._updateManualJogJointPresentation()


    def setManualJogLimitsUnavailable(self, message: str) -> None:
        self._manualJogLimits = {}
        self._manualJogMechanicalLimits = None
        self._manualJogLimitsValid = False
        self._manualJogCommandLimitsValid = False
        self.setManualJogAvailability(False, False)
        self._setManualJogStatus(
            "blocked",
            "Manual jog unavailable because mechanical URDF limits could not be read: "
            + str(message),
        )

    def setManualJogRequestPending(self) -> None:
        self._manualJogBusy = True
        self.setManualJogAvailability(
            self._manualJogAvailable, self._manualJogGuardContextAvailable
        )
        self._setManualJogStatus(
            "pending", "Guard status: pending — waiting for the simulation guard."
        )

    def setManualJogRequestComplete(self) -> None:
        self._manualJogBusy = False
        self.setManualJogAvailability(
            self._manualJogAvailable, self._manualJogGuardContextAvailable
        )

    def setManualJogStatus(self, state: str, message: str, evidence=None) -> None:
        if evidence is not None:
            self._manualJogEvidence = dict(evidence)
            if "manualJogReconciliationRequired" in evidence:
                self.manualJogReconciliationRequired = (
                    evidence["manualJogReconciliationRequired"] is True
                )
            native_summary = self._formatManualJogNativeEvidence(evidence)
            if native_summary:
                message = f"{message} {native_summary}"
        self._updateManualJogKeyboardControlState()
        self._setManualJogStatus(state, message)
        self._updateManualJogJointPresentation()

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
        command_limits = details.get("draftWithinCommandLimits")
        if command_limits is None:
            command_limits = evaluation.get("draftWithinCommandLimits")
        limit_authoritative = details.get("limitAssessmentAuthoritative")
        if limit_authoritative is None:
            limit_authoritative = evaluation.get("limitAssessmentAuthoritative")
        limit_violations = details.get("limitViolations")
        if not isinstance(limit_violations, (list, tuple)):
            limit_violations = evaluation.get("limitViolations")
        if not isinstance(limit_violations, (list, tuple)):
            limit_violations = ()
        limit_status = (
            "within command limits"
            if command_limits is True
            else "outside command limits"
            if command_limits is False
            else "command-limit assessment unavailable"
        )
        authority_status = (
            "authoritative"
            if limit_authoritative is True
            else "not authoritative"
            if limit_authoritative is False
            else "authority unavailable"
        )
        violation_text = []
        for violation in limit_violations:
            if not isinstance(violation, Mapping):
                continue
            joint = str(violation.get("jointLabel") or violation.get("jointName") or "Joint")
            source = str(violation.get("limitSource") or "command")
            bound = str(violation.get("bound") or "limit")
            unit = str(violation.get("unit") or "")
            candidate = violation.get("candidateDisplayValue")
            bound_value = violation.get("boundDisplayValue")
            margin = violation.get("margin")
            try:
                candidate = float(candidate)
                candidate_text = f"{candidate:.2f} {unit}".strip() if isfinite(candidate) else "unavailable"
            except (TypeError, ValueError, OverflowError):
                candidate_text = "unavailable"
            try:
                bound_value = float(bound_value)
                bound_text = f"{bound_value:.2f} {unit}".strip() if isfinite(bound_value) else "unavailable"
            except (TypeError, ValueError, OverflowError):
                bound_text = "unavailable"
            rendered = (
                f"{joint} {candidate_text} violates {source} {bound} {bound_text}"
            )
            try:
                margin = float(margin)
                if isfinite(margin):
                    rendered += f" (margin {margin:.2f} {unit})"
            except (TypeError, ValueError, OverflowError):
                pass
            violation_text.append(rendered)
        self.manualDraftStateCheckStatusLabel.text = "\n".join(
            (
                marker,
                f"Command limits: {limit_status}; assessment {authority_status}.",
                "Limit violations: "
                + ("; ".join(violation_text) if violation_text else "none reported"),
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

    def setManualRecordImportStatus(self, state: str, message: str) -> None:
        self.manualRecordImportStatusLabel.text = message
        self.manualRecordImportStatusLabel.setProperty("dentobotState", state)
        self.manualRecordImportStatusLabel.style().unpolish(
            self.manualRecordImportStatusLabel
        )
        self.manualRecordImportStatusLabel.style().polish(
            self.manualRecordImportStatusLabel
        )

    def setManualSimulationRecords(self, records) -> None:
        self._manualSimulationRecords = tuple(records)
        selector = self.manualSimulationRecordComboBox
        selector.blockSignals(True)
        selector.clear()
        for index, record in enumerate(self._manualSimulationRecords, start=1):
            fingerprint = str(record.get("record_fingerprint") or "")
            selector.addItem(
                f"Record {index} — {record.get('record_status', 'unknown')} — "
                f"{fingerprint[:12]}"
            )
        selector.enabled = bool(self._manualSimulationRecords)
        selector.setCurrentIndex(0 if self._manualSimulationRecords else -1)
        selector.blockSignals(False)
        self.clearManualRecordButton.enabled = bool(self._manualSimulationRecords)
        if self._manualSimulationRecords:
            self._onManualSimulationRecordChanged(0)
        else:
            self.manualSimulationRecordIdentityLabel.text = (
                "No historical record loaded."
            )
            self.manualSimulationEventList.clear()
            self.manualSimulationEventDetailsText.setPlainText(
                "Select a record event to inspect its saved evidence."
            )
            self.previousManualSimulationEventButton.enabled = False
            self.nextManualSimulationEventButton.enabled = False

    def clearManualSimulationRecords(self) -> None:
        self._manualSimulationRecords = ()
        selector = self.manualSimulationRecordComboBox
        selector.blockSignals(True)
        selector.clear()
        selector.setCurrentIndex(-1)
        selector.blockSignals(False)
        selector.enabled = False
        self.clearManualRecordButton.enabled = False
        self.manualSimulationEventList.blockSignals(True)
        self.manualSimulationEventList.clear()
        self.manualSimulationEventList.blockSignals(False)
        self.manualSimulationRecordIdentityLabel.text = (
            "No historical record loaded."
        )
        self.manualSimulationEventDetailsText.setPlainText(
            "Select a record event to inspect its saved evidence."
        )
        self.previousManualSimulationEventButton.enabled = False
        self.nextManualSimulationEventButton.enabled = False
        self.setManualRecordImportStatus(
            "idle",
            "Historical record display cleared. Live simulation state was not read or changed.",
        )

    def _onManualSimulationRecordChanged(self, index: int) -> None:
        if index < 0 or index >= len(self._manualSimulationRecords):
            return
        record = self._manualSimulationRecords[index]
        identity = {
            "schema_version": record["schema_version"],
            "record_status": record["record_status"],
            "record_fingerprint": record["record_fingerprint"],
            "identity": record["identity"],
            "current_identity": "unknown (historical fingerprints are not compared to live state)",
        }
        self.manualSimulationRecordIdentityLabel.text = json.dumps(
            identity, indent=2, sort_keys=True, allow_nan=False
        )
        events = record["events"]
        self.manualSimulationEventList.blockSignals(True)
        self.manualSimulationEventList.clear()
        first_time = events[0]["monotonic_ns"] if events else 0
        for event_index, event in enumerate(events, start=1):
            elapsed = (event["monotonic_ns"] - first_time) / 1_000_000_000.0
            kind = str(event["kind"])
            status = {
                "requested": "REQUESTED",
                "guard_accepted": "ACCEPTED",
                "guard_rejected": "REJECTED",
                "diagnostic": "DIAGNOSTIC",
            }.get(kind, kind.replace("_", " ").upper())
            self.manualSimulationEventList.addItem(
                f"{event_index:04d} · {status} · t+{elapsed:.6f} s "
                f"({event['monotonic_ns']} monotonic ns)"
            )
        self.manualSimulationEventList.setCurrentRow(0 if events else -1)
        self.manualSimulationEventList.blockSignals(False)
        self._onManualSimulationEventChanged(0 if events else -1)
        self._invoke("show_manual_record", record)

    def _onManualSimulationEventChanged(self, index: int) -> None:
        if not self._manualSimulationRecords:
            return
        record_index = self.manualSimulationRecordComboBox.currentIndex
        if record_index < 0 or record_index >= len(self._manualSimulationRecords):
            return
        events = self._manualSimulationRecords[record_index]["events"]
        self.previousManualSimulationEventButton.enabled = index > 0
        self.nextManualSimulationEventButton.enabled = 0 <= index < len(events) - 1
        if index < 0 or index >= len(events):
            self.manualSimulationEventDetailsText.setPlainText(
                "This record contains no events. No live state was changed."
            )
            return
        event = events[index]
        first_time = events[0]["monotonic_ns"]
        evidence_fields = (
            "requested_joints",
            "evaluated_joints",
            "accepted_joints",
            "monitored_joints",
            "native_failure_evidence",
            "collision_evidence",
            "tcp_point_ras_mm",
            "tcp_pose_world_ras_mm",
            "drill_axis_world_ras_unit",
            "tcp_path_ras_mm",
            "diagnostic",
            "details",
        )
        shown_event = dict(event)
        for field in evidence_fields:
            shown_event.setdefault(field, "unknown (not recorded)")
        elapsed = (event["monotonic_ns"] - first_time) / 1_000_000_000.0
        heading = (
            f"Historical event {index + 1} of {len(events)}: "
            f"{event['kind']} — source monotonic timestamp "
            f"{event['monotonic_ns']} ns (t+{elapsed:.6f} s).\n"
            "Step-through selection only; no motion, guard, FK, or preview call.\n\n"
        )
        self.manualSimulationEventDetailsText.setPlainText(
            heading
            + json.dumps(shown_event, indent=2, sort_keys=True, allow_nan=False)
        )

    def _stepManualSimulationEvent(self, step: int) -> None:
        record_index = self.manualSimulationRecordComboBox.currentIndex
        if not 0 <= record_index < len(self._manualSimulationRecords):
            return
        event_count = len(self._manualSimulationRecords[record_index]["events"])
        if not event_count:
            return
        current = self.manualSimulationEventList.currentRow
        self.manualSimulationEventList.setCurrentRow(
            min(event_count - 1, max(0, current + int(step)))
        )

    def setManualJogDraftDisplayResult(self, success: bool, message: str) -> None:
        if self._taskHomeSetupMode == "offline":
            self.manualJogDraftStateLabel.text = (
                "Draft state: "
                + self._formatManualJogDisplayValues(self._manualJogDisplayValues)
                + " — Home configuration draft retained; "
                + str(message)
            )
        elif self._taskHomeSetupMode != "connected":
            self.manualJogDraftStateLabel.text = (
                "Draft state: "
                + self._formatManualJogDisplayValues(self._manualJogDisplayValues)
                + " — draft retained; live display blocked because setup mode is "
                "unknown. "
                + str(message)
            )
        elif success:
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
        saved_home_available = bool(
            self._taskHomeConfigurationReady
            and self._taskHomeConfiguredJointPositionsSi
        )
        use_home_configuration = bool(
            self._taskHomeSetupMode == "offline"
            or (
                getattr(self, "_manualJogControlsInHomeGroup", False)
                and saved_home_available
            )
        )
        if use_home_configuration:
            state = (
                self._taskHomeConfiguredJointPositionsSi
                if saved_home_available
                else self._manualJogLocalJointPositionsSi
            )
        else:
            state = self._manualJogAcceptedJointPositionsSi
        if not state:
            self._setManualJogStatus(
                "unknown",
                "Guard status: unknown — no Home configuration or reset pose is available.",
            )
            return
        display = (
            degrees(state[JOINT_NAMES[0]]),
            state[JOINT_NAMES[1]] * 1000.0,
            degrees(state[JOINT_NAMES[2]]),
            state[JOINT_NAMES[3]] * 1000.0,
            degrees(state[JOINT_NAMES[4]]),
        )
        self._setManualJogDraftValues(display, notify=True)

    def manualJogJointPositionsSi(self) -> dict[str, float]:
        positions = joint_positions_si_from_display(*self._manualJogDisplayValues)
        return {joint: float(positions[joint]) for joint in JOINT_NAMES}

    def _onManualJogSliderChanged(self, joint: str, position: int) -> None:
        if not self._manualJogLimits or not self._manualJogSliderRanges:
            return
        index = JOINT_NAMES.index(joint)
        minimum, maximum = self._manualJogSliderRanges[index]
        value = (
            minimum + (maximum - minimum) * int(position) / 10000.0
            if maximum > minimum
            else minimum
        )
        slider, spinbox, _label = self.manualJogJointControls[joint]
        spinbox.blockSignals(True)
        spinbox.setValue(value)
        spinbox.blockSignals(False)
        self._updateManualJogDraftFromControls(joint, value)

    def _onTaskHomeSliderChanged(self, joint: str, position: int) -> None:
        controls = self.manualJogJointControls.get(joint)
        if controls is not None:
            controls[0].setValue(int(position))

    def _onTaskHomeNumericChanged(self, joint: str, value: float) -> None:
        controls = self.manualJogJointControls.get(joint)
        if controls is not None:
            controls[1].setValue(float(value))

    def _syncTaskHomeJointEditor(self) -> None:
        home_controls = getattr(self, "taskHomeJointControls", {})
        for joint in JOINT_NAMES:
            source = self.manualJogJointControls.get(joint)
            target = home_controls.get(joint)
            presentation = self._manualJogJointPresentation.get(joint, {})
            if source is None or target is None:
                continue
            source_slider, source_value, _label = source
            slider, value, state = target
            slider.blockSignals(True)
            value.blockSignals(True)
            slider.minimum = source_slider.minimum
            slider.maximum = source_slider.maximum
            slider.value = source_slider.value
            slider.enabled = source_slider.enabled
            value.minimum = source_value.minimum
            value.maximum = source_value.maximum
            value.value = source_value.value
            value.enabled = source_value.enabled
            value.blockSignals(False)
            slider.blockSignals(False)
            comparison = presentation.get("comparison")
            lower = presentation.get("lower")
            upper = presentation.get("upper")
            state.text = str(getattr(comparison, "text", "Draft unavailable"))
            state.toolTip = (
                str(getattr(comparison, "toolTip", ""))
                + " Slider range: "
                + str(getattr(lower, "text", "--"))
                + " to "
                + str(getattr(upper, "text", "--"))
            ).strip()

    def _onManualJogNumericChanged(self, joint: str, value: float) -> None:
        if not self._manualJogLimits or not self._manualJogSliderRanges:
            return
        index = JOINT_NAMES.index(joint)
        minimum, maximum = self._manualJogSliderRanges[index]
        slider, spinbox, _label = self.manualJogJointControls[joint]
        slider.blockSignals(True)
        slider.value = round(
            min(1.0, max(0.0, (float(value) - minimum) / (maximum - minimum)))
            * 10000
        ) if maximum > minimum else 0
        slider.blockSignals(False)
        self._updateManualJogDraftFromControls(joint, value)

    def _updateManualJogDraftFromControls(
        self, joint: str | None = None, value: float | None = None
    ) -> None:
        if joint is None:
            values = tuple(
                float(self.manualJogJointControls[name][1].value)
                for name in JOINT_NAMES
            )
        else:
            updated = list(self._manualJogDisplayValues)
            index = JOINT_NAMES.index(joint)
            updated[index] = float(
                self.manualJogJointControls[joint][1].value
                if value is None else value
            )
            values = tuple(updated)
        self._manualJogDisplayValues = values
        self._manualJogDraftInitialized = True
        self.manualJogDraftStateLabel.text = (
            "Draft state: " + self._formatManualJogDisplayValues(values)
        )
        self._setManualJogStatus(
            "unknown",
            "Guard status: unknown for this draft — no request has been sent.",
        )
        self.setManualJogAvailability(
            self._manualJogAvailable, self._manualJogGuardContextAvailable
        )
        self._invoke("manual_draft_changed", self.manualJogJointPositionsSi())

    def _setManualJogDraftValues(self, values, *, notify: bool) -> None:
        if not self._manualJogLimits or not self._manualJogMechanicalLimits:
            return
        try:
            requested = tuple(float(value) for value in values)
        except (TypeError, ValueError, OverflowError):
            return
        if len(requested) != len(JOINT_NAMES) or not all(
            isfinite(value) for value in requested
        ):
            return
        bounded = tuple(
            min(max(value, self._manualJogMechanicalLimits[index][0]),
                self._manualJogMechanicalLimits[index][1])
            for index, value in enumerate(requested)
        )
        for index, joint in enumerate(JOINT_NAMES):
            slider, spinbox, _label = self.manualJogJointControls[joint]
            minimum, maximum = self._manualJogSliderRanges[index]
            spinbox.blockSignals(True)
            slider.blockSignals(True)
            spinbox.setValue(bounded[index])
            slider.value = round(
                min(1.0, max(0.0, (bounded[index] - minimum) / (maximum - minimum)))
                * 10000
            ) if maximum > minimum else 0
            spinbox.blockSignals(False)
            slider.blockSignals(False)
        self._manualJogDisplayValues = bounded
        self._manualJogDraftInitialized = True
        self.manualJogDraftStateLabel.text = (
            "Draft state: "
            + self._formatManualJogDisplayValues(self._manualJogDisplayValues)
        )
        self.setManualJogAvailability(
            self._manualJogAvailable, self._manualJogGuardContextAvailable
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

    def _invoke_task_space_box(self) -> None:
        self._invoke(
            "set_task_space_box",
            bool(self.showTaskSpaceBoxCheckBox.checked),
            float(self.taskSpaceBoxSideSpinBox.value),
            float(self.taskSpaceBoxOpacitySlider.value) / 100.0,
        )

    def syncPlanningAidMirrors(self) -> None:
        """Mirror the 6.3 planning-aid checkboxes into the 6.1 Display dialog."""
        for owner, mirror in (
            (self.showMouthBarrierCheckBox, getattr(self, "displayShowMouthBarrierCheckBox", None)),
            (self.showTaskSpaceBoxCheckBox, getattr(self, "displayShowTaskSpaceBoxCheckBox", None)),
        ):
            if mirror is not None and bool(mirror.checked) != bool(owner.checked):
                was = mirror.blockSignals(True)
                mirror.checked = bool(owner.checked)
                mirror.blockSignals(was)

    def syncStep6OverlayControls(self, *, barrier_opacity: float, show_task_space_box: bool,
                                 task_space_box_side_mm: float, task_space_box_opacity: float) -> None:
        """Mirror persisted 6.3 overlay settings without re-emitting actions."""
        values = (
            (self.mouthBarrierOpacitySlider, "value", int(round(100.0 * float(barrier_opacity)))),
            (self.showTaskSpaceBoxCheckBox, "checked", bool(show_task_space_box)),
            (self.taskSpaceBoxSideSpinBox, "value", float(task_space_box_side_mm)),
            (self.taskSpaceBoxOpacitySlider, "value", int(round(100.0 * float(task_space_box_opacity)))),
        )
        for widget, attribute, value in values:
            if getattr(widget, attribute) != value:
                was = widget.blockSignals(True)
                setattr(widget, attribute, value)
                widget.blockSignals(was)
        self.syncPlanningAidMirrors()

    def syncStep6RunOptions(self, *, dev_fast_mode: bool, depth_peeling: bool) -> None:
        """Mirror the live run options (facade flag, 3D view state) without re-emitting."""
        for widget, checked in ((self.devFastModeCheckBox, dev_fast_mode),
                                (self.depthPeelingCheckBox, depth_peeling)):
            if bool(widget.checked) != bool(checked):
                was = widget.blockSignals(True)
                widget.checked = bool(checked)
                widget.blockSignals(was)

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
        next_substep = max(0, min(int(substep_index), 4))
        if next_substep != 3:
            self._disableTcpDragForSubstepChange()
        display_dialog = getattr(self, "_displayDialog", None)
        setup_dialog = getattr(self, "_setupToolsDialog", None)
        home_dialog = getattr(self, "_taskHomeDetailsDialog", None)
        if next_substep != 1 and display_dialog is not None:
            display_dialog.hide()
        if next_substep != 1 and setup_dialog is not None:
            setup_dialog.hide()
        if next_substep != 2 and home_dialog is not None:
            home_dialog.hide()
        if next_substep != 3:
            for dialog in (
                getattr(self, "_manualRecordsDialog", None),
                getattr(self, "_planningToolsDialog", None),
                getattr(self, "_anatomyReviewDialog", None),
                getattr(self, "_baseDiagnosisDialog", None),
            ):
                if dialog is not None:
                    dialog.hide()
        self._activeSubstep = next_substep
        self._updateTcpCartesianControlState()
        self._updateManualJogKeyboardControlState()

    def setBaseInteractionStatus(self, state: str, message: str) -> None:
        self.baseInteractionStatusLabel.text = str(message)
        self.baseInteractionStatusLabel.setProperty("dentobotState", str(state))
        self.baseInteractionStatusLabel.style().unpolish(
            self.baseInteractionStatusLabel
        )
        self.baseInteractionStatusLabel.style().polish(
            self.baseInteractionStatusLabel
        )

    def showSetupToolsDialog(self) -> None:
        if self._activeSubstep != 1:
            return
        if self._setupToolsDialog is None:
            dialog = qt.QDialog(self.visualizationGroup)
            dialog.objectName = "DENTOBOTStep61SetupToolsDialog"
            dialog.windowTitle = "DENTOBOT Step 6.1 Setup Tools"
            dialog.setModal(False)
            layout = qt.QVBoxLayout(dialog)
            description = qt.QLabel(
                "Infrequent setup actions. Reset changes the detached Base draft; "
                "delete removes the local robot setup after confirmation.",
                dialog,
            )
            description.wordWrap = True
            layout.addWidget(description)
            reset_button = qt.QPushButton("Reset Base to World", dialog)
            delete_button = qt.QPushButton("Delete Robot Setup…", dialog)
            reset_button.clicked.connect(
                lambda checked=False: self._invoke("reset_base")
            )
            delete_button.clicked.connect(
                lambda checked=False: self._invoke("delete_setup")
            )
            layout.addWidget(reset_button)
            layout.addWidget(delete_button)
            close_button = qt.QPushButton("Close", dialog)
            close_button.clicked.connect(dialog.hide)
            layout.addWidget(close_button)
            self._setupToolsDialog = dialog
        self._setupToolsDialog.show()

    BASE_DIAGNOSIS_COLORS = {
        "PASS": "#1e7d32", "WARNING": "#b26a00", "FAIL": "#b3261e", "NOT RUN": "#5f6368",
    }

    def showBaseDiagnosisDialog(self, summary) -> None:
        """Non-modal Diagnose This Base table (S6-BASE-DIAGNOSE)."""
        if self._baseDiagnosisDialog is None:
            dialog = qt.QDialog(self.approachGroup)
            dialog.objectName = "DENTOBOTBaseDiagnosisDialog"
            dialog.windowTitle = "DENTOBOT Diagnose This Base"
            dialog.setModal(False)
            layout = qt.QVBoxLayout(dialog)
            self._baseDiagnosisVerdictLabel = qt.QLabel("", dialog)
            self._baseDiagnosisVerdictLabel.wordWrap = True
            layout.addWidget(self._baseDiagnosisVerdictLabel)
            table = qt.QTableWidget(0, 4, dialog)
            table.objectName = "DENTOBOTBaseDiagnosisTable"
            table.setHorizontalHeaderLabels(["Check", "Result", "Cause", "Detail"])
            table.setMinimumWidth(720)
            table.setMinimumHeight(220)
            table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(table)
            self._baseDiagnosisTable = table
            note = qt.QLabel(
                "Checks stop at the first failure. Diagnostic only: no route, preview "
                "or gate change.", dialog
            )
            note.wordWrap = True
            layout.addWidget(note)
            close_button = qt.QPushButton("Close", dialog)
            close_button.clicked.connect(dialog.hide)
            layout.addWidget(close_button)
            self._baseDiagnosisDialog = dialog
        status = str(summary.get("status") or "NOT RUN")
        color = self.BASE_DIAGNOSIS_COLORS.get(status, "#5f6368")
        self._baseDiagnosisVerdictLabel.text = f"{status} — {summary.get('verdict', '')}"
        self._baseDiagnosisVerdictLabel.styleSheet = f"font-weight: bold; color: {color};"
        rows = list(summary.get("rows") or ())
        table = self._baseDiagnosisTable
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            cells = (row.get("title", ""), row.get("status", ""), row.get("cause_title", ""), row.get("detail", ""))
            for column, value in enumerate(cells):
                item = qt.QTableWidgetItem(str(value))
                if column == 1:
                    item.setForeground(qt.QBrush(qt.QColor(
                        self.BASE_DIAGNOSIS_COLORS.get(str(value), "#5f6368")
                    )))
                table.setItem(index, column, item)
        table.resizeColumnsToContents()
        self._baseDiagnosisDialog.show()
        self._baseDiagnosisDialog.raise_()

    def showTaskHomeDetailsDialog(self) -> None:
        if self._activeSubstep != 2:
            return
        if self._taskHomeDetailsDialog is None:
            dialog = qt.QDialog(self.homeGroup)
            dialog.objectName = "DENTOBOTTaskHomeDetailsDialog"
            dialog.windowTitle = "DENTOBOT Task Home Details"
            dialog.setModal(False)
            layout = qt.QVBoxLayout(dialog)
            self._taskHomeDetailsText = qt.QPlainTextEdit(dialog)
            self._taskHomeDetailsText.readOnly = True
            self._taskHomeDetailsText.setMinimumWidth(420)
            self._taskHomeDetailsText.setMinimumHeight(240)
            layout.addWidget(self._taskHomeDetailsText)
            close_button = qt.QPushButton("Close", dialog)
            close_button.clicked.connect(dialog.hide)
            layout.addWidget(close_button)
            self._taskHomeDetailsDialog = dialog
        self._taskHomeDetailsText.setPlainText(
            "\n\n".join(
                (
                    str(self.taskHomeCurrentStateLabel.text),
                    str(self.taskHomeConfiguredStateLabel.text),
                    str(self.taskHomeCandidateLabel.text),
                    str(self.taskHomeReviewStatusLabel.text),
                    str(self.homeStatusLabel.text),
                )
            )
        )
        self._taskHomeDetailsDialog.show()

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
        if self._activeSubstep != 3:
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
        seed_text = "Task Home" if seed is None else f"workspace sample {int(seed)}"
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
                "Task Home/base placement or use a distinct Home-connected workspace route. "
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

    @staticmethod
    def _motionDiagnosticTargetConditioningText(
        session, exact_current_session: bool = False
    ) -> str:
        conditioning = session.full_task_outcome.get("target_conditioning")
        if (
            not isinstance(conditioning, Mapping)
            or conditioning.get("world_frame") != "RAS_mm"
        ):
            return ""
        try:
            points = {
                label: tuple(float(value) for value in conditioning[field])
                for label, field in (
                    ("PreEntry", "pre_entry_world_ras_mm"),
                    ("Entry", "entry_world_ras_mm"),
                    ("Target", "target_world_ras_mm"),
                )
            }
            if any(
                len(point) != 3 or not all(isfinite(value) for value in point)
                for point in points.values()
            ):
                return ""
            standoff = conditioning.get("standoff_mm")
            standoff_text = (
                f"{float(standoff):.3f} mm"
                if standoff is not None and isfinite(float(standoff))
                else "not recorded"
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return ""
        state = str(getattr(session, "state", ""))
        stale_reason = str(getattr(session, "stale_reason", ""))
        is_current = exact_current_session and state == "Current" and not stale_reason
        if is_current:
            provenance = "Exact current diagnostic snapshot at display time"
        elif state == "Stale" or stale_reason:
            provenance = "Stale saved diagnostic snapshot"
        else:
            provenance = "Saved diagnostic snapshot; currentness not confirmed"
        coordinate_text = " | ".join(
            f"{label} ({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})"
            for label, point in points.items()
        )
        return (
            f"TCP target coordinates — {coordinate_text} RAS mm | "
            f"standoff {standoff_text}. {provenance}. DISPLAY ONLY — no route authority."
        )

    @staticmethod
    def _motionDiagnosticInspectionSummary(details) -> str:
        details = details if isinstance(details, Mapping) else {}
        inspection = details.get("diagnosticInspection")
        if not isinstance(inspection, Mapping):
            return ""
        expected = inspection.get("expected")
        expected = expected if isinstance(expected, Mapping) else {}
        fk = inspection.get("fk")
        fk = fk if isinstance(fk, Mapping) else {}
        static = inspection.get("static_state_validity")
        static = static if isinstance(static, Mapping) else {}
        native = inspection.get("native")
        native = native if isinstance(native, Mapping) else {}

        def vector_text(values):
            if not isinstance(values, (list, tuple)) or len(values) != 3:
                return "not reported"
            try:
                numbers = tuple(float(value) for value in values)
            except (TypeError, ValueError, OverflowError):
                return "not reported"
            if not all(isfinite(value) for value in numbers):
                return "not reported"
            return "(" + ", ".join(f"{value:.4g}" for value in numbers) + ")"

        def pose_position_text(matrix):
            if not isinstance(matrix, (list, tuple)) or len(matrix) != 4:
                return "not reported"
            try:
                rows = tuple(tuple(float(value) for value in row) for row in matrix)
            except (TypeError, ValueError, OverflowError):
                return "not reported"
            if any(len(row) != 4 for row in rows) or not all(
                isfinite(value) for row in rows for value in row
            ):
                return "not reported"
            return vector_text(tuple(rows[index][3] for index in range(3)))

        def scalar_text(key, unit):
            value = inspection.get(key)
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                return "not reported"
            return f"{number:.4g} {unit}" if isfinite(number) else "not reported"

        authoritative = static.get("authoritative")
        authoritative_text = (
            "yes" if authoritative is True else "no" if authoritative is False else "not reported"
        )
        static_text = str(static.get("status") or "unknown")
        static_message = str(static.get("message") or "no message reported")
        fk_status = str(fk.get("status") or "unknown")
        fk_message = str(fk.get("message") or "no message reported")
        native_message = str(
            native.get("message")
            or native.get("solver_message")
            or "not reported"
        )
        termination_reason = str(
            native.get("termination_reason") or "not reported"
        )
        collision_status = str(
            native.get("collision_check_status") or "not reported"
        )
        return (
            "Failed solver pose, read-only inspection (not accepted or route-authorized). "
            f"Requested TCP RAS mm {vector_text(expected.get('tcp_world_ras_mm'))}; "
            f"FK TCP RAS mm {pose_position_text(fk.get('pose_world_ras_mm'))}. "
            f"Requested/actual drill axis {vector_text(expected.get('drilling_axis_world_ras_unit'))} / "
            f"{vector_text(fk.get('drilling_axis_world_ras_unit'))}; residuals "
            f"{scalar_text('position_residual_mm', 'mm')} / "
            f"{scalar_text('drilling_axis_residual_deg', 'deg')}. "
            f"FK inspection: {fk_status} — {fk_message}. "
            f"Read-only static validity: {static_text} (authoritative: "
            f"{authoritative_text}) — {static_message}. Native status/reason: "
            f"{inspection.get('status') or 'unknown'} / {native_message}; "
            f"termination: {termination_reason}; native collision-check status: "
            f"{collision_status}."
        )

    @staticmethod
    def _invokeMotionDiagnosticCandidate(
        on_candidate_selected,
        candidate_index: int,
        *,
        exact_current_session: bool,
        preentry_ik_failure: bool,
    ):
        if not on_candidate_selected or (
            preentry_ik_failure and not exact_current_session
        ):
            return None
        return on_candidate_selected(int(candidate_index))

    def showMotionDiagnostics(
        self,
        session,
        on_candidate_selected,
        on_review,
        on_candidate_path=None,
        on_candidate_preview=None,
        on_candidate_apply=None,
        on_candidate_unlock=None,
        exact_current_session: bool = False,
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
        summary.setMinimumWidth(0)
        summary.setSizePolicy(qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred)
        layout.addWidget(summary)
        target_conditioning_text = self._motionDiagnosticTargetConditioningText(
            session, exact_current_session=exact_current_session
        )
        self._motionDiagnosticTargetConditioningLabel = None
        if target_conditioning_text:
            target_conditioning_label = qt.QLabel(target_conditioning_text, dialog)
            target_conditioning_label.objectName = (
                "DENTOBOTMotionDiagnosticTargetCoordinates"
            )
            target_conditioning_label.wordWrap = True
            target_conditioning_label.setMinimumWidth(0)
            target_conditioning_label.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            target_conditioning_label.setProperty(
                "dentobotRole",
                "status"
                if "Exact current diagnostic snapshot at display time"
                in target_conditioning_text
                else "warning",
            )
            target_conditioning_label.setStyleSheet(
                "font-size: 14pt; font-weight: 700; padding: 6px;"
            )
            self._motionDiagnosticTargetConditioningLabel = (
                target_conditioning_label
            )
            layout.addWidget(target_conditioning_label)
        identity_label = qt.QLabel(
            "Evidence identity — "
            f"task {session.task_fingerprint[:12]}; "
            f"trajectory {session.trajectory_fingerprint[:12]}; "
            f"robot base {session.base_fingerprint[:12]}.",
            dialog,
        )
        identity_label.wordWrap = True
        identity_label.setMinimumWidth(0)
        identity_label.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        layout.addWidget(identity_label)
        diagnostic_kind = str(
            session.full_task_outcome.get("diagnostic_kind") or ""
        )
        preentry_ik_failure = (
            diagnostic_kind == "preentry_ik"
            or str(session.full_task_outcome.get("blocked_stage") or "")
            == "preentry_ik"
        )
        if preentry_ik_failure and diagnostic_kind != "preentry_ik":
            summary.text = (
                "Guarded planning stopped at PreEntry IK. Selecting a seed shows only "
                "its translucent best failed J1–J5 pose; that pose is not accepted, "
                "not verified collision-free, and has no route, preview, or motion authority."
            )
            summary.setProperty("dentobotRole", "warning")
        if diagnostic_kind == "preentry_ik":
            outcome = session.full_task_outcome
            summary.text = (
                "PreEntry IK endpoint diagnostic only. P1/Stage 1, Stage 2, Stage 3, "
                "route planning, guard, preview, and motion application were not run. "
                "It is display-only and can never be route authority; a saved/reopened "
                "report requires fresh live checks before any later planning. "
                f"Endpoint status: {outcome.get('diagnostic_status', 'Unknown')}."
            )
            summary.setProperty("dentobotRole", "warning")
            conditioning_help = qt.QLabel(
                "Endpoint conditioning: task-Jacobian singular-value ratio is "
                "tolerance-scaled (0≈singular; 1 better conditioned). Unknown values "
                "are shown as — and are not a feasibility verdict. For collision "
                "checks, only status 'clear' means the endpoint scene check ran and "
                "accepted; every other status is unverified.",
                dialog,
            )
            conditioning_help.wordWrap = True
            conditioning_help.setMinimumWidth(0)
            conditioning_help.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            layout.addWidget(conditioning_help)
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
            identity_notes.setMinimumWidth(0)
            identity_notes.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            layout.addWidget(identity_notes)
            candidate_display_status = qt.QLabel(
                (
                    "Select a seed to show its translucent best failed J1–J5 pose. "
                    "This is not accepted robot state and is not verified collision-free."
                    if exact_current_session
                    else "Saved/stale report is text-only. Re-run this diagnostic to "
                    "display a seed; no current robot pose is shown."
                ),
                dialog,
            )
            candidate_display_status.wordWrap = True
            candidate_display_status.setMinimumWidth(0)
            candidate_display_status.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            candidate_display_status.setProperty(
                "dentobotRole", "warning" if exact_current_session else "status"
            )
            layout.addWidget(candidate_display_status)
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
            table.setMinimumWidth(0)
            table.setWordWrap(True)
            table.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Expanding
            )
            layout.addWidget(table)
            details = qt.QPlainTextEdit(dialog)
            details.readOnly = True
            details.setMinimumWidth(0)
            details.setLineWrapMode(qt.QPlainTextEdit.WidgetWidth)
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
                    result = self._invokeMotionDiagnosticCandidate(
                        on_candidate_selected,
                        int(row),
                        exact_current_session=exact_current_session,
                        preentry_ik_failure=True,
                    )
                    if result is not None:
                        details.appendPlainText(
                            "\n\nCandidate display: " + result.message
                        )
                        result_details = getattr(result, "details", {}) or {}
                        inspection = (
                            result_details.get("diagnosticInspection")
                            if isinstance(result_details, Mapping)
                            else None
                        )
                        inspection_summary = (
                            self._motionDiagnosticInspectionSummary(result_details)
                        )
                        if isinstance(inspection, Mapping):
                            details.appendPlainText(
                                "\n\nRead-only failed-pose inspection:\n"
                                + json.dumps(inspection, indent=2, sort_keys=True)
                            )
                        if inspection_summary:
                            details.appendPlainText("\n\n" + inspection_summary)
                        display_status = (
                            f"Translucent best failed J1–J5 from seed {int(row) + 1} "
                            "is displayed. This is not accepted robot state and is "
                            "not verified collision-free."
                            if result.success
                            else "Diagnostic display was incomplete: "
                            f"{result.message} No accepted robot state or "
                            "collision-free claim was made."
                        )
                        candidate_display_status.text = display_status + (
                            " " + inspection_summary if inspection_summary else ""
                        )
                    elif exact_current_session:
                        candidate_display_status.text = (
                            "The translucent best failed J1–J5 pose is unavailable; "
                            "no accepted robot state or collision-free claim was made."
                        )
                    else:
                        candidate_display_status.text = (
                            "Saved/stale report is text-only. Re-run this diagnostic "
                            "to display a seed; no current robot pose is shown."
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
        planner_policy_label.setMinimumWidth(0)
        planner_policy_label.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        layout.addWidget(planner_policy_label)
        full_status = str(session.full_task_outcome.get("status") or "Unknown")
        template_excluded = bool(
            session.full_task_outcome.get("template_collision_exclusion_active")
        )
        orientation_id = str(
            session.full_task_outcome.get("tool_orientation_fingerprint") or ""
        )
        full_task_label = qt.QLabel(
            f"Full task: {full_status}. The five-DOF arm controls position and drill-axis direction; axial roll is unconstrained."
            + (
                f" Stage-1 fixed tool frame: {orientation_id[:12]}."
                if orientation_id
                else " Stage-1 tool frame is not yet committed."
            ),
            dialog,
        )
        full_task_label.wordWrap = True
        full_task_label.setMinimumWidth(0)
        full_task_label.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
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
        selection_label.setMinimumWidth(0)
        selection_label.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
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
            collision_scope_label.setMinimumWidth(0)
            collision_scope_label.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
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
            anatomy_scope_label.setMinimumWidth(0)
            anatomy_scope_label.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            anatomy_scope_label.setProperty("dentobotRole", "warning")
            layout.addWidget(anatomy_scope_label)
        feedback_label = qt.QLabel(
            self._motionPlannerFeedback(session),
            dialog,
        )
        feedback_label.wordWrap = True
        feedback_label.setMinimumWidth(0)
        feedback_label.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
        )
        feedback_label.setProperty("dentobotRole", "status")
        layout.addWidget(feedback_label)
        candidate_display_status = None
        if preentry_ik_failure:
            candidate_display_status = qt.QLabel(
                (
                    "Select a seed to request its read-only failed-pose inspection. "
                    "No pose is displayed automatically; it is not accepted robot "
                    "state and is not verified collision-free."
                    if exact_current_session
                    else "Saved/stale report is text-only. Re-run this diagnostic to "
                    "display a seed; no current robot pose is shown."
                ),
                dialog,
            )
            candidate_display_status.wordWrap = True
            candidate_display_status.setProperty(
                "dentobotRole", "warning" if exact_current_session else "status"
            )
            layout.addWidget(candidate_display_status)
        operator_error = str(session.full_task_outcome.get("operator_error_message") or "")
        if operator_error:
            error_text = qt.QPlainTextEdit(dialog)
            error_text.readOnly = True
            error_text.setMinimumWidth(0)
            error_text.setLineWrapMode(qt.QPlainTextEdit.WidgetWidth)
            error_text.plainText = operator_error
            error_text.toolTip = "Exact error-dialog text from this planner attempt; copyable after the dialog closes."
            error_label = qt.QLabel("Planner error-dialog text (retained):", dialog)
            error_label.wordWrap = True
            error_label.setMinimumWidth(0)
            error_label.setSizePolicy(
                qt.QSizePolicy.Ignored, qt.QSizePolicy.Preferred
            )
            layout.addWidget(error_label)
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
        stage_table.setMinimumWidth(0)
        stage_table.setWordWrap(True)
        stage_table.setSizePolicy(
            qt.QSizePolicy.Ignored, qt.QSizePolicy.Expanding
        )
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
                    else f"workspace sample {int(record['ik_seed_sample_index'])}"
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
        table.setMinimumWidth(0)
        table.setWordWrap(True)
        table.setSizePolicy(qt.QSizePolicy.Ignored, qt.QSizePolicy.Expanding)
        layout.addWidget(table)
        scrubber = qt.QSlider(qt.Qt.Horizontal, dialog)
        scrubber.minimum = 0
        scrubber.maximum = max(0, len(records) - 1)
        scrubber.value = int(session.selected_candidate_index)
        layout.addWidget(scrubber)
        details = qt.QPlainTextEdit(dialog)
        details.readOnly = True
        details.setMinimumWidth(0)
        details.setLineWrapMode(qt.QPlainTextEdit.WidgetWidth)
        layout.addWidget(details)
        dialog_buttons = qt.QVBoxLayout()
        display_buttons = qt.QHBoxLayout()
        route_buttons = qt.QHBoxLayout()
        path_button = qt.QPushButton("Show Selected Paths", dialog)
        preview_button = qt.QPushButton("Preview Selected Leg", dialog)
        apply_button = qt.QPushButton("Use Selected Route (replan)", dialog)
        lock_button = qt.QPushButton("Lock + Replan Selected Route", dialog)
        unlock_button = qt.QPushButton("Unlock Saved Route", dialog)
        review_button = qt.QPushButton("Mark Current Evidence Reviewed", dialog)
        close_button = qt.QPushButton("Close", dialog)
        for button in (path_button, preview_button, close_button):
            button.setMinimumWidth(0)
            display_buttons.addWidget(button)
        for button in (apply_button, lock_button, unlock_button, review_button):
            button.setMinimumWidth(0)
            route_buttons.addWidget(button)
        dialog_buttons.addLayout(display_buttons)
        dialog_buttons.addLayout(route_buttons)
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
        path_button.enabled = bool(on_candidate_path and not preentry_ik_failure)
        preview_button.enabled = bool(on_candidate_preview and not preentry_ik_failure)

        def update_plan_buttons(index: int) -> None:
            record = records[index]
            complete = str(record.get("full_chain_candidate_status") or "") == "Complete"
            locked = plan_selection_state == "locked"
            apply_button.enabled = bool(
                on_candidate_apply and complete and not locked and not preentry_ik_failure
            )
            lock_button.enabled = bool(
                on_candidate_apply and complete and not locked and not preentry_ik_failure
            )
            unlock_button.enabled = bool(
                on_candidate_unlock and locked and not preentry_ik_failure
            )

        last_inspected_candidate = {"index": None}

        def select_candidate(index: int, *, inspect: bool = True) -> None:
            index = max(0, min(len(records) - 1, int(index)))
            table.selectRow(index)
            scrubber.blockSignals(True)
            scrubber.value = index
            scrubber.blockSignals(False)
            record = records[index]
            feedback_label.text = self._motionPlannerFeedback(session, index)
            details.plainText = json.dumps(record, indent=2, sort_keys=True)
            update_plan_buttons(index)
            if not inspect:
                return
            if last_inspected_candidate["index"] == index:
                return
            last_inspected_candidate["index"] = index
            result = self._invokeMotionDiagnosticCandidate(
                on_candidate_selected,
                index,
                exact_current_session=exact_current_session,
                preentry_ik_failure=preentry_ik_failure,
            )
            if result is not None:
                details.appendPlainText("\n\nDisplay result: " + result.message)
                result_details = getattr(result, "details", {}) or {}
                inspection = (
                    result_details.get("diagnosticInspection")
                    if isinstance(result_details, Mapping)
                    else None
                )
                inspection_summary = self._motionDiagnosticInspectionSummary(
                    result_details
                )
                if isinstance(inspection, Mapping):
                    details.appendPlainText(
                        "\n\nRead-only failed-pose inspection:\n"
                        + json.dumps(inspection, indent=2, sort_keys=True)
                    )
                if inspection_summary:
                    details.appendPlainText("\n\n" + inspection_summary)
                if candidate_display_status is not None:
                    display_status = (
                        f"Translucent best failed J1–J5 from seed {index + 1} "
                        "is displayed. This is not accepted robot state and is "
                        "not verified collision-free."
                        if result.success
                        else "Diagnostic display was incomplete: "
                        f"{result.message} No accepted robot state or "
                        "collision-free claim was made."
                    )
                    candidate_display_status.text = display_status + (
                        " " + inspection_summary if inspection_summary else ""
                    )
            elif candidate_display_status is not None and not exact_current_session:
                candidate_display_status.text = (
                    "Saved/stale report is text-only. Re-run this diagnostic to "
                    "display a seed; no current robot pose is shown."
                )
            elif candidate_display_status is not None:
                candidate_display_status.text = (
                    "The translucent best failed J1–J5 pose is unavailable; no "
                    "accepted robot state or collision-free claim was made."
                )

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

        self._diagnosticDialog = dialog
        select_candidate(int(session.selected_candidate_index), inspect=False)
        table.currentCellChanged.connect(
            lambda row, column, previous_row, previous_column: (
                select_candidate(row) if row >= 0 else None
            )
        )
        table.cellClicked.connect(
            lambda row, _column: select_candidate(row) if row >= 0 else None
        )
        scrubber.valueChanged.connect(select_candidate)
        dialog.show()

    def setMotionDiagnosticTargetFiducialStatus(self, visible: bool) -> None:
        label = self._motionDiagnosticTargetConditioningLabel
        if label is not None:
            label.text += (
                " Viewport fiducials show these diagnostic snapshot coordinates."
                if visible
                else " Viewport fiducials could not be shown; use the coordinates above."
            )

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
        self._tcpIkAvailable = bool(capabilities.ik_available)
        self.planGoalButton.enabled = False
        self._updateTcpCartesianControlState()
        self._updateManualJogKeyboardControlState()
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
        self.goalStatusLabel.text += (
            "\nLive drag/nudge IK is kinematic-only ghost review, not collision "
            "validity. Solve IK is collision-aware and stages J1–J5 as a draft. "
            "A failed or missing live IK pose remains visual/rejected review. Only "
            "Guarded Jog with authoritative guard acknowledgement advances accepted "
            "simulated state; no route or preview authority is granted."
        )

    def showRuntimeResult(self, result) -> None:
        self._show_result(self.runtimeStatusLabel, result)

    def showConfirmationResult(self, result) -> None:
        self._show_result(self.confirmationStatusLabel, result)

    def showCollisionResult(self, result) -> None:
        self._show_result(self.collisionStatusLabel, result)
