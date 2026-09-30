"""Host-only checks for reversible Workflow Focus chrome handling."""

import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "DENTOWorkflow/Resources/Python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))
LIFECYCLE = PYTHON / "dentobot_workflow/widget_lifecycle.py"

from dentobot_workflow.ui_workflow_focus import WorkflowFocusChromeController


class FakeWidget:
    def __init__(self, *, hidden=False, toolbar=False):
        self.hidden = hidden
        self.visible = not hidden
        self.toolbar = toolbar
        self.deleted = False
        self.objectName = "toolbar" if toolbar else "widget"

    def _check(self):
        if self.deleted:
            raise RuntimeError("wrapped C++ object has been deleted")

    def isHidden(self):
        self._check()
        return self.hidden

    def hide(self):
        self._check()
        self.hidden = True
        self.visible = False

    def show(self):
        self._check()
        self.hidden = False
        self.visible = True

    def inherits(self, name):
        self._check()
        return self.toolbar and name == "QToolBar"


def load_lifecycle_module(fakeSlicer):
    runtime = types.ModuleType("dentobot_workflow.runtime")
    runtime.slicer = fakeSlicer
    moduleName = "dentobot_workflow._test_widget_lifecycle"
    spec = importlib.util.spec_from_file_location(moduleName, LIFECYCLE)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"dentobot_workflow.runtime": runtime}):
        spec.loader.exec_module(module)
    return module


class WorkflowFocusControllerTest(unittest.TestCase):
    def test_repeated_apply_restores_original_explicit_hidden_state(self):
        controller = WorkflowFocusChromeController()
        originallyVisible = FakeWidget()
        originallyHidden = FakeWidget(hidden=True)

        controller.apply((originallyVisible, originallyHidden))
        originallyVisible.show()
        controller.apply((originallyVisible, originallyHidden))
        controller.restore()

        self.assertFalse(originallyVisible.isHidden())
        self.assertTrue(originallyHidden.isHidden())

    def test_deleted_widget_does_not_block_other_restoration(self):
        controller = WorkflowFocusChromeController()
        deleted = FakeWidget()
        live = FakeWidget()
        controller.apply((deleted, live))
        deleted.deleted = True

        controller.restore()

        self.assertFalse(live.isHidden())

    def test_switching_target_sets_restores_before_new_capture(self):
        controller = WorkflowFocusChromeController()
        toolbar = FakeWidget()
        logo = FakeWidget(hidden=True)

        controller.apply((toolbar, logo))
        controller.restore()
        controller.apply((logo,))
        controller.restore()

        self.assertFalse(toolbar.isHidden())
        self.assertTrue(logo.isHidden())

    def test_shell_toggle_changes_only_snapshot_toolbars(self):
        controller = WorkflowFocusChromeController()
        toolbar = FakeWidget(toolbar=True)
        initiallyHiddenToolbar = FakeWidget(hidden=True, toolbar=True)
        menu = FakeWidget()
        shell = SimpleNamespace(
            _chrome_snapshot=(
                (toolbar, True),
                (initiallyHiddenToolbar, False),
                (menu, True),
            )
        )

        controller.set_shell_toolbars_visible(shell, False)
        self.assertFalse(toolbar.visible)
        self.assertFalse(initiallyHiddenToolbar.visible)
        self.assertTrue(menu.visible)

        controller.set_shell_toolbars_visible(shell, True)
        self.assertTrue(toolbar.visible)
        self.assertFalse(initiallyHiddenToolbar.visible)
        self.assertTrue(menu.visible)

    def test_missing_named_panel_widgets_are_ignored(self):
        toolbar = FakeWidget(toolbar=True)

        class MainWindow:
            def findChildren(self, _class_name):
                return (toolbar,)

        fakeSlicer = SimpleNamespace(
            util=SimpleNamespace(
                mainWindow=lambda: MainWindow(),
                findChild=lambda _parent, _name: (_ for _ in ()).throw(IndexError()),
            )
        )
        module = load_lifecycle_module(fakeSlicer)
        widget = object.__new__(module.LifecycleWidgetMixin)
        widget._workflowFocusEntered = True
        widget._workflowSlicerToolsVisible = False
        widget._applicationShell = None
        widget._step6ExpertReturnToolbar = None
        widget._applyWorkflowFocusChrome()

        self.assertTrue(toolbar.isHidden())

    def test_lifecycle_toggle_restores_legacy_chrome_and_excludes_expert_toolbar(self):
        toolbar = FakeWidget(toolbar=True)
        initiallyHiddenToolbar = FakeWidget(hidden=True, toolbar=True)
        expertToolbar = FakeWidget(toolbar=True)
        expertToolbar.objectName = "DENTOBOTExpertReturnToolbar"
        logo = FakeWidget(hidden=True)
        helpPanel = FakeWidget()
        dataProbe = FakeWidget()
        widgets = {
            "LogoLabel": logo,
            "HelpCollapsibleButton": helpPanel,
            "DataProbeCollapsibleWidget": dataProbe,
        }

        class MainWindow:
            def findChildren(self, _class_name):
                return (toolbar, initiallyHiddenToolbar, expertToolbar)

        fakeSlicer = SimpleNamespace(
            util=SimpleNamespace(
                mainWindow=lambda: MainWindow(),
                findChild=lambda _parent, name: widgets.get(name),
            )
        )
        module = load_lifecycle_module(fakeSlicer)
        widget = object.__new__(module.LifecycleWidgetMixin)
        widget._workflowFocusEntered = True
        widget._workflowSlicerToolsVisible = False
        widget._applicationShell = None
        widget._step6ExpertReturnToolbar = expertToolbar

        widget._applyWorkflowFocusChrome()
        self.assertTrue(toolbar.isHidden())
        self.assertTrue(initiallyHiddenToolbar.isHidden())
        self.assertFalse(expertToolbar.isHidden())
        self.assertTrue(logo.isHidden())
        self.assertTrue(helpPanel.isHidden())
        self.assertTrue(dataProbe.isHidden())

        widget._setWorkflowSlicerToolsVisible(True)
        self.assertFalse(toolbar.isHidden())
        self.assertTrue(initiallyHiddenToolbar.isHidden())
        self.assertFalse(expertToolbar.isHidden())
        self.assertTrue(logo.isHidden())
        self.assertFalse(helpPanel.isHidden())
        self.assertFalse(dataProbe.isHidden())

        widget._setWorkflowSlicerToolsVisible(False)
        widget._restoreWorkflowFocusChrome()
        self.assertFalse(toolbar.isHidden())
        self.assertTrue(initiallyHiddenToolbar.isHidden())
        self.assertFalse(expertToolbar.isHidden())
        self.assertTrue(logo.isHidden())
        self.assertFalse(helpPanel.isHidden())
        self.assertFalse(dataProbe.isHidden())

    def test_lifecycle_restores_before_exit_handoff_and_shell_cleanup(self):
        source = LIFECYCLE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lifecycle = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "LifecycleWidgetMixin"
        )
        methods = {
            node.name: node
            for node in lifecycle.body
            if isinstance(node, ast.FunctionDef)
        }

        def call_line(method, attribute):
            return min(
                node.lineno
                for node in ast.walk(method)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == attribute
            )

        exitMethod = methods["exit"]
        handoffLine = next(
            node.lineno
            for node in exitMethod.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Attribute)
            and node.test.attr == "_step6ExpertDiagnosticHandoffActive"
        )
        self.assertLess(call_line(exitMethod, "_restoreWorkflowFocusChrome"), handoffLine)
        self.assertLess(handoffLine, call_line(exitMethod, "deactivate"))
        self.assertLess(
            call_line(methods["enter"], "_applyDENTOBOTGuiMode"),
            call_line(methods["enter"], "_applyWorkflowFocusChrome"),
        )
        self.assertLess(
            call_line(methods["cleanup"], "_restoreWorkflowFocusChrome"),
            call_line(methods["cleanup"], "cleanup"),
        )


    def test_more_menu_sync_blocks_callbacks_and_disables_unavailable_gui(self):
        source = (PYTHON / "dentobot_workflow/widget_application.py").read_text()
        tree = ast.parse(source)
        owner = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        method = next(n for n in owner.body if isinstance(n, ast.FunctionDef)
                      and n.name == "_syncWorkflowMoreMenu")
        namespace = {"_": lambda text: text}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(PYTHON), "exec"), namespace)

        class Action:
            def __init__(self):
                self.blocked = False
                self.callback_count = 0
                self._checked = False

            def blockSignals(self, blocked):
                previous = self.blocked
                self.blocked = blocked
                return previous

            @property
            def checked(self):
                return self._checked

            @checked.setter
            def checked(self, value):
                if value != self._checked and not self.blocked:
                    self.callback_count += 1
                self._checked = value

        widget = SimpleNamespace(
            ui=SimpleNamespace(frameWorkflowViewButton=SimpleNamespace(enabled=True),
                               restoreWorkflowViewButton=SimpleNamespace(enabled=False),
                               showGuidanceCheckBox=SimpleNamespace(checked=True),
                               reloadDENTOWorkflowButton=SimpleNamespace(enabled=True)),
            _workflowSlicerToolsVisible=True,
        )
        for name in ("FrameView", "RestoreView", "Guidance", "GuiModeMenu",
                     "ReloadMenu", "SlicerTools"):
            setattr(widget, "_workflow" + name + "Action", Action())
        namespace["_syncWorkflowMoreMenu"](widget)
        self.assertFalse(widget._workflowGuiModeMenuAction.enabled)
        self.assertFalse(widget._workflowRestoreViewAction.enabled)
        for action in (widget._workflowGuidanceAction, widget._workflowSlicerToolsAction):
            self.assertTrue(action.checked)
            self.assertEqual(action.callback_count, 0)
            self.assertFalse(action.blocked)
        widget._guiModeButton = SimpleNamespace(enabled=True)
        widget._applicationShell = SimpleNamespace(active=True)
        namespace["_syncWorkflowMoreMenu"](widget)
        self.assertEqual(widget._workflowGuiModeMenuAction.text, "Return to Legacy GUI")
        self.assertTrue(widget._workflowGuiModeMenuAction.enabled)


if __name__ == "__main__":
    unittest.main()
