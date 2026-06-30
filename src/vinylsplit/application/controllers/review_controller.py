from __future__ import annotations

from vinylsplit.application.dto.review_result import ReviewResult
from vinylsplit.application.interfaces.services import ReviewServiceInterface


class ReviewController:
    """Translate presentation requests into review service calls."""

    def __init__(self, review_service: ReviewServiceInterface) -> None:
        self._review_service = review_service

    def review(
        self,
        filename: str,
        expected_track_count: int | None = None,
        expected_boundary_times: tuple[float, ...] | None = None,
        diagnostics: bool = False,
    ) -> ReviewResult:
        """Create a review session from a source recording."""

        return self._review_service.review(
            filename=filename,
            expected_track_count=expected_track_count,
            expected_boundary_times=expected_boundary_times,
            diagnostics=diagnostics,
        )
