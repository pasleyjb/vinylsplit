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


class ReviewDialog(QDialog):
    """Boundary review dialog that serves as the visual foundation for future editing."""

    def __init__(self, boundaries: tuple[object, ...], parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Boundary Review")
        self.setModal(True)
        self.resize(1240, 780)

        self._boundaries = tuple(boundaries)

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

        title = QLabel("Waveform Editor")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Coming Soon")
        subtitle.setObjectName("StatusBarText")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        capabilities = QLabel(
            "Future capabilities\n"
            "• Zoom\n"
            "• Playback Preview\n"
            "• Boundary Dragging\n"
            "• Spectrogram Overlay\n"
            "• Keyboard Shortcuts\n"
            "• Undo / Redo\n"
            "• Precision Editing"
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
        boundaries = list(self._boundaries)
        self._tracks_table.setRowCount(len(boundaries))

        for row, boundary in enumerate(boundaries):
            start = float(getattr(boundary, "start_time", 0.0))
            end = self._track_end_seconds(row)
            length = max(0.0, end - start) if end is not None else None
            confidence = getattr(boundary, "detector_confidence", None)
            status = getattr(getattr(boundary, "state", None), "display_label", None)

            self._tracks_table.setItem(row, 0, QTableWidgetItem(str(getattr(boundary, "track_number", row + 1))))
            self._tracks_table.setItem(row, 1, QTableWidgetItem(_format_timestamp(start)))
            self._tracks_table.setItem(row, 2, QTableWidgetItem(_format_timestamp(end) if end is not None else "--"))
            self._tracks_table.setItem(row, 3, QTableWidgetItem(_format_duration(length) if length is not None else "--"))
            self._tracks_table.setItem(
                row,
                4,
                QTableWidgetItem(f"{confidence * 100:.0f}%" if confidence is not None else "--"),
            )
            self._tracks_table.setItem(
                row,
                5,
                QTableWidgetItem(
                    status(confidence) if callable(status) else str(getattr(boundary, "state", "AUTO"))
                ),
            )

    def _track_end_seconds(self, row: int) -> float | None:
        if row + 1 < len(self._boundaries):
            return float(getattr(self._boundaries[row + 1], "start_time", 0.0))
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

        track_number = getattr(boundary, "track_number", row + 1)
        start = float(getattr(boundary, "start_time", 0.0))
        end = self._track_end_seconds(row)
        length = max(0.0, end - start) if end is not None else None
        confidence = getattr(boundary, "detector_confidence", None)
        reasons = getattr(boundary, "reasons", None) or []
        state = getattr(boundary, "state", None)

        self._selection_label.setText(f"Current selection: Track {track_number}")

        _set_info_card(self._track_card, str(track_number))
        _set_info_card(self._start_card, _format_timestamp(start))
        _set_info_card(self._end_card, _format_timestamp(end) if end is not None else "End of recording")
        _set_info_card(self._length_card, _format_duration(length) if length is not None else "--")
        _set_info_card(self._confidence_card, f"{confidence * 100:.0f}%" if confidence is not None else "--")
        _set_info_card(self._method_card, reasons[0] if reasons else "Silence-guided detection")
        _set_info_card(
            self._status_card,
            state.display_label(confidence) if state is not None and hasattr(state, "display_label") else "AUTO",
        )
        _set_info_card(
            self._notes_card,
            "; ".join(reasons) if reasons else "No additional notes for this boundary.",
        )

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
