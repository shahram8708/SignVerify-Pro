"""Interactive full-screen crop dialog for signature extraction."""

from __future__ import annotations

from PIL import Image
from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from config import C_BLUE, C_BORDER, C_DANGER, C_GOLD, C_SUCCESS, C_TEXT_SECONDARY, C_WHITE
from utils.logger import get_logger


class CropDialog(QDialog):
    """Full-screen crop selection dialog with auto-detected suggestions."""

    def __init__(
        self,
        parent=None,
        screenshot: Image.Image | None = None,
        detections: list | None = None,
        source_context: str | None = None,
    ) -> None:
        super().__init__(parent)

        self.screenshot = screenshot
        self.detections = detections or []
        self.source_context = (source_context or "").strip()
        self.selected_rect: QRect | None = None
        self.is_drawing = False
        self.draw_start: QPoint | None = None
        self.current_rect: QRect | None = None
        self.screenshot_pixmap: QPixmap | None = None
        self.scale_factor = 1.0
        self.display_image_rect = QRect()

        self.logger = get_logger("crop_dialog")

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setWindowOpacity(0.95)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("QDialog { background: rgba(0, 0, 0, 0.92); }")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.display_label = QLabel(self)
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display_label.setStyleSheet("background: transparent;")
        self.display_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        root_layout.addWidget(self.display_label, 1)

        self.instruction_bar = QFrame(self)
        self.instruction_bar.setStyleSheet(
            f"""
            QFrame {{
                background: rgba(10, 22, 40, 217);
                border-top: 1px solid rgba(255, 255, 255, 40);
            }}
            QLabel {{
                background: transparent;
            }}
            """
        )

        instruction_layout = QHBoxLayout(self.instruction_bar)
        instruction_layout.setContentsMargins(18, 10, 18, 10)
        instruction_layout.setSpacing(16)

        self.source_context_label = QLabel(
            self._format_source_context_text(),
            self.instruction_bar,
        )
        self.source_context_label.setStyleSheet(
            f"background: rgba(255, 255, 255, 28); color: {C_WHITE}; border-radius: 4px; padding: 4px 8px; font-size: 8.5pt; font-weight: 700;"
        )
        self.source_context_label.setVisible(bool(self.source_context))

        self.left_instruction = QLabel(
            "✏ Click and drag to select the signature region",
            self.instruction_bar,
        )
        self.left_instruction.setStyleSheet(f"color: {C_WHITE}; font-size: 10pt;")

        self.center_instruction = QLabel(
            "Or click a highlighted region below to select it automatically",
            self.instruction_bar,
        )
        self.center_instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.center_instruction.setStyleSheet(f"color: {C_WHITE}; font-size: 10pt;")

        self.warning_label = QLabel("", self.instruction_bar)
        self.warning_label.setVisible(False)
        self.warning_label.setStyleSheet(f"color: {C_DANGER}; font-size: 9pt; font-weight: 700;")

        button_wrap = QHBoxLayout()
        button_wrap.setSpacing(8)

        self.confirm_button = QPushButton("✓ Confirm", self.instruction_bar)
        self.confirm_button.setEnabled(False)
        self.confirm_button.clicked.connect(self._on_confirm)
        self.confirm_button.setStyleSheet(
            f"""
            QPushButton {{
                background: {C_SUCCESS};
                color: {C_WHITE};
                font-size: 10pt;
                font-weight: 700;
                border-radius: 6px;
                padding: 8px 14px;
            }}
            QPushButton:disabled {{
                background: {C_BORDER};
                color: {C_TEXT_SECONDARY};
            }}
            """
        )

        self.cancel_button = QPushButton("✗ Cancel", self.instruction_bar)
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setStyleSheet(
            f"""
            QPushButton {{
                background: {C_DANGER};
                color: {C_WHITE};
                font-size: 10pt;
                font-weight: 700;
                border-radius: 6px;
                padding: 8px 14px;
            }}
            """
        )

        button_wrap.addWidget(self.confirm_button)
        button_wrap.addWidget(self.cancel_button)

        instruction_layout.addWidget(self.source_context_label)
        instruction_layout.addWidget(self.left_instruction)
        instruction_layout.addWidget(self.center_instruction, 1)
        instruction_layout.addWidget(self.warning_label)
        instruction_layout.addLayout(button_wrap)

        root_layout.addWidget(self.instruction_bar)

        if self.screenshot is not None:
            self.screenshot_pixmap = self._pil_to_qpixmap(self.screenshot)

        self._update_display_pixmap()

    def _format_source_context_text(self) -> str:
        if not self.source_context:
            return ""
        return f"Source: {self.source_context}"

    def _pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        rgb_image = pil_image.convert("RGB")
        width, height = rgb_image.size
        bytes_data = rgb_image.tobytes("raw", "RGB")
        qimage = QImage(bytes_data, width, height, width * 3, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(qimage)

    def _update_display_pixmap(self) -> None:
        if self.screenshot_pixmap is None or self.screenshot_pixmap.isNull():
            self.display_label.setText("No screenshot provided")
            self.display_label.setStyleSheet(f"color: {C_TEXT_SECONDARY};")
            self.display_image_rect = QRect()
            self.scale_factor = 1.0
            return

        available_size = self.display_label.size()
        if available_size.width() <= 0 or available_size.height() <= 0:
            return

        scaled = self.screenshot_pixmap.scaled(
            available_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.display_label.setPixmap(scaled)

        original_width = max(1, self.screenshot.width)
        self.scale_factor = scaled.width() / float(original_width)

        label_rect = self.display_label.geometry()
        offset_x = (label_rect.width() - scaled.width()) // 2
        offset_y = (label_rect.height() - scaled.height()) // 2
        self.display_image_rect = QRect(
            label_rect.x() + offset_x,
            label_rect.y() + offset_y,
            scaled.width(),
            scaled.height(),
        )

    def _clip_to_image_rect(self, point: QPoint) -> QPoint:
        if self.display_image_rect.isNull():
            return point

        x = min(max(point.x(), self.display_image_rect.left()), self.display_image_rect.right())
        y = min(max(point.y(), self.display_image_rect.top()), self.display_image_rect.bottom())
        return QPoint(x, y)

    def _display_rect_from_detection(self, detection: dict) -> QRect:
        x = int(detection.get("x", 0))
        y = int(detection.get("y", 0))
        width = int(detection.get("width", 0))
        height = int(detection.get("height", 0))

        return QRect(
            self.display_image_rect.x() + int(round(x * self.scale_factor)),
            self.display_image_rect.y() + int(round(y * self.scale_factor)),
            int(round(width * self.scale_factor)),
            int(round(height * self.scale_factor)),
        )

    def _display_to_screenshot_rect(self, rect: QRect) -> QRect | None:
        if self.screenshot is None or self.scale_factor <= 0:
            return None

        source_width = self.screenshot.width
        source_height = self.screenshot.height

        x = int(round((rect.x() - self.display_image_rect.x()) / self.scale_factor))
        y = int(round((rect.y() - self.display_image_rect.y()) / self.scale_factor))
        width = int(round(rect.width() / self.scale_factor))
        height = int(round(rect.height() / self.scale_factor))

        x = max(0, min(x, source_width - 1))
        y = max(0, min(y, source_height - 1))
        width = max(1, min(width, source_width - x))
        height = max(1, min(height, source_height - y))

        return QRect(x, y, width, height)

    def _selected_rect_in_display_coords(self) -> QRect | None:
        if self.selected_rect is None:
            return None

        return QRect(
            self.display_image_rect.x() + int(round(self.selected_rect.x() * self.scale_factor)),
            self.display_image_rect.y() + int(round(self.selected_rect.y() * self.scale_factor)),
            int(round(self.selected_rect.width() * self.scale_factor)),
            int(round(self.selected_rect.height() * self.scale_factor)),
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)

        if self.display_image_rect.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rank_colors = {1: QColor(C_SUCCESS), 2: QColor(C_BLUE), 3: QColor(C_GOLD)}
        rank_labels = {
            1: "Auto-detected #1 (Best Match)",
            2: "Auto-detected #2",
            3: "Auto-detected #3",
        }

        for index, detection in enumerate(self.detections[:3], start=1):
            rect = self._display_rect_from_detection(detection)
            if rect.width() <= 0 or rect.height() <= 0:
                continue

            rank = int(detection.get("rank", index))
            color = rank_colors.get(rank, QColor(C_BLUE))

            pen = QPen(color, 2)
            pen.setDashPattern([6, 3])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

            badge_text = rank_labels.get(rank, f"Auto-detected #{rank}")
            badge_font = QFont(self.font())
            badge_font.setPointSize(8)
            badge_font.setBold(True)
            painter.setFont(badge_font)

            metrics = painter.fontMetrics()
            badge_width = metrics.horizontalAdvance(badge_text) + 16
            badge_height = metrics.height() + 6
            badge_x = rect.x()
            badge_y = rect.y() - badge_height - 4
            if badge_y < self.display_image_rect.y():
                badge_y = rect.y() + 4

            badge_rect = QRect(badge_x, badge_y, badge_width, badge_height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(badge_rect, 6, 6)
            painter.setPen(QColor(C_WHITE))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        if self.current_rect is not None and self.is_drawing:
            painter.setPen(QPen(QColor(C_BLUE), 2))
            painter.setBrush(QColor(21, 101, 192, 60))
            painter.drawRect(self.current_rect)

        selected_display_rect = self._selected_rect_in_display_coords()
        if selected_display_rect is not None:
            painter.setPen(QPen(QColor(C_SUCCESS), 3))
            painter.setBrush(QColor(46, 125, 50, 40))
            painter.drawRect(selected_display_rect)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        click_point = event.position().toPoint()

        if not self.display_image_rect.contains(click_point):
            super().mousePressEvent(event)
            return

        for detection in self.detections[:3]:
            detection_rect = self._display_rect_from_detection(detection)
            if detection_rect.contains(click_point):
                self.selected_rect = QRect(
                    int(detection.get("x", 0)),
                    int(detection.get("y", 0)),
                    int(detection.get("width", 0)),
                    int(detection.get("height", 0)),
                )
                self.current_rect = None
                self.is_drawing = False
                self.confirm_button.setEnabled(True)
                self.warning_label.setVisible(False)
                self.update()
                return

        self.is_drawing = True
        self.draw_start = self._clip_to_image_rect(click_point)
        self.current_rect = QRect(self.draw_start, QSize(0, 0))
        self.selected_rect = None
        self.confirm_button.setEnabled(False)
        self.warning_label.setVisible(False)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.is_drawing or self.draw_start is None:
            super().mouseMoveEvent(event)
            return

        end_point = self._clip_to_image_rect(event.position().toPoint())
        self.current_rect = QRect(self.draw_start, end_point).normalized()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton or not self.is_drawing:
            super().mouseReleaseEvent(event)
            return

        self.is_drawing = False

        if self.current_rect is not None and self.current_rect.width() > 20 and self.current_rect.height() > 10:
            screenshot_rect = self._display_to_screenshot_rect(self.current_rect)
            if screenshot_rect is not None:
                self.selected_rect = screenshot_rect
                self.confirm_button.setEnabled(True)
        else:
            self.current_rect = None

        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return

        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self.selected_rect is not None:
            self.accept()
            return

        super().keyPressEvent(event)

    def _on_confirm(self) -> None:
        if self.selected_rect is None:
            self.warning_label.setText("Please select a region first")
            self.warning_label.setVisible(True)
            QTimer.singleShot(1500, lambda: self.warning_label.setVisible(False))
            return

        self.accept()

    def get_cropped_image(self) -> Image.Image | None:
        if self.selected_rect is None or self.screenshot is None:
            return None

        image_width = self.screenshot.width
        image_height = self.screenshot.height

        x = max(0, min(self.selected_rect.x(), image_width - 1))
        y = max(0, min(self.selected_rect.y(), image_height - 1))
        width = max(1, min(self.selected_rect.width(), image_width - x))
        height = max(1, min(self.selected_rect.height(), image_height - y))

        return self.screenshot.crop((x, y, x + width, y + height))

    def get_selected_rect(self) -> QRect | None:
        return self.selected_rect

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_display_pixmap()
        self.update()
