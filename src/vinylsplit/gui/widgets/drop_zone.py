from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class DropZone(QFrame):
    """Large drag-and-drop target for selecting a recording file."""

    _SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".flac", ".aiff", ".aif", ".ogg", ".mp3"}

    file_dropped = Signal(str)
    drag_state_changed = Signal(bool)

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setProperty("dragActive", False)
        self.setProperty("compact", False)

        self._title = QLabel("Drop Recording Here")
        self._title.setObjectName("DropZoneTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._subtitle = QLabel("Supports WAV, FLAC, AIFF and other PCM sources")
        self._subtitle.setObjectName("DropZoneSubtitle")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(8)
        layout.addStretch(1)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addStretch(1)
        self.setMinimumHeight(180)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept local file drags."""

        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in self._SUPPORTED_AUDIO_EXTENSIONS:
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
            if (
                path.exists()
                and path.is_file()
                and path.suffix.lower() in self._SUPPORTED_AUDIO_EXTENSIONS
            ):
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

    def set_compact(self, compact: bool) -> None:
        """Reduce visual emphasis after a recording is loaded."""

        self.setProperty("compact", compact)
        if compact:
            self.setMinimumHeight(88)
            self._title.setText("Drop another recording to replace")
            self._subtitle.setText("You can also drag files anywhere in the window")
        else:
            self.setMinimumHeight(180)
            self._title.setText("Drop Recording Here")
            self._subtitle.setText("Supports WAV, FLAC, AIFF and other PCM sources")

        self.style().unpolish(self)
        self.style().polish(self)
