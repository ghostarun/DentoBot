from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "DENTOWorkflow/Resources/Python"))
from DENTOStep6State import JOINT_NAMES


RUNNER = Path(__file__).with_name("run_dentobot_tcp_workbench_headed.py")
JOINTS = dict.fromkeys(JOINT_NAMES, 0.0)


class Rect:
    def __init__(self, x=1, y=2, width=30, height=20):
        self.x, self.y, self.width, self.height = x, y, width, height


class Layout:
    def __init__(self, parent=None):
        self.parent = parent
        self.widgets = []
        self.events = []

    def addWidget(self, widget):
        if widget not in self.widgets:
            self.widgets.append(widget)
            self.events.append(("add", widget))

    def removeWidget(self, widget):
        if widget in self.widgets:
            self.widgets.remove(widget)
            self.events.append(("remove", widget))


class Control:
    def __init__(self, name="", title="", *, visible=True, enabled=True):
        self._object_name = name
        self._title = title
        self.visible = visible
        self.enabled = enabled
        self.parent = None
        self.children = []
        self.deleted = False
        self._layout = None
        self.ui_events = []
        self.event_filters = []

    def geometry(self):
        return Rect()

    def installEventFilter(self, observer):
        self.event_filters.append(observer)

    def removeEventFilter(self, observer):
        if observer in self.event_filters:
            self.event_filters.remove(observer)

    def dispatch_event(self, event):
        for observer in tuple(self.event_filters):
            observer.eventFilter(self, event)

    def objectName(self):
        return self._object_name

    def setObjectName(self, name):
        self._object_name = str(name)
        self.ui_events.append(("setObjectName", self._object_name))

    def title(self):
        return self._title

    def isVisible(self):
        return self.visible

    def isEnabled(self):
        return self.enabled

    def setFocus(self, *_args):
        Application.focus = self
        self.ui_events.append(("setFocus",))
        Application.focus_events.append(("focus", self))

    def deleteLater(self):
        self.deleted = True
        self.ui_events.append(("deleteLater",))
        Application.focus_events.append(("delete", self))
        if Application.focus is self:
            Application.focus = None

    def show(self):
        self.visible = True
        self.ui_events.append(("show",))

    def hide(self):
        self.visible = False
        self.ui_events.append(("hide",))

    def setParent(self, parent):
        if self.parent is not None and hasattr(self.parent, "children") and self in self.parent.children:
            self.parent.children.remove(self)
        self.parent = parent
        if parent is not None and hasattr(parent, "children") and self not in parent.children:
            parent.children.append(self)
        self.panel = getattr(parent, "panel", None)
        self.ui_events.append(("setParent", parent))

    def layout(self):
        if self._layout is None:
            self._layout = Layout(self)
        return self._layout


class CheckBox(Control):
    def __init__(self, *args, on_click=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.checked = False
        self.on_click = on_click

    def click(self):
        self.checked = not self.checked
        if self.on_click:
            self.on_click(self.checked)


class LineEdit(Control):
    created = []

    def __init__(self, *args, **kwargs):
        parent = kwargs.pop("parent", None)
        name = kwargs.pop("name", "")
        title = kwargs.pop("title", "")
        visible = kwargs.pop("visible", True)
        enabled = kwargs.pop("enabled", True)
        if args:
            if isinstance(args[0], Control):
                parent = args[0]
            else:
                name = args[0]
                if len(args) > 1 and isinstance(args[1], Control):
                    parent = args[1]
        super().__init__(name, title, visible=visible, enabled=enabled)
        self.parent = parent
        self._text = ""
        self.parent_at_creation = parent
        self.panel = getattr(parent, "panel", None)
        if parent is not None and hasattr(parent, "children"):
            parent.children.append(self)
        self.created.append(self)

    def inherits(self, class_name):
        return class_name == "QLineEdit"

    def setText(self, value):
        self._text = str(value)
        self.ui_events.append(("setText", self._text))

    def text(self):
        return self._text

    def clear(self):
        self._text = ""


class SpinBox(Control):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value = 0.1
        self._line_edit = LineEdit("stepLineEdit", parent=self)

    def findChild(self, kind):
        return self._line_edit if kind is LineEdit else None

    def inherits(self, class_name):
        return class_name == "QAbstractSpinBox"


class Button(Control):
    def __init__(self, *args, on_click=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.on_click = on_click

    def click(self):
        if self.enabled and self.on_click:
            self.on_click()


class Shortcut:
    def __init__(self):
        self.autoRepeat = False
        self.enabled = False


class Matrix:
    def __init__(self):
        self.values = [[float(r == c) for c in range(4)] for r in range(4)]

    def Identity(self):
        self.values = [[float(r == c) for c in range(4)] for r in range(4)]

    def GetElement(self, row, column):
        return self.values[row][column]

    def SetElement(self, row, column, value):
        self.values[row][column] = float(value)


class DisplayNode:
    _next_id = 0

    def __init__(self, *, visible=True, editor_visibility=False, scene=None, name=""):
        type(self)._next_id += 1
        self.name = name
        self.node_id = f"display-{type(self)._next_id}"
        self.scene = scene
        self.visible = visible
        self.editor_visibility = editor_visibility

    def GetVisibility(self):
        return self.visible

    def GetEditorVisibility(self):
        return self.editor_visibility

    def GetName(self):
        return self.name

    def SetName(self, name):
        self.name = str(name)

    def GetID(self):
        return self.node_id

    def GetClassName(self):
        return "vtkMRMLTransformDisplayNode"

    def IsA(self, class_name):
        return class_name in {"vtkMRMLDisplayNode", "vtkMRMLTransformDisplayNode"}

    def GetScene(self):
        return self.scene


class Goal:
    _next_id = 0

    def __init__(self, scene, *, visible=True, editor_visibility=False, name="ProbeSphere_Transform"):
        type(self)._next_id += 1
        self.name = name
        self.node_id = f"transform-{type(self)._next_id}"
        self.scene = scene
        self.matrix = Matrix()
        self.display_node = DisplayNode(
            visible=visible, editor_visibility=editor_visibility
        )
        self.display_node.scene = scene
        self.display_node.SetName(name + "_Display")

    def GetName(self):
        return self.name

    def SetName(self, name):
        self.name = str(name)
        self.display_node.SetName(self.name + "_Display")

    def GetID(self):
        return self.node_id

    def GetClassName(self):
        return "vtkMRMLLinearTransformNode"

    def IsA(self, class_name):
        return class_name in {"vtkMRMLTransformNode", "vtkMRMLLinearTransformNode"}

    def GetScene(self):
        return self.scene

    def GetDisplayNode(self):
        return self.display_node

    def GetMatrixTransformToParent(self, target):
        for row in range(4):
            for column in range(4):
                target.SetElement(row, column, self.matrix.GetElement(row, column))

    def SetMatrixTransformToParent(self, matrix):
        self.matrix = Matrix()
        for row in range(4):
            for column in range(4):
                self.matrix.SetElement(row, column, matrix[row][column])


class Scene:
    def __init__(self):
        self.nodes = {}

    def GetFirstNodeByName(self, name):
        return self.nodes.get(name)

    def GetNumberOfNodes(self):
        return len(self.nodes)

    def GetNthNode(self, index):
        return tuple(self.nodes.values())[index]

    def AddNode(self, node):
        return self.add_node(node)

    def add_node(self, node):
        name = str(node.GetName())
        base_name = name
        suffix = 1
        while name in self.nodes:
            name = f"{base_name}_{suffix}"
            suffix += 1
        setter = getattr(node, "SetName", None)
        if callable(setter):
            setter(name)
        if hasattr(node, "scene"):
            node.scene = self
        self.nodes[name] = node
        return node

    def RemoveNode(self, node):
        for name, current in tuple(self.nodes.items()):
            if current is node:
                del self.nodes[name]
                if hasattr(node, "scene"):
                    node.scene = None
                return


class ProbeModel:
    _next_id = 0

    def __init__(self, scene, *, name="ProbeSphere"):
        type(self)._next_id += 1
        self.name = name
        self.node_id = f"model-{type(self)._next_id}"
        self.scene = scene

    def GetName(self):
        return self.name

    def SetName(self, name):
        self.name = str(name)

    def GetID(self):
        return self.node_id

    def GetClassName(self):
        return "vtkMRMLModelNode"

    def IsA(self, class_name):
        return class_name == "vtkMRMLModelNode"

    def GetScene(self):
        return self.scene


class NativeLogic:
    def __init__(self):
        self.obsNode = None
        self.obsTag = None
        self.last_ik_solution = ()


class ScrollBar:
    minimum = 0
    maximum = 80
    value = 10
    pageStep = 20


class ScrollArea:
    def ensureWidgetVisible(self, *_args):
        pass

    def verticalScrollBar(self):
        return ScrollBar()


class App:
    def __init__(self):
        self.view = Control("view")

    def processEvents(self):
        pass

    def layoutManager(self):
        return SimpleNamespace(threeDWidget=lambda _index: SimpleNamespace(
            threeDView=lambda: self.view
        ))


def mouse_event(event_type, *, buttons=0, button=0):
    return SimpleNamespace(
        type=lambda: event_type,
        buttons=lambda: buttons,
        button=lambda: button,
    )


class Application:
    focus = None
    focus_events = []

    @classmethod
    def focusWidget(cls):
        return cls.focus

    @staticmethod
    def sendEvent(*_args):
        return True


class FakeQTest:
    events = []

    @staticmethod
    def keyClick(target, key, modifiers):
        focus = Application.focus
        FakeQTest.events.append((target, focus, getattr(focus, "parent", None), key, modifiers))
        panel = getattr(focus, "panel", None)
        if panel is None:
            parent = getattr(focus, "parent", None)
            panel = getattr(parent, "panel", None)
        if panel is None:
            panel = getattr(target, "panel", None)
        # A real QLineEdit consumes arrow-key input while it has focus, so the
        # application's enabled TCP shortcuts do not receive that key event.
        if isinstance(focus, LineEdit):
            return
        if isinstance(focus, SpinBox) and key == 1:
            focus.value += 0.1
        if panel is None:
            return
        mapping = {
            (2, 0): (False, 0, 1.0),
            (3, 1): (True, 1, 1.0),
            (2, 2): (True, 2, 1.0),
        }
        key = mapping.get((key, modifiers))
        if key and panel.tcpKeyboardEnabledCheckBox.checked:
            panel.tcpCartesianNudgeButtons[key].click()


class Harness:
    def __init__(self, native_solution=None):
        Application.focus = None
        Application.focus_events = []
        FakeQTest.events = []
        LineEdit.created = []
        Goal._next_id = 0
        DisplayNode._next_id = 0
        ProbeModel._next_id = 0
        self.scene = Scene()
        self.logic = NativeLogic()
        self.accepted = dict(JOINTS)
        self.native_drag = False
        self._passive_goal_at_drag_start = None
        self.qt = SimpleNamespace(
            QObject=type("QObject", (), {"__init__": lambda self, *_args: None}),
            QApplication=Application,
            QTest=FakeQTest,
            QLineEdit=LineEdit,
            QPoint=lambda *_args: SimpleNamespace(x=lambda: 0, y=lambda: 0),
            QEvent=SimpleNamespace(MouseMove=1, MouseButtonRelease=2),
            Qt=SimpleNamespace(
                Key_Right=2,
                Key_Up=3,
                NoModifier=0,
                ControlModifier=1,
                ShiftModifier=2,
                LeftButton=1,
                RightButton=2,
            ),
        )
        self.slicer = SimpleNamespace(
            mrmlScene=self.scene,
            app=App(),
            util=SimpleNamespace(
                getNode=self.get_node,
                mainWindow=lambda: None,
                selectModule=lambda _name: None,
                getModuleWidget=lambda _name: self.widget,
            ),
        )
        self.bridge = ModuleType("DENTOROS2Bridge")
        self.bridge.ROS2_JOINT_SI_ORDER = JOINT_NAMES
        self.bridge._native_tcp_drag_enabled = False
        self.bridge.get_motion_control_logic = lambda: self.logic
        self.bridge.last_accepted_joint_positions_si = lambda: dict(self.accepted)
        self.bridge.monitored_joint_positions_si = lambda: dict(self.accepted)
        self.bridge.set_moveit_tcp_goal_matrix = self.set_goal
        self.bridge.connect_dentobot_motion_control = lambda *_args, **_kwargs: (object(), "ok")
        self.native_solution = tuple(JOINTS.values()) if native_solution is None else native_solution
        self._build_panel()
        self.widget = SimpleNamespace(
            _robotSimulationPanel=self.panel,
            _robotWorkflowFacade=self.facade,
            _step6MotionPlan=None,
            _workflowContentScrollArea=ScrollArea(),
            logic=SimpleNamespace(ensureRobotBaseTransform=lambda _base: "base"),
            _parameterNode=SimpleNamespace(robotBaseTransform="base"),
            _setWorkflowStage=lambda _index: None,
            _workflowStageEntries=lambda: ("step1", "step6"),
            _refreshShellRobotCapabilities=lambda: None,
            _updateStep6PlanningUi=lambda: None,
            _configureRobotSimulationShellSubstep=self.set_substep,
        )
        self.widget._configureRobotSimulationShellSubstep(3)
        self.module = self._load_runner()
        self.module._process_events = lambda _seconds=0.0, monitor=None: (
            monitor() if monitor else None
        )
        self.module._wait_goal_change = self.wait_goal_change

    def _load_runner(self):
        sys.modules["qt"] = self.qt
        sys.modules["slicer"] = self.slicer
        sys.modules["vtk"] = SimpleNamespace(vtkMatrix4x4=Matrix)
        sys.modules["DENTOROS2Bridge"] = self.bridge
        spec = importlib.util.spec_from_file_location("tcp_probe_host_test", RUNNER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def get_node(self, name):
        if name not in self.scene.nodes:
            raise KeyError(name)
        return self.scene.nodes[name]

    def add_goal_transform(
        self, *, scene=None, visible=True, editor_visibility=False,
        name="ProbeSphere_Transform",
    ):
        goal = Goal(
            self.scene if scene is None else scene,
            visible=visible,
            editor_visibility=editor_visibility,
            name=name,
        )
        self.scene.nodes[goal.GetName()] = goal
        self.scene.nodes[goal.GetDisplayNode().GetName()] = goal.GetDisplayNode()
        return goal

    def set_goal(self, matrix):
        goal = self.scene.nodes.get("ProbeSphere_Transform")
        if goal is None:
            return False, "missing", None
        goal.SetMatrixTransformToParent(matrix)
        return True, "updated", goal

    def _nudge(self, key):
        is_rotation, axis, sign = key
        goal = self.scene.nodes["ProbeSphere_Transform"]
        matrix = goal.matrix.values
        if not is_rotation:
            matrix[axis][3] += sign * 0.1
            return
        import math

        angle = math.radians(sign * 0.1)
        cosine, sine = math.cos(angle), math.sin(angle)
        if axis == 1:
            rotation = ((cosine, 0.0, sine), (0.0, 1.0, 0.0), (-sine, 0.0, cosine))
        else:
            rotation = ((cosine, -sine, 0.0), (sine, cosine, 0.0), (0.0, 0.0, 1.0))
        old = [row[:] for row in matrix]
        for row in range(3):
            for column in range(3):
                matrix[row][column] = sum(old[row][k] * rotation[k][column] for k in range(3))

    def _build_panel(self):
        panel = SimpleNamespace()
        panel._activeSubstep = 3
        panel._tcpDragEnabled = False
        panel._tcpKeyboardShortcuts = [Shortcut() for _ in range(3)]
        panel.goalGroup = Control("goal", "TCP Workbench", visible=True)
        panel.goalGroup.panel = panel
        panel.approachGroup = Control(
            "approach", "Approach Planning & Diagnostics", visible=True
        )
        panel.previewControlGroup = Control(
            "preview", "Preview & Control", visible=False
        )
        panel.solveIkButton = Button("solve", enabled=False)
        panel.planGoalButton = Button("plan", enabled=False)
        panel.tcpTranslationStepMm = SpinBox("translation-step")
        panel.tcpRotationStepDeg = SpinBox("rotation-step")
        panel.tcpCartesianNudgeButtons = {}
        for is_rotation, axis in ((False, 0), (False, 1), (False, 2), (True, 1), (True, 2)):
            for sign in (-1.0, 1.0):
                key = (is_rotation, axis, sign)
                button = Button(
                    f"nudge-{key}",
                    enabled=False,
                    on_click=lambda key=key: self._nudge(key),
                )
                button.panel = panel
                panel.tcpCartesianNudgeButtons[key] = button
        panel.tcpDragEnabledCheckBox = CheckBox(
            "drag",
            enabled=True,
            on_click=lambda checked: self._toggle_drag(panel, checked),
        )
        panel.tcpKeyboardEnabledCheckBox = CheckBox(
            "keyboard",
            enabled=False,
            on_click=lambda checked: self._toggle_keyboard(panel, checked),
        )
        panel.goalStatusLabel = SimpleNamespace(text="TCP review ready")
        panel.draft = dict(JOINTS)
        panel.manualJogJointPositionsSi = lambda: dict(panel.draft)
        panel.solveIkButton.on_click = lambda: self._solve(panel)
        self.panel = panel
        self.facade = SimpleNamespace(
            currentRobotState=self.current_state,
            capabilities=lambda: SimpleNamespace(
                simulation_only=True,
                connected=True,
                planning_ready=True,
                ik_available=True,
                collision_check_available=True,
                planning_scene_synchronized=True,
            ),
            previewActive=False,
            returnHomeRequired=False,
            motionPlan=None,
        )

    def _toggle_drag(self, panel, checked):
        panel._tcpDragEnabled = checked
        self.bridge._native_tcp_drag_enabled = checked
        if checked:
            self._passive_goal_at_drag_start = self.scene.nodes.get(
                "ProbeSphere_Transform"
            )
            goal = Goal(self.scene)
            self.scene.nodes["ProbeSphere_Transform"] = goal
            self.scene.nodes[goal.GetDisplayNode().GetName()] = goal.GetDisplayNode()
            self.scene.nodes["ProbeSphere"] = ProbeModel(self.scene)
            self.logic.obsNode, self.logic.obsTag = goal, 1
            panel.solveIkButton.enabled = True
            for button in panel.tcpCartesianNudgeButtons.values():
                button.enabled = True
            panel.tcpKeyboardEnabledCheckBox.enabled = True
        else:
            self.scene.nodes.clear()
            if self._passive_goal_at_drag_start is not None:
                self.scene.nodes["ProbeSphere_Transform"] = self._passive_goal_at_drag_start
                self.scene.nodes[
                    self._passive_goal_at_drag_start.GetDisplayNode().GetName()
                ] = self._passive_goal_at_drag_start.GetDisplayNode()
                self.logic.obsNode = self._passive_goal_at_drag_start
            else:
                self.logic.obsNode = None
            self.logic.obsTag = None
            self._passive_goal_at_drag_start = None
            panel.solveIkButton.enabled = False
            panel.tcpKeyboardEnabledCheckBox.checked = False
            panel.tcpKeyboardEnabledCheckBox.enabled = False
            for item in panel._tcpKeyboardShortcuts:
                item.enabled = False
            for button in panel.tcpCartesianNudgeButtons.values():
                button.enabled = False

    def _toggle_keyboard(self, panel, checked):
        for item in panel._tcpKeyboardShortcuts:
            item.enabled = checked

    def _solve(self, panel):
        self.logic.last_ik_solution = self.native_solution
        if len(self.native_solution) == 5:
            panel.draft = dict(zip(JOINT_NAMES, self.native_solution))
        panel.goalStatusLabel.text = "authoritative MoveIt static validity"

    def current_state(self):
        return SimpleNamespace(
            joint_positions_si=dict(self.accepted),
            ros_motion_active=True,
            base_locked=True,
            preview_active=False,
            return_home_required=False,
            has_motion_plan=False,
            scene_kind="case",
        )

    def set_substep(self, index):
        self.panel._activeSubstep = index
        self.panel.goalGroup.visible = index == 3
        self.panel.approachGroup.visible = index == 3
        self.panel.previewControlGroup.visible = index == 4

    def wait_goal_change(self, goal, before, timeout_sec=10.0, monitor=None):
        if monitor:
            monitor()
        after = self.module._matrix(goal)
        if self.module._changed(before, after):
            import time

            return after, time.monotonic_ns()
        return after, None


@pytest.fixture
def harness(monkeypatch):
    del monkeypatch
    return Harness()


def test_drag_observer_requires_left_release_after_drag(harness, monkeypatch):
    observer = harness.module._DragEventObserver(Control("view"))
    ticks = iter((100, 200))
    monkeypatch.setattr(harness.module.time, "monotonic_ns", lambda: next(ticks))

    observer.eventFilter(
        None,
        mouse_event(
            harness.qt.QEvent.MouseButtonRelease,
            button=harness.qt.Qt.LeftButton,
        ),
    )
    assert observer.first_drag_event_ns is None
    assert observer.left_release_event_ns is None

    observer.eventFilter(
        None,
        mouse_event(harness.qt.QEvent.MouseMove, buttons=harness.qt.Qt.LeftButton),
    )
    first_drag_ns = observer.first_drag_event_ns
    assert first_drag_ns == 100
    assert observer.left_release_event_ns is None

    observer.eventFilter(
        None,
        mouse_event(harness.qt.QEvent.MouseMove, buttons=harness.qt.Qt.LeftButton),
    )
    observer.eventFilter(
        None,
        mouse_event(
            harness.qt.QEvent.MouseButtonRelease,
            button=harness.qt.Qt.RightButton,
        ),
    )
    assert observer.first_drag_event_ns == first_drag_ns
    assert observer.left_release_event_ns is None

    observer.eventFilter(
        None,
        mouse_event(
            harness.qt.QEvent.MouseButtonRelease,
            button=harness.qt.Qt.LeftButton,
        ),
    )
    assert observer.left_release_event_ns == 200


def test_mouse_callback_evidence_matches_qt_events_and_preserves_accepted_state(
    harness, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        harness.module,
        "_rendezvous",
        lambda _view, baseline: {"goal_before": baseline},
    )
    view = harness.slicer.app.view
    queued_releases = [
        mouse_event(
            harness.qt.QEvent.MouseMove,
            buttons=harness.qt.Qt.LeftButton,
        ),
        mouse_event(
            harness.qt.QEvent.MouseButtonRelease,
            button=harness.qt.Qt.RightButton,
        ),
        mouse_event(
            harness.qt.QEvent.MouseButtonRelease,
            button=harness.qt.Qt.LeftButton,
        ),
    ]

    def process_event_turn():
        if queued_releases:
            view.dispatch_event(queued_releases.pop(0))

    monkeypatch.setattr(harness.module, "_process_event_turn", process_event_turn)

    def drag_callback(context):
        view.dispatch_event(
            mouse_event(
                harness.qt.QEvent.MouseMove,
                buttons=harness.qt.Qt.LeftButton,
            )
        )
        observer = view.event_filters[0]
        first_drag_ns = observer.first_drag_event_ns
        assert first_drag_ns is not None
        assert observer.left_release_event_ns is None
        moved_goal = [row[:] for row in context["rendezvous"]["goal_before"]]
        moved_goal[0][3] += 0.1
        harness.set_goal(moved_goal)

        delivery = context["wait_for_delivery"]()
        assert observer.first_drag_event_ns == first_drag_ns
        assert observer.left_release_event_ns == delivery["release_monotonic_ns"]
        return {
            "method": "host_qt_event_regression",
            **delivery,
        }

    result = harness.module.run_case_bound_tcp_probe(
        harness.widget,
        harness.panel,
        harness.facade,
        tmp_path,
        lambda stage: {"stage": stage},
        mouse_drag_callback=drag_callback,
    )

    sample = next(item for item in result["latency_samples"]
                  if item["observation"] == "mouse_drag")
    delivery = sample["delivery"]
    assert result["mouse_drag"]["status"] == "PASS"
    assert delivery["event_monotonic_ns"] == sample["input_monotonic_ns"]
    assert delivery["release_monotonic_ns"] == sample["release_monotonic_ns"]
    assert delivery["release_monotonic_ns"] >= delivery["event_monotonic_ns"]
    assert sample["timing_scope"] == "first_drag_event_to_goal_read_after_left_release"
    assert "Not first-paint latency" in result["latency_interpretation"]
    assert result["accepted_state"]["unchanged"] is True
    assert result["accepted_monitored_displayed_before"] == result[
        "accepted_monitored_displayed_after"
    ]
    assert harness.accepted == JOINTS
    assert queued_releases == []


def test_mouse_callback_fails_within_deadline_when_release_is_missing(
    harness, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        harness.module,
        "_rendezvous",
        lambda _view, baseline: {"goal_before": baseline},
    )
    monkeypatch.setattr(harness.module, "_process_event_turn", lambda: None)
    clock = iter((0.0, harness.module.DRAG_EVENT_TIMEOUT_SEC + 1.0))
    clock_calls = []

    def monotonic():
        clock_calls.append(None)
        return next(clock)

    monkeypatch.setattr(harness.module.time, "monotonic", monotonic)

    def missing_release(context):
        harness.slicer.app.view.dispatch_event(
            mouse_event(
                harness.qt.QEvent.MouseMove,
                buttons=harness.qt.Qt.LeftButton,
            )
        )
        return context["wait_for_delivery"]()

    with pytest.raises(
        harness.module.TcpProbeError,
        match="both a Qt mouse drag and its left-button release within 30 seconds",
    ) as error:
        harness.module.run_case_bound_tcp_probe(
            harness.widget,
            harness.panel,
            harness.facade,
            tmp_path,
            lambda stage: {"stage": stage},
            mouse_drag_callback=missing_release,
        )

    assert len(clock_calls) == 2
    assert error.value.evidence["accepted_state"]["unchanged"] is True
    assert harness.accepted == JOINTS


def test_precondition_rejects_stale_scene_before_any_capture(harness):
    harness.facade.capabilities = lambda: SimpleNamespace(
        simulation_only=True,
        connected=True,
        planning_ready=True,
        ik_available=True,
        collision_check_available=True,
        planning_scene_synchronized=False,
    )
    captures = []
    with pytest.raises(harness.module.TcpProbeError, match="scene"):
        harness.module.run_case_bound_tcp_probe(
            harness.widget, harness.panel, harness.facade, Path("/tmp"),
            lambda stage: captures.append(stage),
        )
    assert captures == []
    assert harness.panel.tcpDragEnabledCheckBox.checked is False


def test_precondition_rejects_non_case_scene_before_any_capture(harness):
    harness.facade.currentRobotState = lambda: SimpleNamespace(
        ros_motion_active=True,
        base_locked=True,
        preview_active=False,
        return_home_required=False,
        has_motion_plan=False,
        scene_kind="simulation",
    )
    captures = []
    with pytest.raises(harness.module.TcpProbeError, match="case-backed"):
        harness.module.run_case_bound_tcp_probe(
            harness.widget, harness.panel, harness.facade, Path("/tmp"),
            lambda stage: captures.append(stage),
        )
    assert captures == []
    assert harness.panel.tcpDragEnabledCheckBox.checked is False


def test_case_scene_allows_same_scene_inert_workspace_goal_with_default_off_evidence(
    harness, tmp_path
):
    goal = harness.add_goal_transform(visible=True, editor_visibility=False)
    harness.logic.obsNode = goal
    assert goal.GetScene() is harness.scene
    assert goal.GetDisplayNode().GetVisibility() is True
    assert goal.GetDisplayNode().GetEditorVisibility() is False

    result = harness.module.run_case_bound_tcp_probe(
        harness.widget, harness.panel, harness.facade, tmp_path,
        lambda stage: {"stage": stage},
    )

    assert result["passive_goal_transform_before"] == {
        "present": True,
        "editor_enabled": False,
        "scene_current": True,
    }
    assert result["native_observer_before"] == {
        "target_reference_present": True,
        "target_reference_matches_passive_goal": True,
        "installed_observer": False,
        "native_drag_enabled": False,
    }
    assert result["default_off"] is True
    assert result["route_authority"] is False
    assert result["preview_started"] is False
    assert result["planner_calls"] == 0
    assert result["mouse_drag"]["status"] == "NOT_RUN"
    # The display node shares the goal's name prefix but is not itself a goal
    # transform in the runner's scene-wide typed inventory.
    assert harness.module._nodes_named("ProbeSphere_Transform") == [goal]


def test_keyboard_probe_uses_temporary_plain_editor_focus_and_removes_it(harness, tmp_path):
    result = harness.module.run_case_bound_tcp_probe(
        harness.widget,
        harness.panel,
        harness.facade,
        tmp_path,
        lambda stage: {"stage": stage},
    )

    sinks = [
        item
        for item in LineEdit.created
        if item.parent_at_creation is harness.panel.goalGroup
    ]
    assert len(sinks) == 1
    sink = sinks[0]
    assert sink.inherits("QLineEdit")
    assert sink.objectName() == "DENTOBOTTcpTextFocusProbe"
    assert sink.text() == "focus probe"
    assert sink.isVisible() is False  # The runner hides it during its finally cleanup.
    assert sink.parent is None
    assert [event[0] for event in sink.ui_events] == [
        "setObjectName", "setText", "show", "setFocus", "hide", "setParent", "deleteLater"
    ]
    delivered = [event for event in FakeQTest.events if event[1] is sink]
    assert delivered
    assert all(event[0] is sink and event[1] is sink for event in delivered)
    assert all(event[2] is harness.panel.goalGroup for event in delivered)
    layout_events = harness.panel.goalGroup.layout().events
    assert ("add", sink) in layout_events
    assert ("remove", sink) in layout_events
    assert layout_events.index(("add", sink)) < layout_events.index(("remove", sink))
    focus_event = next(
        index for index, event in enumerate(Application.focus_events)
        if event == ("focus", sink)
    )
    removal_event = next(
        index for index, event in enumerate(Application.focus_events)
        if event == ("delete", sink)
    )
    assert focus_event < removal_event
    assert sink.deleted is True
    assert sink not in harness.panel.goalGroup.layout().widgets
    assert Application.focusWidget() is not sink
    text_evidence = result["editor_focus_suppressed"]["text"]
    assert text_evidence["goal_unchanged"] is True
    assert text_evidence["delivery"]


def test_case_cleanup_retains_only_the_same_inert_passive_goal(harness, tmp_path):
    goal = harness.add_goal_transform(visible=True, editor_visibility=False)
    harness.logic.obsNode = goal
    matrix_before = [row[:] for row in goal.matrix.values]

    result = harness.module.run_case_bound_tcp_probe(
        harness.widget,
        harness.panel,
        harness.facade,
        tmp_path,
        lambda stage: {"stage": stage},
    )

    assert result["cleanup"]["goal_transform_status"] == "retained_passive"
    assert result["reentered"]["goal_transform_status"] == "retained_passive"
    assert result["cleanup"]["goal_transform_status_after_reentry"] == "retained_passive"
    assert result["cleanup"]["goal_removed_or_original_passive"] is True
    assert result["reentered"]["goal_removed_or_original_passive"] is True
    assert harness.module._nodes_named("ProbeSphere_Transform") == [goal]
    assert goal.GetScene() is harness.scene
    assert goal.GetDisplayNode().GetEditorVisibility() is False
    assert goal.matrix.values == matrix_before
    assert harness.module._nodes_named("ProbeSphere") == []
    assert harness.logic.obsTag is None
    assert harness.bridge._native_tcp_drag_enabled is False
    assert harness.panel._tcpDragEnabled is False
    assert harness.panel.tcpKeyboardEnabledCheckBox.checked is False
    assert all(not shortcut.enabled for shortcut in harness.panel._tcpKeyboardShortcuts)


def _inject_cleanup_leak(harness, goal, scenario):
    checkbox = harness.panel.tcpDragEnabledCheckBox
    original = checkbox.on_click

    def toggle_then_leak(checked):
        original(checked)
        if checked:
            return
        if scenario == "foreign_goal":
            goal.scene = Scene()
        elif scenario == "replacement_goal":
            harness.scene.nodes["ProbeSphere_Transform"] = Goal(harness.scene)
        elif scenario == "suffixed_goal":
            leaked_goal = Goal(harness.scene)
            harness.scene.AddNode(leaked_goal)
            harness.scene.AddNode(leaked_goal.GetDisplayNode())
        elif scenario == "editor_enabled":
            goal.GetDisplayNode().editor_visibility = True
        elif scenario in {"observer_tag_zero", "observer_tag_one"}:
            harness.logic.obsNode = goal
            harness.logic.obsTag = 0 if scenario == "observer_tag_zero" else 1
        elif scenario == "probe_model":
            harness.scene.nodes["ProbeSphere"] = ProbeModel(harness.scene)
        elif scenario == "suffixed_probe_model":
            harness.scene.AddNode(ProbeModel(harness.scene, name="ProbeSphere_1"))
        elif scenario == "native_drag_enabled":
            harness.bridge._native_tcp_drag_enabled = True
        elif scenario == "native_drag_unknown":
            harness.bridge._native_tcp_drag_enabled = None
        elif scenario == "keyboard_enabled":
            harness.panel.tcpKeyboardEnabledCheckBox.checked = True
        else:
            raise AssertionError(f"unknown cleanup mutation: {scenario}")

    checkbox.on_click = toggle_then_leak


@pytest.mark.parametrize(
    "scenario",
    (
        "foreign_goal",
        "replacement_goal",
        "suffixed_goal",
        "editor_enabled",
        "observer_tag_zero",
        "observer_tag_one",
        "probe_model",
        "suffixed_probe_model",
        "native_drag_enabled",
        "native_drag_unknown",
        "keyboard_enabled",
    ),
)
def test_case_cleanup_rejects_goal_observer_or_tooling_leaks(
    harness, tmp_path, scenario
):
    goal = harness.add_goal_transform(visible=True, editor_visibility=False)
    harness.logic.obsNode = goal
    _inject_cleanup_leak(harness, goal, scenario)

    with pytest.raises(harness.module.TcpProbeError):
        harness.module.run_case_bound_tcp_probe(
            harness.widget,
            harness.panel,
            harness.facade,
            tmp_path,
            lambda stage: {"stage": stage},
        )

    assert harness.panel.tcpDragEnabledCheckBox.checked is False


@pytest.mark.parametrize(
    "scenario",
    (
        "editor_visible",
        "foreign_scene",
        "probe_model",
        "observer_tag",
        "unmatched_observer_node",
        "zero_observer_tag",
        "native_drag",
    ),
)
def test_case_scene_rejects_non_inert_existing_goal_before_capture(
    harness, tmp_path, scenario
):
    goal = harness.add_goal_transform()
    if scenario == "editor_visible":
        goal.GetDisplayNode().editor_visibility = True
    elif scenario == "foreign_scene":
        goal.scene = Scene()
    elif scenario == "probe_model":
        harness.scene.nodes["ProbeSphere"] = ProbeModel(harness.scene)
    elif scenario == "observer_tag":
        harness.logic.obsNode, harness.logic.obsTag = goal, 1
    elif scenario == "unmatched_observer_node":
        harness.logic.obsNode, harness.logic.obsTag = object(), None
    elif scenario == "zero_observer_tag":
        harness.logic.obsNode, harness.logic.obsTag = goal, 0
    elif scenario == "native_drag":
        harness.bridge._native_tcp_drag_enabled = True

    captures = []
    with pytest.raises(harness.module.TcpProbeError):
        harness.module.run_case_bound_tcp_probe(
            harness.widget, harness.panel, harness.facade, tmp_path,
            lambda stage: captures.append(stage),
        )

    assert captures == []
    assert harness.panel.tcpDragEnabledCheckBox.checked is False
    assert harness.panel._tcpDragEnabled is False


def test_explicit_standalone_mode_preserves_non_case_scene(harness, tmp_path):
    harness.facade.currentRobotState = lambda: SimpleNamespace(
        joint_positions_si=dict(JOINTS),
        ros_motion_active=True,
        base_locked=True,
        preview_active=False,
        return_home_required=False,
        has_motion_plan=False,
        scene_kind="simulation",
    )
    result = harness.module.run_case_bound_tcp_probe(
        harness.widget,
        harness.panel,
        harness.facade,
        tmp_path,
        lambda stage: {"stage": stage},
        require_case_scene=False,
    )
    assert result["live_capabilities"]["scene_kind"] == "simulation"


def test_standalone_mode_still_rejects_preexisting_goal_transform(harness, tmp_path):
    goal = harness.add_goal_transform()
    captures = []

    with pytest.raises(harness.module.TcpProbeError):
        harness.module.run_case_bound_tcp_probe(
            harness.widget,
            harness.panel,
            harness.facade,
            tmp_path,
            lambda stage: captures.append(stage),
            require_case_scene=False,
        )

    assert captures == []
    assert harness.scene.nodes["ProbeSphere_Transform"] is goal
    assert harness.panel.tcpDragEnabledCheckBox.checked is False


def test_accepted_monitored_displayed_state_stays_unchanged(harness, tmp_path):
    result = harness.module.run_case_bound_tcp_probe(
        harness.widget, harness.panel, harness.facade, tmp_path,
        lambda stage: {"stage": stage},
    )
    assert result["accepted_state"]["unchanged"] is True
    assert result["accepted_monitored_displayed_before"] == result[
        "accepted_monitored_displayed_after"
    ]
    assert harness.accepted == JOINTS


def test_solve_ik_rejects_anything_but_five_joints_and_cleans_up(harness, tmp_path):
    harness.native_solution = (0.0, 1.0, 2.0, 3.0)
    with pytest.raises(harness.module.TcpProbeError, match="exactly five") as error:
        harness.module.run_case_bound_tcp_probe(
            harness.widget, harness.panel, harness.facade, tmp_path,
            lambda stage: {"stage": stage},
        )
    assert error.value.evidence["cleanup"]["default_off_after_reentry"] is True
    assert harness.panel._activeSubstep == 3
    assert not harness.panel.tcpDragEnabledCheckBox.checked


def test_cleanup_reenters_default_off_and_mouse_is_not_run(harness, tmp_path):
    result = harness.module.run_case_bound_tcp_probe(
        harness.widget, harness.panel, harness.facade, tmp_path,
        lambda stage: {"stage": stage},
    )
    assert result["mouse_drag"]["status"] == "NOT_RUN"
    assert result["cleanup"]["default_off_after_reentry"] is True
    assert result["cleanup"]["goal_transform_status"] == "removed"
    assert result["reentered"]["goal_transform_status"] == "removed"
    assert result["cleanup"]["goal_transform_status_after_reentry"] == "removed"
    assert result["cleanup"]["goal_removed_or_original_passive"] is True
    assert result["reentered"]["goal_removed_or_original_passive"] is True
    assert result["owners_by_substep"]["step6_preview"]["preview_control"]["visible"]
    assert result["owners_by_substep"]["step6_3b_after"]["planning_diagnostics"]["visible"]
    assert harness.module._nodes_named("ProbeSphere_Transform") == []
    assert harness.module._nodes_named("ProbeSphere") == []
    assert harness.logic.obsNode is None


def test_standalone_cleanup_rejects_newly_leaked_goal(harness, tmp_path):
    checkbox = harness.panel.tcpDragEnabledCheckBox
    original = checkbox.on_click

    def toggle_then_leak(checked):
        original(checked)
        if not checked:
            goal = Goal(harness.scene)
            harness.scene.AddNode(goal)
            harness.scene.AddNode(goal.GetDisplayNode())

    checkbox.on_click = toggle_then_leak
    with pytest.raises(harness.module.TcpProbeError):
        harness.module.run_case_bound_tcp_probe(
            harness.widget,
            harness.panel,
            harness.facade,
            tmp_path,
            lambda stage: {"stage": stage},
            require_case_scene=False,
        )

    assert harness.panel.tcpDragEnabledCheckBox.checked is False


def test_latency_summary_is_finite_json_evidence(harness):
    summary = harness.module._latency_summary(
        [{"latency_ms": value} for value in (1.0, 2.0, 3.0, 4.0)]
    )
    assert summary == {
        "sample_count": 4,
        "median_ms": 2.5,
        "p95_ms": 4.0,
        "max_ms": 4.0,
        "units": "ms",
    }
    json.dumps(summary, allow_nan=False)


def test_standalone_runner_delegates_to_reusable_probe(harness, tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    evidence_dir = run_dir / "evidence"
    run_dir.mkdir()
    evidence_dir.mkdir()
    result_path = run_dir / "result.json"
    writes = []
    monkeypatch.setattr(
        harness.module, "_execution_paths",
        lambda: (run_dir, evidence_dir, result_path),
    )
    monkeypatch.setattr(harness.module, "_mouse_drag_requested", lambda: False)
    monkeypatch.setattr(harness.module, "_checkout_provenance", lambda: {})
    monkeypatch.setattr(harness.module, "_native_provenance", lambda: {})
    monkeypatch.setattr(harness.module, "_process_events", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        harness.module, "_write_json",
        lambda _path, value, **_kwargs: writes.append(dict(value)),
    )
    calls = []

    def delegated(widget, panel, facade, passed_run_dir, capture_callback, *,
                  mouse_drag_callback=None, require_case_scene=True):
        calls.append((widget, panel, facade, passed_run_dir, mouse_drag_callback))
        assert callable(capture_callback)
        assert require_case_scene is False
        return {
            "captures": {"default_off": "01-default-off.png"},
            "latency_samples": [],
            "latency_summary": harness.module._latency_summary([]),
            "route_authority": False,
            "preview_started": False,
            "hardware_or_drilling_action": False,
            "planner_calls": 0,
        }

    monkeypatch.setattr(harness.module, "run_case_bound_tcp_probe", delegated)
    assert harness.module.run() == 0
    assert calls == [(
        harness.widget, harness.panel, harness.facade, run_dir, None
    )]
    assert writes[-1]["status"] == "PASS"
    assert writes[-1]["screenshots"] == {"default_off": "01-default-off.png"}


def test_standalone_binds_external_mouse_rendezvous_callback(
    harness, tmp_path, monkeypatch, capsys
):
    run_dir = tmp_path / "run"
    evidence_dir = run_dir / "evidence"
    run_dir.mkdir()
    evidence_dir.mkdir()
    result_path = run_dir / "result.json"
    monkeypatch.setattr(
        harness.module, "_execution_paths",
        lambda: (run_dir, evidence_dir, result_path),
    )
    monkeypatch.setattr(harness.module, "_mouse_drag_requested", lambda: True)
    monkeypatch.setattr(harness.module, "_checkout_provenance", lambda: {})
    monkeypatch.setattr(harness.module, "_native_provenance", lambda: {})
    monkeypatch.setattr(harness.module, "_process_events", lambda *_args, **_kwargs: None)
    callback_results = []
    callbacks = []
    wait_calls = []
    rendezvous = {"global_center_top_origin": [10, 20], "goal_before": [[1.0]]}
    delivery = {
        "delivered": True,
        "event_monotonic_ns": 123456789,
        "release_monotonic_ns": 123456790,
    }

    def delegated(widget, panel, facade, passed_run_dir, capture_callback, *,
                  mouse_drag_callback=None, require_case_scene=True):
        assert callable(capture_callback)
        assert require_case_scene is False
        callbacks.append(mouse_drag_callback)
        callback_results.append(mouse_drag_callback({
            "run_dir": str(passed_run_dir),
            "rendezvous": rendezvous,
            "wait_for_delivery": lambda: (wait_calls.append(True), delivery)[1],
        }))
        return {
            "captures": {"default_off": "01-default-off.png"},
            "latency_samples": [],
            "latency_summary": harness.module._latency_summary([]),
            "route_authority": False,
            "preview_started": False,
            "hardware_or_drilling_action": False,
            "planner_calls": 0,
        }

    monkeypatch.setattr(harness.module, "run_case_bound_tcp_probe", delegated)
    assert harness.module.run() == 0

    assert callback_results == [{
        "method": "external_xdotool_rendezvous",
        "delivered": True,
        "event_monotonic_ns": 123456789,
        "release_monotonic_ns": 123456790,
    }]
    ready_path = run_dir / "drag-ready.json"
    assert json.loads(ready_path.read_text(encoding="utf-8")) == rendezvous
    with pytest.raises(FileExistsError):
        callbacks[0]({
            "rendezvous": rendezvous,
            "wait_for_delivery": lambda: (wait_calls.append(True), delivery)[1],
        })
    assert wait_calls == [True]
    assert "DENTOBOT_TCP_DRAG_READY" in capsys.readouterr().out
