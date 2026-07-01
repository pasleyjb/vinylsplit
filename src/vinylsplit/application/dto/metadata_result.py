from __future__ import annotations

from dataclasses import dataclass

from vinylsplit.lookup import AlbumMatch


@dataclass(frozen=True, slots=True)
class MetadataResult:
    """Metadata lookup result exposed by the application layer."""

    source_file: str
    match: AlbumMatch | None
    found: bool
