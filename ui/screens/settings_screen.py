"""Settings screen implementation for SignVerify Pro."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

import cv2
import mss
import torch
from PyQt6.QtCore import QThread, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QImage, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
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

logger = get_logger(__name__)
BUILD_TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ModelTestWorker(QThread):
    completed = pyqtSignal(bool, str)

    def run(self) -> None:
        try:
            from services.local_model_service import LocalModelService

            ready, message = LocalModelService().ping()
            if ready:
                self.completed.emit(True, "✓ Model loaded and ready")
            else:
                self.completed.emit(False, f"✗ {message}")
        except Exception as exc:
            self.completed.emit(False, f"✗ Model test failed: {exc}")


class SettingsScreen(BaseScreen):
    def __init__(self, parent=None) -> None:
        self.controller = settings_controller
        self.licence_manager = LicenceManager.get_instance()
        self._model_test_worker: ModelTestWorker | None = None
        super().__init__(parent)

    def _build_ui(self) -> None:
        title = QLabel("Settings")
        title.setStyleSheet(f"font-size: 20pt; font-weight: 700; color: {C_NAVY};")
        self.content_layout.addWidget(title)

        self.tabs = QTabWidget(self)
        self.content_layout.addWidget(self.tabs)

        self._build_model_tab()
        self._build_capture_tab()
        self._build_camera_tab()
        self._build_detection_tab()
        self._build_about_tab()

    def _build_model_tab(self) -> None:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        status_heading = QLabel("Local Model Status")
        status_heading.setStyleSheet("font-weight: 700; font-size: 12pt;")

        self.model_status_frame = QFrame(tab)
        self.model_status_layout = QVBoxLayout(self.model_status_frame)
        self.model_status_layout.setContentsMargins(12, 10, 12, 10)
        self.model_status_layout.setSpacing(6)

        self.model_status_label = QLabel("✗ Model Not Found", self.model_status_frame)
        self.model_status_label.setStyleSheet("font-size: 10pt; font-weight: 700;")

        self.model_arch_label = QLabel("Architecture: -", self.model_status_frame)
        self.model_eer_label = QLabel("Trained EER: -", self.model_status_frame)
        self.model_date_label = QLabel("Training Date: -", self.model_status_frame)
        self.model_datasets_label = QLabel("Datasets Used: -", self.model_status_frame)
        self.model_pairs_label = QLabel("Total Training Pairs: -", self.model_status_frame)
        self.model_device_label = QLabel("Inference Device: -", self.model_status_frame)

        for item in [
            self.model_arch_label,
            self.model_eer_label,
            self.model_date_label,
            self.model_datasets_label,
            self.model_pairs_label,
            self.model_device_label,
        ]:
            item.setStyleSheet("font-size: 9pt;")

        self.model_status_layout.addWidget(self.model_status_label)
        self.model_status_layout.addWidget(self.model_arch_label)
        self.model_status_layout.addWidget(self.model_eer_label)
        self.model_status_layout.addWidget(self.model_date_label)
        self.model_status_layout.addWidget(self.model_datasets_label)
        self.model_status_layout.addWidget(self.model_pairs_label)
        self.model_status_layout.addWidget(self.model_device_label)

        path_heading = QLabel("Model File Path")
        path_heading.setStyleSheet("font-weight: 700;")

        path_row = QHBoxLayout()
        path_row.setSpacing(10)

        self.model_path_input = QLineEdit(tab)
        self.model_path_input.setPlaceholderText("Select local .pth model file path")

        browse_btn = QPushButton("Browse", tab)
        browse_btn.setObjectName("secondary")
        browse_btn.clicked.connect(self._browse_model_path)

        self.test_model_btn = QPushButton("Test Model", tab)
        self.test_model_btn.setStyleSheet(f"QPushButton {{ background: {C_BLUE}; color: white; }}")
        self.test_model_btn.clicked.connect(self._test_model)

        path_row.addWidget(self.model_path_input, 1)
        path_row.addWidget(browse_btn)
        path_row.addWidget(self.test_model_btn)

        self.model_test_status_label = QLabel("", tab)
        self.model_test_status_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        training_heading = QLabel("Training Instructions")
        training_heading.setStyleSheet("font-weight: 700;")

        instructions_box = QFrame(tab)
        instructions_box.setStyleSheet(
            "background: #E3F2FD; border: 1px solid #90CAF9; border-radius: 8px;"
        )
        instructions_layout = QVBoxLayout(instructions_box)
        instructions_layout.setContentsMargins(10, 10, 10, 10)
        instructions_layout.setSpacing(5)

        instructions_text = QLabel(
            "To train the model:\n"
            "1. Ensure datasets are downloaded (run model_training/dataset_downloader.py)\n"
            "2. Run model_training/train.py\n"
            "3. Training takes 8 to 24 hours on GPU or 3 to 7 days on CPU\n"
            "4. The trained model will be saved automatically"
        )
        instructions_text.setWordWrap(True)
        instructions_text.setStyleSheet("font-size: 9pt; color: #0A1628;")

        open_training_btn = QPushButton("Open Training Folder", tab)
        open_training_btn.setObjectName("secondary")
        open_training_btn.clicked.connect(self._open_training_folder)

        instructions_layout.addWidget(instructions_text)
        instructions_layout.addWidget(open_training_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        inference_heading = QLabel("Inference Device")
        inference_heading.setStyleSheet("font-weight: 700;")

        self.inference_device_combo = QComboBox(tab)
        self.inference_device_combo.addItem("Auto-detect (recommended)", "auto")
        self.inference_device_combo.addItem("CPU only", "cpu")
        self.inference_device_combo.addItem("CUDA GPU", "cuda")

        cuda_text = "CUDA devices: None detected"
        if torch.cuda.is_available():
            cuda_devices = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
            cuda_text = "CUDA devices: " + ", ".join(cuda_devices)

        self.cuda_devices_label = QLabel(cuda_text, tab)
        self.cuda_devices_label.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")
        self.cuda_devices_label.setWordWrap(True)

        self.save_model_settings_btn = QPushButton("Save Model Settings", tab)
        self.save_model_settings_btn.clicked.connect(self._save_model_settings)

        layout.addWidget(status_heading)
        layout.addWidget(self.model_status_frame)
        layout.addWidget(path_heading)
        layout.addLayout(path_row)
        layout.addWidget(self.model_test_status_label)
        layout.addWidget(training_heading)
        layout.addWidget(instructions_box)
        layout.addWidget(inference_heading)
        layout.addWidget(self.inference_device_combo)
        layout.addWidget(self.cuda_devices_label)
        layout.addWidget(self.save_model_settings_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

        self.tabs.addTab(tab, "🤖 Model Settings")

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

    def _get_inference_device_label(self, preference: str) -> str:
        normalized = str(preference or "auto").strip().lower()
        if normalized == "cpu":
            return "CPU"
        if normalized == "cuda":
            if torch.cuda.is_available():
                return f"CUDA - {torch.cuda.get_device_name(0)}"
            return "CPU (CUDA unavailable)"
        if torch.cuda.is_available():
            return f"CUDA - {torch.cuda.get_device_name(0)}"
        return "CPU"

    def _refresh_model_status_panel(self) -> None:
        from services.local_model_service import LocalModelService

        service = LocalModelService()
        ready, message = service.ping()

        metadata = {}
        try:
            metadata = service.get_model_info()
        except Exception:
            metadata = {}

        if ready:
            self.model_status_frame.setStyleSheet(
                "background: #E8F5E9; border: 1px solid #81C784; border-radius: 8px;"
            )
            self.model_status_label.setText("✓ Model Ready")
            self.model_status_label.setStyleSheet("font-size: 10pt; font-weight: 700; color: #2E7D32;")
        else:
            self.model_status_frame.setStyleSheet(
                "background: #FFEBEE; border: 1px solid #EF9A9A; border-radius: 8px;"
            )
            self.model_status_label.setText("✗ Model Not Found")
            self.model_status_label.setStyleSheet("font-size: 10pt; font-weight: 700; color: #C62828;")

        architecture = str(metadata.get("model_architecture", "SiameseResNet50-v1.0") or "SiameseResNet50-v1.0")

        eer_value = metadata.get("training_eer")
        eer_text = "-"
        if eer_value is not None:
            try:
                numeric = float(eer_value)
                if numeric <= 1.0:
                    numeric *= 100.0
                eer_text = f"{numeric:.2f}%"
            except (TypeError, ValueError):
                eer_text = str(eer_value)

        training_date = str(metadata.get("training_date", "-") or "-")
        datasets_used = metadata.get("datasets_used", [])
        if isinstance(datasets_used, list):
            datasets_text = f"{len(datasets_used)} datasets"
        else:
            datasets_text = "-"

        total_pairs = metadata.get("total_training_pairs", 0)
        try:
            total_pairs_text = f"{int(total_pairs):,}"
        except (TypeError, ValueError):
            total_pairs_text = "-"

        preference = self.controller.get_inference_device()
        device_label = self._get_inference_device_label(preference)

        self.model_arch_label.setText(f"Architecture: {architecture}")
        self.model_eer_label.setText(f"Trained EER: {eer_text}")
        self.model_date_label.setText(f"Training Date: {training_date}")
        self.model_datasets_label.setText(f"Datasets Used: {datasets_text}")
        self.model_pairs_label.setText(f"Total Training Pairs: {total_pairs_text}")
        self.model_device_label.setText(f"Inference Device: {device_label}")

        if ready:
            self.model_test_status_label.setText("✓ Model loaded and ready")
            self.model_test_status_label.setStyleSheet("color: #2E7D32; font-size: 9pt; font-weight: 600;")
        else:
            self.model_test_status_label.setText(f"✗ {message}")
            self.model_test_status_label.setStyleSheet("color: #C62828; font-size: 9pt; font-weight: 600;")

    def _browse_model_path(self) -> None:
        current = self.model_path_input.text().strip() or str(Path.cwd())
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Model File",
            current,
            "PyTorch Model Files (*.pth *.pt)",
        )
        if selected_path:
            self.model_path_input.setText(selected_path)

    def _test_model(self) -> None:
        self.test_model_btn.setEnabled(False)
        self.test_model_btn.setText("Testing...")
        self.model_test_status_label.setText("Testing model...")
        self.model_test_status_label.setStyleSheet(f"color: {C_TEXT_SECONDARY}; font-size: 9pt;")

        self._model_test_worker = ModelTestWorker()
        self._model_test_worker.completed.connect(self._handle_model_test_result)
        self._model_test_worker.start()

    def _handle_model_test_result(self, success: bool, message: str) -> None:
        color = C_SUCCESS if success else "#C62828"
        self.model_test_status_label.setText(message)
        self.model_test_status_label.setStyleSheet(f"color: {color}; font-size: 9pt; font-weight: 600;")

        self.test_model_btn.setEnabled(True)
        self.test_model_btn.setText("Test Model")

        if self._model_test_worker is not None:
            self._model_test_worker.deleteLater()
            self._model_test_worker = None

        self._refresh_model_status_panel()
        self._notify_main_window_status_refresh()

    def _open_training_folder(self) -> None:
        training_dir = Path(__file__).resolve().parents[2] / "model_training"
        training_dir.mkdir(parents=True, exist_ok=True)

        try:
            if os.name == "nt":
                os.startfile(str(training_dir))
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(training_dir)))
        except Exception as exc:
            self.show_error("Open Folder Failed", str(exc))

    def _save_model_settings(self) -> None:
        model_path = self.model_path_input.text().strip()
        if not model_path:
            self.show_error("Missing Model Path", "Please select a model file path.")
            return

        inference_device = str(self.inference_device_combo.currentData() or "auto")

        try:
            self.controller.set_model_path(model_path)
            self.controller.set_inference_device(inference_device)
            self._flash_saved(self.save_model_settings_btn, "Save Model Settings")
            self._refresh_model_status_panel()
            self._notify_main_window_status_refresh()
        except Exception as exc:
            logger.exception("Failed to save model settings")
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
        except Exception:
            logger.exception("Failed to enumerate monitors")
            self.monitor_selector.addItem("Primary Monitor", 1)

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
        if hasattr(window, "update_model_banner"):
            window.update_model_banner()
        if hasattr(window, "update_api_banner"):
            window.update_api_banner()

    def on_show(self, **kwargs) -> None:
        _ = kwargs
        logger.info("Settings screen shown")

        self.model_path_input.setText(self.controller.get_model_path())

        current_device = self.controller.get_inference_device()
        idx = self.inference_device_combo.findData(current_device)
        self.inference_device_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self._refresh_model_status_panel()

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
