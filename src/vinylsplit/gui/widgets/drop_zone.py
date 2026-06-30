from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class DropZone(QFrame):
    """Large drag-and-drop target for selecting a recording file."""

    file_dropped = Signal(str)
    drag_state_changed = Signal(bool)

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)

        title = QLabel("Drop Recording Here")
        title.setObjectName("DropZoneTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Supports WAV, FLAC, AIFF and other PCM sources")
        subtitle.setObjectName("DropZoneSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(8)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch(1)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept local file drags."""

        if event.mimeData().hasUrls():
            self._set_drag_active(True)
            event.acceptProposedAction()
            return

        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        """Reset visual state when drag leaves the drop area."""

        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        """Emit the first dropped local file path."""

        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.exists() and path.is_file():
                self._set_drag_active(False)
                self.file_dropped.emit(str(path))
                event.acceptProposedAction()
                return

        self._set_drag_active(False)
        event.ignore()

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)
        self.drag_state_changed.emit(active)
