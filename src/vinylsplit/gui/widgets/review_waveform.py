from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from vinylsplit.application.dto.review import ReviewBoundaryDTO


class ReviewWaveformView(QWidget):
    """Waveform-like timeline display backed by review boundary candidates."""

    TAB_HALF_WIDTH = 18.0
    TAB_HEIGHT = 16.0

    candidate_selected = Signal(float)
    boundary_dragged = Signal(float)
    boundary_tab_selected = Signal(int)
    boundary_tab_dragged = Signal(int, float)
    seek_requested = Signal(float)
    add_boundary_requested = Signal(float)
    delete_boundary_requested = Signal(int)
    anchor_and_refine_requested = Signal(int)
    undo_requested = Signal()
    redo_requested = Signal()

    def __init__(
        self,
        boundary: ReviewBoundaryDTO,
        duration: float,
        boundary_times: list[float] | None = None,
        waveform_envelope: list[float] | None = None,
        selected_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._boundary = boundary
        self._duration = max(1.0, duration)
        self._boundary_times = list(boundary_times or [boundary.selected_timestamp])
        if not self._boundary_times:
            self._boundary_times = [boundary.selected_timestamp]
        self._selected_index = max(0, min(selected_index, len(self._boundary_times) - 1))

        self._zoom_factor = 3.0
        self._base_pixels_per_second = 2.0

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

        self._canvas = _WaveformCanvas(
            boundary=boundary,
            duration=self._duration,
            boundary_times=self._boundary_times,
            waveform_envelope=waveform_envelope,
            selected_index=self._selected_index,
        )
        self._canvas.candidate_clicked.connect(self._on_candidate_clicked)
        self._canvas.boundary_dragged.connect(self._on_boundary_dragged)
        self._canvas.boundary_tab_selected.connect(self._on_boundary_tab_selected)
        self._canvas.boundary_tab_dragged.connect(self._on_boundary_tab_dragged)
        self._canvas.seek_requested.connect(self._on_seek_requested)
        self._canvas.add_boundary_requested.connect(self.add_boundary_requested.emit)
        self._canvas.delete_boundary_requested.connect(self.delete_boundary_requested.emit)
        self._canvas.anchor_and_refine_requested.connect(self.anchor_and_refine_requested.emit)
        self._canvas.undo_requested.connect(self.undo_requested.emit)
        self._canvas.redo_requested.connect(self.redo_requested.emit)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(6)
        zoom_label = QLabel("Zoom")
        zoom_label.setObjectName("StatusBarText")

        self._zoom_out_button = QPushButton("🔍−")
        self._zoom_out_button.setObjectName("SecondaryButton")
        self._zoom_out_button.setFixedSize(26, 20)
        self._zoom_out_button.clicked.connect(self._zoom_out)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(1, 12)
        self._zoom_slider.setValue(int(round(self._zoom_factor)))
        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)

        self._zoom_in_button = QPushButton("🔍+")
        self._zoom_in_button.setObjectName("SecondaryButton")
        self._zoom_in_button.setFixedSize(26, 20)
        self._zoom_in_button.clicked.connect(self._zoom_in)

        self._zoom_value_label = QLabel("")
        self._zoom_value_label.setObjectName("StatusBarText")

        zoom_row.addWidget(zoom_label)
        zoom_row.addWidget(self._zoom_out_button)
        zoom_row.addWidget(self._zoom_slider, stretch=1)
        zoom_row.addWidget(self._zoom_in_button)
        zoom_row.addWidget(self._zoom_value_label)

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setWidget(self._canvas)

        self._apply_zoom(center_seconds=boundary.selected_timestamp)

        layout.addWidget(header)
        layout.addWidget(confidence)
        layout.addLayout(zoom_row)
        layout.addWidget(self._scroll_area, stretch=1)

        QTimer.singleShot(0, lambda: self._ensure_visible(boundary.selected_timestamp, center=True))

    def set_playhead(self, seconds: float) -> None:
        self._canvas.set_playhead(seconds)
        self._ensure_visible(seconds)

    def minimum_boundary_gap_seconds(self) -> float:
        return self._canvas.minimum_boundary_gap_seconds()

    def _on_zoom_changed(self, value: int) -> None:
        self._zoom_factor = float(value)
        self._apply_zoom(center_seconds=self._current_view_center_seconds())

    def _zoom_in(self) -> None:
        self._zoom_slider.setValue(min(self._zoom_slider.maximum(), self._zoom_slider.value() + 1))

    def _zoom_out(self) -> None:
        self._zoom_slider.setValue(max(self._zoom_slider.minimum(), self._zoom_slider.value() - 1))

    def _apply_zoom(self, center_seconds: float | None = None) -> None:
        pixels_per_second = self._base_pixels_per_second * self._zoom_factor
        content_width = int(max(900, (self._duration * pixels_per_second) + (2 * _WaveformCanvas.MARGIN)))
        self._canvas.setFixedWidth(content_width)
        self._zoom_value_label.setText(f"{self._zoom_factor:.1f}x")
        if center_seconds is not None:
            QTimer.singleShot(0, lambda: self._ensure_visible(center_seconds, center=True))

    def _current_view_center_seconds(self) -> float:
        scrollbar = self._scroll_area.horizontalScrollBar()
        viewport_width = self._scroll_area.viewport().width()
        center_x = scrollbar.value() + max(0, viewport_width // 2)
        return self._canvas.x_to_seconds(center_x)

    def _ensure_visible(self, seconds: float, center: bool = False) -> None:
        x = self._canvas.seconds_to_x(seconds)
        scrollbar = self._scroll_area.horizontalScrollBar()
        viewport_width = self._scroll_area.viewport().width()

        if center:
            target = int(x - (viewport_width / 2))
            scrollbar.setValue(max(0, target))
            return

        left = scrollbar.value()
        right = left + viewport_width
        padding = 48
        if x < left + padding:
            scrollbar.setValue(max(0, int(x - padding)))
        elif x > right - padding:
            scrollbar.setValue(max(0, int(x - viewport_width + padding)))

    def _on_candidate_clicked(self, timestamp: float) -> None:
        self._ensure_visible(timestamp)
        self.candidate_selected.emit(timestamp)

    def _on_boundary_dragged(self, timestamp: float) -> None:
        self._ensure_visible(timestamp)
        self.boundary_dragged.emit(timestamp)

    def _on_boundary_tab_selected(self, index: int) -> None:
        if 0 <= index < len(self._boundary_times):
            self._ensure_visible(self._boundary_times[index])
        self.boundary_tab_selected.emit(index)

    def _on_boundary_tab_dragged(self, index: int, timestamp: float) -> None:
        if 0 <= index < len(self._boundary_times):
            self._boundary_times[index] = timestamp
        self._ensure_visible(timestamp)
        self.boundary_tab_dragged.emit(index, timestamp)

    def _on_seek_requested(self, timestamp: float) -> None:
        self._ensure_visible(timestamp)
        self.seek_requested.emit(timestamp)


class _WaveformCanvas(QFrame):
    """Simple painted timeline with candidate markers."""

    TAB_HALF_WIDTH = 18.0
    TAB_HEIGHT = 16.0
    TAB_GAP_PIXELS = 6.0

    candidate_clicked = Signal(float)
    boundary_dragged = Signal(float)
    boundary_tab_selected = Signal(int)
    boundary_tab_dragged = Signal(int, float)
    seek_requested = Signal(float)
    add_boundary_requested = Signal(float)
    delete_boundary_requested = Signal(int)
    anchor_and_refine_requested = Signal(int)
    undo_requested = Signal()
    redo_requested = Signal()

    MARGIN = 40

    def __init__(
        self,
        boundary: ReviewBoundaryDTO,
        duration: float,
        boundary_times: list[float],
        waveform_envelope: list[float] | None,
        selected_index: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._boundary = boundary
        self._duration = max(1.0, duration)
        self._selected_timestamp = boundary.selected_timestamp
        self._boundary_times = list(boundary_times)
        self._waveform_left: list[float] = []
        self._waveform_right: list[float] = []
        self._set_waveform_envelope(waveform_envelope)
        self._selected_index = max(0, min(selected_index, len(self._boundary_times) - 1))
        self._tab_hitboxes: list[tuple[int, QRectF]] = []
        self._playhead_timestamp: float | None = None
        self._dragging_boundary = False
        self._dragging_tab_index: int | None = None
        self.setMinimumHeight(380)
        self.setStyleSheet("background-color: #1f1f1f; border: 1px solid #3f3f3f;")

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        margin = self.MARGIN

        painter.fillRect(margin, 20, width - 2 * margin, height - 40, QColor("#2a2a2a"))
        self._draw_waveform(painter, width, height, margin)
        self._draw_timeline(painter, width, height, margin)
        self._draw_boundary_tabs(painter, width, height, margin)
        self._draw_candidates(painter, width, height, margin)
        self._draw_playhead(painter, width, height, margin)
        self._draw_selected(painter, width, height, margin)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return

        width = self.width()
        margin = self.MARGIN
        canvas_width = width - 2 * margin
        x_pos = event.position().x()
        if x_pos < margin or x_pos > width - margin:
            return

        clicked_time = ((x_pos - margin) / max(1.0, canvas_width)) * self._duration

        for index, tab_rect in self._tab_hitboxes:
            if tab_rect.contains(QPointF(x_pos, event.position().y())):
                self._selected_index = index
                self._selected_timestamp = self._boundary_times[index]
                self.boundary_tab_selected.emit(index)
                self._dragging_tab_index = index
                self.update()
                return

        selected_x = margin + (self._selected_timestamp / self._duration) * canvas_width
        if abs(x_pos - selected_x) <= 10:
            self._dragging_boundary = True
            self._selected_timestamp = self._clamp_timestamp(clicked_time)
            self.update()
            return

        if not self._boundary.candidates:
            self.seek_requested.emit(clicked_time)
            return

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
            return

        self.seek_requested.emit(clicked_time)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging_tab_index is not None:
            width = self.width()
            margin = self.MARGIN
            canvas_width = width - 2 * margin
            x_pos = min(max(event.position().x(), margin), width - margin)
            moved_time = ((x_pos - margin) / max(1.0, canvas_width)) * self._duration
            clamped = self._clamp_tab_timestamp(self._dragging_tab_index, moved_time)
            self._boundary_times[self._dragging_tab_index] = clamped
            self._selected_index = self._dragging_tab_index
            self._selected_timestamp = clamped
            self.boundary_tab_dragged.emit(self._dragging_tab_index, clamped)
            self.update()
            return

        if not self._dragging_boundary:
            return

        width = self.width()
        margin = self.MARGIN
        canvas_width = width - 2 * margin
        x_pos = min(max(event.position().x(), margin), width - margin)
        moved_time = ((x_pos - margin) / max(1.0, canvas_width)) * self._duration
        self._selected_timestamp = self._clamp_timestamp(moved_time)
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_tab_index is not None:
            index = self._dragging_tab_index
            self._dragging_tab_index = None
            self.boundary_tab_dragged.emit(index, self._boundary_times[index])
            self.update()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._dragging_boundary:
            self._dragging_boundary = False
            self.boundary_dragged.emit(self._selected_timestamp)
            self.update()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        width = self.width()
        margin = self.MARGIN
        canvas_width = width - 2 * margin
        x_pos = float(event.pos().x())
        y_pos = float(event.pos().y())

        menu = QMenu(self)
        tab_index = None
        for index, tab_rect in self._tab_hitboxes:
            if tab_rect.contains(QPointF(x_pos, y_pos)):
                tab_index = index
                break

        if margin <= x_pos <= width - margin:
            clicked_time = ((x_pos - margin) / max(1.0, canvas_width)) * self._duration
            add_action = menu.addAction("Add boundary here")
            add_action.triggered.connect(lambda: self.add_boundary_requested.emit(self._clamp_timestamp(clicked_time)))

        if tab_index is not None:
            anchor_action = menu.addAction("Anchor boundary and refine")
            anchor_action.triggered.connect(lambda: self.anchor_and_refine_requested.emit(tab_index))

            if tab_index > 0:
                delete_action = menu.addAction("Delete boundary")
                delete_action.triggered.connect(lambda: self.delete_boundary_requested.emit(tab_index))

        menu.addSeparator()
        undo_action = menu.addAction("Undo")
        redo_action = menu.addAction("Redo")
        undo_action.triggered.connect(self.undo_requested.emit)
        redo_action.triggered.connect(self.redo_requested.emit)

        menu.exec(event.globalPos())

    def _clamp_timestamp(self, value: float) -> float:
        return min(max(value, 0.0), self._duration)

    def _clamp_tab_timestamp(self, index: int, value: float) -> float:
        minimum_gap = self.minimum_boundary_gap_seconds()
        lower = 0.0 if index == 0 else self._boundary_times[index - 1] + minimum_gap
        upper = self._duration if index + 1 >= len(self._boundary_times) else self._boundary_times[index + 1] - minimum_gap
        return min(max(value, lower), upper)

    def minimum_boundary_gap_seconds(self) -> float:
        canvas_width = max(1.0, self.width() - (2 * self.MARGIN))
        seconds_per_pixel = self._duration / canvas_width
        required_pixels = (self.TAB_HALF_WIDTH * 2.0) + self.TAB_GAP_PIXELS
        return max(0.05, required_pixels * seconds_per_pixel)

    def set_playhead(self, seconds: float) -> None:
        self._playhead_timestamp = self._clamp_timestamp(seconds)
        self.update()

    def _draw_timeline(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        painter.setPen(QPen(QColor("#444444"), 1))
        painter.setFont(QFont("Monospace", 8))

        pixels_per_second = (width - 2 * margin) / max(1.0, self._duration)
        if pixels_per_second >= 16:
            step = 5.0
        elif pixels_per_second >= 8:
            step = 10.0
        elif pixels_per_second >= 4:
            step = 20.0
        else:
            step = 30.0

        tick = 0.0
        while tick <= self._duration:
            x = margin + (tick / self._duration) * (width - 2 * margin)
            painter.drawLine(int(x), 20, int(x), height - 20)
            painter.drawText(int(x) - 16, height - 6, _format_time(tick))
            tick += step

    def _draw_waveform(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        if not self._waveform_left and not self._waveform_right:
            return

        top = 24
        bottom = height - 24
        center = (top + bottom) / 2.0
        max_half_height = max(30.0, (bottom - top) * 0.43)
        canvas_width = width - 2 * margin
        sample_count = max(len(self._waveform_left), len(self._waveform_right))
        if canvas_width <= 0 or sample_count == 0:
            return

        self._draw_channel(
            painter,
            width,
            margin,
            self._waveform_left,
            center - (max_half_height * 0.58),
            max_half_height * 0.45,
            QColor(91, 192, 190, 180),
        )
        self._draw_channel(
            painter,
            width,
            margin,
            self._waveform_right,
            center + (max_half_height * 0.58),
            max_half_height * 0.45,
            QColor(255, 154, 31, 180),
        )

    def _draw_channel(
        self,
        painter: QPainter,
        width: int,
        margin: int,
        channel: list[float],
        center_y: float,
        max_half_height: float,
        color: QColor,
    ) -> None:
        if not channel:
            return

        canvas_width = width - 2 * margin
        sample_count = len(channel)
        if canvas_width <= 0 or sample_count == 0:
            return

        painter.setPen(QPen(color, 1))
        for index, peak in enumerate(channel):
            x = margin + (index / max(1, sample_count - 1)) * canvas_width
            clamped = min(max(peak, 0.0), 1.0)
            half_height = max(1.0, clamped * max_half_height)
            painter.drawLine(int(x), int(center_y - half_height), int(x), int(center_y + half_height))

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

    def _draw_boundary_tabs(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        canvas_width = width - 2 * margin
        self._tab_hitboxes = []
        painter.setFont(QFont("Monospace", 8, QFont.Weight.Bold))

        for index, timestamp in enumerate(self._boundary_times):
            x = margin + (timestamp / self._duration) * canvas_width
            top_rect = QRectF(x - self.TAB_HALF_WIDTH, 2, self.TAB_HALF_WIDTH * 2, self.TAB_HEIGHT)
            bottom_rect = QRectF(
                x - self.TAB_HALF_WIDTH,
                height - self.TAB_HEIGHT - 2,
                self.TAB_HALF_WIDTH * 2,
                self.TAB_HEIGHT,
            )
            self._tab_hitboxes.append((index, top_rect))
            self._tab_hitboxes.append((index, bottom_rect))
            is_selected = index == self._selected_index
            fill = QColor("#ff9a1f") if is_selected else QColor("#556270")
            painter.setPen(QPen(QColor("#111111") if is_selected else QColor("#d0d7de"), 1))
            painter.fillRect(top_rect, fill)
            painter.fillRect(bottom_rect, fill)
            painter.drawRect(top_rect)
            painter.drawRect(bottom_rect)
            painter.drawText(top_rect, Qt.AlignmentFlag.AlignCenter, f"T{index + 1}")
            painter.drawText(bottom_rect, Qt.AlignmentFlag.AlignCenter, f"T{index + 1}")

            painter.setPen(QPen(QColor("#ff9a1f") if is_selected else QColor("#768390"), 2 if is_selected else 1))
            painter.drawLine(int(x), int(top_rect.bottom()), int(x), int(bottom_rect.top()))

    def _draw_playhead(self, painter: QPainter, width: int, height: int, margin: int) -> None:
        if self._playhead_timestamp is None:
            return

        canvas_width = width - 2 * margin
        x = margin + (self._playhead_timestamp / self._duration) * canvas_width
        painter.setPen(QPen(QColor("#00e5ff"), 2))
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

    def seconds_to_x(self, seconds: float) -> float:
        clamped = self._clamp_timestamp(seconds)
        canvas_width = self.width() - (2 * self.MARGIN)
        return self.MARGIN + (clamped / self._duration) * max(1.0, canvas_width)

    def x_to_seconds(self, x_pos: float) -> float:
        canvas_width = self.width() - (2 * self.MARGIN)
        if canvas_width <= 0:
            return 0.0
        normalized = (x_pos - self.MARGIN) / canvas_width
        return self._clamp_timestamp(normalized * self._duration)

    def _set_waveform_envelope(self, waveform_envelope: list[float] | list[tuple[float, float]] | None) -> None:
        if not waveform_envelope:
            self._waveform_left = []
            self._waveform_right = []
            return

        first = waveform_envelope[0]
        if isinstance(first, (tuple, list)) and len(first) >= 2:
            self._waveform_left = [float(item[0]) for item in waveform_envelope]
            self._waveform_right = [float(item[1]) for item in waveform_envelope]
            return

        mono = [float(value) for value in waveform_envelope]
        self._waveform_left = mono
        self._waveform_right = list(mono)


def _format_time(seconds: float) -> str:
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes:02d}:{secs:02d}"
