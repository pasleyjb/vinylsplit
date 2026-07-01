"""Metadata verification models and provider interface.

This module defines the data structures and abstract interface for metadata
evidence gathering and verification.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class MetadataSource(Enum):
    """Origin of a metadata claim."""

    USER_INPUT = "user_input"
    EMBEDDED_TAGS = "embedded_tags"
    ACOUSTID = "acoustid"
    MUSICBRAINZ = "musicbrainz"
    ALBUM_RESOLVER = "album_resolver"
    FILE_PROPERTIES = "file_properties"
    DISCOGS = "discogs"  # Future
    LOCAL_CACHE = "local_cache"  # Future
    MUSICBRAINZ_RELEASE_GROUP = "musicbrainz_release_group"  # Future


@dataclass
class MetadataEvidence:
    """A single piece of metadata from one source."""

    source: MetadataSource
    release_id: str | None
    artist: str | None
    album_title: str | None
    year: str | None
    track_count: int | None
    tracklist: list[str] | None

    # Confidence score (0.0 = complete guess, 1.0 = certain)
    confidence: float

    # Reasoning (why this source exists, any caveats)
    reasoning: str

    # Timestamp for audit
    timestamp: float

    # Optional: source-specific metadata
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate confidence is in range."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")


@dataclass
class ReleaseEvidenceSet:
    """All evidence gathered about a potential release."""

    # Primary identifier
    canonical_release_id: str | None

    # All evidence about this release from all sources
    evidence_list: list[MetadataEvidence]

    # Aggregated/voted values (majority vote or weighted average)
    consensus_artist: str
    consensus_album_title: str
    consensus_year: str
    consensus_track_count: int | None

    # Confidence that this release is correct (0.0-1.0)
    overall_confidence: float

    # Individual agreement scores (how well sources agree)
    artist_agreement: float
    album_title_agreement: float
    year_agreement: float
    track_count_agreement: float

    # Metadata from best-scoring source for each field
    best_tracklist: list[str] = field(default_factory=list)
    best_tracklist_source: MetadataSource | None = None


@dataclass
class MetadataConflict:
    """A disagreement between metadata sources."""

    field: Literal["artist", "album_title", "year", "track_count", "release_id"]

    # What each source claims
    claims: dict[MetadataSource, str | int | None]

    # Which claim has the most support
    majority_claim: str | int | None
    majority_count: int

    # Possible explanations (for display)
    explanations: list[str] = field(default_factory=list)

    # Severity (how much this affects usability)
    severity: Literal["low", "medium", "high"] = "low"


@dataclass
class VerificationReport:
    """Report on metadata verification for a track or album."""

    # The verified release (if agreed upon)
    release: ReleaseEvidenceSet | None

    # Whether to proceed automatically (if consensus is strong)
    auto_proceed: bool

    # Threshold used to make the decision
    confidence_threshold: float

    # Any conflicts detected
    conflicts: list[MetadataConflict] = field(default_factory=list)

    # Recommendation to the user
    recommendation: str = ""
    recommendation_severity: Literal["clean", "warning", "conflict"] = "clean"

    # For auditing
    created_at: float = 0.0
    all_releases_considered: list[ReleaseEvidenceSet] = field(default_factory=list)


@dataclass
class MetadataContext:
    """Context shared during evidence gathering."""

    # Source recording file
    source_file: str
    split_track: "SplitTrack"  # noqa: F821

    # User-provided hints
    user_artist: str | None
    user_album: str | None

    # Already-gathered evidence (for cross-reference)
    previous_evidence: list[MetadataEvidence]

    # Configuration
    config: "MetadataVerifierConfig"  # noqa: F821


@dataclass
class MetadataVerifierConfig:
    """Configuration for metadata verification behavior."""

    # Thresholds
    auto_proceed_threshold: float = 0.80
    conflict_warning_threshold: float = 0.60
    agreement_threshold: float = 0.70

    # Behavior
    require_user_confirmation: bool = False
    interactive_mode: bool = True
    log_all_evidence: bool = True

    # Timeout for slow sources (seconds)
    gather_timeout: float = 30.0

    # Optional: cache location, database paths, etc.
    cache_dir: str | None = None
    discogs_api_key: str | None = None

    def __post_init__(self) -> None:
        """Validate thresholds."""
        for name in ["auto_proceed_threshold", "conflict_warning_threshold", "agreement_threshold"]:
            val = getattr(self, name)
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"{name} must be 0.0-1.0, got {val}")


class MetadataSourceProvider(ABC):
    """Abstract base for any metadata source provider."""

    @property
    @abstractmethod
    def source_type(self) -> MetadataSource:
        """Return the source type identifier."""
        pass

    @property
    @abstractmethod
    def default_confidence(self) -> float:
        """Default confidence for this source (0.0-1.0)."""
        pass

    @abstractmethod
    async def gather(
        self,
        context: MetadataContext,
    ) -> MetadataEvidence | None:
        """Gather evidence from this source.

        Args:
            context: Context (e.g., user-provided hints, file properties)

        Returns:
            MetadataEvidence if the source produces a claim, else None if unavailable/failed.
        """
        pass

    @property
    def is_required(self) -> bool:
        """If True, a failure to gather evidence is a pipeline error."""
        return False
