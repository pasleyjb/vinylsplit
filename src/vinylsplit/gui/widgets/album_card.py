from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class AlbumCard(QFrame):
    """Compact placeholder card for artwork and album metadata."""

    def __init__(self, parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AlbumCard")

        self._artwork = QLabel("Artwork")
        self._artwork.setObjectName("ArtworkPlaceholder")
        self._artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artwork.setMinimumHeight(140)

        self._artist = QLabel("Unknown Artist")
        self._artist.setObjectName("AlbumArtist")

        self._album = QLabel("Unknown Album")
        self._album.setObjectName("AlbumTitle")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(self._artwork)
        layout.addWidget(self._artist)
        layout.addWidget(self._album)

    def set_album(self, artist: str, title: str) -> None:
        """Update card labels for album context."""

        self._artist.setText(artist)
        self._album.setText(title)
