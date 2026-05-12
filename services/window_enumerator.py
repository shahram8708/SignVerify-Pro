"""Window enumeration and capture service for Mode A window picker."""

from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mss
import numpy as np
import psutil
from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtGui import QIcon

import win32api
import win32con
import win32gui
import win32process
import win32ui

PW_RENDERFULLCONTENT = 2
WINDOW_CLOSED_SENTINEL = "WINDOW_CLOSED"


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    process_name: str
    process_id: int
    rect: tuple[int, int, int, int]
    width: int
    height: int
    thumbnail: Image.Image | None = None
    is_minimized: bool = False
    icon_path: str | None = None
    monitor_index: int | None = None


class WindowEnumerator:
    """Enumerate visible windows and capture window previews or full images."""

    def get_all_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        hwnds: list[int] = []

        def _enum_callback(hwnd: int, _lparam: Any) -> bool:
            hwnds.append(hwnd)
            return True

        win32gui.EnumWindows(_enum_callback, None)

        for hwnd in hwnds:
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    continue

                title = (win32gui.GetWindowText(hwnd) or "").strip()
                if not title:
                    continue

                if title.lower() == "signverify pro":
                    continue

                if win32gui.GetParent(hwnd) != 0:
                    continue

                class_name = win32gui.GetClassName(hwnd)
                if class_name == "Shell_TrayWnd":
                    continue

                exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                if exstyle & win32con.WS_EX_TOOLWINDOW:
                    continue

                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                width = int(right - left)
                height = int(bottom - top)
                if width < 100 or height < 100:
                    continue

                process_id = int(win32process.GetWindowThreadProcessId(hwnd)[1])
                process_name, icon_path = self._resolve_process_details(process_id)
                is_minimized = bool(win32gui.IsIconic(hwnd))

                windows.append(
                    WindowInfo(
                        hwnd=int(hwnd),
                        title=title,
                        process_name=process_name,
                        process_id=process_id,
                        rect=(int(left), int(top), int(right), int(bottom)),
                        width=width,
                        height=height,
                        thumbnail=None,
                        is_minimized=is_minimized,
                        icon_path=icon_path,
                    )
                )
            except Exception:
                continue

        windows.sort(key=lambda item: item.title.lower())
        return self._build_screen_entries() + windows

    def capture_window_thumbnail(
        self,
        window_info: WindowInfo,
        thumb_width: int = 280,
        thumb_height: int = 160,
    ) -> Image.Image:
        if window_info.hwnd < 0:
            image = self._capture_screen_entry(window_info)
            return self._fit_to_canvas(image, thumb_width, thumb_height)

        if not win32gui.IsWindow(window_info.hwnd):
            return self.create_placeholder_thumbnail(
                "Preview unavailable",
                thumb_width,
                thumb_height,
            )

        restored_for_capture = False
        elevated_error = False
        black_frame_detected = False

        try:
            if win32gui.IsIconic(window_info.hwnd):
                try:
                    win32gui.ShowWindow(window_info.hwnd, win32con.SW_RESTORE)
                    restored_for_capture = True
                    time.sleep(0.2)
                except Exception:
                    restored_for_capture = False

            rect = win32gui.GetWindowRect(window_info.hwnd)
            image = self._capture_window_via_printwindow(window_info.hwnd, rect)

            if self._is_black_image(image):
                black_frame_detected = True
                image = self._capture_window_via_mss(rect)

            return self._fit_to_canvas(image, thumb_width, thumb_height)
        except Exception as exc:
            message = str(exc).lower()
            if "access is denied" in message or "permission" in message:
                elevated_error = True

            try:
                rect = win32gui.GetWindowRect(window_info.hwnd)
                fallback = self._capture_window_via_mss(rect)
                return self._fit_to_canvas(fallback, thumb_width, thumb_height)
            except Exception:
                if elevated_error:
                    return self.create_placeholder_thumbnail(
                        "Preview unavailable\n(elevated process)",
                        thumb_width,
                        thumb_height,
                    )
                if black_frame_detected:
                    return self.create_placeholder_thumbnail(
                        "Preview unavailable\n(hardware accelerated window)",
                        thumb_width,
                        thumb_height,
                    )
                return self.create_placeholder_thumbnail(
                    "Preview unavailable",
                    thumb_width,
                    thumb_height,
                )
        finally:
            if restored_for_capture:
                try:
                    win32gui.ShowWindow(window_info.hwnd, win32con.SW_MINIMIZE)
                except Exception:
                    pass

    def capture_window_full(self, window_info: WindowInfo) -> Image.Image:
        if window_info.hwnd < 0:
            return self._capture_screen_entry(window_info)

        if not win32gui.IsWindow(window_info.hwnd):
            raise RuntimeError(WINDOW_CLOSED_SENTINEL)

        rect = win32gui.GetWindowRect(window_info.hwnd)

        try:
            image = self._capture_window_via_printwindow(window_info.hwnd, rect)
            if self._is_black_image(image):
                image = self._capture_window_via_mss(rect)
            return image
        except Exception:
            return self._capture_window_via_mss(rect)

    def get_process_icon(self, window_info: WindowInfo) -> QIcon | None:
        if window_info.hwnd < 0:
            return None

        try:
            icon_handle = win32gui.SendMessage(window_info.hwnd, win32con.WM_GETICON, win32con.ICON_SMALL2, 0)
            if not icon_handle:
                icon_handle = win32gui.SendMessage(
                    window_info.hwnd,
                    win32con.WM_GETICON,
                    win32con.ICON_SMALL,
                    0,
                )
            if not icon_handle:
                icon_handle = win32gui.SendMessage(window_info.hwnd, win32con.WM_GETICON, win32con.ICON_BIG, 0)
            if not icon_handle:
                icon_handle = win32gui.GetClassLong(window_info.hwnd, win32con.GCL_HICON)

            if icon_handle:
                try:
                    from PyQt6.QtWinExtras import QtWin

                    pixmap = QtWin.fromHICON(int(icon_handle))
                    if not pixmap.isNull():
                        return QIcon(pixmap)
                except Exception:
                    pass

            if window_info.icon_path and Path(window_info.icon_path).exists():
                icon = QIcon(str(window_info.icon_path))
                if not icon.isNull():
                    return icon
        except Exception:
            return None

        return None

    def create_placeholder_thumbnail(
        self,
        message: str,
        width: int = 280,
        height: int = 160,
    ) -> Image.Image:
        image = Image.new("RGB", (int(width), int(height)), color=(232, 234, 237))
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        text = message.strip() or "Preview unavailable"
        text_bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center")
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]
        x = max(0, (width - text_w) // 2)
        y = max(0, (height - text_h) // 2)
        draw.multiline_text((x, y), text, fill=(84, 99, 122), font=font, align="center")

        return image

    def _build_screen_entries(self) -> list[WindowInfo]:
        screens: list[WindowInfo] = []
        monitors = win32api.EnumDisplayMonitors()

        if not monitors:
            screens.append(
                WindowInfo(
                    hwnd=-1,
                    title="Entire Screen (Monitor 1)",
                    process_name="Screen",
                    process_id=0,
                    rect=(0, 0, 1920, 1080),
                    width=1920,
                    height=1080,
                    is_minimized=False,
                    icon_path=None,
                    monitor_index=1,
                )
            )
            return screens

        monitor_entries: list[WindowInfo] = []
        for index, monitor in enumerate(monitors, start=1):
            rect = monitor[2]
            left, top, right, bottom = int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])
            width = max(1, right - left)
            height = max(1, bottom - top)
            hwnd = -1 if index == 1 else -(100 + index)

            monitor_entries.append(
                WindowInfo(
                    hwnd=hwnd,
                    title=f"Entire Screen (Monitor {index})",
                    process_name="Screen",
                    process_id=0,
                    rect=(left, top, right, bottom),
                    width=width,
                    height=height,
                    is_minimized=False,
                    icon_path=None,
                    monitor_index=index,
                )
            )

        screens.append(monitor_entries[0])

        if len(monitors) > 1:
            all_left = min(monitor[2][0] for monitor in monitors)
            all_top = min(monitor[2][1] for monitor in monitors)
            all_right = max(monitor[2][2] for monitor in monitors)
            all_bottom = max(monitor[2][3] for monitor in monitors)
            screens.append(
                WindowInfo(
                    hwnd=-2,
                    title="Entire Screen (All Monitors)",
                    process_name="Screen",
                    process_id=0,
                    rect=(int(all_left), int(all_top), int(all_right), int(all_bottom)),
                    width=int(all_right - all_left),
                    height=int(all_bottom - all_top),
                    is_minimized=False,
                    icon_path=None,
                    monitor_index=0,
                )
            )

            screens.extend(monitor_entries[1:])

        return screens

    def _resolve_process_details(self, process_id: int) -> tuple[str, str | None]:
        process_name = "Unknown Process"
        icon_path: str | None = None

        try:
            proc = psutil.Process(process_id)
            process_name = proc.name() or process_name
            try:
                exe_path = proc.exe()
                if exe_path:
                    icon_path = exe_path
            except Exception:
                pass
        except Exception:
            pass

        process_handle = None
        try:
            process_handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_LIMITED_INFORMATION | win32con.PROCESS_VM_READ,
                False,
                process_id,
            )
            module_path = win32process.GetModuleFileNameEx(process_handle, 0)
            if module_path:
                if process_name == "Unknown Process":
                    process_name = Path(module_path).name
                if icon_path is None:
                    icon_path = module_path
        except Exception:
            pass
        finally:
            if process_handle:
                try:
                    win32api.CloseHandle(process_handle)
                except Exception:
                    pass

        return process_name, icon_path

    def _capture_screen_entry(self, window_info: WindowInfo) -> Image.Image:
        with mss.mss() as sct:
            if window_info.hwnd == -2 and len(sct.monitors) > 1:
                monitor = sct.monitors[0]
            elif window_info.monitor_index is not None and 0 <= window_info.monitor_index < len(sct.monitors):
                monitor = sct.monitors[window_info.monitor_index]
            elif len(sct.monitors) > 1:
                monitor = sct.monitors[1]
            else:
                monitor = sct.monitors[0]

            shot = sct.grab(monitor)
            return Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)

    def _capture_window_via_printwindow(
        self,
        hwnd: int,
        rect: tuple[int, int, int, int],
    ) -> Image.Image:
        width = max(1, int(rect[2] - rect[0]))
        height = max(1, int(rect[3] - rect[1]))

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        save_bitmap = win32ui.CreateBitmap()

        try:
            save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(save_bitmap)

            result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), PW_RENDERFULLCONTENT)
            if result != 1:
                raise RuntimeError("PrintWindow failed")

            bmp_info = save_bitmap.GetInfo()
            bmp_bytes = save_bitmap.GetBitmapBits(True)
            image = Image.frombuffer(
                "RGB",
                (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                bmp_bytes,
                "raw",
                "BGRX",
                0,
                1,
            )
            return image.copy()
        finally:
            win32gui.DeleteObject(save_bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)

    def _capture_window_via_mss(self, rect: tuple[int, int, int, int]) -> Image.Image:
        left, top, right, bottom = [int(value) for value in rect]
        width = max(1, right - left)
        height = max(1, bottom - top)

        with mss.mss() as sct:
            shot = sct.grab(
                {
                    "left": left,
                    "top": top,
                    "width": width,
                    "height": height,
                }
            )
            return Image.frombytes("RGB", (shot.width, shot.height), shot.rgb)

    def _is_black_image(self, image: Image.Image) -> bool:
        array = np.array(image.convert("RGB"), dtype=np.uint8)
        return float(np.mean(array)) < 5.0

    def _fit_to_canvas(self, image: Image.Image, width: int, height: int) -> Image.Image:
        canvas = Image.new("RGB", (int(width), int(height)), color=(255, 255, 255))
        resized = image.convert("RGB")
        resized.thumbnail((int(width), int(height)), Image.Resampling.LANCZOS)

        x = (int(width) - resized.width) // 2
        y = (int(height) - resized.height) // 2
        canvas.paste(resized, (x, y))
        return canvas
