from __future__ import annotations

from vinylsplit.application.dto.review_result import ReviewResult
from vinylsplit.application.interfaces.services import ReviewServiceInterface
from vinylsplit.pipeline import Pipeline


class ReviewService(ReviewServiceInterface):
    """Application service for preparing review sessions."""

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    def review(
        self,
        filename: str,
        expected_track_count: int | None = None,
        expected_boundary_times: tuple[float, ...] | None = None,
        diagnostics: bool = False,
    ) -> ReviewResult:
        """Create a review session from existing pipeline analysis."""

        if not filename.strip():
            raise ValueError("filename must not be empty")

        session = self._pipeline.create_review_session(
            filename=filename,
            expected_track_count=expected_track_count,
            expected_boundary_times=list(expected_boundary_times)
            if expected_boundary_times is not None
            else None,
            diagnostics=diagnostics,
        )
        return ReviewResult(
            source_file=filename,
            session=session,
            detected_track_count=len(session.boundaries),
        )
