"""Sidebar navigation widget."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from config import (
    APP_VERSION,
    C_BLUE,
    C_NAVY,
    C_SIDEBAR_ACTIVE_BG,
    C_TEXT_SECONDARY,
    SIDEBAR_WIDTH,
)
from controllers.navigation_controller import NavigationController
from utils.licence_manager import LicenceManager


class SidebarNav(QWidget):
    """Persistent left side navigation for primary app sections."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.nav_buttons: dict[str, QToolButton] = {}
        self.tier_label: QLabel | None = None
        self.licence_manager = LicenceManager.get_instance()
        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f"""
            QWidget {{
                background: {C_NAVY};
                color: #f8fafc;
            }}
            QToolButton {{
                color: #e2e8f0;
                text-align: left;
                padding-left: 18px;
                border: none;
                border-left: 4px solid transparent;
                font-size: 10pt;
                font-weight: 600;
                min-height: 48px;
                max-height: 48px;
                background: transparent;
            }}
            QToolButton:hover {{
                background: {C_SIDEBAR_ACTIVE_BG};
            }}
            QToolButton[active="true"] {{
                background: {C_SIDEBAR_ACTIVE_BG};
                border-left: 4px solid {C_BLUE};
                color: #ffffff;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QWidget(self)
        top.setFixedHeight(70)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(12, 10, 12, 10)
        top_layout.setSpacing(10)

        logo_label = QLabel("SV", top)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setFixedSize(36, 36)
        logo_label.setStyleSheet(
            f"background:{C_BLUE}; color:white; border-radius:9px; font-size:11pt; font-weight:700;"
        )

        title_wrap = QWidget(top)
        title_layout = QVBoxLayout(title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(1)

        title_label = QLabel("SignVerify Pro", title_wrap)
        title_label.setStyleSheet("color: white; font-size: 11pt; font-weight: 700;")

        subtitle_label = QLabel("AI Verification", title_wrap)
        subtitle_label.setStyleSheet(f"color: {C_TEXT_SECONDARY}; font-size: 8pt;")

        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)

        top_layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        top_layout.addWidget(title_wrap, alignment=Qt.AlignmentFlag.AlignVCenter)

        nav_widget = QWidget(self)
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 8, 0, 0)
        nav_layout.setSpacing(2)

        nav_items = [
            ("home", "🏠  Home"),
            ("database", "🗂  Database"),
            ("verification", "🖋  Verification"),
            ("history", "🕘  History"),
            ("settings", "⚙  Settings"),
        ]

        for screen_name, text in nav_items:
            button = QToolButton(nav_widget)
            button.setText(text)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedWidth(SIDEBAR_WIDTH)
            button.clicked.connect(
                lambda _checked=False, target=screen_name: NavigationController.get_instance().navigate_to(target)
            )
            nav_layout.addWidget(button)
            self.nav_buttons[screen_name] = button

        nav_layout.addStretch(1)

        footer = QWidget(self)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 10)
        footer_layout.setSpacing(6)

        divider = QFrame(footer)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background: #2b3b54; min-height: 1px; max-height: 1px;")

        version_label = QLabel(f"v{APP_VERSION}", footer)
        version_label.setStyleSheet("font-size: 8pt; color: #a5b4c8;")

        self.tier_label = QLabel(self.licence_manager.get_tier(), footer)
        self.tier_label.setStyleSheet("font-size: 8pt; color: #a5b4c8;")

        footer_layout.addWidget(divider)
        footer_layout.addWidget(version_label)
        footer_layout.addWidget(self.tier_label)

        layout.addWidget(top)
        layout.addWidget(nav_widget)
        layout.addStretch(1)
        layout.addWidget(footer)

    def set_active(self, screen_name: str) -> None:
        for name, button in self.nav_buttons.items():
            button.setProperty("active", name == screen_name)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def refresh_licence_tier(self) -> None:
        if self.tier_label is not None:
            self.tier_label.setText(self.licence_manager.get_tier())
