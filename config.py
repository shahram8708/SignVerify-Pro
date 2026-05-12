"""Application configuration constants for SignVerify Pro."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "SignVerify Pro"
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

IS_FROZEN = bool(getattr(sys, "frozen", False))
SOURCE_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else SOURCE_DIR


def _resolve_assets_dir() -> Path:
    if not IS_FROZEN:
        return SOURCE_DIR / "assets"

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets")
    candidates.append(RUNTIME_DIR / "assets")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0] if candidates else SOURCE_DIR / "assets"


BASE_DIR = SOURCE_DIR
ASSETS_DIR = _resolve_assets_dir()
ICONS_DIR = ASSETS_DIR / "icons"
SEED_SIGNATURES_DIR = ASSETS_DIR / "seed_signatures"
FONTS_DIR = ASSETS_DIR / "fonts"

if os.name == "nt":
    appdata_root = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    APP_DATA_DIR = appdata_root / "SignVerifyPro"
else:
    APP_DATA_DIR = Path.home() / ".signverifypro"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

SIGNATURES_STORAGE_DIR = APP_DATA_DIR / "signatures"
SIGNATURES_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def resolve_signature_path(relative_path: str) -> str:
    """Resolve stored signature paths that may be absolute or relative."""
    if not relative_path:
        return str(SIGNATURES_STORAGE_DIR.resolve())

    candidate = Path(relative_path)
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)

    if candidate.is_absolute() and not candidate.exists():
        candidate = Path(candidate.name)

    return str((SIGNATURES_STORAGE_DIR / candidate).resolve())

_default_db_path = APP_DATA_DIR / "signverify.db" if IS_FROZEN else SOURCE_DIR / "signverify.db"
_db_path = Path(os.getenv("DB_PATH", str(_default_db_path)))
if not _db_path.is_absolute():
    _db_base_dir = RUNTIME_DIR if IS_FROZEN else SOURCE_DIR
    _db_path = _db_base_dir / _db_path
DB_PATH = _db_path.resolve()

LOG_FILE_PATH = APP_DATA_DIR / "logs" / "signverify.log" if IS_FROZEN else SOURCE_DIR / "logs" / "signverify.log"
LICENCE_TIER = os.getenv("LICENCE_TIER", "FREE")

C_NAVY = "#0A1628"
C_BLUE = "#1565C0"
C_BLUE_HOVER = "#1976D2"
C_GOLD = "#F9A825"
C_SUCCESS = "#2E7D32"
C_SUCCESS_BG = "#E8F5E9"
C_DANGER = "#C62828"
C_DANGER_BG = "#FFEBEE"
C_AMBER = "#E65100"
C_AMBER_BG = "#FFF3E0"
C_GREY_LT = "#F5F7FA"
C_WHITE = "#FFFFFF"
C_BORDER = "#E0E4EC"
C_TEXT_PRIMARY = "#1A1A2E"
C_TEXT_SECONDARY = "#6B7280"
C_SIDEBAR_ACTIVE_BG = "#1E3A5F"
C_BLUE_TINT = "#F0F7FF"
C_BLUE_TINT_STRONG = "#E3F2FD"
C_INFO_BORDER = "#90CAF9"
C_MUTED_BORDER = "#D0D5DD"
C_TABLE_HEADER = "#EEF2F7"
C_TABLE_GRID = "#D9DEE8"
C_GREY_SOFT = "#FAFBFC"

MIN_WINDOW_WIDTH = 1280
MIN_WINDOW_HEIGHT = 800
SIDEBAR_WIDTH = 220

SCREEN_NAMES = {
    "home": 0,
    "database": 1,
    "verification": 2,
    "mode_a": 3,
    "mode_b": 4,
    "mode_c": 5,
    "results": 6,
    "history": 7,
    "settings": 8,
}

GLOBAL_QSS = f"""
QMainWindow, QWidget {{
    background: {C_WHITE};
    color: {C_TEXT_PRIMARY};
    font-family: 'Segoe UI';
    font-size: 9.5pt;
}}

QStackedWidget {{
    background: {C_WHITE};
}}

QPushButton {{
    background: {C_BLUE};
    color: {C_WHITE};
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 700;
}}

QPushButton:hover {{
    background: {C_BLUE_HOVER};
}}

QPushButton:disabled {{
    background: #d1d5db;
    color: #9ca3af;
}}

QPushButton#secondary {{
    background: {C_WHITE};
    color: {C_TEXT_PRIMARY};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
}}

QPushButton#secondary:hover {{
    background: {C_GREY_LT};
}}

QPushButton[danger="true"] {{
    background: {C_DANGER};
    color: {C_WHITE};
}}

QLineEdit {{
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    background: {C_WHITE};
}}

QLineEdit:focus {{
    border: 2px solid {C_BLUE};
}}

QComboBox {{
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    background: {C_WHITE};
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

QTableWidget, QTableView {{
    gridline-color: {C_BORDER};
    alternate-background-color: {C_GREY_LT};
    background: {C_WHITE};
    selection-background-color: #E3F2FD;
    selection-color: {C_TEXT_PRIMARY};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
}}

QHeaderView::section {{
    background: {C_GREY_LT};
    font-weight: 700;
    border: none;
    border-bottom: 2px solid {C_BORDER};
    padding: 8px;
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

QTabWidget::pane {{
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    top: -1px;
}}

QTabBar::tab {{
    padding: 10px 20px;
    border-radius: 6px 6px 0 0;
    margin-right: 2px;
    background: {C_GREY_LT};
    color: {C_TEXT_SECONDARY};
}}

QTabBar::tab:selected {{
    background: {C_BLUE};
    color: {C_WHITE};
}}

QStatusBar {{
    background: {C_NAVY};
    color: {C_WHITE};
    font-size: 8pt;
}}

QMessageBox {{
    background: {C_WHITE};
    font-family: 'Segoe UI';
    font-size: 9.5pt;
}}

QToolTip {{
    background: {C_NAVY};
    color: {C_WHITE};
    border: none;
    padding: 6px 10px;
    border-radius: 4px;
}}

QSlider::groove:horizontal {{
    height: 6px;
    background: {C_BORDER};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    background: {C_BLUE};
    border-radius: 8px;
    margin: -5px 0;
}}

QSpinBox, QDoubleSpinBox {{
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    background: {C_WHITE};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {C_BORDER};
    border-radius: 4px;
    background: {C_WHITE};
}}

QCheckBox::indicator:checked {{
    background: {C_BLUE};
    border: 2px solid {C_BLUE};
}}
"""
