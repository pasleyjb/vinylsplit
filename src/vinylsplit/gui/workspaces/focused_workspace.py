from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtGui import QFont, QFontDatabase
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
from PySide6.QtWidgets import QSizePolicy

from vinylsplit.application import ApplicationContext
from vinylsplit.application.events import ProgressUpdated
from vinylsplit.gui.dialogs import ReviewDialog
from vinylsplit.gui.state import WorkspaceViewState
from vinylsplit.gui.widgets.album_card import AlbumCard
from vinylsplit.gui.widgets.drop_zone import DropZone
from vinylsplit.gui.widgets.progress_card import ProgressCard
from vinylsplit.gui.widgets.status_banner import StatusBanner


class FocusedWorkspace(QWidget):
    """Beginner-friendly single-flow workspace for core VinylSplit tasks."""

    state_changed = Signal(object)

    def __init__(self, app_context: ApplicationContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("FocusedWorkspaceRoot")
        self.setAcceptDrops(True)
        self.setProperty("workspaceDropActive", False)
        self._app_context = app_context
        self._state = WorkspaceViewState()
        self._ui_step = FocusedStep.WELCOME
        self._drag_restore_message = self._state.status_message
        self._review_session: object | None = None
        self._last_output_directory: str | None = None
        self._export_thread: QThread | None = None
        self._export_worker: _ExportWorker | None = None
        self._progress_visible = False

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(18)

        title = QLabel("VinylSplit")
        title.setObjectName("FocusedTitle")
        title.setFont(_title_font())

        subtitle = QLabel("Intelligent Archive Tool")
        subtitle.setObjectName("FocusedTagline")
        subtitle.setFont(_tagline_font())

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
        self._recording_info.setWordWrap(True)
        self._recording_info.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        self._album_card = AlbumCard()
        self._album_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        self._primary_action = QPushButton("Analyze Recording")
        self._primary_action.setObjectName("PrimaryButton")
        self._primary_action.setMinimumHeight(52)
        self._primary_action.setToolTip("Advance to the next workflow step")
        self._primary_action.setAccessibleName("Primary Workflow Action")
        self._primary_action.clicked.connect(self._advance_flow)

        self._progress_card = ProgressCard()
        self._progress_card.setVisible(False)
        self._status_banner = StatusBanner()
        self._status_banner.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

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
        left_column.addStretch(1)

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
        self._review_session = None
        self._last_output_directory = None

        self._state.recording_path = str(path)
        self._state.recording_info = f"Recording loaded: {path.name}"
        self._state.status_message = "Recording loaded. You're ready to analyze."
        self._state.progress_label = "Ready to analyze"
        self._state.progress_value = 0
        self._state.analysis_state = "Not started"
        self._state.review_state = "Not requested"
        self._state.track_list = ()
        self._state.album_artist = "Unknown Artist"
        self._state.album_title = "Unknown Album"
        self._ui_step = FocusedStep.RECORDING_LOADED
        self._set_progress_visible(False)
        self._emit_state_change()

    def load_recording(self, filename: str) -> None:
        """Public entry point for loading a recording from outer containers."""

        self._on_file_selected(filename)

    def _advance_flow(self) -> None:
        if self._state.recording_path is None:
            self._state.status_message = "Choose a recording to continue."
            self._emit_state_change()
            return

        if self._ui_step in {FocusedStep.WELCOME, FocusedStep.RECORDING_LOADED}:
            self._run_analysis()
            return

        if self._ui_step is FocusedStep.REVIEW_RECOMMENDED:
            self._open_review_dialog()
            return

        if self._ui_step is FocusedStep.READY_TO_SPLIT:
            self._start_export()
            return

        self._open_output_folder()

    def _run_analysis(self) -> None:
        if self._state.recording_path is None:
            return

        self._ui_step = FocusedStep.ANALYZING
        self._state.status_message = "Analyzing your recording..."
        self._state.progress_label = "Analyzing"
        self._state.progress_value = 12
        self._set_progress_visible(True)
        self._emit_state_change()

        try:
            review_result = self._app_context.review_controller.review(self._state.recording_path)
        except Exception as exc:
            self._state.analysis_state = "Failed"
            self._state.status_message = "We couldn't analyze this recording. Please try another file."
            self._state.progress_label = "Analysis failed"
            self._state.progress_value = 0
            self._set_progress_visible(False)
            self._ui_step = FocusedStep.RECORDING_LOADED
            self._emit_state_change()
            return

        metadata_match = None
        try:
            metadata = self._app_context.analyze_controller.lookup_metadata(self._state.recording_path)
            metadata_match = metadata.match
        except Exception:
            metadata_match = None

        self._review_session = review_result.session
        boundaries = tuple(self._review_session.boundaries)

        self._state.analysis_state = "Analyzed"
        self._state.review_state = "Requested"
        self._state.track_list = tuple(
            boundary.track_title or f"Track {boundary.track_number:02d}"
            for boundary in boundaries
        )

        if metadata_match:
            self._state.album_artist = metadata_match.artist
            self._state.album_title = metadata_match.album
            self._state.status_message = "Analysis complete. Review the detected boundaries before splitting."
        else:
            self._state.album_artist = "Album information couldn't be identified"
            self._state.album_title = Path(self._state.recording_path).stem
            self._state.status_message = (
                "Album information couldn't be identified. You can still split this recording."
            )

        self._state.progress_label = "Analysis complete"
        self._state.progress_value = 100
        self._state.recording_info = (
            f"Detected {len(boundaries)} tracks. Review boundaries, then split when you're ready."
        )
        self._ui_step = FocusedStep.REVIEW_RECOMMENDED
        self._set_progress_visible(False)
        self._emit_state_change()

    def _open_review_dialog(self) -> None:
        if self._review_session is None:
            self._state.status_message = "Analyze this recording before opening review."
            self._emit_state_change()
            return

        dialog = ReviewDialog(boundaries=tuple(self._review_session.boundaries), parent=self)
        if dialog.exec() == ReviewDialog.DialogCode.Accepted:
            self._state.review_state = "Completed"
            self._state.progress_value = 0
            self._state.progress_label = "Review approved"
            self._state.status_message = "Review complete. Split the album when you're ready."
            self._ui_step = FocusedStep.READY_TO_SPLIT
            self._set_progress_visible(False)
            self._emit_state_change()

    def _start_export(self) -> None:
        if self._state.recording_path is None or self._review_session is None:
            self._state.status_message = "Analyze and review before splitting."
            self._emit_state_change()
            return

        output_directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Folder",
            str(Path("output").resolve()),
        )
        if not output_directory:
            return

        self._last_output_directory = output_directory
        self._ui_step = FocusedStep.EXPORTING
        self._state.status_message = "Splitting your album..."
        self._state.progress_label = "Preparing"
        self._state.progress_value = 5
        self._set_progress_visible(True)
        self._emit_state_change()
        self._primary_action.setEnabled(False)

        self._export_thread = QThread(self)
        self._export_worker = _ExportWorker(
            app_context=self._app_context,
            recording_path=self._state.recording_path,
            output_directory=output_directory,
            review_session=self._review_session,
        )
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.completed.connect(self._on_export_complete)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.completed.connect(self._export_thread.quit)
        self._export_worker.failed.connect(self._export_thread.quit)
        self._export_thread.finished.connect(self._cleanup_export_worker)
        self._export_thread.start()

    @Slot(object)
    def _on_export_progress(self, event: ProgressUpdated) -> None:
        value = self._stage_progress_value(event.stage, event.completed, event.total)
        self._state.progress_value = value
        self._state.progress_label = event.stage
        if event.description:
            self._state.status_message = event.description
        self._emit_state_change()

    @Slot(int)
    def _on_export_complete(self, exported_tracks: int) -> None:
        if self._last_output_directory:
            exported_tracks = len(list(Path(self._last_output_directory).rglob("*.flac")))
        self._state.progress_value = 0
        self._state.progress_label = "Idle"
        self._state.recording_info = f"Your album is ready. {exported_tracks} FLAC tracks were created."
        self._state.status_message = "Your album is ready. Open the output folder to review your tracks."
        self._ui_step = FocusedStep.FINISHED
        self._set_progress_visible(False)
        self._primary_action.setEnabled(True)
        self._emit_state_change()

    @Slot(str)
    def _on_export_failed(self, message: str) -> None:
        self._state.progress_label = "Split failed"
        self._state.status_message = "We couldn't complete the split. Please try again."
        self._state.progress_value = 0
        self._set_progress_visible(False)
        self._ui_step = FocusedStep.READY_TO_SPLIT
        self._primary_action.setEnabled(True)
        self._emit_state_change()

    @Slot()
    def _cleanup_export_worker(self) -> None:
        if self._export_worker is not None:
            self._export_worker.deleteLater()
        self._export_worker = None
        self._export_thread = None

    def _open_output_folder(self) -> None:
        if not self._last_output_directory:
            self._state.status_message = "No output folder is available yet."
            self._emit_state_change()
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_output_directory))
        self._state.status_message = "Output folder opened."
        self._emit_state_change()

    @staticmethod
    def _stage_progress_value(stage: str, completed: int, total: int | None) -> int:
        stage_order = [
            "Preparing",
            "Analyzing Audio",
            "Interactive Review",
            "Write Tracks",
            "Identifying Tracks",
            "Resolving Album",
            "Downloading Artwork",
            "Organize Tracks",
            "Embedding Artwork",
            "Finalizing",
            "Complete",
        ]
        if stage not in stage_order:
            return 15

        index = stage_order.index(stage)
        base = index / max(1, len(stage_order) - 1)
        fraction = 0.0
        if total and total > 0:
            fraction = max(0.0, min(1.0, completed / total)) / max(1, len(stage_order) - 1)

        return max(0, min(100, int((base + fraction) * 100)))

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
            self._drop_zone.set_compact(False)
            return

        if self._ui_step is FocusedStep.RECORDING_LOADED:
            self._browse_button.setText("Choose Another Recording")
            self._primary_action.setText("Analyze Recording")
            self._primary_action.setEnabled(True)
            self._drop_zone.set_compact(True)
            return

        if self._ui_step is FocusedStep.ANALYZING:
            self._browse_button.setText("Choose Another Recording")
            self._primary_action.setText("Analyzing...")
            self._primary_action.setEnabled(False)
            self._drop_zone.set_compact(True)
            return

        if self._ui_step is FocusedStep.REVIEW_RECOMMENDED:
            self._browse_button.setText("Change Recording")
            self._primary_action.setText("Open Review")
            self._primary_action.setEnabled(True)
            self._drop_zone.set_compact(True)
            return

        if self._ui_step is FocusedStep.READY_TO_SPLIT:
            self._browse_button.setText("Change Recording")
            self._primary_action.setText("Split Album")
            self._primary_action.setEnabled(True)
            self._drop_zone.set_compact(True)
            return

        if self._ui_step is FocusedStep.EXPORTING:
            self._browse_button.setText("Change Recording")
            self._primary_action.setText("Splitting...")
            self._primary_action.setEnabled(False)
            self._drop_zone.set_compact(True)
            return

        self._browse_button.setText("Analyze Another Album")
        self._primary_action.setText("Open Output Folder")
        self._primary_action.setEnabled(True)
        self._drop_zone.set_compact(True)

    def _sync_step_from_state(self) -> None:
        if self._ui_step in {FocusedStep.ANALYZING, FocusedStep.EXPORTING}:
            return

        if self._state.progress_value >= 100 and self._state.review_state == "Completed":
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

    def _set_progress_visible(self, visible: bool) -> None:
        self._progress_visible = visible
        self._progress_card.setVisible(visible)


class FocusedStep(Enum):
    """Presentation-only milestones for the focused workspace flow."""

    WELCOME = "welcome"
    RECORDING_LOADED = "recording_loaded"
    ANALYZING = "analyzing"
    REVIEW_RECOMMENDED = "review_recommended"
    READY_TO_SPLIT = "ready_to_split"
    EXPORTING = "exporting"
    FINISHED = "finished"


class _ExportWorker(QObject):
    """Background worker that runs export without blocking the GUI thread."""

    progress = Signal(object)
    completed = Signal(int)
    failed = Signal(str)

    def __init__(
        self,
        app_context: ApplicationContext,
        recording_path: str,
        output_directory: str,
        review_session: object,
    ) -> None:
        super().__init__()
        self._app_context = app_context
        self._recording_path = recording_path
        self._output_directory = output_directory
        self._review_session = review_session

    @Slot()
    def run(self) -> None:
        def on_progress(event: ProgressUpdated) -> None:
            self.progress.emit(event)

        try:
            result = asyncio.run(
                self._app_context.export_controller.export(
                    filename=self._recording_path,
                    output_directory=self._output_directory,
                    review_session=self._review_session,
                    progress_callback=on_progress,
                )
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        self.completed.emit(result.exported_tracks)


def _title_font() -> QFont:
    """Return archival display font with graceful serif fallback."""

    desired = [
        "Friz Quadrata Bold",
        "Friz Quadrata",
        "Cinzel",
        "Times New Roman",
        "Georgia",
        "Noto Serif",
        "DejaVu Serif",
    ]
    available = {family.lower(): family for family in QFontDatabase.families()}

    for family in desired:
        match = available.get(family.lower())
        if match:
            font = QFont(match, 30)
            font.setBold(True)
            return font

    fallback = QFont()
    fallback.setPointSize(30)
    fallback.setBold(True)
    return fallback


def _tagline_font() -> QFont:
    """Return elegant subtitle font aligned with title family where possible."""

    title = _title_font()
    font = QFont(title)
    font.setPointSize(13)
    font.setBold(False)
    return font
