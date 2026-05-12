"""Centralized navigation controller singleton."""

from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)


class NavigationController:
    """Singleton controller that delegates navigation to the main window."""

    _instance = None

    def __init__(self) -> None:
        self._main_window = None

    @classmethod
    def get_instance(cls) -> "NavigationController":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_main_window(self, window) -> None:
        self._main_window = window

    def navigate_to(self, screen_name: str, **kwargs) -> None:
        if self._main_window is None:
            logger.warning("Navigation ignored, main window is not set")
            return
        logger.info("Navigating to screen: %s", screen_name)
        self._main_window.navigate_to(screen_name, **kwargs)


navigation_controller = NavigationController.get_instance()
