"""Small, reversible controller for the Slicer widgets hidden by Workflow Focus."""


class WorkflowFocusChromeController:
    def __init__(self):
        self._snapshot = []

    def _has_snapshot(self, widget):
        for saved_widget, _was_hidden in self._snapshot:
            if saved_widget is widget:
                return True
            try:
                if saved_widget == widget:
                    return True
            except (RuntimeError, TypeError):
                pass
        return False

    def apply(self, widgets):
        for widget in widgets:
            if widget is None:
                continue
            if not self._has_snapshot(widget):
                try:
                    self._snapshot.append((widget, bool(widget.isHidden())))
                except RuntimeError:
                    continue
            try:
                widget.hide()
            except RuntimeError:
                pass

    def restore(self, *, keep_snapshot=False):
        for widget, was_hidden in self._snapshot:
            try:
                (widget.hide if was_hidden else widget.show)()
            except RuntimeError:
                pass
        if not keep_snapshot:
            self._snapshot.clear()

    @staticmethod
    def set_shell_toolbars_visible(shell, visible):
        for widget, was_visible in getattr(shell, "_chrome_snapshot", ()):
            try:
                if widget.inherits("QToolBar"):
                    widget.visible = bool(was_visible) if visible else False
            except (AttributeError, RuntimeError, TypeError):
                pass
