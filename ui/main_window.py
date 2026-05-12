"""Main window shell for SignVerify Pro."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, select

from config import (
    C_AMBER,
    C_AMBER_BG,
    C_BORDER,
    C_TEXT_PRIMARY,
    C_TEXT_SECONDARY,
    GLOBAL_QSS,
    ICONS_DIR,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    SCREEN_NAMES,
)
from controllers.navigation_controller import NavigationController
from controllers.settings_controller import settings_controller
from database.db_manager import SessionLocal
from models.person import Person
from ui.screens.database_screen import DatabaseScreen
from ui.screens.history_screen import HistoryScreen
from ui.screens.home_screen import HomeScreen
from ui.screens.mode_a_screen import ModeAScreen
from ui.screens.mode_b_screen import ModeBScreen
from ui.screens.mode_c_screen import ModeCScreen
from ui.screens.results_screen import ResultsScreen
from ui.screens.settings_screen import SettingsScreen
from ui.screens.verification_hub import VerificationHubScreen
from ui.sidebar import SidebarNav
from utils.logger import get_logger

logger = get_logger(__name__)


class MainWindow(QMainWindow):
    """Root application window containing sidebar and stacked screens."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SignVerify Pro — AI-Powered Signature Verification")
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)

        self._set_window_icon_if_available()

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(GLOBAL_QSS)

        self.sidebar: SidebarNav | None = None
        self.stack: QStackedWidget | None = None
        self.screens: dict[str, QWidget] = {}

        self.status_operation_label: QLabel | None = None
        self.api_indicator_label: QLabel | None = None
        self.record_count_label: QLabel | None = None

        self.api_banner: QFrame | None = None
        self.window_controls_bar: QFrame | None = None

        self.minimize_button: QPushButton | None = None
        self.maximize_button: QPushButton | None = None
        self.close_button: QPushButton | None = None

        self._build_ui()
        self._center_on_primary_screen()
        self._refresh_maximize_button_icon()

        NavigationController.get_instance().set_main_window(self)

        self.navigate_to("home")
        self.refresh_status_indicators()
        self.update_api_banner()

    def _set_window_icon_if_available(self) -> None:
        icon_candidates = ["app.ico", "app.png", "icon.png", "signverify.ico"]
        for filename in icon_candidates:
            path = Path(ICONS_DIR) / filename
            if path.exists():
                self.setWindowIcon(QIcon(str(path)))
                return

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = SidebarNav(self)
        layout.addWidget(self.sidebar)

        right_container = QWidget(self)
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.window_controls_bar = self._build_window_controls_bar(right_container)
        right_layout.addWidget(self.window_controls_bar)

        self.api_banner = self._build_api_banner(right_container)
        right_layout.addWidget(self.api_banner)

        self.stack = QStackedWidget(right_container)
        right_layout.addWidget(self.stack, stretch=1)

        layout.addWidget(right_container, stretch=1)

        self._init_screens()
        self._init_status_bar()

    def _build_api_banner(self, parent: QWidget) -> QFrame:
        banner = QFrame(parent)
        banner.setVisible(False)
        banner.setStyleSheet(
            f"""
            QFrame {{
                background: {C_AMBER_BG};
                border-bottom: 1px solid #f4c76d;
            }}
            QLabel {{
                color: {C_AMBER};
                font-weight: 600;
            }}
            """
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        message = QLabel(
            "No Gemini API key configured. Go to Settings to add your key.",
            banner,
        )

        button = QPushButton("Open Settings", banner)
        button.setObjectName("secondary")
        button.clicked.connect(lambda: self.navigate_to("settings"))

        layout.addWidget(message)
        layout.addStretch(1)
        layout.addWidget(button)

        return banner

    def _build_window_controls_bar(self, parent: QWidget) -> QFrame:
        bar = QFrame(parent)
        bar.setObjectName("window_controls_bar")
        bar.setStyleSheet(
            f"""
            QFrame#window_controls_bar {{
                background: white;
                border-bottom: 1px solid {C_BORDER};
            }}
            QLabel#window_controls_title {{
                color: {C_TEXT_PRIMARY};
                font-size: 9pt;
                font-weight: 700;
            }}
            QPushButton#window_control_button {{
                background: transparent;
                border: none;
                border-radius: 5px;
                padding: 0px;
            }}
            QPushButton#window_control_button:hover {{
                background: #f3f4f6;
            }}
            QPushButton#window_control_button:pressed {{
                background: #e5e7eb;
            }}
            QPushButton#window_close_button {{
                background: transparent;
                border: none;
                border-radius: 5px;
                padding: 0px;
            }}
            QPushButton#window_close_button:hover {{
                background: #ef4444;
            }}
            QPushButton#window_close_button:pressed {{
                background: #dc2626;
            }}
            """
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("SignVerify Pro", bar)
        title.setObjectName("window_controls_title")

        subtitle = QLabel("Desktop Mode", bar)
        subtitle.setStyleSheet(f"color: {C_TEXT_SECONDARY}; font-size: 8pt;")

        title_wrap = QWidget(bar)
        title_layout = QVBoxLayout(title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        self.minimize_button = QPushButton(bar)
        self.minimize_button.setObjectName("window_control_button")
        self.minimize_button.setFixedSize(34, 26)
        self.minimize_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minimize_button.setToolTip("Minimize")
        self.minimize_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMinButton)
        )
        self.minimize_button.clicked.connect(self.showMinimized)

        self.maximize_button = QPushButton(bar)
        self.maximize_button.setObjectName("window_control_button")
        self.maximize_button.setFixedSize(34, 26)
        self.maximize_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.maximize_button.clicked.connect(self._toggle_maximize_restore)

        self.close_button = QPushButton(bar)
        self.close_button.setObjectName("window_close_button")
        self.close_button.setFixedSize(34, 26)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.setToolTip("Close")
        self.close_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)
        )
        self.close_button.clicked.connect(self.close)

        layout.addWidget(title_wrap)
        layout.addStretch(1)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        return bar

    def _toggle_maximize_restore(self) -> None:
        if self.isMaximized() or self.isFullScreen():
            self.showNormal()
        else:
            self.showMaximized()

    def _refresh_maximize_button_icon(self) -> None:
        if self.maximize_button is None:
            return

        if self.isMaximized() or self.isFullScreen():
            self.maximize_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton)
            )
            self.maximize_button.setToolTip("Restore Down")
        else:
            self.maximize_button.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMaxButton)
            )
            self.maximize_button.setToolTip("Maximize")

    def _init_screens(self) -> None:
        self.screens = {
            "home": HomeScreen(self),
            "database": DatabaseScreen(self),
            "verification": VerificationHubScreen(self),
            "mode_a": ModeAScreen(self),
            "mode_b": ModeBScreen(self),
            "mode_c": ModeCScreen(self),
            "results": ResultsScreen(self),
            "history": HistoryScreen(self),
            "settings": SettingsScreen(self),
        }

        if self.stack is None:
            return

        for screen_name, _ in sorted(SCREEN_NAMES.items(), key=lambda item: item[1]):
            self.stack.addWidget(self.screens[screen_name])

    def _init_status_bar(self) -> None:
        status = QStatusBar(self)
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)

        self.status_operation_label = QLabel("Ready", self)
        self.status_operation_label.setStyleSheet("color: white;")

        center_spacer = QWidget(self)
        center_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        right_widget = QWidget(self)
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.api_indicator_label = QLabel("●", self)
        self.api_indicator_label.setStyleSheet("color: #9ca3af; font-size: 12pt;")

        self.record_count_label = QLabel("0 records in database", self)
        self.record_count_label.setStyleSheet("color: white;")

        right_layout.addWidget(self.api_indicator_label)
        right_layout.addWidget(self.record_count_label)

        status.addWidget(self.status_operation_label, 1)
        status.addWidget(center_spacer, 1)
        status.addPermanentWidget(right_widget)

    def _center_on_primary_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return

        geometry = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(geometry.center())
        self.move(frame.topLeft())

    def navigate_to(self, screen_name: str, **kwargs) -> None:
        if screen_name not in SCREEN_NAMES:
            logger.warning("Unknown screen requested: %s", screen_name)
            return

        if self.stack is None:
            return

        index = SCREEN_NAMES[screen_name]
        self.stack.setCurrentIndex(index)

        screen = self.screens.get(screen_name)
        if screen is not None and hasattr(screen, "on_show"):
            screen.on_show(**kwargs)

        if self.sidebar is not None:
            sidebar_target = screen_name
            if screen_name in {"mode_a", "mode_b", "mode_c", "results"}:
                sidebar_target = "verification"
            self.sidebar.set_active(sidebar_target)

        if self.status_operation_label is not None:
            friendly_name = screen_name.replace("_", " ").title()
            self.status_operation_label.setText(f"Viewing {friendly_name}")

    def refresh_status_indicators(self) -> None:
        api_key = settings_controller.get_api_key().strip()

        if self.api_indicator_label is not None:
            if api_key:
                self.api_indicator_label.setStyleSheet("color: #2E7D32; font-size: 12pt;")
                self.api_indicator_label.setToolTip("API key configured")
            else:
                self.api_indicator_label.setStyleSheet("color: #9ca3af; font-size: 12pt;")
                self.api_indicator_label.setToolTip("API key not configured")

        if self.sidebar is not None:
            self.sidebar.refresh_licence_tier()

        self.refresh_status_bar()

    def refresh_status_bar(self) -> None:
        """Refresh status bar record count text from the database."""

        try:
            with SessionLocal() as session:
                count = session.scalar(select(func.count()).select_from(Person)) or 0
        except Exception as exc:
            logger.exception("Failed to count database records")
            count = 0
            if self.status_operation_label is not None:
                self.status_operation_label.setText(f"Database status warning: {exc}")

        if self.record_count_label is not None:
            self.record_count_label.setText(f"{count} records in database")

    def update_api_banner(self) -> None:
        api_key = settings_controller.get_api_key().strip()
        if self.api_banner is not None:
            self.api_banner.setVisible(not bool(api_key))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._refresh_maximize_button_icon()
