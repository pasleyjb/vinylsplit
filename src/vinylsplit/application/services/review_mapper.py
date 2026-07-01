"""Mappers between domain models and Application Layer DTOs.

These mappers translate internal domain objects into read-only DTOs
for consumption by GUI and other client code.
"""

from __future__ import annotations

from vinylsplit.models import Boundary
from vinylsplit.review_candidate import ConfidenceBreakdown
from vinylsplit.boundary_states import BoundaryState
from vinylsplit.application.dto.review import (
    ReviewBoundaryDTO,
    ReviewCandidateDTO,
    ReviewConfidenceDTO,
    ReviewDetectionEvidenceDTO,
    ReviewSessionDTO,
)
from vinylsplit.review_state import AdaptiveReviewState


def map_boundary_to_dto(boundary: Boundary) -> ReviewBoundaryDTO:
    """Convert a domain Boundary to a ReviewBoundaryDTO for display.
    
    Maps internal fields to clean DTO representation.
    No domain model types leak through.
    """

    # Map confidence breakdown
    confidence_dto = None
    if boundary.confidence_breakdown:
        confidence_dto = ReviewConfidenceDTO(
            silence_quality=boundary.confidence_breakdown.silence_score,
            metadata_agreement=boundary.confidence_breakdown.distance_score,
            overall=boundary.confidence_breakdown.overall or boundary.detector_confidence or 0.0,
        )

    # Map candidate boundaries, ranked by confidence (descending)
    candidates_dto: list[ReviewCandidateDTO] = []
    if boundary.candidate_boundaries:
        sorted_candidates = sorted(
            boundary.candidate_boundaries,
            key=lambda c: c.confidence,
            reverse=True,
        )
        for rank, candidate in enumerate(sorted_candidates):
            candidates_dto.append(
                ReviewCandidateDTO(
                    timestamp=candidate.timestamp,
                    confidence=candidate.confidence,
                    rank=rank,
                    reason=candidate.reason,
                )
            )

    # Map detection evidence
    evidence_dto = None
    if boundary.detection_evidence:
        # Extract method and parse evidence
        method = "Audio analysis"
        silence_duration = None
        distance_from_expected = None

        for evidence_line in boundary.detection_evidence:
            if "Silence:" in evidence_line:
                try:
                    silence_duration = float(evidence_line.split(":")[1].strip().split("s")[0])
                except (ValueError, IndexError):
                    pass
            elif "Distance" in evidence_line:
                try:
                    distance_from_expected = float(evidence_line.split(":")[1].strip().split("s")[0])
                except (ValueError, IndexError):
                    pass
            elif "Metadata" in evidence_line:
                method = "Metadata-guided"

        evidence_dto = ReviewDetectionEvidenceDTO(
            method=method,
            silence_duration=silence_duration,
            distance_from_expected=distance_from_expected,
        )

    # Map state flags
    is_locked = boundary.state == BoundaryState.LOCKED
    is_verified = boundary.state == BoundaryState.VERIFIED

    return ReviewBoundaryDTO(
        track_number=boundary.track_number,
        selected_timestamp=boundary.detected_boundary or boundary.start_time,
        title=boundary.track_title,
        confidence=confidence_dto,
        candidates=candidates_dto,
        evidence=evidence_dto,
        notes=boundary.reasons or [],
        is_locked=is_locked,
        is_verified=is_verified,
    )


def map_session_to_dto(session: AdaptiveReviewState) -> ReviewSessionDTO:
    """Convert an AdaptiveReviewState to ReviewSessionDTO for GUI binding.
    
    Maps all boundaries and session metadata to DTOs.
    GUI receives only frozen DTOs, cannot modify domain state directly.
    """

    boundaries_dto = [map_boundary_to_dto(b) for b in session.boundaries]

    return ReviewSessionDTO(
        source_file=session.source_file,
        boundaries=boundaries_dto,
        detected_track_count=len(session.boundaries) - 1,  # Exclude start boundary
        album_title=getattr(session, "album_title", None),
        artist_name=getattr(session, "artist_name", None),
    )
