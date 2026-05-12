"""Settings screen implementation for SignVerify Pro."""

from __future__ import annotations

from datetime import datetime
from urllib import error, request

import cv2
import mss
from PyQt6.QtCore import QThread, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QImage, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_NAME,
    APP_VERSION,
    C_AMBER_BG,
    C_BLUE,
    C_GOLD,
    C_NAVY,
    C_SUCCESS,
    C_TEXT_SECONDARY,
)
from controllers.settings_controller import settings_controller
from ui.base_screen import BaseScreen
from utils.licence_manager import LicenceManager
from utils.logger import get_logger
from utils.validators import validate_api_key

logger = get_logger(__name__)
BUILD_TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class APIConnectionWorker(QThread):
    completed = pyqtSignal(bool, str)

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self.api_key = api_key

    def run(self) -> None:
        if not self.api_key:
            self.completed.emit(False, "✗ API key is required")
            return

        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
        try:
            req = request.Request(url, method="GET")
            with request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    self.completed.emit(True, "✓ Connection successful")
                else:
                    self.completed.emit(False, "✗ Invalid API key")
        except error.HTTPError as exc:
            if exc.code in {400, 401, 403}:
                self.completed.emit(False, "✗ Invalid API key")
            else:
                self.completed.emit(False, f"✗ Connection failed ({exc.code})")
        except error.URLError:
            self.completed.emit(False, "✗ Network error")
        except Exception:
            self.completed.emit(False, "✗ Connection test failed")


class SettingsScreen(BaseScreen):
    def __init__(self, parent=None) -> None:
        self.controller = settings_controller
        self.licence_manager = LicenceManager.get_instance()
        self._api_worker: APIConnectionWorker | None = None
        super().__init__(parent)

    def _build_ui(self) -> None:
        title = QLabel("Settings")
        title.setStyleSheet(f"font-size: 20pt; font-weight: 700; color: {C_NAVY};")
        self.content_layout.addWidget(title)

        self.tabs = QTabWidget(self)
        self.content_layout.addWidget(self.tabs)

        self._build_api_tab()
        self._build_capture_tab()
        self._build_camera_tab()
        self._build_detection_tab()
        self._build_about_tab()

    def _build_api_tab(self) -> None:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel("Key")
        heading.setStyleSheet("font-weight: 700;")

        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.api_key_input = QLineEdit(tab)
        self.api_key_input.setObjectName("api_key_input")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter your Gemini API key (AIza...)")

        self.toggle_api_visibility_btn = QPushButton("Show", tab)
        self.toggle_api_visibility_btn.setObjectName("secondary")
        self.toggle_api_visibility_btn.clicked.connect(self._toggle_api_visibility)

        input_row.addWidget(self.api_key_input)
        input_row.addWidget(self.toggle_api_visibility_btn)

        caption = QLabel("Get your free API key at Google AI Studio (aistudio.google.com)")
        caption.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.test_connection_btn = QPushButton("Test Connection", tab)
        self.test_connection_btn.clicked.connect(self._test_api_connection)

        self.connection_status_label = QLabel("", tab)
        self.connection_status_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        action_row.addWidget(self.test_connection_btn)
        action_row.addWidget(self.connection_status_label, stretch=1)

        model_label = QLabel("Model")
        model_label.setStyleSheet("font-weight: 700;")

        self.model_selector = QComboBox(tab)
        self.model_selector.addItems(["gemini-2.5-flash", "gemini-1.5-flash"])

        self.save_api_btn = QPushButton("Save API Settings", tab)
        self.save_api_btn.clicked.connect(self._save_api_settings)

        layout.addWidget(heading)
        layout.addLayout(input_row)
        layout.addWidget(caption)
        layout.addLayout(action_row)
        layout.addWidget(model_label)
        layout.addWidget(self.model_selector)
        layout.addWidget(self.save_api_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

        self.tabs.addTab(tab, "API Settings")

    def _build_capture_tab(self) -> None:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        heading = QLabel("Screen Capture Mode")
        heading.setStyleSheet("font-weight: 700;")

        self.capture_mode_group = QButtonGroup(self)
        self.capture_radio_full = QRadioButton("Full Screen", tab)
        self.capture_radio_active = QRadioButton("Active Window", tab)
        self.capture_radio_custom = QRadioButton("Custom Region", tab)

        self.capture_mode_group.addButton(self.capture_radio_full)
        self.capture_mode_group.addButton(self.capture_radio_active)
        self.capture_mode_group.addButton(self.capture_radio_custom)

        self.capture_mode_map = {
            "full_screen": self.capture_radio_full,
            "active_window": self.capture_radio_active,
            "custom_region": self.capture_radio_custom,
        }

        monitor_label = QLabel("Monitor Selection")
        monitor_label.setStyleSheet("font-weight: 700;")

        self.monitor_selector = QComboBox(tab)
        self._populate_monitors()

        self.save_capture_btn = QPushButton("Save Capture Settings", tab)
        self.save_capture_btn.clicked.connect(self._save_capture_settings)

        layout.addWidget(heading)
        layout.addWidget(self.capture_radio_full)
        layout.addWidget(self.capture_radio_active)
        layout.addWidget(self.capture_radio_custom)
        layout.addSpacing(8)
        layout.addWidget(monitor_label)
        layout.addWidget(self.monitor_selector)
        layout.addWidget(self.save_capture_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

        self.tabs.addTab(tab, "Capture Settings")

    def _build_camera_tab(self) -> None:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        camera_index_label = QLabel("Camera Device Index")
        camera_index_label.setStyleSheet("font-weight: 700;")

        self.camera_index_spin = QSpinBox(tab)
        self.camera_index_spin.setRange(0, 10)
        self.camera_index_spin.setValue(0)

        camera_resolution_label = QLabel("Capture Resolution")
        camera_resolution_label.setStyleSheet("font-weight: 700;")

        self.camera_resolution_combo = QComboBox(tab)
        self.camera_resolution_combo.addItems(["640×480", "1280×720", "1920×1080"])

        form.addWidget(camera_index_label, 0, 0)
        form.addWidget(self.camera_index_spin, 0, 1)
        form.addWidget(camera_resolution_label, 1, 0)
        form.addWidget(self.camera_resolution_combo, 1, 1)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)

        self.test_camera_btn = QPushButton("Test Camera", tab)
        self.test_camera_btn.setObjectName("secondary")
        self.test_camera_btn.clicked.connect(self._test_camera)

        self.save_camera_btn = QPushButton("Save Camera Settings", tab)
        self.save_camera_btn.clicked.connect(self._save_camera_settings)

        buttons_row.addWidget(self.test_camera_btn)
        buttons_row.addWidget(self.save_camera_btn)
        buttons_row.addStretch(1)

        layout.addLayout(form)
        layout.addLayout(buttons_row)
        layout.addStretch(1)

        self.tabs.addTab(tab, "Camera Settings")

    def _build_detection_tab(self) -> None:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        sensitivity_label = QLabel("Detection Sensitivity")
        sensitivity_label.setStyleSheet("font-weight: 700;")

        sensitivity_row = QHBoxLayout()
        sensitivity_row.setSpacing(10)

        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal, tab)
        self.sensitivity_slider.setRange(1, 10)
        self.sensitivity_slider.setValue(5)

        self.sensitivity_value_label = QLabel("5", tab)
        self.sensitivity_value_label.setFixedWidth(30)
        self.sensitivity_slider.valueChanged.connect(
            lambda value: self.sensitivity_value_label.setText(str(value))
        )

        sensitivity_note = QLabel(
            "Lower values reduce false detections. Higher values detect more candidate strokes."
        )
        sensitivity_note.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        sensitivity_row.addWidget(self.sensitivity_slider)
        sensitivity_row.addWidget(self.sensitivity_value_label)

        min_area_label = QLabel("Minimum Signature Area (px²)")
        min_area_label.setStyleSheet("font-weight: 700;")
        self.min_area_spin = QSpinBox(tab)
        self.min_area_spin.setRange(100, 5000)
        self.min_area_spin.setValue(800)
        min_area_note = QLabel("Rejects tiny artifacts that are unlikely to be valid signatures.")
        min_area_note.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        aspect_min_label = QLabel("Aspect Ratio Min")
        aspect_min_label.setStyleSheet("font-weight: 700;")
        self.aspect_min_spin = QDoubleSpinBox(tab)
        self.aspect_min_spin.setRange(0.5, 5.0)
        self.aspect_min_spin.setSingleStep(0.1)
        self.aspect_min_spin.setValue(1.5)
        aspect_min_note = QLabel("Defines the lowest width to height shape accepted as signature like.")
        aspect_min_note.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        aspect_max_label = QLabel("Aspect Ratio Max")
        aspect_max_label.setStyleSheet("font-weight: 700;")
        self.aspect_max_spin = QDoubleSpinBox(tab)
        self.aspect_max_spin.setRange(1.0, 15.0)
        self.aspect_max_spin.setSingleStep(0.5)
        self.aspect_max_spin.setValue(8.0)
        aspect_max_note = QLabel("Prevents extremely long blobs from being treated as valid signatures.")
        aspect_max_note.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        self.save_detection_btn = QPushButton("Save Detection Settings", tab)
        self.save_detection_btn.clicked.connect(self._save_detection_settings)

        layout.addWidget(sensitivity_label)
        layout.addLayout(sensitivity_row)
        layout.addWidget(sensitivity_note)
        layout.addWidget(min_area_label)
        layout.addWidget(self.min_area_spin)
        layout.addWidget(min_area_note)
        layout.addWidget(aspect_min_label)
        layout.addWidget(self.aspect_min_spin)
        layout.addWidget(aspect_min_note)
        layout.addWidget(aspect_max_label)
        layout.addWidget(self.aspect_max_spin)
        layout.addWidget(aspect_max_note)
        layout.addWidget(self.save_detection_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

        self.tabs.addTab(tab, "Detection Settings")

    def _build_about_tab(self) -> None:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        app_name_label = QLabel(APP_NAME)
        app_name_label.setStyleSheet(f"font-size: 20pt; font-weight: 700; color: {C_NAVY};")

        version_label = QLabel(f"Version {APP_VERSION}")
        subtitle = QLabel("AI-Powered Signature Verification System")
        subtitle.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        divider = QFrame(tab)
        divider.setFrameShape(QFrame.Shape.HLine)

        tier = self.licence_manager.get_tier().upper()
        badge_color = self._get_licence_badge_color(tier)

        self.licence_badge = QLabel(tier)
        self.licence_badge.setStyleSheet(
            f"background: {badge_color}; color: white; padding: 4px 10px; border-radius: 10px; font-weight: 700;"
        )

        tier_row = QHBoxLayout()
        tier_row.addWidget(QLabel("Licence Tier:"))
        tier_row.addWidget(self.licence_badge)
        tier_row.addStretch(1)

        table = QTableWidget(4, 3, tab)
        table.setHorizontalHeaderLabels(["Feature", "Free", "Professional"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)

        rows = [
            ("Verifications per day", "10", "Unlimited"),
            ("PDF Export", "✗", "✓"),
            ("CSV Export", "✗", "✓"),
            ("All 3 Modes", "✓", "✓"),
        ]

        for row_index, row_data in enumerate(rows):
            for col_index, value in enumerate(row_data):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_index == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row_index, col_index, item)

        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        docs_button = QPushButton("Documentation", tab)
        docs_button.setObjectName("secondary")
        docs_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://docs.signverifypro.com"))
        )

        self.upgrade_licence_btn = QPushButton(tab)
        self.upgrade_licence_btn.clicked.connect(self._upgrade_to_professional)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        actions_row.addWidget(docs_button)
        actions_row.addWidget(self.upgrade_licence_btn)
        actions_row.addStretch(1)

        build_label = QLabel(f"Build Timestamp: {BUILD_TIMESTAMP}")
        build_label.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        layout.addWidget(app_name_label)
        layout.addWidget(version_label)
        layout.addWidget(subtitle)
        layout.addWidget(divider)
        layout.addLayout(tier_row)
        layout.addWidget(table)
        layout.addLayout(actions_row)
        layout.addWidget(build_label)
        layout.addStretch(1)

        self._refresh_licence_ui()
        self.tabs.addTab(tab, "About")

    def _get_licence_badge_color(self, tier: str) -> str:
        return {
            LicenceManager.FREE: C_GOLD,
            LicenceManager.PROFESSIONAL: C_BLUE,
            LicenceManager.ENTERPRISE: C_NAVY,
        }.get(tier.upper(), C_AMBER_BG)

    def _refresh_licence_ui(self) -> None:
        tier = self.licence_manager.get_tier().upper()

        badge_color = self._get_licence_badge_color(tier)
        self.licence_badge.setText(tier)
        self.licence_badge.setStyleSheet(
            f"background: {badge_color}; color: white; padding: 4px 10px; border-radius: 10px; font-weight: 700;"
        )

        if tier == LicenceManager.FREE:
            self.upgrade_licence_btn.setEnabled(True)
            self.upgrade_licence_btn.setText("Convert to Professional")
        elif tier == LicenceManager.PROFESSIONAL:
            self.upgrade_licence_btn.setEnabled(False)
            self.upgrade_licence_btn.setText("Professional Active")
        else:
            self.upgrade_licence_btn.setEnabled(False)
            self.upgrade_licence_btn.setText("Enterprise Managed")

    def _upgrade_to_professional(self) -> None:
        current_tier = self.licence_manager.get_tier().upper()
        if current_tier != LicenceManager.FREE:
            self._refresh_licence_ui()
            self.show_success("Licence Status", f"Current tier is {current_tier}")
            return

        decision = QMessageBox.question(
            self,
            "Confirm Upgrade",
            "Upgrade this installation from Free to Professional now?\n\n"
            "This will unlock unlimited daily verifications and export features immediately.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if decision != QMessageBox.StandardButton.Yes:
            return

        self.upgrade_licence_btn.setEnabled(False)
        self.upgrade_licence_btn.setText("Upgrading...")

        success, message = self.licence_manager.upgrade_to_professional()
        self._refresh_licence_ui()

        if success:
            self._notify_main_window_status_refresh()
            self.show_success("Upgrade Complete", message)
            return

        self.show_error("Upgrade Failed", message)

    def _toggle_api_visibility(self) -> None:
        if self.api_key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_api_visibility_btn.setText("Hide")
        else:
            self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_api_visibility_btn.setText("Show")

    def _test_api_connection(self) -> None:
        api_key = self.api_key_input.text().strip()
        valid, message = validate_api_key(api_key)
        if not valid:
            self.connection_status_label.setText(f"✗ {message}")
            self.connection_status_label.setStyleSheet("color: #C62828; font-size: 9pt;")
            return

        self.connection_status_label.setText("Testing connection...")
        self.connection_status_label.setStyleSheet(f"color: {C_TEXT_SECONDARY}; font-size: 9pt;")
        self.test_connection_btn.setEnabled(False)
        self.test_connection_btn.setText("Testing...")

        self._api_worker = APIConnectionWorker(api_key)
        self._api_worker.completed.connect(self._handle_api_test_result)
        self._api_worker.start()

    def _handle_api_test_result(self, success: bool, message: str) -> None:
        color = C_SUCCESS if success else "#C62828"
        self.connection_status_label.setText(message)
        self.connection_status_label.setStyleSheet(f"color: {color}; font-size: 9pt; font-weight: 600;")

        self.test_connection_btn.setEnabled(True)
        self.test_connection_btn.setText("Test Connection")

        if self._api_worker is not None:
            self._api_worker.deleteLater()
            self._api_worker = None

    def _save_api_settings(self) -> None:
        api_key = self.api_key_input.text().strip()
        valid, message = validate_api_key(api_key)
        if not valid:
            self.show_error("Invalid API Key", message)
            return

        try:
            self.controller.set_api_key(api_key)
            self.controller.set("gemini_model", self.model_selector.currentText())
            self.show_success("Settings Saved", "API settings were saved successfully")
            self._flash_saved(self.save_api_btn, "Save API Settings")
            self._notify_main_window_status_refresh()
        except Exception as exc:
            logger.exception("Failed to save API settings")
            self.show_error("Save Failed", str(exc))

    def _populate_monitors(self) -> None:
        self.monitor_selector.clear()
        try:
            with mss.mss() as sct:
                monitors = sct.monitors[1:] if len(sct.monitors) > 1 else sct.monitors
                if not monitors:
                    self.monitor_selector.addItem("Primary Monitor", 1)
                    return

                for index, monitor in enumerate(monitors, start=1):
                    width = monitor.get("width", 0)
                    height = monitor.get("height", 0)
                    left = monitor.get("left", 0)
                    top = monitor.get("top", 0)
                    label = f"Monitor {index} ({width}x{height}) [{left},{top}]"
                    self.monitor_selector.addItem(label, index)
        except Exception as exc:
            logger.exception("Failed to enumerate monitors")
            self.monitor_selector.addItem("Primary Monitor", 1)
            self.connection_status_label.setText(f"Monitor scan warning: {exc}")

    def _save_capture_settings(self) -> None:
        mode = "full_screen"
        if self.capture_radio_active.isChecked():
            mode = "active_window"
        elif self.capture_radio_custom.isChecked():
            mode = "custom_region"

        monitor_index = int(self.monitor_selector.currentData() or 1)

        try:
            self.controller.set("capture_mode", mode)
            self.controller.set("capture_monitor_index", str(monitor_index))
            self._flash_saved(self.save_capture_btn, "Save Capture Settings")
        except Exception as exc:
            logger.exception("Failed to save capture settings")
            self.show_error("Save Failed", str(exc))

    def _parse_resolution(self) -> tuple[int, int]:
        text = self.camera_resolution_combo.currentText().replace("×", "x")
        parts = text.split("x")
        if len(parts) != 2:
            return 1280, 720
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return 1280, 720

    def _test_camera(self) -> None:
        device_index = self.camera_index_spin.value()
        width, height = self._parse_resolution()

        camera = cv2.VideoCapture(device_index)
        try:
            if not camera.isOpened():
                self.show_error("Camera Error", "Camera not found")
                return

            camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            ok, frame = camera.read()
            if not ok or frame is None:
                self.show_error("Camera Error", "Unable to capture frame from camera")
                return

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_height, frame_width, channels = rgb_frame.shape
            image = QImage(
                rgb_frame.data,
                frame_width,
                frame_height,
                channels * frame_width,
                QImage.Format.Format_RGB888,
            )

            preview = QLabel()
            preview.setPixmap(
                QPixmap.fromImage(image).scaled(
                    640,
                    360,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

            dialog = QDialog(self)
            dialog.setWindowTitle("Camera Test")
            dialog_layout = QVBoxLayout(dialog)
            dialog_layout.addWidget(preview)

            close_button = QPushButton("Close", dialog)
            close_button.setObjectName("secondary")
            close_button.clicked.connect(dialog.accept)
            dialog_layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)

            dialog.exec()
        except Exception as exc:
            logger.exception("Camera test failed")
            self.show_error("Camera Error", str(exc))
        finally:
            camera.release()

    def _save_camera_settings(self) -> None:
        try:
            self.controller.set("camera_index", str(self.camera_index_spin.value()))
            self.controller.set("camera_resolution", self.camera_resolution_combo.currentText())
            self._flash_saved(self.save_camera_btn, "Save Camera Settings")
        except Exception as exc:
            logger.exception("Failed to save camera settings")
            self.show_error("Save Failed", str(exc))

    def _save_detection_settings(self) -> None:
        sensitivity = self.sensitivity_slider.value() / 10.0
        try:
            self.controller.set("detection_sensitivity", str(sensitivity))
            self.controller.set("minimum_signature_area", str(self.min_area_spin.value()))
            self.controller.set("aspect_ratio_min", str(self.aspect_min_spin.value()))
            self.controller.set("aspect_ratio_max", str(self.aspect_max_spin.value()))
            self._flash_saved(self.save_detection_btn, "Save Detection Settings")
        except Exception as exc:
            logger.exception("Failed to save detection settings")
            self.show_error("Save Failed", str(exc))

    def _flash_saved(self, button: QPushButton, original_text: str) -> None:
        original_style = button.styleSheet()
        button.setText("✓ Saved!")
        button.setStyleSheet(f"background: {C_SUCCESS}; color: white;")

        def _restore() -> None:
            button.setText(original_text)
            button.setStyleSheet(original_style)

        QTimer.singleShot(2000, _restore)

    def _notify_main_window_status_refresh(self) -> None:
        window = self.window()
        if hasattr(window, "refresh_status_indicators"):
            window.refresh_status_indicators()
        if hasattr(window, "update_api_banner"):
            window.update_api_banner()

    def on_show(self, **kwargs) -> None:
        _ = kwargs
        logger.info("Settings screen shown")

        self.api_key_input.setText(self.controller.get_api_key())

        model_name = str(self.controller.get("gemini_model", "gemini-2.5-flash") or "gemini-2.5-flash")
        model_index = self.model_selector.findText(model_name)
        self.model_selector.setCurrentIndex(model_index if model_index >= 0 else 0)

        self._populate_monitors()
        capture_mode = self.controller.get_capture_mode()
        self.capture_mode_map.get(capture_mode, self.capture_radio_full).setChecked(True)

        monitor_setting = self.controller.get("capture_monitor_index", "1")
        try:
            monitor_value = int(monitor_setting)
        except (TypeError, ValueError):
            monitor_value = 1
        monitor_index = self.monitor_selector.findData(monitor_value)
        self.monitor_selector.setCurrentIndex(monitor_index if monitor_index >= 0 else 0)

        self.camera_index_spin.setValue(self.controller.get_camera_index())

        resolution = str(self.controller.get("camera_resolution", "1280×720") or "1280×720")
        resolution_index = self.camera_resolution_combo.findText(resolution)
        self.camera_resolution_combo.setCurrentIndex(resolution_index if resolution_index >= 0 else 1)

        sensitivity = self.controller.get_detection_sensitivity()
        slider_value = max(1, min(10, int(round(sensitivity * 10))))
        self.sensitivity_slider.setValue(slider_value)

        try:
            self.min_area_spin.setValue(int(self.controller.get("minimum_signature_area", 800)))
        except (TypeError, ValueError):
            self.min_area_spin.setValue(800)

        try:
            self.aspect_min_spin.setValue(float(self.controller.get("aspect_ratio_min", 1.5)))
        except (TypeError, ValueError):
            self.aspect_min_spin.setValue(1.5)

        try:
            self.aspect_max_spin.setValue(float(self.controller.get("aspect_ratio_max", 8.0)))
        except (TypeError, ValueError):
            self.aspect_max_spin.setValue(8.0)

        self._refresh_licence_ui()
