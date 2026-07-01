from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from vinylsplit.gui.theme import AppearanceMode


class PlaybackSettingsDialog(QDialog):
    """Placeholder dialog for selecting and configuring playback providers."""

    OUTPUT_DIRECTORY_KEY = "focused/preferredOutputDirectory"
    OUTPUT_FORMAT_KEY = "focused/preferredOutputFormat"

    def __init__(self, current_mode: AppearanceMode, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(520, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        intro = QLabel("Configure appearance and export preferences.")
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

        output_group = QGroupBox("Output")
        output_layout = QVBoxLayout(output_group)
        output_layout.setContentsMargins(12, 10, 12, 10)
        output_layout.setSpacing(8)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        output_row = QHBoxLayout()
        output_row.setSpacing(8)

        self._output_directory_input = QLineEdit()
        self._output_directory_input.setPlaceholderText("Choose a default output folder")
        stored_output = self._settings.value(self.OUTPUT_DIRECTORY_KEY, "")
        self._output_directory_input.setText(str(stored_output or ""))

        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self._browse_for_output_directory)

        clear_button = QPushButton("Clear")
        clear_button.setObjectName("SecondaryButton")
        clear_button.clicked.connect(self._output_directory_input.clear)

        output_row.addWidget(self._output_directory_input, stretch=1)
        output_row.addWidget(browse_button)
        output_row.addWidget(clear_button)

        form.addRow("Default folder", output_row)

        self._output_format_combo = QComboBox()
        self._output_format_combo.addItem("FLAC", "flac")
        self._output_format_combo.addItem("WAV", "wav")
        self._output_format_combo.addItem("MP3", "mp3")
        stored_format = str(self._settings.value(self.OUTPUT_FORMAT_KEY, "flac") or "flac").lower()
        format_index = self._output_format_combo.findData(stored_format)
        if format_index >= 0:
            self._output_format_combo.setCurrentIndex(format_index)
        form.addRow("Default format", self._output_format_combo)

        output_layout.addLayout(form)

        note = QLabel("When set, VinylSplit will use this folder as the default archive destination.")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        output_layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(intro)
        root.addWidget(appearance_group)
        root.addWidget(output_group)
        root.addStretch(1)
        root.addWidget(buttons)

    def accept(self) -> None:
        output_directory = self.selected_output_directory()
        if output_directory:
            self._settings.setValue(self.OUTPUT_DIRECTORY_KEY, output_directory)
        else:
            self._settings.remove(self.OUTPUT_DIRECTORY_KEY)
        self._settings.setValue(self.OUTPUT_FORMAT_KEY, self.selected_output_format())
        super().accept()

    def selected_mode(self) -> AppearanceMode:
        """Return selected appearance mode."""

        if self._dark_mode.isChecked():
            return AppearanceMode.DARK
        if self._light_mode.isChecked():
            return AppearanceMode.LIGHT
        return AppearanceMode.FOLLOW_SYSTEM

    def selected_output_directory(self) -> str | None:
        value = self._output_directory_input.text().strip()
        return value or None

    def selected_output_format(self) -> str:
        return str(self._output_format_combo.currentData() or "flac").lower()

    def _browse_for_output_directory(self) -> None:
        current_value = self._output_directory_input.text().strip()
        initial_directory = current_value or str(Path.cwd() / "output")
        selected = QFileDialog.getExistingDirectory(self, "Choose default output folder", initial_directory)
        if selected:
            self._output_directory_input.setText(selected)

    def _set_mode(self, mode: AppearanceMode) -> None:
        if mode is AppearanceMode.DARK:
            self._dark_mode.setChecked(True)
        elif mode is AppearanceMode.LIGHT:
            self._light_mode.setChecked(True)
        else:
            self._system_mode.setChecked(True)
