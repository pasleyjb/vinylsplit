"""Review workstation waveform view with backend-driven candidate display.

Displays:
- Waveform timeline representation
- All backend-detected candidate boundaries with their confidence scores
- Per-detector confidence breakdown visualization
- Click-to-select candidate boundaries
- Visual confidence indicators
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QFrame

from vinylsplit.application.dto.review import ReviewBoundaryDTO


class ReviewWaveformView(QWidget):
    """Waveform display with backend candidate visualization."""

    candidate_selected = Signal(float)  # Emits timestamp of selected candidate

    def __init__(self, boundary: ReviewBoundaryDTO, duration: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._boundary = boundary
        self._duration = duration
        self._selected_candidate_idx = 0 if boundary.candidates else None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header with boundary info
        header = QLabel(f"Track {boundary.track_number}: Boundary at {boundary.selected_timestamp:.2f}s")
        header.setObjectName("SectionTitle")

        # Confidence display
        if boundary.confidence:
            confidence_text = (
                f"Confidence: {boundary.confidence.overall * 100:.0f}% | "
                f"{boundary.confidence.display_breakdown}"
            )
        else:
            confidence_text = "Confidence: Unknown"
        confidence_label = QLabel(confidence_text)
        confidence_label.setObjectName("StatusBarText")

        # Waveform canvas (custom painting)
        self._waveform = _WaveformCanvas(boundary, duration)
        self._waveform.candidate_clicked.connect(self._on_candidate_clicked)

        # Candidates list
        candidates_label = QLabel("Detected Candidates (ranked by confidence):")
        candidates_label.setObjectName("StatusBarText")
        candidates_text = self._build_candidates_text()
        candidates_display = QLabel(candidates_text)
        candidates_display.setObjectName("StatusBarText")
        candidates_display.setWordWrap(True)

        layout.addWidget(header)
        layout.addWidget(confidence_label)
        layout.addWidget(candidates_label)
        layout.addWidget(self._waveform, stretch=2)
        layout.addWidget(candidates_display, stretch=1)

    def _build_candidates_text(self) -> str:
        """Build formatted text listing all candidates."""
        if not self._boundary.candidates:
            return "No alternative candidates detected."

        lines = []
        for candidate in self._boundary.candidates:
            icon = "✓" if candidate.rank == 0 else "○"
            lines.append(f"  {icon} {candidate.display_label}")
        return "\n".join(lines)

    def _on_candidate_clicked(self, timestamp: float) -> None:
        """Handle candidate selection from waveform."""
        # Find candidate index
        for idx, candidate in enumerate(self._boundary.candidates):
            if abs(candidate.timestamp - timestamp) < 0.01:
                self._selected_candidate_idx = idx
                break
        self.candidate_selected.emit(timestamp)


class _WaveformCanvas(QFrame):
    """Canvas for drawing waveform and candidate markers."""

    candidate_clicked = Signal(float)

    def __init__(self, boundary: ReviewBoundaryDTO, duration: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._boundary = boundary
        self._duration = duration
        self._selected_timestamp = boundary.selected_timestamp
        self.setStyleSheet("background-color: #1e1e1e; border: 1px solid #404040;")
        self.setMinimumHeight(180)

    def paintEvent(self, event) -> None:
        """Draw waveform timeline, candidates, and confidence visualization."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        margin = 40

        # Draw timeline background
        painter.fillRect(margin, 20, width - 2 * margin, height - 40, QColor("#252525"))

        # Draw time grid and labels
        self._draw_timeline(painter, width, height, margin)

        # Draw candidate markers
        if self._boundary.candidates:
            self._draw_candidates(painter, width, height, margin)

        # Draw selected boundary highlight
        self._draw_selected_boundary(painter, width, height, margin)

    def _draw_timeline(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        """Draw timeline grid and time labels."""
        painter.setPen(QPen(QColor("#404040"), 1))

        # Draw major grid lines every 30 seconds
        step = 30.0
        time = 0.0
        font = QFont("Courier", 8)
        painter.setFont(font)

        while time <= self._duration:
            x = margin + (time / self._duration) * (width - 2 * margin)
            painter.drawLine(int(x), 20, int(x), height - 20)

            # Draw time label
            time_str = _format_time(time)
            text_rect = painter.fontMetrics().boundingRect(time_str)
            painter.drawText(int(x) - text_rect.width() // 2, height - 8, time_str)

            time += step

    def _draw_candidates(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        """Draw candidate boundary markers."""
        canvas_width = width - 2 * margin
        canvas_height = height - 40
        baseline = 20 + canvas_height // 2

        for candidate in self._boundary.candidates:
            # Calculate x position
            x = margin + (candidate.timestamp / self._duration) * canvas_width

            # Color based on rank (selected is green, others fade)
            if candidate.rank == 0:
                color = QColor("#00d946")  # Green for selected
                line_width = 3
            else:
                # Fade color based on confidence
                confidence = int(candidate.confidence * 255)
                color = QColor(100, 100, 255, confidence)
                line_width = 2

            # Draw vertical line marker
            painter.setPen(QPen(color, line_width))
            painter.drawLine(int(x), 20, int(x), height - 20)

            # Draw confidence label above marker
            confidence_pct = int(candidate.confidence * 100)
            label = f"{confidence_pct}%"

            # Draw semi-transparent box with text
            painter.setPen(QPen(color, 1))
            painter.setFont(QFont("Courier", 8))
            text_rect = painter.fontMetrics().boundingRect(label)
            box_x = int(x) - text_rect.width() // 2 - 2
            box_y = 5
            painter.fillRect(box_x - 2, box_y - 2, text_rect.width() + 4, text_rect.height() + 4, QColor(0, 0, 0, 200))
            painter.drawText(box_x, box_y + text_rect.height(), label)

    def _draw_selected_boundary(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        """Highlight the selected boundary."""
        canvas_width = width - 2 * margin
        x = margin + (self._selected_timestamp / self._duration) * canvas_width

        # Draw thick orange line for selected
        painter.setPen(QPen(QColor("#ff9500"), 4))
        painter.drawLine(int(x), 20, int(x), height - 20)

        # Draw label
        painter.setFont(QFont("Courier", 9, QFont.Weight.Bold))
        label = "SELECTED"
        text_rect = painter.fontMetrics().boundingRect(label)
        box_x = int(x) - text_rect.width() // 2 - 2
        box_y = height - 35
        painter.fillRect(box_x - 2, box_y - 2, text_rect.width() + 4, text_rect.height() + 4, QColor(255, 149, 0, 200))
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.drawText(box_x, box_y + text_rect.height(), label)

    def mousePressEvent(self, event) -> None:
        """Handle candidate selection by clicking."""
        if event.button() != Qt.MouseButton.LeftButton:
            return

        width = self.width()
        height = self.height()
        margin = 40

        # Calculate which candidate was clicked
        canvas_width = width - 2 * margin
        x_pos = event.position().x()

        if margin <= x_pos <= width - margin:
            # Convert screen position to time
            clicked_time = (x_pos - margin) / canvas_width * self._duration

            # Find nearest candidate within 2 seconds
            nearest_candidate = None
            nearest_distance = 2.0

            for candidate in self._boundary.candidates:
                distance = abs(candidate.timestamp - clicked_time)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_candidate = candidate

            if nearest_candidate:
                self._selected_timestamp = nearest_candidate.timestamp
                self.candidate_clicked.emit(nearest_candidate.timestamp)
                self.update()


def _format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"
