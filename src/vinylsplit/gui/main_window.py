from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from vinylsplit.application import ApplicationContext
from vinylsplit.gui.dialogs import PlaybackSettingsDialog
from vinylsplit.gui.theme import ThemeManager
from vinylsplit.gui.workspaces import FocusedWorkspace


class MainWindow(QMainWindow):
    """Top-level desktop shell hosting the Focused workspace."""

    _SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".flac", ".aiff", ".aif", ".ogg", ".mp3"}

    def __init__(
        self,
        app_context: ApplicationContext,
        theme_manager: ThemeManager,
        parent: QMainWindow | None = None,
    ) -> None:
        super().__init__(parent)
        self._app_context = app_context
        self._theme_manager = theme_manager
        self.setAcceptDrops(True)

        self.setWindowTitle("VinylSplit")
        self.resize(1280, 860)
        self.setMinimumSize(1024, 720)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addStretch(1)

        self._settings_button = QPushButton("Settings")
        self._settings_button.clicked.connect(self._open_playback_settings)
        header.addWidget(self._settings_button)

        self._stack = QStackedWidget()

        self._focused_workspace = FocusedWorkspace(app_context=self._app_context)
        self._stack.addWidget(self._focused_workspace)
        self._stack.setCurrentWidget(self._focused_workspace)
        self._theme_manager.appearance_applied.connect(self._animate_theme_transition)

        layout.addLayout(header)
        layout.addWidget(self._stack, stretch=1)

        self.setCentralWidget(root)

        self._opacity_effect = QGraphicsOpacityEffect(self._stack)
        self._stack.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(1.0)

        self._transition = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._transition.setDuration(180)
        self._transition.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def _open_playback_settings(self) -> None:
        dialog = PlaybackSettingsDialog(current_mode=self._theme_manager.mode, parent=self)
        if dialog.exec() == PlaybackSettingsDialog.DialogCode.Accepted:
            self._theme_manager.apply_mode(dialog.selected_mode())

    def _animate_workspace_transition(self, _workspace_id: str) -> None:
        """Apply subtle crossfade transition between workspace views."""

        if self._reduced_motion_enabled():
            self._opacity_effect.setOpacity(1.0)
            return

        self._transition.stop()
        self._opacity_effect.setOpacity(0.78)
        self._transition.setStartValue(0.78)
        self._transition.setEndValue(1.0)
        self._transition.start()

    def _animate_theme_transition(self, _mode: str) -> None:
        """Apply subtle transition when appearance updates at runtime."""

        if self._reduced_motion_enabled():
            return

        self._transition.stop()
        self._opacity_effect.setOpacity(0.92)
        self._transition.setStartValue(0.92)
        self._transition.setEndValue(1.0)
        self._transition.start()

    @staticmethod
    def _reduced_motion_enabled() -> bool:
        return bool(QApplication.instance().property("vinylsplit_reduced_motion"))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.suffix.lower() in self._SUPPORTED_AUDIO_EXTENSIONS:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if (
                path.exists()
                and path.is_file()
                and path.suffix.lower() in self._SUPPORTED_AUDIO_EXTENSIONS
            ):
                self._focused_workspace.load_recording(str(path))
                event.acceptProposedAction()
                return

        event.ignore()
