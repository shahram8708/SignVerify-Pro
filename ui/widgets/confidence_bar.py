"""Confidence progress bar widget with custom painting and animation."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PyQt6.QtWidgets import QProgressBar

from config import C_GREY_LT


class ConfidenceBar(QProgressBar):
    """Rounded confidence bar that paints confidence gradients manually."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRange(0, 100)
        self.setValue(0)
        self.setFixedHeight(28)
        self.setTextVisible(True)
        self.setFormat("%p%")
        self.setStyleSheet("QProgressBar { border: none; background: transparent; }")

        self._animation_timer: QTimer | None = None
        self._animation_step = 0
        self._animation_steps = 0
        self._animation_start = 0
        self._animation_target = 0

    def _colors_for_value(self, value: int) -> tuple[str, str]:
        if value <= 49:
            return "#C62828", "#E53935"
        if value <= 65:
            return "#E65100", "#FF9800"
        if value <= 85:
            return "#388E3C", "#66BB6A"
        return "#2E7D32", "#43A047"

    def paintEvent(self, event) -> None:  # noqa: N802
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect().adjusted(0, 0, -1, -1))
        radius = 6.0

        groove_path = QPainterPath()
        groove_path.addRoundedRect(rect, radius, radius)
        painter.fillPath(groove_path, QBrush(QColor(C_GREY_LT)))

        value = max(0, min(100, int(self.value())))
        if value > 0:
            fill_width = int((value / 100.0) * rect.width())
            fill_rect = rect.adjusted(0, 0, -(rect.width() - fill_width), 0)

            fill_path = QPainterPath()
            fill_path.addRoundedRect(fill_rect, radius, radius)

            left_color, right_color = self._colors_for_value(value)
            gradient = QLinearGradient(fill_rect.left(), fill_rect.center().y(), fill_rect.right(), fill_rect.center().y())
            gradient.setColorAt(0.0, QColor(left_color))
            gradient.setColorAt(1.0, QColor(right_color))

            painter.fillPath(fill_path, QBrush(gradient))

        text = f"{value}%"
        text_font = QFont(self.font())
        text_font.setBold(True)
        painter.setFont(text_font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(rect, 0x0004 | 0x0080, text)

    def set_confidence(self, value: float) -> None:
        percentage = int(round(max(0.0, min(1.0, float(value))) * 100.0))
        self.setValue(percentage)
        self.update()

    def animate_to(self, target_value: float, duration_ms: int = 800) -> None:
        target = int(round(max(0.0, min(1.0, float(target_value))) * 100.0))
        start = int(self.value())

        if self._animation_timer is not None and self._animation_timer.isActive():
            self._animation_timer.stop()
            self._animation_timer.deleteLater()

        self._animation_step = 0
        self._animation_steps = max(1, int(duration_ms / 16))
        self._animation_start = start
        self._animation_target = target

        interval = max(10, int(duration_ms / self._animation_steps))

        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(interval)

        def _tick() -> None:
            self._animation_step += 1
            progress = min(1.0, self._animation_step / self._animation_steps)
            current = int(round(self._animation_start + (self._animation_target - self._animation_start) * progress))
            self.setValue(current)
            self.update()

            if self._animation_step >= self._animation_steps and self._animation_timer is not None:
                self._animation_timer.stop()

        self._animation_timer.timeout.connect(_tick)
        self._animation_timer.start()
