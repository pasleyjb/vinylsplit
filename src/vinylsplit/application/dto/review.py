"""Application Layer DTOs for review workflow.

These DTOs represent the public interface for the review workstation.
No internal domain models leak through these boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ReviewCandidateDTO:
    """A candidate boundary detected during analysis."""

    timestamp: float
    """Exact timestamp of the candidate boundary."""

    confidence: float
    """Confidence [0.0, 1.0] that this is a real boundary."""

    rank: int
    """Rank among all candidates for this boundary (0=best)."""

    reason: str
    """Why this candidate was detected."""

    @property
    def display_label(self) -> str:
        """Human-readable label showing rank and confidence."""
        rank_label = "SELECTED" if self.rank == 0 else f"Alt {self.rank}"
        return f"{rank_label} @ {self.timestamp:.2f}s ({self.confidence * 100:.0f}%)"


@dataclass(frozen=True, slots=True)
class ReviewConfidenceDTO:
    """Per-detector confidence contributions for a boundary."""

    silence_quality: float
    """Confidence from silence/RMS analysis [0.0, 1.0]."""

    metadata_agreement: float
    """Confidence from proximity to expected metadata boundary [0.0, 1.0]."""

    overall: float
    """Combined confidence [0.0, 1.0]."""

    @property
    def display_breakdown(self) -> str:
        """Human-readable breakdown of confidence sources."""
        parts = []
        if self.silence_quality > 0.0:
            parts.append(f"Silence {self.silence_quality * 100:.0f}%")
        if self.metadata_agreement > 0.0:
            parts.append(f"Metadata {self.metadata_agreement * 100:.0f}%")
        return " + ".join(parts) if parts else "Unknown"

    @property
    def confidence_emoji(self) -> str:
        """Visual indicator of confidence level."""
        if self.overall >= 0.8:
            return "✓✓"  # High confidence
        elif self.overall >= 0.6:
            return "✓"  # Medium confidence
        else:
            return "?"  # Low confidence


@dataclass(frozen=True, slots=True)
class ReviewDetectionEvidenceDTO:
    """Structured evidence from detection analysis."""

    method: str
    """Detection method (e.g., 'Metadata-guided silence', 'Audio-only')."""

    silence_duration: float | None = None
    """Duration of silence in seconds if applicable."""

    distance_from_expected: float | None = None
    """Distance from expected boundary in seconds if metadata was available."""

    @property
    def evidence_summary(self) -> str:
        """Human-readable summary of how boundary was detected."""
        parts = [self.method]
        if self.silence_duration is not None:
            parts.append(f"Silence: {self.silence_duration:.2f}s")
        if self.distance_from_expected is not None:
            parts.append(f"Distance: {self.distance_from_expected:.2f}s")
        return " • ".join(parts)


@dataclass(frozen=True, slots=True)
class ReviewBoundaryDTO:
    """Application-layer boundary for review workstation display.
    
    No internal domain model types leak through this interface.
    All data is read-only (frozen). GUI cannot accidentally modify boundaries.
    """

    track_number: int
    """Track number (1-based)."""

    selected_timestamp: float
    """The selected boundary timestamp (best candidate)."""

    title: str | None = None
    """Track title if available."""

    confidence: ReviewConfidenceDTO | None = None
    """Confidence breakdown from detection."""

    candidates: list[ReviewCandidateDTO] = field(default_factory=list)
    """All candidate boundaries, ranked by confidence."""

    evidence: ReviewDetectionEvidenceDTO | None = None
    """Detection evidence explaining how boundary was found."""

    notes: list[str] = field(default_factory=list)
    """Additional context notes."""

    is_locked: bool = False
    """Whether this boundary is locked from editing."""

    is_verified: bool = False
    """Whether user has verified this boundary."""

    @property
    def confidence_pct(self) -> int:
        """Confidence as percentage for UI display."""
        if self.confidence is None:
            return 0
        return round(self.confidence.overall * 100)

    @property
    def status_indicator(self) -> str:
        """Visual status of boundary confidence."""
        if self.is_locked:
            return "🔒"
        if self.is_verified:
            return "✓"
        if self.confidence is None or self.confidence.overall < 0.5:
            return "⚠"
        return "○"


@dataclass(slots=True)
class ReviewSessionDTO:
    """Application-layer review session for GUI binding.
    
    Contains only DTOs and read-only data, no domain model internals.
    Represents the complete state for the review workstation display.
    """

    source_file: str
    """Path to the source audio file."""

    boundaries: list[ReviewBoundaryDTO] = field(default_factory=list)
    """All boundaries in the session."""

    detected_track_count: int | None = None
    """Number of tracks detected by analysis."""

    expected_track_count: int | None = None
    """Number of tracks expected from metadata (if available)."""

    album_title: str | None = None
    """Album title from metadata if available."""

    artist_name: str | None = None
    """Artist name from metadata if available."""

    is_analyzing: bool = False
    """Whether backend is currently analyzing."""

    last_error: str | None = None
    """Last error message if any."""

    @property
    def boundary_count(self) -> int:
        """Total boundaries including start."""
        return len(self.boundaries)

    @property
    def verified_count(self) -> int:
        """Number of verified boundaries."""
        return sum(1 for b in self.boundaries if b.is_verified)

    @property
    def locked_count(self) -> int:
        """Number of locked boundaries."""
        return sum(1 for b in self.boundaries if b.is_locked)

    @property
    def avg_confidence(self) -> float:
        """Average confidence across all boundaries."""
        if not self.boundaries or not any(b.confidence for b in self.boundaries):
            return 0.0
        confidences = [b.confidence.overall for b in self.boundaries if b.confidence]
        return sum(confidences) / len(confidences) if confidences else 0.0
