"""Review candidate boundaries and confidence evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReviewCandidate:
    """One candidate boundary detected during analysis."""

    timestamp: float
    """Exact timestamp of the candidate boundary."""

    confidence: float
    """Confidence [0.0, 1.0] that this is a real boundary."""

    reason: str
    """Why this candidate was detected (e.g., 'Silence peak', 'Spectral transition')."""

    @property
    def display_name(self) -> str:
        """Human-readable label for the candidate."""
        return f"{self.timestamp:.2f}s ({self.reason}, {self.confidence * 100:.0f}%)"


@dataclass(frozen=True, slots=True)
class ConfidenceBreakdown:
    """Per-detector confidence contributions."""

    silence_score: float = 0.0
    """Confidence from silence/RMS analysis."""

    distance_score: float = 0.0
    """Confidence from proximity to expected metadata boundary."""

    overall: float = 0.0
    """Combined confidence [0.0, 1.0]."""

    @property
    def display_text(self) -> str:
        """Summary for inspector display."""
        parts = []
        if self.silence_score > 0:
            parts.append(f"silence {self.silence_score * 100:.0f}%")
        if self.distance_score > 0:
            parts.append(f"distance {self.distance_score * 100:.0f}%")
        return " + ".join(parts) if parts else "unknown sources"
