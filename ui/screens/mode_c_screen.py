"""Mode C screen implementation for ad-hoc two-signature comparison."""

from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_DATA_DIR,
    C_BLUE,
    C_BLUE_TINT_STRONG,
    C_BORDER,
    C_DANGER,
    C_GOLD,
    C_GREY_LT,
    C_INFO_BORDER,
    C_NAVY,
    C_SUCCESS,
    C_SUCCESS_BG,
    C_TEXT_PRIMARY,
    C_TEXT_SECONDARY,
    C_WHITE,
)
from controllers.navigation_controller import NavigationController
from controllers.verification_controller import VerificationController
from ui.base_screen import BaseScreen
from ui.dialogs.camera_dialog import CameraDialog
from ui.widgets.signature_preview_label import SignaturePreviewLabel
from utils.logger import get_logger
from utils.validators import validate_file_mime, validate_image_path

logger = get_logger(__name__)


class ModeCScreen(BaseScreen):
    """Mode C workflow: compare any two signature images without database lookup."""

    def __init__(self, parent=None) -> None:
        self.image_path_1: str | None = None
        self.image_path_2: str | None = None
        self.gemini_worker = None
        self.slot_widgets: dict[int, dict] = {}

        super().__init__(parent)

    def _build_ui(self) -> None:
        self.content_layout.setContentsMargins(18, 16, 18, 16)
        self.content_layout.setSpacing(12)

        title = QLabel("Mode C — Ad-Hoc Signature Comparison", self)
        title.setStyleSheet(f"font-size: 20pt; font-weight: 700; color: {C_NAVY};")

        subtitle = QLabel(
            "Compare any two signatures directly — no database lookup required.",
            self,
        )
        subtitle.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        info_box = QFrame(self)
        info_box.setStyleSheet(
            f"background: {C_BLUE_TINT_STRONG}; border: 1px solid {C_INFO_BORDER}; border-radius: 8px;"
        )
        info_layout = QHBoxLayout(info_box)
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(8)

        info_label = QLabel(
            "ℹ This mode is ideal for one-off forensic comparisons, legal disputes, or testing. "
            "Results are saved to your verification history.",
            info_box,
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_PRIMARY};")
        info_layout.addWidget(info_label)

        main = QWidget(self)
        main_layout = QHBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        slot_1_panel, _slot_1_preview = self._build_signature_slot(1)
        slot_2_panel, _slot_2_preview = self._build_signature_slot(2)

        center_divider = QWidget(main)
        center_divider.setFixedWidth(60)
        center_layout = QVBoxLayout(center_divider)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(4)
        center_layout.addStretch(1)

        icon_label = QLabel("⚖", center_divider)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 24pt;")

        vs_label = QLabel("VS", center_divider)
        vs_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vs_label.setStyleSheet(f"font-size: 10pt; font-weight: 700; color: {C_TEXT_SECONDARY};")

        center_layout.addWidget(icon_label)
        center_layout.addWidget(vs_label)
        center_layout.addStretch(1)

        main_layout.addWidget(slot_1_panel, 1)
        main_layout.addWidget(center_divider)
        main_layout.addWidget(slot_2_panel, 1)

        bottom = QWidget(self)
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        self.both_loaded_frame = QFrame(bottom)
        self.both_loaded_frame.setVisible(False)
        self.both_loaded_frame.setStyleSheet(
            f"background: {C_SUCCESS_BG}; border: 1px solid {C_SUCCESS}; border-radius: 8px;"
        )
        both_layout = QHBoxLayout(self.both_loaded_frame)
        both_layout.setContentsMargins(10, 8, 10, 8)

        both_label = QLabel("✓ Both signatures loaded — ready to compare", self.both_loaded_frame)
        both_label.setStyleSheet(f"font-size: 10pt; font-weight: 700; color: {C_SUCCESS};")
        both_layout.addWidget(both_label)

        self.compare_button = QPushButton("⚖ Compare Signatures", bottom)
        self.compare_button.setEnabled(False)
        self.compare_button.setStyleSheet(
            f"QPushButton {{ background: {C_BLUE}; color: {C_WHITE}; min-height: 56px; font-size: 14pt; font-weight: 700; }}"
        )
        self.compare_button.clicked.connect(self._do_verify)

        self.progress_label = QLabel("", bottom)
        self.progress_label.setVisible(False)
        self.progress_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        bottom_layout.addWidget(self.both_loaded_frame)
        bottom_layout.addWidget(self.compare_button)
        bottom_layout.addWidget(self.progress_label)

        self.content_layout.addWidget(title)
        self.content_layout.addWidget(subtitle)
        self.content_layout.addWidget(info_box)
        self.content_layout.addWidget(main, 1)
        self.content_layout.addWidget(bottom)

    def _build_signature_slot(self, slot_number: int) -> tuple[QFrame, SignaturePreviewLabel]:
        panel = QFrame(self)
        panel.setStyleSheet(
            f"background: {C_WHITE}; border: 1px solid {C_BORDER}; border-radius: 12px;"
        )

        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 25))
        panel.setGraphicsEffect(shadow)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        title = QLabel(f"Signature {slot_number}", panel)
        title.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        badge = QLabel("REFERENCE" if slot_number == 1 else "QUESTIONED", panel)
        badge_bg = C_BLUE if slot_number == 1 else C_GOLD
        badge_fg = C_WHITE if slot_number == 1 else C_NAVY
        badge.setStyleSheet(
            f"background: {badge_bg}; color: {badge_fg}; font-size: 8pt; font-weight: 700; border-radius: 10px; padding: 4px 10px;"
        )

        header_row.addWidget(title)
        header_row.addStretch(1)
        header_row.addWidget(badge)

        preview = SignaturePreviewLabel(panel)
        preview.setFixedHeight(130)
        preview.image_dropped.connect(
            lambda path, n=slot_number: self._on_dropped_image(n, path)
        )
        preview.clicked.connect(lambda n=slot_number: self._browse_image(n))

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        browse_btn = QPushButton("📁 Browse File", panel)
        browse_btn.setStyleSheet(f"QPushButton {{ background: {C_BLUE}; color: {C_WHITE}; font-weight: 700; }}")
        browse_btn.clicked.connect(lambda _checked=False, n=slot_number: self._browse_image(n))

        camera_btn = QPushButton("📷 Camera", panel)
        camera_btn.setObjectName("secondary")
        camera_btn.clicked.connect(lambda _checked=False, n=slot_number: self._capture_from_camera(n))

        button_row.addWidget(browse_btn)
        button_row.addWidget(camera_btn)

        info_label = QLabel("", panel)
        info_label.setVisible(False)
        info_label.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        error_label = QLabel("", panel)
        error_label.setVisible(False)
        error_label.setStyleSheet(f"font-size: 8.5pt; color: {C_DANGER};")

        clear_btn = QPushButton("✕ Clear", panel)
        clear_btn.setObjectName("secondary")
        clear_btn.setVisible(False)
        clear_btn.clicked.connect(lambda _checked=False, n=slot_number: self._clear_slot(n))

        quality_badge = QLabel("", panel)
        quality_badge.setVisible(False)
        quality_badge.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 8px; padding: 6px;"
        )

        status_label = QLabel("⭕ No image selected", panel)
        status_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        layout.addLayout(header_row)
        layout.addWidget(preview)
        layout.addLayout(button_row)
        layout.addWidget(info_label)
        layout.addWidget(error_label)
        layout.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(quality_badge)
        layout.addWidget(status_label)
        layout.addStretch(1)

        self.slot_widgets[slot_number] = {
            "preview": preview,
            "info_label": info_label,
            "error_label": error_label,
            "clear_btn": clear_btn,
            "quality_badge": quality_badge,
            "status_label": status_label,
        }

        return panel, preview

    def _set_slot_error(self, slot: int, message: str) -> None:
        widgets = self.slot_widgets[slot]
        error_label: QLabel = widgets["error_label"]
        if message:
            error_label.setText(message)
            error_label.setVisible(True)
        else:
            error_label.clear()
            error_label.setVisible(False)

    def _quality_style(self, rating: str) -> str:
        normalized = (rating or "").strip().lower()
        if normalized == "high":
            bg = C_SUCCESS
            fg = C_WHITE
        elif normalized == "medium":
            bg = C_GOLD
            fg = C_NAVY
        else:
            bg = C_DANGER
            fg = C_WHITE
        return f"background: {bg}; color: {fg}; border-radius: 8px; padding: 6px; font-weight: 700;"

    def _browse_image(self, slot: int) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Signature {slot}",
            "",
            "Image Files (*.png *.jpg *.jpeg)",
        )
        if not path:
            return

        valid, message = validate_image_path(path)
        if not valid:
            self._set_slot_error(slot, message)
            return

        valid_mime, mime_message = validate_file_mime(path)
        if not valid_mime:
            self._set_slot_error(slot, mime_message)
            return

        self._set_slot_error(slot, "")
        self._on_image_selected(slot, path)

    def _on_dropped_image(self, slot: int, path: str) -> None:
        valid, message = validate_image_path(path)
        if not valid:
            self._set_slot_error(slot, message)
            self.slot_widgets[slot]["preview"].clear_image()
            return

        valid_mime, mime_message = validate_file_mime(path)
        if not valid_mime:
            self._set_slot_error(slot, mime_message)
            self.slot_widgets[slot]["preview"].clear_image()
            return

        self._set_slot_error(slot, "")
        self._on_image_selected(slot, path)

    def _capture_from_camera(self, slot: int) -> None:
        dialog = CameraDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        captured = dialog.get_captured_pil_image()
        if captured is None:
            self._set_slot_error(slot, "No image captured from camera")
            return

        temp_dir = APP_DATA_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"capture_{uuid.uuid4().hex[:12]}.png"
        captured.save(temp_path, format="PNG")

        self._set_slot_error(slot, "")
        self._on_image_selected(slot, str(temp_path))

    def _file_info(self, path: str) -> str:
        path_obj = Path(path)
        size_kb = max(1, int(path_obj.stat().st_size / 1024))
        with Image.open(path_obj) as image:
            width, height = image.size
        return f"{path_obj.name} • {size_kb} KB • {width}x{height}"

    def _on_image_selected(self, slot: int, path: str) -> None:
        if slot == 1:
            self.image_path_1 = path
        else:
            self.image_path_2 = path

        widgets = self.slot_widgets[slot]
        preview: SignaturePreviewLabel = widgets["preview"]
        info_label: QLabel = widgets["info_label"]
        clear_btn: QPushButton = widgets["clear_btn"]
        quality_badge: QLabel = widgets["quality_badge"]
        status_label: QLabel = widgets["status_label"]

        preview.set_image_from_path(path)

        try:
            info_label.setText(self._file_info(path))
        except Exception:
            info_label.setText(Path(path).name)
        info_label.setVisible(True)

        from services.image_utils import ImageUtils

        quality = ImageUtils().assess_quality(path)
        quality_badge.setText(f"Overall Quality: {quality.overall}")
        quality_badge.setStyleSheet(self._quality_style(quality.overall))
        quality_badge.setToolTip(
            f"Resolution: {quality.resolution_detail}\n"
            f"Contrast: {quality.contrast_detail}\n"
            f"Ink Coverage: {quality.ink_coverage_detail}"
        )
        quality_badge.setVisible(True)

        clear_btn.setVisible(True)
        status_label.setText("✅ Ready")
        status_label.setStyleSheet(f"font-size: 9pt; color: {C_SUCCESS}; font-weight: 700;")

        self._set_slot_error(slot, "")
        self._update_compare_state()
        logger.info("Mode C slot %s image selected: %s", slot, path)

    def _clear_slot(self, slot: int) -> None:
        if slot == 1:
            self.image_path_1 = None
        else:
            self.image_path_2 = None

        widgets = self.slot_widgets[slot]
        widgets["preview"].clear_image()
        widgets["info_label"].clear()
        widgets["info_label"].setVisible(False)
        widgets["quality_badge"].clear()
        widgets["quality_badge"].setVisible(False)
        widgets["clear_btn"].setVisible(False)
        widgets["status_label"].setText("⭕ No image selected")
        widgets["status_label"].setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self._set_slot_error(slot, "")
        self._update_compare_state()

    def _update_compare_state(self) -> None:
        both_ready = bool(self.image_path_1 and self.image_path_2)
        self.both_loaded_frame.setVisible(both_ready)
        self.compare_button.setEnabled(both_ready)

    def _do_verify(self) -> None:
        if not self.image_path_1 or not self.image_path_2:
            self.show_error("Missing Images", "Please load both signatures before comparing.")
            return

        if not Path(self.image_path_1).exists() or not Path(self.image_path_2).exists():
            self.show_error("Missing File", "One or both selected image files could not be found.")
            return

        self.show_loading("Initiating ad-hoc forensic comparison...")
        try:
            controller = VerificationController()
            self.gemini_worker = controller.start_verification(
                self.image_path_1,
                self.image_path_2,
                mode="C_ADHOC",
                person_id=None,
                person_name=None,
                parent_widget=self,
            )
            if self.gemini_worker is None:
                self.hide_loading()
                return

            self.gemini_worker.result_ready.connect(self._on_verification_complete)
            self.gemini_worker.error_occurred.connect(self._on_verification_error)
            self.gemini_worker.progress_updated.connect(lambda msg: self.show_loading(msg))
            self.gemini_worker.start()
        except Exception as exc:
            self.hide_loading()
            logger.exception("Mode C verification start failed")
            self.show_error("Verification Failed", str(exc))

    def _on_verification_complete(self, result_dict: dict) -> None:
        self.hide_loading()

        verification = VerificationController().save_verification_result(
            result_dict,
            mode="C_ADHOC",
            person_id=None,
            reference_image_path=self.image_path_1 or "",
            submitted_image_path=self.image_path_2 or "",
        )

        NavigationController.get_instance().navigate_to(
            "results",
            result_dict=result_dict,
            verification=verification,
            person=None,
        )

    def _on_verification_error(self, message: str) -> None:
        self.hide_loading()
        self.show_error("Verification Failed", message)

    def _reset_slot(self, slot: int) -> None:
        widgets = self.slot_widgets[slot]
        widgets["preview"].clear_image()
        widgets["info_label"].clear()
        widgets["info_label"].setVisible(False)
        widgets["error_label"].clear()
        widgets["error_label"].setVisible(False)
        widgets["clear_btn"].setVisible(False)
        widgets["quality_badge"].clear()
        widgets["quality_badge"].setVisible(False)
        widgets["status_label"].setText("⭕ No image selected")
        widgets["status_label"].setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

    def on_show(self, **kwargs) -> None:
        _ = kwargs
        logger.info("Mode C screen shown")

        self.hide_loading()
        self.image_path_1 = None
        self.image_path_2 = None

        self._reset_slot(1)
        self._reset_slot(2)

        self.progress_label.clear()
        self.progress_label.setVisible(False)
        self.both_loaded_frame.setVisible(False)
        self.compare_button.setEnabled(False)
