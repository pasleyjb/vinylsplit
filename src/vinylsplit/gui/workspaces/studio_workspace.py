from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vinylsplit.application import ApplicationContext
from vinylsplit.gui.state import WorkspaceViewState


class StudioWorkspace(QWidget):
    """Advanced inspection workspace with professional placeholder panels."""

    state_changed = Signal(object)

    def __init__(self, app_context: ApplicationContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_context = app_context
        self._state = WorkspaceViewState(active_workspace="studio")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel("Studio Workspace")
        title.setObjectName("SectionTitle")
        subtitle = QLabel("Advanced inspection, diagnostics, and refinement placeholders")
        subtitle.setObjectName("FocusedSubtitle")

        toolbar = QFrame()
        toolbar.setObjectName("Card")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        toolbar_layout.setSpacing(10)
        toolbar_layout.addWidget(QPushButton("Playback Provider"))
        toolbar_layout.addWidget(QPushButton("Analysis Panel"))
        toolbar_layout.addWidget(QPushButton("Diagnostics"))
        toolbar_layout.addStretch(1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        grid.addWidget(_panel("Waveform", "Waveform preview placeholder"), 0, 0, 1, 2)
        grid.addWidget(_panel("Track List", "Detected tracks will appear here"), 1, 0)
        grid.addWidget(_panel("Metadata Inspector", "Metadata fields placeholder"), 1, 1)
        grid.addWidget(_panel("Boundary Inspector", "Boundary detail placeholder"), 2, 0)
        grid.addWidget(_panel("Playback Controls", "Play/Pause/Seek placeholders"), 2, 1)
        grid.addWidget(_panel("Future Spectrogram", "Reserved for spectrogram"), 3, 0)
        grid.addWidget(_panel("Future Analysis", "Reserved for analysis insights"), 3, 1)

        self._track_list = QListWidget()
        self._track_list.setObjectName("TrackList")
        self._track_list.addItem(QListWidgetItem("No tracks yet"))

        status = QFrame()
        status.setObjectName("Card")
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(12, 10, 12, 10)
        self._status_label = QLabel("Studio ready")
        self._status_label.setObjectName("StatusBarText")
        status_layout.addWidget(self._status_label)

        root.addWidget(toolbar)
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addLayout(grid)
        root.addWidget(QLabel("Track Overview"))
        root.addWidget(self._track_list)
        root.addWidget(status)

    def apply_state(self, state: WorkspaceViewState) -> None:
        """Apply shared state snapshot to studio workspace controls."""

        self._state = state
        self._status_label.setText(
            f"{state.status_message}  |  Analysis: {state.analysis_state}  |  Review: {state.review_state}"
        )

        self._track_list.clear()
        if state.track_list:
            for track in state.track_list:
                self._track_list.addItem(QListWidgetItem(track))
        elif state.recording_path:
            self._track_list.addItem(QListWidgetItem("Track list placeholder (analysis not implemented)"))
        else:
            self._track_list.addItem(QListWidgetItem("No tracks yet"))

    def current_state(self) -> WorkspaceViewState:
        """Return current local state snapshot."""

        return self._state


def _panel(title: str, description: str) -> QFrame:
    panel = QFrame()
    panel.setObjectName("Card")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(6)

    label = QLabel(title)
    label.setObjectName("SectionTitle")
    desc = QLabel(description)
    desc.setWordWrap(True)

    layout.addWidget(label)
    layout.addWidget(desc)
    return panel
