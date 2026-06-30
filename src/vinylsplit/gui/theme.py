from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, Qt, QSettings, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


class AppearanceMode(str, Enum):
    """Supported appearance modes for the VinylSplit desktop shell."""

    FOLLOW_SYSTEM = "system"
    DARK = "dark"
    LIGHT = "light"


@dataclass(frozen=True, slots=True)
class ThemePalette:
    """Semantic theme tokens consumed by all presentation widgets."""

    background: str
    surface: str
    surface_elevated: str
    panel: str
    panel_elevated: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_text: str
    accent_hover: str
    accent_pressed: str
    border: str
    border_focus: str
    success: str
    warning: str
    error: str
    disabled: str
    selection: str
    drop_target: str
    drop_target_border: str


class ThemeManager(QObject):
    """Centralized runtime theme engine with persistence and system-follow support."""

    appearance_applied = Signal(str)

    _SETTINGS_KEY = "appearance/mode"

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self._settings = QSettings()
        self._mode = self._load_mode()

        style_hints = self._app.styleHints()
        if hasattr(style_hints, "colorSchemeChanged"):
            style_hints.colorSchemeChanged.connect(self._on_system_scheme_changed)

    @property
    def mode(self) -> AppearanceMode:
        """Return the user-selected appearance mode."""

        return self._mode

    def initialize(self) -> None:
        """Initialize app style and apply the persisted appearance."""

        self._app.setStyle("Fusion")
        self._app.setFont(QFont("Segoe UI", 10))
        self.apply_mode(self._mode, persist=False)

    def apply_mode(self, mode: AppearanceMode, persist: bool = True) -> None:
        """Apply an appearance mode immediately to the running application."""

        self._mode = mode
        if persist:
            self._settings.setValue(self._SETTINGS_KEY, mode.value)

        resolved = self._resolved_mode(mode)
        palette = dark_palette() if resolved is AppearanceMode.DARK else light_palette()
        self._app.setStyleSheet(render_stylesheet(palette))
        self.appearance_applied.emit(mode.value)

    def _load_mode(self) -> AppearanceMode:
        raw_value = self._settings.value(self._SETTINGS_KEY, AppearanceMode.FOLLOW_SYSTEM.value)
        try:
            return AppearanceMode(str(raw_value))
        except ValueError:
            return AppearanceMode.FOLLOW_SYSTEM

    def _resolved_mode(self, mode: AppearanceMode) -> AppearanceMode:
        if mode is not AppearanceMode.FOLLOW_SYSTEM:
            return mode

        scheme = self._app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return AppearanceMode.DARK

        return AppearanceMode.LIGHT

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._mode is AppearanceMode.FOLLOW_SYSTEM:
            self.apply_mode(self._mode, persist=False)


def dark_palette() -> ThemePalette:
    """Return VinylSplit dark semantic tokens."""

    return ThemePalette(
        background="#16141f",
        surface="#1f1b2d",
        surface_elevated="#29223d",
        panel="#1f1b2d",
        panel_elevated="#232039",
        text_primary="#ece8f8",
        text_secondary="#c8bfdf",
        text_muted="#a79ec5",
        accent="#7a4dff",
        accent_text="#ffffff",
        accent_hover="#8a63ff",
        accent_pressed="#6d44e0",
        border="#352d4f",
        border_focus="#9b82e8",
        success="#5cc78a",
        warning="#d9a85d",
        error="#d97284",
        disabled="#6f6884",
        selection="#2d2645",
        drop_target="#2a2440",
        drop_target_border="#9a7bff",
    )


def light_palette() -> ThemePalette:
    """Return VinylSplit light semantic tokens."""

    return ThemePalette(
        background="#f3f1f7",
        surface="#f8f7fb",
        surface_elevated="#ffffff",
        panel="#faf9fd",
        panel_elevated="#ffffff",
        text_primary="#252230",
        text_secondary="#4e4a5d",
        text_muted="#6f6a7f",
        accent="#7a4dff",
        accent_text="#ffffff",
        accent_hover="#8a63ff",
        accent_pressed="#6d44e0",
        border="#d8d4e4",
        border_focus="#7a4dff",
        success="#2f8a5b",
        warning="#a8761a",
        error="#b44960",
        disabled="#9a95a9",
        selection="#ebe6fa",
        drop_target="#ede7ff",
        drop_target_border="#7a4dff",
    )


def render_stylesheet(t: ThemePalette) -> str:
    """Render the global stylesheet from semantic tokens."""

    return f"""
    QWidget {{
        background-color: {t.background};
        color: {t.text_primary};
        font-size: 13px;
        selection-background-color: {t.selection};
    }}

    QMainWindow {{
        background-color: {t.background};
    }}

    QWidget#FocusedWorkspaceRoot[workspaceDropActive="true"] {{
        background-color: {t.drop_target};
        border-radius: 16px;
    }}

    QFrame#Card, QFrame#AlbumCard, QFrame#ProgressCard, QFrame#StatusBanner {{
        background-color: {t.surface};
        border: 1px solid {t.border};
        border-radius: 12px;
    }}

    QLabel#FocusedTitle {{
        font-size: 34px;
        font-weight: 700;
        color: {t.text_primary};
    }}

    QLabel#FocusedSubtitle {{
        font-size: 16px;
        color: {t.text_secondary};
        margin-bottom: 8px;
    }}

    QLabel#FocusedTagline {{
        font-size: 13px;
        color: {t.text_muted};
        letter-spacing: 0.6px;
        margin-bottom: 10px;
    }}

    QLabel#SectionTitle {{
        font-size: 14px;
        font-weight: 600;
        color: {t.text_primary};
    }}

    QFrame#DropZone {{
        background-color: {t.panel};
        border: 2px dashed {t.border};
        border-radius: 14px;
        min-height: 180px;
    }}

    QFrame#DropZone[compact="true"] {{
        min-height: 88px;
        border: 1px dashed {t.border};
        background-color: {t.surface};
    }}

    QFrame#DropZone[dragActive="true"] {{
        background-color: {t.drop_target};
        border: 2px solid {t.drop_target_border};
    }}

    QLabel#DropZoneTitle {{
        font-size: 22px;
        font-weight: 600;
        color: {t.text_primary};
    }}

    QLabel#DropZoneSubtitle {{
        font-size: 13px;
        color: {t.text_muted};
    }}

    QFrame#DropZone[compact="true"] QLabel#DropZoneTitle {{
        font-size: 15px;
    }}

    QFrame#DropZone[compact="true"] QLabel#DropZoneSubtitle {{
        font-size: 12px;
    }}

    QLabel#RecordingInfo {{
        background-color: {t.surface};
        border: 1px solid {t.border};
        border-radius: 10px;
        padding: 10px;
        color: {t.text_secondary};
    }}

    QLabel#ArtworkPlaceholder {{
        background-color: {t.surface_elevated};
        border: 1px solid {t.border};
        border-radius: 10px;
        color: {t.text_muted};
        font-size: 15px;
        font-weight: 500;
    }}

    QLabel#AlbumArtist {{
        font-size: 14px;
        color: {t.text_primary};
        font-weight: 600;
    }}

    QLabel#AlbumTitle {{
        font-size: 13px;
        color: {t.text_secondary};
    }}

    QPushButton {{
        background-color: {t.panel_elevated};
        border: 1px solid {t.border};
        border-radius: 10px;
        padding: 8px 14px;
        color: {t.text_primary};
        font-size: 13px;
    }}

    QPushButton:hover {{
        background-color: {t.selection};
    }}

    QPushButton:focus {{
        border: 1px solid {t.border_focus};
    }}

    QPushButton:pressed {{
        background-color: {t.surface};
    }}

    QPushButton:disabled {{
        color: {t.disabled};
    }}

    QPushButton#PrimaryButton {{
        background-color: {t.accent};
        border: 1px solid {t.accent_hover};
        color: {t.accent_text};
        font-size: 15px;
        font-weight: 600;
    }}

    QPushButton#PrimaryButton:hover {{
        background-color: {t.accent_hover};
    }}

    QPushButton#PrimaryButton:pressed {{
        background-color: {t.accent_pressed};
    }}

    QComboBox#WorkspaceSelector {{
        min-width: 140px;
        background-color: {t.panel_elevated};
        border: 1px solid {t.border};
        border-radius: 8px;
        padding: 6px 10px;
    }}

    QComboBox#WorkspaceSelector:focus {{
        border: 1px solid {t.border_focus};
    }}

    QComboBox, QLineEdit {{
        background-color: {t.surface_elevated};
        border: 1px solid {t.border};
        border-radius: 8px;
        padding: 6px 8px;
        color: {t.text_primary};
    }}

    QLineEdit:focus, QComboBox:focus {{
        border: 1px solid {t.border_focus};
    }}

    QGroupBox {{
        background-color: {t.surface};
        border: 1px solid {t.border};
        border-radius: 10px;
        margin-top: 10px;
        padding: 10px;
        color: {t.text_secondary};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 6px;
        color: {t.text_primary};
        font-weight: 600;
    }}

    QRadioButton {{
        spacing: 8px;
        color: {t.text_primary};
        min-height: 22px;
    }}

    QRadioButton::indicator {{
        width: 14px;
        height: 14px;
        border-radius: 7px;
        border: 1px solid {t.border};
        background: {t.surface_elevated};
    }}

    QRadioButton::indicator:checked {{
        border: 1px solid {t.accent};
        background: {t.accent};
    }}

    QRadioButton::indicator:focus {{
        border: 1px solid {t.border_focus};
    }}

    QProgressBar {{
        background-color: {t.surface_elevated};
        border: 1px solid {t.border};
        border-radius: 8px;
        text-align: center;
        min-height: 18px;
        color: {t.text_primary};
    }}

    QProgressBar::chunk {{
        background-color: {t.accent};
        border-radius: 8px;
    }}

    QListWidget {{
        background-color: {t.surface_elevated};
        border: 1px solid {t.border};
        border-radius: 10px;
        padding: 4px;
        color: {t.text_secondary};
    }}

    QTableWidget {{
        background-color: {t.surface_elevated};
        border: 1px solid {t.border};
        border-radius: 10px;
        gridline-color: {t.border};
        selection-background-color: {t.selection};
        alternate-background-color: {t.surface};
    }}

    QTableWidget::item {{
        padding: 6px;
    }}

    QHeaderView::section {{
        background-color: {t.surface};
        color: {t.text_primary};
        border: 0;
        border-bottom: 1px solid {t.border};
        padding: 6px 8px;
        font-weight: 600;
    }}

    QFrame#ReviewWaveformPlaceholder {{
        background-color: {t.panel};
        border: 1px dashed {t.border};
        border-radius: 10px;
        min-height: 210px;
        color: {t.text_muted};
    }}

    QLabel#InspectorValue {{
        color: {t.text_primary};
        font-size: 14px;
        font-weight: 600;
    }}

    QFrame#StatusBanner[tone="info"] {{
        background-color: {t.panel_elevated};
        border: 1px solid {t.border};
    }}

    QFrame#StatusBanner[tone="success"] {{
        background-color: {t.panel_elevated};
        border: 1px solid {t.success};
    }}

    QFrame#StatusBanner[tone="warning"] {{
        background-color: {t.panel_elevated};
        border: 1px solid {t.warning};
    }}

    QFrame#StatusBanner[tone="error"] {{
        background-color: {t.panel_elevated};
        border: 1px solid {t.error};
    }}

    QLabel#StatusBannerText, QLabel#StatusBarText {{
        color: {t.text_secondary};
    }}

    QLabel#ProgressLabel {{
        color: {t.text_secondary};
        font-weight: 600;
    }}
    """
