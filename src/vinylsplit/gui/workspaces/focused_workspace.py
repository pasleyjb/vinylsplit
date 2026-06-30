from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
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
from vinylsplit.gui.widgets.album_card import AlbumCard
from vinylsplit.gui.widgets.drop_zone import DropZone
from vinylsplit.gui.widgets.progress_card import ProgressCard
from vinylsplit.gui.widgets.status_banner import StatusBanner


class FocusedWorkspace(QWidget):
    """Beginner-friendly single-flow workspace for core VinylSplit tasks."""

    state_changed = Signal(object)
    review_requested = Signal()

    def __init__(self, app_context: ApplicationContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FocusedWorkspaceRoot")
        self.setAcceptDrops(True)
        self.setProperty("workspaceDropActive", False)
        self._app_context = app_context
        self._state = WorkspaceViewState()
        self._ui_step = FocusedStep.WELCOME
        self._drag_restore_message = self._state.status_message

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(18)

        title = QLabel("VinylSplit")
        title.setObjectName("FocusedTitle")

        subtitle = QLabel("Turn one recording into perfectly split tracks.")
        subtitle.setObjectName("FocusedSubtitle")

        self._drop_zone = DropZone()
        self._drop_zone.file_dropped.connect(self._on_file_selected)
        self._drop_zone.drag_state_changed.connect(self._on_drop_zone_drag_state_changed)

        self._browse_button = QPushButton("Browse Recording")
        self._browse_button.setObjectName("SecondaryButton")
        self._browse_button.setMinimumHeight(44)
        self._browse_button.setToolTip("Choose a recording from disk")
        self._browse_button.setAccessibleName("Browse Recording")
        self._browse_button.clicked.connect(self._browse_recording)

        self._recording_info = QLabel("No recording selected")
        self._recording_info.setObjectName("RecordingInfo")

        self._album_card = AlbumCard()

        self._primary_action = QPushButton("Analyze Recording")
        self._primary_action.setObjectName("PrimaryButton")
        self._primary_action.setMinimumHeight(52)
        self._primary_action.setToolTip("Advance to the next workflow step")
        self._primary_action.setAccessibleName("Primary Workflow Action")
        self._primary_action.clicked.connect(self._advance_placeholder_flow)

        self._progress_card = ProgressCard()
        self._status_banner = StatusBanner()

        self._recent_projects = QListWidget()
        self._recent_projects.setObjectName("RecentProjectsList")
        self._recent_projects.addItem(QListWidgetItem("Recent projects will appear here"))

        info_row = QHBoxLayout()
        info_row.setSpacing(16)

        left_column = QVBoxLayout()
        left_column.setSpacing(10)
        left_column.addWidget(self._recording_info)
        left_column.addWidget(self._primary_action)
        left_column.addWidget(self._progress_card)
        left_column.addWidget(self._status_banner)

        right_column = QVBoxLayout()
        right_column.setSpacing(10)
        right_column.addWidget(self._album_card)

        info_row.addLayout(left_column, 3)
        info_row.addLayout(right_column, 2)

        recent_frame = QFrame()
        recent_frame.setObjectName("Card")
        recent_layout = QVBoxLayout(recent_frame)
        recent_layout.setContentsMargins(16, 16, 16, 16)
        recent_layout.setSpacing(8)
        recent_title = QLabel("Recent Projects")
        recent_title.setObjectName("SectionTitle")
        recent_layout.addWidget(recent_title)
        recent_layout.addWidget(self._recent_projects)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(self._drop_zone)
        root.addWidget(self._browse_button, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addLayout(info_row)
        root.addWidget(recent_frame)

        self._apply_step_ui()

    def apply_state(self, state: WorkspaceViewState) -> None:
        """Apply shared state snapshot to focused workspace controls."""

        self._state = state
        self._sync_step_from_state()
        self._recording_info.setText(state.recording_info)
        self._album_card.set_album(state.album_artist, state.album_title)
        self._progress_card.set_progress(state.progress_value, state.progress_label)
        self._status_banner.set_status(state.status_message, tone="info")
        self._apply_step_ui()

        self._recent_projects.clear()
        if state.recent_projects:
            for item in state.recent_projects:
                self._recent_projects.addItem(QListWidgetItem(item))
        else:
            self._recent_projects.addItem(QListWidgetItem("Recent projects will appear here"))

    def current_state(self) -> WorkspaceViewState:
        """Return current local state snapshot."""

        return self._state

    def _browse_recording(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Recording",
            "",
            "Audio Files (*.wav *.flac *.aiff *.aif *.ogg *.mp3);;All Files (*)",
        )
        if filename:
            self._on_file_selected(filename)

    def _on_file_selected(self, filename: str) -> None:
        path = Path(filename)
        self._set_workspace_drop_active(False)
        self._state.recording_path = str(path)
        self._state.recording_info = f"Recording loaded: {path.name}"
        self._state.status_message = "Recording loaded. Analyze when you're ready."
        self._state.progress_label = "Ready to analyze"
        self._state.progress_value = 10
        self._state.analysis_state = "Not started"
        self._state.review_state = "Not requested"
        self._ui_step = FocusedStep.RECORDING_LOADED
        self._emit_state_change()

    def _advance_placeholder_flow(self) -> None:
        if self._state.recording_path is None:
            self._state.status_message = "Choose a recording first to continue."
            self._emit_state_change()
            return

        if self._ui_step in {FocusedStep.WELCOME, FocusedStep.RECORDING_LOADED}:
            self._state.analysis_state = "Analyzed"
            self._state.review_state = "Requested"
            self._state.album_artist = "Album identified"
            self._state.album_title = "Metadata matched"
            self._state.track_list = tuple(f"Track {index:02d}" for index in range(1, 13))
            self._state.progress_value = 60
            self._state.progress_label = "Tracks found"
            self._state.status_message = "Album identified. 12 tracks found. Review is recommended."
            self._ui_step = FocusedStep.REVIEW_RECOMMENDED
            self.review_requested.emit()
        elif self._ui_step is FocusedStep.REVIEW_RECOMMENDED:
            self._state.review_state = "Completed"
            self._state.progress_value = 82
            self._state.progress_label = "Review complete"
            self._state.status_message = "Review complete. Split album when you're ready."
            self._ui_step = FocusedStep.READY_TO_SPLIT
        elif self._ui_step is FocusedStep.READY_TO_SPLIT:
            self._state.progress_value = 100
            self._state.progress_label = "Your album is ready"
            self._state.status_message = "Album split successfully. 12 FLAC files created. Output folder ready."
            self._ui_step = FocusedStep.FINISHED
        else:
            self._state.status_message = "Start another album whenever you are ready."

        self._emit_state_change()

    def _emit_state_change(self) -> None:
        self.apply_state(self._state)
        self.state_changed.emit(self._state)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Highlight focused workspace when a recording is dragged over the view."""

        if event.mimeData().hasUrls():
            self._drag_restore_message = self._state.status_message
            self._state.status_message = "Drop to open recording"
            self._set_workspace_drop_active(True)
            self._emit_state_change()
            event.acceptProposedAction()
            return

        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        """Reset workspace highlight when dragging leaves the view."""

        self._state.status_message = self._drag_restore_message
        self._set_workspace_drop_active(False)
        self._emit_state_change()
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        """Accept drops anywhere in focused workspace."""

        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.exists() and path.is_file():
                self._on_file_selected(str(path))
                event.acceptProposedAction()
                return

        self._state.status_message = self._drag_restore_message
        self._set_workspace_drop_active(False)
        self._emit_state_change()
        event.ignore()

    def _apply_step_ui(self) -> None:
        if self._ui_step is FocusedStep.WELCOME:
            self._browse_button.setText("Browse Recording")
            self._primary_action.setText("Analyze Recording")
            self._primary_action.setEnabled(True)
            return

        if self._ui_step is FocusedStep.RECORDING_LOADED:
            self._browse_button.setText("Choose Another Recording")
            self._primary_action.setText("Analyze Recording")
            self._primary_action.setEnabled(True)
            return

        if self._ui_step is FocusedStep.REVIEW_RECOMMENDED:
            self._browse_button.setText("Change Recording")
            self._primary_action.setText("Review Recommended")
            self._primary_action.setEnabled(True)
            return

        if self._ui_step is FocusedStep.READY_TO_SPLIT:
            self._browse_button.setText("Change Recording")
            self._primary_action.setText("Split Album")
            self._primary_action.setEnabled(True)
            return

        self._browse_button.setText("Analyze Another Album")
        self._primary_action.setText("Open Output Folder")
        self._primary_action.setEnabled(False)

    def _sync_step_from_state(self) -> None:
        if self._state.progress_value >= 100:
            self._ui_step = FocusedStep.FINISHED
            return

        if self._state.review_state == "Completed":
            self._ui_step = FocusedStep.READY_TO_SPLIT
            return

        if self._state.review_state == "Requested":
            self._ui_step = FocusedStep.REVIEW_RECOMMENDED
            return

        if self._state.recording_path:
            self._ui_step = FocusedStep.RECORDING_LOADED
            return

        self._ui_step = FocusedStep.WELCOME

    def _set_workspace_drop_active(self, active: bool) -> None:
        self.setProperty("workspaceDropActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def _on_drop_zone_drag_state_changed(self, active: bool) -> None:
        if not active:
            return
        self._set_workspace_drop_active(True)


class FocusedStep(Enum):
    """Presentation-only milestones for the focused workspace placeholder flow."""

    WELCOME = "welcome"
    RECORDING_LOADED = "recording_loaded"
    REVIEW_RECOMMENDED = "review_recommended"
    READY_TO_SPLIT = "ready_to_split"
    FINISHED = "finished"
