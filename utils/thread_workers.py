"""QThread worker definitions for async tasks."""

from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal

from utils.logger import get_logger

logger = get_logger(__name__)


class LocalModelWorker(QThread):
    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(str)

    def __init__(
        self,
        reference_image_path: str,
        submitted_image_path: str,
        person_name: str,
    ) -> None:
        super().__init__()
        self.reference_image_path = reference_image_path
        self.submitted_image_path = submitted_image_path
        self.person_name = person_name

    def run(self) -> None:
        try:
            self.progress_updated.emit("Loading local AI model...")

            from services.local_model_service import LocalModelService

            service = LocalModelService()

            self.progress_updated.emit("Preprocessing signature images...")
            time.sleep(0.2)

            self.progress_updated.emit("Running 13-strategy forensic analysis on local model...")
            result_dict = service.verify_signatures(
                self.reference_image_path,
                self.submitted_image_path,
                self.person_name,
            )
            self.progress_updated.emit("Computing forensic observations...")
            time.sleep(0.3)
            self.result_ready.emit(result_dict)
        except Exception as exc:
            self.error_occurred.emit(f"Local model inference failed: {str(exc)}")


class DetectionWorker(QThread):
    detections_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(str)

    def __init__(self, screenshot_image, sensitivity: float) -> None:
        super().__init__()
        self.screenshot_image = screenshot_image
        self.sensitivity = sensitivity

    def run(self) -> None:
        try:
            self.progress_updated.emit("Initializing OpenCV detection pipeline...")

            from services.signature_detector import SignatureDetector

            detector = SignatureDetector(sensitivity=self.sensitivity)

            self.progress_updated.emit("Applying adaptive thresholding and morphological analysis...")
            detections = detector.detect(self.screenshot_image)

            self.progress_updated.emit("Scoring and ranking candidate regions...")
            time.sleep(0.3)

            if not detections:
                self.detections_ready.emit([])
                return

            self.detections_ready.emit(detections)
        except Exception as exc:
            logger.exception("Detection worker failed")
            self.error_occurred.emit(f"Detection failed: {str(exc)}")


class CameraWorker(QThread):
    frame_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, device_index: int, resolution: tuple) -> None:
        super().__init__()
        self.device_index = device_index
        self.resolution = resolution
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        from services.camera_service import CameraService

        camera_service = CameraService(self.device_index, self.resolution)
        if not camera_service.open():
            self.error_occurred.emit(
                f"Cannot open camera device {self.device_index}. Check camera connection and device index in Settings."
            )
            return

        frames_processed = 0
        fps_checkpoint = time.time()

        try:
            while not self._stop_event.is_set():
                frame = camera_service.read_frame()
                if frame is None:
                    self.error_occurred.emit("Camera feed lost.")
                    break

                qimage = CameraService.frame_to_qimage(frame)
                self.frame_ready.emit(qimage)

                frames_processed += 1
                if frames_processed % 30 == 0:
                    now = time.time()
                    elapsed = now - fps_checkpoint
                    _fps = 0.0 if elapsed <= 0 else 30.0 / elapsed
                    fps_checkpoint = now

                time.sleep(0.033)
        except Exception as exc:
            self.error_occurred.emit(f"Camera worker error: {exc}")
        finally:
            camera_service.release()


class ExportWorker(QThread):
    export_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(str)

    def __init__(self, verification_data: dict, output_path: str) -> None:
        super().__init__()
        self.verification_data = verification_data
        self.output_path = output_path

    def run(self) -> None:
        try:
            self.progress_updated.emit("Generating PDF report...")

            from services.export_service import ExportService

            ExportService().generate_report(self.verification_data, self.output_path)
            self.export_complete.emit(self.output_path)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
