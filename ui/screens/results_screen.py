"""Detailed verification results screen implementation."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import (
    C_AMBER,
    C_AMBER_BG,
    C_BLUE,
    C_BORDER,
    C_DANGER,
    C_DANGER_BG,
    C_GOLD,
    C_GREY_LT,
    C_NAVY,
    C_SUCCESS,
    C_SUCCESS_BG,
    C_TEXT_PRIMARY,
    C_TEXT_SECONDARY,
    C_WHITE,
)
from controllers.database_controller import database_controller
from controllers.navigation_controller import NavigationController
from models.person import Person
from models.verification import Verification
from ui.base_screen import BaseScreen
from ui.widgets.confidence_bar import ConfidenceBar
from ui.widgets.observations_table import ObservationsTable
from ui.widgets.signature_preview_label import SignaturePreviewLabel
from ui.widgets.verdict_badge import VerdictBadge
from utils.licence_manager import LicenceManager
from utils.logger import get_logger
from utils.thread_workers import ExportWorker

logger = get_logger(__name__)


class ResultsScreen(BaseScreen):
    """Displays full forensic results and export actions."""

    MODE_LABELS = {
        "A_SCREEN": "MODE A · SCREEN DETECTION",
        "B_UPLOAD": "MODE B · UPLOAD",
        "B_CAMERA": "MODE B · CAMERA",
        "C_ADHOC": "MODE C · AD-HOC",
    }

    def __init__(self, parent=None) -> None:
        self.result_dict: dict | None = None
        self.verification: Verification | None = None
        self.person: Person | None = None
        self._current_result_dict: dict | None = None
        self._current_verification: Verification | None = None
        self._current_person: Person | None = None
        self.export_worker: ExportWorker | None = None
        self.fade_animation: QPropertyAnimation | None = None
        self.opacity_effect: QGraphicsOpacityEffect | None = None

        self.copy_json_button: QPushButton | None = None
        self.edit_button: QPushButton | None = None
        self.flag_button: QPushButton | None = None
        self.confidence_bar: ConfidenceBar | None = None
        super().__init__(parent)

    def _build_ui(self) -> None:
        self.content_layout.setContentsMargins(14, 12, 14, 12)
        self.content_layout.setSpacing(10)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.scroll_container = QWidget(self.scroll_area)
        self.scroll_layout = QVBoxLayout(self.scroll_container)
        self.scroll_layout.setContentsMargins(12, 12, 12, 16)
        self.scroll_layout.setSpacing(14)

        self.scroll_area.setWidget(self.scroll_container)
        self.content_layout.addWidget(self.scroll_area)

    def _clear_scroll_layout(self) -> None:
        while self.scroll_layout.count() > 0:
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                while child_layout.count() > 0:
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget is not None:
                        child_widget.deleteLater()

    def _format_model_name(self, model_name: str) -> str:
        normalized = (model_name or "gemini-2.5-flash").strip().lower()
        if normalized == "gemini-2.5-flash":
            return "SignVerify Pro"
        return model_name

    def _quality_text(self, result_dict: dict) -> str:
        quality = result_dict.get("image_quality")
        if quality:
            return str(quality)

        ref_quality = result_dict.get("reference_quality") or {}
        sub_quality = result_dict.get("submitted_quality") or {}
        ref_overall = ref_quality.get("overall") if isinstance(ref_quality, dict) else None
        sub_overall = sub_quality.get("overall") if isinstance(sub_quality, dict) else None

        if ref_overall and sub_overall:
            return f"Ref {ref_overall} · Sub {sub_overall}"
        if ref_overall:
            return f"Ref {ref_overall}"
        if sub_overall:
            return f"Sub {sub_overall}"
        return "Not available"

    def _confidence_interpretation(self, confidence: float) -> str:
        if confidence <= 0.49:
            return "Strong forensic differentiators identified"
        if confidence <= 0.65:
            return "Insufficient evidence for definitive determination"
        if confidence <= 0.85:
            return "Significant forensic similarity across multiple strategies"
        return "Overwhelming forensic evidence — all strategies align"

    def _mode_badge_text(self, mode: str) -> str:
        return self.MODE_LABELS.get(mode, f"MODE · {mode or 'UNKNOWN'}")

    def _set_preview_image(self, preview: SignaturePreviewLabel, image_path: str) -> None:
        preview.setFixedSize(240, 100)
        preview.setAcceptDrops(False)
        preview.setCursor(Qt.CursorShape.ArrowCursor)

        if image_path and Path(image_path).exists():
            preview.set_image_from_path(image_path)
            return

        preview.clear_image()
        preview.setText("Image not available")
        preview.setStyleSheet(
            f"border: 1px solid {C_BORDER}; background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; font-size: 8pt;"
        )

    def show_result(self, result_dict: dict, verification: Verification, person: Person | None = None) -> None:
        self._current_result_dict = result_dict
        self._current_verification = verification
        self._current_person = person

        self.result_dict = result_dict
        self.verification = verification
        self.person = person

        self._clear_scroll_layout()

        verdict = str(
            result_dict.get("verdict")
            or result_dict.get("result")
            or "INCONCLUSIVE"
        ).upper()
        confidence = float(result_dict.get("confidence", 0.0) or 0.0)
        reason = str(result_dict.get("reason", "No forensic reasoning available.") or "No forensic reasoning available.")
        observations = result_dict.get("observations") or {}
        if not isinstance(observations, dict):
            observations = {}

        mode = str(verification.mode or "")
        person_name = person.full_name if person is not None else (
            "Ad-Hoc Comparison" if mode == "C_ADHOC" else "Unknown Person"
        )

        verified_at = verification.verified_at if verification.verified_at else datetime.now()
        timestamp_text = verified_at.strftime("%d %b %Y, %H:%M")
        model_used = self._format_model_name(str(result_dict.get("model_used", "gemini-2.5-flash")))

        header_row = QWidget(self.scroll_container)
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        mode_badge = QLabel(self._mode_badge_text(mode), header_row)
        mode_badge.setStyleSheet(
            f"background: {C_NAVY}; color: {C_WHITE}; font-size: 8pt; font-weight: 700; "
            "padding: 4px 10px; border-radius: 10px;"
        )

        person_label = QLabel(person_name, header_row)
        person_label.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

        timestamp_label = QLabel(timestamp_text, header_row)
        timestamp_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        model_label = QLabel(model_used, header_row)
        model_label.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        right_stack = QVBoxLayout()
        right_stack.setContentsMargins(0, 0, 0, 0)
        right_stack.setSpacing(2)
        right_stack.addWidget(timestamp_label, alignment=Qt.AlignmentFlag.AlignRight)
        right_stack.addWidget(model_label, alignment=Qt.AlignmentFlag.AlignRight)

        header_layout.addWidget(mode_badge)
        header_layout.addWidget(person_label)
        header_layout.addStretch(1)
        header_layout.addLayout(right_stack)
        self.scroll_layout.addWidget(header_row)

        verdict_bg = C_AMBER_BG
        verdict_border = C_AMBER
        if verdict == "MATCH":
            verdict_bg = C_SUCCESS_BG
            verdict_border = C_SUCCESS
        elif verdict == "MISMATCH":
            verdict_bg = C_DANGER_BG
            verdict_border = C_DANGER

        verdict_frame = QFrame(self.scroll_container)
        verdict_frame.setStyleSheet(
            f"background: {verdict_bg}; border: 2px solid {verdict_border}; border-radius: 12px;"
        )
        verdict_layout = QHBoxLayout(verdict_frame)
        verdict_layout.setContentsMargins(14, 14, 14, 14)
        verdict_layout.setSpacing(16)

        left_column = QVBoxLayout()
        left_column.setSpacing(6)

        verdict_badge = VerdictBadge(verdict, verdict_frame)
        verdict_badge.setFixedHeight(52)
        badge_font = verdict_badge.font()
        badge_font.setPointSize(12)
        badge_font.setBold(True)
        verdict_badge.setFont(badge_font)

        interpretation = QLabel(self._confidence_interpretation(confidence), verdict_frame)
        interpretation.setWordWrap(True)
        interpretation.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        left_column.addWidget(verdict_badge)
        left_column.addWidget(interpretation)

        center_column = QVBoxLayout()
        center_column.setSpacing(8)

        self.confidence_bar = ConfidenceBar(verdict_frame)
        self.confidence_bar.setFixedHeight(32)
        self.confidence_bar.set_confidence(0.0)

        confidence_label = QLabel(f"{confidence * 100.0:.1f}% Confidence", verdict_frame)
        confidence_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_PRIMARY}; font-weight: 700;")

        center_column.addWidget(self.confidence_bar)
        center_column.addWidget(confidence_label)

        right_column = QVBoxLayout()
        right_column.setSpacing(4)
        analysis_time_value = result_dict.get("analysis_time_sec")
        try:
            analysis_text = f"{float(analysis_time_value):.1f}s"
        except (TypeError, ValueError):
            analysis_text = "N/A"

        stats = [
            "Strategies Analysed: 13",
            f"Analysis Time: {analysis_text}",
            f"Image Quality: {self._quality_text(result_dict)}",
        ]
        for stat in stats:
            stat_label = QLabel(stat, verdict_frame)
            stat_label.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")
            right_column.addWidget(stat_label)
        right_column.addStretch(1)

        verdict_layout.addLayout(left_column, 1)
        verdict_layout.addLayout(center_column, 2)
        verdict_layout.addLayout(right_column, 1)
        self.scroll_layout.addWidget(verdict_frame)

        QTimer.singleShot(300, lambda: self.confidence_bar.animate_to(confidence))

        image_row = QWidget(self.scroll_container)
        image_layout = QHBoxLayout(image_row)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.setSpacing(16)

        left_panel = QWidget(image_row)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        left_title = QLabel("Reference Signature", left_panel)
        left_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_title.setStyleSheet(f"font-size: 9pt; font-weight: 700; color: {C_TEXT_SECONDARY};")

        left_preview = SignaturePreviewLabel(left_panel)
        self._set_preview_image(left_preview, verification.reference_image_path or "")

        left_file = QLabel(Path(verification.reference_image_path).name if verification.reference_image_path else "", left_panel)
        left_file.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_file.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        left_layout.addWidget(left_title)
        left_layout.addWidget(left_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(left_file)

        separator = QFrame(image_row)
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet(f"color: {C_BORDER};")

        right_panel = QWidget(image_row)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        right_title = QLabel("Submitted Signature", right_panel)
        right_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_title.setStyleSheet(f"font-size: 9pt; font-weight: 700; color: {C_TEXT_SECONDARY};")

        right_preview = SignaturePreviewLabel(right_panel)
        self._set_preview_image(right_preview, verification.submitted_image_path or "")

        right_file = QLabel(Path(verification.submitted_image_path).name if verification.submitted_image_path else "", right_panel)
        right_file.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_file.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        right_layout.addWidget(right_title)
        right_layout.addWidget(right_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(right_file)

        image_layout.addWidget(left_panel, 1)
        image_layout.addWidget(separator)
        image_layout.addWidget(right_panel, 1)
        self.scroll_layout.addWidget(image_row)

        observations_heading = QLabel("Forensic Observations", self.scroll_container)
        observations_heading.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        observations_subtitle = QLabel(
            "Similarity assessment across 25 forensic dimensions",
            self.scroll_container,
        )
        observations_subtitle.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        observations_table = ObservationsTable(self.scroll_container)
        observations_table.populate(observations if isinstance(observations, dict) else {})
        observations_table.setFixedHeight(320)

        self.scroll_layout.addWidget(observations_heading)
        self.scroll_layout.addWidget(observations_subtitle)
        self.scroll_layout.addWidget(observations_table)

        reasoning_heading = QLabel("Forensic Reasoning", self.scroll_container)
        reasoning_heading.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        reasoning_scroll = QScrollArea(self.scroll_container)
        reasoning_scroll.setWidgetResizable(True)
        reasoning_scroll.setFrameShape(QFrame.Shape.NoFrame)
        reasoning_scroll.setMinimumHeight(80)
        reasoning_scroll.setMaximumHeight(140)

        reasoning_container = QWidget(reasoning_scroll)
        reasoning_layout = QVBoxLayout(reasoning_container)
        reasoning_layout.setContentsMargins(0, 0, 0, 0)

        reasoning_label = QLabel(reason, reasoning_container)
        reasoning_label.setWordWrap(True)
        reasoning_label.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_PRIMARY}; font-size: 10pt; "
            "padding: 16px; border-radius: 8px;"
        )

        reasoning_layout.addWidget(reasoning_label)
        reasoning_scroll.setWidget(reasoning_container)

        self.scroll_layout.addWidget(reasoning_heading)
        self.scroll_layout.addWidget(reasoning_scroll)

        button_row = QWidget(self.scroll_container)
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(10)
        button_layout.addStretch(1)

        export_button = QPushButton("📄 Export PDF", button_row)
        export_button.clicked.connect(self._on_export_pdf)

        self.copy_json_button = QPushButton("{ } Copy JSON", button_row)
        self.copy_json_button.setObjectName("secondary")
        self.copy_json_button.clicked.connect(self._on_copy_json)

        self.edit_button = QPushButton("✎ Edit Result", button_row)
        self.edit_button.setObjectName("secondary")
        self.edit_button.setMinimumWidth(110)
        self.edit_button.clicked.connect(self._on_edit_clicked)

        self.flag_button = QPushButton("⚑ Flag for Review", button_row)
        self.flag_button.setStyleSheet(
            f"background: {C_GOLD}; color: {C_NAVY}; border: none; font-weight: 700;"
        )
        self.flag_button.clicked.connect(self._on_flag_for_review)

        if int(verification.flagged_for_review or 0) == 1:
            self._set_flag_button_flagged_state()

        new_verification_button = QPushButton("▶ New Verification", button_row)
        new_verification_button.setStyleSheet(
            f"background: {C_SUCCESS}; color: {C_WHITE}; border: none; font-weight: 700;"
        )
        new_verification_button.clicked.connect(
            lambda: NavigationController.get_instance().navigate_to("verification")
        )

        button_layout.addWidget(export_button)
        button_layout.addWidget(self.copy_json_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.flag_button)
        button_layout.addWidget(new_verification_button)

        self.scroll_layout.addWidget(button_row)
        self.scroll_layout.addStretch(1)

    def _set_flag_button_flagged_state(self) -> None:
        if self.flag_button is None:
            return
        self.flag_button.setText("⚑ Flagged")
        self.flag_button.setEnabled(False)
        self.flag_button.setStyleSheet(
            f"background: {C_BORDER}; color: {C_TEXT_SECONDARY}; border: none; font-weight: 700;"
        )

    def _safe_filename_fragment(self, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
        return cleaned.strip("_") or "Report"

    def _build_export_payload(self) -> dict:
        if self.result_dict is None or self.verification is None:
            return {}

        person_name = self.person.full_name if self.person is not None else "AdHoc"
        verified_at = self.verification.verified_at.strftime("%d %b %Y %H:%M") if self.verification.verified_at else ""

        return {
            "verification_id": self.verification.id if self.verification.id is not None else "N/A",
            "person_name": person_name,
            "mode": self.verification.mode,
            "verdict": self.result_dict.get("verdict") or self.result_dict.get("result"),
            "confidence": self.result_dict.get("confidence"),
            "reason": self.result_dict.get("reason"),
            "observations": self.result_dict.get("observations")
            if isinstance(self.result_dict.get("observations"), dict)
            else {},
            "reference_image_path": self.verification.reference_image_path or "",
            "submitted_image_path": self.verification.submitted_image_path or "",
            "verified_at": verified_at,
            "response_hash": self.verification.response_hash or "",
        }

    def _on_export_pdf(self) -> None:
        if self.result_dict is None or self.verification is None:
            self.show_error("Export Failed", "No verification result available for export.")
            return

        licence_manager = LicenceManager.get_instance()
        if not licence_manager.can_export_pdf():
            licence_manager.show_upgrade_prompt(self, "PDF Report Export")
            return

        person_name = self.person.full_name if self.person is not None else "AdHoc"
        safe_name = self._safe_filename_fragment(person_name)
        date_tag = datetime.now().strftime("%Y%m%d")
        default_name = f"SignVerify_Report_{safe_name}_{date_tag}.pdf"

        downloads_dir = Path.home() / "Downloads"
        try:
            downloads_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            downloads_dir = Path.cwd()

        default_path = str((downloads_dir / default_name).resolve())

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF Report",
            default_path,
            "PDF Files (*.pdf)",
        )
        if not output_path:
            return
        if not output_path.lower().endswith(".pdf"):
            output_path = f"{output_path}.pdf"

        payload = self._build_export_payload()
        self.show_loading("Generating PDF report...")

        self.export_worker = ExportWorker(payload, output_path)
        self.export_worker.progress_updated.connect(self.show_loading)
        self.export_worker.export_complete.connect(self._on_export_complete)
        self.export_worker.error_occurred.connect(self._on_export_error)
        self.export_worker.start()

    def _on_export_complete(self, output_path: str) -> None:
        self.hide_loading()

        if self.verification is not None and self.verification.id is not None:
            database_controller.mark_exported(self.verification.id)

        self.show_success("PDF Exported", f"Report saved to {output_path}")

        open_choice = QMessageBox.question(
            self,
            "Open Report",
            "Would you like to open the exported PDF now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if open_choice == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))

        if self.export_worker is not None:
            self.export_worker.deleteLater()
            self.export_worker = None

    def _on_export_error(self, message: str) -> None:
        self.hide_loading()
        self.show_error("Export Failed", message)
        if self.export_worker is not None:
            self.export_worker.deleteLater()
            self.export_worker = None

    def _on_copy_json(self) -> None:
        if self.result_dict is None:
            return

        clipboard = QApplication.clipboard()
        clipboard.setText(json.dumps(self.result_dict, indent=2, ensure_ascii=False))

        if self.copy_json_button is None:
            return

        original_text = "{ } Copy JSON"
        self.copy_json_button.setText("✓ Copied!")
        QTimer.singleShot(1500, lambda: self.copy_json_button.setText(original_text))

    def _on_edit_clicked(self) -> None:
        if self._current_verification is None:
            self.show_error("No Verification", "No verification result is currently loaded.")
            return

        if self._current_result_dict is None:
            self.show_error("No Data", "No result data is available to edit.")
            return

        try:
            from ui.dialogs.edit_verification_dialog import EditVerificationDialog

            dialog = EditVerificationDialog(
                parent=self,
                verification=self._current_verification,
                result_dict=self._current_result_dict,
            )

            result = dialog.exec()
            if result != QDialog.DialogCode.Accepted:
                return

            saved_result_dict = dialog.get_saved_result_dict()
            saved_verification = dialog.get_saved_verification()
            if not saved_result_dict or saved_verification is None:
                return

            self.show_result(
                result_dict=saved_result_dict,
                verification=saved_verification,
                person=self._current_person,
            )

            main_window = self.window()
            if hasattr(main_window, "statusBar"):
                status_bar = main_window.statusBar()
                if status_bar is not None:
                    status_bar.showMessage("Result updated successfully.", 3000)

            logger.info(
                "ResultsScreen re-rendered after edit: verification_id=%s",
                getattr(saved_verification, "id", "N/A"),
            )
        except Exception as exc:
            logger.error("Edit dialog error: %s", exc, exc_info=True)
            self.show_error("Edit Error", f"Could not open the edit form: {str(exc)}")

    def _on_flag_for_review(self) -> None:
        if self.verification is None:
            return

        if self.verification.id is not None:
            success = database_controller.flag_verification(self.verification.id, flagged=True)
            if not success:
                self.show_error("Update Failed", "Unable to flag this verification for review.")
                return

        self.verification.flagged_for_review = 1
        self._set_flag_button_flagged_state()

        status_bar = self.window().statusBar() if hasattr(self.window(), "statusBar") else None
        if status_bar is not None:
            status_bar.showMessage("Verification flagged for manual review", 3000)

    def _build_empty_state(self) -> None:
        self._clear_scroll_layout()

        empty_wrap = QWidget(self.scroll_container)
        empty_layout = QVBoxLayout(empty_wrap)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(10)

        label = QLabel("No result data to display. Please start a new verification.", empty_wrap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"font-size: 10pt; color: {C_TEXT_SECONDARY};")

        button = QPushButton("Start New Verification", empty_wrap)
        button.clicked.connect(lambda: NavigationController.get_instance().navigate_to("verification"))

        empty_layout.addWidget(label)
        empty_layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.scroll_layout.addStretch(1)
        self.scroll_layout.addWidget(empty_wrap)
        self.scroll_layout.addStretch(1)

    def _start_fade_in(self) -> None:
        if self.opacity_effect is not None:
            self.scroll_container.setGraphicsEffect(None)
            self.opacity_effect = None

        self.opacity_effect = QGraphicsOpacityEffect(self.scroll_container)
        self.opacity_effect.setOpacity(0.0)
        self.scroll_container.setGraphicsEffect(self.opacity_effect)

        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.fade_animation.setDuration(400)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.fade_animation.start()

    def on_show(
        self,
        result_dict: dict | None = None,
        verification: Verification | None = None,
        person: Person | None = None,
        **kwargs,
    ) -> None:
        _ = kwargs
        logger.info("ResultsScreen shown")

        if result_dict is not None and verification is not None:
            self.show_result(result_dict, verification, person)
            QTimer.singleShot(50, self._start_fade_in)
            return

        self._build_empty_state()
        QTimer.singleShot(50, self._start_fade_in)
