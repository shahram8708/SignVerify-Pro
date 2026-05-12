"""Window picker dialog with live thumbnail previews for Mode A capture."""

from __future__ import annotations

from typing import Literal

from PIL import Image
from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import C_BLUE, C_BORDER, C_GREY_LT, C_NAVY, C_TEXT_PRIMARY, C_TEXT_SECONDARY, C_WHITE
from services.window_enumerator import WindowInfo
from ui.widgets.window_card_widget import WindowCardWidget
from utils.window_thumbnail_worker import WindowThumbnailWorker


class WindowPickerDialog(QDialog):
    """Modal dialog that lets users pick an app window or screen before capture."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.selected_window: WindowInfo | None = None
        self.window_list: list[WindowInfo] = []
        self.thumbnail_worker: WindowThumbnailWorker | None = None
        self.card_widgets: dict[int, WindowCardWidget] = {}

        self._active_tab: Literal["all", "screens", "windows"] = "all"
        self._search_text = ""
        self._loading_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._loading_index = 0

        self._refresh_frames = ["↻", "↺"]
        self._refresh_index = 0

        self.setWindowTitle("Select a Window or Screen to Capture")
        self.setModal(True)
        self.resize(900, 620)
        self.setMinimumSize(700, 500)
        self.setStyleSheet(f"background: {C_WHITE};")

        self._build_ui()
        self._center_on_parent()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(self)
        header.setFixedHeight(56)
        header.setStyleSheet(f"background: {C_NAVY};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(8)

        icon_label = QLabel("🪟", header)
        icon_label.setFixedSize(16, 16)
        icon_label.setStyleSheet(f"color: {C_WHITE};")

        title_label = QLabel("Select Application Window", header)
        title_label.setStyleSheet(f"color: {C_WHITE}; font-size: 12pt; font-weight: 700;")

        self.search_input = QLineEdit(header)
        self.search_input.setPlaceholderText("Search windows...")
        self.search_input.setEnabled(False)
        self.search_input.setFixedWidth(220)
        self.search_input.setStyleSheet(
            f"QLineEdit {{"
            f"background: {C_WHITE};"
            f"border: 1px solid {C_BORDER};"
            "border-radius: 4px;"
            "padding: 6px 10px;"
            "}"
        )
        self.search_input.textChanged.connect(self._filter_cards)

        header_layout.addWidget(icon_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.search_input)

        tabs = QFrame(self)
        tabs.setFixedHeight(40)
        tabs.setStyleSheet(
            f"background: #F8F9FA;"
            f"border-bottom: 1px solid {C_BORDER};"
        )
        tabs_layout = QHBoxLayout(tabs)
        tabs_layout.setContentsMargins(16, 0, 16, 0)
        tabs_layout.setSpacing(10)

        self.screens_tab_button = QPushButton("🖥 Screens", tabs)
        self.screens_tab_button.setFlat(True)
        self.screens_tab_button.clicked.connect(lambda: self._set_tab("screens"))

        self.windows_tab_button = QPushButton("🪟 Application Windows", tabs)
        self.windows_tab_button.setFlat(True)
        self.windows_tab_button.clicked.connect(lambda: self._set_tab("windows"))

        self.all_tab_button = QPushButton("📋 All", tabs)
        self.all_tab_button.setFlat(True)
        self.all_tab_button.clicked.connect(lambda: self._set_tab("all"))

        tabs_layout.addWidget(self.screens_tab_button)
        tabs_layout.addWidget(self.windows_tab_button)
        tabs_layout.addWidget(self.all_tab_button)
        tabs_layout.addStretch(1)

        self._set_tab("all")

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.grid_host = QWidget(self.scroll_area)
        self.grid_layout = QGridLayout(self.grid_host)
        self.grid_layout.setContentsMargins(16, 16, 16, 16)
        self.grid_layout.setHorizontalSpacing(12)
        self.grid_layout.setVerticalSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.grid_host)

        self.loading_label = QLabel("Loading windows...", self.grid_host)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet(f"font-size: 10pt; color: {C_TEXT_SECONDARY};")

        self.empty_label = QLabel("", self.grid_host)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"font-size: 10pt; color: {C_TEXT_SECONDARY};")
        self.empty_label.setVisible(False)

        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(100)
        self.loading_timer.timeout.connect(self._animate_loading)

        bottom = QFrame(self)
        bottom.setFixedHeight(64)
        bottom.setStyleSheet(
            f"background: {C_GREY_LT};"
            f"border-top: 1px solid {C_BORDER};"
        )
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 0, 16, 0)
        bottom_layout.setSpacing(10)

        self.selected_title_label = QLabel(
            "No window selected. click a window above to select it",
            bottom,
        )
        self.selected_title_label.setStyleSheet(
            f"color: {C_TEXT_SECONDARY}; font-style: italic; font-size: 9pt;"
        )

        self.selected_meta_label = QLabel("", bottom)
        self.selected_meta_label.setStyleSheet(f"color: {C_TEXT_SECONDARY}; font-size: 8pt;")

        selected_wrap = QVBoxLayout()
        selected_wrap.setContentsMargins(0, 0, 0, 0)
        selected_wrap.setSpacing(2)
        selected_wrap.addWidget(self.selected_title_label)
        selected_wrap.addWidget(self.selected_meta_label)

        self.refresh_button = QPushButton("↻ Refresh", bottom)
        self.refresh_button.setObjectName("secondary")
        self.refresh_button.setMinimumWidth(90)
        self.refresh_button.clicked.connect(self._refresh_windows)

        self.capture_button = QPushButton("📷 Capture", bottom)
        self.capture_button.setEnabled(False)
        self.capture_button.setMinimumWidth(140)
        self.capture_button.setFixedHeight(40)
        self.capture_button.setStyleSheet(
            f"QPushButton {{ background: {C_BLUE}; color: {C_WHITE}; font-size: 12pt; font-weight: 700; border: none; border-radius: 6px; }}"
            f"QPushButton:disabled {{ background: #D1D5DB; color: #9CA3AF; }}"
        )
        self.capture_button.clicked.connect(self.accept)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(220)
        self.refresh_timer.timeout.connect(self._animate_refresh_button)

        bottom_layout.addLayout(selected_wrap)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self.refresh_button)
        bottom_layout.addWidget(self.capture_button)

        root.addWidget(header)
        root.addWidget(tabs)
        root.addWidget(self.scroll_area, 1)
        root.addWidget(bottom)

        self._show_loading_state()

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(parent.frameGeometry().center())
        self.move(frame.topLeft())

    def _show_loading_state(self) -> None:
        self.loading_label.setVisible(True)
        self.empty_label.setVisible(False)
        self.loading_label.setText("Loading windows...")
        self.loading_timer.start()

        self._clear_grid_layout()
        self.grid_layout.addWidget(self.loading_label, 0, 0, 1, 3)

    def _animate_loading(self) -> None:
        marker = self._loading_frames[self._loading_index]
        self._loading_index = (self._loading_index + 1) % len(self._loading_frames)
        self.loading_label.setText(f"{marker} Loading windows...")

    def _set_tab(self, tab_name: Literal["all", "screens", "windows"]) -> None:
        self._active_tab = tab_name

        buttons = [
            (self.screens_tab_button, tab_name == "screens"),
            (self.windows_tab_button, tab_name == "windows"),
            (self.all_tab_button, tab_name == "all"),
        ]

        for button, active in buttons:
            if active:
                button.setStyleSheet(
                    f"QPushButton {{"
                    "background: transparent;"
                    f"color: {C_TEXT_PRIMARY};"
                    "border: none;"
                    f"border-bottom: 2px solid {C_BLUE};"
                    "font-size: 9pt;"
                    "font-weight: 700;"
                    "padding: 6px 2px;"
                    "}"
                )
            else:
                button.setStyleSheet(
                    f"QPushButton {{"
                    "background: transparent;"
                    f"color: {C_TEXT_SECONDARY};"
                    "border: none;"
                    "font-size: 9pt;"
                    "font-weight: 600;"
                    "padding: 6px 2px;"
                    "}"
                )

        self._apply_filters_and_layout()

    def _refresh_windows(self) -> None:
        self._stop_worker(disconnect_signals=True)

        self.selected_window = None
        self.capture_button.setEnabled(False)
        self.selected_title_label.setText("No window selected. click a window above to select it")
        self.selected_title_label.setStyleSheet(
            f"color: {C_TEXT_SECONDARY}; font-style: italic; font-size: 9pt;"
        )
        self.selected_meta_label.setText("")

        self.search_input.clear()
        self.search_input.setEnabled(False)
        for card in self.card_widgets.values():
            card.deleteLater()
        self.card_widgets.clear()

        self._show_loading_state()
        self._start_worker()

    def _start_worker(self) -> None:
        self.thumbnail_worker = WindowThumbnailWorker(thumb_width=280, thumb_height=160)
        self.thumbnail_worker.windows_discovered.connect(self._on_windows_discovered)
        self.thumbnail_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.thumbnail_worker.refresh_complete.connect(self._on_refresh_complete)
        self.thumbnail_worker.error_occurred.connect(self._on_worker_error)

        self.refresh_button.setEnabled(False)
        self.refresh_timer.start()
        self.thumbnail_worker.start()

    def _stop_worker(self, disconnect_signals: bool) -> None:
        if self.thumbnail_worker is None:
            return

        worker = self.thumbnail_worker

        try:
            worker.stop()
            if disconnect_signals:
                try:
                    worker.windows_discovered.disconnect(self._on_windows_discovered)
                except Exception:
                    pass
                try:
                    worker.thumbnail_ready.disconnect(self._on_thumbnail_ready)
                except Exception:
                    pass
                try:
                    worker.refresh_complete.disconnect(self._on_refresh_complete)
                except Exception:
                    pass
                try:
                    worker.error_occurred.disconnect(self._on_worker_error)
                except Exception:
                    pass

            if worker.isRunning():
                worker.wait(3000)
        finally:
            worker.deleteLater()
            self.thumbnail_worker = None

    @pyqtSlot(list)
    def _on_windows_discovered(self, window_list: list) -> None:
        self.window_list = window_list
        self.card_widgets.clear()

        self.loading_timer.stop()
        self.loading_label.setVisible(False)
        self.empty_label.setVisible(False)

        self._clear_grid_layout()

        for window_info in self.window_list:
            card = WindowCardWidget(window_info, self.grid_host, dialog=self)
            card.selected.connect(self._on_card_selected)
            self.card_widgets[int(window_info.hwnd)] = card

        self.search_input.setEnabled(True)
        self._apply_filters_and_layout()

    @pyqtSlot(int, object)
    def _on_thumbnail_ready(self, hwnd: int, thumbnail: Image.Image) -> None:
        for window_info in self.window_list:
            if int(window_info.hwnd) == int(hwnd):
                window_info.thumbnail = thumbnail
                break

        card = self.card_widgets.get(int(hwnd))
        if card is not None:
            card.set_thumbnail(thumbnail)

    @pyqtSlot()
    def _on_refresh_complete(self) -> None:
        self.refresh_timer.stop()
        self.refresh_button.setText("↻ Refresh")
        self.refresh_button.setEnabled(True)

    @pyqtSlot(str)
    def _on_worker_error(self, message: str) -> None:
        self.refresh_timer.stop()
        self.refresh_button.setText("↻ Refresh")
        self.refresh_button.setEnabled(True)

        self.loading_timer.stop()
        self.loading_label.setVisible(False)
        self.empty_label.setText(f"Could not load windows: {message}")
        self.empty_label.setVisible(True)

    @pyqtSlot(int)
    def _on_card_selected(self, hwnd: int) -> None:
        for card_hwnd, card in self.card_widgets.items():
            card.set_selected(card_hwnd == int(hwnd))

        self.selected_window = next((item for item in self.window_list if int(item.hwnd) == int(hwnd)), None)

        if self.selected_window is None:
            self.capture_button.setEnabled(False)
            self.selected_title_label.setText("No window selected. click a window above to select it")
            self.selected_title_label.setStyleSheet(
                f"color: {C_TEXT_SECONDARY}; font-style: italic; font-size: 9pt;"
            )
            self.selected_meta_label.setText("")
            return

        title = self.selected_window.title or "Untitled"
        if len(title) > 60:
            title = title[:57] + "..."

        self.selected_title_label.setText(f"Selected: {title}")
        self.selected_title_label.setStyleSheet(
            f"color: {C_TEXT_PRIMARY}; font-size: 9pt; font-weight: 700;"
        )
        self.selected_meta_label.setText(
            f"{self.selected_window.process_name} · {self.selected_window.width}×{self.selected_window.height}px"
        )
        self.capture_button.setEnabled(True)

    @pyqtSlot(str)
    def _filter_cards(self, search_text: str) -> None:
        self._search_text = (search_text or "").strip().lower()
        self._apply_filters_and_layout()

    def _window_matches_filters(self, window: WindowInfo) -> bool:
        tab_ok = True
        if self._active_tab == "screens":
            tab_ok = window.hwnd < 0
        elif self._active_tab == "windows":
            tab_ok = window.hwnd >= 0

        if not tab_ok:
            return False

        if self._search_text and self._search_text not in (window.title or "").lower():
            return False

        return True

    def _apply_filters_and_layout(self) -> None:
        if not self.card_widgets:
            return

        self._clear_grid_layout()

        visible_cards: list[WindowCardWidget] = []
        ordered = sorted(self.card_widgets.items(), key=lambda pair: self._window_order_key(pair[0]))

        for hwnd, card in ordered:
            window = next((item for item in self.window_list if int(item.hwnd) == int(hwnd)), None)
            if window is None:
                card.setVisible(False)
                continue

            should_show = self._window_matches_filters(window)
            card.setVisible(should_show)
            if should_show:
                visible_cards.append(card)

        if not visible_cards:
            if self._active_tab == "windows" and not any(item.hwnd >= 0 for item in self.window_list):
                message = "No applications are currently open"
            elif self._search_text:
                message = "No windows match your search"
            else:
                message = "No windows available"

            self.empty_label.setText(message)
            self.empty_label.setVisible(True)
            self.grid_layout.addWidget(self.empty_label, 0, 0, 1, 3)
            return

        self.empty_label.setVisible(False)

        columns = max(1, min(3, (self.scroll_area.viewport().width() - 48) // (280 + 12)))
        for index, card in enumerate(visible_cards):
            row = index // columns
            col = index % columns
            self.grid_layout.addWidget(card, row, col)

        self.grid_layout.setColumnStretch(columns, 1)

    def _window_order_key(self, hwnd: int) -> tuple[int, int, str]:
        window = next((item for item in self.window_list if int(item.hwnd) == int(hwnd)), None)
        if window is None:
            return (2, 0, "")

        if window.hwnd < 0:
            return (0, abs(window.hwnd), window.title.lower())
        return (1, 0, window.title.lower())

    def _clear_grid_layout(self) -> None:
        while self.grid_layout.count() > 0:
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            if widget in (self.loading_label, self.empty_label):
                widget.setParent(self.grid_host)
                continue
            widget.setParent(self.grid_host)

    def _animate_refresh_button(self) -> None:
        icon = self._refresh_frames[self._refresh_index]
        self._refresh_index = (self._refresh_index + 1) % len(self._refresh_frames)
        self.refresh_button.setText(f"{icon} Refresh")

    def get_selected_window(self) -> WindowInfo | None:
        return self.selected_window

    def showEvent(self, event: QEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_windows()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_filters_and_layout()

    def closeEvent(self, event: QEvent) -> None:  # noqa: N802
        self.loading_timer.stop()
        self.refresh_timer.stop()
        self._stop_worker(disconnect_signals=True)
        super().closeEvent(event)
