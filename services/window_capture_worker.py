"""Worker for non blocking full resolution window capture."""

from __future__ import annotations

import time

from PyQt6.QtCore import QThread, pyqtSignal

import win32con
import win32gui

from services.window_enumerator import WindowEnumerator, WindowInfo


class CaptureWorker(QThread):
    capture_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    progress_updated = pyqtSignal(str)

    def __init__(self, window_info: WindowInfo) -> None:
        super().__init__()
        self.window_info = window_info

    def run(self) -> None:
        was_minimized = bool(self.window_info.is_minimized)

        try:
            self.progress_updated.emit("Preparing window for capture...")

            if self.window_info.hwnd >= 0 and not win32gui.IsWindow(self.window_info.hwnd):
                raise RuntimeError("WINDOW_CLOSED")

            if self.window_info.hwnd >= 0 and was_minimized:
                self.progress_updated.emit("Restoring minimised window...")
                win32gui.ShowWindow(self.window_info.hwnd, win32con.SW_RESTORE)
                time.sleep(0.5)

            self.progress_updated.emit(f"Capturing '{self.window_info.title}'...")
            image = WindowEnumerator().capture_window_full(self.window_info)

            if self.window_info.hwnd >= 0 and was_minimized:
                win32gui.ShowWindow(self.window_info.hwnd, win32con.SW_MINIMIZE)

            self.capture_ready.emit(image)
        except Exception as exc:
            try:
                if self.window_info.hwnd >= 0 and was_minimized and win32gui.IsWindow(self.window_info.hwnd):
                    win32gui.ShowWindow(self.window_info.hwnd, win32con.SW_MINIMIZE)
            except Exception:
                pass
            self.error_occurred.emit(str(exc))
