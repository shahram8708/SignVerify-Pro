"""Mode B screen implementation for upload or camera verification."""

from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_DATA_DIR,
    C_BLUE,
    C_BORDER,
    C_DANGER,
    C_GOLD,
    C_GREY_LT,
    C_NAVY,
    C_SUCCESS,
    C_TEXT_PRIMARY,
    C_TEXT_SECONDARY,
    C_WHITE,
    resolve_signature_path,
)
from controllers.database_controller import database_controller
from controllers.navigation_controller import NavigationController
from controllers.verification_controller import VerificationController
from ui.base_screen import BaseScreen
from ui.dialogs.camera_dialog import CameraDialog
from ui.widgets.signature_preview_label import SignaturePreviewLabel
from utils.logger import get_logger
from utils.validators import validate_file_mime, validate_image_path

logger = get_logger(__name__)


class ModeBScreen(BaseScreen):
    """Mode B workflow: compare selected person with uploaded or captured signature."""

    def __init__(self, parent=None) -> None:
        self.person_id: int | None = None
        self.person_name: str | None = None
        self.person = None
        self.submitted_image_path: str | None = None
        self.capture_mode_used = "B_UPLOAD"
        self.gemini_worker = None
        self.reference_image_path: str = ""

        super().__init__(parent)

    def _build_ui(self) -> None:
        self.content_layout.setContentsMargins(18, 16, 18, 16)
        self.content_layout.setSpacing(12)

        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        title = QLabel("Mode B — Upload or Camera Verification", header)
        title.setStyleSheet(f"font-size: 20pt; font-weight: 700; color: {C_NAVY};")

        breadcrumb_row = QHBoxLayout()
        breadcrumb_row.setContentsMargins(0, 0, 0, 0)
        breadcrumb_row.setSpacing(8)

        back_link = QPushButton("← Back", header)
        back_link.setObjectName("secondary")
        back_link.clicked.connect(lambda: NavigationController.get_instance().navigate_to("verification"))

        breadcrumb = QLabel("Verification Hub → Mode B", header)
        breadcrumb.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        breadcrumb_row.addWidget(back_link)
        breadcrumb_row.addWidget(breadcrumb)
        breadcrumb_row.addStretch(1)

        header_layout.addWidget(title)
        header_layout.addLayout(breadcrumb_row)

        main = QWidget(self)
        main_layout = QHBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_panel = self._build_left_panel(main)
        self.right_panel = self._build_right_panel(main)

        main_layout.addWidget(self.left_panel)
        main_layout.addWidget(self.right_panel, 1)

        bottom_bar = QWidget(self)
        bottom_layout = QVBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        self.progress_label = QLabel("", bottom_bar)
        self.progress_label.setVisible(False)
        self.progress_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.verify_button = QPushButton("🔍 Verify Now", bottom_bar)
        self.verify_button.setEnabled(False)
        self.verify_button.setStyleSheet(
            f"QPushButton {{ background: {C_BLUE}; color: {C_WHITE}; min-height: 56px; font-size: 14pt; font-weight: 700; }}"
        )
        self.verify_button.clicked.connect(self._do_verify)

        bottom_layout.addWidget(self.progress_label)
        bottom_layout.addWidget(self.verify_button)

        self.content_layout.addWidget(header)
        self.content_layout.addWidget(main, 1)
        self.content_layout.addWidget(bottom_bar)

    def _build_left_panel(self, parent: QWidget) -> QWidget:
        panel = QFrame(parent)
        panel.setFixedWidth(340)
        panel.setStyleSheet(
            f"background: {C_GREY_LT}; border-right: 1px solid {C_BORDER};"
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("Reference Signature", panel)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 12pt; font-weight: 700; color: {C_NAVY};")

        subtitle = QLabel("Stored in database", panel)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        self.reference_preview = SignaturePreviewLabel(panel)
        self.reference_preview.setFixedHeight(120)
        self.reference_preview.setAcceptDrops(False)
        self.reference_preview.setCursor(Qt.CursorShape.ArrowCursor)

        self.person_name_label = QLabel("", panel)
        self.person_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.person_name_label.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        self.person_date_label = QLabel("", panel)
        self.person_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.person_date_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.reference_path_label = QLabel("", panel)
        self.reference_path_label.setWordWrap(True)
        self.reference_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reference_path_label.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        divider = QFrame(panel)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {C_BORDER};")

        quality_title = QLabel("📊 Reference Quality:", panel)
        quality_title.setStyleSheet(f"font-size: 9pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

        self.reference_quality_badge = QLabel("Not assessed", panel)
        self.reference_quality_badge.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border: 1px solid {C_BORDER}; border-radius: 8px; padding: 6px;"
        )

        change_person_button = QPushButton("🔄 Change Person", panel)
        change_person_button.setObjectName("secondary")
        change_person_button.clicked.connect(
            lambda: NavigationController.get_instance().navigate_to("verification")
        )

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.reference_preview)
        layout.addWidget(self.person_name_label)
        layout.addWidget(self.person_date_label)
        layout.addWidget(self.reference_path_label)
        layout.addWidget(divider)
        layout.addWidget(quality_title)
        layout.addWidget(self.reference_quality_badge)
        layout.addStretch(1)
        layout.addWidget(change_person_button)

        return panel

    def _build_right_panel(self, parent: QWidget) -> QWidget:
        panel = QWidget(parent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel("Submitted Signature", panel)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 12pt; font-weight: 700; color: {C_NAVY};")

        subtitle = QLabel("Upload or capture the signature to verify", panel)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        self.tabs = QTabWidget(panel)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        upload_tab = QWidget(panel)
        upload_layout = QVBoxLayout(upload_tab)
        upload_layout.setContentsMargins(10, 12, 10, 12)
        upload_layout.setSpacing(8)

        self.upload_preview = SignaturePreviewLabel(upload_tab)
        self.upload_preview.setFixedHeight(120)
        self.upload_preview.image_dropped.connect(self._on_upload_image_dropped)
        self.upload_preview.clicked.connect(self._browse_file)

        browse_button = QPushButton("📂 Browse Files", upload_tab)
        browse_button.setStyleSheet(f"QPushButton {{ background: {C_BLUE}; color: {C_WHITE}; font-weight: 700; }}")
        browse_button.clicked.connect(self._browse_file)

        self.upload_file_info_label = QLabel("", upload_tab)
        self.upload_file_info_label.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        self.upload_inline_error_label = QLabel("", upload_tab)
        self.upload_inline_error_label.setVisible(False)
        self.upload_inline_error_label.setStyleSheet(f"font-size: 8.5pt; color: {C_DANGER};")

        upload_layout.addWidget(self.upload_preview)
        upload_layout.addWidget(browse_button)
        upload_layout.addWidget(self.upload_file_info_label)
        upload_layout.addWidget(self.upload_inline_error_label)
        upload_layout.addStretch(1)

        camera_tab = QWidget(panel)
        camera_layout = QVBoxLayout(camera_tab)
        camera_layout.setContentsMargins(10, 12, 10, 12)
        camera_layout.setSpacing(8)

        self.camera_preview = SignaturePreviewLabel(camera_tab)
        self.camera_preview.setFixedHeight(120)
        self.camera_preview.setAcceptDrops(False)

        camera_button = QPushButton("📷 Open Camera", camera_tab)
        camera_button.setStyleSheet(f"QPushButton {{ background: {C_BLUE}; color: {C_WHITE}; font-weight: 700; }}")
        camera_button.clicked.connect(self._open_camera)

        camera_instruction = QLabel(
            "Hold the document to the camera and click Capture.",
            camera_tab,
        )
        camera_instruction.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        camera_layout.addWidget(self.camera_preview)
        camera_layout.addWidget(camera_button)
        camera_layout.addWidget(camera_instruction)
        camera_layout.addStretch(1)

        self.tabs.addTab(upload_tab, "📁 Upload File")
        self.tabs.addTab(camera_tab, "📷 Camera Capture")

        self.quality_section = QFrame(panel)
        self.quality_section.setVisible(False)
        self.quality_section.setStyleSheet(
            f"background: {C_WHITE}; border: 1px solid {C_BORDER}; border-radius: 8px;"
        )
        quality_layout = QVBoxLayout(self.quality_section)
        quality_layout.setContentsMargins(10, 10, 10, 10)
        quality_layout.setSpacing(8)

        quality_title = QLabel("📊 Submitted Image Quality:", self.quality_section)
        quality_title.setStyleSheet(f"font-size: 9pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

        badges_row = QHBoxLayout()
        badges_row.setSpacing(8)

        self.resolution_badge = QLabel("Resolution: -", self.quality_section)
        self.contrast_badge = QLabel("Contrast: -", self.quality_section)
        self.ink_badge = QLabel("Ink Coverage: -", self.quality_section)

        for badge in [self.resolution_badge, self.contrast_badge, self.ink_badge]:
            badge.setStyleSheet(
                f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 6px; padding: 6px;"
            )
            badges_row.addWidget(badge)

        self.overall_quality_badge = QLabel("Overall: -", self.quality_section)
        self.overall_quality_badge.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 8px; padding: 8px; font-weight: 700;"
        )

        quality_layout.addWidget(quality_title)
        quality_layout.addLayout(badges_row)
        quality_layout.addWidget(self.overall_quality_badge)

        self.comparison_section = QFrame(panel)
        self.comparison_section.setVisible(False)
        self.comparison_section.setStyleSheet(
            f"background: {C_WHITE}; border: 1px solid {C_BORDER}; border-radius: 8px;"
        )
        comparison_layout = QVBoxLayout(self.comparison_section)
        comparison_layout.setContentsMargins(10, 10, 10, 10)
        comparison_layout.setSpacing(8)

        ready_label = QLabel("Ready to Compare", self.comparison_section)
        ready_label.setStyleSheet(f"font-size: 12pt; font-weight: 700; color: {C_SUCCESS};")

        preview_row = QHBoxLayout()
        preview_row.setSpacing(8)

        self.comparison_reference_preview = SignaturePreviewLabel(self.comparison_section)
        self.comparison_reference_preview.setFixedSize(120, 60)
        self.comparison_reference_preview.setAcceptDrops(False)
        self.comparison_reference_preview.setCursor(Qt.CursorShape.ArrowCursor)

        vs_label = QLabel("vs", self.comparison_section)
        vs_label.setStyleSheet(f"font-size: 11pt; font-weight: 700; color: {C_TEXT_SECONDARY};")

        self.comparison_submitted_preview = SignaturePreviewLabel(self.comparison_section)
        self.comparison_submitted_preview.setFixedSize(120, 60)
        self.comparison_submitted_preview.setAcceptDrops(False)
        self.comparison_submitted_preview.setCursor(Qt.CursorShape.ArrowCursor)

        preview_row.addWidget(self.comparison_reference_preview)
        preview_row.addWidget(vs_label, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_row.addWidget(self.comparison_submitted_preview)

        comparison_layout.addWidget(ready_label)
        comparison_layout.addLayout(preview_row)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.tabs)
        layout.addWidget(self.quality_section)
        layout.addWidget(self.comparison_section)
        layout.addStretch(1)

        return panel

    def _quality_style(self, rating: str, prominent: bool = False) -> str:
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

        weight = "700" if prominent else "600"
        return f"background: {bg}; color: {fg}; border-radius: 8px; padding: 6px; font-weight: {weight};"

    def _set_inline_error(self, message: str) -> None:
        if message:
            self.upload_inline_error_label.setText(message)
            self.upload_inline_error_label.setVisible(True)
        else:
            self.upload_inline_error_label.setVisible(False)
            self.upload_inline_error_label.clear()

    def _file_info_text(self, path: str) -> str:
        path_obj = Path(path)
        size_kb = max(1, int(path_obj.stat().st_size / 1024))
        with Image.open(path_obj) as img:
            width, height = img.size
        return f"{path_obj.name} • {size_kb} KB • {width}x{height}"

    def _on_upload_image_dropped(self, path: str) -> None:
        valid, message = validate_image_path(path)
        if not valid:
            self._set_inline_error(message)
            self.upload_preview.clear_image()
            return

        valid_mime, mime_message = validate_file_mime(path)
        if not valid_mime:
            self._set_inline_error(mime_message)
            self.upload_preview.clear_image()
            return

        self._set_inline_error("")
        self._on_image_selected(path)

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Signature Image",
            "",
            "Image Files (*.png *.jpg *.jpeg)",
        )
        if not file_path:
            return

        valid, message = validate_image_path(file_path)
        if not valid:
            self._set_inline_error(message)
            return

        valid_mime, mime_message = validate_file_mime(file_path)
        if not valid_mime:
            self._set_inline_error(mime_message)
            return

        self._set_inline_error("")
        self._on_image_selected(file_path)

    def _open_camera(self) -> None:
        dialog = CameraDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        captured = dialog.get_captured_pil_image()
        if captured is None:
            QMessageBox.warning(self, "Camera", "No image was captured.")
            return

        temp_dir = APP_DATA_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"capture_{uuid.uuid4().hex[:12]}.png"
        captured.save(temp_path, format="PNG")

        self.capture_mode_used = "B_CAMERA"
        self._on_image_selected(str(temp_path), source="camera")

    def _on_image_selected(self, path: str, source: str | None = None) -> None:
        self.submitted_image_path = path

        if source == "camera":
            self.capture_mode_used = "B_CAMERA"
        elif self.tabs.currentIndex() == 0:
            self.capture_mode_used = "B_UPLOAD"

        self.upload_preview.set_image_from_path(path)
        self.camera_preview.set_image_from_path(path)

        try:
            self.upload_file_info_label.setText(self._file_info_text(path))
        except Exception:
            self.upload_file_info_label.setText(Path(path).name)

        from services.image_utils import ImageUtils

        quality = ImageUtils().assess_quality(path)

        self.resolution_badge.setText(f"Resolution: {quality.resolution}")
        self.contrast_badge.setText(f"Contrast: {quality.contrast}")
        self.ink_badge.setText(f"Ink Coverage: {quality.ink_coverage}")

        self.resolution_badge.setStyleSheet(self._quality_style(quality.resolution))
        self.contrast_badge.setStyleSheet(self._quality_style(quality.contrast))
        self.ink_badge.setStyleSheet(self._quality_style(quality.ink_coverage))

        self.overall_quality_badge.setText(f"Overall: {quality.overall}")
        self.overall_quality_badge.setStyleSheet(self._quality_style(quality.overall, prominent=True))

        tooltip = (
            f"Resolution: {quality.resolution_detail}\n"
            f"Contrast: {quality.contrast_detail}\n"
            f"Ink Coverage: {quality.ink_coverage_detail}"
        )
        self.overall_quality_badge.setToolTip(tooltip)

        self.quality_section.setVisible(True)
        self.comparison_section.setVisible(True)

        if self.reference_image_path and Path(self.reference_image_path).exists():
            self.comparison_reference_preview.set_image_from_path(self.reference_image_path)
        self.comparison_submitted_preview.set_image_from_path(path)

        self.verify_button.setEnabled(True)
        self.progress_label.setVisible(True)
        self.progress_label.setText(f"Selected: {Path(path).name}")
        logger.info("Mode B image selected: %s", path)

    def _load_person(self) -> None:
        if self.person_id is None:
            return

        self.person = database_controller.get_person_by_id(self.person_id)
        if self.person is None:
            self.show_error(
                "Person Not Found",
                "The selected person's record could not be found. Please go back and select again.",
            )
            NavigationController.get_instance().navigate_to("verification")
            return

        self.person_name = self.person.full_name
        self.reference_image_path = resolve_signature_path(self.person.signature_image_path)

        if Path(self.reference_image_path).exists():
            self.reference_preview.set_image_from_path(self.reference_image_path)
            self.comparison_reference_preview.set_image_from_path(self.reference_image_path)
        else:
            self.reference_preview.clear_image()

        self.person_name_label.setText(self.person.full_name)

        if self.person.created_at:
            self.person_date_label.setText(f"Added: {self.person.created_at.strftime('%d %b %Y')}")
        else:
            self.person_date_label.setText("Added: Unknown")

        path_display = self.reference_image_path
        if len(path_display) > 56:
            path_display = f"...{path_display[-53:]}"
        self.reference_path_label.setText(path_display)

        from services.image_utils import ImageUtils

        if Path(self.reference_image_path).exists():
            quality = ImageUtils().assess_quality(self.reference_image_path)
            self.reference_quality_badge.setText(f"{quality.overall} Quality")
            self.reference_quality_badge.setStyleSheet(self._quality_style(quality.overall, prominent=True))
            self.reference_quality_badge.setToolTip(
                f"Resolution: {quality.resolution_detail}\n"
                f"Contrast: {quality.contrast_detail}\n"
                f"Ink Coverage: {quality.ink_coverage_detail}"
            )
        else:
            self.reference_quality_badge.setText("Reference image not found")
            self.reference_quality_badge.setStyleSheet(
                f"background: {C_DANGER}; color: {C_WHITE}; border-radius: 8px; padding: 6px;"
            )

    def _do_verify(self) -> None:
        if not self.submitted_image_path:
            self.show_error("Missing Signature", "Please upload or capture a signature image first.")
            return

        if not Path(self.submitted_image_path).exists():
            self.show_error("Missing Signature", "The selected signature image file no longer exists.")
            return

        if self.person is None:
            self.show_error("Person Missing", "Please select a person before verification.")
            return

        reference_path = resolve_signature_path(self.person.signature_image_path)
        if not Path(reference_path).exists():
            self.show_error("Reference Missing", "The selected reference signature was not found.")
            return

        self.show_loading("Initiating AI verification...")
        try:
            controller = VerificationController()
            self.gemini_worker = controller.start_verification(
                reference_path,
                self.submitted_image_path,
                mode=self.capture_mode_used,
                person_id=self.person_id,
                person_name=self.person_name,
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
            logger.exception("Mode B verification start failed")
            self.show_error("Verification Failed", str(exc))

    def _on_verification_complete(self, result_dict: dict) -> None:
        self.hide_loading()

        if self.person is None:
            self.show_error("Verification", "Person context is missing.")
            return

        verification = VerificationController().save_verification_result(
            result_dict,
            mode=self.capture_mode_used,
            person_id=self.person_id,
            reference_image_path=resolve_signature_path(self.person.signature_image_path),
            submitted_image_path=self.submitted_image_path or "",
        )

        NavigationController.get_instance().navigate_to(
            "results",
            result_dict=result_dict,
            verification=verification,
            person=self.person,
        )

    def _on_verification_error(self, message: str) -> None:
        self.hide_loading()
        self.show_error("Verification Failed", message)

    def _on_tab_changed(self, index: int) -> None:
        if self.submitted_image_path and index == 0 and self.capture_mode_used != "B_CAMERA":
            self.capture_mode_used = "B_UPLOAD"

    def _reset_right_panel(self) -> None:
        self.submitted_image_path = None
        self.capture_mode_used = "B_UPLOAD"

        self.upload_preview.clear_image()
        self.camera_preview.clear_image()
        self.comparison_submitted_preview.clear_image()
        self.upload_file_info_label.clear()

        self._set_inline_error("")

        self.quality_section.setVisible(False)
        self.comparison_section.setVisible(False)

        self.resolution_badge.setText("Resolution: -")
        self.contrast_badge.setText("Contrast: -")
        self.ink_badge.setText("Ink Coverage: -")
        self.overall_quality_badge.setText("Overall: -")

        for badge in [self.resolution_badge, self.contrast_badge, self.ink_badge, self.overall_quality_badge]:
            badge.setStyleSheet(
                f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 8px; padding: 6px;"
            )

        self.progress_label.setVisible(False)
        self.progress_label.clear()
        self.verify_button.setEnabled(False)
        self.tabs.setCurrentIndex(0)

    def on_show(self, person_id: int = None, person_name: str = None, **kwargs) -> None:
        _ = kwargs
        logger.info("Mode B screen shown")

        self.hide_loading()
        self.person_id = int(person_id) if person_id is not None else None
        self.person_name = person_name
        self.person = None
        self.reference_image_path = ""

        self._reset_right_panel()

        if self.person_id is None:
            self.show_error("Person Required", "Please select a person before using Mode B.")
            NavigationController.get_instance().navigate_to("verification")
            return

        self._load_person()
