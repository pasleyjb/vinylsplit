from dataclasses import dataclass, field

from vinylsplit.detection import TrackBoundary


@dataclass
class AnalysisReport:
    """Complete analysis of an audio recording."""

    filename: str

    duration: float

    sample_rate: int

    channels: int

    detected_tracks: list[TrackBoundary] = field(default_factory=list)

    confidence: float = 0.0

    warnings: list[str] = field(default_factory=list)

    notes: list[str] = field(default_factory=list)

    @property
    def track_count(self) -> int:
        """Return the number of detected tracks."""
        return len(self.detected_tracks)