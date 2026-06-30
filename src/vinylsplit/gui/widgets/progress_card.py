from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout


class ProgressCard(QFrame):
    """Progress summary card used by workspace placeholders."""

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProgressCard")

        self._label = QLabel("Idle")
        self._label.setObjectName("ProgressLabel")

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(True)

        self._anim = QPropertyAnimation(self._bar, b"value", self)
        self._anim.setDuration(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)

    def set_progress(self, value: int, label: str) -> None:
        """Set current progress details."""

        clamped = max(0, min(100, value))
        self._anim.stop()
        self._anim.setStartValue(self._bar.value())
        self._anim.setEndValue(clamped)
        self._anim.start()
        self._label.setText(label)
