"""Verification history screen with filtering and audit log table."""

from __future__ import annotations

import csv
import json
from datetime import datetime, time, timedelta

from PyQt6.QtCore import QDate, QTimer, Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import C_AMBER, C_BLUE, C_BORDER, C_DANGER, C_GREY_LT, C_NAVY, C_SUCCESS, C_TEXT_SECONDARY
from controllers.database_controller import database_controller
from controllers.navigation_controller import NavigationController
from models.verification import Verification
from ui.base_screen import BaseScreen
from ui.widgets.verdict_badge import VerdictBadge
from utils.licence_manager import LicenceManager
from utils.logger import get_logger

logger = get_logger(__name__)


class HistoryScreen(BaseScreen):
    """Audit log view for all historical verifications."""

    MODE_LABELS = {
        "A_SCREEN": "🖥 Screen",
        "B_UPLOAD": "📁 Upload",
        "B_CAMERA": "📷 Camera",
        "C_ADHOC": "⚖ Ad-Hoc",
    }

    def __init__(self, parent=None) -> None:
        self.current_verifications: list[Verification] = []
        self.search_timer: QTimer | None = None
        super().__init__(parent)

    def _build_ui(self) -> None:
        self.content_layout.setContentsMargins(16, 14, 16, 14)
        self.content_layout.setSpacing(10)

        title = QLabel("Verification History", self)
        title.setStyleSheet(f"font-size: 20pt; font-weight: 700; color: {C_NAVY};")

        subtitle = QLabel("Complete audit log of all signature verifications", self)
        subtitle.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"color: {C_BORDER};")

        self.content_layout.addWidget(title)
        self.content_layout.addWidget(subtitle)
        self.content_layout.addWidget(divider)

        self._build_filter_toolbar()
        self._build_table()
        self._build_status_row()

    def _build_filter_toolbar(self) -> None:
        toolbar = QFrame(self)
        toolbar.setStyleSheet(
            f"background: {C_GREY_LT}; border: 1px solid {C_BORDER}; border-radius: 8px;"
        )
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.search_input = QLineEdit(toolbar)
        self.search_input.setPlaceholderText("Search by person name...")
        self.search_input.setMinimumWidth(220)
        self.search_input.textChanged.connect(self._on_search_text_changed)

        self.verdict_filter_combo = QComboBox(toolbar)
        self.verdict_filter_combo.addItems(["All Verdicts", "MATCH", "MISMATCH", "INCONCLUSIVE"])
        self.verdict_filter_combo.currentIndexChanged.connect(self._load_data)

        self.date_from_edit = QDateEdit(toolbar)
        self.date_from_edit.setCalendarPopup(True)
        self.date_from_edit.setDate(QDate.currentDate().addDays(-30))
        self.date_from_edit.dateChanged.connect(self._load_data)

        self.date_to_edit = QDateEdit(toolbar)
        self.date_to_edit.setCalendarPopup(True)
        self.date_to_edit.setDate(QDate.currentDate())
        self.date_to_edit.dateChanged.connect(self._load_data)

        clear_button = QPushButton("Clear Filters", toolbar)
        clear_button.setObjectName("secondary")
        clear_button.clicked.connect(self._clear_filters)

        export_button = QPushButton("📥 Export CSV", toolbar)
        export_button.setObjectName("secondary")
        export_button.clicked.connect(self._export_csv)

        from_label = QLabel("From", toolbar)
        from_label.setStyleSheet(f"color: {C_TEXT_SECONDARY};")
        to_label = QLabel("To", toolbar)
        to_label.setStyleSheet(f"color: {C_TEXT_SECONDARY};")

        layout.addWidget(self.search_input)
        layout.addWidget(self.verdict_filter_combo)
        layout.addWidget(from_label)
        layout.addWidget(self.date_from_edit)
        layout.addWidget(to_label)
        layout.addWidget(self.date_to_edit)
        layout.addWidget(clear_button)
        layout.addStretch(1)
        layout.addWidget(export_button)

        self.content_layout.addWidget(toolbar)

        self.search_timer = QTimer(self)
        self.search_timer.setInterval(300)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._load_data)

    def _build_table(self) -> None:
        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(
            ["Timestamp", "Person", "Mode", "Verdict", "Confidence", "Flagged", "Actions"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)

        header = self.table.horizontalHeader()
        header.resizeSection(0, 150)
        header.resizeSection(1, 180)
        header.resizeSection(2, 120)
        header.resizeSection(3, 130)
        header.resizeSection(4, 100)
        header.resizeSection(5, 80)
        header.resizeSection(6, 100)

        self.content_layout.addWidget(self.table, 1)

    def _build_status_row(self) -> None:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.showing_label = QLabel("Showing 0 verifications", row)
        self.showing_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        self.total_label = QLabel("Total: 0 records in database", row)
        self.total_label.setStyleSheet(f"font-size: 9pt; color: {C_TEXT_SECONDARY};")

        layout.addWidget(self.showing_label)
        layout.addStretch(1)
        layout.addWidget(self.total_label)
        self.content_layout.addWidget(row)

    def _on_search_text_changed(self) -> None:
        if self.search_timer is not None:
            self.search_timer.start()

    def _clear_filters(self) -> None:
        self.search_input.clear()
        self.verdict_filter_combo.setCurrentIndex(0)
        self.date_from_edit.setDate(QDate.currentDate().addDays(-30))
        self.date_to_edit.setDate(QDate.currentDate())
        self._load_data()

    def _format_timestamp(self, value: datetime | None) -> str:
        if value is None:
            return ""
        return value.strftime("%d %b %Y %H:%M")

    def _load_data(self) -> None:
        search_name = self.search_input.text().strip() or None
        verdict_value = self.verdict_filter_combo.currentText().strip()
        verdict_filter = None if verdict_value == "All Verdicts" else verdict_value

        from_date = self.date_from_edit.date().toPyDate()
        to_date = self.date_to_edit.date().toPyDate()
        date_from = datetime.combine(from_date, time.min)
        date_to = datetime.combine(to_date, time.max)

        self.current_verifications = database_controller.get_all_verifications(
            limit=100000,
            offset=0,
            verdict_filter=verdict_filter,
            search_name=search_name,
            date_from=date_from,
            date_to=date_to,
        )

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for row_index, verification in enumerate(self.current_verifications):
            self.table.insertRow(row_index)

            timestamp_item = QTableWidgetItem(self._format_timestamp(verification.verified_at))
            timestamp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_index, 0, timestamp_item)

            if verification.mode == "C_ADHOC" or verification.person is None:
                person_item = QTableWidgetItem("Ad-Hoc")
                italic_font = QFont(person_item.font())
                italic_font.setItalic(True)
                person_item.setFont(italic_font)
                person_item.setForeground(QColor(C_TEXT_SECONDARY))
            else:
                person_item = QTableWidgetItem(verification.person.full_name)
            self.table.setItem(row_index, 1, person_item)

            mode_text = self.MODE_LABELS.get(verification.mode, verification.mode)
            mode_item = QTableWidgetItem(mode_text)
            mode_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_index, 2, mode_item)

            verdict_badge = VerdictBadge(verification.verdict, self.table)
            verdict_badge.setFixedHeight(30)
            self.table.setCellWidget(row_index, 3, verdict_badge)

            confidence_value = float(verification.confidence or 0.0)
            confidence_text = f"{confidence_value * 100.0:.1f}%"
            confidence_item = QTableWidgetItem(confidence_text)
            confidence_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if confidence_value > 0.65:
                confidence_item.setForeground(QColor(C_SUCCESS))
            elif confidence_value < 0.50:
                confidence_item.setForeground(QColor(C_DANGER))
            else:
                confidence_item.setForeground(QColor(C_AMBER))
            self.table.setItem(row_index, 4, confidence_item)

            flagged_text = "⚑ Flagged" if int(verification.flagged_for_review or 0) == 1 else ""
            flagged_item = QTableWidgetItem(flagged_text)
            flagged_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if flagged_text:
                flagged_item.setForeground(QColor(C_AMBER))
            self.table.setItem(row_index, 5, flagged_item)

            view_button = QPushButton("View →", self.table)
            view_button.setObjectName("secondary")
            view_button.setFixedWidth(60)
            view_button.clicked.connect(
                lambda _checked=False, vid=verification.id: self._view_verification(vid)
            )
            self.table.setCellWidget(row_index, 6, view_button)

            self.table.setRowHeight(row_index, 44)

        self.table.setSortingEnabled(True)

        filtered_count = len(self.current_verifications)
        all_count = len(database_controller.get_all_verifications(limit=100000, offset=0))
        self.showing_label.setText(f"Showing {filtered_count} verifications")
        self.total_label.setText(f"Total: {all_count} records in database")

    def _view_verification(self, verification_id: int) -> None:
        verification = database_controller.get_verification_by_id(verification_id)
        if verification is None:
            self.show_error("Not Found", "Selected verification record no longer exists.")
            return

        observations = {}
        if verification.observations_json:
            try:
                parsed_observations = json.loads(verification.observations_json)
                if isinstance(parsed_observations, dict):
                    observations = parsed_observations
            except json.JSONDecodeError:
                observations = {}

        result_dict = {}
        if verification.raw_response_json:
            try:
                parsed_result = json.loads(verification.raw_response_json)
                if isinstance(parsed_result, dict):
                    result_dict = parsed_result
            except json.JSONDecodeError:
                result_dict = {}

        result_dict["verdict"] = verification.verdict
        result_dict["confidence"] = float(verification.confidence or 0.0)
        result_dict["reason"] = verification.reason or ""
        result_dict["observations"] = observations
        result_dict.setdefault("model_used", "gemini-2.5-flash")
        result_dict.setdefault("raw_response", verification.raw_response_json or "")

        person = (
            database_controller.get_person_by_id(verification.person_id)
            if verification.person_id is not None
            else None
        )

        NavigationController.get_instance().navigate_to(
            "results",
            result_dict=result_dict,
            verification=verification,
            person=person,
        )

    def _export_csv(self) -> None:
        licence_manager = LicenceManager.get_instance()
        if not licence_manager.can_export_csv():
            licence_manager.show_upgrade_prompt(self, "CSV Export")
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Verification History",
            f"signverify_history_{datetime.now().strftime('%Y%m%d')}.csv",
            "CSV Files (*.csv)",
        )
        if not output_path:
            return
        if not output_path.lower().endswith(".csv"):
            output_path = f"{output_path}.csv"

        try:
            with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(
                    [
                        "ID",
                        "Timestamp",
                        "Person Name",
                        "Mode",
                        "Verdict",
                        "Confidence",
                        "Reason",
                        "Flagged",
                        "Exported",
                    ]
                )

                for verification in self.current_verifications:
                    person_name = "Ad-Hoc"
                    if verification.person is not None:
                        person_name = verification.person.full_name

                    reason = (verification.reason or "").strip()
                    if len(reason) > 200:
                        reason = reason[:200] + "..."

                    writer.writerow(
                        [
                            verification.id,
                            self._format_timestamp(verification.verified_at),
                            person_name,
                            verification.mode,
                            verification.verdict,
                            f"{float(verification.confidence or 0.0) * 100.0:.1f}%",
                            reason,
                            "Yes" if int(verification.flagged_for_review or 0) == 1 else "No",
                            "Yes" if int(verification.exported or 0) == 1 else "No",
                        ]
                    )

            self.show_success("CSV Exported", f"Filtered history exported to:\n{output_path}")
        except Exception as exc:
            logger.exception("Failed to export history CSV")
            self.show_error("Export Failed", str(exc))

    def on_show(self, **kwargs) -> None:
        _ = kwargs
        logger.info("HistoryScreen shown")
        self._load_data()
