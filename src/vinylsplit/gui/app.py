from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from vinylsplit.application import build_application_context
from vinylsplit.gui.main_window import MainWindow
from vinylsplit.gui.theme import ThemeManager


def run() -> int:
    """Run the VinylSplit desktop application."""

    app = QApplication(sys.argv)
    app.setApplicationName("VinylSplit")
    app.setOrganizationName("VinylSplit")
    app.setProperty("vinylsplit_reduced_motion", _reduced_motion_requested())

    theme_manager = ThemeManager(app)
    theme_manager.initialize()

    app_context = build_application_context()
    window = MainWindow(app_context=app_context, theme_manager=theme_manager)
    window.show()

    return app.exec()


def _reduced_motion_requested() -> bool:
    value = os.getenv("VINYLSPLIT_REDUCED_MOTION", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}
