# VinylSplit Metadata Verifier Architecture

## Executive Summary

The **MetadataVerifier** is a new component that treats metadata discovery as an **evidence aggregation and conflict resolution system** rather than a simple lookup chain. Every metadata source (AcoustID, MusicBrainz, user input, embedded tags, file properties, future providers) is treated as **evidence** with a confidence score. The system automatically proceeds if all sources agree above a configurable threshold, and presents an interactive conflict report if evidence diverges.

---

## Design Principles

1. **Never blindly trust a single source.** Every source can be wrong.
2. **Evidence-based reasoning.** All sources contribute signals; none is authoritative by default.
3. **User authority preserved.** The user always has final say. VinylSplit may recommend, never dictate.
4. **Transparency.** The user can see why VinylSplit made a recommendation (which sources agreed/disagreed).
5. **Graceful degradation.** VinylSplit continues even if some sources fail; it works with partial evidence.
6. **Extensibility.** New metadata sources (Discogs, local cache, MusicBrainz release group hints, etc.) can be plugged in without rewriting core logic.
7. **Reproducibility.** All evidence and decisions are logged for audit/learning.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Pipeline (process)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MetadataVerifier                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ gather_evidence()                                        │  │
│  │  - Collects signals from all sources                     │  │
│  │  - Returns ReleaseEvidenceSet                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ verify_release()                                         │  │
│  │  - Analyzes evidence for conflicts                       │  │
│  │  - Scores confidence (0.0-1.0)                           │  │
│  │  - Returns VerificationReport                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ resolve_conflicts() [Interactive]                        │  │
│  │  - Presents conflict UI to user                          │  │
│  │  - Returns user's chosen release                         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Evidence Sources                           │
├─────────────────────────────────────────────────────────────────┤
│ • UserInputMetadataProvider (--artist, --album)                │
│ • EmbeddedMetadataProvider (FLAC tags)                          │
│ • AcoustIDMetadataProvider (fingerprint)                        │
│ • MusicBrainzProvider (release search)                          │
│ • AlbumResolverProvider (track consensus)                       │
│ • FilePropertiesProvider (track count, duration)                │
│ • Future: Discogs, cache, MusicBrainz release group, etc.      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Data Models

### 1. MetadataSource (Enum)

```
Represents the origin of a metadata claim:

ENUM MetadataSource:
  USER_INPUT
  EMBEDDED_TAGS
  ACOUSTID
  MUSICBRAINZ
  ALBUM_RESOLVER
  FILE_PROPERTIES
  DISCOGS                       # Future
  LOCAL_CACHE                   # Future
  MUSICBRAINZ_RELEASE_GROUP     # Future
```

---

### 2. MetadataEvidence (Dataclass)

Represents a single claim from a source:

```python
@dataclass
class MetadataEvidence:
    """A single piece of metadata from one source."""

    source: MetadataSource
    release_id: str | None              # MusicBrainz UUID or None
    artist: str | None
    album_title: str | None
    year: str | None                    # YYYY or "---" if unknown
    track_count: int | None
    tracklist: list[str] | None         # Official titles if available

    # Confidence score (0.0 = complete guess, 1.0 = certain)
    confidence: float                   # Default varies by source

    # Reasoning (why this source exists, any caveats)
    reasoning: str                      # e.g., "Fingerprint matched with high score"

    # Timestamp for audit
    timestamp: float                    # time.monotonic() or datetime

    # Optional: source-specific metadata
    extra: dict[str, Any]               # e.g., {"acoustid_score": 0.95, "fingerprint_duration": 234}
```

---

### 3. ReleaseEvidenceSet (Dataclass)

Collects all evidence for a single release:

```python
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
    artist_agreement: float              # Fraction of sources that agree on artist
    album_title_agreement: float
    year_agreement: float
    track_count_agreement: float

    # Metadata from best-scoring source for each field
    best_tracklist: list[str]            # Official track titles
    best_tracklist_source: MetadataSource
```

---

### 4. VerificationReport (Dataclass)

Result of the verification step:

```python
@dataclass
class VerificationReport:
    """Report on metadata verification for a track or album."""

    # The verified release (if agreed upon)
    release: ReleaseEvidenceSet | None

    # Whether to proceed automatically (if consensus is strong)
    auto_proceed: bool                   # True if confidence > threshold

    # Threshold used to make the decision
    confidence_threshold: float          # Configurable, default 0.80

    # Any conflicts detected
    conflicts: list[MetadataConflict]

    # Recommendation to the user
    recommendation: str                  # e.g., "All sources agree on this release (95% confidence)."
    recommendation_severity: Literal["clean", "warning", "conflict"]
    # - "clean": All sources agree, proceed
    # - "warning": Most sources agree but some diverge; proceed with caution
    # - "conflict": Sources strongly disagree; user must choose

    # For auditing
    created_at: float
    all_releases_considered: list[ReleaseEvidenceSet]  # All candidates, ranked by confidence
```

---

### 5. MetadataConflict (Dataclass)

Documents a specific conflict:

```python
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
    explanations: list[str]
    # Examples:
    #   - "AcoustID may have returned a live version"
    #   - "Embedded FLAC tag is outdated"
    #   - "User provided partial information"

    # Severity (how much this affects usability)
    severity: Literal["low", "medium", "high"]
    # - "low": Nice-to-have (e.g., year differs by 1-2 years)
    # - "medium": Important (e.g., artist name differs due to encoding/accent)
    # - "high": Critical (e.g., album title completely different)
```

---

### 6. MetadataSourceProvider (Abstract Base)

Interface that all metadata sources implement:

```python
class MetadataSourceProvider(ABC):
    """Abstract base for any metadata source."""

    @property
    def source_type(self) -> MetadataSource:
        """Return the source type identifier."""
        pass

    @property
    def default_confidence(self) -> float:
        """Default confidence for this source (0.0-1.0)."""
        # Examples:
        #   USER_INPUT:        0.70 (user may make typos)
        #   EMBEDDED_TAGS:     0.65 (may be old/incorrect)
        #   ACOUSTID:          0.85 (fingerprint is strong, but can fail)
        #   MUSICBRAINZ:       0.90 (DB is vetted; single-source lookup is okay)
        #   ALBUM_RESOLVER:    0.80 (consensus of multiple fingerprints)
        #   FILE_PROPERTIES:   0.95 (file track count is certain)
        pass

    @abstractmethod
    async def gather(self, track: SplitTrack, context: MetadataContext) -> MetadataEvidence | None:
        """Gather evidence from this source.

        Args:
            track: The track being analyzed
            context: Context (e.g., user-provided hints, file properties)

        Returns:
            MetadataEvidence if the source produces a claim, else None if unavailable/failed.
        """
        pass

    @property
    def is_required(self) -> bool:
        """If True, a failure to gather evidence is a pipeline error."""
        # Only FILE_PROPERTIES is required; others are optional.
        pass
```

---

### 7. MetadataContext (Dataclass)

Contextual information passed to providers:

```python
@dataclass
class MetadataContext:
    """Context shared during evidence gathering."""

    # Source recording file
    source_file: str
    split_track: SplitTrack

    # User-provided hints
    user_artist: str | None
    user_album: str | None

    # Already-gathered evidence (for cross-reference)
    previous_evidence: list[MetadataEvidence]

    # Configuration
    config: MetadataVerifierConfig
```

---

### 8. MetadataVerifierConfig (Dataclass)

Configuration for the verifier:

```python
@dataclass
class MetadataVerifierConfig:
    """Configuration for metadata verification behavior."""

    # Thresholds
    auto_proceed_threshold: float = 0.80          # If confidence >= this, proceed automatically
    conflict_warning_threshold: float = 0.60      # If confidence < this, show warnings
    agreement_threshold: float = 0.70             # Fraction of sources that must agree

    # Behavior
    require_user_confirmation: bool = False       # If True, always show report even if confident
    interactive_mode: bool = True                 # If True, show conflict UI; else use best-guess
    log_all_evidence: bool = True                 # If True, write detailed logs

    # Timeout for slow sources
    gather_timeout: float = 30.0                  # Seconds per source

    # Future: cache location, database paths, etc.
    cache_dir: str | None = None
    discogs_api_key: str | None = None
```

---

## Confidence Scoring Model

### Overall Confidence Formula

```
overall_confidence = weighted_average(
    source_confidences,
    weights = source_weights
)

where:
  source_confidences[i] = evidence[i].confidence
  source_weights[i] = 1.0 / (1.0 + distance(evidence[i].value, majority_value))
                      * agreement_bonus[i]

agreement_bonus[i] = 1.0 + (fraction_of_sources_agreeing - 0.5) * 0.2
                     (ranges 0.8 to 1.2; rewards majority agreement)
```

### Field-Level Agreement

For each field (artist, album_title, year, track_count):

```
agreement = (count_of_sources_claiming_X) / (count_of_non_null_sources)
```

If `agreement >= agreement_threshold`, the field is considered "agreed upon."

---

## The MetadataVerifier Class

### Public API

```python
class MetadataVerifier:
    """Aggregates metadata evidence and guides conflict resolution."""

    def __init__(self, config: MetadataVerifierConfig | None = None):
        """Initialize with optional custom config."""
        self.config = config or MetadataVerifierConfig()
        self._providers: list[MetadataSourceProvider] = []
        self._logger = Logger()  # Audit trail

    def register_provider(self, provider: MetadataSourceProvider) -> None:
        """Register a metadata source provider."""
        self._providers.append(provider)

    async def gather_evidence(
        self,
        split_track: SplitTrack,
        source_file: str,
        user_artist: str | None = None,
        user_album: str | None = None,
    ) -> ReleaseEvidenceSet | None:
        """Gather evidence from all registered providers.

        Returns the best-matching release with confidence scores,
        or None if evidence is too weak/conflicting to propose a release.
        """
        context = MetadataContext(
            source_file=source_file,
            split_track=split_track,
            user_artist=user_artist,
            user_album=user_album,
            previous_evidence=[],
            config=self.config,
        )

        # Gather evidence in parallel from all providers
        evidence_list = await self._gather_all(context)

        # Group evidence by release_id and compute ReleaseEvidenceSet
        release_evidence_set = self._aggregate_evidence(evidence_list, context)

        return release_evidence_set

    async def verify_release(
        self,
        release_evidence: ReleaseEvidenceSet,
    ) -> VerificationReport:
        """Analyze evidence for conflicts and produce a verification report.

        Does NOT interact with the user; purely analytical.
        """
        # Compute agreement scores
        conflicts = self._detect_conflicts(release_evidence)

        # Score confidence
        overall_confidence = self._score_confidence(release_evidence)

        # Decide: auto-proceed?
        auto_proceed = (
            overall_confidence >= self.config.auto_proceed_threshold
            and len(conflicts) == 0
        )

        # Build recommendation
        recommendation, severity = self._build_recommendation(
            overall_confidence, conflicts, auto_proceed
        )

        report = VerificationReport(
            release=release_evidence,
            auto_proceed=auto_proceed,
            confidence_threshold=self.config.auto_proceed_threshold,
            conflicts=conflicts,
            recommendation=recommendation,
            recommendation_severity=severity,
            created_at=time.monotonic(),
            all_releases_considered=[release_evidence],  # Future: rank alternatives
        )

        return report

    async def resolve_conflicts_interactive(
        self,
        report: VerificationReport,
    ) -> ReleaseEvidenceSet:
        """Present conflicts to user and return their choice.

        If report.auto_proceed is True, may skip UI (unless required).
        """
        if report.auto_proceed and not self.config.require_user_confirmation:
            return report.release

        # Present conflict UI (using Rich dashboard)
        chosen_release = await self._show_conflict_ui(report)

        return chosen_release

    async def process_track(
        self,
        split_track: SplitTrack,
        source_file: str,
        user_artist: str | None = None,
        user_album: str | None = None,
    ) -> tuple[ReleaseEvidenceSet | None, VerificationReport]:
        """High-level workflow: gather → verify → resolve.

        Returns (selected_release, report).
        """
        # Step 1: Gather
        evidence = await self.gather_evidence(
            split_track, source_file, user_artist, user_album
        )

        if evidence is None:
            return None, VerificationReport(
                release=None,
                auto_proceed=False,
                conflicts=[],
                recommendation="No metadata evidence found.",
                recommendation_severity="conflict",
                created_at=time.monotonic(),
                all_releases_considered=[],
            )

        # Step 2: Verify
        report = await self.verify_release(evidence)

        # Step 3: Resolve conflicts (interactive if needed)
        if self.config.interactive_mode and report.conflicts:
            chosen = await self.resolve_conflicts_interactive(report)
        else:
            chosen = report.release

        return chosen, report
```

---

## Verification Report Display (Interactive UI)

When conflicts exist and `interactive_mode=True`, the verifier presents:

```
┌────────────────────────────────────────────────────────────────┐
│           Metadata Conflict Resolution                         │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Track: 01 - Some Song (2:34)                                 │
│                                                                │
│  Overall Confidence: 67% ⚠ (sources do not fully agree)      │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ FIELD: Artist                                          │   │
│  ├────────────────────────────────────────────────────────┤   │
│  │ Agreement: 60% (3/5 sources)                           │   │
│  │                                                        │   │
│  │ [✓] The Beatles     ← MusicBrainz, AcoustID, Tags     │   │
│  │ [ ] The Beatles' 1  ← Embedded FLAC tag (old)         │   │
│  │ [ ] Beatles, The    ← File sort name                  │   │
│  │                                                        │   │
│  │ Explanation:                                           │   │
│  │ • Embedded tag is outdated (Audacity 2018)            │   │
│  │ • File sort name is alternative format                │   │
│  │ • Recommend: The Beatles (standard format)            │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                │
│  ┌────────────────────────────────────────────────────────┐   │
│  │ FIELD: Album Title                                     │   │
│  ├────────────────────────────────────────────────────────┤   │
│  │ Agreement: 100% (all sources)                          │   │
│  │ Value: Sgt. Pepper's Lonely Hearts Club Band          │   │
│  │ Status: ✓ Agreed                                       │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                │
│  [Select Artist]  [Confirm All]  [Manual Edit]  [Skip Track] │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagram

### Workflow: process_track()

```
User calls: process_track(split_track, source_file, user_artist, user_album)
│
├─ gather_evidence()
│  ├─ Create MetadataContext with user hints
│  ├─ For each provider in parallel:
│  │  └─ provider.gather(track, context) → MetadataEvidence | None
│  ├─ Collect all evidence → evidence_list
│  └─ Aggregate by release_id → ReleaseEvidenceSet (with scores)
│
├─ verify_release(evidence_set)
│  ├─ Detect conflicts in evidence
│  ├─ Score overall confidence
│  ├─ Build recommendation string
│  └─ Return VerificationReport
│
└─ resolve_conflicts_interactive(report) [if needed]
   ├─ If auto_proceed and no conflicts → return report.release
   ├─ Else show UI with evidence table
   ├─ User selects preferred values
   └─ Return updated ReleaseEvidenceSet
```

---

## Pipeline Integration

The `Pipeline.process()` method will be updated:

```python
async def process(
    self,
    filename: str,
    output_directory: str,
    artist: str | None = None,
    album: str | None = None,
    interactive_metadata: bool = True,
) -> list[tuple[SplitTrack, ReleaseEvidenceSet]]:
    """Main processing pipeline, now using MetadataVerifier."""

    # ... Split audio, detect tracks ...

    # For each split track:
    for track in split_tracks:
        # Use the verifier instead of SmartIdentifier
        release_evidence, report = await verifier.process_track(
            track,
            source_file=filename,
            user_artist=artist,
            user_album=album,
        )

        if release_evidence:
            results.append((track, release_evidence))
        else:
            failed.append(track)

    # ... Continue with consensus, artwork, etc. ...
```

---

## Metadata Sources

### Built-in Providers

1. **UserInputMetadataProvider**
   - Confidence: 0.70 (user can make typos, but high intent signal)
   - Searches MusicBrainz using `--artist` and `--album` hints

2. **EmbeddedMetadataProvider**
   - Confidence: 0.65 (may be outdated, may be manually added)
   - Reads FLAC Vorbis comments (artist, album, date, etc.)

3. **AcoustIDMetadataProvider**
   - Confidence: 0.85 (fingerprint is strong signal, but can fail on noisy vinyl)
   - Uses existing `AcoustIDService.lookup()`

4. **MusicBrainzProvider**
   - Confidence: 0.90 (official DB, but may lack obscure releases)
   - Uses existing `MusicBrainzService.lookup_release()`

5. **AlbumResolverProvider**
   - Confidence: 0.80 (consensus of multiple track IDs)
   - Uses `AlbumResolver.resolve()` on best matches

6. **FilePropertiesProvider**
   - Confidence: 0.95 (track count and duration are certain from file)
   - Extracts track count and average duration from file

### Future Providers (Extensible)

- **DiscogsProvider** (confidence 0.75) — For vinyl-specific metadata
- **LocalCacheProvider** (confidence 0.80) — Remember user choices
- **MusicBrainzReleaseGroupProvider** (confidence 0.70) — For grouping variants
- **Shazam/SoundHound Provider** (confidence 0.75) — Commercial metadata
- **Genre/Year Hints Provider** (confidence 0.60) — From audio analysis

---

## Conflict Detection Logic

A conflict is detected when:

1. **Multiple sources claim different values** for the same field, AND
2. **Agreement is below the threshold** (e.g., 70%)
3. **The difference is material** (e.g., "Beatles" vs "Beatles'" is minor; "Beatles" vs "Rolling Stones" is major)

Conflict **severity** is assigned based on:

- **Low**: Cosmetic differences (artist name encoding, year off by 1-2, title punctuation)
- **Medium**: Informational (different remaster year, remix note in title)
- **High**: Critical (wrong artist, wrong album, wrong release)

---

## Confidence Scoring

For each field, VinylSplit scores:

- **Source confidence**: How sure is this provider? (0.0–1.0)
- **Agreement bonus**: Do other sources agree? (+0.2 if majority agrees)
- **Distance penalty**: How far from the majority? (-proportional)

**Overall confidence** is the weighted average across all fields.

---

## User Authority

- The user can **override any field** in the interactive UI.
- User selections are **logged with reasoning**.
- User can optionally **save selections** to a local cache (for future similar recordings).
- VinylSplit **never** silently ignores the user's choice.

---

## Logging & Audit Trail

Every verification includes:

```
[timestamp] track=01-song_title source_file=input.flac
  sources_gathered: [AcoustID, MusicBrainz, EmbeddedTags, ...]
  conflicts_detected: 1 (artist name variant)
  overall_confidence: 0.87
  auto_proceed: true
  user_confirmed: [explicit timestamp if interactive]
  final_release_id: 12345abc-...
```

This enables **learning** (which sources are most reliable) and **debugging** (why did this release get chosen).

---

## Implementation Phases

### Phase 1: Foundation
- Define all dataclasses
- Implement MetadataSourceProvider base class
- Implement MetadataVerifier core methods (gather, verify, score)

### Phase 2: Built-in Providers
- Implement 6 core providers (User, Embedded, AcoustID, MusicBrainz, AlbumResolver, FileProperties)
- Integrate with existing services

### Phase 3: Conflict Resolution UI
- Build interactive report display (Rich Panels/Tables)
- Implement user selection flow
- Add logging & audit trail

### Phase 4: Pipeline Integration
- Refactor `Pipeline.process()` to use MetadataVerifier
- Remove/deprecate SmartIdentifier (replace with verifier)
- Add CLI flag `--interactive-metadata` (default: True)

### Phase 5: Extensibility & Polish
- Document provider interface
- Add cache support
- Prepare for future providers (Discogs, etc.)
- Performance optimization

---

## Future Enhancements

1. **Machine Learning**: Train a model on user choices to predict preferred resolution.
2. **Collaborative Confidence**: Crowdsource confidence scores from VinylSplit users.
3. **Discogs Integration**: Add vinyl-specific metadata source.
4. **Local Cache**: Remember user selections per artist/album hash.
5. **Fuzzy Matching**: Better detect "same" values despite encoding/accents.
6. **Batch Operations**: Apply learned metadata choices to similar recordings.
7. **Metadata Export**: Export verified metadata to external formats (JSON, MusicBrainz, Discogs).

---

## Conclusion

The **MetadataVerifier** transforms VinylSplit from a "single source, best guess" tool into a **verifiable, auditable, user-centric metadata engine**. By treating metadata as evidence and preserving user authority, VinylSplit becomes suitable for **archival workflows** where metadata integrity is critical.

The architecture is **modular, extensible, and future-proof**, allowing new sources and strategies to be integrated without disrupting core logic.
