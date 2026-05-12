"""Camera capture dialog implementation."""

from __future__ import annotations

import time
from collections import deque

import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent, QImage, QPixmap
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from config import C_BLUE, C_DANGER, C_SUCCESS, C_TEXT_SECONDARY
from controllers.settings_controller import settings_controller
from utils.logger import get_logger
from utils.thread_workers import CameraWorker

logger = get_logger(__name__)


class CameraDialog(QDialog):
    """Modal dialog that provides live camera preview and frame capture."""

    def __init__(
        self,
        parent=None,
        device_index: int = 0,
        resolution: tuple = (640, 480),
    ) -> None:
        super().__init__(parent)

        self.device_index = device_index
        self.resolution = resolution

        if device_index == 0:
            self.device_index = settings_controller.get_camera_index()

        if resolution == (640, 480):
            self.resolution = self._parse_resolution_from_settings(
                str(settings_controller.get("camera_resolution", "640×480") or "640×480")
            )

        self.camera_worker: CameraWorker | None = None
        self._latest_qimage: QImage | None = None
        self._captured_qimage: QImage | None = None
        self.captured_image: Image.Image | None = None
        self._preview_frozen = False

        self._frame_timestamps = deque(maxlen=30)
        self._frame_counter = 0

        self.setWindowTitle("Camera Capture")
        self.setModal(True)
        self.setFixedSize(720, 580)

        self._build_ui()
        self._center_on_parent()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        top_bar = QHBoxLayout()
        self.status_label = QLabel("🟢 Camera Active", self)
        self.status_label.setStyleSheet("font-size: 10pt; font-weight: 700;")

        self.fps_label = QLabel("FPS: --", self)
        self.fps_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.fps_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        top_bar.addWidget(self.status_label)
        top_bar.addStretch(1)
        top_bar.addWidget(self.fps_label)

        self.preview_label = QLabel(self)
        self.preview_label.setFixedSize(640, 480)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background: #000000; color: #FFFFFF; border-radius: 6px;")
        self.preview_label.setText("Starting camera...")

        self.captured_label = QLabel(self)
        self.captured_label.setFixedSize(640, 480)
        self.captured_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.captured_label.setStyleSheet("background: #000000; color: #FFFFFF; border-radius: 6px;")
        self.captured_label.hide()

        info_label = QLabel("📷 Hold the document with the signature facing the camera", self)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.captured_info_label = QLabel("✓ Image captured — ready to use", self)
        self.captured_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.captured_info_label.setStyleSheet(f"font-size: 9pt; font-weight: 700; color: {C_SUCCESS};")
        self.captured_info_label.hide()

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addStretch(1)

        self.capture_button = QPushButton("📷 Capture", self)
        self.capture_button.setMinimumWidth(150)
        self.capture_button.setStyleSheet(f"QPushButton {{ background: {C_BLUE}; color: white; font-weight: 700; }}")
        self.capture_button.clicked.connect(self._capture_frame)

        self.retake_button = QPushButton("🔄 Retake", self)
        self.retake_button.setObjectName("secondary")
        self.retake_button.clicked.connect(self._retake_frame)
        self.retake_button.hide()

        self.use_button = QPushButton("✓ Use This Image", self)
        self.use_button.setStyleSheet(f"QPushButton {{ background: {C_SUCCESS}; color: white; font-weight: 700; }}")
        self.use_button.clicked.connect(self._use_captured_image)
        self.use_button.hide()

        cancel_button = QPushButton("✗ Cancel", self)
        cancel_button.setObjectName("secondary")
        cancel_button.clicked.connect(self.reject)

        button_row.addWidget(self.capture_button)
        button_row.addWidget(self.retake_button)
        button_row.addWidget(self.use_button)
        button_row.addWidget(cancel_button)
        button_row.addStretch(1)

        layout.addLayout(top_bar)
        layout.addWidget(self.preview_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.captured_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)
        layout.addWidget(self.captured_info_label)
        layout.addLayout(button_row)

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        center = parent.frameGeometry().center()
        frame = self.frameGeometry()
        frame.moveCenter(center)
        self.move(frame.topLeft())

    def _parse_resolution_from_settings(self, value: str) -> tuple[int, int]:
        text = value.replace("×", "x").strip()
        parts = text.split("x")
        if len(parts) != 2:
            return 640, 480
        try:
            width = int(parts[0])
            height = int(parts[1])
            return width, height
        except ValueError:
            return 640, 480

    def _start_camera_worker(self) -> None:
        if self.camera_worker is not None and self.camera_worker.isRunning():
            return

        self.camera_worker = CameraWorker(self.device_index, self.resolution)
        self.camera_worker.frame_ready.connect(self._on_frame_ready)
        self.camera_worker.error_occurred.connect(self._on_camera_error)
        self.camera_worker.start()

    def _stop_camera_worker(self) -> None:
        if self.camera_worker is None:
            return

        try:
            self.camera_worker.stop()
            if self.camera_worker.isRunning():
                self.camera_worker.wait(3000)
        except Exception:
            logger.exception("Error while stopping camera worker")
        finally:
            self.camera_worker.deleteLater()
            self.camera_worker = None

    def _set_unavailable_preview(self, message: str) -> None:
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Camera feed unavailable. Check device index in Settings.")
        self.preview_label.setStyleSheet(
            "background: #DDE2EA; color: #4B5563; border-radius: 6px; font-size: 9pt; padding: 10px;"
        )
        logger.error("Camera error: %s", message)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._start_camera_worker()

    def _on_frame_ready(self, qimage: QImage) -> None:
        if self._preview_frozen:
            return

        self._latest_qimage = qimage.copy()

        pixmap = QPixmap.fromImage(qimage).scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setStyleSheet("background: #000000; color: #FFFFFF; border-radius: 6px;")

        self.status_label.setText("🟢 Camera Active")
        self.status_label.setStyleSheet("font-size: 10pt; font-weight: 700;")

        now = time.time()
        self._frame_timestamps.append(now)
        self._frame_counter += 1

        if self._frame_counter % 15 == 0 and len(self._frame_timestamps) == self._frame_timestamps.maxlen:
            elapsed = self._frame_timestamps[-1] - self._frame_timestamps[0]
            if elapsed > 0:
                fps = len(self._frame_timestamps) / elapsed
                self.fps_label.setText(f"FPS: {fps:.1f}")

    def _on_camera_error(self, message: str) -> None:
        self.status_label.setText("🔴 Camera Error")
        self.status_label.setStyleSheet(f"font-size: 10pt; font-weight: 700; color: {C_DANGER};")
        self.fps_label.setText("FPS: --")
        self._set_unavailable_preview(message)

    def _capture_frame(self) -> None:
        if self._latest_qimage is None:
            QMessageBox.warning(self, "Capture", "No camera frame available yet.")
            return

        self._captured_qimage = self._latest_qimage.copy()
        self._preview_frozen = True

        pixmap = QPixmap.fromImage(self._captured_qimage).scaled(
            self.captured_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.captured_label.setPixmap(pixmap)
        self.preview_label.hide()
        self.captured_label.show()
        self.captured_info_label.show()

        self.capture_button.hide()
        self.retake_button.show()
        self.use_button.show()

    def _retake_frame(self) -> None:
        self._captured_qimage = None
        self.captured_image = None
        self._preview_frozen = False

        self.captured_label.hide()
        self.preview_label.show()
        self.captured_info_label.hide()

        self.retake_button.hide()
        self.use_button.hide()
        self.capture_button.show()

    def _qimage_to_pil(self, qimage: QImage) -> Image.Image:
        converted = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
        width = converted.width()
        height = converted.height()
        ptr = converted.bits()
        ptr.setsize(converted.sizeInBytes())
        array = np.frombuffer(ptr, dtype=np.uint8).reshape((height, width, 4))
        return Image.fromarray(array[:, :, :3], "RGB")

    def _use_captured_image(self) -> None:
        if self._captured_qimage is None:
            QMessageBox.warning(self, "Capture", "Please capture an image first.")
            return

        try:
            self.captured_image = self._qimage_to_pil(self._captured_qimage)
            self.accept()
        except Exception as exc:
            logger.exception("Failed to convert captured frame")
            QMessageBox.critical(self, "Capture Error", str(exc))

    def reject(self) -> None:
        self._stop_camera_worker()
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._stop_camera_worker()
        super().closeEvent(event)

    def get_captured_pil_image(self) -> Image.Image | None:
        return self.captured_image
