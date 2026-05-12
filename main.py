from dotenv import load_dotenv

load_dotenv()

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QMessageBox

import config
from config import APP_NAME, APP_VERSION
from database.db_manager import init_db
from services.seed_service import run_seed_if_empty
from utils.logger import get_logger

logger = get_logger(__name__)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("SignVerifyPro")
    app.setApplicationVersion(APP_VERSION)

    try:
        init_db()
        (config.APP_DATA_DIR / "temp").mkdir(parents=True, exist_ok=True)
        (config.APP_DATA_DIR / "signatures").mkdir(parents=True, exist_ok=True)
        logger.info("Application directories initialized")
        run_seed_if_empty()
        app.setFont(QFont("Segoe UI", 9))

        from ui.main_window import MainWindow

        window = MainWindow()
        window.showMaximized()
        return app.exec()
    except Exception as exc:
        logger.exception("Critical startup error")
        QMessageBox.critical(
            None,
            "Startup Error",
            f"A critical startup error occurred:\n{exc}",
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
