from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from vinylsplit.application.dto.review import ReviewBoundaryDTO


class ReviewWaveformView(QWidget):
    """Waveform-like timeline display backed by review boundary candidates."""

    candidate_selected = Signal(float)

    def __init__(self, boundary: ReviewBoundaryDTO, duration: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._boundary = boundary
        self._duration = max(1.0, duration)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel(f"Track {boundary.track_number} boundary @ {boundary.selected_timestamp:.2f}s")
        header.setObjectName("SectionTitle")

        confidence_text = "Confidence: --"
        if boundary.confidence is not None:
            confidence_text = (
                f"Confidence: {boundary.confidence.overall * 100:.0f}% "
                f"({boundary.confidence.display_breakdown})"
            )
        confidence = QLabel(confidence_text)
        confidence.setObjectName("StatusBarText")

        candidates_label = QLabel("Candidates")
        candidates_label.setObjectName("StatusBarText")
        candidates_detail = QLabel(self._build_candidates_text())
        candidates_detail.setObjectName("StatusBarText")
        candidates_detail.setWordWrap(True)

        self._canvas = _WaveformCanvas(boundary=boundary, duration=self._duration)
        self._canvas.candidate_clicked.connect(self.candidate_selected.emit)

        layout.addWidget(header)
        layout.addWidget(confidence)
        layout.addWidget(self._canvas, stretch=2)
        layout.addWidget(candidates_label)
        layout.addWidget(candidates_detail, stretch=1)

    def _build_candidates_text(self) -> str:
        if not self._boundary.candidates:
            return "No alternative candidates detected by backend."

        lines = []
        for candidate in self._boundary.candidates[:5]:
            marker = "*" if candidate.rank == 0 else "-"
            lines.append(f"{marker} {candidate.display_label} ({candidate.reason})")
        return "\n".join(lines)


class _WaveformCanvas(QFrame):
    """Simple painted timeline with candidate markers."""

    candidate_clicked = Signal(float)

    def __init__(self, boundary: ReviewBoundaryDTO, duration: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._boundary = boundary
        self._duration = max(1.0, duration)
        self._selected_timestamp = boundary.selected_timestamp
        self.setMinimumHeight(180)
        self.setStyleSheet("background-color: #1f1f1f; border: 1px solid #3f3f3f;")

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        margin = 40

        painter.fillRect(margin, 20, width - 2 * margin, height - 40, QColor("#2a2a2a"))
        self._draw_timeline(painter, width, height, margin)
        self._draw_candidates(painter, width, height, margin)
        self._draw_selected(painter, width, height, margin)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if not self._boundary.candidates:
            return

        width = self.width()
        margin = 40
        canvas_width = width - 2 * margin
        x_pos = event.position().x()
        if x_pos < margin or x_pos > width - margin:
            return

        clicked_time = ((x_pos - margin) / max(1.0, canvas_width)) * self._duration
        nearest = None
        nearest_distance = 2.0
        for candidate in self._boundary.candidates:
            distance = abs(candidate.timestamp - clicked_time)
            if distance < nearest_distance:
                nearest = candidate
                nearest_distance = distance

        if nearest is not None:
            self._selected_timestamp = nearest.timestamp
            self.candidate_clicked.emit(nearest.timestamp)
            self.update()

    def _draw_timeline(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        painter.setPen(QPen(QColor("#444444"), 1))
        painter.setFont(QFont("Monospace", 8))
        step = 30.0
        tick = 0.0
        while tick <= self._duration:
            x = margin + (tick / self._duration) * (width - 2 * margin)
            painter.drawLine(int(x), 20, int(x), height - 20)
            painter.drawText(int(x) - 16, height - 6, _format_time(tick))
            tick += step

    def _draw_candidates(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        if not self._boundary.candidates:
            return

        canvas_width = width - 2 * margin
        for candidate in self._boundary.candidates:
            x = margin + (candidate.timestamp / self._duration) * canvas_width
            if candidate.rank == 0:
                color = QColor("#27d345")
                line_width = 3
            else:
                alpha = max(70, min(220, int(candidate.confidence * 255)))
                color = QColor(90, 150, 255, alpha)
                line_width = 2

            painter.setPen(QPen(color, line_width))
            painter.drawLine(int(x), 20, int(x), height - 20)

    def _draw_selected(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        canvas_width = width - 2 * margin
        x = margin + (self._selected_timestamp / self._duration) * canvas_width
        painter.setPen(QPen(QColor("#ff9a1f"), 4))
        painter.drawLine(int(x), 20, int(x), height - 20)

        label = "SELECTED"
        painter.setFont(QFont("Monospace", 9, QFont.Weight.Bold))
        painter.setPen(QPen(QColor("#111111"), 1))
        painter.fillRect(int(x) - 30, height - 32, 60, 18, QColor(255, 154, 31, 210))
        painter.drawText(int(x) - 25, height - 18, label)


def _format_time(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"