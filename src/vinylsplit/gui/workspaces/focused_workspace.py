"""Focused workspace — automatic archival assistant.

The user selects a recording and an output folder.
VinylSplit does the rest.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QUrl
from PySide6.QtGui import (
    QCloseEvent,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QFont,
    QFontDatabase,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from vinylsplit.application import ApplicationContext
from vinylsplit.application.events import ProgressUpdated
from vinylsplit.gui.dialogs import ReviewDialog
from vinylsplit.gui.state import WorkspaceViewState
from vinylsplit.gui.widgets.drop_zone import DropZone


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@dataclass
class FocusedSettings:
    """User-configurable automation preferences for Focused mode."""

    auto_analyze: bool = True
    auto_deep_identify: bool = True
    auto_split_on_high_confidence: bool = True
    review_threshold: str = "Good"  # "Excellent" | "Good" | "Fair"

    def confidence_threshold(self) -> float:
        return {"Excellent": 0.85, "Good": 0.70, "Fair": 0.55}.get(
            self.review_threshold, 0.70
        )


# ---------------------------------------------------------------------------
# Internal step enum
# ---------------------------------------------------------------------------


class _Step(Enum):
    WELCOME = "welcome"
    READY = "ready"
    ANALYZING = "analyzing"
    IDENTIFYING = "identifying"
    SPLITTING = "splitting"
    REVIEWING = "reviewing"
    COMPLETE = "complete"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


class FocusedWorkspace(QWidget):
    """Automatic archival workflow. Select a recording. VinylSplit does the rest."""

    state_changed = Signal(object)

    def __init__(
        self, app_context: ApplicationContext, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("FocusedWorkspaceRoot")
        self.setAcceptDrops(True)

        self._app_context = app_context
        self._settings = FocusedSettings()

        # Internal state
        self._step = _Step.WELCOME
        self._recording_path: str | None = None
        self._output_folder: str = str(Path.home() / "Music")
        self._review_session: object | None = None
        self._last_exported_folder: str | None = None
        self._archive_info: dict = {}

        # Background threads / workers
        self._analyze_thread: QThread | None = None
        self._analyze_worker: _FocusedAnalyzeWorker | None = None
        self._identify_thread: QThread | None = None
        self._identify_worker: _FocusedIdentifyWorker | None = None
        self._export_thread: QThread | None = None
        self._export_worker: _FocusedExportWorker | None = None

        # Shared state for WorkspaceManager sync
        self._state = WorkspaceViewState()

        # Build UI: two pages stacked
        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_workflow_page())
        self._pages.addWidget(self._build_complete_page())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._pages)

        self._update_ui()

    # ------------------------------------------------------------------
    # Public API (WorkspaceManager interface)
    # ------------------------------------------------------------------

    def apply_state(self, state: WorkspaceViewState) -> None:
        """Receive cross-workspace state from WorkspaceManager."""
        self._state.active_workspace = state.active_workspace
        self._state.recent_projects = state.recent_projects

    def current_state(self) -> WorkspaceViewState:
        return self._state

    def load_recording(self, filename: str) -> None:
        """Drop / MainWindow-initiated entry point."""
        self._on_file_selected(filename)

    def update_settings(self, settings: FocusedSettings) -> None:
        """Called by Settings dialog when preferences change."""
        self._settings = settings

    # ------------------------------------------------------------------
    # Layout builders
    # ------------------------------------------------------------------

    def _build_workflow_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(80, 48, 80, 48)
        root.setSpacing(0)

        # Branding
        title = QLabel("VinylSplit")
        title.setObjectName("FocusedTitle")
        title.setFont(_title_font())
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        tagline = QLabel("Intelligent Archive Tool")
        tagline.setObjectName("FocusedTagline")
        tagline.setFont(_tagline_font())
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addStretch(1)
        root.addWidget(title)
        root.addSpacing(6)
        root.addWidget(tagline)
        root.addSpacing(36)

        # Recording selection
        self._drop_zone = DropZone()
        self._drop_zone.file_dropped.connect(self._on_file_selected)
        self._drop_zone.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        root.addWidget(self._drop_zone)
        root.addSpacing(12)

        browse_row = QHBoxLayout()
        self._browse_button = QPushButton("Browse Recording")
        self._browse_button.setObjectName("SecondaryButton")
        self._browse_button.setMinimumHeight(42)
        self._browse_button.clicked.connect(self._browse_recording)

        self._recording_label = QLabel("No recording selected")
        self._recording_label.setObjectName("RecordingInfo")
        self._recording_label.setWordWrap(True)
        self._recording_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        browse_row.addWidget(self._browse_button)
        browse_row.addSpacing(12)
        browse_row.addWidget(self._recording_label, 1)
        root.addLayout(browse_row)
        root.addSpacing(14)

        # Output folder
        output_row = QHBoxLayout()
        self._output_button = QPushButton("Output Folder")
        self._output_button.setObjectName("SecondaryButton")
        self._output_button.setMinimumHeight(42)
        self._output_button.clicked.connect(self._choose_output_folder)

        self._output_label = QLabel(self._output_folder)
        self._output_label.setObjectName("RecordingInfo")
        self._output_label.setWordWrap(True)
        self._output_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        output_row.addWidget(self._output_button)
        output_row.addSpacing(12)
        output_row.addWidget(self._output_label, 1)
        root.addLayout(output_row)
        root.addSpacing(36)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)
        root.addSpacing(28)

        # Stage heading
        self._stage_label = QLabel("")
        self._stage_label.setObjectName("SectionTitle")
        self._stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._stage_label)
        root.addSpacing(14)

        # Large progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setMinimumHeight(26)
        self._progress_bar.setTextVisible(True)
        root.addWidget(self._progress_bar)
        root.addSpacing(12)

        # Status detail
        self._status_label = QLabel("")
        self._status_label.setObjectName("StatusBarText")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)
        root.addSpacing(24)

        # Action buttons
        action_row = QHBoxLayout()
        action_row.addStretch(1)

        self._begin_button = QPushButton("Begin Archiving")
        self._begin_button.setObjectName("PrimaryButton")
        self._begin_button.setMinimumHeight(52)
        self._begin_button.setMinimumWidth(200)
        self._begin_button.clicked.connect(self._start_pipeline)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setObjectName("SecondaryButton")
        self._cancel_button.setMinimumHeight(52)
        self._cancel_button.setMinimumWidth(140)
        self._cancel_button.clicked.connect(self._cancel_pipeline)

        action_row.addWidget(self._begin_button)
        action_row.addSpacing(12)
        action_row.addWidget(self._cancel_button)
        action_row.addStretch(1)
        root.addLayout(action_row)

        root.addStretch(2)
        return page

    def _build_complete_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(80, 60, 80, 60)
        root.setSpacing(0)

        root.addStretch(1)

        check = QLabel("\u2713 Archive Complete")
        check.setObjectName("FocusedTitle")
        check.setFont(_title_font())
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(check)
        root.addSpacing(28)

        self._complete_album_label = QLabel("")
        self._complete_album_label.setObjectName("SectionTitle")
        self._complete_album_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._complete_album_label)
        root.addSpacing(8)

        self._complete_detail_label = QLabel("")
        self._complete_detail_label.setObjectName("StatusBarText")
        self._complete_detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._complete_detail_label.setWordWrap(True)
        root.addWidget(self._complete_detail_label)
        root.addSpacing(8)

        self._complete_path_label = QLabel("")
        self._complete_path_label.setObjectName("RecordingInfo")
        self._complete_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._complete_path_label.setWordWrap(True)
        root.addWidget(self._complete_path_label)
        root.addSpacing(36)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)
        root.addSpacing(28)

        button_row = QHBoxLayout()
        button_row.addStretch(1)

        open_button = QPushButton("Open Folder")
        open_button.setObjectName("PrimaryButton")
        open_button.setMinimumHeight(52)
        open_button.setMinimumWidth(160)
        open_button.clicked.connect(self._open_output_folder)

        another_button = QPushButton("Archive Another Album")
        another_button.setObjectName("SecondaryButton")
        another_button.setMinimumHeight(52)
        another_button.setMinimumWidth(200)
        another_button.clicked.connect(self._reset_to_welcome)

        button_row.addWidget(open_button)
        button_row.addSpacing(16)
        button_row.addWidget(another_button)
        button_row.addStretch(1)
        root.addLayout(button_row)

        root.addStretch(2)
        return page

    # ------------------------------------------------------------------
    # Recording / output folder selection
    # ------------------------------------------------------------------

    def _browse_recording(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Recording",
            "",
            "Audio Files (*.wav *.flac *.aiff *.aif *.ogg *.mp3);;All Files (*)",
        )
        if filename:
            self._on_file_selected(filename)

    def _choose_output_folder(self) -> None:
        if self._step in (_Step.ANALYZING, _Step.IDENTIFYING, _Step.SPLITTING):
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self._output_folder
        )
        if folder:
            self._output_folder = folder
            self._output_label.setText(folder)
            self._maybe_auto_start()

    def _on_file_selected(self, filename: str) -> None:
        path = Path(filename)
        self._recording_path = str(path)
        self._review_session = None
        self._last_exported_folder = None
        self._archive_info = {}

        self._recording_label.setText(path.name)
        self._step = _Step.READY
        self._pages.setCurrentIndex(0)

        self._state.recording_path = str(path)
        self._state.recording_info = f"Recording loaded: {path.name}"
        self._state.analysis_state = "Not started"
        self._state.review_state = "Not requested"
        self._state.track_list = ()
        self._state.album_artist = "Unknown Artist"
        self._state.album_title = "Unknown Album"

        self._set_progress(0, "Recording loaded.")
        self._update_ui()
        self._maybe_auto_start()
        self._emit_state_change()

    def _maybe_auto_start(self) -> None:
        if (
            self._recording_path
            and self._output_folder
            and self._settings.auto_analyze
            and self._step == _Step.READY
        ):
            self._start_pipeline()

    # ------------------------------------------------------------------
    # Pipeline orchestration
    # ------------------------------------------------------------------

    def _start_pipeline(self) -> None:
        if not self._recording_path:
            self._set_progress(0, "Select a recording to begin.")
            return
        if not self._output_folder:
            self._set_progress(0, "Select an output folder to continue.")
            return
        self._step = _Step.ANALYZING
        self._update_ui()
        self._set_progress(5, "Analyzing audio...")
        self._launch_analyze_worker()

    # ── Analyze phase ──────────────────────────────────────────────────

    def _launch_analyze_worker(self) -> None:
        self._analyze_thread = QThread(self)
        self._analyze_worker = _FocusedAnalyzeWorker(
            app_context=self._app_context,
            recording_path=self._recording_path,
        )
        self._analyze_worker.moveToThread(self._analyze_thread)
        self._analyze_thread.started.connect(self._analyze_worker.run)
        self._analyze_worker.progress.connect(self._on_analyze_progress)
        self._analyze_worker.completed.connect(self._on_analyze_complete)
        self._analyze_worker.failed.connect(self._on_stage_failed)
        self._analyze_worker.completed.connect(self._analyze_thread.quit)
        self._analyze_worker.failed.connect(self._analyze_thread.quit)
        self._analyze_thread.finished.connect(self._cleanup_analyze_worker)
        self._analyze_thread.start()

    @Slot(int, str)
    def _on_analyze_progress(self, value: int, message: str) -> None:
        self._set_progress(5 + int(value * 0.29), message)

    @Slot(object)
    def _on_analyze_complete(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        review_session = data.get("review_session")
        metadata_match = data.get("metadata_match")

        if review_session is None:
            self._on_stage_failed("Analysis returned no session.")
            return

        self._review_session = review_session
        boundaries = tuple(getattr(self._review_session, "boundaries", ()))

        self._state.analysis_state = "Analyzed"
        self._state.review_state = "Requested"
        self._state.track_list = tuple(
            getattr(b, "track_title", None)
            or f"Track {getattr(b, 'track_number', i + 1):02d}"
            for i, b in enumerate(boundaries)
        )
        if metadata_match:
            artist = getattr(metadata_match, "artist", "")
            album = getattr(metadata_match, "album", "")
            release_id = getattr(metadata_match, "release_id", "")
            self._state.album_artist = artist
            self._state.album_title = album
            self._archive_info.update(artist=artist, album=album, release_id=release_id)

        self._emit_state_change()
        self._set_progress(34, f"Found {len(boundaries)} track boundaries.")

        if self._settings.auto_deep_identify:
            self._step = _Step.IDENTIFYING
            self._update_ui()
            self._set_progress(35, "Identifying album...")
            self._launch_identify_worker()
        else:
            self._evaluate_confidence_and_proceed()

    @Slot()
    def _cleanup_analyze_worker(self) -> None:
        if self._analyze_worker is not None:
            self._analyze_worker.deleteLater()
        self._analyze_worker = None
        self._analyze_thread = None

    # ── Identify phase ─────────────────────────────────────────────────

    def _launch_identify_worker(self) -> None:
        if self._review_session is None or not self._recording_path:
            self._evaluate_confidence_and_proceed()
            return
        self._identify_thread = QThread(self)
        self._identify_worker = _FocusedIdentifyWorker(
            app_context=self._app_context,
            recording_path=self._recording_path,
            review_session=self._review_session,
        )
        self._identify_worker.moveToThread(self._identify_thread)
        self._identify_thread.started.connect(self._identify_worker.run)
        self._identify_worker.progress.connect(self._on_identify_progress)
        self._identify_worker.completed.connect(self._on_identify_complete)
        self._identify_worker.failed.connect(self._on_identify_failed)
        self._identify_worker.completed.connect(self._identify_thread.quit)
        self._identify_worker.failed.connect(self._identify_thread.quit)
        self._identify_thread.finished.connect(self._cleanup_identify_worker)
        self._identify_thread.start()

    @Slot(int, str)
    def _on_identify_progress(self, value: int, message: str) -> None:
        self._set_progress(35 + int(value * 0.30), message)

    @Slot(object)
    def _on_identify_complete(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        album = data.get("album")
        tracklist = data.get("tracklist") or []

        if album is not None and self._review_session is not None:
            artist = getattr(album, "artist", "")
            album_title = getattr(album, "album", "")
            year = getattr(album, "year", "")
            release_id = getattr(album, "release_id", "")
            self._review_session.album_artist = artist
            self._review_session.album_title = album_title
            self._review_session.album_year = year
            self._review_session.release_id = release_id
            self._archive_info.update(
                artist=artist, album=album_title, year=year, release_id=release_id
            )
            if tracklist:
                self._review_session.track_titles = list(tracklist)
                for idx, boundary in enumerate(self._review_session.boundaries):
                    if idx < len(tracklist):
                        boundary.track_title = tracklist[idx]
                self._state.track_list = tuple(tracklist)
            self._state.album_artist = artist
            self._state.album_title = album_title
            self._emit_state_change()
            self._set_progress(65, f"Album identified: {album_title}")
        else:
            self._set_progress(65, "Identification complete.")

        self._evaluate_confidence_and_proceed()

    @Slot(str)
    def _on_identify_failed(self, message: str) -> None:
        # Non-fatal — continue without identification
        self._set_progress(65, "Identification unavailable. Continuing...")
        self._evaluate_confidence_and_proceed()

    @Slot()
    def _cleanup_identify_worker(self) -> None:
        if self._identify_worker is not None:
            self._identify_worker.deleteLater()
        self._identify_worker = None
        self._identify_thread = None

    # ── Confidence gate ────────────────────────────────────────────────

    def _evaluate_confidence_and_proceed(self) -> None:
        if self._review_session is None:
            self._on_stage_failed("No review session available.")
            return

        boundaries = list(getattr(self._review_session, "boundaries", []))
        if not boundaries:
            self._on_stage_failed("No boundaries detected.")
            return

        threshold = self._settings.confidence_threshold()
        scored = [
            float(getattr(b, "detector_confidence", 0.0) or 0.0)
            for b in boundaries
            if getattr(b, "detector_confidence", None) is not None
        ]
        avg = sum(scored) / len(scored) if scored else 0.0
        high_confidence = avg >= threshold and self._settings.auto_split_on_high_confidence

        if high_confidence:
            self._set_progress(67, f"Confidence {avg * 100:.0f}% \u2014 splitting automatically...")
            self._start_split()
        else:
            self._step = _Step.REVIEWING
            self._update_ui()
            if avg > 0:
                threshold_pct = int(threshold * 100)
                msg = (
                    f"Average confidence {avg * 100:.0f}% is below the {threshold_pct}% threshold. "
                    "VinylSplit found boundaries that should be verified."
                )
            else:
                msg = "Track boundaries detected. Please verify them before splitting."
            self._set_progress(67, msg)
            self._open_review_workstation()

    def _open_review_workstation(self) -> None:
        session_dto = self._app_context.review_controller.get_session_dto()
        if session_dto is not None:
            dialog = ReviewDialog(session_dto=session_dto, parent=self)
        else:
            dialog = ReviewDialog(
                boundaries=tuple(getattr(self._review_session, "boundaries", ())),
                parent=self,
            )

        self._status_label.setText(
            "VinylSplit found boundaries that should be verified. "
            "Review them and click Accept Changes to continue archiving."
        )

        if dialog.exec() == ReviewDialog.DialogCode.Accepted:
            self._state.review_state = "Completed"
            self._emit_state_change()
            self._start_split()
        else:
            self._step = _Step.READY
            self._state.review_state = "Cancelled"
            self._emit_state_change()
            self._set_progress(0, "Review cancelled. Adjust settings or begin again.")
            self._update_ui()

    # ── Split phase ────────────────────────────────────────────────────

    def _start_split(self) -> None:
        if self._review_session is None or not self._recording_path:
            self._on_stage_failed("Missing session or recording path.")
            return
        self._step = _Step.SPLITTING
        self._update_ui()
        self._set_progress(70, "Splitting album...")
        self._launch_export_worker()

    def _launch_export_worker(self) -> None:
        artist = self._archive_info.get("artist") or ""
        album = self._archive_info.get("album") or ""
        _no_artist = ("", "Unknown Artist", "Album information couldn't be identified")
        _no_album = ("", "Unknown Album")

        self._export_thread = QThread(self)
        self._export_worker = _FocusedExportWorker(
            app_context=self._app_context,
            recording_path=self._recording_path,
            output_directory=self._output_folder,
            review_session=self._review_session,
            artist=artist if artist not in _no_artist else None,
            album=album if album not in _no_album else None,
        )
        self._export_worker.moveToThread(self._export_thread)
        self._export_thread.started.connect(self._export_worker.run)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.completed.connect(self._on_export_complete)
        self._export_worker.failed.connect(self._on_stage_failed)
        self._export_worker.completed.connect(self._export_thread.quit)
        self._export_worker.failed.connect(self._export_thread.quit)
        self._export_thread.finished.connect(self._cleanup_export_worker)
        self._export_thread.start()

    @Slot(object)
    def _on_export_progress(self, event: ProgressUpdated) -> None:
        completed = event.completed or 0
        total = event.total or 1
        mapped = 70 + int((completed / max(1, total)) * 29)
        msg = event.description or event.stage or ""
        self._set_progress(min(99, mapped), msg)

    @Slot(int)
    def _on_export_complete(self, exported_tracks: int) -> None:
        try:
            from vinylsplit.utils import sanitize_filename
            artist = self._archive_info.get("artist", "")
            album = self._archive_info.get("album", "")
            _no_artist = ("", "Unknown Artist", "Album information couldn't be identified")
            _no_album = ("", "Unknown Album")
            if artist not in _no_artist and album not in _no_album:
                folder_name = sanitize_filename(f"{artist} - {album}")
            elif album not in _no_album:
                folder_name = sanitize_filename(album)
            else:
                folder_name = "Album"
            self._last_exported_folder = str(Path(self._output_folder) / folder_name)
        except Exception:
            self._last_exported_folder = self._output_folder

        self._step = _Step.COMPLETE
        self._set_progress(100, "Archive complete.")
        self._state.recording_info = f"Archive complete: {exported_tracks} FLAC tracks"
        self._state.status_message = "Archive complete."
        self._emit_state_change()
        self._show_archive_complete(exported_tracks)

    @Slot()
    def _cleanup_export_worker(self) -> None:
        if self._export_worker is not None:
            self._export_worker.deleteLater()
        self._export_worker = None
        self._export_thread = None

    @Slot(str)
    def _on_stage_failed(self, message: str) -> None:
        self._step = _Step.FAILED
        self._update_ui()
        self._set_progress(0, f"Error: {message}")

    def _cancel_pipeline(self) -> None:
        self._shutdown_background_threads()
        self._step = _Step.READY if self._recording_path else _Step.WELCOME
        self._update_ui()
        self._set_progress(0, "Processing cancelled.")

    # ------------------------------------------------------------------
    # Archive complete screen
    # ------------------------------------------------------------------

    def _show_archive_complete(self, track_count: int) -> None:
        artist = self._archive_info.get("artist", "")
        album = self._archive_info.get("album", "")
        year = self._archive_info.get("year", "")
        _no_artist = ("", "Unknown Artist", "Album information couldn't be identified")

        if artist not in _no_artist and album:
            album_line = f"{artist} \u2013 {album}"
        elif album:
            album_line = album
        else:
            album_line = Path(self._recording_path or "").stem

        if year:
            album_line += f"  ({year})"

        self._complete_album_label.setText(album_line)
        details = [
            f"{track_count} FLAC tracks created",
            "Metadata embedded",
            "Artwork embedded",
        ]
        self._complete_detail_label.setText("\n".join(details))
        folder = self._last_exported_folder or self._output_folder
        self._complete_path_label.setText(f"Saved to:\n{folder}")
        self._pages.setCurrentIndex(1)

    def _open_output_folder(self) -> None:
        folder = self._last_exported_folder or self._output_folder
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _reset_to_welcome(self) -> None:
        self._recording_path = None
        self._review_session = None
        self._last_exported_folder = None
        self._archive_info = {}
        self._step = _Step.WELCOME
        self._recording_label.setText("No recording selected")
        self._state = WorkspaceViewState()
        self._pages.setCurrentIndex(0)
        self._set_progress(0, "")
        self._update_ui()
        self._emit_state_change()

    # ------------------------------------------------------------------
    # UI sync helpers
    # ------------------------------------------------------------------

    def _set_progress(self, value: int, message: str) -> None:
        self._progress_bar.setValue(max(0, min(100, value)))
        self._status_label.setText(message)
        self._state.progress_value = value
        self._state.progress_label = message
        self._state.status_message = message

    def _update_ui(self) -> None:
        processing = self._step in (_Step.ANALYZING, _Step.IDENTIFYING, _Step.SPLITTING)
        complete = self._step == _Step.COMPLETE
        ready_to_start = self._step in (_Step.READY, _Step.FAILED) and bool(self._recording_path)

        self._browse_button.setEnabled(not processing and not complete)
        self._output_button.setEnabled(not processing and not complete)

        manual_mode = not self._settings.auto_analyze and ready_to_start
        self._begin_button.setVisible(bool(manual_mode))
        self._begin_button.setEnabled(bool(manual_mode))
        self._cancel_button.setVisible(processing)

        stage_text = {
            _Step.WELCOME: "Drop a recording to begin.",
            _Step.READY: "Recording loaded.",
            _Step.ANALYZING: "Analyzing recording...",
            _Step.IDENTIFYING: "Identifying album...",
            _Step.SPLITTING: "Archiving tracks...",
            _Step.REVIEWING: "Review Required",
            _Step.COMPLETE: "",
            _Step.FAILED: "Processing Failed",
        }.get(self._step, "")
        self._stage_label.setText(stage_text)

        if hasattr(self._drop_zone, "set_compact"):
            self._drop_zone.set_compact(bool(self._recording_path))

    def _emit_state_change(self) -> None:
        self.state_changed.emit(self._state)

    # ------------------------------------------------------------------
    # Thread lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._shutdown_background_threads()
        super().closeEvent(event)

    def _shutdown_background_threads(self) -> None:
        for thread in (self._analyze_thread, self._identify_thread, self._export_thread):
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
                thread.quit()
                if not thread.wait(5000):
                    thread.terminate()
                    thread.wait(2000)

    # ------------------------------------------------------------------
    # Drag-and-drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.exists() and path.is_file():
                self._on_file_selected(str(path))
                event.acceptProposedAction()
                return
        event.ignore()


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------


class _FocusedAnalyzeWorker(QObject):
    """Boundary detection + metadata lookup in background."""

    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, app_context: ApplicationContext, recording_path: str) -> None:
        super().__init__()
        self._app_context = app_context
        self._recording_path = recording_path

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit(10, "Detecting silence regions...")
            review_result = self._app_context.review_controller.review(self._recording_path)
            self.progress.emit(70, "Looking up metadata...")
            metadata_match = None
            try:
                result = self._app_context.analyze_controller.lookup_metadata(self._recording_path)
                metadata_match = result.match
            except Exception:
                metadata_match = None
            self.progress.emit(100, "Analysis complete.")
            self.completed.emit({
                "review_session": review_result.session,
                "metadata_match": metadata_match,
            })
        except Exception as exc:
            self.failed.emit(str(exc))


class _FocusedIdentifyWorker(QObject):
    """Per-track deep identification in background."""

    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        app_context: ApplicationContext,
        recording_path: str,
        review_session: object,
    ) -> None:
        super().__init__()
        self._app_context = app_context
        self._recording_path = recording_path
        self._review_session = review_session

    @Slot()
    def run(self) -> None:
        try:
            thread = QThread.currentThread()
            boundaries = list(getattr(self._review_session, "boundaries", ()) or ())
            if not boundaries:
                self.completed.emit({"album": None, "tracklist": []})
                return
            identified = []
            with TemporaryDirectory(prefix="vinylsplit-focused-") as tmp_dir:
                tracks = self._app_context.pipeline.splitter.split(
                    filename=self._recording_path,
                    boundaries=boundaries,
                    output_directory=tmp_dir,
                )
                total = max(1, len(tracks))
                for index, track in enumerate(tracks, start=1):
                    if thread.isInterruptionRequested():
                        self.failed.emit("Cancelled")
                        return
                    self.progress.emit(
                        int((index - 1) / total * 100),
                        f"Identifying track {index}/{total}...",
                    )
                    try:
                        match = self._app_context.pipeline.identifier.identify(
                            source_file=self._recording_path,
                            track=track,
                        )
                        identified.append((track, match))
                    except Exception:
                        continue
            if not identified:
                self.completed.emit({"album": None, "tracklist": []})
                return
            album, tracklist = self._app_context.pipeline.resolver.resolve(identified)
            self.completed.emit({"album": album, "tracklist": tracklist})
        except Exception as exc:
            self.failed.emit(str(exc))


class _FocusedExportWorker(QObject):
    """Full export pipeline — split + metadata + artwork."""

    progress = Signal(object)
    completed = Signal(int)
    failed = Signal(str)

    def __init__(
        self,
        app_context: ApplicationContext,
        recording_path: str,
        output_directory: str,
        review_session: object,
        artist: str | None = None,
        album: str | None = None,
    ) -> None:
        super().__init__()
        self._app_context = app_context
        self._recording_path = recording_path
        self._output_directory = output_directory
        self._review_session = review_session
        self._artist = artist
        self._album = album

    @Slot()
    def run(self) -> None:
        def on_progress(event: ProgressUpdated) -> None:
            self.progress.emit(event)

        try:
            result = asyncio.run(
                self._app_context.export_controller.export(
                    filename=self._recording_path,
                    output_directory=self._output_directory,
                    artist=self._artist,
                    album=self._album,
                    review_session=self._review_session,
                    progress_callback=on_progress,
                )
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(result.exported_tracks)


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------


def _title_font() -> QFont:
    desired = [
        "Friz Quadrata Bold", "Friz Quadrata", "Cinzel",
        "Times New Roman", "Georgia", "Noto Serif", "DejaVu Serif",
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
    title = _title_font()
    font = QFont(title)
    font.setPointSize(13)
    font.setBold(False)
    return font
