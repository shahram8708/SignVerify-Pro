"""Mode A screen implementation for screen-based signature detection."""

from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QRect, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config import (
    APP_DATA_DIR,
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
    resolve_signature_path,
)
from controllers.database_controller import database_controller
from controllers.navigation_controller import NavigationController
from controllers.verification_controller import VerificationController
from services.window_capture_worker import CaptureWorker
from services.window_enumerator import WINDOW_CLOSED_SENTINEL, WindowInfo
from ui.base_screen import BaseScreen
from ui.dialogs.crop_dialog import CropDialog
from ui.dialogs.window_picker_dialog import WindowPickerDialog
from ui.widgets.signature_preview_label import SignaturePreviewLabel
from utils.logger import get_logger

logger = get_logger(__name__)


class DetectionPreviewLabel(QLabel):
    """Screenshot preview with optional detection overlays."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(280)
        self.setStyleSheet(
            f"border: 1px solid {C_BORDER}; background: {C_GREY_LT}; color: {C_TEXT_SECONDARY};"
        )
        self.setText("Screenshot captured — click Detect to analyse.")

        self._source_pixmap: QPixmap | None = None
        self._detections: list[dict] = []

    def set_source_pixmap(self, pixmap: QPixmap | None) -> None:
        self._source_pixmap = QPixmap(pixmap) if pixmap is not None else None
        self.update()

    def set_detections(self, detections: list[dict]) -> None:
        self._detections = detections or []
        self.update()

    def clear(self) -> None:
        self._source_pixmap = None
        self._detections = []
        self.setText("Screenshot captured — click Detect to analyse.")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._source_pixmap is None or self._source_pixmap.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(C_GREY_LT))

        scaled = self._source_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        draw_x = (self.width() - scaled.width()) // 2
        draw_y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(draw_x, draw_y, scaled)

        if scaled.width() <= 0 or scaled.height() <= 0:
            return

        scale_factor = scaled.width() / float(max(1, self._source_pixmap.width()))

        rank_colors = {1: QColor(C_SUCCESS), 2: QColor(C_BLUE), 3: QColor(C_GOLD)}
        for index, detection in enumerate(self._detections[:3], start=1):
            rank = int(detection.get("rank", index))
            color = rank_colors.get(rank, QColor(C_BLUE))

            x = draw_x + int(round(int(detection.get("x", 0)) * scale_factor))
            y = draw_y + int(round(int(detection.get("y", 0)) * scale_factor))
            width = int(round(int(detection.get("width", 0)) * scale_factor))
            height = int(round(int(detection.get("height", 0)) * scale_factor))

            pen = QPen(color, 2)
            pen.setDashPattern([6, 3])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(x, y, width, height)

            badge_text = f"#{rank}"
            badge_rect = QRect(x, max(draw_y, y - 18), 26, 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(badge_rect, 5, 5)
            painter.setPen(QColor(C_WHITE))
            badge_font = QFont(self.font())
            badge_font.setPointSize(8)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)


class ModeAScreen(BaseScreen):
    """Mode A workflow: capture screen, detect signature, review crop, and verify."""

    STEP_LABELS = ["Select Window", "Detect Signature", "Review Crop", "Verify"]

    def __init__(self, parent=None) -> None:
        self.person_id: int | None = None
        self.person_name: str | None = None
        self.screenshot: Image.Image | None = None
        self.detections: list[dict] = []
        self.cropped_image: Image.Image | None = None
        self.cropped_image_path: str | None = None
        self.current_step = 1
        self.detection_worker = None
        self.local_model_worker = None
        self.capture_worker: CaptureWorker | None = None
        self.current_quality = None
        self.reference_image_path: str = ""
        self.selected_window_info: WindowInfo | None = None
        self.selected_window_thumbnail: Image.Image | None = None
        self.capture_source_context: str = "No source selected"

        super().__init__(parent)

    def _build_ui(self) -> None:
        self.content_layout.setContentsMargins(18, 16, 18, 16)
        self.content_layout.setSpacing(12)

        title = QLabel("Mode A — Screen-Based Signature Detection", self)
        title.setStyleSheet(f"font-size: 18pt; font-weight: 700; color: {C_NAVY};")
        self.content_layout.addWidget(title)

        self._build_step_indicator()
        self._build_person_info_bar()
        self._build_steps_stack()

    def _build_step_indicator(self) -> None:
        container = QFrame(self)
        container.setStyleSheet(
            f"background: {C_WHITE}; border: 1px solid {C_BORDER}; border-radius: 10px;"
        )
        layout = QHBoxLayout(container)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)

        self.step_circles: list[QLabel] = []
        self.step_texts: list[QLabel] = []
        self.step_connectors: list[QFrame] = []

        for index, step_name in enumerate(self.STEP_LABELS, start=1):
            node = QWidget(container)
            node_layout = QVBoxLayout(node)
            node_layout.setContentsMargins(0, 0, 0, 0)
            node_layout.setSpacing(6)

            circle = QLabel(str(index), node)
            circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            circle.setFixedSize(32, 32)

            label = QLabel(step_name, node)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            node_layout.addWidget(circle, alignment=Qt.AlignmentFlag.AlignCenter)
            node_layout.addWidget(label)

            self.step_circles.append(circle)
            self.step_texts.append(label)

            layout.addWidget(node)
            if index < len(self.STEP_LABELS):
                connector = QFrame(container)
                connector.setFrameShape(QFrame.Shape.HLine)
                connector.setFixedHeight(2)
                connector.setStyleSheet(f"background: {C_BORDER}; border: none;")
                self.step_connectors.append(connector)
                layout.addWidget(connector, 1)

        self.content_layout.addWidget(container)

    def _build_person_info_bar(self) -> None:
        frame = QFrame(self)
        frame.setStyleSheet(
            f"background: {C_GREY_LT}; border: 1px solid {C_BORDER}; border-radius: 8px;"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        left_label = QLabel("Verifying Against:", frame)
        left_label.setStyleSheet(f"font-size: 9pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

        self.person_preview = SignaturePreviewLabel(frame)
        self.person_preview.setFixedSize(120, 50)
        self.person_preview.setAcceptDrops(False)
        self.person_preview.setCursor(Qt.CursorShape.ArrowCursor)

        self.person_name_label = QLabel("", frame)
        self.person_name_label.setStyleSheet(f"font-size: 12pt; font-weight: 700; color: {C_NAVY};")

        change_button = QPushButton("Change Person", frame)
        change_button.setObjectName("secondary")
        change_button.clicked.connect(
            lambda: NavigationController.get_instance().navigate_to("verification")
        )

        layout.addWidget(left_label)
        layout.addWidget(self.person_preview)
        layout.addWidget(self.person_name_label)
        layout.addStretch(1)
        layout.addWidget(change_button)

        self.content_layout.addWidget(frame)

    def _build_steps_stack(self) -> None:
        self.steps_stack = QStackedWidget(self)
        self.steps_stack.addWidget(self._build_step1_widget())
        self.steps_stack.addWidget(self._build_step2_widget())
        self.steps_stack.addWidget(self._build_step3_widget())
        self.steps_stack.addWidget(self._build_step4_widget())
        self.content_layout.addWidget(self.steps_stack, 1)

    def _build_step1_widget(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        title = QLabel("Step 1: Select Application Window", step)
        title.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        desc = QLabel(
            "Choose which application window contains the signature document you want to scan.",
            step,
        )
        desc.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.window_preview_frame = QFrame(step)
        self.window_preview_frame.setMinimumHeight(180)
        self.window_preview_frame.setStyleSheet(
            f"background: {C_GREY_LT}; border: 1px solid {C_BORDER}; border-radius: 8px;"
        )
        preview_layout = QVBoxLayout(self.window_preview_frame)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)

        self.step1_preview_stack = QStackedWidget(self.window_preview_frame)

        self.step1_empty_widget = QWidget(self.step1_preview_stack)
        empty_layout = QVBoxLayout(self.step1_empty_widget)
        empty_layout.setContentsMargins(0, 10, 0, 10)
        empty_layout.setSpacing(4)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_icon = QLabel("🪟", self.step1_empty_widget)
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setStyleSheet("font-size: 32pt;")

        empty_title = QLabel("No window selected", self.step1_empty_widget)
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet(f"font-size: 12pt; font-weight: 700; color: {C_NAVY};")

        empty_subtitle = QLabel(
            "Click 'Select Window' below to choose an application",
            self.step1_empty_widget,
        )
        empty_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_subtitle.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        empty_layout.addWidget(empty_icon)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_subtitle)

        self.step1_selected_widget = QWidget(self.step1_preview_stack)
        selected_layout = QHBoxLayout(self.step1_selected_widget)
        selected_layout.setContentsMargins(0, 0, 0, 0)
        selected_layout.setSpacing(12)

        self.step1_selected_thumb_label = QLabel(self.step1_selected_widget)
        self.step1_selected_thumb_label.setFixedSize(240, 140)
        self.step1_selected_thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step1_selected_thumb_label.setStyleSheet(
            f"background: {C_WHITE}; border: 1px solid {C_BORDER}; border-radius: 6px;"
        )

        selected_info_wrap = QWidget(self.step1_selected_widget)
        selected_info_layout = QVBoxLayout(selected_info_wrap)
        selected_info_layout.setContentsMargins(0, 4, 0, 4)
        selected_info_layout.setSpacing(4)

        selected_title_row = QHBoxLayout()
        selected_title_row.setContentsMargins(0, 0, 0, 0)
        selected_title_row.setSpacing(6)

        self.step1_selected_icon_label = QLabel(selected_info_wrap)
        self.step1_selected_icon_label.setFixedSize(24, 24)
        self.step1_selected_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step1_selected_icon_label.setStyleSheet(
            f"background: {C_BLUE}; color: {C_WHITE}; border-radius: 5px; font-size: 8pt; font-weight: 700;"
        )
        self.step1_selected_icon_label.setText("APP")

        self.step1_selected_title_label = QLabel("", selected_info_wrap)
        self.step1_selected_title_label.setStyleSheet(
            f"font-size: 14pt; font-weight: 700; color: {C_NAVY};"
        )

        selected_title_row.addWidget(self.step1_selected_icon_label)
        selected_title_row.addWidget(self.step1_selected_title_label, 1)

        self.step1_selected_process_label = QLabel("", selected_info_wrap)
        self.step1_selected_process_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.step1_selected_size_label = QLabel("", selected_info_wrap)
        self.step1_selected_size_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.step1_selected_minimized_label = QLabel(
            "⚠ This window is currently minimised. It will be restored briefly during capture.",
            selected_info_wrap,
        )
        self.step1_selected_minimized_label.setStyleSheet(f"font-size: 9pt; color: {C_AMBER};")

        self.step1_selected_status_label = QLabel("✓ Window Selected", selected_info_wrap)
        self.step1_selected_status_label.setStyleSheet(
            "font-size: 9pt; font-weight: 700; color: #2E7D32;"
        )

        selected_info_layout.addLayout(selected_title_row)
        selected_info_layout.addWidget(self.step1_selected_process_label)
        selected_info_layout.addWidget(self.step1_selected_size_label)
        selected_info_layout.addWidget(self.step1_selected_minimized_label)
        selected_info_layout.addWidget(self.step1_selected_status_label)
        selected_info_layout.addStretch(1)

        selected_layout.addWidget(self.step1_selected_thumb_label)
        selected_layout.addWidget(selected_info_wrap, 1)

        self.step1_preview_stack.addWidget(self.step1_empty_widget)
        self.step1_preview_stack.addWidget(self.step1_selected_widget)
        preview_layout.addWidget(self.step1_preview_stack)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        self.select_window_button = QPushButton("🪟 Select Window...", step)
        self.select_window_button.setMinimumWidth(200)
        self.select_window_button.setFixedHeight(44)
        self.select_window_button.setStyleSheet(
            f"QPushButton {{ background: {C_BLUE}; color: {C_WHITE}; font-size: 11pt; font-weight: 700; border: none; border-radius: 6px; }}"
        )
        self.select_window_button.clicked.connect(self._open_window_picker)

        self.clear_window_selection_button = QPushButton("✕ Clear Selection", step)
        self.clear_window_selection_button.setObjectName("secondary")
        self.clear_window_selection_button.setVisible(False)
        self.clear_window_selection_button.clicked.connect(self._clear_window_selection)

        action_row.addWidget(self.select_window_button)
        action_row.addWidget(self.clear_window_selection_button)
        action_row.addStretch(1)

        self.capture_window_button = QPushButton("📷 Capture Window", step)
        self.capture_window_button.setEnabled(False)
        self.capture_window_button.setMinimumHeight(48)
        self.capture_window_button.setStyleSheet(
            f"QPushButton {{ background: {C_SUCCESS}; color: {C_WHITE}; min-height: 48px; font-size: 12pt; font-weight: 700; border: none; border-radius: 6px; }}"
            "QPushButton:disabled { background: #D1D5DB; color: #9CA3AF; }"
        )
        self.capture_window_button.clicked.connect(self._do_capture_selected_window)

        self._clear_window_selection()

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(self.window_preview_frame)
        layout.addLayout(action_row)
        layout.addWidget(self.capture_window_button)
        layout.addStretch(1)

        return step

    def _build_step2_widget(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Step 2: Detect Signature", step)
        title.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        desc = QLabel(
            "The AI will automatically locate signature regions in your captured screen.",
            step,
        )
        desc.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.step2_source_label = QLabel(f"Capture Source: {self.capture_source_context}", step)
        self.step2_source_label.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 6px; padding: 6px 8px; font-size: 9pt;"
        )

        self.screenshot_preview_label = DetectionPreviewLabel(step)

        self.detection_status_label = QLabel("", step)
        self.detection_status_label.setVisible(False)
        self.detection_status_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.detect_progress = QProgressBar(step)
        self.detect_progress.setRange(0, 0)
        self.detect_progress.setVisible(False)

        self.detect_button = QPushButton("🔍 Detect Signature", step)
        self.detect_button.setStyleSheet(
            f"QPushButton {{ background: {C_BLUE}; color: {C_WHITE}; min-height: 48px; font-size: 11pt; font-weight: 700; }}"
        )
        self.detect_button.clicked.connect(self._do_detect)

        self.manual_crop_step2_button = QPushButton("✏ Manual Crop", step)
        self.manual_crop_step2_button.setObjectName("secondary")
        self.manual_crop_step2_button.setVisible(False)
        self.manual_crop_step2_button.clicked.connect(self._open_manual_crop_dialog)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(self.step2_source_label)
        layout.addWidget(self.screenshot_preview_label, 1)
        layout.addWidget(self.detection_status_label)
        layout.addWidget(self.detect_progress)
        layout.addWidget(self.detect_button)
        layout.addWidget(self.manual_crop_step2_button)

        return step

    def _build_step3_widget(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Step 3: Review and Confirm Crop", step)
        title.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        self.step3_source_label = QLabel(f"Capture Source: {self.capture_source_context}", step)
        self.step3_source_label.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 6px; padding: 6px 8px; font-size: 9pt;"
        )

        body = QWidget(step)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)

        left_panel = QFrame(body)
        left_panel.setStyleSheet(
            f"background: {C_WHITE}; border: 1px solid {C_BORDER}; border-radius: 8px;"
        )
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        left_title = QLabel("Detected Candidates", left_panel)
        left_title.setStyleSheet(f"font-size: 10pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

        self.candidates_scroll = QScrollArea(left_panel)
        self.candidates_scroll.setWidgetResizable(True)
        self.candidates_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.candidates_widget = QWidget(self.candidates_scroll)
        self.candidates_layout = QVBoxLayout(self.candidates_widget)
        self.candidates_layout.setContentsMargins(0, 0, 0, 0)
        self.candidates_layout.setSpacing(8)
        self.candidates_scroll.setWidget(self.candidates_widget)

        left_layout.addWidget(left_title)
        left_layout.addWidget(self.candidates_scroll, 1)

        right_panel = QFrame(body)
        right_panel.setStyleSheet(
            f"background: {C_WHITE}; border: 1px solid {C_BORDER}; border-radius: 8px;"
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        preview_title = QLabel("Selected Crop Preview", right_panel)
        preview_title.setStyleSheet(f"font-size: 10pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

        self.selected_crop_preview = SignaturePreviewLabel(right_panel)
        self.selected_crop_preview.setFixedSize(300, 120)
        self.selected_crop_preview.setAcceptDrops(False)
        self.selected_crop_preview.setCursor(Qt.CursorShape.ArrowCursor)

        self.quality_badge_label = QLabel("Image quality not assessed", right_panel)
        self.quality_badge_label.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 8px; padding: 8px;"
        )

        quality_row = QHBoxLayout()
        quality_row.setSpacing(8)

        self.resolution_label = QLabel("Resolution: -", right_panel)
        self.contrast_label = QLabel("Contrast: -", right_panel)
        self.ink_label = QLabel("Ink Coverage: -", right_panel)

        for item in [self.resolution_label, self.contrast_label, self.ink_label]:
            item.setStyleSheet(
                f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 6px; padding: 6px;"
            )
            quality_row.addWidget(item)

        self.manual_crop_step3_button = QPushButton("✏ Crop Manually Instead", right_panel)
        self.manual_crop_step3_button.setObjectName("secondary")
        self.manual_crop_step3_button.clicked.connect(self._open_manual_crop_dialog)

        self.accept_continue_button = QPushButton("✓ Accept & Continue", right_panel)
        self.accept_continue_button.setStyleSheet(
            f"QPushButton {{ background: {C_SUCCESS}; color: {C_WHITE}; min-height: 48px; font-size: 11pt; font-weight: 700; }}"
        )
        self.accept_continue_button.clicked.connect(self._on_accept_continue)

        right_layout.addWidget(preview_title)
        right_layout.addWidget(self.selected_crop_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.quality_badge_label)
        right_layout.addLayout(quality_row)
        right_layout.addStretch(1)
        right_layout.addWidget(self.manual_crop_step3_button)
        right_layout.addWidget(self.accept_continue_button)

        body_layout.addWidget(left_panel, 1)
        body_layout.addWidget(right_panel, 1)

        layout.addWidget(title)
        layout.addWidget(self.step3_source_label)
        layout.addWidget(body, 1)

        return step

    def _build_step4_widget(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Step 4: AI Forensic Verification", step)
        title.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        summary_frame = QFrame(step)
        summary_frame.setStyleSheet(
            f"background: {C_WHITE}; border: 1px solid {C_BORDER}; border-radius: 10px;"
        )
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        summary_layout.setSpacing(10)

        image_row = QHBoxLayout()
        image_row.setSpacing(12)

        left_wrap = QVBoxLayout()
        left_label = QLabel("Reference Signature", summary_frame)
        left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step4_reference_preview = SignaturePreviewLabel(summary_frame)
        self.step4_reference_preview.setFixedSize(260, 100)
        self.step4_reference_preview.setAcceptDrops(False)
        self.step4_reference_preview.setCursor(Qt.CursorShape.ArrowCursor)
        left_wrap.addWidget(left_label)
        left_wrap.addWidget(self.step4_reference_preview)

        right_wrap = QVBoxLayout()
        right_label = QLabel("Submitted Signature", summary_frame)
        right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.step4_submitted_preview = SignaturePreviewLabel(summary_frame)
        self.step4_submitted_preview.setFixedSize(260, 100)
        self.step4_submitted_preview.setAcceptDrops(False)
        self.step4_submitted_preview.setCursor(Qt.CursorShape.ArrowCursor)
        right_wrap.addWidget(right_label)
        right_wrap.addWidget(self.step4_submitted_preview)

        image_row.addLayout(left_wrap)
        image_row.addLayout(right_wrap)

        self.step4_quality_summary = QLabel("Image Quality: Not assessed", summary_frame)
        self.step4_quality_summary.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 8px; padding: 8px;"
        )

        info = QLabel(
            "Ready to perform 13-strategy forensic analysis using the local offline SignVerify Pro model. "
            "Typical analysis time: 2–8 seconds depending on hardware.",
            summary_frame,
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.model_warning_frame = QFrame(summary_frame)
        self.model_warning_frame.setStyleSheet(
            f"background: {C_GOLD}; border-radius: 8px; border: 1px solid {C_AMBER};"
        )
        warning_layout = QHBoxLayout(self.model_warning_frame)
        warning_layout.setContentsMargins(10, 8, 10, 8)
        warning_layout.setSpacing(8)

        self.model_warning_label = QLabel(
            "⚠ Local model is not installed. Go to Settings and configure the model file path.",
            self.model_warning_frame,
        )
        self.model_warning_label.setStyleSheet(f"color: {C_NAVY}; font-size: 9pt; font-weight: 700;")

        warning_btn = QPushButton("Open Settings", self.model_warning_frame)
        warning_btn.setObjectName("secondary")
        warning_btn.clicked.connect(lambda: NavigationController.get_instance().navigate_to("settings"))

        warning_layout.addWidget(self.model_warning_label, 1)
        warning_layout.addWidget(warning_btn)

        self.verify_button = QPushButton("🔍 Verify Signature", summary_frame)
        self.verify_button.setStyleSheet(
            f"QPushButton {{ background: {C_BLUE}; color: {C_WHITE}; min-height: 56px; font-size: 14pt; font-weight: 700; }}"
        )
        self.verify_button.clicked.connect(self._do_verify)

        summary_layout.addLayout(image_row)
        summary_layout.addWidget(self.step4_quality_summary)
        summary_layout.addWidget(info)
        summary_layout.addWidget(self.model_warning_frame)
        summary_layout.addWidget(self.verify_button)

        layout.addWidget(title)
        layout.addWidget(summary_frame)
        layout.addStretch(1)

        return step

    def _update_step_indicator(self, active_step: int) -> None:
        for index, circle in enumerate(self.step_circles, start=1):
            label = self.step_texts[index - 1]

            if index < active_step:
                circle.setText("✓")
                circle.setFixedSize(32, 32)
                circle.setStyleSheet(
                    f"background: {C_SUCCESS}; color: {C_WHITE}; border-radius: 16px; font-weight: 700;"
                )
                label.setStyleSheet(f"font-size: 9pt; color: {C_SUCCESS}; font-weight: 700;")
                circle.setGraphicsEffect(None)
            elif index == active_step:
                circle.setText(str(index))
                circle.setFixedSize(36, 36)
                circle.setStyleSheet(
                    f"background: {C_BLUE}; color: {C_WHITE}; border-radius: 18px; font-weight: 700;"
                )
                label.setStyleSheet(f"font-size: 9pt; color: {C_BLUE}; font-weight: 700;")

                shadow = QGraphicsDropShadowEffect(circle)
                shadow.setBlurRadius(12)
                shadow.setOffset(0, 2)
                shadow.setColor(QColor(21, 101, 192, 100))
                circle.setGraphicsEffect(shadow)
            else:
                circle.setText(str(index))
                circle.setFixedSize(32, 32)
                circle.setStyleSheet(
                    f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 16px; font-weight: 700;"
                )
                label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")
                circle.setGraphicsEffect(None)

        for connector_index, connector in enumerate(self.step_connectors, start=1):
            color = C_SUCCESS if active_step > connector_index else C_BORDER
            connector.setStyleSheet(f"background: {color}; border: none;")

    def _go_to_step(self, step: int) -> None:
        self.current_step = max(1, min(4, int(step)))
        self.steps_stack.setCurrentIndex(self.current_step - 1)
        self._update_step_indicator(self.current_step)

        if self.current_step == 3:
            self._populate_step3_candidates()
        if self.current_step == 4:
            self._refresh_step4_summary()

    def _pil_to_qpixmap(self, pil_image: Image.Image) -> QPixmap:
        rgb_image = pil_image.convert("RGB")
        width, height = rgb_image.size
        data = rgb_image.tobytes("raw", "RGB")
        qimage = QImage(data, width, height, width * 3, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(qimage)

    def _save_pil_to_temp(self, image: Image.Image, prefix: str) -> str:
        temp_dir = APP_DATA_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        path = temp_dir / f"{prefix}_{uuid.uuid4().hex[:12]}.png"
        image.save(path, format="PNG")
        return str(path.resolve())

    def _build_capture_source_context(self, window_info: WindowInfo | None) -> str:
        if window_info is None:
            return "No source selected"

        title = (window_info.title or "").strip() or "Untitled Window"
        if len(title) > 90:
            title = title[:87] + "..."

        size_text = f"{window_info.width}x{window_info.height}px"
        if window_info.hwnd < 0:
            return f"{title} · {size_text}"

        process = (window_info.process_name or "Unknown process").strip()
        return f"{title} · {process} · {size_text}"

    def _set_capture_source_context(self, window_info: WindowInfo | None) -> None:
        self.capture_source_context = self._build_capture_source_context(window_info)
        context_text = f"Capture Source: {self.capture_source_context}"

        if hasattr(self, "step2_source_label"):
            self.step2_source_label.setText(context_text)
        if hasattr(self, "step3_source_label"):
            self.step3_source_label.setText(context_text)

    def _clear_window_selection(self) -> None:
        self.selected_window_info = None
        self.selected_window_thumbnail = None

        self.step1_preview_stack.setCurrentWidget(self.step1_empty_widget)
        self.clear_window_selection_button.setVisible(False)
        self.capture_window_button.setEnabled(False)

        self.step1_selected_thumb_label.clear()
        self.step1_selected_icon_label.setPixmap(QPixmap())
        self.step1_selected_icon_label.setText("APP")
        self.step1_selected_icon_label.setStyleSheet(
            f"background: {C_BLUE}; color: {C_WHITE}; border-radius: 5px; font-size: 8pt; font-weight: 700;"
        )
        self.step1_selected_title_label.setText("")
        self.step1_selected_process_label.setText("")
        self.step1_selected_size_label.setText("")
        self.step1_selected_minimized_label.setVisible(False)
        self._set_capture_source_context(None)

    def _open_window_picker(self) -> None:
        dialog = WindowPickerDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        selected_window = dialog.get_selected_window()
        if selected_window is None:
            return

        self.selected_window_info = selected_window
        self.selected_window_thumbnail = selected_window.thumbnail

        if self.selected_window_thumbnail is None:
            try:
                from services.window_enumerator import WindowEnumerator

                self.selected_window_thumbnail = WindowEnumerator().capture_window_thumbnail(
                    self.selected_window_info,
                    thumb_width=240,
                    thumb_height=140,
                )
            except Exception:
                self.selected_window_thumbnail = None

        icon_pixmap = None
        try:
            from services.window_enumerator import WindowEnumerator

            icon = WindowEnumerator().get_process_icon(self.selected_window_info)
            if icon is not None:
                candidate = icon.pixmap(24, 24)
                if not candidate.isNull():
                    icon_pixmap = candidate
        except Exception:
            icon_pixmap = None

        if icon_pixmap is not None:
            self.step1_selected_icon_label.setPixmap(icon_pixmap)
            self.step1_selected_icon_label.setText("")
            self.step1_selected_icon_label.setStyleSheet("background: transparent;")
        else:
            self.step1_selected_icon_label.setPixmap(QPixmap())
            fallback = (self.selected_window_info.process_name or "APP").split(".")[0][:3].upper()
            self.step1_selected_icon_label.setText(fallback or "APP")
            self.step1_selected_icon_label.setStyleSheet(
                f"background: {C_BLUE}; color: {C_WHITE}; border-radius: 5px; font-size: 8pt; font-weight: 700;"
            )

        if self.selected_window_thumbnail is not None:
            preview = self._pil_to_qpixmap(self.selected_window_thumbnail).scaled(
                self.step1_selected_thumb_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.step1_selected_thumb_label.setPixmap(preview)
        else:
            self.step1_selected_thumb_label.setPixmap(QPixmap())
            self.step1_selected_thumb_label.setText("Preview unavailable")

        title = self.selected_window_info.title.strip() or "Untitled Window"
        if len(title) > 80:
            title = title[:77] + "..."

        self.step1_selected_title_label.setText(title)
        self.step1_selected_process_label.setText(self.selected_window_info.process_name)
        self.step1_selected_size_label.setText(
            f"{self.selected_window_info.width} × {self.selected_window_info.height} pixels"
        )
        self.step1_selected_minimized_label.setVisible(bool(self.selected_window_info.is_minimized))
        self._set_capture_source_context(self.selected_window_info)

        self.clear_window_selection_button.setVisible(True)
        self.capture_window_button.setEnabled(True)
        self.step1_preview_stack.setCurrentWidget(self.step1_selected_widget)

        # Real-world flow: once a source is selected, start capture immediately.
        QTimer.singleShot(100, self._do_capture_selected_window)

    def _cleanup_capture_worker(self) -> None:
        if self.capture_worker is None:
            return
        try:
            if self.capture_worker.isRunning():
                self.capture_worker.wait(3000)
        except Exception:
            pass
        self.capture_worker.deleteLater()
        self.capture_worker = None

    def _do_capture_selected_window(self) -> None:
        if self.selected_window_info is None:
            self.show_error("Window Required", "Please select a window before capture.")
            return

        self._cleanup_capture_worker()

        self.hide_loading()
        self.show_loading(f"Capturing '{self.selected_window_info.title}'...")

        self.capture_worker = CaptureWorker(self.selected_window_info)
        self.capture_worker.progress_updated.connect(self.show_loading)
        self.capture_worker.capture_ready.connect(self._on_capture_ready)
        self.capture_worker.error_occurred.connect(self._on_capture_error)
        self.capture_worker.start()

    def _on_capture_ready(self, pil_image: Image.Image) -> None:
        self.hide_loading()

        try:
            from services.screen_capture import ScreenCaptureService

            self.screenshot = pil_image
            self.detections = []
            self.cropped_image = None
            self.cropped_image_path = None
            self.current_quality = None

            ScreenCaptureService().save_capture_to_temp(pil_image)

            self.screenshot_preview_label.set_source_pixmap(self._pil_to_qpixmap(pil_image))
            self.screenshot_preview_label.set_detections([])
            self.detection_status_label.setVisible(True)
            self.detection_status_label.setStyleSheet(f"font-size: 9pt; color: {C_BLUE};")
            self.detection_status_label.setText("Capture completed. Opening crop tool...")
            self.manual_crop_step2_button.setVisible(True)
            self._set_capture_source_context(self.selected_window_info)

            self._go_to_step(2)
            QTimer.singleShot(150, lambda: self._open_manual_crop_dialog(auto_invoked=True))
        except Exception as exc:
            logger.exception("Window capture handling failed")
            self.show_error("Capture Failed", str(exc))
        finally:
            self._cleanup_capture_worker()

    def _on_capture_error(self, message: str) -> None:
        self.hide_loading()

        if message.strip().upper() == WINDOW_CLOSED_SENTINEL:
            self.show_error(
                "Window Closed",
                "The selected window was closed before capture. Please click 'Select Window' again to choose an open window.",
            )
            self._clear_window_selection()
        else:
            self.show_error("Capture Failed", message)

        self._cleanup_capture_worker()

    def _do_detect(self) -> None:
        if self.screenshot is None:
            self.show_error("Missing Screenshot", "Capture a screen image before running detection.")
            return

        self.detect_progress.setVisible(True)
        self.detect_button.setEnabled(False)
        self.manual_crop_step2_button.setVisible(False)

        self.detection_status_label.setVisible(True)
        self.detection_status_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")
        self.detection_status_label.setText("Initializing OpenCV detection pipeline...")

        from utils.thread_workers import DetectionWorker

        sensitivity = settings_controller.get_detection_sensitivity()
        self.detection_worker = DetectionWorker(self.screenshot, sensitivity)
        self.detection_worker.detections_ready.connect(self._on_detections_ready)
        self.detection_worker.error_occurred.connect(self._on_detection_error)
        self.detection_worker.progress_updated.connect(self._on_detection_progress)
        self.detection_worker.start()

    def _on_detection_progress(self, message: str) -> None:
        self.detection_status_label.setVisible(True)
        self.detection_status_label.setText(message)

    def _on_detections_ready(self, detections: list) -> None:
        self.detect_progress.setVisible(False)
        self.detect_button.setEnabled(True)
        self.detections = detections or []

        self.screenshot_preview_label.set_detections(self.detections)

        if self.detections:
            count = len(self.detections)
            suffix = "candidate" if count == 1 else "candidates"
            self.detection_status_label.setText(f"{count} signature {suffix} found")
            self.detection_status_label.setStyleSheet(f"font-size: 9pt; color: {C_SUCCESS};")
            self._select_detection(self.detections[0])
            QTimer.singleShot(500, lambda: self._go_to_step(3))
            return

        self.detection_status_label.setText(
            "No signature regions detected. Use Manual Crop to select the signature manually."
        )
        self.detection_status_label.setStyleSheet(f"font-size: 9pt; color: {C_DANGER};")
        self.manual_crop_step2_button.setVisible(True)

    def _on_detection_error(self, message: str) -> None:
        self.detect_progress.setVisible(False)
        self.detect_button.setEnabled(True)
        self.show_error("Detection Error", message)

    def _clear_layout_widgets(self, layout: QVBoxLayout) -> None:
        while layout.count() > 0:
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout_widgets(child_layout)

    def _populate_step3_candidates(self) -> None:
        self._clear_layout_widgets(self.candidates_layout)

        if not self.detections:
            empty_label = QLabel(
                "No auto-detected candidates available. Use manual crop to continue.",
                self.candidates_widget,
            )
            empty_label.setWordWrap(True)
            empty_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")
            self.candidates_layout.addWidget(empty_label)
            self.candidates_layout.addStretch(1)
            return

        if self.cropped_image is None:
            self._select_detection(self.detections[0])

        for index, detection in enumerate(self.detections[:3], start=1):
            card = QFrame(self.candidates_widget)
            card.setStyleSheet(
                f"background: {C_GREY_LT}; border: 1px solid {C_BORDER}; border-radius: 8px;"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(6)

            preview = SignaturePreviewLabel(card)
            preview.setFixedSize(200, 80)
            preview.setAcceptDrops(False)
            preview.setCursor(Qt.CursorShape.ArrowCursor)

            if self.screenshot is not None:
                from services.signature_detector import SignatureDetector

                detector = SignatureDetector(sensitivity=settings_controller.get_detection_sensitivity())
                crop = detector.crop_region(
                    self.screenshot,
                    int(detection.get("x", 0)),
                    int(detection.get("y", 0)),
                    int(detection.get("width", 0)),
                    int(detection.get("height", 0)),
                )
                preview.set_image_from_pixmap(self._pil_to_qpixmap(crop))

            label_text = "Best Match" if index == 1 else f"Match #{index}"
            card_label = QLabel(label_text, card)
            card_label.setStyleSheet(f"font-size: 9pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

            button = QPushButton("Select This", card)
            button.setObjectName("secondary")
            button.clicked.connect(lambda _checked=False, det=detection: self._select_detection(det))

            card_layout.addWidget(preview, alignment=Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(card_label)
            card_layout.addWidget(button)

            self.candidates_layout.addWidget(card)

        self.candidates_layout.addStretch(1)

    def _quality_style(self, rating: str) -> str:
        normalized = (rating or "").strip().lower()
        if normalized == "high":
            return f"background: {C_SUCCESS}; color: {C_WHITE}; border-radius: 8px; padding: 8px;"
        if normalized == "medium":
            return f"background: {C_GOLD}; color: {C_NAVY}; border-radius: 8px; padding: 8px;"
        return f"background: {C_DANGER}; color: {C_WHITE}; border-radius: 8px; padding: 8px;"

    def _apply_quality_to_labels(self, quality) -> None:
        self.current_quality = quality
        overall = str(quality.overall)

        badge_icon = "🟢" if overall == "High" else ("🟡" if overall == "Medium" else "🔴")
        self.quality_badge_label.setText(f"{badge_icon} {overall} Quality")
        self.quality_badge_label.setStyleSheet(self._quality_style(overall))

        tooltip = (
            f"Resolution: {quality.resolution_detail}\n"
            f"Contrast: {quality.contrast_detail}\n"
            f"Ink Coverage: {quality.ink_coverage_detail}"
        )
        self.quality_badge_label.setToolTip(tooltip)

        self.resolution_label.setText(f"Resolution: {quality.resolution}")
        self.contrast_label.setText(f"Contrast: {quality.contrast}")
        self.ink_label.setText(f"Ink Coverage: {quality.ink_coverage}")

        self.resolution_label.setStyleSheet(self._quality_style(quality.resolution))
        self.contrast_label.setStyleSheet(self._quality_style(quality.contrast))
        self.ink_label.setStyleSheet(self._quality_style(quality.ink_coverage))

    def _select_detection(self, detection: dict) -> None:
        if self.screenshot is None:
            return

        from services.signature_detector import SignatureDetector
        from services.image_utils import ImageUtils

        detector = SignatureDetector(sensitivity=settings_controller.get_detection_sensitivity())
        crop = detector.crop_region(
            self.screenshot,
            int(detection.get("x", 0)),
            int(detection.get("y", 0)),
            int(detection.get("width", 0)),
            int(detection.get("height", 0)),
        )

        crop_path = self._save_pil_to_temp(crop, "crop")
        self.cropped_image = crop
        self.cropped_image_path = crop_path

        self.selected_crop_preview.set_image_from_pixmap(self._pil_to_qpixmap(crop))

        quality = ImageUtils().assess_quality(crop_path)
        self._apply_quality_to_labels(quality)

    def _open_manual_crop_dialog(self, auto_invoked: bool = False) -> None:
        if self.screenshot is None:
            self.show_error("Missing Screenshot", "Capture a screen image before manual crop.")
            return

        crop_dialog = CropDialog(
            self,
            screenshot=self.screenshot,
            detections=self.detections,
            source_context=self.capture_source_context,
        )
        crop_dialog.setWindowState(crop_dialog.windowState() | Qt.WindowState.WindowFullScreen)
        if crop_dialog.exec() != crop_dialog.DialogCode.Accepted:
            if auto_invoked:
                self.detection_status_label.setVisible(True)
                self.detection_status_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")
                self.detection_status_label.setText(
                    "Manual crop was skipped. Use Detect Signature or Manual Crop to continue."
                )
            return

        cropped = crop_dialog.get_cropped_image()
        if cropped is None:
            self.show_error("Manual Crop", "No crop region selected.")
            return

        from services.image_utils import ImageUtils

        crop_path = self._save_pil_to_temp(cropped, "crop")
        self.cropped_image = cropped
        self.cropped_image_path = crop_path

        self.selected_crop_preview.set_image_from_pixmap(self._pil_to_qpixmap(cropped))
        quality = ImageUtils().assess_quality(crop_path)
        self._apply_quality_to_labels(quality)

        if auto_invoked:
            self.detection_status_label.setVisible(True)
            self.detection_status_label.setStyleSheet(f"font-size: 9pt; color: {C_SUCCESS};")
            self.detection_status_label.setText("Manual crop applied. Review and confirm in Step 3.")

        self._go_to_step(3)

    def _on_accept_continue(self) -> None:
        if self.cropped_image is None or not self.cropped_image_path:
            self.show_error("Missing Crop", "Select a signature crop before continuing.")
            return
        self._go_to_step(4)

    def _refresh_step4_summary(self) -> None:
        person = database_controller.get_person_by_id(int(self.person_id or 0)) if self.person_id else None
        if person is not None:
            reference_path = resolve_signature_path(person.signature_image_path)
            self.reference_image_path = reference_path
            if Path(reference_path).exists():
                self.step4_reference_preview.set_image_from_path(reference_path)
            else:
                self.step4_reference_preview.clear_image()

        if self.cropped_image_path and Path(self.cropped_image_path).exists():
            self.step4_submitted_preview.set_image_from_path(self.cropped_image_path)
        else:
            self.step4_submitted_preview.clear_image()

        if self.current_quality is not None:
            overall = str(self.current_quality.overall)
            self.step4_quality_summary.setText(f"Image Quality: {overall}")
            self.step4_quality_summary.setStyleSheet(self._quality_style(overall))
        else:
            self.step4_quality_summary.setText("Image Quality: Not assessed")
            self.step4_quality_summary.setStyleSheet(
                f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 8px; padding: 8px;"
            )

        model_ready = False
        model_message = "Local model is not installed"
        try:
            from services.local_model_service import LocalModelService

            model_ready, model_message = LocalModelService().ping()
        except Exception as exc:
            model_ready = False
            model_message = str(exc)

        self.model_warning_label.setText(f"⚠ {model_message}")
        self.model_warning_frame.setVisible(not model_ready)

        self.verify_button.setEnabled(
            bool(self.cropped_image_path and Path(self.cropped_image_path).exists() and model_ready)
        )

    def _do_verify(self) -> None:
        if not self.cropped_image_path or not Path(self.cropped_image_path).exists():
            self.show_error("Missing Crop", "Please select and confirm a cropped signature first.")
            return

        person = database_controller.get_person_by_id(int(self.person_id or 0)) if self.person_id else None
        if person is None:
            self.show_error("Person Missing", "Selected person record not found.")
            NavigationController.get_instance().navigate_to("verification")
            return

        reference_path = resolve_signature_path(person.signature_image_path)
        if not Path(reference_path).exists():
            self.show_error("Reference Missing", "Reference signature image could not be found.")
            return

        self.reference_image_path = reference_path

        self.show_loading("Loading local AI model...")
        try:
            controller = VerificationController()
            self.local_model_worker = controller.start_verification(
                reference_path,
                self.cropped_image_path,
                mode="A_SCREEN",
                person_id=self.person_id,
                person_name=self.person_name,
                parent_widget=self,
            )

            if self.local_model_worker is None:
                self.hide_loading()
                return

            self.local_model_worker.result_ready.connect(self._on_verification_complete)
            self.local_model_worker.error_occurred.connect(self._on_verification_error)
            self.local_model_worker.progress_updated.connect(lambda msg: self.show_loading(msg))
            self.local_model_worker.start()
        except Exception as exc:
            self.hide_loading()
            logger.exception("Failed to start verification")
            self.show_error("Verification Failed", str(exc))

    def _on_verification_complete(self, result_dict: dict) -> None:
        self.hide_loading()

        verification = VerificationController().save_verification_result(
            result_dict,
            mode="A_SCREEN",
            person_id=self.person_id,
            reference_image_path=self.reference_image_path,
            submitted_image_path=self.cropped_image_path or "",
        )

        person = database_controller.get_person_by_id(int(self.person_id or 0))
        NavigationController.get_instance().navigate_to(
            "results",
            result_dict=result_dict,
            verification=verification,
            person=person,
        )

    def _on_verification_error(self, message: str) -> None:
        self.hide_loading()
        self.show_error("Verification Failed", message)

    def _reset_state(self) -> None:
        self._cleanup_capture_worker()

        self.screenshot = None
        self.detections = []
        self.cropped_image = None
        self.cropped_image_path = None
        self.current_quality = None
        self.reference_image_path = ""
        self.selected_window_info = None
        self.selected_window_thumbnail = None

        self._clear_window_selection()
        self._set_capture_source_context(None)

        self.screenshot_preview_label.clear()
        self.detection_status_label.clear()
        self.detection_status_label.setVisible(False)
        self.detect_progress.setVisible(False)
        self.detect_button.setEnabled(True)
        self.manual_crop_step2_button.setVisible(False)

        self.selected_crop_preview.clear_image()
        self.quality_badge_label.setText("Image quality not assessed")
        self.quality_badge_label.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 8px; padding: 8px;"
        )
        self.resolution_label.setText("Resolution: -")
        self.contrast_label.setText("Contrast: -")
        self.ink_label.setText("Ink Coverage: -")
        for item in [self.resolution_label, self.contrast_label, self.ink_label]:
            item.setStyleSheet(
                f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 6px; padding: 6px;"
            )

        self.step4_reference_preview.clear_image()
        self.step4_submitted_preview.clear_image()
        self.step4_quality_summary.setText("Image Quality: Not assessed")
        self.step4_quality_summary.setStyleSheet(
            f"background: {C_GREY_LT}; color: {C_TEXT_SECONDARY}; border-radius: 8px; padding: 8px;"
        )
        self.verify_button.setEnabled(False)

        self._clear_layout_widgets(self.candidates_layout)

    def on_show(self, person_id: int = None, person_name: str = None, **kwargs) -> None:
        _ = kwargs
        logger.info("Mode A screen shown")

        self.hide_loading()
        self.person_id = int(person_id) if person_id is not None else None
        self.person_name = person_name

        self._reset_state()

        if self.person_id is None:
            self.show_error("Person Required", "Please select a person before using Mode A.")
            NavigationController.get_instance().navigate_to("verification")
            return

        person = database_controller.get_person_by_id(self.person_id)
        if person is None:
            self.show_error("Person Not Found", "The selected person's record could not be found.")
            NavigationController.get_instance().navigate_to("verification")
            return

        self.person_name = person.full_name
        self.person_name_label.setText(person.full_name)

        if person.thumbnail_blob:
            self.person_preview.set_image_from_bytes(person.thumbnail_blob)
        else:
            ref_path = resolve_signature_path(person.signature_image_path)
            if Path(ref_path).exists():
                self.person_preview.set_image_from_path(ref_path)
            else:
                self.person_preview.clear_image()

        self._go_to_step(1)
