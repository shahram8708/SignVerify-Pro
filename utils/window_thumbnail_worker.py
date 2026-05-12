"""Background worker for progressive window thumbnail refresh."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from PyQt6.QtCore import QThread, pyqtSignal

from services.window_enumerator import WindowEnumerator


class WindowThumbnailWorker(QThread):
    windows_discovered = pyqtSignal(list)
    thumbnail_ready = pyqtSignal(int, object)
    refresh_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, thumb_width: int = 280, thumb_height: int = 160) -> None:
        super().__init__()
        self.thumb_width = int(thumb_width)
        self.thumb_height = int(thumb_height)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            enumerator = WindowEnumerator()
            window_list = enumerator.get_all_windows()
            self.windows_discovered.emit(window_list)

            executor = ThreadPoolExecutor(max_workers=4)
            try:
                for window_info in window_list:
                    if self._stop_event.is_set():
                        break

                    future = executor.submit(
                        enumerator.capture_window_thumbnail,
                        window_info,
                        self.thumb_width,
                        self.thumb_height,
                    )

                    try:
                        thumbnail = future.result(timeout=0.5)
                    except FutureTimeoutError:
                        thumbnail = enumerator.create_placeholder_thumbnail(
                            "Preview unavailable",
                            self.thumb_width,
                            self.thumb_height,
                        )
                    except Exception:
                        thumbnail = enumerator.create_placeholder_thumbnail(
                            "Preview unavailable",
                            self.thumb_width,
                            self.thumb_height,
                        )

                    if self._stop_event.is_set():
                        break

                    self.thumbnail_ready.emit(int(window_info.hwnd), thumbnail)
                    time.sleep(0.05)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

            self.refresh_complete.emit()
        except Exception as exc:
            self.error_occurred.emit(str(exc))
