from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from vinylsplit.application.dto.review import ReviewBoundaryDTO, ReviewConfidenceDTO, ReviewSessionDTO
from vinylsplit.boundary_states import BoundaryState
from vinylsplit.models import Boundary
from vinylsplit.review_state import AdaptiveReviewState
from vinylsplit.adaptive_analysis import LocalAnalyzer, build_local_analyzer
from vinylsplit.gui.widgets.review_waveform import ReviewWaveformView


class ReviewDialog(QDialog):
    """Boundary review dialog backed by the Application Layer.

    Accepts a ReviewSessionDTO (Step 5 path) and retains legacy boundaries
    compatibility to avoid breaking existing callers.
    """

    def __init__(
        self,
        session_dto: ReviewSessionDTO | None = None,
        boundaries: tuple[object, ...] | None = None,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Boundary Review")
        self.setModal(True)
        self.resize(1240, 780)

        self._session_dto = session_dto
        if boundaries is not None:
            self._boundaries = list(boundaries)
        elif session_dto is not None:
            self._boundaries = list(session_dto.boundaries)
        else:
            self._boundaries = list(boundaries or ())
        self._editable_starts = [self._boundary_start_seconds_raw(boundary) for boundary in self._boundaries]
        self._current_waveform: ReviewWaveformView | None = None
        self._audio_output: QAudioOutput | None = None
        self._player: QMediaPlayer | None = None
        self._playback_source: str | None = self._resolve_playback_source()
        self._waveform_envelope, self._source_duration_seconds = _load_waveform_envelope(self._playback_source)
        self._last_player_seconds: float = 0.0
        self._programmatic_seek = False
        self._last_auto_snap_boundary: int | None = None
        self._boundary_pre_roll_seconds = 2.0
        self._boundary_post_roll_seconds = 5.0
        self._loop_window_seconds = 4.0
        self._loop_center_seconds: float | None = None
        self._boundary_play_end: float | None = None
        self._local_analyzer: LocalAnalyzer | None = None
        self._refine_thread: QThread | None = None
        self._refine_worker: _BoundaryRefineWorker | None = None
        self._undo_stack: list[dict[str, object]] = []
        self._redo_stack: list[dict[str, object]] = []
        self._shortcuts: list[QShortcut] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(8)

        top_split = QSplitter(Qt.Orientation.Horizontal)

        tracks_panel = self._build_tracks_panel()
        inspector_panel = self._build_inspector_panel()

        top_split.addWidget(tracks_panel)
        top_split.addWidget(inspector_panel)
        top_split.setStretchFactor(0, 3)
        top_split.setStretchFactor(1, 2)
        top_split.setSizes([760, 430])

        self._waveform_box = self._build_waveform_box()

        self._main_split = QSplitter(Qt.Orientation.Vertical)
        self._main_split.addWidget(top_split)
        self._main_split.addWidget(self._waveform_box)
        self._main_split.setStretchFactor(0, 3)
        self._main_split.setStretchFactor(1, 4)
        self._main_split.setSizes([320, 380])

        root.addWidget(self._main_split, stretch=1)

        self._populate_tracks_table()
        self._init_playback_engine()
        self._init_shortcuts()
        self._tracks_table.itemSelectionChanged.connect(self._on_selection_changed)
        if self._tracks_table.rowCount() > 0:
            self._tracks_table.selectRow(0)
        self._on_selection_changed()

    def _build_tracks_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self._tracks_table = QTableWidget()
        self._tracks_table.setObjectName("ReviewTracksTable")
        self._tracks_table.setColumnCount(6)
        self._tracks_table.setHorizontalHeaderLabels(
            ["Track", "Title", "Start", "End", "Length", "Confidence"]
        )
        self._tracks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tracks_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._tracks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tracks_table.setAlternatingRowColors(True)
        self._tracks_table.verticalHeader().setVisible(False)
        self._tracks_table.verticalHeader().setDefaultSectionSize(38)
        self._tracks_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table_header = self._tracks_table.horizontalHeader()
        table_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table_header.setStretchLastSection(False)
        self._tracks_table.setColumnWidth(0, 72)
        self._tracks_table.setColumnWidth(1, 280)
        self._tracks_table.setColumnWidth(2, 110)
        self._tracks_table.setColumnWidth(3, 110)
        self._tracks_table.setColumnWidth(4, 110)
        self._tracks_table.setColumnWidth(5, 120)

        self._tracks_artwork_label = QLabel("No artwork")
        self._tracks_artwork_label.setObjectName("ArtworkPlaceholder")
        self._tracks_artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tracks_artwork_label.setMinimumSize(200, 200)

        tracks_artwork_wrap = QFrame()
        tracks_artwork_wrap.setObjectName("Card")
        tracks_artwork_layout = QVBoxLayout(tracks_artwork_wrap)
        tracks_artwork_layout.setContentsMargins(10, 10, 10, 10)
        tracks_artwork_layout.setSpacing(0)
        tracks_artwork_layout.addStretch(1)
        tracks_artwork_layout.addWidget(self._tracks_artwork_label, alignment=Qt.AlignmentFlag.AlignCenter)
        tracks_artwork_layout.addStretch(1)

        content_row = QHBoxLayout()
        content_row.setSpacing(10)
        content_row.addWidget(self._tracks_table, stretch=4)
        content_row.addWidget(tracks_artwork_wrap, stretch=2)

        layout.addLayout(content_row, stretch=1)
        return panel

    def _build_inspector_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QLabel("Selection Inspector")
        header.setObjectName("SectionTitle")

        self._selection_label = QLabel("Current selection: none")
        self._selection_label.setObjectName("StatusBarText")

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self._track_card = _info_card("Track Number")
        self._start_card = _info_card("Start Time")
        self._end_card = _info_card("End Time")
        self._length_card = _info_card("Track Length")
        self._confidence_card = _info_card("Confidence")
        self._method_card = _info_card("Detection Method")
        self._status_card = _info_card("Boundary Status")
        self._notes_card = _info_card("Notes")

        cards = [
            self._track_card,
            self._start_card,
            self._end_card,
            self._length_card,
            self._confidence_card,
            self._method_card,
            self._status_card,
            self._notes_card,
        ]
        for idx, card in enumerate(cards):
            row = idx // 2
            col = idx % 2
            grid.addWidget(card, row, col)

        layout.addWidget(header)
        layout.addWidget(self._selection_label)
        layout.addLayout(grid)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)
        edit_label = QLabel("Edit Boundary Time")
        edit_label.setObjectName("StatusBarText")
        self._boundary_time_input = QLineEdit()
        self._boundary_time_input.setPlaceholderText("mm:ss.cc or seconds")
        self._boundary_time_input.editingFinished.connect(self._on_boundary_time_edited)
        edit_row.addWidget(edit_label)
        edit_row.addWidget(self._boundary_time_input, stretch=1)

        layout.addLayout(edit_row)
        self._auto_snap_checkbox = QCheckBox("Auto-snap playback to crossed boundaries")
        self._auto_snap_checkbox.setChecked(False)
        layout.addWidget(self._auto_snap_checkbox)
        layout.addStretch(1)
        return panel

    def set_album_artwork(self, pixmap: QPixmap | None) -> None:
        target = getattr(self, "_tracks_artwork_label", None)
        if not isinstance(target, QLabel):
            return

        if pixmap is None or pixmap.isNull():
            target.clear()
            target.setText("No artwork")
            return

        target.setPixmap(
            pixmap.scaled(
                180,
                180,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        target.setText("")

    def _build_waveform_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("Card")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(10, 10, 10, 10)
        box_layout.setSpacing(8)

        self._waveform_panel = QFrame()
        self._waveform_panel.setObjectName("ReviewWaveformPlaceholder")
        self._waveform_layout = QVBoxLayout(self._waveform_panel)
        self._waveform_layout.setContentsMargins(8, 8, 8, 8)
        self._waveform_layout.setSpacing(0)
        self._waveform_panel.setMinimumHeight(420)

        self._show_waveform_placeholder("Select a track to view candidate waveform markers.")
        box_layout.addWidget(self._waveform_panel, stretch=1)
        box_layout.addLayout(self._build_toolbar())
        return box

    def _show_waveform_placeholder(self, subtitle_text: str) -> None:
        self._clear_layout(self._waveform_layout)

        panel = QFrame()
        panel.setObjectName("Card")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(10)

        title = QLabel("Waveform View")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("StatusBarText")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        capabilities = QLabel(
            "Backend-driven display\n"
            "- Candidate boundary markers\n"
            "- Confidence-based coloring\n"
            "- Click to select nearest candidate"
        )
        capabilities.setAlignment(Qt.AlignmentFlag.AlignCenter)
        capabilities.setObjectName("StatusBarText")

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(capabilities)
        layout.addStretch(1)
        self._waveform_layout.addWidget(panel)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _build_toolbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)

        self._play_button = QToolButton()
        self._play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self._play_button.setToolTip("Play")
        self._play_button.setAutoRaise(False)
        self._play_button.clicked.connect(self._on_play)

        self._pause_button = QToolButton()
        self._pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self._pause_button.setToolTip("Pause")
        self._pause_button.setAutoRaise(False)
        self._pause_button.clicked.connect(self._on_pause)

        self._stop_button = QToolButton()
        self._stop_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self._stop_button.setToolTip("Stop")
        self._stop_button.setAutoRaise(False)
        self._stop_button.clicked.connect(self._on_stop)

        self._play_boundary_button = QToolButton()
        self._play_boundary_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self._play_boundary_button.setToolTip("Play from boundary")
        self._play_boundary_button.setAutoRaise(False)
        self._play_boundary_button.clicked.connect(self._play_from_selected_boundary)

        self._next_boundary_button = QToolButton()
        self._next_boundary_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward))
        self._next_boundary_button.setToolTip("Skip to next boundary")
        self._next_boundary_button.setAutoRaise(False)
        self._next_boundary_button.clicked.connect(self._skip_to_next_boundary)

        self._loop_button = QToolButton()
        self._loop_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self._loop_button.setToolTip("Loop playback")
        self._loop_button.setAutoRaise(False)
        self._loop_button.setCheckable(True)
        self._loop_button.toggled.connect(self._on_loop_toggled)

        self._loop_indicator = QLabel()
        self._loop_indicator.setFixedSize(12, 12)
        self._loop_indicator.setToolTip("Loop status")
        self._set_loop_indicator(False)

        self._exporting_indicator = QLabel()
        self._exporting_indicator.setFixedSize(12, 12)
        self._exporting_indicator.setToolTip("Export status")
        self._set_exporting_indicator(False)

        self._exporting_label = QLabel("Exporting")
        self._exporting_label.setObjectName("StatusBarText")

        self._playback_position_label = QLabel("Position: 00:00.00")
        self._playback_position_label.setObjectName("StatusBarText")

        layout.addWidget(self._play_button)
        layout.addWidget(self._pause_button)
        layout.addWidget(self._stop_button)
        layout.addWidget(self._play_boundary_button)
        layout.addWidget(self._next_boundary_button)
        layout.addWidget(self._loop_button)
        layout.addWidget(self._loop_indicator)
        layout.addSpacing(6)
        layout.addWidget(self._exporting_indicator)
        layout.addWidget(self._exporting_label)
        layout.addWidget(self._playback_position_label)
        layout.addStretch(1)

        cancel_button = QPushButton("Cancel")
        cancel_button.setMinimumHeight(38)
        cancel_button.clicked.connect(self.reject)

        reset_button = QPushButton("Reset Selection")
        reset_button.setObjectName("SecondaryButton")
        reset_button.setMinimumHeight(38)
        reset_button.clicked.connect(self._reset_selection)

        accept_button = QPushButton("Accept Changes")
        accept_button.setObjectName("PrimaryButton")
        accept_button.setMinimumHeight(42)
        accept_button.clicked.connect(self.accept)

        layout.addWidget(cancel_button)
        layout.addWidget(reset_button)
        layout.addWidget(accept_button)
        return layout

    def _set_loop_indicator(self, enabled: bool) -> None:
        color = "#22c55e" if enabled else "#14532d"
        self._loop_indicator.setStyleSheet(
            f"border-radius: 6px; background-color: {color}; border: 1px solid #0b2f1a;"
        )

    def _set_exporting_indicator(self, exporting: bool) -> None:
        color = "#ef4444" if exporting else "#3f1d1d"
        self._exporting_indicator.setStyleSheet(
            f"border-radius: 6px; background-color: {color}; border: 1px solid #3f1d1d;"
        )

    def set_exporting_active(self, exporting: bool) -> None:
        self._set_exporting_indicator(exporting)

    def _populate_tracks_table(self) -> None:
        boundaries = list(self._boundaries)
        self._tracks_table.setRowCount(len(boundaries))

        for row, boundary in enumerate(boundaries):
            start = self._start_for_row(row)
            end = self._track_end_seconds(row)
            length = max(0.0, end - start) if end is not None else None
            confidence_text = self._boundary_confidence_text(boundary)
            track_number = self._boundary_track_number(boundary, row)
            title = self._boundary_title(boundary)

            self._tracks_table.setItem(row, 0, QTableWidgetItem(str(track_number)))
            self._tracks_table.setItem(row, 1, QTableWidgetItem(title))
            self._tracks_table.setItem(row, 2, QTableWidgetItem(_format_timestamp(start)))
            self._tracks_table.setItem(row, 3, QTableWidgetItem(_format_timestamp(end) if end is not None else "--"))
            self._tracks_table.setItem(row, 4, QTableWidgetItem(_format_duration(length) if length is not None else "--"))
            self._tracks_table.setItem(row, 5, QTableWidgetItem(confidence_text))

    def _track_end_seconds(self, row: int) -> float | None:
        if row + 1 < len(self._boundaries):
            return self._start_for_row(row + 1)
        return None

    def _on_selection_changed(self) -> None:
        selected_rows = self._tracks_table.selectionModel().selectedRows()
        if not selected_rows:
            self._selection_label.setText("Current selection: none")
            _set_info_card(self._track_card, "--")
            _set_info_card(self._start_card, "--")
            _set_info_card(self._end_card, "--")
            _set_info_card(self._length_card, "--")
            _set_info_card(self._confidence_card, "--")
            _set_info_card(self._method_card, "--")
            _set_info_card(self._status_card, "--")
            _set_info_card(self._notes_card, "No selection")
            self._boundary_time_input.setText("")
            return

        row = selected_rows[0].row()
        boundary = self._boundaries[row]

        track_number = self._boundary_track_number(boundary, row)
        start = self._start_for_row(row)
        end = self._track_end_seconds(row)
        length = max(0.0, end - start) if end is not None else None
        confidence_text = self._boundary_confidence_text(boundary)
        confidence_detail = self._boundary_confidence_detail(boundary)
        method = self._boundary_method(boundary)
        status = self._boundary_status(boundary)
        notes = self._boundary_notes(boundary)
        title = self._boundary_title(boundary)

        if title != "--":
            self._selection_label.setText(f"Current selection: Track {track_number} - {title}")
        else:
            self._selection_label.setText(f"Current selection: Track {track_number}")

        _set_info_card(self._track_card, str(track_number))
        _set_info_card(self._start_card, _format_timestamp(start))
        _set_info_card(self._end_card, _format_timestamp(end) if end is not None else "End of recording")
        _set_info_card(self._length_card, _format_duration(length) if length is not None else "--")
        _set_info_card(self._confidence_card, confidence_detail or confidence_text)
        _set_info_card(self._method_card, method)
        _set_info_card(self._status_card, status)
        _set_info_card(self._notes_card, notes)
        self._boundary_time_input.setText(_format_timestamp(start))
        self._update_waveform_view(boundary, row)

    def _reset_selection(self) -> None:
        if self._tracks_table.rowCount() > 0:
            self._tracks_table.selectRow(0)

    def _update_waveform_view(self, boundary: object, row: int) -> None:
        duration = self._estimate_session_duration()
        editable_boundary = self._to_waveform_boundary(boundary, row)
        waveform = ReviewWaveformView(
            boundary=editable_boundary,
            duration=duration,
            boundary_times=list(self._editable_starts),
            waveform_envelope=self._waveform_envelope,
            selected_index=row,
            parent=self,
        )
        waveform.candidate_selected.connect(self._on_waveform_candidate_selected)
        waveform.boundary_dragged.connect(self._on_waveform_boundary_dragged)
        waveform.boundary_tab_selected.connect(self._on_waveform_boundary_tab_selected)
        waveform.boundary_tab_dragged.connect(self._on_waveform_boundary_tab_dragged)
        waveform.seek_requested.connect(self._on_waveform_seek_requested)
        waveform.add_boundary_requested.connect(self._on_waveform_add_boundary_requested)
        waveform.delete_boundary_requested.connect(self._on_waveform_delete_boundary_requested)
        waveform.anchor_and_refine_requested.connect(self._on_waveform_anchor_and_refine_requested)
        waveform.undo_requested.connect(self._undo_last_edit)
        waveform.redo_requested.connect(self._redo_last_edit)
        self._clear_layout(self._waveform_layout)
        self._waveform_layout.addWidget(waveform)
        self._current_waveform = waveform
        self._sync_waveform_playhead()

    def _to_waveform_boundary(self, boundary: object, row: int) -> ReviewBoundaryDTO:
        if isinstance(boundary, ReviewBoundaryDTO):
            return replace(boundary, selected_timestamp=self._start_for_row(row))

        detector_confidence = float(getattr(boundary, "detector_confidence", 0.0) or 0.0)
        confidence = ReviewConfidenceDTO(
            silence_quality=detector_confidence,
            metadata_agreement=0.0,
            overall=detector_confidence,
        )
        return ReviewBoundaryDTO(
            track_number=self._boundary_track_number(boundary, row),
            selected_timestamp=self._start_for_row(row),
            title=self._boundary_title(boundary),
            confidence=confidence,
            notes=list(getattr(boundary, "reasons", None) or []),
        )

    def _on_waveform_candidate_selected(self, timestamp: float) -> None:
        row = self._current_selected_row()
        if row is None:
            return
        self._set_boundary_start(row, timestamp)

    def _on_waveform_boundary_dragged(self, timestamp: float) -> None:
        row = self._current_selected_row()
        if row is None:
            return
        self._set_boundary_start(row, timestamp)

    def _on_waveform_boundary_tab_selected(self, row: int) -> None:
        if 0 <= row < self._tracks_table.rowCount():
            self._tracks_table.selectRow(row)

    def _on_waveform_boundary_tab_dragged(self, row: int, timestamp: float) -> None:
        self._set_boundary_start(row, timestamp)

    def _on_waveform_seek_requested(self, timestamp: float) -> None:
        if self._loop_button.isChecked():
            self._loop_center_seconds = max(0.0, timestamp)
        self._seek_playback(timestamp)

    def _on_waveform_add_boundary_requested(self, timestamp: float) -> None:
        if not self._boundaries or any(isinstance(boundary, ReviewBoundaryDTO) for boundary in self._boundaries):
            self._selection_label.setText("Current selection: add boundary unavailable for DTO-backed review")
            return

        self._push_undo_snapshot()
        self._redo_stack.clear()

        insert_row = 0
        while insert_row < len(self._editable_starts) and self._editable_starts[insert_row] < timestamp:
            insert_row += 1

        minimum_gap = self._minimum_boundary_gap_seconds()
        lower = 0.0 if insert_row == 0 else self._editable_starts[insert_row - 1] + minimum_gap
        upper = None if insert_row >= len(self._editable_starts) else self._editable_starts[insert_row] - minimum_gap
        clamped = max(lower, timestamp)
        if upper is not None:
            clamped = min(clamped, upper)

        if upper is not None and clamped >= upper:
            self._selection_label.setText("Current selection: cannot add boundary at this position")
            self._undo_stack.pop()
            return

        new_boundary = Boundary(
            track_number=insert_row + 1,
            start_time=clamped,
            reasons=["Manually inserted in review waveform"],
            state=BoundaryState.LOCKED,
        )
        self._boundaries.insert(insert_row, new_boundary)
        self._editable_starts.insert(insert_row, clamped)
        self._renumber_tracks()
        self._refresh_after_boundary_edit(insert_row)

    def _on_waveform_delete_boundary_requested(self, row: int) -> None:
        if row <= 0 or row >= len(self._editable_starts):
            self._selection_label.setText("Current selection: start boundary cannot be deleted")
            return
        if any(isinstance(boundary, ReviewBoundaryDTO) for boundary in self._boundaries):
            self._selection_label.setText("Current selection: delete boundary unavailable for DTO-backed review")
            return

        self._push_undo_snapshot()
        self._redo_stack.clear()
        self._editable_starts.pop(row)
        self._boundaries.pop(row)
        self._renumber_tracks()
        self._refresh_after_boundary_edit(min(row, len(self._editable_starts) - 1))

    def _on_waveform_anchor_and_refine_requested(self, row: int) -> None:
        if row < 0 or row >= len(self._boundaries):
            return
        if isinstance(self._boundaries[row], ReviewBoundaryDTO):
            self._selection_label.setText("Current selection: anchor/refine unavailable for DTO-backed review")
            return
        if self._refine_thread is not None:
            self._selection_label.setText("Current selection: refinement already running")
            return

        self._push_undo_snapshot()
        self._redo_stack.clear()
        self._set_refine_busy(True)

        self._refine_thread = QThread(self)
        self._refine_worker = _BoundaryRefineWorker(
            source_file=self._playback_source or "",
            boundaries=copy.deepcopy(self._boundaries),
            anchor_row=row,
            duration_seconds=self._estimate_session_duration(),
        )
        self._refine_worker.moveToThread(self._refine_thread)
        self._refine_thread.started.connect(self._refine_worker.run)
        self._refine_worker.completed.connect(self._on_boundary_refine_complete)
        self._refine_worker.failed.connect(self._on_boundary_refine_failed)
        self._refine_worker.completed.connect(self._refine_thread.quit)
        self._refine_worker.failed.connect(self._refine_thread.quit)
        self._refine_thread.finished.connect(self._cleanup_refine_worker)
        self._refine_thread.start()

    def _snapshot_state(self) -> dict[str, object]:
        return {
            "boundaries": copy.deepcopy(self._boundaries),
            "editable_starts": list(self._editable_starts),
            "selected_row": self._current_selected_row(),
        }

    def _restore_snapshot(self, snapshot: dict[str, object]) -> None:
        self._boundaries = copy.deepcopy(snapshot["boundaries"])
        self._editable_starts = list(snapshot["editable_starts"])
        self._populate_tracks_table()
        selected_row = snapshot.get("selected_row")
        if isinstance(selected_row, int) and 0 <= selected_row < self._tracks_table.rowCount():
            self._tracks_table.selectRow(selected_row)
        elif self._tracks_table.rowCount() > 0:
            self._tracks_table.selectRow(0)
        self._on_selection_changed()

    def _push_undo_snapshot(self) -> None:
        self._undo_stack.append(self._snapshot_state())

    def _undo_last_edit(self) -> None:
        if not self._undo_stack:
            self._selection_label.setText("Current selection: nothing to undo")
            return
        self._redo_stack.append(self._snapshot_state())
        snapshot = self._undo_stack.pop()
        self._restore_snapshot(snapshot)

    def _redo_last_edit(self) -> None:
        if not self._redo_stack:
            self._selection_label.setText("Current selection: nothing to redo")
            return
        self._undo_stack.append(self._snapshot_state())
        snapshot = self._redo_stack.pop()
        self._restore_snapshot(snapshot)

    def undo_last_edit(self) -> None:
        """Public hook for external undo action bindings."""
        self._undo_last_edit()

    def redo_last_edit(self) -> None:
        """Public hook for external redo action bindings."""
        self._redo_last_edit()

    def _set_boundary_locked(self, row: int) -> None:
        boundary = self._boundaries[row]
        if hasattr(boundary, "state"):
            setattr(boundary, "state", BoundaryState.LOCKED)

    def _renumber_tracks(self) -> None:
        for index, boundary in enumerate(self._boundaries, start=1):
            if hasattr(boundary, "track_number"):
                setattr(boundary, "track_number", index)

    def _set_refine_busy(self, busy: bool) -> None:
        self._tracks_table.setEnabled(not busy)
        self._boundary_time_input.setEnabled(not busy)
        for button in (
            self._play_button,
            self._pause_button,
            self._stop_button,
            self._play_boundary_button,
            self._next_boundary_button,
            self._loop_button,
        ):
            button.setEnabled(not busy)
        self._selection_label.setText("Current selection: refining boundary anchors..." if busy else self._selection_label.text())

    @Slot(object)
    def _on_boundary_refine_complete(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        boundaries = data.get("boundaries")
        improved = int(data.get("improved", 0) or 0)
        anchor_timestamp = float(data.get("anchor_timestamp", -1.0) or -1.0)

        if isinstance(boundaries, list):
            self._boundaries = boundaries
            self._editable_starts = [float(boundary.start_time) for boundary in self._boundaries]
            self._renumber_tracks()
            self._populate_tracks_table()
            selected_row = 0
            if anchor_timestamp >= 0.0:
                selected_row = min(
                    range(len(self._boundaries)),
                    key=lambda idx: abs(self._start_for_row(idx) - anchor_timestamp),
                )
            if 0 <= selected_row < self._tracks_table.rowCount():
                self._tracks_table.selectRow(selected_row)
            self._on_selection_changed()
            self._selection_label.setText(f"Current selection: anchor applied, refined {improved} boundaries")

        self._set_refine_busy(False)

    @Slot(str)
    def _on_boundary_refine_failed(self, message: str) -> None:
        self._set_refine_busy(False)
        self._selection_label.setText(f"Current selection: refinement failed - {message}")

    @Slot()
    def _cleanup_refine_worker(self) -> None:
        if self._refine_worker is not None:
            self._refine_worker.deleteLater()
        self._refine_worker = None
        self._refine_thread = None

    def _estimate_session_duration(self) -> float:
        if self._source_duration_seconds is not None and self._source_duration_seconds > 1.0:
            return self._source_duration_seconds

        if not self._boundaries:
            return 60.0

        starts = list(self._editable_starts)
        last_start = max(starts)
        if len(starts) > 1:
            ordered = sorted(starts)
            gaps = [ordered[i + 1] - ordered[i] for i in range(len(ordered) - 1) if ordered[i + 1] > ordered[i]]
            avg_gap = (sum(gaps) / len(gaps)) if gaps else 30.0
        else:
            avg_gap = 30.0

        return max(last_start + max(30.0, avg_gap), 60.0)

    def _on_boundary_time_edited(self) -> None:
        row = self._current_selected_row()
        if row is None:
            return

        parsed = _parse_timestamp_text(self._boundary_time_input.text())
        if parsed is None:
            self._boundary_time_input.setText(_format_timestamp(self._start_for_row(row)))
            return

        self._set_boundary_start(row, parsed)

    def _set_boundary_start(self, row: int, value: float, record_undo: bool = True) -> None:
        if row < 0 or row >= len(self._editable_starts):
            return

        previous = self._start_for_row(row - 1) if row > 0 else 0.0
        next_start = self._start_for_row(row + 1) if row + 1 < len(self._editable_starts) else None

        minimum_gap = self._minimum_boundary_gap_seconds()
        lower_bound = max(0.0, previous + minimum_gap) if row > 0 else 0.0
        upper_bound = (next_start - minimum_gap) if next_start is not None else None

        clamped = max(lower_bound, value)
        if upper_bound is not None:
            clamped = min(clamped, upper_bound)

        if abs(clamped - self._editable_starts[row]) < 1e-6:
            return

        if record_undo:
            self._push_undo_snapshot()
            self._redo_stack.clear()

        self._editable_starts[row] = clamped
        self._apply_boundary_to_model(row, clamped)
        self._refresh_after_boundary_edit(row)

    def _resolve_playback_source(self) -> str | None:
        if self._session_dto is not None:
            source = getattr(self._session_dto, "source_file", None)
            if source:
                return str(source)

        for boundary in self._boundaries:
            source = getattr(boundary, "source_file", None)
            if source:
                return str(source)

        return None

    def _init_playback_engine(self) -> None:
        source = self._playback_source
        if not source or not Path(source).exists():
            self._playback_position_label.setText("Playback unavailable (source audio not found)")
            self._set_playback_buttons_enabled(False)
            return

        self._audio_output = QAudioOutput(self)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.positionChanged.connect(self._on_player_position_changed)
        self._player.setSource(QUrl.fromLocalFile(source))
        self._set_playback_buttons_enabled(True)

    def _init_shortcuts(self) -> None:
        self._shortcuts = []
        specs = [
            ("Space", self._toggle_play_pause),
            ("Left", lambda: self._nudge_selected_boundary(-0.05)),
            ("Right", lambda: self._nudge_selected_boundary(0.05)),
            ("Shift+Left", lambda: self._nudge_selected_boundary(-0.2)),
            ("Shift+Right", lambda: self._nudge_selected_boundary(0.2)),
            ("Ctrl+Z", self._undo_last_edit),
            ("Ctrl+Y", self._redo_last_edit),
        ]
        for key, handler in specs:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(handler)
            self._shortcuts.append(shortcut)

    def _set_playback_buttons_enabled(self, enabled: bool) -> None:
        self._play_button.setEnabled(enabled)
        self._pause_button.setEnabled(enabled)
        self._stop_button.setEnabled(enabled)
        self._play_boundary_button.setEnabled(enabled)
        self._next_boundary_button.setEnabled(enabled)

    def _on_play(self) -> None:
        if self._player is not None:
            self._boundary_play_end = None
            if self._loop_button.isChecked():
                self._loop_center_seconds = self._current_playhead_seconds()
                loop_start, _ = self._current_loop_window()
                self._seek_playback(loop_start)
            self._player.play()

    def _on_pause(self) -> None:
        if self._player is not None:
            self._player.pause()

    def _toggle_play_pause(self) -> None:
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._on_pause()
        else:
            self._on_play()

    def _on_stop(self) -> None:
        if self._player is None:
            return
        self._boundary_play_end = None
        self._player.stop()
        self._on_player_position_changed(0)

    def _play_from_selected_boundary(self) -> None:
        row = self._current_selected_row()
        if row is None:
            return
        segment_start, segment_end = self._selected_boundary_window()
        self._boundary_play_end = segment_end
        self._seek_playback(segment_start)
        if self._player is not None:
            self._player.play()

    def _skip_to_next_boundary(self) -> None:
        was_playing = (
            self._player is not None
            and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        current_seconds = self._current_playhead_seconds()
        for index, boundary_time in enumerate(self._editable_starts):
            if boundary_time > (current_seconds + 0.01):
                self._seek_playback(boundary_time)
                if 0 <= index < self._tracks_table.rowCount():
                    self._tracks_table.selectRow(index)
                if was_playing and self._player is not None:
                    self._player.play()
                return
        self._selection_label.setText("Current selection: already at final boundary")

    def _seek_playback(self, seconds: float) -> None:
        if self._player is None:
            return
        self._programmatic_seek = True
        self._player.setPosition(max(0, int(seconds * 1000)))

    def _on_player_position_changed(self, position_ms: int) -> None:
        seconds = max(0.0, position_ms / 1000.0)
        self._playback_position_label.setText(f"Position: {_format_timestamp(seconds)}")
        self._sync_waveform_playhead(seconds)

        if self._programmatic_seek:
            self._programmatic_seek = False
            self._last_player_seconds = seconds
            return

        if self._auto_snap_checkbox.isChecked() and self._player is not None:
            self._apply_auto_snap(seconds)

        if self._boundary_play_end is not None and self._player is not None:
            if seconds >= self._boundary_play_end and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                if self._loop_button.isChecked():
                    if self._loop_center_seconds is None:
                        self._loop_center_seconds = seconds
                    loop_start, _ = self._current_loop_window()
                    self._seek_playback(loop_start)
                else:
                    self._player.stop()
                    self._boundary_play_end = None
        elif self._loop_button.isChecked() and self._player is not None:
            if self._loop_center_seconds is None:
                self._loop_center_seconds = seconds
            loop_start, loop_end = self._current_loop_window()
            if seconds >= loop_end and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._seek_playback(loop_start)

        self._last_player_seconds = seconds

    def _apply_auto_snap(self, seconds: float) -> None:
        if seconds <= self._last_player_seconds:
            return

        crossed_index = None
        for index, boundary_time in enumerate(self._editable_starts):
            if self._last_player_seconds < boundary_time <= seconds:
                crossed_index = index
                break

        if crossed_index is None:
            return

        if crossed_index == self._last_auto_snap_boundary:
            return

        target = self._start_for_row(crossed_index)
        self._last_auto_snap_boundary = crossed_index
        self._seek_playback(target)
        if 0 <= crossed_index < self._tracks_table.rowCount():
            self._tracks_table.selectRow(crossed_index)

    def _selected_boundary_window(self) -> tuple[float, float]:
        """Return selected track playback window (boundary -> next boundary)."""

        row = self._current_selected_row()
        if row is None:
            return 0.0, max(2.0, self._estimate_session_duration())

        start = self._start_for_row(row)
        end = self._track_end_seconds(row)
        session_end = self._estimate_session_duration()
        if end is None:
            end = session_end
        end = min(max(end, start + 0.25), session_end)
        return start, end

    def _current_playhead_seconds(self) -> float:
        if self._player is None:
            return self._last_player_seconds
        return max(0.0, self._player.position() / 1000.0)

    def _current_loop_window(self) -> tuple[float, float]:
        center = self._loop_center_seconds if self._loop_center_seconds is not None else self._current_playhead_seconds()
        half_window = self._loop_window_seconds / 2.0
        session_end = self._estimate_session_duration()
        start = max(0.0, center - half_window)
        end = min(session_end, start + self._loop_window_seconds)
        if end - start < self._loop_window_seconds:
            start = max(0.0, end - self._loop_window_seconds)
        if end <= start:
            end = min(session_end, start + 0.25)
        return start, end

    def _on_loop_toggled(self, checked: bool) -> None:
        self._set_loop_indicator(checked)
        if checked:
            self._loop_center_seconds = self._current_playhead_seconds()
            return
        self._loop_center_seconds = None

    def _nudge_selected_boundary(self, delta_seconds: float) -> None:
        row = self._current_selected_row()
        if row is None:
            return
        if isinstance(self.focusWidget(), QLineEdit):
            return
        self._set_boundary_start(row, self._start_for_row(row) + delta_seconds)

    def _sync_waveform_playhead(self, seconds: float | None = None) -> None:
        if self._current_waveform is None:
            return

        if seconds is None:
            if self._player is None:
                return
            seconds = max(0.0, self._player.position() / 1000.0)

        self._current_waveform.set_playhead(seconds)

    def _shutdown_playback(self) -> None:
        """Stop and detach media resources when dialog is dismissed."""
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())
        if self._audio_output is not None:
            self._audio_output.setVolume(0.0)

    def reject(self) -> None:
        self._shutdown_playback()
        super().reject()

    def accept(self) -> None:
        self._shutdown_playback()
        super().accept()

    def done(self, result: int) -> None:
        self._shutdown_playback()
        super().done(result)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._shutdown_playback()
        super().closeEvent(event)

    def _apply_boundary_to_model(self, row: int, start_value: float) -> None:
        boundary = self._boundaries[row]
        if isinstance(boundary, ReviewBoundaryDTO):
            return

        if hasattr(boundary, "edited_boundary"):
            setattr(boundary, "edited_boundary", start_value)
        if hasattr(boundary, "detected_boundary"):
            setattr(boundary, "detected_boundary", start_value)
        if hasattr(boundary, "start_time"):
            setattr(boundary, "start_time", start_value)
        if hasattr(boundary, "state"):
            setattr(boundary, "state", BoundaryState.LOCKED)

    def _refresh_after_boundary_edit(self, row: int) -> None:
        self._populate_tracks_table()

        if 0 <= row < self._tracks_table.rowCount():
            self._tracks_table.selectRow(row)

    def _current_selected_row(self) -> int | None:
        selected_rows = self._tracks_table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        return selected_rows[0].row()

    def _start_for_row(self, row: int) -> float:
        if 0 <= row < len(self._editable_starts):
            return float(self._editable_starts[row])
        return 0.0

    def _minimum_boundary_gap_seconds(self) -> float:
        if self._current_waveform is not None:
            return self._current_waveform.minimum_boundary_gap_seconds()
        return 0.05

    @staticmethod
    def _boundary_track_number(boundary: object, row: int) -> int:
        return int(getattr(boundary, "track_number", row + 1))

    @staticmethod
    def _boundary_start_seconds_raw(boundary: object) -> float:
        if isinstance(boundary, ReviewBoundaryDTO):
            return float(boundary.selected_timestamp)
        return float(getattr(boundary, "start_time", 0.0))

    @staticmethod
    def _boundary_title(boundary: object) -> str:
        if isinstance(boundary, ReviewBoundaryDTO):
            return boundary.title or "--"
        return str(getattr(boundary, "track_title", "--") or "--")

    @staticmethod
    def _boundary_confidence_text(boundary: object) -> str:
        if isinstance(boundary, ReviewBoundaryDTO):
            if boundary.confidence is None:
                return "--"
            return f"{boundary.confidence_pct}%"

        confidence = getattr(boundary, "detector_confidence", None)
        return f"{confidence * 100:.0f}%" if confidence is not None else "--"

    @staticmethod
    def _boundary_confidence_detail(boundary: object) -> str:
        if isinstance(boundary, ReviewBoundaryDTO) and boundary.confidence is not None:
            return f"{boundary.confidence_pct}% ({boundary.confidence.display_breakdown})"
        return ""

    @staticmethod
    def _boundary_status(boundary: object) -> str:
        if isinstance(boundary, ReviewBoundaryDTO):
            return boundary.status_indicator

        confidence = getattr(boundary, "detector_confidence", None)
        status = getattr(getattr(boundary, "state", None), "display_label", None)
        if callable(status):
            return str(status(confidence))
        return str(getattr(boundary, "state", "AUTO"))

    @staticmethod
    def _boundary_method(boundary: object) -> str:
        if isinstance(boundary, ReviewBoundaryDTO):
            if boundary.evidence is None:
                return "Silence-guided detection"
            return boundary.evidence.evidence_summary

        reasons = getattr(boundary, "reasons", None) or []
        return str(reasons[0]) if reasons else "Silence-guided detection"

    @staticmethod
    def _boundary_notes(boundary: object) -> str:
        if isinstance(boundary, ReviewBoundaryDTO):
            notes = list(boundary.notes)
            if boundary.candidates:
                top = ", ".join(candidate.display_label for candidate in boundary.candidates[:3])
                notes.append(f"Candidates: {top}")
            return "; ".join(notes) if notes else "No additional notes for this boundary."

        reasons = getattr(boundary, "reasons", None) or []
        return "; ".join(reasons) if reasons else "No additional notes for this boundary."


def _info_card(label: str) -> QFrame:
    card = QFrame()
    card.setObjectName("Card")

    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(4)

    caption = QLabel(label)
    caption.setObjectName("StatusBarText")

    value = QLabel("--")
    value.setObjectName("InspectorValue")
    value.setWordWrap(True)

    layout.addWidget(caption)
    layout.addWidget(value)
    card._value_label = value  # type: ignore[attr-defined]
    return card


def _set_info_card(card: QFrame, value: str) -> None:
    label = getattr(card, "_value_label", None)
    if isinstance(label, QLabel):
        label.setText(value)


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


class _BoundaryRefineWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, source_file: str, boundaries: list[Boundary], anchor_row: int, duration_seconds: float) -> None:
        super().__init__()
        self._source_file = source_file
        self._boundaries = boundaries
        self._anchor_row = anchor_row
        self._duration_seconds = duration_seconds

    @Slot()
    def run(self) -> None:
        try:
            if not self._source_file:
                raise ValueError("Missing source audio for refinement.")

            analyzer = build_local_analyzer(self._source_file)
            if analyzer is None:
                raise ValueError("Unable to load source audio for refinement.")

            if not (0 <= self._anchor_row < len(self._boundaries)):
                raise ValueError("Anchor boundary is out of range.")

            anchor_boundary = self._boundaries[self._anchor_row]
            anchor_timestamp = float(anchor_boundary.start_time)
            anchor_boundary.state = BoundaryState.LOCKED

            state = AdaptiveReviewState(
                source_file=self._source_file,
                boundaries=self._boundaries,
                track_titles=[],
            )

            summary = analyzer.refine_boundaries(
                state=state,
                duration_seconds=self._duration_seconds,
                minimum_spacing_seconds=0.25,
                debug=False,
            )

            state._normalize()
            self.completed.emit(
                {
                    "boundaries": copy.deepcopy(state.boundaries),
                    "improved": summary.boundaries_improved,
                    "anchor_timestamp": anchor_timestamp,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


def _parse_timestamp_text(raw: str) -> float | None:
    text = raw.strip()
    if not text:
        return None

    if ":" in text:
        try:
            minutes_str, seconds_str = text.split(":", 1)
            minutes = int(minutes_str)
            seconds = float(seconds_str)
            value = (minutes * 60.0) + seconds
            return value if value >= 0.0 else None
        except ValueError:
            return None

    try:
        value = float(text)
        return value if value >= 0.0 else None
    except ValueError:
        return None


def _load_waveform_envelope(
    source: str | None,
    sample_points: int = 1400,
) -> tuple[list[tuple[float, float]] | None, float | None]:
    """Build a compact stereo waveform envelope from the source audio file."""
    if not source:
        return None, None

    path = Path(source)
    if not path.exists():
        return None, None

    try:
        with sf.SoundFile(path) as audio_file:
            total_frames = len(audio_file)
            sample_rate = float(audio_file.samplerate or 0)
            if total_frames <= 0 or sample_rate <= 0.0:
                return None, None

            duration_seconds = total_frames / sample_rate
            block_size = max(1, int(total_frames / max(1, sample_points)))
            peaks: list[tuple[float, float]] = []

            audio_file.seek(0)
            for block in audio_file.blocks(blocksize=block_size, dtype="float32", always_2d=True):
                if block.size == 0:
                    continue
                left = block[:, 0]
                right = block[:, 1] if block.shape[1] > 1 else left
                left_peak = max(0.0, min(1.0, float(np.max(np.abs(left)))))
                right_peak = max(0.0, min(1.0, float(np.max(np.abs(right)))))
                peaks.append((left_peak, right_peak))
                if len(peaks) >= sample_points:
                    break

            if not peaks:
                return None, duration_seconds

            values = np.asarray(peaks, dtype=np.float32)
            scale = float(np.percentile(values, 95.0))
            if scale > 1e-6:
                values = np.clip(values / scale, 0.0, 1.0)

            return [tuple(map(float, pair)) for pair in values.tolist()], duration_seconds
    except Exception:
        return None, None
