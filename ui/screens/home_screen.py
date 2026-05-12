"""Home dashboard screen implementation."""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import C_BLUE, C_BLUE_HOVER, C_BORDER, C_GREY_LT, C_NAVY, C_TEXT_PRIMARY, C_TEXT_SECONDARY, C_WHITE
from controllers.database_controller import database_controller
from controllers.navigation_controller import NavigationController
from models.verification import Verification
from ui.base_screen import BaseScreen
from ui.widgets.verdict_badge import VerdictBadge
from utils.logger import get_logger

logger = get_logger(__name__)


class QuickActionCard(QFrame):
    """Clickable quick action card with hover elevation and tint."""

    clicked = pyqtSignal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        background: str,
        border_color: str,
        text_color: str,
        title_size: int,
        border_width: int = 1,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._background = background
        self._border_color = border_color
        self._text_color = text_color
        self._title_size = title_size
        self._border_width = border_width

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(80)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(8)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(0, 0, 0, 25))
        self.setGraphicsEffect(self._shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(2)

        self.title_label = QLabel(title, self)
        self.title_label.setStyleSheet(
            f"font-size: {title_size}pt; font-weight: 700; color: {text_color};"
        )

        self.subtitle_label = QLabel(subtitle, self)
        self.subtitle_label.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        layout.addStretch(1)

        self._apply_style(hover=False)

    def _apply_style(self, hover: bool) -> None:
        bg = self._background
        if hover:
            if self._background == C_BLUE:
                bg = C_BLUE_HOVER
            else:
                bg = C_GREY_LT

        self.setStyleSheet(
            f"""
            QFrame {{
                background: {bg};
                border: {self._border_width}px solid {self._border_color};
                border-radius: 10px;
            }}
            """
        )
        self._shadow.setBlurRadius(14 if hover else 8)
        self._shadow.setOffset(0, 4 if hover else 2)

    def enterEvent(self, event) -> None:  # noqa: N802
        self._apply_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._apply_style(hover=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class VerificationFeedRow(QFrame):
    """Clickable recent verification row widget."""

    clicked = pyqtSignal(int)

    MODE_LABELS = {
        "A_SCREEN": "Screen Detection",
        "B_UPLOAD": "Upload",
        "B_CAMERA": "Camera",
        "C_ADHOC": "Ad-Hoc",
    }

    def __init__(self, verification: Verification, parent=None) -> None:
        super().__init__(parent)
        self.verification_id = verification.id

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(60)

        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(12)

        badge = VerdictBadge(verification.verdict, self)
        badge.setFixedHeight(24)

        person_name = verification.person.full_name if verification.person is not None else "Unknown Person"
        mode_label = self.MODE_LABELS.get(verification.mode, verification.mode)

        name_label = QLabel(person_name, self)
        name_label.setStyleSheet(f"font-size: 10pt; font-weight: 700; color: {C_TEXT_PRIMARY};")

        mode_text_label = QLabel(mode_label, self)
        mode_text_label.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        name_wrap = QWidget(self)
        name_layout = QVBoxLayout(name_wrap)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(1)
        name_layout.addWidget(name_label)
        name_layout.addWidget(mode_text_label)

        confidence_value = float(verification.confidence or 0.0) * 100.0
        confidence_label = QLabel(f"{confidence_value:.1f}%", self)
        confidence_label.setStyleSheet(f"font-size: 10pt; font-weight: 700; color: {C_BLUE};")

        timestamp_label = QLabel(self._format_timestamp(verification.verified_at), self)
        timestamp_label.setStyleSheet(f"font-size: 8pt; color: {C_TEXT_SECONDARY};")

        row_layout.addWidget(badge)
        row_layout.addWidget(name_wrap, 1)
        row_layout.addWidget(confidence_label)
        row_layout.addWidget(timestamp_label)

        self.setStyleSheet(
            f"""
            QFrame {{
                background: {C_WHITE};
                border-bottom: 1px solid {C_GREY_LT};
            }}
            """
        )

    def _format_timestamp(self, timestamp: datetime | None) -> str:
        if timestamp is None:
            return ""

        now = datetime.now()
        date_only = timestamp.date()

        if date_only == now.date():
            return f"Today {timestamp.strftime('%H:%M')}"
        if date_only == (now - timedelta(days=1)).date():
            return "Yesterday"
        return timestamp.strftime("%d %b %Y")

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {C_GREY_LT};
                border-bottom: 1px solid {C_GREY_LT};
            }}
            """
        )
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {C_WHITE};
                border-bottom: 1px solid {C_GREY_LT};
            }}
            """
        )
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.verification_id)
        super().mousePressEvent(event)


class HomeScreen(BaseScreen):
    """Home dashboard with KPIs, actions, and recent verification feed."""

    def _build_ui(self) -> None:
        self.content_layout.setContentsMargins(20, 18, 20, 18)
        self.content_layout.setSpacing(14)

        self._build_kpi_tiles_row()
        self._add_divider()
        self._build_quick_actions_row()
        self._add_divider()
        self._build_recent_feed_section()

    def _create_tile_shadow(self, widget: QWidget) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(8)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 20))
        widget.setGraphicsEffect(shadow)

    def _build_kpi_tile(self, icon_text: str, description: str, use_badge: bool = False) -> tuple[QFrame, QWidget]:
        tile = QFrame(self)
        tile.setFixedHeight(100)
        tile.setStyleSheet(
            f"""
            QFrame {{
                background: {C_WHITE};
                border: 1px solid {C_BORDER};
                border-radius: 10px;
            }}
            """
        )
        self._create_tile_shadow(tile)

        layout = QHBoxLayout(tile)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        left_wrap = QWidget(tile)
        left_layout = QVBoxLayout(left_wrap)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        if use_badge:
            value_widget: QWidget = VerdictBadge("", left_wrap)
        else:
            value_label = QLabel("0", left_wrap)
            value_label.setStyleSheet(f"font-size: 28pt; font-weight: 700; color: {C_NAVY};")
            value_widget = value_label

        desc_label = QLabel(description, left_wrap)
        desc_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        left_layout.addWidget(value_widget)
        left_layout.addWidget(desc_label)

        icon_label = QLabel(icon_text, tile)
        icon_label.setStyleSheet("font-size: 20pt;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(left_wrap, 1)
        layout.addWidget(icon_label)

        return tile, value_widget

    def _build_kpi_tiles_row(self) -> None:
        row_widget = QWidget(self)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        tile_total, self.total_records_value = self._build_kpi_tile("🗂", "Registered Signatures")
        tile_today, self.verifications_today_value = self._build_kpi_tile("✅", "Verified Today")
        tile_avg, self.avg_confidence_value = self._build_kpi_tile("📊", "Average AI Confidence")
        tile_last, self.last_verdict_badge = self._build_kpi_tile("🔍", "Last Verdict", use_badge=True)

        row_layout.addWidget(tile_total, 1)
        row_layout.addWidget(tile_today, 1)
        row_layout.addWidget(tile_avg, 1)
        row_layout.addWidget(tile_last, 1)

        self.content_layout.addWidget(row_widget)

    def _build_quick_actions_row(self) -> None:
        row_widget = QWidget(self)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        start_card = QuickActionCard(
            "▶ Start Verification",
            "Run an AI powered signature verification",
            background=C_BLUE,
            border_color=C_BLUE,
            text_color=C_WHITE,
            title_size=16,
            border_width=1,
            parent=self,
        )
        start_card.clicked.connect(lambda: NavigationController.get_instance().navigate_to("verification"))

        add_card = QuickActionCard(
            "＋ Add Record",
            "Register a new reference signature",
            background=C_WHITE,
            border_color=C_BLUE,
            text_color=C_BLUE,
            title_size=14,
            border_width=2,
            parent=self,
        )
        add_card.clicked.connect(
            lambda: NavigationController.get_instance().navigate_to("database", open_add_dialog=True)
        )

        history_card = QuickActionCard(
            "🕐 View History",
            "Browse completed verification sessions",
            background=C_WHITE,
            border_color=C_BORDER,
            text_color=C_TEXT_PRIMARY,
            title_size=14,
            border_width=1,
            parent=self,
        )
        history_card.clicked.connect(lambda: NavigationController.get_instance().navigate_to("history"))

        row_layout.addWidget(start_card, 1)
        row_layout.addWidget(add_card, 1)
        row_layout.addWidget(history_card, 1)

        self.content_layout.addWidget(row_widget)

    def _build_recent_feed_section(self) -> None:
        section_header = QWidget(self)
        header_layout = QHBoxLayout(section_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        title = QLabel("Recent Verifications", section_header)
        title.setStyleSheet(f"font-size: 14pt; font-weight: 700; color: {C_NAVY};")

        view_all_btn = QPushButton("View All →", section_header)
        view_all_btn.setFlat(True)
        view_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all_btn.setStyleSheet(f"QPushButton {{ color: {C_BLUE}; font-weight: 700; border: none; }}")
        view_all_btn.clicked.connect(lambda: NavigationController.get_instance().navigate_to("history"))

        header_layout.addWidget(title)
        header_layout.addStretch(1)
        header_layout.addWidget(view_all_btn)

        self.recent_scroll = QScrollArea(self)
        self.recent_scroll.setWidgetResizable(True)
        self.recent_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.recent_container = QWidget(self.recent_scroll)
        self.recent_layout = QVBoxLayout(self.recent_container)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(0)

        self.recent_scroll.setWidget(self.recent_container)

        self.content_layout.addWidget(section_header)
        self.content_layout.addWidget(self.recent_scroll, 1)

    def _add_divider(self) -> None:
        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {C_GREY_LT}; background: {C_GREY_LT}; max-height: 1px;")
        self.content_layout.addWidget(divider)

    def _clear_recent_feed(self) -> None:
        while self.recent_layout.count() > 0:
            item = self.recent_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _populate_recent_feed(self, verifications: list[Verification]) -> None:
        self._clear_recent_feed()

        if not verifications:
            empty_wrap = QWidget(self.recent_container)
            empty_layout = QVBoxLayout(empty_wrap)
            empty_layout.setContentsMargins(0, 30, 0, 30)
            empty_layout.setSpacing(8)
            empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            icon = QLabel("🧾", empty_wrap)
            icon.setStyleSheet("font-size: 36px;")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

            text = QLabel(
                "No verifications yet. Start your first verification to see results here.",
                empty_wrap,
            )
            text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

            empty_layout.addWidget(icon)
            empty_layout.addWidget(text)
            self.recent_layout.addWidget(empty_wrap)
            self.recent_layout.addStretch(1)
            return

        for verification in verifications:
            row = VerificationFeedRow(verification, self.recent_container)
            row.clicked.connect(self._on_recent_row_clicked)
            self.recent_layout.addWidget(row)

        self.recent_layout.addStretch(1)

    def _on_recent_row_clicked(self, verification_id: int) -> None:
        _ = verification_id
        NavigationController.get_instance().navigate_to("history")

    def _refresh_main_window_status(self) -> None:
        window = self.window()
        if hasattr(window, "refresh_status_bar"):
            window.refresh_status_bar()

    def _refresh_dashboard_data(self) -> None:
        total_records = database_controller.get_person_count()
        verifications_today = database_controller.get_verifications_today_count()
        average_confidence = database_controller.get_average_confidence() * 100.0
        last_verdict = database_controller.get_last_verdict()
        recent_verifications = database_controller.get_recent_verifications(10)

        if isinstance(self.total_records_value, QLabel):
            self.total_records_value.setText(str(total_records))
        if isinstance(self.verifications_today_value, QLabel):
            self.verifications_today_value.setText(str(verifications_today))
        if isinstance(self.avg_confidence_value, QLabel):
            self.avg_confidence_value.setText(f"{average_confidence:.1f}%")

        self.last_verdict_badge.set_verdict(last_verdict or "")
        self._populate_recent_feed(recent_verifications)

    def on_show(self, **kwargs) -> None:
        _ = kwargs
        logger.info("Home screen shown")
        self._refresh_main_window_status()

        try:
            self._refresh_dashboard_data()
        except Exception as exc:
            logger.exception("Failed to refresh home dashboard")
            self.show_error("Dashboard Error", str(exc))
