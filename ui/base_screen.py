"""Reusable base screen widget with shared helpers."""

from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QFrame, QLabel, QMessageBox, QVBoxLayout, QWidget

from config import C_DANGER, C_SUCCESS


class BaseScreen(QWidget):
    """Base class for all app screens."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._loading_overlay: QFrame | None = None
        self._spinner_label: QLabel | None = None
        self._loading_message_label: QLabel | None = None
        self._spinner_timer: QTimer | None = None
        self._spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_index = 0

        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(24, 20, 24, 20)
        self.content_layout.setSpacing(16)

        self._build_ui()

    def _build_ui(self) -> None:
        label = QLabel("Base Screen")
        self.content_layout.addWidget(label)

    def on_show(self, **kwargs) -> None:
        _ = kwargs
        return None

    def _set_content_enabled(self, enabled: bool) -> None:
        for index in range(self.content_layout.count()):
            item = self.content_layout.itemAt(index)
            widget = item.widget()
            if widget is not None and widget is not self._loading_overlay:
                widget.setEnabled(enabled)

    def show_loading(self, msg: str = "Processing...") -> None:
        if self._loading_overlay is not None:
            if self._loading_message_label is not None:
                self._loading_message_label.setText(msg)
            return

        self._set_content_enabled(False)

        overlay = QFrame(self)
        overlay.setObjectName("loading_overlay")
        overlay.setGeometry(self.rect())
        overlay.setStyleSheet("QFrame#loading_overlay { background-color: rgba(10, 22, 40, 170); }")

        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overlay_layout.setSpacing(8)

        spinner_label = QLabel(self._spinner_frames[0], overlay)
        spinner_label.setStyleSheet("color: white; font-size: 30px; font-weight: 700;")
        spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        message_label = QLabel(msg, overlay)
        message_label.setStyleSheet("color: white; font-size: 11pt;")
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        overlay_layout.addWidget(spinner_label)
        overlay_layout.addWidget(message_label)

        timer = QTimer(self)
        timer.setInterval(80)

        def _tick() -> None:
            self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
            if self._spinner_label is not None:
                self._spinner_label.setText(self._spinner_frames[self._spinner_index])

        timer.timeout.connect(_tick)
        timer.start()

        self._loading_overlay = overlay
        self._spinner_label = spinner_label
        self._loading_message_label = message_label
        self._spinner_timer = timer

        overlay.show()
        overlay.raise_()

    def hide_loading(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer.deleteLater()
            self._spinner_timer = None

        if self._loading_overlay is not None:
            self._loading_overlay.hide()
            self._loading_overlay.deleteLater()
            self._loading_overlay = None

        self._spinner_label = None
        self._loading_message_label = None
        self._set_content_enabled(True)

    def show_error(self, title: str, message: str) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.setStyleSheet(
            f"""
            QMessageBox QLabel {{ color: {C_DANGER}; }}
            QMessageBox QPushButton {{ min-width: 90px; }}
            """
        )
        dialog.exec()

    def show_success(self, title: str, message: str) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.setStyleSheet(
            f"""
            QMessageBox QLabel {{ color: {C_SUCCESS}; }}
            QMessageBox QPushButton {{ min-width: 90px; }}
            """
        )
        dialog.exec()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._loading_overlay is not None:
            self._loading_overlay.setGeometry(self.rect())
