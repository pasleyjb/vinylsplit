from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QSplitter,
    QVBoxLayout,
)


class ReviewDialog(QDialog):
    """Modal placeholder for advanced boundary review workflow."""

    def __init__(self, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Boundary Review")
        self.setModal(True)
        self.resize(1000, 640)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        intro = QLabel(
            "Review mode placeholder. Future milestones will add waveform, markers, playback, zoom, and editing tools."
        )
        intro.setWordWrap(True)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        waveform = _panel("Waveform", "Waveform renderer placeholder")
        inspector = _panel("Boundary Inspector", "Boundary controls placeholder")

        right_column = QFrame()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        right_layout.addWidget(inspector)

        track_nav = QListWidget()
        track_nav.addItem("Track navigation placeholder")
        track_nav.addItem("Playback preview placeholder")
        track_nav.addItem("Marker editing placeholder")
        right_layout.addWidget(track_nav)

        splitter.addWidget(waveform)
        splitter.addWidget(right_column)
        splitter.setSizes([700, 300])

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Zoom placeholder"))
        controls.addStretch(1)
        controls.addWidget(QLabel("Save/Cancel actions are placeholders"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(intro)
        root.addWidget(splitter, stretch=1)
        root.addLayout(controls)
        root.addWidget(buttons)


def _panel(title: str, text: str) -> QFrame:
    panel = QFrame()
    panel.setObjectName("Card")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(6)
    header = QLabel(title)
    header.setObjectName("SectionTitle")
    body = QLabel(text)
    body.setWordWrap(True)
    layout.addWidget(header)
    layout.addWidget(body)
    return panel
