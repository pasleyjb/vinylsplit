from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)

from vinylsplit.gui.theme import AppearanceMode


class PlaybackSettingsDialog(QDialog):
    """Placeholder dialog for selecting and configuring playback providers."""

    def __init__(self, current_mode: AppearanceMode, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(520, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        intro = QLabel("Configure appearance and playback integration preferences.")
        intro.setWordWrap(True)

        appearance_group = QGroupBox("Appearance")
        appearance_layout = QVBoxLayout(appearance_group)
        appearance_layout.setContentsMargins(12, 10, 12, 10)
        appearance_layout.setSpacing(8)

        self._appearance_buttons = QButtonGroup(self)

        self._system_mode = QRadioButton("Follow System")
        self._dark_mode = QRadioButton("Dark")
        self._light_mode = QRadioButton("Light")

        self._appearance_buttons.addButton(self._system_mode)
        self._appearance_buttons.addButton(self._dark_mode)
        self._appearance_buttons.addButton(self._light_mode)

        appearance_layout.addWidget(self._system_mode)
        appearance_layout.addWidget(self._dark_mode)
        appearance_layout.addWidget(self._light_mode)

        self._set_mode(current_mode)

        playback_group = QGroupBox("Playback (Placeholder)")
        playback_layout = QVBoxLayout(playback_group)
        playback_layout.setContentsMargins(12, 10, 12, 10)
        playback_layout.setSpacing(8)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        provider = QComboBox()
        provider.addItem("Internal Preview (future)")
        provider.addItem("System Default Player (future)")
        provider.addItem("mpv (future)")
        provider.addItem("VLC (future)")
        provider.addItem("Foobar2000 (future)")
        provider.addItem("Audacious (future)")

        executable = QLineEdit()
        executable.setPlaceholderText("Optional custom executable path")

        form.addRow("Provider", provider)
        form.addRow("Executable", executable)
        playback_layout.addLayout(form)

        note = QLabel("Playback providers are extension points and are not active in this milestone.")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        playback_layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(intro)
        root.addWidget(appearance_group)
        root.addWidget(playback_group)
        root.addStretch(1)
        root.addWidget(buttons)

    def selected_mode(self) -> AppearanceMode:
        """Return selected appearance mode."""

        if self._dark_mode.isChecked():
            return AppearanceMode.DARK
        if self._light_mode.isChecked():
            return AppearanceMode.LIGHT
        return AppearanceMode.FOLLOW_SYSTEM

    def _set_mode(self, mode: AppearanceMode) -> None:
        if mode is AppearanceMode.DARK:
            self._dark_mode.setChecked(True)
        elif mode is AppearanceMode.LIGHT:
            self._light_mode.setChecked(True)
        else:
            self._system_mode.setChecked(True)
