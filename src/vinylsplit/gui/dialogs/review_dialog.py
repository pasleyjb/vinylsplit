from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from vinylsplit.application.dto.review import ReviewBoundaryDTO, ReviewSessionDTO
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
        if session_dto is not None:
            self._boundaries = tuple(session_dto.boundaries)
        else:
            self._boundaries = tuple(boundaries or ())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("Boundary Review")
        title.setObjectName("SectionTitle")

        intro = QLabel(
            "Review detected boundaries before splitting. "
            "Select a track to inspect timing and confidence details."
        )
        intro.setObjectName("StatusBarText")
        intro.setWordWrap(True)

        top_split = QSplitter(Qt.Orientation.Horizontal)

        left_panel = self._build_tracks_panel()
        right_panel = self._build_inspector_panel()

        top_split.addWidget(left_panel)
        top_split.addWidget(right_panel)
        top_split.setStretchFactor(0, 3)
        top_split.setStretchFactor(1, 2)
        top_split.setSizes([760, 430])

        bottom_panel = self._build_waveform_panel()
        toolbar = self._build_toolbar()

        root.addWidget(title)
        root.addWidget(intro)
        root.addWidget(top_split, stretch=4)
        root.addWidget(bottom_panel, stretch=2)
        root.addLayout(toolbar)

        self._populate_tracks_table()
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

        header = QLabel("Detected Tracks")
        header.setObjectName("SectionTitle")

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
        self._tracks_table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(header)
        layout.addWidget(self._tracks_table, stretch=1)
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
        layout.addStretch(1)
        return panel

    def _build_waveform_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("ReviewWaveformPlaceholder")

        self._waveform_layout = QVBoxLayout(panel)
        self._waveform_layout.setContentsMargins(8, 8, 8, 8)
        self._waveform_layout.setSpacing(0)

        self._show_waveform_placeholder("Select a track to view candidate waveform markers.")
        return panel

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

    def _populate_tracks_table(self) -> None:
        boundaries = list(self._boundaries)
        self._tracks_table.setRowCount(len(boundaries))

        for row, boundary in enumerate(boundaries):
            start = self._boundary_start_seconds(boundary)
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
            return self._boundary_start_seconds(self._boundaries[row + 1])
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
            return

        row = selected_rows[0].row()
        boundary = self._boundaries[row]

        track_number = self._boundary_track_number(boundary, row)
        start = self._boundary_start_seconds(boundary)
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
        self._update_waveform_view(boundary, row)

    def _reset_selection(self) -> None:
        if self._tracks_table.rowCount() > 0:
            self._tracks_table.selectRow(0)

    def _update_waveform_view(self, boundary: object, row: int) -> None:
        if not isinstance(boundary, ReviewBoundaryDTO):
            self._show_waveform_placeholder("Waveform preview available after backend DTO review mapping.")
            return

        duration = self._estimate_session_duration()
        waveform = ReviewWaveformView(boundary=boundary, duration=duration, parent=self)
        waveform.candidate_selected.connect(self._on_waveform_candidate_selected)
        self._clear_layout(self._waveform_layout)
        self._waveform_layout.addWidget(waveform)

    def _on_waveform_candidate_selected(self, timestamp: float) -> None:
        current_notes = self._notes_card.findChild(QLabel, "InspectorValue")
        if current_notes is not None:
            existing = current_notes.text().strip()
            prefix = f"Selected waveform candidate: {timestamp:.2f}s"
            current_notes.setText(f"{prefix}; {existing}" if existing and existing != "--" else prefix)

    def _estimate_session_duration(self) -> float:
        if not self._boundaries:
            return 60.0

        starts = [self._boundary_start_seconds(boundary) for boundary in self._boundaries]
        last_start = max(starts)
        if len(starts) > 1:
            ordered = sorted(starts)
            gaps = [ordered[i + 1] - ordered[i] for i in range(len(ordered) - 1) if ordered[i + 1] > ordered[i]]
            avg_gap = (sum(gaps) / len(gaps)) if gaps else 30.0
        else:
            avg_gap = 30.0

        return max(last_start + max(30.0, avg_gap), 60.0)

    @staticmethod
    def _boundary_track_number(boundary: object, row: int) -> int:
        return int(getattr(boundary, "track_number", row + 1))

    @staticmethod
    def _boundary_start_seconds(boundary: object) -> float:
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
