from __future__ import annotations

from vinylsplit.application.dto.review_result import ReviewResult
from vinylsplit.application.dto.review import ReviewSessionDTO, ReviewBoundaryDTO
from vinylsplit.application.interfaces.services import ReviewServiceInterface
from vinylsplit.application.services.review_mapper import map_session_to_dto, map_boundary_to_dto
from vinylsplit.pipeline import Pipeline
from vinylsplit.boundary_states import BoundaryState
from vinylsplit.review_state import AdaptiveReviewState


class ReviewService(ReviewServiceInterface):
    """Application service for preparing review sessions."""

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline
        self._current_session: AdaptiveReviewState | None = None

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
        self._current_session = session
        return ReviewResult(
            source_file=filename,
            session=session,
            detected_track_count=len(session.boundaries),
        )

    # DTO-based interface for GUI consumption (Phase 4+)

    def get_session_dto(self) -> ReviewSessionDTO | None:
        """Get current session as frozen DTO for GUI."""
        if self._current_session is None:
            return None
        return map_session_to_dto(self._current_session)

    def get_boundary_dto(self, track_number: int) -> ReviewBoundaryDTO | None:
        """Get a specific boundary as DTO."""
        if self._current_session is None:
            return None
        for boundary in self._current_session.boundaries:
            if boundary.track_number == track_number:
                return map_boundary_to_dto(boundary)
        return None

    def verify_boundary(self, track_number: int) -> bool:
        """Mark a boundary as verified by user."""
        if self._current_session is None:
            return False
        for boundary in self._current_session.boundaries:
            if boundary.track_number == track_number:
                boundary.state = BoundaryState.VERIFIED
                return True
        return False

    def lock_boundary(self, track_number: int) -> bool:
        """Lock a boundary to prevent editing."""
        if self._current_session is None:
            return False
        for boundary in self._current_session.boundaries:
            if boundary.track_number == track_number:
                boundary.state = BoundaryState.LOCKED
                return True
        return False

    def unlock_boundary(self, track_number: int) -> bool:
        """Unlock a boundary to allow editing."""
        if self._current_session is None:
            return False
        for boundary in self._current_session.boundaries:
            if boundary.track_number == track_number:
                if boundary.state != BoundaryState.LOCKED:
                    return True
                boundary.state = BoundaryState.AUTO
                return True
        return False

    def move_boundary(self, track_number: int, new_timestamp: float) -> bool:
        """Move a boundary to a new timestamp."""
        if self._current_session is None:
            return False
        for boundary in self._current_session.boundaries:
            if boundary.track_number == track_number:
                boundary.edited_boundary = new_timestamp
                boundary.detected_boundary = new_timestamp
                return True
        return False

    def get_all_boundaries_dto(self) -> list[ReviewBoundaryDTO]:
        """Get all boundaries as frozen DTOs."""
        if self._current_session is None:
            return []
        return [map_boundary_to_dto(b) for b in self._current_session.boundaries]

    def accept_all_boundaries(self) -> None:
        """Accept all boundaries as final."""
        if self._current_session is None:
            return
        for boundary in self._current_session.boundaries:
            if boundary.state != BoundaryState.LOCKED:
                boundary.state = BoundaryState.VERIFIED
