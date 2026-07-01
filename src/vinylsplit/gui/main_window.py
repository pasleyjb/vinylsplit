from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from vinylsplit.application import ApplicationContext
from vinylsplit.gui.dialogs import PlaybackSettingsDialog
from vinylsplit.gui.dialogs.startup_wizard_dialog import StartupWizardSelection
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

        self._stack = QStackedWidget()

        self._focused_workspace = FocusedWorkspace(app_context=self._app_context)
        self._focused_workspace.enable_top_menu_mode(True)
        self._stack.addWidget(self._focused_workspace)
        self._stack.setCurrentWidget(self._focused_workspace)
        self._theme_manager.appearance_applied.connect(self._animate_theme_transition)

        layout.addWidget(self._stack, stretch=1)

        self.setCentralWidget(root)
        self._build_top_menus()

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
            self._focused_workspace.set_preferred_output_directory(dialog.selected_output_directory())
            self._focused_workspace.set_preferred_output_format(dialog.selected_output_format())

    def _build_top_menus(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("File")
        select_action = QAction("Select Recording", self)
        select_action.triggered.connect(self._focused_workspace.menu_select_recording)
        file_menu.addAction(select_action)

        analyze_action = QAction("Analyze Now", self)
        analyze_action.triggered.connect(self._focused_workspace.menu_archive_now)
        file_menu.addAction(analyze_action)

        review_action = QAction("Open Review", self)
        review_action.triggered.connect(self._focused_workspace.menu_open_review)
        file_menu.addAction(review_action)

        split_action = QAction("Split", self)
        split_action.triggered.connect(self._focused_workspace.menu_split)
        file_menu.addAction(split_action)

        output_action = QAction("Open Output Folder", self)
        output_action.triggered.connect(self._focused_workspace.menu_open_output_folder)
        file_menu.addAction(output_action)

        file_menu.addSeparator()
        reset_action = QAction("Archive Another Album", self)
        reset_action.triggered.connect(self._focused_workspace.menu_archive_another_album)
        file_menu.addAction(reset_action)

        edit_menu = menu_bar.addMenu("Edit")
        undo_action = QAction("Undo", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._focused_workspace.menu_undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Redo", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self._focused_workspace.menu_redo)
        edit_menu.addAction(redo_action)

        settings_menu = menu_bar.addMenu("Settings")

        open_settings_action = QAction("Open Settings...", self)
        open_settings_action.triggered.connect(self._open_playback_settings)
        settings_menu.addAction(open_settings_action)

        settings_menu.addSeparator()

        auto_analyze_action = QAction("Automatically Analyze", self)
        auto_analyze_action.setCheckable(True)
        auto_analyze_action.setChecked(self._focused_workspace.auto_analyze_enabled())
        auto_analyze_action.toggled.connect(self._focused_workspace.set_auto_analyze_enabled)
        settings_menu.addAction(auto_analyze_action)

        auto_review_action = QAction("Open Review Only When Needed", self)
        auto_review_action.setCheckable(True)
        auto_review_action.setChecked(self._focused_workspace.auto_review_enabled())
        auto_review_action.toggled.connect(self._focused_workspace.set_auto_review_enabled)
        settings_menu.addAction(auto_review_action)

        auto_split_action = QAction("Automatically Split When Confident", self)
        auto_split_action.setCheckable(True)
        auto_split_action.setChecked(self._focused_workspace.auto_split_enabled())
        auto_split_action.toggled.connect(self._focused_workspace.set_auto_split_enabled)
        settings_menu.addAction(auto_split_action)

        auto_artwork_action = QAction("Automatically Fetch Artwork", self)
        auto_artwork_action.setCheckable(True)
        auto_artwork_action.setChecked(self._focused_workspace.auto_artwork_enabled())
        auto_artwork_action.toggled.connect(self._focused_workspace.set_auto_artwork_enabled)
        settings_menu.addAction(auto_artwork_action)

    def begin_startup_flow(self, selection: StartupWizardSelection) -> None:
        self._focused_workspace.begin_startup_flow(selection)

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
