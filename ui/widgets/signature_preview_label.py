"""Signature preview widget with drag and drop support."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import QLabel

from config import C_BLUE, C_BORDER, C_GREY_LT, C_TEXT_SECONDARY


class SignaturePreviewLabel(QLabel):
    """Clickable and droppable image preview label for signature inputs."""

    image_dropped = pyqtSignal(str)
    clicked = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(220, 90)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._current_path: str | None = None
        self._original_pixmap: QPixmap | None = None

        self._apply_placeholder_style()

    def _apply_placeholder_style(self, drag_highlight: bool = False) -> None:
        border_color = C_BLUE if drag_highlight else C_BORDER
        bg_color = "#EAF3FF" if drag_highlight else C_GREY_LT
        self.setPixmap(QPixmap())
        self._original_pixmap = None
        self.setText("Drop image here or click to browse")
        self.setStyleSheet(
            f"""
            QLabel {{
                border: 2px dashed {border_color};
                background: {bg_color};
                color: {C_TEXT_SECONDARY};
                font-size: 8pt;
                font-style: italic;
                padding: 8px;
            }}
            """
        )

    def _apply_image_style(self) -> None:
        self.setStyleSheet(
            f"""
            QLabel {{
                border: 2px solid {C_BORDER};
                background: #FFFFFF;
                color: {C_TEXT_SECONDARY};
                font-size: 8pt;
                padding: 4px;
            }}
            """
        )

    def _render_current_pixmap(self) -> None:
        if self._original_pixmap is None or self._original_pixmap.isNull():
            return

        scaled = self._original_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setText("")
        self._apply_image_style()

    def set_image_from_path(self, file_path: str) -> None:
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            return
        self._current_path = file_path
        self._original_pixmap = pixmap
        self._render_current_pixmap()

    def set_image_from_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            return
        self._current_path = None
        self._original_pixmap = QPixmap(pixmap)
        self._render_current_pixmap()

    def set_image_from_bytes(self, blob: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(QByteArray(blob)):
            return
        self.set_image_from_pixmap(pixmap)

    def clear_image(self) -> None:
        self._current_path = None
        self._apply_placeholder_style()

    def get_current_path(self) -> str | None:
        return self._current_path

    def _is_supported_image(self, path: str) -> bool:
        suffix = Path(path).suffix.lower()
        return suffix in {".png", ".jpg", ".jpeg"}

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile() and self._is_supported_image(url.toLocalFile()):
                    event.acceptProposedAction()
                    self._apply_placeholder_style(drag_highlight=True)
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        if not event.mimeData().hasUrls():
            event.ignore()
            self._apply_placeholder_style()
            return

        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if self._is_supported_image(path):
                self.set_image_from_path(path)
                self.image_dropped.emit(path)
                event.acceptProposedAction()
                return

        event.ignore()
        self._apply_placeholder_style()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        _ = event
        if self._original_pixmap is None:
            self._apply_placeholder_style()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._original_pixmap is not None:
            self._render_current_pixmap()
