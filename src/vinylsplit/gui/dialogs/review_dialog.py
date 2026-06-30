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

from vinylsplit.application.dto.review import ReviewSessionDTO, ReviewBoundaryDTO


class ReviewDialog(QDialog):
    """Boundary review workstation using backend-provided DTOs.
    
    Displays only data from the backend ReviewSessionDTO.
    No synthetic candidates, no fabricated confidence values.
    All information produced by VinylSplit analysis.
    """

    def __init__(self, session_dto: ReviewSessionDTO, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Boundary Review Workstation")
        self.setModal(True)
        self.resize(1240, 780)

        self._session_dto = session_dto
        self._boundaries = session_dto.boundaries

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("Boundary Review Workstation")
        title.setObjectName("SectionTitle")

        intro = QLabel(
            "Review detected boundaries before splitting. "
            "Select a track to inspect timing, confidence, detection evidence, and candidates."
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

        bottom_panel = self._build_waveform_placeholder()
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
            ["Track", "Start", "End", "Length", "Confidence", "Status"]
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

    def _build_waveform_placeholder(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("ReviewWaveformPlaceholder")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(10)

        title = QLabel("Waveform Editor (Future)")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Backend-Driven Waveform Display Coming Soon")
        subtitle.setObjectName("StatusBarText")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        capabilities = QLabel(
            "This waveform will display:\n"
            "• Detected candidates from backend (no synthesis)\n"
            "• Per-detector confidence visualization\n"
            "• Spectrogram overlay with boundary confidence\n"
            "• Click-to-select candidates\n"
            "• Drag-to-refine selected boundary\n"
            "• Metadata guidance overlay\n"
            "• Keyboard navigation & shortcuts\n"
            "• Undo / Redo support"
        )
        capabilities.setAlignment(Qt.AlignmentFlag.AlignCenter)
        capabilities.setObjectName("StatusBarText")

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(capabilities)
        layout.addStretch(1)
        return panel

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
        """Populate table from backend ReviewBoundaryDTO objects."""
        self._tracks_table.setRowCount(len(self._boundaries))

        for row, boundary_dto in enumerate(self._boundaries):
            start = boundary_dto.selected_timestamp
            end = self._track_end_seconds(row)
            length = max(0.0, end - start) if end is not None else None
            confidence_pct = boundary_dto.confidence_pct
            status = boundary_dto.status_indicator

            self._tracks_table.setItem(row, 0, QTableWidgetItem(str(boundary_dto.track_number)))
            self._tracks_table.setItem(row, 1, QTableWidgetItem(_format_timestamp(start)))
            self._tracks_table.setItem(row, 2, QTableWidgetItem(_format_timestamp(end) if end is not None else "--"))
            self._tracks_table.setItem(row, 3, QTableWidgetItem(_format_duration(length) if length is not None else "--"))
            self._tracks_table.setItem(row, 4, QTableWidgetItem(f"{confidence_pct}%"))
            self._tracks_table.setItem(row, 5, QTableWidgetItem(status))

    def _track_end_seconds(self, row: int) -> float | None:
        """Get end time as start of next track."""
        if row + 1 < len(self._boundaries):
            return self._boundaries[row + 1].selected_timestamp
        return None

    def _on_selection_changed(self) -> None:
        """Update inspector when boundary selection changes."""
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
        boundary_dto = self._boundaries[row]

        track_number = boundary_dto.track_number
        start = boundary_dto.selected_timestamp
        end = self._track_end_seconds(row)
        length = max(0.0, end - start) if end is not None else None

        self._selection_label.setText(f"Current selection: Track {track_number}")

        _set_info_card(self._track_card, str(track_number))
        _set_info_card(self._start_card, _format_timestamp(start))
        _set_info_card(self._end_card, _format_timestamp(end) if end is not None else "End of recording")
        _set_info_card(self._length_card, _format_duration(length) if length is not None else "--")

        # Display confidence breakdown from backend
        if boundary_dto.confidence:
            confidence_text = f"{boundary_dto.confidence.overall * 100:.0f}%"
            if boundary_dto.confidence.display_breakdown != "Unknown":
                confidence_text += f"\n({boundary_dto.confidence.display_breakdown})"
            _set_info_card(self._confidence_card, confidence_text)
        else:
            _set_info_card(self._confidence_card, "--")

        # Display detection method and evidence
        if boundary_dto.evidence:
            _set_info_card(self._method_card, boundary_dto.evidence.method)
        else:
            _set_info_card(self._method_card, "No detection evidence")

        # Display status
        status_text = boundary_dto.status_indicator
        if boundary_dto.is_verified:
            status_text += " Verified"
        elif boundary_dto.is_locked:
            status_text += " Locked"
        _set_info_card(self._status_card, status_text)

        # Display all candidate boundaries from backend
        candidates_display = ""
        if boundary_dto.candidates:
            candidates_display = "Detected candidates:\n"
            for candidate in boundary_dto.candidates[:5]:  # Show top 5
                candidates_display += f"  • {candidate.display_label}\n"
        if boundary_dto.notes:
            candidates_display += "\n".join(boundary_dto.notes)
        
        _set_info_card(self._notes_card, candidates_display if candidates_display else "No additional notes")

    def _reset_selection(self) -> None:
        if self._tracks_table.rowCount() > 0:
            self._tracks_table.selectRow(0)


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
