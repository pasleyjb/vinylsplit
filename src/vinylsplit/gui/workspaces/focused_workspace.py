from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QSettings, QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices, QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QCheckBox,
    QComboBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from mutagen import File as MutagenFile

try:
    from vinylsplit.application.context import ApplicationContext
except Exception:  # pragma: no cover - fallback for local import variations
    ApplicationContext = Any  # type: ignore[assignment]

from vinylsplit.application.services.review_mapper import map_session_to_dto
from vinylsplit.gui.dialogs.startup_wizard_dialog import StartupWizardSelection

try:
    from vinylsplit.gui.dialogs.review_dialog import ReviewDialog
except Exception:  # pragma: no cover - fallback if dialog export path changes
    ReviewDialog = None  # type: ignore[assignment]

from vinylsplit.gui.state import WorkspaceViewState


class FocusedStep(Enum):
    WELCOME = "welcome"
    RECORDING_LOADED = "recording_loaded"
    ANALYZING = "analyzing"
    REVIEW_RECOMMENDED = "review_recommended"
    READY_TO_SPLIT = "ready_to_split"
    ARCHIVE_COMPLETE = "archive_complete"


class FocusedWorkspace(QWidget):
    state_changed = Signal(object)
    _LAST_UPLOAD_DIR_KEY = "focused/lastUploadDirectory"
    _PREFERRED_OUTPUT_DIR_KEY = "focused/preferredOutputDirectory"
    _PREFERRED_OUTPUT_FORMAT_KEY = "focused/preferredOutputFormat"

    def __init__(self, app_context: ApplicationContext, state: WorkspaceViewState | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._app_context = app_context
        self._state = state or WorkspaceViewState()
        self._ui_step = FocusedStep.WELCOME
        self._review_session: Any | None = None
        self._analysis_result: dict[str, Any] | None = None
        self._last_output_directory: str | None = None
        self._artwork_available = False
        self._analyze_thread: QThread | None = None
        self._analyze_worker: _FocusedAnalyzeWorker | None = None
        self._export_thread: QThread | None = None
        self._export_worker: _FocusedExportWorker | None = None
        self._workspace_manager: Any | None = None
        self._active_review_dialog: QWidget | None = None
        self._embedded_review_editor: ReviewDialog | None = None
        self._settings = QSettings()
        self._last_output_directory = self._preferred_output_directory()

        self._auto_analyze_check = QCheckBox("Automatically analyze")
        self._auto_review_check = QCheckBox("Open review only when needed")
        self._auto_split_check = QCheckBox("Automatically split when confident")
        self._auto_artwork_check = QCheckBox("Automatically fetch artwork")
        self._review_threshold_combo = QComboBox()
        self._review_threshold_combo.addItem("Excellent", 0.92)
        self._review_threshold_combo.addItem("Good", 0.85)
        self._review_threshold_combo.addItem("Fair", 0.75)
        self._auto_analyze_check.toggled.connect(lambda checked: self._set_state_field("focused_auto_analyze", checked))
        self._auto_review_check.toggled.connect(lambda checked: self._set_state_field("focused_auto_review", checked))
        self._auto_split_check.toggled.connect(lambda checked: self._set_state_field("focused_auto_split", checked))
        self._auto_artwork_check.toggled.connect(lambda checked: self._set_state_field("focused_auto_artwork", checked))
        self._review_threshold_combo.currentIndexChanged.connect(self._on_review_threshold_changed)

        self._build_ui()
        self._sync_state_from_model()
        self._sync_action_buttons()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("VinylSplit")
        title.setObjectName("focusedTitle")
        subtitle = QLabel("Load one recording, review boundaries, refine edits, and export from this workspace.")
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)

        action_row = QHBoxLayout()
        self._select_button = QPushButton("Select Recording")
        self._archive_button = QPushButton("Archive Now")
        self._review_button = QPushButton("Open Review")
        self._split_button = QPushButton("Split")
        self._open_output_button = QPushButton("Open Output Folder")
        self._archive_again_button = QPushButton("Archive Another Album")

        self._select_button.clicked.connect(self._choose_recording)
        self._archive_button.clicked.connect(self._begin_automatic_archive)
        self._review_button.clicked.connect(self._open_review_dialog)
        self._split_button.clicked.connect(self._start_export)
        self._open_output_button.clicked.connect(self._open_output_folder)
        self._archive_again_button.clicked.connect(self._reset_for_next_album)

        for button in (
            self._select_button,
            self._archive_button,
            self._review_button,
            self._split_button,
            self._open_output_button,
            self._archive_again_button,
        ):
            action_row.addWidget(button)

        root.addLayout(action_row)

        self._progress_card = QFrame()
        self._progress_card.setObjectName("focusedProgressCard")
        progress_layout = QVBoxLayout(self._progress_card)
        progress_layout.setContentsMargins(16, 16, 16, 16)
        self._status_label = QLabel("Waiting for a recording.")
        self._status_label.setWordWrap(True)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._status_label)
        progress_layout.addWidget(self._progress_bar)
        root.addWidget(self._progress_card)

        options_card = QFrame()
        options_card.setObjectName("focusedOptionsCard")
        options_layout = QGridLayout(options_card)
        options_layout.setContentsMargins(16, 16, 16, 16)
        options_layout.addWidget(self._auto_analyze_check, 0, 0)
        options_layout.addWidget(self._auto_review_check, 1, 0)
        options_layout.addWidget(self._auto_split_check, 0, 1)
        options_layout.addWidget(self._auto_artwork_check, 1, 1)
        options_layout.addWidget(QLabel("Review threshold"), 2, 0)
        options_layout.addWidget(self._review_threshold_combo, 2, 1)
        root.addWidget(options_card)

        artwork_card = QFrame()
        artwork_card.setObjectName("focusedArtworkCard")
        artwork_layout = QVBoxLayout(artwork_card)
        artwork_layout.setContentsMargins(12, 12, 12, 12)
        artwork_layout.setSpacing(8)
        artwork_title = QLabel("Artwork")
        artwork_title.setObjectName("StatusBarText")
        self._artwork_label = QLabel("No artwork")
        self._artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artwork_label.setMinimumHeight(140)
        self._artwork_label.setObjectName("ArtworkPlaceholder")
        artwork_layout.addWidget(artwork_title)
        artwork_layout.addWidget(self._artwork_label)
        root.addWidget(artwork_card)

        self._summary_label = QLabel("No album loaded.")
        self._summary_label.setWordWrap(True)
        root.addWidget(self._summary_label)

        self._review_editor_card = QFrame()
        self._review_editor_card.setObjectName("Card")
        self._review_editor_layout = QVBoxLayout(self._review_editor_card)
        self._review_editor_layout.setContentsMargins(12, 12, 12, 12)
        self._review_editor_layout.setSpacing(8)
        self._review_editor_placeholder = QLabel(
            "Boundary editor will appear here after analysis completes."
        )
        self._review_editor_placeholder.setObjectName("StatusBarText")
        self._review_editor_placeholder.setWordWrap(True)
        self._review_editor_layout.addWidget(self._review_editor_placeholder)
        root.addWidget(self._review_editor_card, stretch=2)

        root.addStretch(1)

        self._progress_card.hide()

    def apply_state(self, state: WorkspaceViewState) -> None:
        self._state = state
        self._sync_state_from_model()

    def set_workspace_manager(self, manager: Any) -> None:
        self._workspace_manager = manager

    def set_preferred_output_directory(self, output_directory: str | None) -> None:
        self._last_output_directory = output_directory or None
        if self._last_output_directory:
            self._settings.setValue(self._PREFERRED_OUTPUT_DIR_KEY, self._last_output_directory)
        else:
            self._settings.remove(self._PREFERRED_OUTPUT_DIR_KEY)
        self._sync_state_from_model()

    def set_preferred_output_format(self, output_format: str | None) -> None:
        normalized = (output_format or "").strip().lower()
        if normalized in {"flac", "wav", "mp3"}:
            self._settings.setValue(self._PREFERRED_OUTPUT_FORMAT_KEY, normalized)

    def begin_startup_flow(self, selection: StartupWizardSelection) -> None:
        self.set_preferred_output_directory(selection.output_directory)
        self.set_preferred_output_format(selection.output_format)
        self._on_file_selected(selection.recording_path)
        if self._analyze_thread is None:
            self._begin_automatic_archive()

    def _sync_state_from_model(self) -> None:
        recording_path = getattr(self._state, "recording_path", None)
        album_artist = getattr(self._state, "album_artist", None) or ""
        album_title = getattr(self._state, "album_title", None) or ""
        status_message = getattr(self._state, "status_message", None) or "Waiting for a recording."
        progress_label = getattr(self._state, "progress_label", None) or "Idle"
        progress_value = getattr(self._state, "progress_value", 0) or 0
        analysis_state = getattr(self._state, "analysis_state", "") or ""
        track_list = tuple(getattr(self._state, "track_list", ()) or ())

        self._auto_analyze_check.setChecked(bool(getattr(self._state, "focused_auto_analyze", True)))
        self._auto_review_check.setChecked(bool(getattr(self._state, "focused_auto_review", True)))
        self._auto_split_check.setChecked(bool(getattr(self._state, "focused_auto_split", False)))
        self._auto_artwork_check.setChecked(bool(getattr(self._state, "focused_auto_artwork", True)))
        threshold_name = getattr(self._state, "focused_review_threshold", "Good")
        threshold_index = self._review_threshold_combo.findText(str(threshold_name))
        if threshold_index >= 0 and threshold_index != self._review_threshold_combo.currentIndex():
            self._review_threshold_combo.setCurrentIndex(threshold_index)

        summary_parts: list[str] = []
        if recording_path:
            summary_parts.append(f"Loaded: {Path(recording_path).name}")
        else:
            summary_parts.append("No album loaded.")

        if album_artist or album_title:
            summary_parts = [f"{album_artist} - {album_title}".strip(" -")]

        if track_list:
            track_count = len(track_list)
            summary_parts.append(f"{track_count} detected tracks")

        if analysis_state == "Complete":
            summary_parts = ["Archive Complete"]
            if album_artist or album_title:
                summary_parts.append(f"{album_artist} - {album_title}".strip(" -"))
            if self._last_output_directory:
                summary_parts.append(f"Saved to {self._last_output_directory}")

        self._summary_label.setText(" | ".join(part for part in summary_parts if part))

        self._status_label.setText(f"{status_message} [{progress_label}]")
        self._progress_bar.setValue(int(progress_value))
        self._set_progress_visible(bool(recording_path) and analysis_state not in {"", "Idle"})
        self._sync_action_buttons()

    def _choose_recording(self) -> None:
        initial_directory = str(
            self._settings.value(
                self._LAST_UPLOAD_DIR_KEY,
                str(Path.home()),
            )
        )

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select a recording",
            initial_directory,
            "Audio Files (*.flac *.wav *.aiff *.aif *.mp3 *.m4a);;All Files (*)",
        )
        if filename:
            self._on_file_selected(filename)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        mime_data = event.mimeData()
        if mime_data.hasUrls() and any(url.isLocalFile() for url in mime_data.urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self._on_file_selected(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    def _on_file_selected(self, file_path: str) -> None:
        try:
            self._settings.setValue(self._LAST_UPLOAD_DIR_KEY, str(Path(file_path).parent))
        except Exception:
            pass

        self._clear_artwork_preview()
        self._clear_embedded_review_editor()
        self._set_state_field("recording_path", file_path)
        self._set_state_field("recording_info", Path(file_path).name)
        self._apply_embedded_metadata_hint(file_path)
        self._set_state_field("analysis_state", "Idle")
        self._set_state_field("review_state", "Pending")
        self._set_state_field("status_message", "Recording loaded. Archiving will begin automatically.")
        self._ui_step = FocusedStep.RECORDING_LOADED
        self._emit_state_change()

        if self._auto_analyze_check.isChecked():
            self._begin_automatic_archive()

    def _begin_automatic_archive(self) -> None:
        if not getattr(self._state, "recording_path", None):
            return

        if self._analyze_thread is not None:
            return

        self._ui_step = FocusedStep.ANALYZING
        self._set_state_field("analysis_state", "Analyzing")
        self._set_state_field("status_message", "Analyzing your recording...")
        self._set_state_field("progress_label", "Analyzing")
        self._set_state_field("progress_value", 10)
        self._set_progress_visible(True)
        self._emit_state_change()

        self._analyze_thread = QThread(self)
        self._analyze_worker = _FocusedAnalyzeWorker(self._app_context, getattr(self._state, "recording_path"))
        self._analyze_worker.moveToThread(self._analyze_thread)
        self._analyze_thread.started.connect(self._analyze_worker.run)
        self._analyze_worker.progress.connect(self._on_analysis_progress)
        self._analyze_worker.completed.connect(self._on_analysis_complete)
        self._analyze_worker.failed.connect(self._on_analysis_failed)
        self._analyze_worker.completed.connect(self._analyze_thread.quit)
        self._analyze_worker.failed.connect(self._analyze_thread.quit)
        self._analyze_thread.finished.connect(self._cleanup_analyze_worker)
        self._analyze_thread.start()

    def _run_analysis(self) -> None:
        self._begin_automatic_archive()

    def _advance_flow(self) -> None:
        if self._ui_step is FocusedStep.WELCOME:
            self._begin_automatic_archive()
        elif self._ui_step is FocusedStep.REVIEW_RECOMMENDED:
            self._open_review_dialog()
        elif self._ui_step is FocusedStep.READY_TO_SPLIT:
            self._start_export()
        elif self._ui_step is FocusedStep.ARCHIVE_COMPLETE:
            self._open_output_folder()

    def _apply_step_ui(self) -> None:
        self._sync_action_buttons()

    def _sync_step_from_state(self) -> None:
        analysis_state = getattr(self._state, "analysis_state", "") or ""
        review_state = getattr(self._state, "review_state", "") or ""
        if analysis_state == "Complete":
            self._ui_step = FocusedStep.ARCHIVE_COMPLETE
        elif analysis_state == "Analyzed" and review_state == "Completed":
            self._ui_step = FocusedStep.READY_TO_SPLIT
        elif analysis_state == "Analyzed":
            self._ui_step = FocusedStep.REVIEW_RECOMMENDED
        elif analysis_state == "Analyzing":
            self._ui_step = FocusedStep.ANALYZING
        elif getattr(self._state, "recording_path", None):
            self._ui_step = FocusedStep.RECORDING_LOADED
        else:
            self._ui_step = FocusedStep.WELCOME

    def _apply_embedded_metadata_hint(self, file_path: str) -> None:
        """Populate the header from embedded tags before acoustic identification runs."""

        try:
            audio = MutagenFile(file_path)
        except Exception:
            audio = None

        tags = getattr(audio, "tags", None)
        if not tags:
            return

        def first_value(keys: tuple[str, ...]) -> str | None:
            for key in keys:
                values = tags.get(key)
                if values:
                    value = values[0]
                    if value:
                        return str(value)
            return None

        artist = first_value(("artist", "ARTIST", "albumartist", "ALBUMARTIST"))
        album = first_value(("album", "ALBUM"))

        if artist:
            self._set_state_field("album_artist", artist)
        if album:
            self._set_state_field("album_title", album)

    @Slot(int, int, str)
    def _on_analysis_progress(self, completed: int, total: int, message: str) -> None:
        total = max(1, total)
        self._set_state_field("progress_value", max(0, min(100, int((completed / total) * 100))))
        self._set_state_field("progress_label", message)
        self._set_state_field("status_message", message)
        self._emit_state_change()

    @Slot(object)
    def _on_analysis_complete(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        review_result = data.get("review_result")
        metadata_match = data.get("metadata_match")
        release_tracklist = data.get("release_tracklist") or []
        release_artwork = data.get("release_artwork")
        confidence = float(data.get("confidence") or 0.0)

        self._analysis_result = data
        self._review_session = getattr(review_result, "session", None)

        if metadata_match is not None:
            self._set_state_field("album_artist", getattr(metadata_match, "artist", ""))
            self._set_state_field("album_title", getattr(metadata_match, "album", ""))
        else:
            self._set_state_field("album_artist", "Album information couldn't be identified")
            self._set_state_field("album_title", Path(getattr(self._state, "recording_path", "") or "").stem)

        boundaries = tuple(getattr(self._review_session, "boundaries", ()) or ())
        if release_tracklist and self._review_session is not None:
            self._review_session.track_titles = list(release_tracklist)
            for index, boundary in enumerate(boundaries):
                if index < len(release_tracklist):
                    boundary.track_title = release_tracklist[index]

        track_labels = tuple(
            getattr(boundary, "track_title", None) or f"Track {getattr(boundary, 'track_number', index + 1):02d}"
            for index, boundary in enumerate(boundaries)
        )
        self._set_state_field("track_list", track_labels)
        self._set_state_field("analysis_state", "Analyzed")
        self._set_state_field("review_state", "Requested")
        self._set_state_field("progress_label", "Analysis complete")
        self._set_state_field("progress_value", 100)
        self._set_state_field("recording_info", f"Detected {len(track_labels)} tracks.")

        if release_artwork:
            self._update_artwork_preview(release_artwork)
        else:
            self._clear_artwork_preview()

        self._ui_step = FocusedStep.REVIEW_RECOMMENDED
        self._set_progress_visible(False)
        self._emit_state_change()
        self._show_embedded_review_editor()

    @Slot(str)
    def _on_analysis_failed(self, message: str) -> None:
        self._set_state_field("analysis_state", "Failed")
        self._set_state_field("status_message", f"We couldn't analyze this recording: {message}")
        self._set_state_field("progress_label", "Analysis failed")
        self._set_state_field("progress_value", 0)
        self._ui_step = FocusedStep.RECORDING_LOADED
        self._set_progress_visible(False)
        self._emit_state_change()

    @Slot()
    def _cleanup_analyze_worker(self) -> None:
        if self._analyze_worker is not None:
            self._analyze_worker.deleteLater()
        self._analyze_worker = None
        self._analyze_thread = None
        self._sync_action_buttons()

    def _open_review_dialog(self) -> None:
        if self._embedded_review_editor is not None:
            self._embedded_review_editor.show()
            self._embedded_review_editor.raise_()
            return

        if ReviewDialog is None:
            self._set_state_field("status_message", "Review dialog is unavailable in this build.")
            self._emit_state_change()
            return

        dialog = self._build_review_dialog()
        if dialog is None:
            self._set_state_field("status_message", "Review could not be opened.")
            self._emit_state_change()
            return

        self._active_review_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._active_review_dialog = None
        self._set_state_field("review_state", "Completed")
        self._ui_step = FocusedStep.READY_TO_SPLIT
        self._sync_action_buttons()
        self._emit_state_change()

        if self._auto_split_check.isChecked():
            self._start_export()

    def _show_embedded_review_editor(self) -> None:
        if ReviewDialog is None:
            self._set_state_field("status_message", "Review editor is unavailable in this build.")
            self._emit_state_change()
            return

        dialog = self._build_review_dialog()
        if dialog is None:
            self._set_state_field("status_message", "Review editor could not be opened.")
            self._emit_state_change()
            return

        self._clear_embedded_review_editor()

        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setWindowFlags(Qt.WindowType.Widget)
        dialog.setParent(self._review_editor_card)
        dialog.accepted.connect(self._on_embedded_review_accepted)
        dialog.rejected.connect(self._on_embedded_review_rejected)
        self._review_editor_layout.addWidget(dialog)
        dialog.show()

        self._embedded_review_editor = dialog
        self._set_state_field("review_state", "In progress")
        self._set_state_field("status_message", "Review editor ready. Adjust boundaries and export when ready.")
        self._sync_action_buttons()
        self._emit_state_change()

    def _clear_embedded_review_editor(self) -> None:
        if self._embedded_review_editor is not None:
            self._embedded_review_editor.setParent(None)
            self._embedded_review_editor.deleteLater()
            self._embedded_review_editor = None

        while self._review_editor_layout.count() > 1:
            item = self._review_editor_layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _on_embedded_review_accepted(self) -> None:
        self._set_state_field("review_state", "Completed")
        self._ui_step = FocusedStep.READY_TO_SPLIT
        self._set_state_field("status_message", "Review accepted. Ready to export.")
        self._sync_action_buttons()
        self._emit_state_change()

    def _on_embedded_review_rejected(self) -> None:
        self._set_state_field("review_state", "Requested")
        self._ui_step = FocusedStep.REVIEW_RECOMMENDED
        self._set_state_field("status_message", "Review closed. Reopen editor to continue refining boundaries.")
        self._sync_action_buttons()
        self._emit_state_change()

    def _build_review_dialog(self) -> QWidget | None:
        recording_path = getattr(self._state, "recording_path", None)
        if recording_path is None:
            return None

        session_dto = None
        get_session_dto = getattr(getattr(self._app_context, "review_controller", None), "get_session_dto", None)
        if callable(get_session_dto):
            session_dto = get_session_dto()

        if session_dto is None and self._review_session is not None:
            session_dto = map_session_to_dto(self._review_session)

        if session_dto is not None:
            boundaries = tuple(self._review_session.boundaries) if self._review_session is not None else None
            return ReviewDialog(session_dto=session_dto, boundaries=boundaries, parent=self)

        if self._review_session is not None:
            return ReviewDialog(boundaries=tuple(self._review_session.boundaries), parent=self)

        return None

    def _start_export(self) -> None:
        if self._export_thread is not None:
            return

        recording_path = getattr(self._state, "recording_path", None)
        if not recording_path:
            return

        output_directory = self._last_output_directory or self._preferred_output_directory()
        if not output_directory:
            output_directory = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if not output_directory:
            return

        self.set_preferred_output_directory(output_directory)
        self._set_state_field("status_message", "Archiving your album...")
        self._set_state_field("progress_label", "Splitting")
        self._set_state_field("progress_value", 15)
        self._set_progress_visible(True)
        self._emit_state_change()

        self._export_thread = QThread(self)
        self._export_worker = _FocusedExportWorker(
            self._app_context,
            recording_path,
            output_directory,
            self._auto_artwork_check.isChecked(),
            getattr(self._review_session, "session", self._review_session),
            self._preferred_output_format(),
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

    @Slot(int, int, str)
    def _on_export_progress(self, completed: int, total: int, message: str) -> None:
        total = max(1, total)
        self._set_state_field("progress_value", max(0, min(100, int((completed / total) * 100))))
        self._set_state_field("progress_label", message)
        self._set_state_field("status_message", message)
        self._emit_state_change()

    @Slot(object)
    def _on_export_complete(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        output_directory = data.get("output_directory") or self._last_output_directory
        exported_tracks_raw = data.get("exported_tracks")
        if isinstance(exported_tracks_raw, int):
            exported_tracks_count = exported_tracks_raw
        elif isinstance(exported_tracks_raw, (list, tuple, set)):
            exported_tracks_count = len(exported_tracks_raw)
        else:
            exported_tracks_count = 0
        self._set_state_field("analysis_state", "Complete")
        self._set_state_field("review_state", "Completed")
        self._set_state_field("progress_label", "Archive complete")
        self._set_state_field("progress_value", 100)
        self._set_state_field("status_message", "Archive complete.")
        self._set_progress_visible(False)
        self._ui_step = FocusedStep.ARCHIVE_COMPLETE
        self._emit_state_change()

        if output_directory:
            self._last_output_directory = str(output_directory)

        if exported_tracks_count > 0:
            self._set_state_field("recording_info", f"Archive complete: {exported_tracks_count} tracks saved.")
        self._sync_action_buttons()

    @Slot(str)
    def _on_export_failed(self, message: str) -> None:
        self._set_state_field("status_message", f"Archive failed: {message}")
        self._set_state_field("progress_label", "Archive failed")
        self._set_state_field("progress_value", 0)
        self._set_progress_visible(False)
        self._emit_state_change()

    @Slot()
    def _cleanup_export_worker(self) -> None:
        if self._export_worker is not None:
            self._export_worker.deleteLater()
        self._export_worker = None
        self._export_thread = None
        self._sync_action_buttons()

    def _open_output_folder(self) -> None:
        output_directory = self._last_output_directory
        if not output_directory:
            output_directory = self._preferred_output_directory()
        if not output_directory:
            output_directory = QFileDialog.getExistingDirectory(self, "Choose output folder")
            if not output_directory:
                return
            self.set_preferred_output_directory(output_directory)

        QDesktopServices.openUrl(QUrl.fromLocalFile(output_directory))

    def _reset_for_next_album(self) -> None:
        self._clear_artwork_preview()
        self._clear_embedded_review_editor()
        self._set_state_field("recording_path", None)
        self._set_state_field("recording_info", None)
        self._set_state_field("album_artist", None)
        self._set_state_field("album_title", None)
        self._set_state_field("analysis_state", "Idle")
        self._set_state_field("review_state", "Pending")
        self._set_state_field("status_message", "Ready for the next album.")
        self._set_state_field("progress_label", "Idle")
        self._set_state_field("progress_value", 0)
        self._set_state_field("track_list", tuple())
        self._review_session = None
        self._analysis_result = None
        self._ui_step = FocusedStep.WELCOME
        self._set_progress_visible(False)
        self._emit_state_change()

    def _sync_action_buttons(self) -> None:
        has_recording = bool(getattr(self._state, "recording_path", None))
        busy = self._analyze_thread is not None or self._export_thread is not None
        has_tracks = bool(tuple(getattr(self._state, "track_list", ()) or ()))

        self._archive_button.setEnabled(has_recording and not busy)
        self._review_button.setEnabled(has_tracks and not busy)
        self._split_button.setEnabled(has_tracks and not busy)
        self._open_output_button.setEnabled(bool(self._last_output_directory))
        self._archive_again_button.setEnabled(self._ui_step is FocusedStep.ARCHIVE_COMPLETE)

    def _set_progress_visible(self, visible: bool) -> None:
        self._progress_card.setVisible(visible)

    def _update_artwork_preview(self, artwork: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(artwork):
            self._artwork_label.setPixmap(
                pixmap.scaled(
                    180,
                    180,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._artwork_label.setText("")
            self._artwork_available = True
            return
        self._clear_artwork_preview()

    def _clear_artwork_preview(self) -> None:
        self._artwork_label.clear()
        self._artwork_label.setText("No artwork")
        self._artwork_available = False

    def _review_threshold_value(self) -> float:
        value = self._review_threshold_combo.currentData()
        return float(value) if value is not None else 0.85

    def _on_review_threshold_changed(self, index: int) -> None:
        self._set_state_field("focused_review_threshold", self._review_threshold_combo.currentText())

    def _preferred_output_directory(self) -> str | None:
        value = self._settings.value(self._PREFERRED_OUTPUT_DIR_KEY, "")
        cleaned = str(value or "").strip()
        return cleaned or None

    def _preferred_output_format(self) -> str:
        value = self._settings.value(self._PREFERRED_OUTPUT_FORMAT_KEY, "flac")
        cleaned = str(value or "flac").strip().lower()
        if cleaned not in {"flac", "wav", "mp3"}:
            return "flac"
        return cleaned

    def _set_state_field(self, name: str, value: Any) -> None:
        try:
            setattr(self._state, name, value)
        except Exception:
            pass

    def _emit_state_change(self) -> None:
        self._sync_state_from_model()
        self.state_changed.emit(self._state)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._shutdown_active_review_dialog()
        self._shutdown_background_threads()
        super().closeEvent(event)

    def _shutdown_active_review_dialog(self) -> None:
        dialog = self._active_review_dialog
        if dialog is not None:
            dialog.close()
        self._active_review_dialog = None
        self._clear_embedded_review_editor()

    def _shutdown_background_threads(self) -> None:
        for thread in (self._analyze_thread, self._export_thread):
            if thread is not None and thread.isRunning():
                thread.requestInterruption()
                thread.quit()
                if not thread.wait(3000):
                    thread.terminate()
                    thread.wait(1000)


class _FocusedAnalyzeWorker(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, app_context: ApplicationContext, recording_path: str) -> None:
        super().__init__()
        self._app_context = app_context
        self._recording_path = recording_path

    @Slot()
    def run(self) -> None:
        try:
            self.progress.emit(1, 4, "Analyzing recording...")
            review_controller = getattr(self._app_context, "review_controller", None)
            analyze_controller = getattr(self._app_context, "analyze_controller", None)
            review_result = None
            if review_controller is not None and hasattr(review_controller, "review"):
                review_result = review_controller.review(self._recording_path)

            self.progress.emit(2, 4, "Looking up metadata...")
            metadata_match = None
            release_tracklist: list[str] = []
            release_artwork: bytes | None = None
            if analyze_controller is not None and hasattr(analyze_controller, "lookup_metadata"):
                try:
                    metadata = analyze_controller.lookup_metadata(self._recording_path)
                    metadata_match = getattr(metadata, "match", None)
                except Exception:
                    metadata_match = None

            release_id = getattr(metadata_match, "release_id", "") if metadata_match is not None else ""
            if release_id:
                try:
                    release_tracklist = self._app_context.pipeline.resolver.musicbrainz.tracklist(release_id)
                except Exception:
                    release_tracklist = []

                try:
                    release_artwork = self._app_context.pipeline.artwork.download_artwork(release_id)
                except Exception:
                    release_artwork = None

            confidence = 0.0
            if review_result is not None:
                session = getattr(review_result, "session", None)
                confidence = float(
                    getattr(session, "average_confidence", None)
                    or getattr(review_result, "confidence", None)
                    or 0.0
                )

            self.progress.emit(3, 4, "Preparing archive...")
            self.completed.emit(
                {
                    "review_result": review_result,
                    "metadata_match": metadata_match,
                    "release_tracklist": release_tracklist,
                    "release_artwork": release_artwork,
                    "confidence": confidence,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class _FocusedExportWorker(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        app_context: ApplicationContext,
        recording_path: str,
        output_directory: str,
        fetch_artwork: bool,
        review_session: Any | None,
        output_format: str,
    ) -> None:
        super().__init__()
        self._app_context = app_context
        self._recording_path = recording_path
        self._output_directory = output_directory
        self._fetch_artwork = fetch_artwork
        self._review_session = review_session
        self._output_format = output_format

    @Slot()
    def run(self) -> None:
        def on_progress(event: Any) -> None:
            completed = int(getattr(event, "completed", 0) or 0)
            total = int(getattr(event, "total", 0) or 0)
            description = str(getattr(event, "description", "Exporting"))
            self.progress.emit(completed, total, description)

        try:
            self.progress.emit(1, 3, "Splitting audio...")
            result = asyncio.run(
                self._app_context.export_controller.export(
                    filename=self._recording_path,
                    output_directory=self._output_directory,
                    review_session=self._review_session,
                    progress_callback=on_progress,
                    output_format=self._output_format,
                )
            )
            exported_tracks = int(getattr(result, "exported_tracks", 0) or 0)

            if self._fetch_artwork:
                for candidate_name in ("artwork_service", "coverart_service"):
                    candidate = getattr(self._app_context, candidate_name, None)
                    if candidate is None:
                        continue
                    artwork_fn = getattr(candidate, "download", None) or getattr(candidate, "fetch", None) or getattr(candidate, "attach", None)
                    if callable(artwork_fn):
                        try:
                            artwork_fn(self._recording_path, self._output_directory)
                        except TypeError:
                            try:
                                artwork_fn(self._recording_path)
                            except Exception:
                                pass
                        break

            self.progress.emit(2, 3, "Finalizing archive...")
            self.completed.emit({"output_directory": self._output_directory, "exported_tracks": exported_tracks})
        except Exception as exc:
            self.failed.emit(str(exc))