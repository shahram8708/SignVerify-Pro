"""Camera service for real-time video capture operations."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtGui import QImage

from utils.logger import get_logger


class CameraService:
    """Provides camera lifecycle management and frame conversion helpers."""

    def __init__(self, device_index: int = 0, resolution: tuple = (640, 480)) -> None:
        self.device_index = int(device_index)
        self.resolution = resolution
        self.cap: cv2.VideoCapture | None = None
        self.logger = get_logger("camera_service")

    def open(self) -> bool:
        width, height = self.resolution
        self.cap = cv2.VideoCapture(self.device_index)
        if not self.cap.isOpened():
            self.logger.error("Failed to open camera device index=%s", self.device_index)
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
        self.logger.info(
            "Camera opened index=%s resolution=%sx%s",
            self.device_index,
            int(width),
            int(height),
        )
        return True

    def read_frame(self) -> np.ndarray | None:
        if self.cap is None or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret or frame is None:
            return None
        return frame

    def release(self) -> None:
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            self.logger.info("Camera released")
        self.cap = None

    def capture_to_pil(self) -> Image.Image | None:
        frame = self.read_frame()
        if frame is None:
            return None
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb_frame)

    @staticmethod
    def frame_to_qimage(frame: np.ndarray) -> QImage:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb_frame.shape
        bytes_per_line = channels * width
        image = QImage(
            rgb_frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        )
        return image.copy()

    def get_device_index(self) -> int:
        return self.device_index

    @staticmethod
    def list_available_cameras(max_check: int = 5) -> list[int]:
        available: list[int] = []
        checks = max(1, int(max_check))
        for index in range(checks):
            cap = cv2.VideoCapture(index)
            try:
                if cap.isOpened():
                    available.append(index)
            finally:
                cap.release()
        return available
