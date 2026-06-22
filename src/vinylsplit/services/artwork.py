"""Artwork and album folder management service."""

import subprocess
from pathlib import Path

import requests
from mutagen.flac import FLAC, Picture


class ArtworkService:
    """Manage album folders, artwork downloads, and embedding."""

    COVER_ART_ARCHIVE_URL = "https://coverartarchive.org/release"

    def __init__(self):
        self.downloaded_artwork: bytes | None = None

    def create_album_folder(
        self,
        output_directory: str,
        artist: str | None,
        album: str | None,
    ) -> Path:
        """Create a sanitized album folder inside the output directory.

        If artist and album are available, uses format: "Artist - Album".
        Otherwise uses generic "Album" or "output".
        """
        from vinylsplit.utils import sanitize_filename

        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)

        # Build folder name
        if artist and album:
            folder_name = f"{artist} - {album}"
        elif album:
            folder_name = album
        elif artist:
            folder_name = artist
        else:
            folder_name = "Album"

        folder_name = sanitize_filename(folder_name)
        album_folder = output / folder_name

        album_folder.mkdir(parents=True, exist_ok=True)

        return album_folder

    def download_artwork(self, release_id: str) -> bytes | None:
        """Download front cover artwork from Cover Art Archive.

        Returns the image bytes, or None if unavailable/failed.
        """
        if not release_id:
            return None

        try:
            response = requests.get(
                f"{self.COVER_ART_ARCHIVE_URL}/{release_id}/front",
                timeout=30,
            )

            if response.status_code == 200:
                self.downloaded_artwork = response.content
                return response.content

            return None
        except Exception:
            return None

    def save_cover_file(self, album_folder: Path, artwork: bytes) -> Path | None:
        """Save artwork as cover.jpg in the album folder.

        Returns the path to the saved cover file, or None on failure.
        """
        if not artwork:
            return None

        try:
            cover_path = album_folder / "cover.jpg"
            cover_path.write_bytes(artwork)
            return cover_path
        except Exception:
            return None

    def embed_artwork(self, flac_path: Path, artwork: bytes) -> bool:
        """Embed artwork into a FLAC file.

        Returns True on success, False on failure.
        """
        if not artwork:
            return False

        try:
            audio = FLAC(str(flac_path))

            picture = Picture()
            picture.type = 3  # Front Cover
            picture.mime = "image/jpeg"
            picture.data = artwork

            audio.clear_pictures()
            audio.add_picture(picture)
            audio.save()

            return True
        except Exception:
            return False

    def embed_artwork_batch(self, flac_paths: list[Path], artwork: bytes) -> int:
        """Embed artwork into multiple FLAC files.

        Returns the number of successful embeds.
        """
        count = 0
        for path in flac_paths:
            if self.embed_artwork(path, artwork):
                count += 1
        return count

    def set_folder_icon_linux(self, folder: Path, icon_path: Path) -> bool:
        """Set custom folder icon on Linux using gio.

        Uses: gio set <folder> metadata::custom-icon file://<icon_path>

        Returns True on success, False on failure or if gio unavailable.
        """
        try:
            # Check if gio is available
            subprocess.run(["which", "gio"], check=True, capture_output=True)

            # Set the custom icon
            icon_uri = f"file://{icon_path.resolve()}"
            subprocess.run(
                ["gio", "set", str(folder), "metadata::custom-icon", icon_uri],
                check=True,
                capture_output=True,
                timeout=10,
            )

            return True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            # gio not available, or command failed, or timeout
            return False
