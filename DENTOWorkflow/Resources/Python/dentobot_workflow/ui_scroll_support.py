"""Scroll-area helpers for workflow combo boxes."""

from __future__ import annotations

import qt


DEFAULT_COMBO_MAX_VISIBLE_ITEMS = 12


def installScrollAreaComboBoxWheelGuards(
    scroll_area: qt.QScrollArea,
    *,
    max_visible_items: int = DEFAULT_COMBO_MAX_VISIBLE_ITEMS,
) -> None:
    """Configure combo popups nested inside a workflow QScrollArea.

    Long tooth and mode lists need a bounded popup height with its own
    scrollbar. Avoid event filters or window-flag changes here; those have
    broken the surrounding workflow shell in live Slicer sessions.
    """
    if scroll_area is None:
        return
    content = scroll_area.widget()
    if content is None:
        return

    _ScrollAreaComboWheelCoordinator(scroll_area)

    for combo_box in content.findChildren("QComboBox"):
        _configureComboBoxPopup(
            combo_box,
            max_visible_items=max_visible_items,
        )


def _configureComboBoxPopup(
    combo_box: qt.QComboBox,
    *,
    max_visible_items: int,
) -> None:
    combo_box.maxVisibleItems = max_visible_items
    view = combo_box.view()
    if view is None:
        return
    view.setVerticalScrollBarPolicy(qt.Qt.ScrollBarAsNeeded)
    view.setVerticalScrollMode(qt.QAbstractItemView.ScrollPerPixel)


def _comboListViewAt(widget: qt.QWidget | None) -> qt.QAbstractItemView | None:
    node = widget
    while node is not None:
        if isinstance(node, qt.QAbstractItemView):
            parent = node.parentWidget()
            while parent is not None:
                if isinstance(parent, qt.QComboBox):
                    return node
                parent = parent.parentWidget()
        node = node.parentWidget()
    return None


class _ScrollAreaComboWheelCoordinator(qt.QObject):
    """Route wheel events to an open combo list under the cursor."""

    def __init__(self, scroll_area: qt.QScrollArea) -> None:
        super().__init__(scroll_area)
        self._viewport = scroll_area.viewport()
        if self._viewport is not None:
            self._viewport.installEventFilter(self)

    def eventFilter(self, watched: qt.QObject, event: qt.QEvent) -> bool:
        if watched is not self._viewport or event.type() != qt.QEvent.Wheel:
            return False
        global_pos = event.globalPos()
        list_view = _comboListViewAt(qt.QApplication.widgetAt(global_pos))
        if list_view is None:
            return False
        qt.QApplication.sendEvent(list_view.viewport(), event)
        return True
