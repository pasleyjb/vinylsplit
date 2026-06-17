from dataclasses import dataclass, field

import numpy as np

from vinylsplit.detection import TrackBoundary


@dataclass(slots=True)
class SilenceRegion:
    """Represents one continuous region of silence."""

    start_window: int
    end_window: int

    @property
    def center_window(self) -> int:
        """Return the center window of the silence region."""
        return (self.start_window + self.end_window) // 2

    @property
    def length(self) -> int:
        """Return the length of the silence region in windows."""
        return self.end_window - self.start_window + 1


@dataclass(slots=True)
class AnalysisReport:
    """Complete results produced by the analysis engine."""

    sample_rate: int
    duration: float

    rms: np.ndarray

    threshold: float

    silence_regions: list[SilenceRegion] = field(default_factory=list)

    boundaries: list[TrackBoundary] = field(default_factory=list)