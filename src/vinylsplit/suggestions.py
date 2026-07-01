"""Suggestion models for adaptive boundary review.

A Suggestion represents a candidate improvement discovered during local
reanalysis.  Suggestions are purely informational: they never modify
boundaries automatically.  The user always decides whether to apply one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Suggestion:
    """A candidate boundary improvement found during local reanalysis.

    Attributes
    ----------
    track_number:
        The track whose boundary would be affected.
    current_position:
        The boundary position currently set (seconds).
    suggested_position:
        The stronger position found during reanalysis (seconds).
    reason:
        Human-readable explanation of why this position is suggested.
    confidence_delta:
        How much the boundary confidence would improve (0–1 scale).
        Positive means the suggested position is stronger.
    distance_ms:
        Distance between the current and suggested position (milliseconds).
    """

    track_number: int
    current_position: float
    suggested_position: float
    reason: str
    confidence_delta: float
    distance_ms: float

    @classmethod
    def from_positions(
        cls,
        track_number: int,
        current_position: float,
        suggested_position: float,
        reason: str,
        confidence_delta: float = 0.0,
    ) -> "Suggestion":
        """Construct a suggestion, computing distance_ms automatically."""

        distance_ms = abs(suggested_position - current_position) * 1000.0

        return cls(
            track_number=track_number,
            current_position=current_position,
            suggested_position=suggested_position,
            reason=reason,
            confidence_delta=confidence_delta,
            distance_ms=distance_ms,
        )

    def summary_text(self) -> str:
        """One-line description for display in the suggestions panel."""

        suggested_m = int(self.suggested_position // 60)
        suggested_s = self.suggested_position % 60
        return (
            f"Track {self.track_number}: "
            f"stronger transition at {suggested_m:02d}:{suggested_s:06.3f} "
            f"({self.distance_ms:.0f} ms away)"
        )
