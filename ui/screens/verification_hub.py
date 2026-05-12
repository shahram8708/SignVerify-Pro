"""Verification hub screen for selecting person and verification mode."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import (
    C_BLUE,
    C_BLUE_TINT,
    C_BLUE_TINT_STRONG,
    C_BORDER,
    C_GOLD,
    C_INFO_BORDER,
    C_NAVY,
    C_TEXT_PRIMARY,
    C_TEXT_SECONDARY,
    C_WHITE,
    SEED_SIGNATURES_DIR,
)
from controllers.database_controller import database_controller
from controllers.navigation_controller import NavigationController
from models.person import Person
from models.verification import Verification
from ui.base_screen import BaseScreen
from utils.logger import get_logger

logger = get_logger(__name__)


class ModeCard(QFrame):
    """Interactive mode selection card with hover and press effects."""

    clicked = pyqtSignal(str)

    def __init__(
        self,
        mode_key: str,
        icon_text: str,
        title: str,
        subtitle: str,
        description: str,
        tags: tuple[str, str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.mode_key = mode_key
        self._is_hovered = False

        self.setMinimumSize(220, 180)
        self.setMaximumWidth(260)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(10)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.setGraphicsEffect(shadow)
        self._shadow = shadow

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        icon = QLabel(icon_text, self)
        icon_font = QFont(self.font())
        icon_font.setPointSize(32)
        icon.setFont(icon_font)
        icon.setAlignment(Qt.AlignmentFlag.AlignLeft)

        title_label = QLabel(title, self)
        title_label.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        subtitle_label = QLabel(subtitle, self)
        subtitle_label.setStyleSheet(
            f"background: {C_GOLD}; color: {C_NAVY}; font-size: 9pt; font-weight: 700; "
            "padding: 3px 8px; border-radius: 10px;"
        )
        subtitle_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        description_label = QLabel(description, self)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        tags_row = QHBoxLayout()
        tags_row.setSpacing(6)
        for tag in tags:
            tag_label = QLabel(tag, self)
            tag_label.setStyleSheet(
                f"background: {C_BLUE_TINT}; border: 1px solid {C_BORDER}; color: {C_TEXT_SECONDARY}; "
                "font-size: 8pt; padding: 2px 6px; border-radius: 8px;"
            )
            tag_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            tags_row.addWidget(tag_label)

        tags_row.addStretch(1)

        layout.addWidget(icon)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(description_label)
        layout.addStretch(1)
        layout.addLayout(tags_row)

        self._apply_card_style(state="default")

    def _apply_card_style(self, state: str) -> None:
        if state == "hover":
            background = C_BLUE_TINT
            border_width = 2
            border_color = C_BLUE
            self._shadow.setBlurRadius(16)
            self._shadow.setOffset(0, 4)
        elif state == "press":
            background = C_BLUE_TINT_STRONG
            border_width = 2
            border_color = C_BLUE
            self._shadow.setBlurRadius(16)
            self._shadow.setOffset(0, 4)
        else:
            background = C_WHITE
            border_width = 1
            border_color = C_BORDER
            self._shadow.setBlurRadius(10)
            self._shadow.setOffset(0, 3)

        self.setStyleSheet(
            f"""
            QFrame {{
                background: {background};
                border: {border_width}px solid {border_color};
                border-radius: 12px;
            }}
            """
        )

    def enterEvent(self, event) -> None:  # noqa: N802
        self._is_hovered = True
        self._apply_card_style(state="hover")
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._is_hovered = False
        self._apply_card_style(state="default")
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._apply_card_style(state="press")

            def _emit_click() -> None:
                self._apply_card_style(state="hover" if self._is_hovered else "default")
                self.clicked.emit(self.mode_key)

            QTimer.singleShot(150, _emit_click)
        super().mousePressEvent(event)


class VerificationHubScreen(BaseScreen):
    """Screen that allows users to choose verification person and mode."""

    def __init__(self, parent=None) -> None:
        self._person_by_id: dict[int, Person] = {}
        super().__init__(parent)

    def _build_ui(self) -> None:
        self.content_layout.setContentsMargins(24, 20, 24, 20)
        self.content_layout.setSpacing(14)

        header_title = QLabel("Start Verification", self)
        header_title.setStyleSheet(f"font-size: 20pt; font-weight: 700; color: {C_NAVY};")

        header_subtitle = QLabel(
            "Select a verification mode and choose the person to verify against.",
            self,
        )
        header_subtitle.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background: {C_BORDER}; max-height: 1px;")

        self.content_layout.addWidget(header_title)
        self.content_layout.addWidget(header_subtitle)
        self.content_layout.addWidget(divider)

        self._build_person_selector_row()
        self._build_mode_cards_row()
        self._build_info_panel()
        self._build_test_button_row()

    def _build_person_selector_row(self) -> None:
        row = QWidget(self)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        label = QLabel("Verify Against:", row)
        label.setStyleSheet(f"font-size: 10pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

        self.person_dropdown = QComboBox(row)
        self.person_dropdown.setObjectName("person_dropdown")
        self.person_dropdown.setEditable(True)
        self.person_dropdown.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.person_dropdown.setMinimumWidth(300)
        self.person_dropdown.currentIndexChanged.connect(self._on_person_selection_changed)
        completer = self.person_dropdown.completer()
        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        add_btn = QPushButton("＋ Add New Person", row)
        add_btn.setObjectName("secondary")
        add_btn.setFixedHeight(30)
        add_btn.clicked.connect(
            lambda: NavigationController.get_instance().navigate_to("database", open_add_dialog=True)
        )

        self.person_thumbnail = QLabel("No signature on file", row)
        self.person_thumbnail.setFixedSize(80, 40)
        self.person_thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.person_thumbnail.setStyleSheet(
            f"background: {C_BLUE_TINT}; border: 1px solid {C_BORDER}; color: {C_TEXT_SECONDARY}; "
            "font-size: 8pt;"
        )

        self.person_info_label = QLabel("", row)
        self.person_info_label.setStyleSheet(f"font-size: 8.5pt; color: {C_TEXT_SECONDARY};")
        self.person_info_label.setMinimumWidth(220)

        row_layout.addWidget(label)
        row_layout.addWidget(self.person_dropdown)
        row_layout.addWidget(add_btn)
        row_layout.addWidget(self.person_thumbnail)
        row_layout.addWidget(self.person_info_label, 1)

        self.content_layout.addWidget(row)

    def _build_mode_cards_row(self) -> None:
        cards_row = QWidget(self)
        cards_layout = QHBoxLayout(cards_row)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(14)

        self.mode_a_card = ModeCard(
            mode_key="mode_a",
            icon_text="🖥",
            title="Screen Detection",
            subtitle="Mode A",
            description=(
                "Automatically detect and capture a signature from any visible "
                "screen region using AI-powered computer vision."
            ),
            tags=("⚡ Auto-Detect", "📐 Manual Crop Fallback"),
            parent=cards_row,
        )
        self.mode_a_card.clicked.connect(self._on_mode_card_clicked)

        self.mode_b_card = ModeCard(
            mode_key="mode_b",
            icon_text="📷",
            title="Upload or Camera",
            subtitle="Mode B",
            description=(
                "Upload a scanned signature image from your file system or capture "
                "it live using your webcam or document camera."
            ),
            tags=("📁 File Upload", "📷 Live Camera"),
            parent=cards_row,
        )
        self.mode_b_card.clicked.connect(self._on_mode_card_clicked)

        self.mode_c_card = ModeCard(
            mode_key="mode_c",
            icon_text="⚖",
            title="Ad-Hoc Compare",
            subtitle="Mode C",
            description=(
                "Compare any two signature images directly without a database lookup. "
                "Ideal for one-off forensic comparisons."
            ),
            tags=("🔄 No DB Required", "📁 Any Two Images"),
            parent=cards_row,
        )
        self.mode_c_card.clicked.connect(self._on_mode_card_clicked)

        cards_layout.addWidget(self.mode_a_card, 1)
        cards_layout.addWidget(self.mode_b_card, 1)
        cards_layout.addWidget(self.mode_c_card, 1)

        self.content_layout.addWidget(cards_row)

    def _build_info_panel(self) -> None:
        info_frame = QFrame(self)
        info_frame.setStyleSheet(
            f"""
            QFrame {{
                background: {C_BLUE_TINT_STRONG};
                border: 1px solid {C_INFO_BORDER};
                border-radius: 8px;
                padding: 12px;
            }}
            """
        )
        info_layout = QHBoxLayout(info_frame)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(8)

        icon = QLabel("ℹ", info_frame)
        icon.setStyleSheet(f"font-size: 13pt; color: {C_BLUE}; font-weight: 700;")

        text = QLabel(
            "Modes A and B compare the selected person's stored reference signature against a "
            "new signature. Mode C compares any two signatures directly. All verifications are "
            "logged automatically.",
            info_frame,
        )
        text.setWordWrap(True)
        text.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        info_layout.addWidget(icon)
        info_layout.addWidget(text, 1)
        self.content_layout.addWidget(info_frame)

    def _build_test_button_row(self) -> None:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.test_result_button = QPushButton("Test Result Screen", row)
        self.test_result_button.setObjectName("secondary")
        self.test_result_button.setFixedHeight(22)
        self.test_result_button.setStyleSheet(f"font-size: 7.5pt; color: {C_TEXT_SECONDARY};")
        self.test_result_button.clicked.connect(self._open_test_result_screen)

        show_test_button = os.getenv("SIGNVERIFY_SHOW_TEST_BUTTON", "0").strip() == "1"
        self.test_result_button.setVisible(show_test_button)

        layout.addWidget(self.test_result_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        self.content_layout.addWidget(row)

    def _populate_person_dropdown(self, preselect_person_id: int | None = None) -> None:
        self.person_dropdown.blockSignals(True)
        self.person_dropdown.clear()
        self._person_by_id.clear()

        self.person_dropdown.addItem("— Select a person (required for Modes A and B) —")
        self.person_dropdown.setItemData(0, None, Qt.ItemDataRole.UserRole)

        all_persons = database_controller.get_all_persons()
        selected_index = 0

        for person in all_persons:
            self._person_by_id[person.id] = person
            self.person_dropdown.addItem(person.full_name)
            index = self.person_dropdown.count() - 1
            self.person_dropdown.setItemData(index, person.id, Qt.ItemDataRole.UserRole)
            if preselect_person_id is not None and person.id == preselect_person_id:
                selected_index = index

        self.person_dropdown.setCurrentIndex(selected_index)
        self.person_dropdown.blockSignals(False)
        self._on_person_selection_changed()

    def _set_thumbnail_placeholder(self) -> None:
        self.person_thumbnail.clear()
        self.person_thumbnail.setText("No signature on file")
        self.person_thumbnail.setStyleSheet(
            f"background: {C_BLUE_TINT}; border: 1px solid {C_BORDER}; color: {C_TEXT_SECONDARY}; "
            "font-size: 8pt;"
        )

    def _on_person_selection_changed(self) -> None:
        person_id = self.person_dropdown.currentData(Qt.ItemDataRole.UserRole)
        if person_id is None:
            self._set_thumbnail_placeholder()
            self.person_info_label.setText("No person selected")
            return

        person = self._person_by_id.get(int(person_id))
        if person is None:
            self._set_thumbnail_placeholder()
            self.person_info_label.setText("Person record not found")
            return

        if person.thumbnail_blob:
            pixmap = QPixmap()
            loaded = pixmap.loadFromData(person.thumbnail_blob)
            if loaded:
                scaled = pixmap.scaled(
                    self.person_thumbnail.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.person_thumbnail.setText("")
                self.person_thumbnail.setPixmap(scaled)
                self.person_thumbnail.setStyleSheet(
                    f"background: {C_WHITE}; border: 1px solid {C_BORDER};"
                )
            else:
                self._set_thumbnail_placeholder()
        else:
            self._set_thumbnail_placeholder()

        added_on = person.created_at.strftime("%d %b %Y") if person.created_at else "Unknown"
        self.person_info_label.setText(f"{person.full_name}\nDate added: {added_on}")

    def _get_selected_person_id(self) -> int | None:
        person_id = self.person_dropdown.currentData(Qt.ItemDataRole.UserRole)
        if person_id is None:
            return None
        try:
            return int(person_id)
        except (TypeError, ValueError):
            return None

    def _get_selected_person_name(self) -> str | None:
        name = self.person_dropdown.currentText().strip()
        return name or None

    def _on_mode_card_clicked(self, mode_key: str) -> None:
        selected_person_id = self._get_selected_person_id()
        selected_person_name = self._get_selected_person_name()

        if mode_key == "mode_a":
            if selected_person_id is None:
                QMessageBox.warning(
                    self,
                    "Person Required",
                    "Please select a person before using Mode A",
                )
                return

            NavigationController.get_instance().navigate_to(
                "mode_a",
                person_id=selected_person_id,
                person_name=selected_person_name,
            )
            return

        if mode_key == "mode_b":
            if selected_person_id is None:
                QMessageBox.warning(
                    self,
                    "Person Required",
                    "Please select a person before using Mode B",
                )
                return

            NavigationController.get_instance().navigate_to(
                "mode_b",
                person_id=selected_person_id,
                person_name=selected_person_name,
            )
            return

        NavigationController.get_instance().navigate_to("mode_c")

    def _first_seed_image(self) -> str:
        for pattern in ("*.png", "*.jpg", "*.jpeg"):
            matches = sorted(SEED_SIGNATURES_DIR.glob(pattern))
            if matches:
                return str(matches[0])
        return ""

    def _open_test_result_screen(self) -> None:
        observation_keys = [
            "overall_gestalt",
            "pen_lift_points",
            "letter_formation",
            "baseline_consistency",
            "slant_angle",
            "pressure_pattern",
            "speed_indicators",
            "loop_proportions",
            "beginning_strokes",
            "ending_strokes",
            "connecting_strokes",
            "abbreviation_style",
            "flourish_patterns",
            "ink_distribution",
            "stroke_consistency",
            "spatial_proportions",
            "retouching_indicators",
            "tremor_assessment",
            "natural_variation",
            "complexity_level",
            "character_spacing",
            "terminal_features",
            "size_consistency",
            "rhythm_pattern",
            "overall_similarity",
        ]
        observations = {key: "High" for key in observation_keys}
        reason = (
            "Both signatures exhibit strong concordance across critical forensic dimensions, "
            "including baseline consistency, stroke rhythm, slant angle, and connecting stroke behavior. "
            "No significant tremor, retouching, or terminal feature divergence was observed. "
            "Natural variation appears controlled and consistent with genuine within-writer variation. "
            "The totality of findings supports a match conclusion."
        )

        sample_image = self._first_seed_image()
        result_dict = {
            "verdict": "MATCH",
            "confidence": 0.87,
            "reason": reason,
            "observations": observations,
            "model_used": "SignVerify-SiameseResNet50-v1.0",
            "analysis_time_sec": 11.2,
            "image_quality": "High",
        }

        mock_verification = Verification(
            person_id=None,
            mode="C_ADHOC",
            reference_image_path=sample_image,
            submitted_image_path=sample_image,
            verdict="MATCH",
            is_match=1,
            confidence=0.87,
            reason=reason,
            observations_json=json.dumps(observations),
            raw_response_json=json.dumps(result_dict),
            verified_at=datetime.utcnow(),
            flagged_for_review=0,
            exported=0,
            response_hash="mock_response_hash",
        )

        NavigationController.get_instance().navigate_to(
            "results",
            result_dict=result_dict,
            verification=mock_verification,
            person=None,
        )

    def on_show(self, **kwargs) -> None:
        preselect_person_id = kwargs.get("person_id")
        if preselect_person_id is not None:
            try:
                preselect_person_id = int(preselect_person_id)
            except (TypeError, ValueError):
                preselect_person_id = None

        self._populate_person_dropdown(preselect_person_id=preselect_person_id)
        logger.info("VerificationHubScreen shown")
