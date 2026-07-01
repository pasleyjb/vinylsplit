from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


@dataclass(frozen=True, slots=True)
class StartupWizardSelection:
    recording_path: str
    output_directory: str
    output_format: str


class StartupWizardDialog(QDialog):
    """Collect source recording and export defaults at app startup."""

    LAST_UPLOAD_DIR_KEY = "focused/lastUploadDirectory"
    LAST_SOURCE_FILE_KEY = "focused/lastSourceFile"
    OUTPUT_DIRECTORY_KEY = "focused/preferredOutputDirectory"
    OUTPUT_FORMAT_KEY = "focused/preferredOutputFormat"

    def __init__(self, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self.setWindowTitle("VinylSplit Setup")
        self.setModal(True)
        self.resize(620, 280)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        intro = QLabel(
            "Choose the recording to split, the output format, and where exports should be written."
        )
        intro.setWordWrap(True)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        self._source_input = QLineEdit()
        self._source_input.setPlaceholderText("Select a source recording")
        source_button = QPushButton("Browse...")
        source_button.clicked.connect(self._browse_source_file)
        source_row.addWidget(self._source_input, stretch=1)
        source_row.addWidget(source_button)
        form.addRow("Recording", source_row)

        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        self._output_input = QLineEdit()
        self._output_input.setPlaceholderText("Choose output directory")
        output_button = QPushButton("Browse...")
        output_button.clicked.connect(self._browse_output_directory)
        output_row.addWidget(self._output_input, stretch=1)
        output_row.addWidget(output_button)
        form.addRow("Output Folder", output_row)

        self._format_combo = QComboBox()
        self._format_combo.addItem("FLAC", "flac")
        self._format_combo.addItem("WAV", "wav")
        self._format_combo.addItem("MP3", "mp3")
        form.addRow("Output Format", self._format_combo)

        self._error_label = QLabel("")
        self._error_label.setObjectName("StatusBarText")
        self._error_label.setStyleSheet("color: #d24d57;")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(intro)
        root.addLayout(form)
        root.addWidget(self._error_label)
        root.addStretch(1)
        root.addWidget(buttons)

        self._load_defaults()

    def selection(self) -> StartupWizardSelection:
        return StartupWizardSelection(
            recording_path=self._source_input.text().strip(),
            output_directory=self._output_input.text().strip(),
            output_format=str(self._format_combo.currentData() or "flac").lower(),
        )

    def accept(self) -> None:
        chosen = self.selection()
        source_path = Path(chosen.recording_path)
        output_path = Path(chosen.output_directory)

        if not chosen.recording_path:
            self._error_label.setText("Please choose a recording file.")
            return
        if not source_path.exists() or not source_path.is_file():
            self._error_label.setText("Recording file does not exist.")
            return
        if not chosen.output_directory:
            self._error_label.setText("Please choose an output folder.")
            return
        if not output_path.exists() or not output_path.is_dir():
            self._error_label.setText("Output folder does not exist.")
            return

        self._settings.setValue(self.LAST_UPLOAD_DIR_KEY, str(source_path.parent))
        self._settings.setValue(self.LAST_SOURCE_FILE_KEY, str(source_path))
        self._settings.setValue(self.OUTPUT_DIRECTORY_KEY, str(output_path))
        self._settings.setValue(self.OUTPUT_FORMAT_KEY, chosen.output_format)
        self._error_label.setText("")
        super().accept()

    def _load_defaults(self) -> None:
        last_upload = str(self._settings.value(self.LAST_UPLOAD_DIR_KEY, "") or "").strip()
        last_source_file = str(self._settings.value(self.LAST_SOURCE_FILE_KEY, "") or "").strip()
        output_directory = str(self._settings.value(self.OUTPUT_DIRECTORY_KEY, "") or "").strip()
        preferred_format = str(self._settings.value(self.OUTPUT_FORMAT_KEY, "flac") or "flac").lower()

        if last_source_file and Path(last_source_file).is_file():
            self._source_input.setText(last_source_file)
        elif last_upload and Path(last_upload).is_dir():
            self._source_input.setText("")

        if output_directory:
            self._output_input.setText(output_directory)

        index = self._format_combo.findData(preferred_format)
        if index >= 0:
            self._format_combo.setCurrentIndex(index)

    def _browse_source_file(self) -> None:
        base = self._source_input.text().strip()
        if base and Path(base).is_file():
            start_dir = str(Path(base).parent)
        elif base and Path(base).is_dir():
            start_dir = base
        else:
            start_dir = str(self._settings.value(self.LAST_UPLOAD_DIR_KEY, str(Path.home())) or Path.home())

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose recording",
            start_dir,
            "Audio Files (*.flac *.wav *.aiff *.aif *.ogg *.mp3 *.m4a);;All Files (*)",
        )
        if filename:
            self._source_input.setText(filename)

    def _browse_output_directory(self) -> None:
        current = self._output_input.text().strip()
        start_dir = current or str(
            self._settings.value(self.OUTPUT_DIRECTORY_KEY, str(Path.cwd() / "output"))
            or (Path.cwd() / "output")
        )
        selected = QFileDialog.getExistingDirectory(self, "Choose output folder", start_dir)
        if selected:
            self._output_input.setText(selected)