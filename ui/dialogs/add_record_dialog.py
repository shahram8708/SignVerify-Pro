"""Dialog for creating and editing signature records."""

from __future__ import annotations

import io
import re
import uuid
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import APP_DATA_DIR, C_BLUE, C_DANGER, C_NAVY, C_TEXT_SECONDARY, SIGNATURES_STORAGE_DIR
from controllers.database_controller import database_controller
from models.person import Person
from ui.dialogs.camera_dialog import CameraDialog
from ui.widgets.signature_preview_label import SignaturePreviewLabel
from utils.logger import get_logger
from utils.validators import validate_file_mime, validate_image_path, validate_name

logger = get_logger(__name__)


class AddRecordDialog(QDialog):
    """Modal dialog for adding or editing a person record with signature image."""

    def __init__(self, parent=None, person: Person = None) -> None:
        super().__init__(parent)
        self.person = person
        self.is_edit_mode = person is not None

        self._upload_image_path: str | None = None
        self._camera_image_path: str | None = None
        self._loading_dialog: QProgressDialog | None = None

        self.setWindowTitle("Edit Signature Record" if self.is_edit_mode else "Add Signature Record")
        self.setModal(True)
        self.setFixedSize(520, 480)

        self._build_ui()
        self._center_on_parent()
        self._load_person_data_if_edit_mode()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header_title = QLabel("Edit Signature Record" if self.is_edit_mode else "Add New Signature Record", self)
        header_title.setStyleSheet(f"font-size: 16pt; font-weight: 700; color: {C_NAVY};")

        subtitle = QLabel(
            "Enter the person's name and provide their reference signature.",
            self,
        )
        subtitle.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)

        layout.addWidget(header_title)
        layout.addWidget(subtitle)
        layout.addWidget(divider)

        name_label = QLabel("Full Name *", self)
        name_label.setStyleSheet("font-size: 10pt; font-weight: 700;")

        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Enter full name (e.g., Priya Sharma)")
        self.name_input.textChanged.connect(self._hide_name_error)

        self.name_error_label = QLabel("", self)
        self.name_error_label.setStyleSheet(f"font-size: 8.5pt; color: {C_DANGER};")
        self.name_error_label.hide()

        layout.addWidget(name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.name_error_label)

        signature_label = QLabel("Reference Signature *", self)
        signature_label.setStyleSheet("font-size: 10pt; font-weight: 700;")
        layout.addWidget(signature_label)

        self.signature_tabs = QTabWidget(self)
        self.signature_tabs.addTab(self._build_upload_tab(), "📁 Upload Image")
        self.signature_tabs.addTab(self._build_camera_tab(), "📷 Camera Capture")
        layout.addWidget(self.signature_tabs)

        notes_label = QLabel("Notes (optional)", self)
        notes_label.setStyleSheet("font-size: 10pt;")

        self.notes_input = QTextEdit(self)
        self.notes_input.setFixedHeight(60)
        self.notes_input.setPlaceholderText("Add any notes about this signature or document source...")

        layout.addWidget(notes_label)
        layout.addWidget(self.notes_input)

        button_row = QHBoxLayout()
        button_row.addStretch(1)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setObjectName("secondary")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Record", self)
        save_btn.setMinimumWidth(120)
        save_btn.setStyleSheet(f"QPushButton {{ background: {C_BLUE}; color: white; font-weight: 700; }}")
        save_btn.clicked.connect(self._on_save)

        button_row.addWidget(cancel_btn)
        button_row.addWidget(save_btn)
        layout.addLayout(button_row)

    def _build_upload_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.upload_preview = SignaturePreviewLabel(tab)
        self.upload_preview.image_dropped.connect(self._on_upload_image_dropped)
        self.upload_preview.clicked.connect(self._browse_upload_image)

        buttons_row = QHBoxLayout()
        browse_btn = QPushButton("Browse Files", tab)
        browse_btn.setObjectName("secondary")
        browse_btn.clicked.connect(self._browse_upload_image)

        clear_btn = QPushButton("Clear", tab)
        clear_btn.setObjectName("secondary")
        clear_btn.setFixedWidth(90)
        clear_btn.clicked.connect(self._clear_upload_image)

        buttons_row.addWidget(browse_btn)
        buttons_row.addWidget(clear_btn)
        buttons_row.addStretch(1)

        self.upload_file_info_label = QLabel("", tab)
        self.upload_file_info_label.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        layout.addWidget(self.upload_preview)
        layout.addLayout(buttons_row)
        layout.addWidget(self.upload_file_info_label)
        return tab

    def _build_camera_tab(self) -> QWidget:
        tab = QWidget(self)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.camera_preview = SignaturePreviewLabel(tab)
        self.camera_preview.clicked.connect(self._open_camera_dialog)

        buttons_row = QHBoxLayout()
        open_camera_btn = QPushButton("Open Camera", tab)
        open_camera_btn.setStyleSheet(f"QPushButton {{ background: {C_BLUE}; color: white; }}")
        open_camera_btn.clicked.connect(self._open_camera_dialog)

        clear_btn = QPushButton("Clear", tab)
        clear_btn.setObjectName("secondary")
        clear_btn.setFixedWidth(90)
        clear_btn.clicked.connect(self._clear_camera_image)

        buttons_row.addWidget(open_camera_btn)
        buttons_row.addWidget(clear_btn)
        buttons_row.addStretch(1)

        instruction = QLabel(
            "Hold the document with the signature up to your camera and click Capture in the camera window.",
            tab,
        )
        instruction.setWordWrap(True)
        instruction.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        layout.addWidget(self.camera_preview)
        layout.addLayout(buttons_row)
        layout.addWidget(instruction)
        return tab

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        parent_center = parent.frameGeometry().center()
        geometry = self.frameGeometry()
        geometry.moveCenter(parent_center)
        self.move(geometry.topLeft())

    def _hide_name_error(self) -> None:
        if self.name_error_label.isVisible():
            self.name_error_label.hide()

    def _show_name_error(self, message: str) -> None:
        self.name_error_label.setText(message)
        self.name_error_label.show()

    def _on_upload_image_dropped(self, path: str) -> None:
        self._validate_and_set_upload_image(path)

    def _browse_upload_image(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Signature Image",
            "",
            "Image Files (*.png *.jpg *.jpeg)",
        )
        if not file_path:
            return
        self._validate_and_set_upload_image(file_path)

    def _validate_and_set_upload_image(self, path: str) -> None:
        valid, message = validate_image_path(path)
        if not valid:
            QMessageBox.warning(self, "Invalid Image", message)
            return

        valid_mime, mime_message = validate_file_mime(path)
        if not valid_mime:
            QMessageBox.warning(self, "Invalid Image", mime_message)
            return

        self.upload_preview.set_image_from_path(path)
        self._upload_image_path = path

        path_obj = Path(path)
        size_kb = max(1, int(path_obj.stat().st_size / 1024))
        self.upload_file_info_label.setText(f"{path_obj.name} • {size_kb} KB")

    def _clear_upload_image(self) -> None:
        self._upload_image_path = None
        self.upload_preview.clear_image()
        self.upload_file_info_label.clear()

    def _open_camera_dialog(self) -> None:
        dialog = CameraDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        captured = dialog.get_captured_pil_image()
        if captured is None:
            QMessageBox.warning(self, "Camera", "No image was captured.")
            return

        temp_dir = APP_DATA_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"capture_{uuid.uuid4().hex}.png"
        captured.save(temp_path, format="PNG")

        self.camera_preview.set_image_from_path(str(temp_path))
        self._camera_image_path = str(temp_path)

    def _clear_camera_image(self) -> None:
        self._camera_image_path = None
        self.camera_preview.clear_image()

    def _load_person_data_if_edit_mode(self) -> None:
        if not self.is_edit_mode or self.person is None:
            return

        self.name_input.setText(self.person.full_name or "")
        self.notes_input.setPlainText(self.person.notes or "")

        existing_path = self._resolve_signature_path(self.person.signature_image_path)
        if existing_path is not None and existing_path.exists():
            path_str = str(existing_path)
            self.upload_preview.set_image_from_path(path_str)
            self.camera_preview.set_image_from_path(path_str)
            self._upload_image_path = path_str
            self._camera_image_path = path_str
            size_kb = max(1, int(existing_path.stat().st_size / 1024))
            self.upload_file_info_label.setText(f"{existing_path.name} • {size_kb} KB")
        elif self.person.thumbnail_blob:
            self.upload_preview.set_image_from_bytes(self.person.thumbnail_blob)
            self.camera_preview.set_image_from_bytes(self.person.thumbnail_blob)

    def _resolve_signature_path(self, signature_path: str | None) -> Path | None:
        if not signature_path:
            return None
        candidate = Path(signature_path)
        if candidate.is_absolute():
            return candidate
        return SIGNATURES_STORAGE_DIR / candidate

    def _get_selected_signature_path(self) -> str | None:
        active_index = self.signature_tabs.currentIndex()
        if active_index == 0 and self._upload_image_path:
            return self._upload_image_path
        if active_index == 1 and self._camera_image_path:
            return self._camera_image_path
        return self._camera_image_path or self._upload_image_path

    def _slugify_name(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
        return slug or "signature"

    def _save_image_as_png(self, source_path: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source_path).convert("RGB") as image:
            image.save(target_path, format="PNG")

    def _build_thumbnail_blob(self, image_path: str) -> bytes:
        with Image.open(image_path).convert("RGB") as image:
            image.thumbnail((100, 40), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            image.save(stream, format="JPEG", quality=85)
            return stream.getvalue()

    def show_loading(self, message: str) -> None:
        if self._loading_dialog is None:
            self._loading_dialog = QProgressDialog(message, "", 0, 0, self)
            self._loading_dialog.setCancelButton(None)
            self._loading_dialog.setWindowTitle("Please wait")
            self._loading_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self._loading_dialog.setMinimumDuration(0)
            self._loading_dialog.setAutoClose(False)
            self._loading_dialog.setAutoReset(False)
        self._loading_dialog.setLabelText(message)
        self._loading_dialog.show()
        QApplication.processEvents()

    def hide_loading(self) -> None:
        if self._loading_dialog is not None:
            self._loading_dialog.hide()

    def _on_save(self) -> None:
        name = self.name_input.text().strip()
        valid_name, name_message = validate_name(name)
        if not valid_name:
            self._show_name_error(name_message)
            return

        selected_image_path = self._get_selected_signature_path()
        if not selected_image_path:
            QMessageBox.warning(self, "Missing Signature", "Please provide a reference signature image.")
            return

        selected_path_obj = Path(selected_image_path)
        if not selected_path_obj.exists():
            QMessageBox.warning(self, "Invalid Signature", "The selected signature image does not exist.")
            return

        notes = self.notes_input.toPlainText().strip() or None
        self.show_loading("Saving record...")

        try:
            thumbnail_blob = self._build_thumbnail_blob(str(selected_path_obj))
            sanitized_name = self._slugify_name(name)

            if self.is_edit_mode and self.person is not None:
                destination = SIGNATURES_STORAGE_DIR / f"{self.person.id}_{sanitized_name}.png"
                self._save_image_as_png(str(selected_path_obj), destination)

                updated = database_controller.update_person(
                    self.person.id,
                    full_name=name,
                    signature_image_path=str(destination),
                    thumbnail_blob=thumbnail_blob,
                    notes=notes,
                )
                if updated is None:
                    raise RuntimeError("Failed to update person record")
                logger.info("Updated person record id=%s", self.person.id)
            else:
                temp_name = f"{uuid.uuid4().hex}_{sanitized_name}.png"
                temp_destination = SIGNATURES_STORAGE_DIR / temp_name
                self._save_image_as_png(str(selected_path_obj), temp_destination)

                created = database_controller.add_person(
                    full_name=name,
                    signature_image_path=str(temp_destination),
                    thumbnail_blob=thumbnail_blob,
                    notes=notes,
                )

                final_destination = SIGNATURES_STORAGE_DIR / f"{created.id}_{sanitized_name}.png"
                if final_destination.exists():
                    final_destination.unlink()
                temp_destination.replace(final_destination)

                database_controller.update_person(
                    created.id,
                    signature_image_path=str(final_destination),
                )
                logger.info("Created person record id=%s", created.id)

            self.hide_loading()
            self.accept()
        except Exception as exc:
            logger.exception("Failed to save person record")
            self.hide_loading()
            QMessageBox.critical(self, "Save Failed", str(exc))
