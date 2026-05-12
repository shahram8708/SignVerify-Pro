"""Verdict badge widget."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QSizePolicy

from config import C_AMBER, C_DANGER, C_GREY_LT, C_SUCCESS, C_TEXT_SECONDARY


class VerdictBadge(QLabel):
    """Compact badge widget for showing verification verdict state."""

    def __init__(self, verdict: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(10)
        self.setFont(font)

        self.set_verdict(verdict)

    def set_verdict(self, verdict: str) -> None:
        normalized = (verdict or "").strip().upper()

        if normalized == "MATCH":
            text = "✓ MATCH"
            bg = C_SUCCESS
            fg = "#FFFFFF"
        elif normalized == "MISMATCH":
            text = "✗ MISMATCH"
            bg = C_DANGER
            fg = "#FFFFFF"
        elif normalized == "INCONCLUSIVE":
            text = "⚠ INCONCLUSIVE"
            bg = C_AMBER
            fg = "#FFFFFF"
        else:
            text = "—"
            bg = C_GREY_LT
            fg = C_TEXT_SECONDARY

        self.setText(text)
        self.setStyleSheet(
            f"""
            QLabel {{
                background: {bg};
                color: {fg};
                padding: 6px 12px;
                border-radius: 12px;
                font-weight: 700;
            }}
            """
        )
        self.adjustSize()

    def clear_verdict(self) -> None:
        self.set_verdict("")
