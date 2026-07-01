from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout


class StatusBanner(QFrame):
    """Status line with semantic visual states for user feedback."""

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBanner")

        self._label = QLabel("Ready")
        self._label.setObjectName("StatusBannerText")
        self._label.setWordWrap(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.addWidget(self._label)

        self.set_status("Drop a recording to begin.", tone="info")

    def set_status(self, message: str, tone: str = "info") -> None:
        """Set banner text and visual tone."""

        marker = _tone_marker(tone)
        self._label.setText(f"{marker} {message}")
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


def _tone_marker(tone: str) -> str:
    markers = {
        "success": "[OK]",
        "warning": "[!]",
        "error": "[X]",
        "info": "[i]",
    }
    return markers.get(tone, "[i]")
