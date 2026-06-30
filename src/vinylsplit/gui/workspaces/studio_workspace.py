from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from vinylsplit.application import ApplicationContext
from vinylsplit.application.events import ProgressUpdated
from vinylsplit.application.services.review_mapper import map_boundary_to_dto
from vinylsplit.gui.dialogs import ReviewDialog
from vinylsplit.gui.state import WorkspaceViewState
from vinylsplit.gui.widgets.review_waveform import ReviewWaveformView


class StudioWorkspace(QWidget):
    """Advanced Studio workspace with full end-to-end processing controls."""

    state_changed = Signal(object)

    def __init__(self, app_context: ApplicationContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app_context = app_context
        self._state = WorkspaceViewState(active_workspace="studio")
        self._review_session: object | None = None
        self._last_output_directory: str | None = None
        self._analyze_thread: QThread | None = None
        self._analyze_worker: _StudioAnalyzeWorker | None = None
        self._export_thread: QThread | None = None
        self._export_worker: _StudioExportWorker | None = None
        self._identify_thread: QThread | None = None
        self._identify_worker: _StudioDeepIdentifyWorker | None = None
        self._playhead_seconds = 0.0
        self._is_playing = False
        self._waveform_widget: ReviewWaveformView | None = None
        self._artwork_available = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        title = QLabel("Studio Workspace")
        title.setObjectName("SectionTitle")
        subtitle = QLabel("Full workflow mode: analyze, review, split, and inspect from Studio")
        subtitle.setObjectName("FocusedSubtitle")

        toolbar = QFrame()
        toolbar.setObjectName("Card")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        toolbar_layout.setSpacing(10)

        self._analyze_button = QPushButton("Analyze")
        self._analyze_button.clicked.connect(self._run_analysis)
        toolbar_layout.addWidget(self._analyze_button)

        self._reanalyze_button = QPushButton("Reanalyze")
        self._reanalyze_button.clicked.connect(self._run_analysis)
        toolbar_layout.addWidget(self._reanalyze_button)

        self._review_button = QPushButton("Review")
        self._review_button.clicked.connect(self._open_review_dialog)
        toolbar_layout.addWidget(self._review_button)

        self._deep_identify_button = QPushButton("Deep Identify")
        self._deep_identify_button.clicked.connect(self._run_deep_identify)
        toolbar_layout.addWidget(self._deep_identify_button)

        self._split_button = QPushButton("Split Album")
        self._split_button.clicked.connect(self._start_export)
        toolbar_layout.addWidget(self._split_button)

        self._open_output_button = QPushButton("Open Output Folder")
        self._open_output_button.clicked.connect(self._open_output_folder)
        toolbar_layout.addWidget(self._open_output_button)

        toolbar_layout.addStretch(1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self._track_list = QListWidget()
        self._track_list.setObjectName("TrackList")
        self._track_list.addItem(QListWidgetItem("No tracks yet"))
        self._track_list.itemSelectionChanged.connect(self._on_track_selection_changed)

        grid.addWidget(self._build_waveform_panel(), 0, 0, 1, 2)
        grid.addWidget(self._build_track_panel(), 1, 0)
        grid.addWidget(self._build_metadata_panel(), 1, 1)
        grid.addWidget(self._build_boundary_panel(), 2, 0)
        grid.addWidget(self._build_playback_panel(), 2, 1)
        grid.addWidget(self._build_spectrogram_panel(), 3, 0)
        grid.addWidget(self._build_analysis_panel(), 3, 1)

        status = QFrame()
        status.setObjectName("Card")
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(12, 10, 12, 10)
        self._status_label = QLabel("Studio ready")
        self._status_label.setObjectName("StatusBarText")
        status_layout.addWidget(self._status_label)

        root.addWidget(toolbar)
        root.addWidget(self._build_progress_panel())
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addLayout(grid)
        root.addWidget(status)

        self._refresh_progress_panel()
        self._refresh_studio_panels()
        self._sync_action_buttons()

    def load_recording(self, filename: str) -> None:
        """Load recording while staying in Studio workspace."""

        path = Path(filename)
        self._review_session = None
        self._last_output_directory = None
        self._state.recording_path = str(path)
        self._state.recording_info = f"Recording loaded: {path.name}"
        self._state.status_message = "Recording loaded in Studio. Ready to analyze."
        self._state.progress_value = 0
        self._state.progress_label = "Ready to analyze"
        self._state.analysis_state = "Not started"
        self._state.review_state = "Not requested"
        self._state.track_list = ()
        self._state.album_artist = "Unknown Artist"
        self._state.album_title = "Unknown Album"
        self._emit_state_change()

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
            self._track_list.addItem(QListWidgetItem("Load complete. Press Analyze to populate tracks."))
        else:
            self._track_list.addItem(QListWidgetItem("No tracks yet"))

        if self._track_list.count() > 0 and state.track_list:
            self._track_list.setCurrentRow(0)

        self._refresh_progress_panel()
        self._refresh_studio_panels()
        self._sync_action_buttons()

    def current_state(self) -> WorkspaceViewState:
        """Return current local state snapshot."""

        return self._state

    def _run_analysis(self) -> None:
        if not self._state.recording_path:
            self._state.status_message = "Load a recording first to analyze in Studio."
            self._emit_state_change()
            return

        if self._analyze_thread is not None:
            self._state.status_message = "Analysis already running."
            self._emit_state_change()
            return

        self._analyze_button.setEnabled(False)
        self._reanalyze_button.setEnabled(False)
        self._state.analysis_state = "Analyzing"
        self._state.progress_label = "Analyzing"
        self._state.progress_value = 5
        self._state.status_message = "Studio analysis in progress..."
        self._emit_state_change()

        self._analyze_thread = QThread(self)
        self._analyze_worker = _StudioAnalyzeWorker(
            app_context=self._app_context,
            recording_path=self._state.recording_path,
        )
        self._analyze_worker.moveToThread(self._analyze_thread)
        self._analyze_thread.started.connect(self._analyze_worker.run)
        self._analyze_worker.progress.connect(self._on_analyze_progress)
        self._analyze_worker.completed.connect(self._on_analyze_complete)
        self._analyze_worker.failed.connect(self._on_analyze_failed)
        self._analyze_worker.completed.connect(self._analyze_thread.quit)
        self._analyze_worker.failed.connect(self._analyze_thread.quit)
        self._analyze_thread.finished.connect(self._cleanup_analyze_worker)
        self._analyze_thread.start()

    @Slot(int, str)
    def _on_analyze_progress(self, value: int, message: str) -> None:
        self._state.progress_value = value
        self._state.status_message = message
        self._emit_state_change()

    @Slot(object)
    def _on_analyze_complete(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        review_session = data.get("review_session")
        metadata_match = data.get("metadata_match")

        if review_session is None:
            self._state.analysis_state = "Failed"
            self._state.progress_label = "Analysis failed"
            self._state.progress_value = 0
            self._state.status_message = "Studio analysis failed. Try reanalyze."
            self._emit_state_change()
            return

        self._review_session = review_session
        boundaries = tuple(self._review_session.boundaries)
        self._state.analysis_state = "Analyzed"
        self._state.review_state = "Requested"
        self._state.progress_label = "Analysis complete"
        self._state.progress_value = 100
        self._state.track_list = _build_track_overview(boundaries)
        self._state.recording_info = f"Detected {len(boundaries)} tracks in Studio workflow."

        if metadata_match is not None:
            self._state.album_artist = getattr(metadata_match, "artist", "Unknown Artist")
            self._state.album_title = getattr(metadata_match, "album", Path(self._state.recording_path or "").stem)
            self._enrich_with_release_metadata(getattr(metadata_match, "release_id", ""))
            self._state.status_message = "Analysis complete. Metadata resolved. Use Review, then Split Album."
        else:
            self._state.album_artist = "Album information couldn't be identified"
            self._state.album_title = Path(self._state.recording_path or "").stem
            self._clear_artwork_preview()
            self._state.status_message = "Analysis complete. Run Deep Identify for full metadata/artwork."

        self._emit_state_change()

    @Slot(str)
    def _on_analyze_failed(self, message: str) -> None:
        self._state.analysis_state = "Failed"
        self._state.progress_label = "Analysis failed"
        self._state.progress_value = 0
        self._state.status_message = f"Analysis failed: {message}"
        self._emit_state_change()

    @Slot()
    def _cleanup_analyze_worker(self) -> None:
        if self._analyze_worker is not None:
            self._analyze_worker.deleteLater()
        self._analyze_worker = None
        self._analyze_thread = None
        self._analyze_button.setEnabled(bool(self._state.recording_path))
        self._reanalyze_button.setEnabled(bool(self._state.recording_path))

    def _enrich_with_release_metadata(self, release_id: str) -> None:
        """Fetch official track list and cover art using the resolved release id."""

        if not release_id:
            self._clear_artwork_preview()
            return

        # Pull official track names from MusicBrainz and apply to boundaries.
        try:
            tracklist = self._app_context.pipeline.resolver.musicbrainz.tracklist(release_id)
        except Exception:
            tracklist = []

        if tracklist and self._review_session is not None:
            self._review_session.track_titles = list(tracklist)
            boundaries = tuple(self._review_session.boundaries)
            for idx, boundary in enumerate(boundaries):
                if idx < len(tracklist):
                    boundary.track_title = tracklist[idx]
            self._state.track_list = _build_track_overview(boundaries)

        # Pull cover art bytes and show preview in metadata panel.
        try:
            artwork = self._app_context.pipeline.artwork.download_artwork(release_id)
        except Exception:
            artwork = None

        if artwork:
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

    def _enrich_via_track_consensus(self) -> bool:
        """Fallback identification using temporary split tracks, similar to CLI process flow."""

        if self._review_session is None or not self._state.recording_path:
            return False

        boundaries = list(self._review_session.boundaries)
        if not boundaries:
            return False

        identified: list[tuple[object, object]] = []
        try:
            with TemporaryDirectory(prefix="vinylsplit-studio-identify-") as tmp_dir:
                tracks = self._app_context.pipeline.splitter.split(
                    filename=self._state.recording_path,
                    boundaries=boundaries,
                    output_directory=tmp_dir,
                )

                # Probe a subset to keep Studio analysis responsive.
                for track in tracks[: min(6, len(tracks))]:
                    try:
                        match = self._app_context.pipeline.identifier.identify(
                            source_file=self._state.recording_path,
                            track=track,
                        )
                    except Exception:
                        continue
                    identified.append((track, match))
        except Exception:
            return False

        if not identified:
            return False

        try:
            album, official_tracks = self._app_context.pipeline.resolver.resolve(identified)
        except Exception:
            return False

        if album is None:
            return False

        self._state.album_artist = album.artist
        self._state.album_title = album.album
        if self._review_session is not None:
            self._review_session.album_artist = album.artist
            self._review_session.album_title = album.album
            self._review_session.album_year = album.year
            self._review_session.release_id = album.release_id

        if official_tracks and self._review_session is not None:
            self._review_session.track_titles = list(official_tracks)
            for idx, boundary in enumerate(self._review_session.boundaries):
                if idx < len(official_tracks):
                    boundary.track_title = official_tracks[idx]
            self._state.track_list = _build_track_overview(tuple(self._review_session.boundaries))

        self._enrich_with_release_metadata(album.release_id)
        return True

    def _open_review_dialog(self) -> None:
        if self._review_session is None:
            self._state.status_message = "Analyze first, then open Review."
            self._emit_state_change()
            return

        session_dto = self._app_context.review_controller.get_session_dto()
        if session_dto is not None:
            dialog = ReviewDialog(session_dto=session_dto, parent=self)
        else:
            dialog = ReviewDialog(boundaries=tuple(self._review_session.boundaries), parent=self)

        if dialog.exec() == ReviewDialog.DialogCode.Accepted:
            self._state.review_state = "Completed"
            self._state.progress_label = "Review approved"
            self._state.progress_value = 0
            self._state.status_message = "Review complete. Ready to split from Studio."
            self._emit_state_change()

    def _run_deep_identify(self) -> None:
        """Run full per-track consensus identification, similar to CLI process."""

        if self._review_session is None or not self._state.recording_path:
            self._state.status_message = "Analyze first, then run Deep Identify."
            self._emit_state_change()
            return

        if self._identify_thread is not None:
            self._state.status_message = "Deep Identify already running."
            self._emit_state_change()
            return

        self._identify_thread = QThread(self)
        self._identify_worker = _StudioDeepIdentifyWorker(
            app_context=self._app_context,
            recording_path=self._state.recording_path,
            review_session=self._review_session,
        )
        self._identify_worker.moveToThread(self._identify_thread)
        self._identify_thread.started.connect(self._identify_worker.run)
        self._identify_worker.progress.connect(self._on_deep_identify_progress)
        self._identify_worker.completed.connect(self._on_deep_identify_complete)
        self._identify_worker.failed.connect(self._on_deep_identify_failed)
        self._identify_worker.completed.connect(self._identify_thread.quit)
        self._identify_worker.failed.connect(self._identify_thread.quit)
        self._identify_thread.finished.connect(self._cleanup_identify_worker)

        self._state.progress_label = "Deep Identify"
        self._state.progress_value = 0
        self._state.status_message = "Running full track consensus identification..."
        self._emit_state_change()

        self._identify_thread.start()

    @Slot(int, int, str)
    def _on_deep_identify_progress(self, completed: int, total: int, message: str) -> None:
        self._state.progress_label = "Deep Identify"
        self._state.progress_value = max(0, min(100, int((completed / max(1, total)) * 100)))
        self._state.status_message = message
        self._emit_state_change()

    @Slot(object)
    def _on_deep_identify_complete(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        album = data.get("album")
        tracklist = data.get("tracklist") or []

        if album is None:
            self._state.status_message = "Deep Identify completed with no consensus album."
            self._state.progress_label = "Deep Identify"
            self._state.progress_value = 100
            self._emit_state_change()
            return

        self._state.album_artist = getattr(album, "artist", self._state.album_artist)
        self._state.album_title = getattr(album, "album", self._state.album_title)

        if self._review_session is not None:
            self._review_session.album_artist = getattr(album, "artist", None)
            self._review_session.album_title = getattr(album, "album", None)
            self._review_session.album_year = getattr(album, "year", None)
            self._review_session.release_id = getattr(album, "release_id", None)
            if tracklist:
                self._review_session.track_titles = list(tracklist)
                for idx, boundary in enumerate(self._review_session.boundaries):
                    if idx < len(tracklist):
                        boundary.track_title = tracklist[idx]
                self._state.track_list = _build_track_overview(tuple(self._review_session.boundaries))

        self._enrich_with_release_metadata(getattr(album, "release_id", ""))
        self._state.progress_label = "Deep Identify"
        self._state.progress_value = 100
        self._state.status_message = "Deep Identify complete: album consensus and artwork applied."
        self._emit_state_change()

    @Slot(str)
    def _on_deep_identify_failed(self, message: str) -> None:
        self._state.progress_label = "Deep Identify"
        self._state.progress_value = 0
        self._state.status_message = f"Deep Identify failed: {message}"
        self._emit_state_change()

    @Slot()
    def _cleanup_identify_worker(self) -> None:
        if self._identify_worker is not None:
            self._identify_worker.deleteLater()
        self._identify_worker = None
        self._identify_thread = None

    def _start_export(self) -> None:
        if self._review_session is None or not self._state.recording_path:
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
        self._state.progress_label = "Preparing"
        self._state.progress_value = 5
        self._state.status_message = "Splitting from Studio..."
        self._emit_state_change()

        self._export_thread = QThread(self)
        self._export_worker = _StudioExportWorker(
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
        self._state.progress_label = event.stage
        if event.description:
            self._state.status_message = event.description
        if event.total and event.total > 0:
            self._state.progress_value = max(0, min(100, int((event.completed / event.total) * 100)))
        self._emit_state_change()

    @Slot(int)
    def _on_export_complete(self, exported_tracks: int) -> None:
        if self._last_output_directory:
            exported_tracks = len(list(Path(self._last_output_directory).rglob("*.flac")))
        self._state.progress_value = 0
        self._state.progress_label = "Idle"
        self._state.status_message = f"Split complete from Studio. {exported_tracks} tracks created."
        self._state.recording_info = f"Album exported: {exported_tracks} FLAC tracks"
        self._emit_state_change()

    @Slot(str)
    def _on_export_failed(self, message: str) -> None:
        self._state.progress_value = 0
        self._state.progress_label = "Split failed"
        self._state.status_message = "Split failed in Studio. Try again."
        self._emit_state_change()

    @Slot()
    def _cleanup_export_worker(self) -> None:
        if self._export_worker is not None:
            self._export_worker.deleteLater()
        self._export_worker = None
        self._export_thread = None

    def _open_output_folder(self) -> None:
        if not self._last_output_directory:
            self._state.status_message = "No exported output folder yet."
            self._emit_state_change()
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_output_directory))
        self._state.status_message = "Output folder opened from Studio."
        self._emit_state_change()

    def _sync_action_buttons(self) -> None:
        has_recording = bool(self._state.recording_path)
        analyze_idle = self._analyze_thread is None
        has_analysis = self._state.analysis_state == "Analyzed"
        review_done = self._state.review_state == "Completed"
        has_output = bool(self._last_output_directory)
        has_selection = bool(self._state.track_list) and self._track_list.currentRow() >= 0

        self._analyze_button.setEnabled(has_recording and analyze_idle)
        self._reanalyze_button.setEnabled(has_recording and analyze_idle)
        self._review_button.setEnabled(has_analysis)
        deep_identify_idle = self._identify_thread is None
        self._deep_identify_button.setEnabled(has_analysis and deep_identify_idle)
        self._split_button.setEnabled(review_done)
        self._open_output_button.setEnabled(has_output)
        self._play_button.setEnabled(has_selection)
        self._pause_button.setEnabled(has_selection)
        self._prev_button.setEnabled(has_selection)
        self._next_button.setEnabled(has_selection)
        self._seek_slider.setEnabled(has_selection)

    def _emit_state_change(self) -> None:
        self.apply_state(self._state)
        self.state_changed.emit(self._state)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Ensure worker threads stop cleanly when Studio widget is closed."""

        self._shutdown_background_threads()
        super().closeEvent(event)

    def _shutdown_background_threads(self) -> None:
        if self._analyze_thread is not None and self._analyze_thread.isRunning():
            self._analyze_thread.requestInterruption()
            self._analyze_thread.quit()
            if not self._analyze_thread.wait(5000):
                self._analyze_thread.terminate()
                self._analyze_thread.wait(2000)

        if self._identify_thread is not None and self._identify_thread.isRunning():
            self._identify_thread.requestInterruption()
            self._identify_thread.quit()
            if not self._identify_thread.wait(5000):
                self._identify_thread.terminate()
                self._identify_thread.wait(2000)

        if self._export_thread is not None and self._export_thread.isRunning():
            self._export_thread.requestInterruption()
            self._export_thread.quit()
            if not self._export_thread.wait(5000):
                self._export_thread.terminate()
                self._export_thread.wait(2000)

    def _build_waveform_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        self._waveform_layout = QVBoxLayout(panel)
        self._waveform_layout.setContentsMargins(12, 12, 12, 12)
        self._waveform_layout.setSpacing(6)

        title = QLabel("Waveform")
        title.setObjectName("SectionTitle")
        self._waveform_summary = QLabel("No waveform data yet. Load and analyze a recording.")
        self._waveform_summary.setWordWrap(True)
        self._waveform_summary.setObjectName("StatusBarText")

        self._waveform_layout.addWidget(title)
        self._waveform_layout.addWidget(self._waveform_summary)
        return panel

    def _build_progress_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        self._progress_title = QLabel("Progress")
        self._progress_title.setObjectName("StatusBarText")

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)

        self._progress_detail = QLabel("Idle")
        self._progress_detail.setObjectName("StatusBarText")

        layout.addWidget(self._progress_title)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._progress_detail)
        return panel

    def _refresh_progress_panel(self) -> None:
        value = max(0, min(100, int(self._state.progress_value)))
        self._progress_bar.setValue(value)
        self._progress_detail.setText(f"{self._state.progress_label} ({value}%)")

    def _build_track_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        title = QLabel("Track List")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        layout.addWidget(self._track_list)
        return panel

    def _build_metadata_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        title = QLabel("Metadata Inspector")
        title.setObjectName("SectionTitle")

        self._artwork_label = QLabel("No artwork")
        self._artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artwork_label.setMinimumHeight(120)
        self._artwork_label.setObjectName("ArtworkPlaceholder")

        self._metadata_label = QLabel("No metadata loaded.")
        self._metadata_label.setObjectName("StatusBarText")
        self._metadata_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self._artwork_label)
        layout.addWidget(self._metadata_label)
        return panel

    def _build_boundary_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        title = QLabel("Boundary Inspector")
        title.setObjectName("SectionTitle")
        self._boundary_label = QLabel("Select a track to inspect boundary details.")
        self._boundary_label.setObjectName("StatusBarText")
        self._boundary_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self._boundary_label)
        return panel

    def _build_playback_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Playback Controls")
        title.setObjectName("SectionTitle")

        buttons = QHBoxLayout()
        self._prev_button = QPushButton("Prev")
        self._prev_button.clicked.connect(self._on_prev_track)
        self._play_button = QPushButton("Play")
        self._play_button.clicked.connect(self._on_play)
        self._pause_button = QPushButton("Pause")
        self._pause_button.clicked.connect(self._on_pause)
        self._next_button = QPushButton("Next")
        self._next_button.clicked.connect(self._on_next_track)

        buttons.addWidget(self._prev_button)
        buttons.addWidget(self._play_button)
        buttons.addWidget(self._pause_button)
        buttons.addWidget(self._next_button)

        self._seek_slider = QSlider()
        self._seek_slider.setOrientation(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 1000)
        self._seek_slider.valueChanged.connect(self._on_seek_changed)

        self._playback_label = QLabel("Position: 00:00.00")
        self._playback_label.setObjectName("StatusBarText")

        layout.addWidget(title)
        layout.addLayout(buttons)
        layout.addWidget(self._seek_slider)
        layout.addWidget(self._playback_label)
        return panel

    def _build_spectrogram_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        title = QLabel("Spectrogram View")
        title.setObjectName("SectionTitle")
        self._spectrogram_label = QLabel("Spectral summary unavailable until analysis completes.")
        self._spectrogram_label.setObjectName("StatusBarText")
        self._spectrogram_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self._spectrogram_label)
        return panel

    def _build_analysis_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        title = QLabel("Analysis Insights")
        title.setObjectName("SectionTitle")
        self._analysis_label = QLabel("No analysis insights yet.")
        self._analysis_label.setObjectName("StatusBarText")
        self._analysis_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self._analysis_label)
        return panel

    def _on_track_selection_changed(self) -> None:
        row = self._track_list.currentRow()
        if row < 0:
            return
        boundary = self._boundary_for_row(row)
        if boundary is not None:
            self._playhead_seconds = float(getattr(boundary, "start_time", 0.0))
        self._refresh_studio_panels()
        self._sync_action_buttons()

    def _on_play(self) -> None:
        self._is_playing = True
        self._state.status_message = "Playback started in Studio preview mode."
        self._emit_state_change()

    def _on_pause(self) -> None:
        self._is_playing = False
        self._state.status_message = "Playback paused in Studio preview mode."
        self._emit_state_change()

    def _on_prev_track(self) -> None:
        row = max(0, self._track_list.currentRow() - 1)
        self._track_list.setCurrentRow(row)

    def _on_next_track(self) -> None:
        row = min(self._track_list.count() - 1, self._track_list.currentRow() + 1)
        self._track_list.setCurrentRow(row)

    def _on_seek_changed(self, value: int) -> None:
        boundaries = self._boundaries()
        if not boundaries:
            self._playback_label.setText("Position: 00:00.00")
            return

        max_time = float(getattr(boundaries[-1], "start_time", 0.0)) + 30.0
        self._playhead_seconds = (value / 1000.0) * max(1.0, max_time)
        self._playback_label.setText(f"Position: {_format_timestamp(self._playhead_seconds)}")

    def _refresh_studio_panels(self) -> None:
        self._refresh_metadata_panel()
        self._refresh_boundary_panel()
        self._refresh_waveform_panel()
        self._refresh_spectrogram_panel()
        self._refresh_analysis_panel()
        self._refresh_playback_panel()

    def _refresh_metadata_panel(self) -> None:
        recording = Path(self._state.recording_path).name if self._state.recording_path else "--"
        self._metadata_label.setText(
            f"File: {recording}\n"
            f"Artist: {self._state.album_artist}\n"
            f"Album: {self._state.album_title}\n"
            f"Analysis: {self._state.analysis_state}\n"
            f"Review: {self._state.review_state}\n"
            f"Artwork: {'available' if self._artwork_available else 'not available'}"
        )

    def _clear_artwork_preview(self) -> None:
        self._artwork_label.clear()
        self._artwork_label.setText("No artwork")
        self._artwork_available = False

    def _refresh_boundary_panel(self) -> None:
        row = self._track_list.currentRow()
        boundary = self._boundary_for_row(row)
        if boundary is None:
            self._boundary_label.setText("Select a track to inspect boundary details.")
            return

        start = float(getattr(boundary, "start_time", 0.0))
        end = self._boundary_end_seconds(row)
        duration = (end - start) if end is not None else None
        confidence = getattr(boundary, "detector_confidence", None)
        title = getattr(boundary, "track_title", None) or f"Track {getattr(boundary, 'track_number', row + 1):02d}"
        status = str(getattr(boundary, "state", "AUTO"))

        self._boundary_label.setText(
            f"Track: {getattr(boundary, 'track_number', row + 1)}\n"
            f"Title: {title}\n"
            f"Start: {_format_timestamp(start)}\n"
            f"End: {_format_timestamp(end) if end is not None else 'End'}\n"
            f"Duration: {_format_duration(duration) if duration is not None else '--'}\n"
            f"Confidence: {f'{confidence * 100:.0f}%' if confidence is not None else '--'}\n"
            f"State: {status}"
        )

    def _refresh_waveform_panel(self) -> None:
        row = self._track_list.currentRow()
        boundary = self._boundary_for_row(row)
        if boundary is None:
            self._waveform_summary.setText("No waveform data yet. Load and analyze a recording.")
            if self._waveform_widget is not None:
                self._waveform_widget.setParent(None)
                self._waveform_widget.deleteLater()
                self._waveform_widget = None
            return

        start = float(getattr(boundary, "start_time", 0.0))
        end = self._boundary_end_seconds(row)
        duration = (end - start) if end is not None else 30.0
        candidates = len(getattr(boundary, "candidate_boundaries", []) or [])
        playhead = self._playhead_seconds
        marker = "■" if self._is_playing else "□"
        self._waveform_summary.setText(
            f"{marker} Track window: {_format_timestamp(start)} -> "
            f"{_format_timestamp(end) if end is not None else 'End'}\n"
            f"Estimated length: {_format_duration(duration)}\n"
            f"Candidate boundaries: {candidates}\n"
            f"Playhead: {_format_timestamp(playhead)}"
        )

        # Replace any prior waveform widget for the newly selected boundary.
        if self._waveform_widget is not None:
            self._waveform_widget.setParent(None)
            self._waveform_widget.deleteLater()
            self._waveform_widget = None

        try:
            boundary_dto = map_boundary_to_dto(boundary)
        except Exception:
            return

        session_duration = self._estimated_session_duration()
        self._waveform_widget = ReviewWaveformView(boundary=boundary_dto, duration=session_duration, parent=self)
        self._waveform_widget.candidate_selected.connect(self._on_waveform_candidate_selected)
        self._waveform_layout.addWidget(self._waveform_widget)

    def _on_waveform_candidate_selected(self, timestamp: float) -> None:
        self._playhead_seconds = max(0.0, timestamp)
        self._is_playing = False
        self._state.status_message = f"Waveform candidate selected at {_format_timestamp(timestamp)}"
        self._refresh_playback_panel()
        self._refresh_waveform_panel()

    def _estimated_session_duration(self) -> float:
        boundaries = self._boundaries()
        if not boundaries:
            return 60.0

        starts = [float(getattr(boundary, "start_time", 0.0)) for boundary in boundaries]
        last_start = max(starts)
        if len(starts) > 1:
            ordered = sorted(starts)
            deltas = [ordered[idx + 1] - ordered[idx] for idx in range(len(ordered) - 1) if ordered[idx + 1] > ordered[idx]]
            tail = (sum(deltas) / len(deltas)) if deltas else 30.0
        else:
            tail = 30.0

        return max(60.0, last_start + max(30.0, tail))

    def _refresh_spectrogram_panel(self) -> None:
        boundaries = self._boundaries()
        if not boundaries:
            self._spectrogram_label.setText("Spectral summary unavailable until analysis completes.")
            return

        lines: list[str] = []
        for idx, boundary in enumerate(boundaries[:8]):
            start = float(getattr(boundary, "start_time", 0.0))
            end = self._boundary_end_seconds(idx)
            duration = (end - start) if end is not None else 30.0
            bars = "#" * max(1, min(20, int(duration // 10) + 1))
            lines.append(f"T{idx + 1:02d} {bars}")

        self._spectrogram_label.setText(
            "Pseudo spectral energy (track duration proxy):\n" + "\n".join(lines)
        )

    def _refresh_analysis_panel(self) -> None:
        boundaries = self._boundaries()
        if not boundaries:
            self._analysis_label.setText("No analysis insights yet.")
            return

        durations: list[float] = []
        confidences: list[float] = []
        for idx, boundary in enumerate(boundaries):
            start = float(getattr(boundary, "start_time", 0.0))
            end = self._boundary_end_seconds(idx)
            if end is not None and end > start:
                durations.append(end - start)
            confidence = getattr(boundary, "detector_confidence", None)
            if confidence is not None:
                confidences.append(float(confidence))

        avg_duration = sum(durations) / len(durations) if durations else 0.0
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        self._analysis_label.setText(
            f"Tracks detected: {len(boundaries)}\n"
            f"Average duration: {_format_duration(avg_duration)}\n"
            f"Average confidence: {avg_confidence * 100:.0f}%\n"
            f"Review status: {self._state.review_state}\n"
            f"Export folder: {self._last_output_directory or '--'}"
        )

    def _refresh_playback_panel(self) -> None:
        boundaries = self._boundaries()
        if not boundaries:
            self._seek_slider.setValue(0)
            self._playback_label.setText("Position: 00:00.00")
            return

        max_time = float(getattr(boundaries[-1], "start_time", 0.0)) + 30.0
        slider_value = int((self._playhead_seconds / max(1.0, max_time)) * 1000)
        self._seek_slider.blockSignals(True)
        self._seek_slider.setValue(max(0, min(1000, slider_value)))
        self._seek_slider.blockSignals(False)
        self._playback_label.setText(f"Position: {_format_timestamp(self._playhead_seconds)}")

    def _boundaries(self) -> tuple[object, ...]:
        if self._review_session is None:
            return ()
        return tuple(getattr(self._review_session, "boundaries", ()) or ())

    def _boundary_for_row(self, row: int) -> object | None:
        boundaries = self._boundaries()
        if row < 0 or row >= len(boundaries):
            return None
        return boundaries[row]

    def _boundary_end_seconds(self, row: int) -> float | None:
        boundaries = self._boundaries()
        if row + 1 < len(boundaries):
            return float(getattr(boundaries[row + 1], "start_time", 0.0))
        return None


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


class _StudioAnalyzeWorker(QObject):
    """Background worker for boundary detection and metadata lookup."""

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
            self.progress.emit(15, "Detecting boundaries...")
            review_result = self._app_context.review_controller.review(self._recording_path)

            self.progress.emit(70, "Looking up metadata...")
            metadata_match = None
            try:
                metadata = self._app_context.analyze_controller.lookup_metadata(self._recording_path)
                metadata_match = metadata.match
            except Exception:
                metadata_match = None

            self.progress.emit(100, "Analysis complete")
            self.completed.emit({
                "review_session": review_result.session,
                "metadata_match": metadata_match,
            })
        except Exception as exc:
            self.failed.emit(str(exc))


class _StudioExportWorker(QObject):
    """Background export worker for Studio workflow."""

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


class _StudioDeepIdentifyWorker(QObject):
    """Background worker for full per-track deep identification."""

    progress = Signal(int, int, str)
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

            identified: list[tuple[object, object]] = []
            with TemporaryDirectory(prefix="vinylsplit-studio-deep-") as tmp_dir:
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
                    self.progress.emit(index - 1, total, f"Identifying track {index}/{total}...")
                    try:
                        match = self._app_context.pipeline.identifier.identify(
                            source_file=self._recording_path,
                            track=track,
                        )
                    except Exception:
                        continue
                    identified.append((track, match))
                    self.progress.emit(index, total, f"Identified track {index}/{total}")

            if not identified:
                self.completed.emit({"album": None, "tracklist": []})
                return

            album, tracklist = self._app_context.pipeline.resolver.resolve(identified)
            self.completed.emit({"album": album, "tracklist": tracklist})
        except Exception as exc:
            self.failed.emit(str(exc))


def _build_track_overview(boundaries: tuple[object, ...]) -> tuple[str, ...]:
    """Build Studio track overview with real boundary details and fallback labels."""

    rows: list[str] = []
    for idx, boundary in enumerate(boundaries):
        track_number = int(getattr(boundary, "track_number", idx + 1))
        title = str(getattr(boundary, "track_title", "") or f"Track {track_number:02d}")
        start = float(getattr(boundary, "start_time", 0.0))
        end = (
            float(getattr(boundaries[idx + 1], "start_time", 0.0))
            if idx + 1 < len(boundaries)
            else None
        )
        duration = (end - start) if end is not None else None
        confidence = getattr(boundary, "detector_confidence", None)

        start_text = _format_timestamp(start)
        end_text = _format_timestamp(end) if end is not None else "End"
        duration_text = _format_duration(duration) if duration is not None else "--"
        confidence_text = f"{confidence * 100:.0f}%" if confidence is not None else "--"

        rows.append(
            f"{track_number:02d} | {title} | Start {start_text} | End {end_text} | "
            f"Duration {duration_text} | Confidence {confidence_text}"
        )

    return tuple(rows)


def _format_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return "--"

    whole = int(seconds)
    minutes = whole // 60
    rem = whole % 60
    centis = int((seconds - whole) * 100)
    return f"{minutes:02d}:{rem:02d}.{centis:02d}"


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "--"

    whole = int(seconds)
    minutes = whole // 60
    rem = whole % 60
    centis = int((seconds - whole) * 100)
    return f"{minutes:02d}:{rem:02d}.{centis:02d}"
