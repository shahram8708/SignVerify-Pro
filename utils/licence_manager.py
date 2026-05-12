"""Licence tier management and feature gating."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QAbstractItemView, QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout

from config import C_BLUE, C_BORDER, C_DANGER, C_GOLD, C_GREY_LT, C_NAVY, C_TEXT_PRIMARY, C_TEXT_SECONDARY, C_WHITE
from controllers.settings_controller import settings_controller
from utils.logger import get_logger

logger = get_logger(__name__)


class LicenceManager:
    """Singleton manager that gates features by configured licence tier."""

    FREE = "FREE"
    PROFESSIONAL = "PROFESSIONAL"
    ENTERPRISE = "ENTERPRISE"

    _instance: "LicenceManager | None" = None

    @classmethod
    def get_instance(cls) -> "LicenceManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_tier(self) -> str:
        try:
            return settings_controller.get_licence_tier()
        except Exception:
            logger.exception("Failed to read persisted licence tier, falling back to environment")
            tier = os.getenv("LICENCE_TIER", self.FREE).strip().upper()
            if tier not in {self.FREE, self.PROFESSIONAL, self.ENTERPRISE}:
                return self.FREE
            return tier

    def set_tier(self, tier: str) -> None:
        normalized_tier = str(tier or "").strip().upper()
        if normalized_tier not in {self.FREE, self.PROFESSIONAL, self.ENTERPRISE}:
            raise ValueError("Invalid licence tier")

        settings_controller.set_licence_tier(normalized_tier)
        os.environ["LICENCE_TIER"] = normalized_tier

    def upgrade_to_professional(self) -> tuple[bool, str]:
        current_tier = self.get_tier()
        if current_tier in {self.PROFESSIONAL, self.ENTERPRISE}:
            return True, f"Account already on {current_tier.title()} tier"

        try:
            self.set_tier(self.PROFESSIONAL)
            logger.info("Licence tier upgraded from FREE to PROFESSIONAL")
            return True, "Account upgraded to Professional successfully"
        except Exception as exc:
            logger.exception("Licence upgrade to Professional failed")
            return False, f"Upgrade failed: {exc}"

    def can_export_pdf(self) -> bool:
        return self.get_tier() in {self.PROFESSIONAL, self.ENTERPRISE}

    def can_export_csv(self) -> bool:
        return self.get_tier() in {self.PROFESSIONAL, self.ENTERPRISE}

    def can_verify_unlimited(self) -> bool:
        return self.get_tier() in {self.PROFESSIONAL, self.ENTERPRISE}

    def get_daily_verification_limit(self) -> int:
        if self.can_verify_unlimited():
            return 999999
        return 10

    def is_enterprise(self) -> bool:
        return self.get_tier() == self.ENTERPRISE

    def check_verification_limit(self, verifications_today: int) -> tuple[bool, str]:
        if self.can_verify_unlimited():
            return True, ""

        if verifications_today >= self.get_daily_verification_limit():
            return (
                False,
                "You have reached the daily verification limit of 10 for the Free tier. "
                "Upgrade to Professional for unlimited verifications.",
            )

        return True, ""

    def show_upgrade_prompt(self, parent_widget, feature_name: str) -> None:
        dialog = QDialog(parent_widget)
        dialog.setModal(True)
        dialog.setWindowTitle("Feature Not Available on Free Tier")
        dialog.setMinimumWidth(520)
        dialog.setStyleSheet(
            f"""
            QDialog {{
                background: {C_WHITE};
            }}
            QLabel#title {{
                color: {C_NAVY};
                font-size: 15pt;
                font-weight: 700;
            }}
            QLabel#message {{
                color: {C_TEXT_PRIMARY};
                font-size: 10pt;
            }}
            QTableWidget {{
                border: 1px solid {C_BORDER};
                background: {C_WHITE};
                alternate-background-color: {C_GREY_LT};
                gridline-color: {C_BORDER};
            }}
            QHeaderView::section {{
                background: {C_GREY_LT};
                color: {C_TEXT_SECONDARY};
                font-weight: 700;
                padding: 6px;
                border: none;
                border-bottom: 1px solid {C_BORDER};
            }}
            QPushButton#later {{
                background: {C_WHITE};
                color: {C_TEXT_PRIMARY};
                border: 1px solid {C_BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton#later:hover {{
                background: {C_GREY_LT};
            }}
            QPushButton#learn {{
                background: {C_BLUE};
                color: {C_WHITE};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 700;
            }}
            QPushButton#learn:hover {{
                background: {C_NAVY};
            }}
            """
        )

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(10)

        lock_icon = QLabel("🔒", dialog)
        lock_icon.setStyleSheet("font-size: 24pt;")
        lock_icon.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(4)

        title = QLabel("Feature Not Available on Free Tier", dialog)
        title.setObjectName("title")

        message = QLabel(
            f"<b>{feature_name}</b> is available on the Professional and Enterprise plans.",
            dialog,
        )
        message.setObjectName("message")
        message.setTextFormat(Qt.TextFormat.RichText)
        message.setWordWrap(True)

        title_wrap.addWidget(title)
        title_wrap.addWidget(message)

        icon_row.addWidget(lock_icon)
        icon_row.addLayout(title_wrap, 1)
        layout.addLayout(icon_row)

        comparison_table = QTableWidget(2, 3, dialog)
        comparison_table.setHorizontalHeaderLabels(["Feature", "Free", "Professional"])
        comparison_table.verticalHeader().setVisible(False)
        comparison_table.setAlternatingRowColors(True)
        comparison_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        comparison_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        comparison_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        comparison_table.setFixedHeight(125)

        rows = [
            (feature_name, "✗", "✓"),
            ("Daily Verifications", "10/day", "Unlimited"),
        ]

        for row_idx, row_data in enumerate(rows):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(value)
                if col_idx == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if value == "✗":
                        item.setForeground(QBrush(QColor(C_DANGER)))
                    if value == "✓":
                        item.setForeground(QBrush(QColor(C_GOLD)))
                comparison_table.setItem(row_idx, col_idx, item)

        comparison_table.horizontalHeader().setStretchLastSection(True)
        comparison_table.horizontalHeader().setDefaultSectionSize(140)
        comparison_table.horizontalHeader().setMinimumSectionSize(100)
        layout.addWidget(comparison_table)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        maybe_later_btn = QPushButton("Maybe Later", dialog)
        maybe_later_btn.setObjectName("later")
        maybe_later_btn.clicked.connect(dialog.reject)

        learn_more_btn = QPushButton("Learn More", dialog)
        learn_more_btn.setObjectName("learn")

        def _open_upgrade() -> None:
            QDesktopServices.openUrl(QUrl("https://signverifypro.com/upgrade"))
            dialog.accept()

        learn_more_btn.clicked.connect(_open_upgrade)

        buttons.addWidget(maybe_later_btn)
        buttons.addWidget(learn_more_btn)
        layout.addLayout(buttons)

        dialog.exec()
