"""Core metadata verification engine."""

import asyncio
import time
from collections import Counter

from vinylsplit.metadata_verifier.models import (
    MetadataContext,
    MetadataConflict,
    MetadataEvidence,
    MetadataSource,
    MetadataSourceProvider,
    MetadataVerifierConfig,
    ReleaseEvidenceSet,
    VerificationReport,
)


class MetadataVerifier:
    """Aggregates metadata evidence and guides conflict resolution."""

    def __init__(self, config: MetadataVerifierConfig | None = None) -> None:
        """Initialize with optional custom config."""
        self.config = config or MetadataVerifierConfig()
        self._providers: list[MetadataSourceProvider] = []

    def register_provider(self, provider: MetadataSourceProvider) -> None:
        """Register a metadata source provider."""
        self._providers.append(provider)

    async def gather_evidence(
        self,
        context: MetadataContext,
    ) -> ReleaseEvidenceSet | None:
        """Gather evidence from all registered providers.

        Returns the best-matching release with confidence scores,
        or None if evidence is too weak/conflicting to propose a release.
        """
        # Gather evidence in parallel from all providers
        tasks = [asyncio.create_task(self._gather_from_provider(p, context)) for p in self._providers]

        evidence_list: list[MetadataEvidence] = []
        for result in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(result, MetadataEvidence):
                evidence_list.append(result)
            elif isinstance(result, Exception):
                # Log but don't crash on individual provider failures
                print(f"Provider error: {result}")

        if not evidence_list:
            return None

        # Group evidence by release_id and compute ReleaseEvidenceSet
        release_evidence_set = self._aggregate_evidence(evidence_list)

        return release_evidence_set

    async def _gather_from_provider(
        self,
        provider: MetadataSourceProvider,
        context: MetadataContext,
    ) -> MetadataEvidence | None:
        """Gather evidence from a single provider with timeout."""
        try:
            return await asyncio.wait_for(
                provider.gather(context),
                timeout=self.config.gather_timeout,
            )
        except asyncio.TimeoutError:
            print(f"{provider.source_type.value}: timeout")
            return None
        except Exception as exc:
            print(f"{provider.source_type.value}: {exc}")
            return None

    def _aggregate_evidence(
        self,
        evidence_list: list[MetadataEvidence],
    ) -> ReleaseEvidenceSet | None:
        """Group evidence by release and compute aggregate scores."""
        if not evidence_list:
            return None

        # Group by release_id (None is also a valid key for unmapped releases)
        releases_by_id: dict[str | None, list[MetadataEvidence]] = {}
        for evidence in evidence_list:
            rid = evidence.release_id
            if rid not in releases_by_id:
                releases_by_id[rid] = []
            releases_by_id[rid].append(evidence)

        # Pick the release with the most evidence as canonical
        best_release_id = max(releases_by_id.keys(), key=lambda r: len(releases_by_id[r]))
        best_evidence_list = releases_by_id[best_release_id]

        # Compute consensus and agreement scores
        return self._score_release_evidence(best_release_id, best_evidence_list)

    def _score_release_evidence(
        self,
        release_id: str | None,
        evidence_list: list[MetadataEvidence],
    ) -> ReleaseEvidenceSet:
        """Score a single release's evidence set."""
        # Compute consensus for each field via majority vote
        artists = [e.artist for e in evidence_list if e.artist]
        albums = [e.album_title for e in evidence_list if e.album_title]
        years = [e.year for e in evidence_list if e.year]
        track_counts = [e.track_count for e in evidence_list if e.track_count is not None]

        consensus_artist = self._majority_vote(artists) or "Unknown Artist"
        consensus_album_title = self._majority_vote(albums) or "Unknown Album"
        consensus_year = self._majority_vote(years) or "----"
        consensus_track_count = self._majority_vote(track_counts) if track_counts else None

        # Compute agreement scores (fraction of sources that agree)
        artist_agreement = len([e for e in evidence_list if e.artist == consensus_artist]) / len(
            [e for e in evidence_list if e.artist]
        )
        album_agreement = len([e for e in evidence_list if e.album_title == consensus_album_title]) / len(
            [e for e in evidence_list if e.album_title]
        )
        year_agreement = len([e for e in evidence_list if e.year == consensus_year]) / len(
            [e for e in evidence_list if e.year]
        )
        track_count_agreement = (
            len([e for e in evidence_list if e.track_count == consensus_track_count])
            / len(track_counts)
            if track_counts
            else 1.0
        )

        # Compute overall confidence as weighted average
        confidences = [e.confidence for e in evidence_list]
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.5

        # Find best tracklist
        best_tracklist: list[str] = []
        best_source: MetadataSource | None = None
        for e in evidence_list:
            if e.tracklist:
                best_tracklist = e.tracklist
                best_source = e.source
                break

        return ReleaseEvidenceSet(
            canonical_release_id=release_id,
            evidence_list=evidence_list,
            consensus_artist=consensus_artist,
            consensus_album_title=consensus_album_title,
            consensus_year=consensus_year,
            consensus_track_count=consensus_track_count,
            overall_confidence=overall_confidence,
            artist_agreement=artist_agreement,
            album_title_agreement=album_agreement,
            year_agreement=year_agreement,
            track_count_agreement=track_count_agreement,
            best_tracklist=best_tracklist,
            best_tracklist_source=best_source,
        )

    @staticmethod
    def _majority_vote(values: list) -> str | int | None:
        """Return the most common value in a list."""
        if not values:
            return None
        counts = Counter(values)
        return counts.most_common(1)[0][0]

    async def verify_release(
        self,
        release_evidence: ReleaseEvidenceSet,
    ) -> VerificationReport:
        """Analyze evidence for conflicts and produce a verification report."""
        # Detect conflicts
        conflicts = self._detect_conflicts(release_evidence)

        # Decide: auto-proceed?
        auto_proceed = (
            release_evidence.overall_confidence >= self.config.auto_proceed_threshold
            and len(conflicts) == 0
        )

        # Build recommendation
        recommendation, severity = self._build_recommendation(
            release_evidence.overall_confidence, conflicts, auto_proceed
        )

        report = VerificationReport(
            release=release_evidence,
            auto_proceed=auto_proceed,
            confidence_threshold=self.config.auto_proceed_threshold,
            conflicts=conflicts,
            recommendation=recommendation,
            recommendation_severity=severity,
            created_at=time.monotonic(),
            all_releases_considered=[release_evidence],
        )

        return report

    def _detect_conflicts(self, release_evidence: ReleaseEvidenceSet) -> list[MetadataConflict]:
        """Detect conflicts in evidence."""
        conflicts: list[MetadataConflict] = []

        # Check each field for disagreement
        for field in ["artist", "album_title", "year", "track_count"]:
            conflict = self._check_field_conflict(release_evidence, field)  # type: ignore
            if conflict:
                conflicts.append(conflict)

        return conflicts

    def _check_field_conflict(
        self,
        release_evidence: ReleaseEvidenceSet,
        field: str,
    ) -> MetadataConflict | None:
        """Check if a single field has conflicting evidence."""
        # Collect claims from each source
        claims: dict[MetadataSource, str | int | None] = {}
        for evidence in release_evidence.evidence_list:
            value = getattr(evidence, field, None)
            if value is not None:
                claims[evidence.source] = value

        if not claims:
            return None

        # Check if all claims agree
        unique_values = set(str(v) for v in claims.values())
        if len(unique_values) <= 1:
            return None  # No conflict, all agree

        # Compute majority
        value_counts = Counter(claims.values())
        majority_claim, majority_count = value_counts.most_common(1)[0]

        # Check agreement threshold
        agreement = majority_count / len(claims)
        if agreement >= self.config.agreement_threshold:
            return None  # Above threshold, not a conflict

        # Build conflict object
        return MetadataConflict(
            field=field,  # type: ignore
            claims=claims,
            majority_claim=majority_claim,
            majority_count=majority_count,
            explanations=[
                f"Field '{field}' has {len(unique_values)} different values from {len(claims)} sources.",
            ],
            severity=self._assess_conflict_severity(field, list(unique_values)),
        )

    @staticmethod
    def _assess_conflict_severity(field: str, values: list[str]) -> str:
        """Assess conflict severity."""
        # Simple heuristic: if values are very different, it's high severity
        if field == "release_id":
            return "high"
        if field == "artist" or field == "album_title":
            # If values are short and very different, likely high
            if all(len(v) < 5 for v in values):
                return "high"
            return "medium"
        return "low"

    @staticmethod
    def _build_recommendation(
        confidence: float,
        conflicts: list[MetadataConflict],
        auto_proceed: bool,
    ) -> tuple[str, str]:
        """Build a recommendation string and severity."""
        if auto_proceed:
            return (
                f"All sources agree on this release ({confidence:.0%} confidence). Proceeding automatically.",
                "clean",
            )

        if conflicts:
            high_conflicts = [c for c in conflicts if c.severity == "high"]
            if high_conflicts:
                return (
                    f"Critical conflicts detected ({confidence:.0%} confidence). Please review.",
                    "conflict",
                )
            else:
                return (
                    f"Minor conflicts detected ({confidence:.0%} confidence). Sources mostly agree.",
                    "warning",
                )

        return (
            f"Confidence: {confidence:.0%}. Ready to proceed.",
            "clean",
        )

    async def process_track(
        self,
        context: MetadataContext,
    ) -> tuple[ReleaseEvidenceSet | None, VerificationReport]:
        """High-level workflow: gather → verify → resolve.

        Returns (selected_release, report).
        """
        # Step 1: Gather
        evidence = await self.gather_evidence(context)

        if evidence is None:
            return None, VerificationReport(
                release=None,
                auto_proceed=False,
                confidence_threshold=self.config.auto_proceed_threshold,
                conflicts=[],
                recommendation="No metadata evidence found.",
                recommendation_severity="conflict",
                created_at=time.monotonic(),
                all_releases_considered=[],
            )

        # Step 2: Verify
        report = await self.verify_release(evidence)

        return evidence, report
