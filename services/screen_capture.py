"""Screen capture service implementation."""

from __future__ import annotations

import os
import uuid

import numpy as np
from PIL import Image

from config import APP_DATA_DIR
from utils.logger import get_logger


class ScreenCaptureService:
    """Capture monitor, active window, or custom regions via mss."""

    def __init__(self) -> None:
        self.logger = get_logger("screen_capture")

    def get_available_monitors(self) -> list[dict]:
        monitors_info: list[dict] = []
        try:
            import mss

            with mss.mss() as sct:
                for index, monitor in enumerate(sct.monitors):
                    width = int(monitor.get("width", 0))
                    height = int(monitor.get("height", 0))
                    left = int(monitor.get("left", 0))
                    top = int(monitor.get("top", 0))

                    if index == 0:
                        label = "All Monitors (Combined)"
                    elif index == 1:
                        label = "Monitor 1 (Primary)"
                    else:
                        label = f"Monitor {index}"

                    monitors_info.append(
                        {
                            "index": index,
                            "label": label,
                            "width": width,
                            "height": height,
                            "left": left,
                            "top": top,
                        }
                    )
        except Exception as exc:
            self.logger.exception("Failed to enumerate monitors")
            self.logger.warning("Monitor enumeration failed: %s", exc)

        return monitors_info

    def capture_full_screen(self, monitor_index: int = 1) -> Image.Image:
        import mss

        requested_index = int(monitor_index)
        with mss.mss() as sct:
            try:
                monitor = sct.monitors[requested_index]
                resolved_index = requested_index
            except IndexError:
                resolved_index = 1 if len(sct.monitors) > 1 else 0
                monitor = sct.monitors[resolved_index]

            shot = sct.grab(monitor)

        image = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
        self.logger.info(
            "Screen captured: %sx%s from monitor %s",
            shot.width,
            shot.height,
            resolved_index,
        )
        return image

    def capture_active_window(self) -> Image.Image:
        if os.name != "nt":
            self.logger.warning(
                "Active window capture not supported on this platform — falling back to full screen"
            )
            return self.capture_full_screen(1)

        try:
            import win32gui

            hwnd = win32gui.GetForegroundWindow()
            if hwnd == 0:
                self.logger.warning("No active window found — falling back to full screen")
                return self.capture_full_screen(1)

            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = int(right - left)
            height = int(bottom - top)

            if width <= 0 or height <= 0:
                self.logger.warning("Active window bounds invalid — falling back to full screen")
                return self.capture_full_screen(1)

            import mss

            region = {
                "left": int(left),
                "top": int(top),
                "width": width,
                "height": height,
            }

            with mss.mss() as sct:
                shot = sct.grab(region)

            image = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
            self.logger.info(
                "Screen captured: %sx%s from active window",
                shot.width,
                shot.height,
            )
            return image
        except Exception as exc:
            self.logger.warning("Active window capture failed: %s", exc)
            return self.capture_full_screen(1)

    def capture_region(self, left: int, top: int, width: int, height: int) -> Image.Image:
        if int(width) <= 0 or int(height) <= 0:
            raise ValueError("Width and height must be greater than zero")

        import mss

        region = {
            "left": int(left),
            "top": int(top),
            "width": int(width),
            "height": int(height),
        }

        with mss.mss() as sct:
            shot = sct.grab(region)

        image = Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)
        self.logger.info(
            "Screen captured: %sx%s from custom region (%s, %s)",
            shot.width,
            shot.height,
            int(left),
            int(top),
        )
        return image

    def capture_by_mode(
        self,
        mode: str,
        monitor_index: int = 1,
        region: dict | None = None,
    ) -> Image.Image:
        normalized_mode = (mode or "").strip().lower()

        if normalized_mode == "full_screen":
            return self.capture_full_screen(monitor_index)
        if normalized_mode == "active_window":
            return self.capture_active_window()
        if normalized_mode == "custom_region":
            if region is None:
                raise ValueError("Custom region requires a region dict")
            return self.capture_region(
                left=int(region["left"]),
                top=int(region["top"]),
                width=int(region["width"]),
                height=int(region["height"]),
            )

        raise ValueError(f"Unsupported capture mode: {mode}")

    def save_capture_to_temp(self, pil_image: Image.Image) -> str:
        temp_dir = APP_DATA_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        filename = f"capture_{uuid.uuid4().hex[:12]}.png"
        output_path = temp_dir / filename
        pil_image.save(output_path, format="PNG")
        return str(output_path.resolve())

    def pil_to_numpy(self, pil_image: Image.Image) -> np.ndarray:
        return np.array(pil_image.convert("RGB"))
