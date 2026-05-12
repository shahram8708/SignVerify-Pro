"""Selectable card widget used by the window picker dialog."""

from __future__ import annotations

import hashlib

from PIL import Image
from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QImage, QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from config import C_BLUE, C_BORDER, C_TEXT_PRIMARY, C_TEXT_SECONDARY, C_WHITE
from services.window_enumerator import WindowEnumerator, WindowInfo


class WindowCardWidget(QFrame):
    """Card representing a selectable screen or application window."""

    selected = pyqtSignal(int)

    def __init__(self, window_info: WindowInfo, parent=None, dialog=None) -> None:
        super().__init__(parent)
        self.window_info = window_info
        self.dialog = dialog
        self._is_selected = False
        self._is_hovered = False
        self._thumbnail_loaded = False
        self._shimmer_on = False

        self.setFixedSize(280, 175)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("windowCard")

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(6)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(0, 0, 0, 20))
        self.setGraphicsEffect(self._shadow)

        self._build_ui()
        self._apply_default_style()
        self._start_shimmer()

        if self.window_info.hwnd < 0:
            self.thumbnail_label.setText("🖥")
            self.thumbnail_label.setStyleSheet(
                "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                "stop:0 #DCEBFF, stop:1 #F4F8FF);"
                "color: #1F3B64;"
                "font-size: 32pt;"
                "font-weight: 700;"
                "border-top-left-radius: 8px;"
                "border-top-right-radius: 8px;"
            )

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.selection_bar = QFrame(self)
        self.selection_bar.setFixedHeight(4)
        self.selection_bar.setVisible(False)
        self.selection_bar.setStyleSheet(f"background: {C_BLUE}; border: none;")

        self.thumbnail_label = QLabel("Loading preview...", self)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setFixedHeight(130)
        self.thumbnail_label.setStyleSheet(
            "background: #E8EAED;"
            "color: #6B7280;"
            "font-size: 8pt;"
            "border-top-left-radius: 8px;"
            "border-top-right-radius: 8px;"
        )

        self.selected_badge = QLabel("✓", self.thumbnail_label)
        self.selected_badge.setFixedSize(20, 20)
        self.selected_badge.move(252, 8)
        self.selected_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selected_badge.setVisible(False)
        self.selected_badge.setStyleSheet(
            f"background: {C_BLUE};"
            f"color: {C_WHITE};"
            "font-size: 9pt;"
            "font-weight: 700;"
            "border-radius: 10px;"
        )

        self.minimized_badge = QLabel("Minimised", self.thumbnail_label)
        self.minimized_badge.adjustSize()
        self.minimized_badge.move(8, 106)
        self.minimized_badge.setVisible(bool(self.window_info.is_minimized))
        self.minimized_badge.setStyleSheet(
            "background: rgba(107,114,128,0.9);"
            "color: white;"
            "font-size: 7pt;"
            "padding: 2px 4px;"
            "border-radius: 4px;"
        )

        bottom = QWidget(self)
        bottom.setFixedHeight(45)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(8, 6, 8, 6)
        bottom_layout.setSpacing(6)

        self.icon_label = QLabel(bottom)
        self.icon_label.setFixedSize(16, 16)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = WindowEnumerator().get_process_icon(self.window_info)
        if icon is not None:
            pixmap = icon.pixmap(16, 16)
            if not pixmap.isNull():
                self.icon_label.setPixmap(pixmap)

        if self.icon_label.pixmap() is None:
            self.icon_label.setStyleSheet(
                f"background: {self._fallback_color(self.window_info.process_name)};"
                "border-radius: 4px;"
            )

        text_wrap = QWidget(bottom)
        text_layout = QVBoxLayout(text_wrap)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        self.title_label = QLabel(self._elided_title(self.window_info.title), text_wrap)
        self.title_label.setStyleSheet(f"font-size: 9pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

        self.process_label = QLabel(self.window_info.process_name or "Unknown Process", text_wrap)
        self.process_label.setStyleSheet(f"font-size: 7pt; color: {C_TEXT_SECONDARY};")

        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.process_label)

        self.resolution_label = QLabel(bottom)
        self.resolution_label.setStyleSheet(f"font-size: 7pt; color: {C_TEXT_SECONDARY};")
        if self.window_info.hwnd < 0:
            self.resolution_label.setText(f"{self.window_info.width}×{self.window_info.height}")
        else:
            self.resolution_label.setText("")

        bottom_layout.addWidget(self.icon_label)
        bottom_layout.addWidget(text_wrap, 1)
        bottom_layout.addWidget(self.resolution_label)

        outer_layout.addWidget(self.selection_bar)
        outer_layout.addWidget(self.thumbnail_label)
        outer_layout.addWidget(bottom)

        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(600)
        self._shimmer_timer.timeout.connect(self._on_shimmer_tick)

    def _fallback_color(self, process_name: str) -> str:
        seed = (process_name or "unknown").encode("utf-8", errors="ignore")
        digest = hashlib.md5(seed).hexdigest()
        red = int(digest[0:2], 16)
        green = int(digest[2:4], 16)
        blue = int(digest[4:6], 16)
        red = 80 + (red % 120)
        green = 80 + (green % 120)
        blue = 80 + (blue % 120)
        return f"rgb({red}, {green}, {blue})"

    def _elided_title(self, title: str) -> str:
        metrics = QFontMetrics(self.font())
        return metrics.elidedText(title, Qt.TextElideMode.ElideRight, 200)

    def _start_shimmer(self) -> None:
        if self.window_info.hwnd < 0:
            return
        self._shimmer_timer.start()

    def _on_shimmer_tick(self) -> None:
        if self._thumbnail_loaded:
            return

        self._shimmer_on = not self._shimmer_on
        color = "#F0F2F5" if self._shimmer_on else "#E8EAED"
        self.thumbnail_label.setStyleSheet(
            f"background: {color};"
            "color: #6B7280;"
            "font-size: 8pt;"
            "border-top-left-radius: 8px;"
            "border-top-right-radius: 8px;"
        )

    def set_thumbnail(self, pil_image: Image.Image) -> None:
        image = pil_image.convert("RGB")
        width, height = image.size
        data = image.tobytes("raw", "RGB")
        qimage = QImage(data, width, height, width * 3, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimage)

        self.thumbnail_label.setText("")
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setPixmap(
            pixmap.scaled(
                280,
                130,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.thumbnail_label.setStyleSheet(
            f"background: {C_WHITE};"
            "border-top-left-radius: 8px;"
            "border-top-right-radius: 8px;"
        )

        self._thumbnail_loaded = True
        if self._shimmer_timer.isActive():
            self._shimmer_timer.stop()

    def set_selected(self, selected: bool) -> None:
        self._is_selected = bool(selected)

        if self._is_selected:
            self.selection_bar.setVisible(True)
            self.selected_badge.setVisible(True)
            self._shadow.setBlurRadius(12)
            self._shadow.setOffset(0, 4)
        else:
            self.selection_bar.setVisible(False)
            self.selected_badge.setVisible(False)
            self._shadow.setBlurRadius(8 if self._is_hovered else 6)
            self._shadow.setOffset(0, 3 if self._is_hovered else 2)

        self._apply_default_style()
        self.update()
        self.repaint()

    def _apply_default_style(self) -> None:
        if self._is_selected:
            self.setStyleSheet(
                f"QFrame#windowCard {{"
                f"background: #F0F7FF;"
                f"border: 2px solid {C_BLUE};"
                "border-radius: 8px;"
                "}"
            )
        elif self._is_hovered:
            self.setStyleSheet(
                f"QFrame#windowCard {{"
                "background: #FAFCFF;"
                f"border: 1px solid {C_BLUE};"
                "border-radius: 8px;"
                "}"
            )
        else:
            self.setStyleSheet(
                f"QFrame#windowCard {{"
                f"background: {C_WHITE};"
                f"border: 1px solid {C_BORDER};"
                "border-radius: 8px;"
                "}"
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(int(self.window_info.hwnd))
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(int(self.window_info.hwnd))
            if self.dialog is not None:
                self.dialog.accept()
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self._is_hovered = True
        if not self._is_selected:
            self._shadow.setBlurRadius(8)
            self._shadow.setOffset(0, 3)
        self._apply_default_style()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self._is_hovered = False
        if not self._is_selected:
            self._shadow.setBlurRadius(6)
            self._shadow.setOffset(0, 2)
        self._apply_default_style()
        super().leaveEvent(event)
