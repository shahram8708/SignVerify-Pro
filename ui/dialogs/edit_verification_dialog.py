"""Dialog for editing an existing verification result."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from PyQt6.QtCore import QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import (
    C_AMBER,
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
)
from utils.logger import get_logger

logger = get_logger("edit_verification_dialog")


class ClickableFrame(QFrame):
    """Simple frame that emits clicked signal."""

    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class EditVerificationDialog(QDialog):
    """Form dialog that allows editing of all verification result fields."""

    RESULT_OPTIONS = ["MATCH", "MISMATCH", "INCONCLUSIVE"]
    HML_OPTIONS = ["High", "Medium", "Low"]
    HML_UA_OPTIONS = ["High", "Medium", "Low", "Unable to assess"]

    OBSERVATION_KEYS = [
        "shape_similarity",
        "stroke_similarity",
        "letter_pattern_similarity",
        "alignment_similarity",
        "pen_pressure_consistency",
        "pen_speed_rhythm_consistency",
        "line_quality_consistency",
        "zone_proportion_match",
        "habitual_features_match",
        "paraph_flourish_match",
        "underscore_match",
        "loop_size_and_shape_match",
        "pen_lift_position_consistency",
        "entry_stroke_match",
        "exit_stroke_match",
        "baseline_consistency",
        "slant_angle_consistency",
        "stroke_direction_consistency",
        "hesitation_marks_detected",
        "retouching_or_patching_detected",
        "forgery_type_suspected",
        "natural_variation_within_expected_range",
        "image_quality_signature_1",
        "image_quality_signature_2",
        "image_quality_impact_on_confidence",
        "additional_anomalies",
    ]

    FIELD_LABELS = {
        "result": "Verdict",
        "confidence": "Confidence Score",
        "matched_person": "Matched Person",
        "reason": "Forensic Reason",
        "shape_similarity": "Shape Similarity",
        "stroke_similarity": "Stroke Similarity",
        "letter_pattern_similarity": "Letter Pattern Similarity",
        "alignment_similarity": "Alignment Similarity",
        "pen_pressure_consistency": "Pen Pressure Consistency",
        "pen_speed_rhythm_consistency": "Pen Speed / Rhythm Consistency",
        "line_quality_consistency": "Line Quality Consistency",
        "zone_proportion_match": "Zone Proportion Match",
        "habitual_features_match": "Habitual Features Match",
        "paraph_flourish_match": "Paraph / Flourish Match",
        "underscore_match": "Underscore Match",
        "loop_size_and_shape_match": "Loop Size and Shape Match",
        "pen_lift_position_consistency": "Pen Lift Position Consistency",
        "entry_stroke_match": "Entry Stroke Match",
        "exit_stroke_match": "Exit Stroke Match",
        "baseline_consistency": "Baseline Consistency",
        "slant_angle_consistency": "Slant Angle Consistency",
        "stroke_direction_consistency": "Stroke Direction Consistency",
        "hesitation_marks_detected": "Hesitation Marks Detected",
        "retouching_or_patching_detected": "Retouching or Patching Detected",
        "forgery_type_suspected": "Forgery Type Suspected",
        "natural_variation_within_expected_range": "Natural Variation Within Expected Range",
        "image_quality_signature_1": "Image Quality - Signature 1",
        "image_quality_signature_2": "Image Quality - Signature 2",
        "image_quality_impact_on_confidence": "Image Quality Impact on Confidence",
        "additional_anomalies": "Additional Anomalies",
    }

    def __init__(self, parent=None, verification=None, result_dict: dict = None) -> None:
        super().__init__(parent)
        self.verification = verification
        self.result_dict = result_dict or {}
        self._field_widgets: dict[str, QWidget] = {}
        self._field_labels: dict[str, QLabel] = {}
        self._field_label_text: dict[str, str] = {}
        self._field_base_styles: dict[str, str] = {}
        self._field_changed: dict[str, bool] = {}
        self._original_values: dict[str, str | float] = {}
        self._has_unsaved_changes = False
        self._suspend_change_tracking = False

        self._saved_result_dict: dict | None = None
        self._saved_verification = None

        self._sections: dict[str, dict] = {}
        self._section_fields: dict[str, list[str]] = {
            "verification_outcome": ["result", "confidence", "matched_person", "reason"],
            "stroke_form_analysis": [
                "shape_similarity",
                "stroke_similarity",
                "letter_pattern_similarity",
                "alignment_similarity",
                "stroke_direction_consistency",
                "line_quality_consistency",
            ],
            "pressure_speed_rhythm": [
                "pen_pressure_consistency",
                "pen_speed_rhythm_consistency",
            ],
            "structural_spatial": [
                "zone_proportion_match",
                "baseline_consistency",
                "slant_angle_consistency",
                "loop_size_and_shape_match",
                "habitual_features_match",
            ],
            "stroke_endpoints": [
                "entry_stroke_match",
                "exit_stroke_match",
                "pen_lift_position_consistency",
            ],
            "decorative_elements": ["paraph_flourish_match", "underscore_match"],
            "forensic_indicators": [
                "hesitation_marks_detected",
                "retouching_or_patching_detected",
                "forgery_type_suspected",
                "natural_variation_within_expected_range",
            ],
            "image_quality": [
                "image_quality_signature_1",
                "image_quality_signature_2",
                "image_quality_impact_on_confidence",
            ],
            "additional_notes": ["additional_anomalies"],
        }

        self.verdict_dot_label: QLabel | None = None
        self.confidence_hint_label: QLabel | None = None
        self.reason_counter_label: QLabel | None = None
        self.change_summary_label: QLabel | None = None
        self.additional_quickfill_combo: QComboBox | None = None

        self.reset_button: QPushButton | None = None
        self.cancel_button: QPushButton | None = None
        self.save_button: QPushButton | None = None

        self.setWindowTitle("Edit Verification Result")
        self.setModal(True)
        self.resize(780, 720)
        self.setMinimumSize(680, 580)

        self._apply_dialog_styles()
        self._build_ui()
        self._setup_shortcuts()
        self._set_tab_order()
        self._center_on_parent()

        self._populate_from_data()

    def _apply_dialog_styles(self) -> None:
        self.setStyleSheet(
            f"""
            QDialog {{
                background: {C_WHITE};
            }}
            QFrame#section_header {{
                background: {C_GREY_LT};
                border: 1px solid {C_BORDER};
                border-radius: 6px 6px 0 0;
            }}
            QFrame#section_header:hover {{
                background: #EAEEF2;
            }}
            QFrame#section_body {{
                border: 1px solid {C_BORDER};
                border-top: none;
                border-radius: 0 0 6px 6px;
                background: {C_WHITE};
            }}
            QFrame#form_row {{
                background: transparent;
                border-radius: 6px;
            }}
            QFrame#form_row:hover {{
                background: #FAFAFA;
            }}
            QLabel#section_title {{
                color: {C_NAVY};
                font-size: 11pt;
                font-weight: 700;
            }}
            QLabel#section_change_badge {{
                color: {C_GOLD};
                font-size: 8.5pt;
                font-weight: 700;
            }}
            QLabel#field_label {{
                color: {C_TEXT_PRIMARY};
                font-size: 9pt;
            }}
            QLineEdit, QComboBox, QDoubleSpinBox {{
                min-height: 34px;
                border: 1px solid {C_BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                background: {C_WHITE};
            }}
            QTextEdit {{
                border: 1px solid {C_BORDER};
                border-radius: 6px;
                padding: 8px 10px;
                background: {C_WHITE};
            }}
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
                border: 2px solid {C_BLUE};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {C_TEXT_SECONDARY};
                margin-right: 8px;
            }}
            QScrollBar:vertical {{
                width: 8px;
                margin: 0;
                background: {C_GREY_LT};
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {C_BORDER};
                min-height: 24px;
                border-radius: 4px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
                height: 0;
            }}
            """
        )

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_header_bar())

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.form_container = QWidget(self.scroll_area)
        self.form_layout = QVBoxLayout(self.form_container)
        self.form_layout.setContentsMargins(20, 16, 20, 16)
        self.form_layout.setSpacing(14)

        self._build_verification_outcome_section()
        self._build_collapsible_section(
            section_id="stroke_form_analysis",
            title="Stroke & Form Analysis",
            field_defs=[
                ("shape_similarity", self.HML_OPTIONS),
                ("stroke_similarity", self.HML_OPTIONS),
                ("letter_pattern_similarity", self.HML_OPTIONS),
                ("alignment_similarity", self.HML_OPTIONS),
                ("stroke_direction_consistency", self.HML_OPTIONS),
                ("line_quality_consistency", self.HML_OPTIONS),
            ],
        )
        self._build_collapsible_section(
            section_id="pressure_speed_rhythm",
            title="Pressure, Speed & Rhythm",
            field_defs=[
                ("pen_pressure_consistency", self.HML_UA_OPTIONS),
                ("pen_speed_rhythm_consistency", self.HML_UA_OPTIONS),
            ],
        )
        self._build_collapsible_section(
            section_id="structural_spatial",
            title="Structural & Spatial Features",
            field_defs=[
                ("zone_proportion_match", self.HML_OPTIONS),
                ("baseline_consistency", self.HML_OPTIONS),
                ("slant_angle_consistency", self.HML_OPTIONS),
                ("loop_size_and_shape_match", self.HML_UA_OPTIONS),
                ("habitual_features_match", self.HML_OPTIONS),
            ],
        )
        self._build_collapsible_section(
            section_id="stroke_endpoints",
            title="Stroke Endpoints & Transitions",
            field_defs=[
                ("entry_stroke_match", self.HML_OPTIONS),
                ("exit_stroke_match", self.HML_OPTIONS),
                ("pen_lift_position_consistency", self.HML_UA_OPTIONS),
            ],
        )
        self._build_collapsible_section(
            section_id="decorative_elements",
            title="Decorative & Special Elements",
            field_defs=[
                (
                    "paraph_flourish_match",
                    [
                        "Present and matching",
                        "Present but different",
                        "Absent in one",
                        "Absent in both",
                        "Unable to assess",
                    ],
                ),
                (
                    "underscore_match",
                    [
                        "Present and matching",
                        "Present but different",
                        "Absent in one",
                        "Absent in both",
                        "Unable to assess",
                    ],
                ),
            ],
        )
        self._build_collapsible_section(
            section_id="forensic_indicators",
            title="Forensic Indicators",
            field_defs=[
                (
                    "hesitation_marks_detected",
                    ["No", "Yes — in signature 1", "Yes — in signature 2", "Yes — in both"],
                ),
                (
                    "retouching_or_patching_detected",
                    ["No", "Yes — in signature 1", "Yes — in signature 2", "Yes — in both"],
                ),
                (
                    "forgery_type_suspected",
                    [
                        "None",
                        "Simulated",
                        "Traced",
                        "Freehand",
                        "Digital manipulation",
                        "Auto-forgery",
                        "Inconclusive",
                    ],
                ),
                (
                    "natural_variation_within_expected_range",
                    ["Yes", "No", "Borderline"],
                ),
            ],
        )
        self._build_collapsible_section(
            section_id="image_quality",
            title="Image Quality Assessment",
            field_defs=[
                ("image_quality_signature_1", self.HML_UA_OPTIONS),
                ("image_quality_signature_2", self.HML_UA_OPTIONS),
                (
                    "image_quality_impact_on_confidence",
                    ["None", "Minor", "Moderate", "Significant"],
                ),
            ],
        )
        self._build_additional_notes_section()

        self.form_layout.addStretch(1)
        self.scroll_area.setWidget(self.form_container)
        root_layout.addWidget(self.scroll_area, stretch=1)

        root_layout.addWidget(self._build_bottom_action_bar())

        QTimer.singleShot(0, self._initialize_section_heights)

    def _build_header_bar(self) -> QFrame:
        header = QFrame(self)
        header.setFixedHeight(60)
        header.setStyleSheet(f"background: {C_NAVY};")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(10)

        title = QLabel("✎ Edit Verification Result", header)
        title.setStyleSheet(f"color: {C_WHITE}; font-size: 14pt; font-weight: 700;")

        verification_id = "N/A"
        timestamp_text = "Unknown time"
        if self.verification is not None:
            if getattr(self.verification, "id", None) is not None:
                verification_id = str(self.verification.id)
            verified_at = getattr(self.verification, "verified_at", None)
            if isinstance(verified_at, datetime):
                timestamp_text = verified_at.strftime("%d %b %Y, %H:%M")

        info = QLabel(f"Verification #{verification_id} · {timestamp_text}", header)
        info.setStyleSheet(f"color: {C_WHITE}; font-size: 9pt;")

        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(info)
        return header

    def _build_verification_outcome_section(self) -> None:
        container = QFrame(self.form_container)
        container.setStyleSheet(f"border-bottom: 1px solid {C_BORDER};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Verification Outcome", container)
        title.setStyleSheet(f"color: {C_NAVY}; font-size: 11pt; font-weight: 700;")

        badge = QLabel("", container)
        badge.setObjectName("section_change_badge")
        badge.setVisible(False)

        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(badge)
        layout.addLayout(title_row)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addLayout(form)

        verdict_combo = self._build_field_widget("result", self.RESULT_OPTIONS, "INCONCLUSIVE")
        self.verdict_dot_label = QLabel("●", container)
        self.verdict_dot_label.setFixedWidth(18)
        self.verdict_dot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        verdict_wrap = QWidget(container)
        verdict_wrap_layout = QHBoxLayout(verdict_wrap)
        verdict_wrap_layout.setContentsMargins(0, 0, 0, 0)
        verdict_wrap_layout.setSpacing(8)
        verdict_wrap_layout.addWidget(verdict_combo)
        verdict_wrap_layout.addWidget(self.verdict_dot_label)
        verdict_wrap_layout.addStretch(1)

        self._add_form_row(form, "result", self.FIELD_LABELS["result"], verdict_wrap, single_line=True)

        confidence_spin = self._build_field_widget("confidence", [], 0.5)
        self.confidence_hint_label = QLabel("", container)
        self.confidence_hint_label.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        confidence_wrap = QWidget(container)
        confidence_layout = QHBoxLayout(confidence_wrap)
        confidence_layout.setContentsMargins(0, 0, 0, 0)
        confidence_layout.setSpacing(8)
        confidence_layout.addWidget(confidence_spin)
        confidence_layout.addWidget(self.confidence_hint_label)
        confidence_layout.addStretch(1)

        self._add_form_row(form, "confidence", self.FIELD_LABELS["confidence"], confidence_wrap, single_line=True)

        matched_person_edit = self._build_field_widget("matched_person", [], "")
        self._add_form_row(form, "matched_person", self.FIELD_LABELS["matched_person"], matched_person_edit, single_line=True)

        reason_text = self._build_field_widget("reason", [], "")
        self.reason_counter_label = QLabel("0 / 2000 characters", container)
        self.reason_counter_label.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")

        reason_wrap = QWidget(container)
        reason_layout = QVBoxLayout(reason_wrap)
        reason_layout.setContentsMargins(0, 0, 0, 0)
        reason_layout.setSpacing(4)
        reason_layout.addWidget(reason_text)
        reason_layout.addWidget(self.reason_counter_label, alignment=Qt.AlignmentFlag.AlignRight)

        self._add_form_row(form, "reason", self.FIELD_LABELS["reason"], reason_wrap, single_line=False)

        verdict_combo.currentIndexChanged.connect(self._on_verdict_changed)
        confidence_spin.valueChanged.connect(self._on_confidence_changed)

        self._sections["verification_outcome"] = {
            "badge": badge,
            "fields": self._section_fields["verification_outcome"],
        }

        self.form_layout.addWidget(container)

    def _build_collapsible_section(self, section_id: str, title: str, field_defs: list[tuple[str, list[str]]]) -> None:
        section = QFrame(self.form_container)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)

        header = ClickableFrame(section)
        header.setObjectName("section_header")
        header.setFixedHeight(40)
        header.setCursor(Qt.CursorShape.PointingHandCursor)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(8)

        arrow_label = QLabel("▼", header)
        arrow_label.setStyleSheet(f"font-size: 10pt; color: {C_NAVY};")
        arrow_label.setFixedWidth(14)

        title_label = QLabel(title, header)
        title_label.setObjectName("section_title")

        badge = QLabel("", header)
        badge.setObjectName("section_change_badge")
        badge.setVisible(False)

        header_layout.addWidget(arrow_label)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(badge)

        content = QFrame(section)
        content.setObjectName("section_body")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(0)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        content_layout.addLayout(form)

        for field_key, allowed_values in field_defs:
            widget = self._build_field_widget(field_key, allowed_values, "")
            self._add_form_row(form, field_key, self.FIELD_LABELS[field_key], widget, single_line=True)

        animation = QPropertyAnimation(content, b"maximumHeight", self)
        animation.setDuration(200)

        section_layout.addWidget(header)
        section_layout.addWidget(content)
        self.form_layout.addWidget(section)

        self._sections[section_id] = {
            "header": header,
            "arrow": arrow_label,
            "badge": badge,
            "content": content,
            "animation": animation,
            "expanded": True,
            "fields": self._section_fields[section_id],
        }

        header.clicked.connect(lambda sid=section_id: self._toggle_section(sid))

    def _build_additional_notes_section(self) -> None:
        section = QFrame(self.form_container)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)

        header = QFrame(section)
        header.setObjectName("section_header")
        header.setFixedHeight(40)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)
        header_layout.setSpacing(8)

        title_label = QLabel("Additional Notes", header)
        title_label.setObjectName("section_title")

        badge = QLabel("", header)
        badge.setObjectName("section_change_badge")
        badge.setVisible(False)

        header_layout.addWidget(title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(badge)

        content = QFrame(section)
        content.setObjectName("section_body")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(0)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        content_layout.addLayout(form)

        anomalies_widget = self._build_field_widget("additional_anomalies", [], "")

        self.additional_quickfill_combo = QComboBox(content)
        self.additional_quickfill_combo.addItems(
            [
                "None",
                "Ink bleeding detected",
                "Paper quality affected scan",
                "Signature appears rushed",
                "Signature appears copied",
                "Custom...",
            ]
        )
        self.additional_quickfill_combo.setCurrentIndex(-1)

        notes_wrap = QWidget(content)
        notes_layout = QVBoxLayout(notes_wrap)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(6)
        notes_layout.addWidget(self.additional_quickfill_combo)
        notes_layout.addWidget(anomalies_widget)

        self._add_form_row(
            form,
            "additional_anomalies",
            self.FIELD_LABELS["additional_anomalies"],
            notes_wrap,
            single_line=False,
        )

        self.additional_quickfill_combo.currentIndexChanged.connect(self._on_additional_quickfill_selected)

        section_layout.addWidget(header)
        section_layout.addWidget(content)
        self.form_layout.addWidget(section)

        self._sections["additional_notes"] = {
            "badge": badge,
            "fields": self._section_fields["additional_notes"],
        }

    def _build_bottom_action_bar(self) -> QFrame:
        bar = QFrame(self)
        bar.setFixedHeight(68)
        bar.setStyleSheet(
            f"background: {C_GREY_LT}; border-top: 1px solid {C_BORDER};"
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(8)

        self.change_summary_label = QLabel("", bar)
        self.change_summary_label.setStyleSheet(f"font-size: 9pt; color: {C_BLUE};")
        self.change_summary_label.setVisible(False)

        self.reset_button = QPushButton("Reset to Original", bar)
        self.reset_button.setObjectName("secondary")
        self.reset_button.setMinimumWidth(140)
        self.reset_button.clicked.connect(self._on_reset_to_original)

        self.cancel_button = QPushButton("Cancel", bar)
        self.cancel_button.setObjectName("secondary")
        self.cancel_button.setMinimumWidth(90)
        self.cancel_button.clicked.connect(self.reject)

        self.save_button = QPushButton("Save Changes", bar)
        self.save_button.setMinimumWidth(130)
        self.save_button.setFixedHeight(40)
        self.save_button.setStyleSheet(
            f"background: {C_BLUE}; color: {C_WHITE}; border: none; border-radius: 6px; font-size: 11pt; font-weight: 700;"
        )
        self.save_button.clicked.connect(self._on_save)

        layout.addWidget(self.change_summary_label)
        layout.addStretch(1)
        layout.addWidget(self.reset_button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.save_button)
        return bar

    def _add_form_row(
        self,
        form_layout: QFormLayout,
        field_key: str,
        label_text: str,
        field_widget: QWidget,
        single_line: bool,
    ) -> None:
        row = QFrame(self.form_container)
        row.setObjectName("form_row")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 2, 8, 2)
        row_layout.setSpacing(12)

        label = QLabel(label_text, row)
        label.setObjectName("field_label")
        label.setFixedWidth(200)
        label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if single_line:
            row.setMinimumHeight(36)
            row.setMaximumHeight(48)

        row_layout.addWidget(label)
        row_layout.addWidget(field_widget, stretch=1)

        form_layout.addRow(row)

        self._field_labels[field_key] = label
        self._field_label_text[field_key] = label_text

    def _build_field_widget(self, field_key: str, allowed_values: list, current_value: str) -> QWidget:
        widget: QWidget

        if field_key == "reason":
            text_edit = QTextEdit(self)
            text_edit.setMinimumHeight(100)
            text_edit.setMaximumHeight(200)
            text_edit.setAcceptRichText(False)
            text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            text_edit.textChanged.connect(self._update_reason_counter)
            text_edit.textChanged.connect(lambda k=field_key: self._on_field_changed(k))
            widget = text_edit
        elif field_key == "additional_anomalies":
            text_edit = QTextEdit(self)
            text_edit.setMinimumHeight(60)
            text_edit.setMaximumHeight(120)
            text_edit.setAcceptRichText(False)
            text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            text_edit.textChanged.connect(lambda k=field_key: self._on_field_changed(k))
            widget = text_edit
        elif field_key == "confidence":
            spin = QDoubleSpinBox(self)
            spin.setObjectName("confidence_spinbox")
            spin.setRange(0.00, 1.00)
            spin.setSingleStep(0.01)
            spin.setDecimals(2)
            spin.setMinimumWidth(100)
            spin.valueChanged.connect(lambda _value, k=field_key: self._on_field_changed(k))
            widget = spin
        elif field_key == "matched_person":
            line_edit = QLineEdit(self)
            line_edit.setPlaceholderText("Enter person name or leave blank")
            line_edit.textChanged.connect(lambda _text, k=field_key: self._on_field_changed(k))
            widget = line_edit
        elif allowed_values and all(isinstance(item, str) for item in allowed_values):
            combo = QComboBox(self)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            for option in allowed_values:
                combo.addItem(option, option)

            display_value = "" if current_value is None else str(current_value)
            if display_value.strip() and self._find_combo_index(combo, display_value) < 0:
                combo.insertItem(0, f"{display_value} (current value — not in standard options)", display_value)
                non_standard_font = QFont(combo.font())
                non_standard_font.setItalic(True)
                combo.setItemData(0, non_standard_font, Qt.ItemDataRole.FontRole)
                combo.setItemData(0, QColor(C_TEXT_SECONDARY), Qt.ItemDataRole.ForegroundRole)
                combo.setCurrentIndex(0)

            combo.currentIndexChanged.connect(lambda _idx, k=field_key: self._on_field_changed(k))
            widget = combo
        else:
            line_edit = QLineEdit(self)
            line_edit.textChanged.connect(lambda _text, k=field_key: self._on_field_changed(k))
            widget = line_edit

        self._field_widgets[field_key] = widget
        base_style = widget.styleSheet()
        self._field_base_styles[field_key] = base_style
        self._field_changed[field_key] = False
        return widget

    def _find_combo_index(self, combo: QComboBox, target_value: str) -> int:
        normalized_target = str(target_value).strip().lower()
        for index in range(combo.count()):
            data_value = combo.itemData(index, Qt.ItemDataRole.UserRole)
            candidate = str(data_value if data_value is not None else combo.itemText(index)).strip().lower()
            if candidate == normalized_target:
                return index
        return -1

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)

    def _set_tab_order(self) -> None:
        order: list[QWidget] = []

        ordered_keys = [
            "result",
            "confidence",
            "matched_person",
            "reason",
            "shape_similarity",
            "stroke_similarity",
            "letter_pattern_similarity",
            "alignment_similarity",
            "stroke_direction_consistency",
            "line_quality_consistency",
            "pen_pressure_consistency",
            "pen_speed_rhythm_consistency",
            "zone_proportion_match",
            "baseline_consistency",
            "slant_angle_consistency",
            "loop_size_and_shape_match",
            "habitual_features_match",
            "entry_stroke_match",
            "exit_stroke_match",
            "pen_lift_position_consistency",
            "paraph_flourish_match",
            "underscore_match",
            "hesitation_marks_detected",
            "retouching_or_patching_detected",
            "forgery_type_suspected",
            "natural_variation_within_expected_range",
            "image_quality_signature_1",
            "image_quality_signature_2",
            "image_quality_impact_on_confidence",
        ]
        for key in ordered_keys:
            widget = self._field_widgets.get(key)
            if widget is not None:
                order.append(widget)

        if self.additional_quickfill_combo is not None:
            order.append(self.additional_quickfill_combo)

        anomalies_widget = self._field_widgets.get("additional_anomalies")
        if anomalies_widget is not None:
            order.append(anomalies_widget)

        if self.reset_button is not None:
            order.append(self.reset_button)
        if self.cancel_button is not None:
            order.append(self.cancel_button)
        if self.save_button is not None:
            order.append(self.save_button)

        for index in range(len(order) - 1):
            self.setTabOrder(order[index], order[index + 1])

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return

        frame = self.frameGeometry()
        frame.moveCenter(parent.frameGeometry().center())
        self.move(frame.topLeft())

    def _initialize_section_heights(self) -> None:
        for section in self._sections.values():
            content = section.get("content")
            if content is None:
                continue
            target = content.sizeHint().height()
            content.setMinimumHeight(0)
            content.setMaximumHeight(max(1, target))

    def _toggle_section(self, section_id: str) -> None:
        section = self._sections.get(section_id)
        if not section:
            return

        content = section.get("content")
        arrow = section.get("arrow")
        animation = section.get("animation")
        expanded = bool(section.get("expanded", True))

        if content is None or arrow is None or animation is None:
            return

        content.setMinimumHeight(0)
        current_height = content.maximumHeight()
        target_height = max(1, content.sizeHint().height())

        animation.stop()
        animation.setDuration(200)

        if expanded:
            animation.setStartValue(current_height if current_height > 0 else target_height)
            animation.setEndValue(0)
            arrow.setText("▶")
            section["expanded"] = False
        else:
            animation.setStartValue(max(0, current_height))
            animation.setEndValue(target_height)
            arrow.setText("▼")
            section["expanded"] = True

        animation.start()

    def _populate_from_data(self) -> None:
        self._suspend_change_tracking = True
        try:
            data = self.result_dict or {}
            obs = data.get("observations", {})
            if not isinstance(obs, dict):
                obs = {}

            self._set_widget_value("result", data.get("verdict") or data.get("result", "INCONCLUSIVE"))
            self._set_widget_value("confidence", float(data.get("confidence", 0.5) or 0.5))
            self._set_widget_value("matched_person", data.get("matched_person") or "")
            self._set_widget_value("reason", data.get("reason") or "")

            for key in self.OBSERVATION_KEYS:
                if key in self._field_widgets:
                    self._set_widget_value(key, obs.get(key, ""))

            self._original_values = self._collect_widget_values()
            self._has_unsaved_changes = False
        finally:
            self._suspend_change_tracking = False

        self._update_reason_counter()
        self._on_verdict_changed()
        confidence_value = float(self._get_widget_value("confidence") or 0.0)
        self._on_confidence_changed(confidence_value)
        self._refresh_change_states()

    def _set_widget_value(self, field_key: str, value) -> None:
        widget = self._field_widgets.get(field_key)
        if widget is None:
            return

        try:
            if isinstance(widget, QComboBox):
                normalized = "" if value is None else str(value).strip()
                index = self._find_combo_index(widget, normalized)
                if index >= 0:
                    widget.setCurrentIndex(index)
                else:
                    display_text = normalized
                    widget.insertItem(0, f"{display_text} (current value — not in standard options)", display_text)
                    item_font = QFont(widget.font())
                    item_font.setItalic(True)
                    widget.setItemData(0, item_font, Qt.ItemDataRole.FontRole)
                    widget.setItemData(0, QColor(C_TEXT_SECONDARY), Qt.ItemDataRole.ForegroundRole)
                    widget.setCurrentIndex(0)
            elif isinstance(widget, QTextEdit):
                widget.setPlainText("" if value is None else str(value))
            elif isinstance(widget, QLineEdit):
                widget.setText("" if value is None else str(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
        except Exception as exc:
            logger.warning("Failed to set widget value for %s: %s", field_key, exc)

    def _get_widget_value(self, field_key: str):
        widget = self._field_widgets.get(field_key)
        if widget is None:
            return ""

        if isinstance(widget, QComboBox):
            data_value = widget.currentData(Qt.ItemDataRole.UserRole)
            if data_value is not None:
                return str(data_value)
            return widget.currentText().strip()
        if isinstance(widget, QTextEdit):
            return widget.toPlainText().strip()
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        if isinstance(widget, QDoubleSpinBox):
            return widget.value()
        return ""

    def _collect_widget_values(self) -> dict[str, str | float]:
        values: dict[str, str | float] = {}
        for key in self._field_widgets:
            values[key] = self._get_widget_value(key)
        return values

    def _collect_all_values(self) -> dict:
        result_value = str(self._get_widget_value("result") or "INCONCLUSIVE").upper()
        confidence_value = float(self._get_widget_value("confidence") or 0.0)
        is_match = result_value == "MATCH"

        observations = {}
        for key in self.OBSERVATION_KEYS:
            observations[key] = self._get_widget_value(key)

        return {
            "is_match": is_match,
            "result": result_value,
            "verdict": result_value,
            "confidence": confidence_value,
            "matched_person": self._get_widget_value("matched_person") or None,
            "reason": self._get_widget_value("reason"),
            "observations": observations,
            "model_used": self.result_dict.get("model_used", "SignVerify-Pro"),
            "raw_response": self.result_dict.get("raw_response", ""),
        }

    def _update_reason_counter(self) -> None:
        if self.reason_counter_label is None:
            return

        reason_text = str(self._get_widget_value("reason") or "")
        count = len(reason_text)
        self.reason_counter_label.setText(f"{count} / 2000 characters")
        color = C_DANGER if count > 2000 else C_TEXT_SECONDARY
        self.reason_counter_label.setStyleSheet(f"font-size: 8.5pt; color: {color};")

    def _on_additional_quickfill_selected(self, index: int) -> None:
        if index < 0 or self.additional_quickfill_combo is None:
            return

        selected = self.additional_quickfill_combo.currentText().strip()
        text_widget = self._field_widgets.get("additional_anomalies")
        if not isinstance(text_widget, QTextEdit):
            return

        if selected == "Custom...":
            text_widget.setFocus()
        elif selected:
            text_widget.setPlainText(selected)
            text_widget.setFocus()

        QTimer.singleShot(0, lambda: self.additional_quickfill_combo.setCurrentIndex(-1))

    def _on_field_changed(self, field_key: str) -> None:
        if self._suspend_change_tracking:
            return

        _ = field_key
        self._refresh_change_states()

    def _refresh_change_states(self) -> None:
        total_changed = 0

        for key, widget in self._field_widgets.items():
            current_value = self._get_widget_value(key)
            original_value = self._original_values.get(key, "")
            is_changed = str(current_value) != str(original_value)

            self._field_changed[key] = is_changed
            self._apply_widget_changed_style(key, widget, is_changed)
            self._apply_label_changed_style(key, is_changed)

            if is_changed:
                total_changed += 1

        self._has_unsaved_changes = total_changed > 0

        if self.change_summary_label is not None:
            if total_changed > 0:
                self.change_summary_label.setText(f"● {total_changed} field(s) modified")
                self.change_summary_label.setVisible(True)
            else:
                self.change_summary_label.setVisible(False)

        self._update_section_change_badges()

    def _apply_widget_changed_style(self, field_key: str, widget: QWidget, is_changed: bool) -> None:
        base_style = self._field_base_styles.get(field_key, "")
        changed_style = f"border-left: 3px solid {C_BLUE};"

        if is_changed:
            widget.setStyleSheet(f"{base_style}{changed_style}")
        else:
            widget.setStyleSheet(base_style)

    def _apply_label_changed_style(self, field_key: str, is_changed: bool) -> None:
        label = self._field_labels.get(field_key)
        base_text = self._field_label_text.get(field_key, "")
        if label is None:
            return

        if is_changed:
            label.setText(f"<span style='color:{C_BLUE};'>●</span> {base_text}")
        else:
            label.setText(base_text)

    def _update_section_change_badges(self) -> None:
        for section in self._sections.values():
            badge = section.get("badge")
            fields = section.get("fields", [])
            if badge is None:
                continue

            changed_count = 0
            for key in fields:
                if self._field_changed.get(key, False):
                    changed_count += 1

            if changed_count > 0:
                badge.setText(f"{changed_count} changed")
                badge.setVisible(True)
            else:
                badge.setVisible(False)

    def _on_verdict_changed(self) -> None:
        verdict = str(self._get_widget_value("result") or "INCONCLUSIVE").upper()

        if self.verdict_dot_label is not None:
            if verdict == "MATCH":
                color = C_SUCCESS
                hint = "→ MATCH range"
            elif verdict == "MISMATCH":
                color = C_DANGER
                hint = "→ MISMATCH range"
            else:
                color = C_AMBER
                hint = "→ INCONCLUSIVE range"

            self.verdict_dot_label.setStyleSheet(f"color: {color}; font-size: 11pt;")

            if self.confidence_hint_label is not None:
                self.confidence_hint_label.setText(hint)
                self.confidence_hint_label.setStyleSheet(f"font-size: 8.5pt; color: {color};")

    def _on_confidence_changed(self, value: float) -> None:
        if self.confidence_hint_label is None:
            return

        if value <= 0.49:
            text = "→ MISMATCH range"
            color = C_DANGER
        elif value <= 0.65:
            text = "→ INCONCLUSIVE range"
            color = C_AMBER
        elif value <= 0.85:
            text = "→ MATCH (Probable) range"
            color = "#6AA84F"
        else:
            text = "→ MATCH (Strong) range"
            color = C_SUCCESS

        self.confidence_hint_label.setText(text)
        self.confidence_hint_label.setStyleSheet(f"font-size: 8.5pt; color: {color};")

    def _on_reset_to_original(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Reset Changes",
            "Reset all changes? This will undo all edits in this session.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._suspend_change_tracking = True
        try:
            for key, value in self._original_values.items():
                self._set_widget_value(key, value)
        finally:
            self._suspend_change_tracking = False

        self._update_reason_counter()
        self._on_verdict_changed()
        confidence_value = float(self._get_widget_value("confidence") or 0.0)
        self._on_confidence_changed(confidence_value)
        self._refresh_change_states()

    def _on_save(self) -> None:
        new_result = self._collect_all_values()

        if not str(new_result.get("reason", "")).strip():
            QMessageBox.warning(self, "Required Field", "The Forensic Reason field cannot be empty.")
            return

        if not new_result.get("result"):
            QMessageBox.warning(self, "Required Field", "Verdict must be selected.")
            return

        new_observations_json = json.dumps(new_result["observations"], ensure_ascii=False, indent=2)
        new_raw_response_json = json.dumps(new_result, ensure_ascii=False, indent=2)
        new_response_hash = hashlib.sha256(new_raw_response_json.encode("utf-8")).hexdigest()

        try:
            if self.verification is None or getattr(self.verification, "id", None) is None:
                QMessageBox.critical(self, "Database Error", "Verification record ID is unavailable.")
                return

            from database.db_manager import SessionLocal
            from models.verification import Verification

            with SessionLocal() as session:
                verification = session.get(Verification, self.verification.id)
                if verification is None:
                    QMessageBox.critical(
                        self,
                        "Database Error",
                        f"Verification record #{self.verification.id} not found in database.",
                    )
                    return

                verification.verdict = new_result["result"]
                verification.is_match = 1 if new_result["is_match"] else 0
                verification.confidence = float(new_result["confidence"])
                verification.reason = new_result["reason"]
                verification.observations_json = new_observations_json
                verification.raw_response_json = new_raw_response_json
                verification.response_hash = new_response_hash

                session.commit()
                session.refresh(verification)
                self._saved_verification = verification

            logger.info(
                "Verification #%s updated successfully: verdict=%s, confidence=%.3f",
                self.verification.id,
                new_result["result"],
                float(new_result["confidence"]),
            )
        except Exception as exc:
            logger.error("Failed to save verification edit: %s", exc, exc_info=True)
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not save changes to database.\n\nError: {str(exc)}\n\nPlease try again.",
            )
            return

        self._saved_result_dict = new_result
        self.accept()

    def get_saved_result_dict(self) -> dict:
        return self._saved_result_dict or {}

    def get_saved_verification(self):
        return self._saved_verification

    def reject(self) -> None:
        if self._has_unsaved_changes:
            confirm = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Close without saving?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        super().reject()
