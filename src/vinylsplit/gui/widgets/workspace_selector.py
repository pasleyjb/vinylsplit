from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox


class WorkspaceSelector(QComboBox):
    """Selector for switching workspace views."""

    workspace_selected = Signal(str)

    def __init__(self, parent: QComboBox | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkspaceSelector")
        self.addItem("Focused", "focused")
        self.currentIndexChanged.connect(self._emit_selection)

    def set_workspace(self, workspace_id: str) -> None:
        """Set active workspace without external callers managing indices."""

        index = self.findData(workspace_id)
        if index >= 0 and index != self.currentIndex():
            self.setCurrentIndex(index)

    def _emit_selection(self) -> None:
        workspace_id = self.currentData()
        if isinstance(workspace_id, str):
            self.workspace_selected.emit(workspace_id)
