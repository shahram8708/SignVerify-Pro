"""Observations table widget for forensic feature assessments."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from config import (
    C_AMBER,
    C_AMBER_BG,
    C_DANGER,
    C_DANGER_BG,
    C_GREY_LT,
    C_SUCCESS,
    C_SUCCESS_BG,
    C_TEXT_PRIMARY,
    C_TEXT_SECONDARY,
)


class ObservationsTable(QTableWidget):
    """Two-column table for displaying forensic feature observations."""

    def __init__(self, parent=None) -> None:
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Forensic Feature", "Assessment"])

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 150)

        header_font = QFont(self.font())
        header_font.setBold(True)
        header.setFont(header_font)

        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self.setStyleSheet(
            f"""
            QHeaderView::section {{
                background: {C_GREY_LT};
                font-weight: 700;
                border: none;
                padding: 8px;
            }}
            """
        )

    def populate(self, observations: dict) -> None:
        self.clear_table()
        if not observations:
            return

        for feature_name, rating_raw in observations.items():
            row_index = self.rowCount()
            self.insertRow(row_index)

            feature_text = str(feature_name).replace("_", " ").title()
            feature_item = QTableWidgetItem(feature_text)
            feature_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.setItem(row_index, 0, feature_item)

            rating_value = "" if rating_raw is None else str(rating_raw)
            normalized = rating_value.strip().lower().replace(" ", "_")

            display_rating = rating_value.replace("_", " ").title()
            if normalized == "unable_to_assess":
                display_rating = "Unable to Assess"

            rating_item = QTableWidgetItem(display_rating)
            rating_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            rating_font = QFont(rating_item.font())
            if normalized in {"high", "medium", "low"}:
                rating_font.setBold(True)

            if normalized == "high":
                rating_item.setBackground(QBrush(QColor(C_SUCCESS_BG)))
                rating_item.setForeground(QBrush(QColor(C_SUCCESS)))
            elif normalized == "low":
                rating_item.setBackground(QBrush(QColor(C_DANGER_BG)))
                rating_item.setForeground(QBrush(QColor(C_DANGER)))
            elif normalized == "medium":
                rating_item.setBackground(QBrush(QColor(C_AMBER_BG)))
                rating_item.setForeground(QBrush(QColor(C_AMBER)))
            elif normalized == "unable_to_assess":
                rating_item.setBackground(QBrush(QColor(C_GREY_LT)))
                rating_item.setForeground(QBrush(QColor(C_TEXT_SECONDARY)))
            else:
                rating_item.setBackground(QBrush(QColor("#FFFFFF")))
                rating_item.setForeground(QBrush(QColor(C_TEXT_PRIMARY)))

            rating_item.setFont(rating_font)
            self.setItem(row_index, 1, rating_item)
            self.setRowHeight(row_index, 32)

    def clear_table(self) -> None:
        self.setRowCount(0)
