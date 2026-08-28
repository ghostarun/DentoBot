"""Application-style DENTOBOT shell hosted by stock 3D Slicer.

This module owns presentation only: workspace navigation, docks, theme, and
Focus/Expert chrome.  Existing workflow widgets are reparented rather than
copied, so MRML bindings and backend callbacks remain authoritative during the
incremental migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import qt
except ImportError:  # Pure registry tests run outside Slicer.
    qt = None


GUI_MODE_LEGACY = "legacy"
GUI_MODE_SHELL = "shell"
GUI_MODE_SETTING = "DENTOBOT/ApplicationShell/GuiMode"
THEME_SETTING = "DENTOBOT/ApplicationShell/Theme"
EXPERT_MODE_SETTING = "DENTOBOT/ApplicationShell/ExpertMode"
TASK_DOCK_GEOMETRY_SETTING = "DENTOBOT/ApplicationShell/TaskDockGeometry"
NAV_DOCK_GEOMETRY_SETTING = "DENTOBOT/ApplicationShell/NavDockGeometry"


@dataclass(frozen=True)
class WorkspaceSpec:
    workspace_id: str
    title: str
    short_title: str
    stage_indices: tuple[int, ...]
    substep_titles: tuple[str, ...]


WORKSPACE_SPECS = (
    WorkspaceSpec("case", "Case", "CASE", (0,), ("Case",)),
    WorkspaceSpec("imaging", "Imaging", "IMAGING", (1,), ("CBCT Imaging",)),
    WorkspaceSpec(
        "segmentation",
        "Segmentation",
        "SEGMENTATION",
        (2, 3),
        ("AI Segmentation", "Review and Correct"),
    ),
    WorkspaceSpec(
        "drill_planning",
        "Drill Planning",
        "DRILL PLAN",
        (4,),
        ("Entry-to-Target Trajectory",),
    ),
    WorkspaceSpec(
        "guide_design",
        "Guide Design",
        "GUIDE DESIGN",
        (5, 6, 7, 8, 9),
        (
            "Support Anatomy",
            "Rails and Docks",
            "Visible Support Surface",
            "Shell and Guide Fusion",
            "Verify and Export",
        ),
    ),
    WorkspaceSpec(
        "robot_simulation",
        "Robot Simulation",
        "ROBOT SIM",
        (10,),
        (
            "6.0 Case and Task",
            "6.1 Robot and Base",
            "6.2 Task Home",
            "6.3 Workspace and Limits",
            "6.4 Runtime and Confirmation",
            "6.5 Goal 1: Approach",
            "6.6 Goal 2: Drilling Preview",
        ),
    ),
)


def normalize_gui_mode(value: object) -> str:
    return GUI_MODE_SHELL if str(value).strip().lower() == GUI_MODE_SHELL else GUI_MODE_LEGACY


def normalize_theme(value: object) -> str:
    return "dark" if str(value).strip().lower() == "dark" else "light"


def workspace_index_for_stage(stage_index: int) -> int:
    index = int(stage_index)
    for workspace_index, spec in enumerate(WORKSPACE_SPECS):
        if index in spec.stage_indices:
            return workspace_index
    return 0


def workspace_for_stage(stage_index: int) -> WorkspaceSpec:
    return WORKSPACE_SPECS[workspace_index_for_stage(stage_index)]


class DENTOApplicationShell:
    """Own the switchable application docks and presentation preferences."""

    def __init__(
        self,
        *,
        main_window,
        module_layout,
        workflow_widget,
        ui,
        set_stage: Callable[[int], None],
        resource_path: Callable[[str], str],
        on_mode_requested: Callable[[str], None],
        on_substep_selected: Callable[[str, int], None],
        on_view_controls_requested: Callable[[], None],
    ) -> None:
        if qt is None:
            raise RuntimeError("Qt is required for the DENTOBOT application shell.")
        self._main_window = main_window
        self._module_layout = module_layout
        self._workflow_widget = workflow_widget
        self._ui = ui
        self._set_stage = set_stage
        self._resource_path = resource_path
        self._on_mode_requested = on_mode_requested
        self._on_substep_selected = on_substep_selected
        self._on_view_controls_requested = on_view_controls_requested
        self._settings = qt.QSettings()
        self._active = False
        self._updating_navigation = False
        self._nav_dock = None
        self._task_dock = None
        self._nav_container = None
        self._task_container = None
        self._task_layout = None
        self._workspace_buttons = []
        self._workspace_group = None
        self._substep_combo = None
        self._workspace_title = None
        self._case_label = None
        self._runtime_label = None
        self._recommendation_label = None
        self._theme_combo = None
        self._expert_checkbox = None
        self._view_button = None
        self._chrome_snapshot = []
        self._panel_dock = None
        self._current_stage = 0
        self._current_workspace_index = 0
        self._recommended_stage = 0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def theme(self) -> str:
        return normalize_theme(self._settings.value(THEME_SETTING, "light"))

    @staticmethod
    def storedGuiMode() -> str:
        if qt is None:
            return GUI_MODE_LEGACY
        return normalize_gui_mode(qt.QSettings().value(GUI_MODE_SETTING, GUI_MODE_LEGACY))

    @staticmethod
    def storeGuiMode(mode: str) -> None:
        if qt is not None:
            qt.QSettings().setValue(GUI_MODE_SETTING, normalize_gui_mode(mode))

    def activate(self, stage_index: int, recommended_stage: int) -> None:
        self._current_stage = int(stage_index)
        self._recommended_stage = int(recommended_stage)
        if self._active:
            self.syncStage(stage_index, recommended_stage)
            self._nav_dock.show()
            self._task_dock.show()
            return
        if self._main_window is None:
            raise RuntimeError("A visible Slicer main window is required for shell mode.")
        self._build()
        self._capture_chrome()
        self._module_layout.removeWidget(self._workflow_widget)
        self._workflow_widget.setParent(self._task_container)
        self._task_layout.addWidget(self._workflow_widget, 1)
        self._ui.workflowNavigationGroupBox.visible = False
        self._ui.productTitleLabel.visible = False
        self._active = True
        self.applyTheme(self.theme)
        expert = str(
            self._settings.value(EXPERT_MODE_SETTING, "false")
        ).strip().lower() in {"true", "1"}
        self._expert_checkbox.checked = expert
        self.setExpertMode(expert)
        self.syncStage(stage_index, recommended_stage)
        self._restore_dock_geometry()
        self._nav_dock.show()
        self._task_dock.show()

    def deactivate(self) -> None:
        if not self._active:
            return
        self._save_dock_geometry()
        self._restore_chrome()
        self._task_layout.removeWidget(self._workflow_widget)
        self._workflow_widget.setParent(None)
        self._module_layout.addWidget(self._workflow_widget)
        self._ui.workflowNavigationGroupBox.visible = True
        self._ui.productTitleLabel.visible = True
        self._active = False
        for dock in (self._nav_dock, self._task_dock):
            if dock is not None:
                dock.hide()
                dock.setWidget(None)
                dock.deleteLater()
        self._nav_dock = None
        self._task_dock = None
        self._nav_container = None
        self._task_container = None
        self._task_layout = None
        self._workspace_buttons = []
        self._workspace_group = None
        self._substep_combo = None
        self._workspace_title = None
        self._case_label = None
        self._runtime_label = None
        self._recommendation_label = None
        self._theme_combo = None
        self._expert_checkbox = None
        self._view_button = None

    def cleanup(self) -> None:
        self.deactivate()

    def _build(self) -> None:
        self._nav_dock = qt.QDockWidget("DENTOBOT Workflow", self._main_window)
        self._nav_dock.objectName = "DENTOBOTNavigationDock"
        self._nav_dock.allowedAreas = qt.Qt.LeftDockWidgetArea | qt.Qt.RightDockWidgetArea
        self._nav_dock.features = qt.QDockWidget.DockWidgetMovable
        self._nav_dock.setMinimumWidth(180)
        self._nav_dock.setMaximumWidth(260)

        nav = qt.QWidget(self._nav_dock)
        nav.objectName = "DENTOBOTNavigationPanel"
        nav_layout = qt.QVBoxLayout(nav)
        nav_layout.setContentsMargins(10, 12, 10, 12)
        nav_layout.setSpacing(7)
        brand = qt.QLabel("DENTOBOT", nav)
        brand.objectName = "DENTOBOTBrandLabel"
        brand.setProperty("dentobotRole", "brand")
        subtitle = qt.QLabel("RESEARCH WORKFLOW", nav)
        subtitle.objectName = "DENTOBOTBrandSubtitle"
        subtitle.setProperty("dentobotRole", "muted")
        nav_layout.addWidget(brand)
        nav_layout.addWidget(subtitle)

        self._workspace_group = qt.QButtonGroup(nav)
        self._workspace_group.exclusive = True
        for workspace_index, spec in enumerate(WORKSPACE_SPECS):
            button = qt.QPushButton(f"{workspace_index + 1}   {spec.title}", nav)
            button.objectName = f"DENTOBOTWorkspace_{spec.workspace_id}"
            button.checkable = True
            button.enabled = True
            button.toolTip = (
                f"Open {spec.title} for inspection or continuation. Restored "
                "cases keep every workspace selectable; task actions validate "
                "their own saved prerequisites."
            )
            button.setProperty("dentobotRole", "workspace")
            button.setMinimumHeight(42)
            button.clicked.connect(
                lambda checked=False, index=workspace_index: self._on_workspace_clicked(index)
            )
            self._workspace_group.addButton(button, workspace_index)
            self._workspace_buttons.append(button)
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        self._recommendation_label = qt.QLabel(nav)
        self._recommendation_label.objectName = "DENTOBOTRecommendationLabel"
        self._recommendation_label.wordWrap = True
        self._recommendation_label.setProperty("dentobotRole", "status")
        nav_layout.addWidget(self._recommendation_label)
        self._nav_container = nav
        self._nav_dock.setWidget(nav)

        self._task_dock = qt.QDockWidget("DENTOBOT Task", self._main_window)
        self._task_dock.objectName = "DENTOBOTTaskDock"
        self._task_dock.allowedAreas = qt.Qt.LeftDockWidgetArea | qt.Qt.RightDockWidgetArea
        self._task_dock.features = qt.QDockWidget.DockWidgetMovable
        self._task_dock.setMinimumWidth(390)
        self._task_dock.setMaximumWidth(620)

        task = qt.QWidget(self._task_dock)
        task.objectName = "DENTOBOTTaskPanel"
        task_layout = qt.QVBoxLayout(task)
        task_layout.setContentsMargins(10, 10, 10, 8)
        task_layout.setSpacing(6)

        header = qt.QWidget(task)
        header.objectName = "DENTOBOTHeader"
        header_layout = qt.QGridLayout(header)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setHorizontalSpacing(8)
        header_layout.setVerticalSpacing(3)
        self._workspace_title = qt.QLabel("CASE", header)
        self._workspace_title.objectName = "DENTOBOTWorkspaceTitle"
        self._workspace_title.setProperty("dentobotRole", "heading")
        self._case_label = qt.QLabel("Case: Untitled", header)
        self._case_label.objectName = "DENTOBOTCaseLabel"
        self._case_label.setProperty("dentobotRole", "muted")
        self._runtime_label = qt.QLabel("SIMULATION / RESEARCH ONLY", header)
        self._runtime_label.objectName = "DENTOBOTRuntimeLabel"
        self._runtime_label.setProperty("dentobotRole", "warning")
        self._runtime_label.alignment = qt.Qt.AlignRight | qt.Qt.AlignVCenter
        header_layout.addWidget(self._workspace_title, 0, 0)
        header_layout.addWidget(self._runtime_label, 0, 1)
        header_layout.addWidget(self._case_label, 1, 0, 1, 2)
        header_layout.setColumnStretch(0, 1)
        task_layout.addWidget(header)

        controls = qt.QWidget(task)
        controls.objectName = "DENTOBOTShellControls"
        controls_layout = qt.QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(5)
        self._substep_combo = qt.QComboBox(controls)
        self._substep_combo.objectName = "DENTOBOTSubstepComboBox"
        self._substep_combo.toolTip = (
            "Open any substep in this workspace. Navigation does not change "
            "case lineage; unavailable actions explain their own prerequisites."
        )
        self._substep_combo.currentIndexChanged.connect(self._on_substep_changed)
        controls_layout.addWidget(self._substep_combo, 1)
        self._view_button = qt.QPushButton("Views", controls)
        self._view_button.objectName = "DENTOBOTViewControlsButton"
        self._view_button.toolTip = (
            "Open recommended views, grouped dental masks, and advanced "
            "display controls without leaving the current workspace."
        )
        self._view_button.clicked.connect(
            lambda checked=False: self._on_view_controls_requested()
        )
        controls_layout.addWidget(self._view_button)
        self._theme_combo = qt.QComboBox(controls)
        self._theme_combo.objectName = "DENTOBOTThemeComboBox"
        self._theme_combo.addItem("Light", "light")
        self._theme_combo.addItem("Dark", "dark")
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        controls_layout.addWidget(self._theme_combo)
        self._expert_checkbox = qt.QCheckBox("Expert", controls)
        self._expert_checkbox.objectName = "DENTOBOTExpertModeCheckBox"
        self._expert_checkbox.toolTip = (
            "Show normal Slicer menus, toolbars, module selector, and developer modules."
        )
        self._expert_checkbox.toggled.connect(self.setExpertMode)
        controls_layout.addWidget(self._expert_checkbox)
        legacy_button = qt.QPushButton("Legacy UI", controls)
        legacy_button.objectName = "DENTOBOTLegacyModeButton"
        legacy_button.toolTip = "Return to the current eleven-stage module interface."
        legacy_button.clicked.connect(
            lambda checked=False: self._on_mode_requested(GUI_MODE_LEGACY)
        )
        controls_layout.addWidget(legacy_button)
        task_layout.addWidget(controls)

        separator = qt.QFrame(task)
        separator.frameShape = qt.QFrame.HLine
        separator.frameShadow = qt.QFrame.Sunken
        task_layout.addWidget(separator)
        self._task_container = task
        self._task_layout = task_layout
        self._task_dock.setWidget(task)

        self._main_window.addDockWidget(qt.Qt.LeftDockWidgetArea, self._nav_dock)
        self._main_window.addDockWidget(qt.Qt.RightDockWidgetArea, self._task_dock)

    def _on_workspace_clicked(self, workspace_index: int) -> None:
        if self._updating_navigation:
            return
        spec = WORKSPACE_SPECS[int(workspace_index)]
        target = (
            self._recommended_stage
            if self._recommended_stage in spec.stage_indices
            else spec.stage_indices[0]
        )
        self._set_stage(target)

    def _on_substep_changed(self, substep_index: int) -> None:
        if self._updating_navigation or substep_index < 0:
            return
        spec = workspace_for_stage(self._current_stage)
        if len(spec.stage_indices) == len(spec.substep_titles) and int(substep_index) < len(spec.stage_indices):
            self._set_stage(spec.stage_indices[int(substep_index)])
        self._on_substep_selected(spec.workspace_id, int(substep_index))

    def syncStage(self, stage_index: int, recommended_stage: Optional[int] = None) -> None:
        if not self._active:
            return
        previous_workspace = self._current_workspace_index
        prior_substep = (
            int(self._substep_combo.currentIndex)
            if self._substep_combo is not None
            else 0
        )
        self._current_stage = int(stage_index)
        if recommended_stage is not None:
            self._recommended_stage = int(recommended_stage)
        workspace_index = workspace_index_for_stage(self._current_stage)
        spec = WORKSPACE_SPECS[workspace_index]
        self._current_workspace_index = workspace_index
        self._updating_navigation = True
        try:
            self._workspace_buttons[workspace_index].checked = True
            self._workspace_title.text = spec.short_title
            self._substep_combo.clear()
            for title in spec.substep_titles:
                self._substep_combo.addItem(title)
            substep_index = (
                spec.stage_indices.index(self._current_stage)
                if len(spec.stage_indices) == len(spec.substep_titles)
                else (prior_substep if previous_workspace == workspace_index else 0)
            )
            substep_index = max(0, min(substep_index, len(spec.substep_titles) - 1))
            self._substep_combo.currentIndex = substep_index
            self._substep_combo.visible = len(spec.substep_titles) > 1
            recommended = workspace_for_stage(self._recommended_stage)
            self._recommendation_label.text = (
                f"Recommended next\n{recommended.title}\n"
                "All workspaces remain selectable"
            )
            for index, button in enumerate(self._workspace_buttons):
                button.setProperty(
                    "dentobotRecommended",
                    index == workspace_index_for_stage(self._recommended_stage),
                )
                button.style().unpolish(button)
                button.style().polish(button)
        finally:
            self._updating_navigation = False
        self._on_substep_selected(spec.workspace_id, substep_index)

    def updateCaseAndRuntime(self, case_name: str, runtime_text: str = "") -> None:
        if self._case_label is not None:
            self._case_label.text = f"Case: {case_name.strip() or 'Untitled'}"
        if self._runtime_label is not None:
            self._runtime_label.text = runtime_text or "SIMULATION / RESEARCH ONLY"

    def _on_theme_changed(self, index: int) -> None:
        if self._updating_navigation or index < 0:
            return
        theme = str(self._theme_combo.itemData(index) or "light")
        self.applyTheme(theme)

    def applyTheme(self, theme: str) -> None:
        theme = normalize_theme(theme)
        self._settings.setValue(THEME_SETTING, theme)
        path = Path(self._resource_path(f"Themes/dentobot-{theme}.qss"))
        stylesheet = path.read_text(encoding="utf-8") if path.is_file() else ""
        for widget in (self._nav_container, self._task_container):
            if widget is not None:
                widget.styleSheet = stylesheet
        if self._theme_combo is not None:
            self._updating_navigation = True
            try:
                desired = self._theme_combo.findData(theme)
                self._theme_combo.currentIndex = max(0, desired)
            finally:
                self._updating_navigation = False

    def _capture_chrome(self) -> None:
        self._chrome_snapshot = []
        menu_bar = self._main_window.menuBar()
        if menu_bar is not None:
            self._chrome_snapshot.append((menu_bar, bool(menu_bar.visible)))
        for toolbar in self._main_window.findChildren("QToolBar"):
            self._chrome_snapshot.append((toolbar, bool(toolbar.visible)))
        self._panel_dock = self._main_window.findChild(
            "QDockWidget",
            "PanelDockWidget",
        )
        if self._panel_dock is not None:
            self._chrome_snapshot.append(
                (self._panel_dock, bool(self._panel_dock.visible))
            )

    def setExpertMode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        self._settings.setValue(EXPERT_MODE_SETTING, enabled)
        if enabled:
            for widget, was_visible in self._chrome_snapshot:
                widget.visible = was_visible
        else:
            for widget, _was_visible in self._chrome_snapshot:
                widget.visible = False
        if self._nav_dock is not None:
            self._nav_dock.visible = True
        if self._task_dock is not None:
            self._task_dock.visible = True

    def _restore_chrome(self) -> None:
        for widget, was_visible in self._chrome_snapshot:
            try:
                widget.visible = was_visible
            except RuntimeError:
                pass
        self._chrome_snapshot = []

    def _save_dock_geometry(self) -> None:
        if self._nav_dock is not None:
            self._settings.setValue(
                NAV_DOCK_GEOMETRY_SETTING,
                self._nav_dock.saveGeometry(),
            )
        if self._task_dock is not None:
            self._settings.setValue(
                TASK_DOCK_GEOMETRY_SETTING,
                self._task_dock.saveGeometry(),
            )

    def _restore_dock_geometry(self) -> None:
        nav_geometry = self._settings.value(NAV_DOCK_GEOMETRY_SETTING)
        task_geometry = self._settings.value(TASK_DOCK_GEOMETRY_SETTING)
        if nav_geometry and self._nav_dock is not None:
            self._nav_dock.restoreGeometry(nav_geometry)
        if task_geometry and self._task_dock is not None:
            self._task_dock.restoreGeometry(task_geometry)
