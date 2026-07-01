from __future__ import annotations

from dataclasses import dataclass

from vinylsplit.review_state import AdaptiveReviewState


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """Review workflow result exposed to presentation callers."""

    source_file: str
    session: AdaptiveReviewState
    detected_track_count: int
