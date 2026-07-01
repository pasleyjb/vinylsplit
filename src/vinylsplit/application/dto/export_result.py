from __future__ import annotations

from dataclasses import dataclass

from vinylsplit.lookup import AlbumMatch
from vinylsplit.splitter import SplitTrack


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Export workflow summary exposed by the application layer."""

    source_file: str
    output_directory: str
    results: tuple[tuple[SplitTrack, AlbumMatch], ...]
    exported_tracks: int
    stopped: bool
