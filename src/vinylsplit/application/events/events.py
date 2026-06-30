from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProcessingStarted:
    """Event raised when end-to-end processing starts."""

    source_file: str
    output_directory: str


@dataclass(frozen=True, slots=True)
class ProgressUpdated:
    """Event raised when application-level progress changes."""

    stage: str
    completed: int
    total: int | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class MetadataFound:
    """Event raised when metadata lookup returns a match."""

    source_file: str
    artist: str
    album: str
    confidence: float


@dataclass(frozen=True, slots=True)
class TracksDetected:
    """Event raised when analysis detects boundaries."""

    source_file: str
    track_count: int


@dataclass(frozen=True, slots=True)
class ReviewRequested:
    """Event raised when manual review is required or started."""

    source_file: str
    detected_track_count: int
    expected_track_count: int | None = None


@dataclass(frozen=True, slots=True)
class ReviewCompleted:
    """Event raised when review has been completed."""

    source_file: str
    approved_track_count: int
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class ExportStarted:
    """Event raised when export begins."""

    source_file: str
    output_directory: str


@dataclass(frozen=True, slots=True)
class ExportCompleted:
    """Event raised when export completes."""

    source_file: str
    output_directory: str
    exported_tracks: int


@dataclass(frozen=True, slots=True)
class ProcessingFailed:
    """Event raised when processing fails."""

    source_file: str
    error_message: str
