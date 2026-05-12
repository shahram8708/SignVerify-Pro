"""Database management screen implementation."""

from __future__ import annotations

import csv
from datetime import datetime

from PyQt6.QtCore import QEvent, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
)

from config import (
    C_BLUE,
    C_BORDER,
    C_DANGER,
    C_DANGER_BG,
    C_GREY_LT,
    C_TEXT_PRIMARY,
    C_TEXT_SECONDARY,
    C_WHITE,
)
from controllers.database_controller import database_controller
from models.person import Person
from ui.base_screen import BaseScreen
from ui.dialogs.add_record_dialog import AddRecordDialog
from utils.logger import get_logger

logger = get_logger(__name__)


class SignatureThumbnailDelegate(QStyledItemDelegate):
    """Draws signature thumbnail previews in the Signature column."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(C_GREY_LT))

        thumbnail_data = index.data(Qt.ItemDataRole.UserRole)
        draw_rect = option.rect.adjusted(10, 8, -10, -8)

        pixmap = QPixmap()
        if isinstance(thumbnail_data, (bytes, bytearray)) and pixmap.loadFromData(bytes(thumbnail_data)):
            scaled = pixmap.scaled(
                draw_rect.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = draw_rect.x() + (draw_rect.width() - scaled.width()) // 2
            y = draw_rect.y() + (draw_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(C_GREY_LT))
            painter.drawRoundedRect(draw_rect, 4, 4)
            painter.setPen(QColor(C_TEXT_SECONDARY))
            painter.drawText(draw_rect, Qt.AlignmentFlag.AlignCenter, "No Image")

        painter.restore()


class SourceBadgeDelegate(QStyledItemDelegate):
    """Draws source badges for seed and manual records."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(C_GREY_LT))

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        badge_rect = option.rect.adjusted(12, 16, -12, -16)

        if text.lower() == "seed":
            bg_color = QColor(C_GREY_LT)
            border_color = QColor(C_BORDER)
            text_color = QColor(C_TEXT_SECONDARY)
        else:
            bg_color = QColor(C_WHITE)
            border_color = QColor(C_BLUE)
            text_color = QColor(C_BLUE)

        painter.setBrush(bg_color)
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(badge_rect, 10, 10)

        label_font = QFont(option.font)
        label_font.setBold(True)
        label_font.setPointSize(8)
        painter.setFont(label_font)
        painter.setPen(text_color)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


class ActionButtonDelegate(QStyledItemDelegate):
    """Renders and handles edit/delete action buttons in table rows."""

    edit_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def _button_rects(self, cell_rect: QRect) -> tuple[QRect, QRect]:
        button_height = 24
        button_width = 44
        gap = 4
        total_width = button_width * 2 + gap

        start_x = cell_rect.x() + max(0, (cell_rect.width() - total_width) // 2)
        y = cell_rect.y() + max(0, (cell_rect.height() - button_height) // 2)

        edit_rect = QRect(start_x, y, button_width, button_height)
        delete_rect = QRect(start_x + button_width + gap, y, button_width, button_height)
        return edit_rect, delete_rect

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(C_GREY_LT))

        edit_rect, delete_rect = self._button_rects(option.rect)

        painter.setBrush(QColor(C_WHITE))
        painter.setPen(QPen(QColor(C_BLUE), 1))
        painter.drawRoundedRect(edit_rect, 4, 4)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(C_DANGER_BG))
        painter.drawRoundedRect(delete_rect, 4, 4)

        edit_font = QFont(option.font)
        edit_font.setPointSize(7)
        edit_font.setBold(True)
        painter.setFont(edit_font)

        painter.setPen(QColor(C_BLUE))
        painter.drawText(edit_rect, Qt.AlignmentFlag.AlignCenter, "✏ Edit")

        painter.setPen(QColor(C_DANGER))
        painter.drawText(delete_rect, Qt.AlignmentFlag.AlignCenter, "🗑 Delete")

        painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:
        _ = model
        if event.type() != QEvent.Type.MouseButtonRelease:
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        person_id = index.sibling(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        if person_id is None:
            return False

        edit_rect, delete_rect = self._button_rects(option.rect)
        click_pos = event.pos()

        if edit_rect.contains(click_pos):
            self.edit_requested.emit(int(person_id))
            return True

        if delete_rect.contains(click_pos):
            self.delete_requested.emit(int(person_id))
            return True

        return False


class DatabaseScreen(BaseScreen):
    """Database management UI for adding, editing, searching, and exporting records."""

    HEADERS = ["ID", "Name", "Signature", "Added", "Source", "Actions"]

    def __init__(self, parent=None) -> None:
        self._search_timer: QTimer | None = None
        self._pending_search_query = ""
        self._person_map: dict[int, Person] = {}
        super().__init__(parent)

    def _build_ui(self) -> None:
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        toolbar = QFrame(self)
        toolbar.setStyleSheet(
            f"""
            QFrame {{
                background: {C_WHITE};
                border-bottom: 1px solid {C_BORDER};
            }}
            """
        )

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 16, 16, 16)
        toolbar_layout.setSpacing(10)

        self.search_input = QLineEdit(toolbar)
        self.search_input.setPlaceholderText("Search by name...")
        self.search_input.setMinimumWidth(250)
        self.search_input.textChanged.connect(self._on_search_changed)

        self.add_button = QPushButton("＋ Add Record", toolbar)
        self.add_button.clicked.connect(self._open_add_dialog)

        self.delete_selected_button = QPushButton("🗑 Delete Selected", toolbar)
        self.delete_selected_button.setObjectName("danger_btn")
        self.delete_selected_button.setProperty("danger", True)
        self.delete_selected_button.setEnabled(False)
        self.delete_selected_button.clicked.connect(self._delete_selected_row)

        self.export_csv_button = QPushButton("📥 Export CSV", toolbar)
        self.export_csv_button.setObjectName("secondary")
        self.export_csv_button.clicked.connect(self._export_visible_to_csv)

        toolbar_layout.addWidget(self.search_input)
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.add_button)
        toolbar_layout.addWidget(self.delete_selected_button)
        toolbar_layout.addWidget(self.export_csv_button)

        self.table_view = QTableView(self)
        self.model = QStandardItemModel(0, len(self.HEADERS), self)
        self.model.setHorizontalHeaderLabels(self.HEADERS)
        self.table_view.setModel(self.model)

        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_view.setShowGrid(False)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.verticalHeader().setDefaultSectionSize(60)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        header = self.table_view.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(0, 60)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 120)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(3, 150)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(4, 80)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(5, 100)

        self.signature_delegate = SignatureThumbnailDelegate(self.table_view)
        self.table_view.setItemDelegateForColumn(2, self.signature_delegate)

        self.source_delegate = SourceBadgeDelegate(self.table_view)
        self.table_view.setItemDelegateForColumn(4, self.source_delegate)

        self.actions_delegate = ActionButtonDelegate(self.table_view)
        self.actions_delegate.edit_requested.connect(self._open_edit_dialog_for_person)
        self.actions_delegate.delete_requested.connect(self._delete_person_by_id)
        self.table_view.setItemDelegateForColumn(5, self.actions_delegate)

        self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)

        self.status_label = QLabel("Showing 0 of 0 records", self)
        self.status_label.setStyleSheet(
            f"""
            QLabel {{
                padding: 8px 16px;
                color: {C_TEXT_SECONDARY};
                border-top: 1px solid {C_BORDER};
                background: {C_WHITE};
            }}
            """
        )

        self._search_timer = QTimer(self)
        self._search_timer.setInterval(300)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._perform_search)

        self.content_layout.addWidget(toolbar)
        self.content_layout.addWidget(self.table_view, 1)
        self.content_layout.addWidget(self.status_label)

    def _create_item(
        self,
        text: str,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        color: str = C_TEXT_PRIMARY,
        bold: bool = False,
    ) -> QStandardItem:
        item = QStandardItem(text)
        item.setEditable(False)
        item.setTextAlignment(alignment)
        item.setForeground(QBrush(QColor(color)))
        font = QFont(item.font())
        font.setBold(bold)
        item.setFont(font)
        return item

    def _format_date(self, value: datetime | None) -> str:
        if value is None:
            return ""
        return value.strftime("%d %b %Y")

    def _on_selection_changed(self) -> None:
        selected_rows = self.table_view.selectionModel().selectedRows()
        self.delete_selected_button.setEnabled(bool(selected_rows))

    def _on_search_changed(self, text: str) -> None:
        self._pending_search_query = text
        if self._search_timer is not None:
            self._search_timer.start()

    def _perform_search(self) -> None:
        self._load_data(search_query=self._pending_search_query)

    def _person_id_from_row(self, row: int) -> int | None:
        id_item = self.model.item(row, 0)
        if id_item is None:
            return None
        value = id_item.data(Qt.ItemDataRole.UserRole)
        if value is None:
            return None
        return int(value)

    def _load_data(self, search_query: str = "") -> None:
        if search_query.strip():
            people = database_controller.search_persons(search_query)
        else:
            people = database_controller.get_all_persons(search_query="")
        total_records = database_controller.get_person_count()

        sorting_enabled = self.table_view.isSortingEnabled()
        self.table_view.setSortingEnabled(False)

        self.model.removeRows(0, self.model.rowCount())
        self._person_map.clear()

        for person in people:
            self._person_map[person.id] = person

            id_item = self._create_item(
                str(person.id),
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                color=C_TEXT_SECONDARY,
            )
            id_item.setData(person.id, Qt.ItemDataRole.UserRole)

            name_item = self._create_item(str(person.full_name), bold=True)

            signature_item = self._create_item("")
            signature_item.setData(person.thumbnail_blob, Qt.ItemDataRole.UserRole)

            added_item = self._create_item(
                self._format_date(person.created_at),
                alignment=Qt.AlignmentFlag.AlignCenter,
                color=C_TEXT_SECONDARY,
            )

            source_text = "Seed" if int(person.is_seed or 0) == 1 else "Manual"
            source_item = self._create_item(source_text, alignment=Qt.AlignmentFlag.AlignCenter, color=C_TEXT_SECONDARY, bold=True)

            actions_item = self._create_item("")
            actions_item.setData(person.id, Qt.ItemDataRole.UserRole)

            self.model.appendRow([id_item, name_item, signature_item, added_item, source_item, actions_item])

        self.table_view.setSortingEnabled(sorting_enabled)

        visible = len(people)
        self.status_label.setText(f"Showing {visible} of {total_records} records")
        self._on_selection_changed()

    def _refresh_main_window_status(self) -> None:
        window = self.window()
        if hasattr(window, "refresh_status_bar"):
            window.refresh_status_bar()

    def _open_add_dialog(self) -> None:
        dialog = AddRecordDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_data(search_query=self.search_input.text().strip())
            self._refresh_main_window_status()

    def _open_edit_dialog_for_person(self, person_id: int) -> None:
        person = database_controller.get_person_by_id(person_id)
        if person is None:
            self.show_error("Edit Failed", "Could not find the selected record.")
            return

        dialog = AddRecordDialog(self, person=person)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_data(search_query=self.search_input.text().strip())
            self._refresh_main_window_status()

    def _on_row_double_clicked(self, index) -> None:
        person_id = self._person_id_from_row(index.row())
        if person_id is None:
            return
        self._open_edit_dialog_for_person(person_id)

    def _confirm_delete(self) -> bool:
        answer = QMessageBox.warning(
            self,
            "Confirm Delete",
            "Are you sure you want to delete this record? Associated verification history will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _delete_person_by_id(self, person_id: int) -> None:
        if not self._confirm_delete():
            return

        if not database_controller.delete_person(person_id):
            self.show_error("Delete Failed", "Unable to delete the selected record.")
            return

        self._load_data(search_query=self.search_input.text().strip())
        self._refresh_main_window_status()

    def _delete_selected_row(self) -> None:
        selected_rows = self.table_view.selectionModel().selectedRows()
        if not selected_rows:
            return

        row = selected_rows[0].row()
        person_id = self._person_id_from_row(row)
        if person_id is None:
            return
        self._delete_person_by_id(person_id)

    def _export_visible_to_csv(self) -> None:
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Records to CSV",
            "records.csv",
            "CSV Files (*.csv)",
        )
        if not output_path:
            return

        if not output_path.lower().endswith(".csv"):
            output_path = f"{output_path}.csv"

        try:
            with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["ID", "Name", "Created At", "Notes", "Is Seed"])

                for row in range(self.model.rowCount()):
                    person_id = self._person_id_from_row(row)
                    if person_id is None:
                        continue

                    person = self._person_map.get(person_id)
                    if person is None:
                        continue

                    created_at = person.created_at.strftime("%Y-%m-%d %H:%M:%S") if person.created_at else ""
                    writer.writerow(
                        [
                            person.id,
                            person.full_name,
                            created_at,
                            person.notes or "",
                            "Yes" if int(person.is_seed or 0) == 1 else "No",
                        ]
                    )

            self.show_success("Export Complete", f"CSV exported successfully to:\n{output_path}")
        except Exception as exc:
            logger.exception("CSV export failed")
            self.show_error("Export Failed", str(exc))

    def on_show(self, open_add_dialog: bool = False, **kwargs) -> None:
        _ = kwargs
        logger.info("Database screen shown")
        self._load_data(search_query=self.search_input.text().strip())
        self._refresh_main_window_status()

        if open_add_dialog:
            self._open_add_dialog()
