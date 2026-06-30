from __future__ import annotations

import numpy as np

from vinylsplit.analysis.rms import RMSAnalysis
from vinylsplit.analysis.silence import SilenceDetector
from vinylsplit.optimization.diagnostics import (
    BoundaryCandidate,
    CandidateDiscoveryDiagnostics,
    CandidateGenerationResult,
    OptimizationRegion,
)
from vinylsplit.optimization.rms_detector import RMSValleyDetector


class CandidateGenerator:
    """Generate per-boundary candidate sets from multiple evidence signals."""

    def __init__(
        self,
        silence_detector: SilenceDetector,
        rms_detector: RMSValleyDetector,
        search_window_seconds: float = 15.0,
        sample_step_seconds: float = 0.5,
    ) -> None:
        self._silence_detector = silence_detector
        self._rms_detector = rms_detector
        self._search_window_seconds = search_window_seconds
        self._sample_step_seconds = max(0.05, sample_step_seconds)

    def generate_region_candidates(
        self,
        region: OptimizationRegion,
        rms: RMSAnalysis,
        original_expected_boundaries: list[float] | None = None,
        drift_applied_seconds: float = 0.0,
    ) -> CandidateGenerationResult:
        """Build candidate lists keyed by boundary index for one region."""
        _, silence_regions = self._silence_detector.detect(rms)

        out: dict[int, list[BoundaryCandidate]] = {}
        discovery: dict[int, CandidateDiscoveryDiagnostics] = {}

        rms_valley_timestamps = self.rms_valley_timestamps(rms)

        expected_pairs = zip(region.boundary_indices, region.expected_boundaries)
        for idx, (boundary_index, expected_time) in enumerate(expected_pairs):
            original_expected = (
                original_expected_boundaries[idx]
                if original_expected_boundaries is not None and idx < len(original_expected_boundaries)
                else expected_time
            )

            original_window_start = max(region.start_time, original_expected - self._search_window_seconds)
            original_window_end = min(region.end_time, original_expected + self._search_window_seconds)
            window_start = max(region.start_time, expected_time - self._search_window_seconds)
            window_end = min(region.end_time, expected_time + self._search_window_seconds)

            candidates, meta = self._candidates_for_expected(
                track_number=boundary_index + 1,
                expected_time=expected_time,
                original_expected_time=original_expected,
                drift_applied_seconds=drift_applied_seconds,
                original_window_start=original_window_start,
                original_window_end=original_window_end,
                window_start=window_start,
                window_end=window_end,
                rms=rms,
                silence_regions=silence_regions,
                rms_valley_timestamps=rms_valley_timestamps,
            )
            out[boundary_index] = candidates
            discovery[boundary_index] = meta

        return CandidateGenerationResult(
            candidates_by_boundary=out,
            discovery_by_boundary=discovery,
        )

    def _candidates_for_expected(
        self,
        track_number: int,
        expected_time: float,
        original_expected_time: float,
        drift_applied_seconds: float,
        original_window_start: float,
        original_window_end: float,
        window_start: float,
        window_end: float,
        rms: RMSAnalysis,
        silence_regions: list,
        rms_valley_timestamps: list[float],
    ) -> tuple[list[BoundaryCandidate], CandidateDiscoveryDiagnostics]:
        timestamps: set[float] = {round(float(expected_time), 3)}
        silence_candidates = 0

        for region in silence_regions:
            center = float(region.center_window * rms.window_seconds)
            if window_start <= center <= window_end:
                silence_candidates += 1
                timestamps.add(round(center, 3))

        valley_candidates = sum(
            1 for ts in rms_valley_timestamps
            if window_start <= ts <= window_end
        )

        nearby_source_timestamps = {
            round(float(expected_time), 3),
        }
        for region in silence_regions:
            center = round(float(region.center_window * rms.window_seconds), 3)
            if abs(center - expected_time) <= self._search_window_seconds * 2.0:
                nearby_source_timestamps.add(center)
        for ts in rms_valley_timestamps:
            if abs(ts - expected_time) <= self._search_window_seconds * 2.0:
                nearby_source_timestamps.add(round(float(ts), 3))

        current = window_start
        while current <= window_end:
            timestamps.add(round(float(current), 3))
            current += self._sample_step_seconds

        merged_by_time = sorted(timestamps)
        entering_candidates = len(merged_by_time)

        max_rms = float(np.max(rms.values)) if len(rms.values) else 1.0
        candidates: list[BoundaryCandidate] = []
        outside_best: BoundaryCandidate | None = None

        for ts in merged_by_time:
            idx = self._time_to_index(rms, ts)
            value = float(rms.values[idx])
            silence_score = float(np.clip(1.0 - (value / max(max_rms, 1e-9)), 0.0, 1.0))
            valley_score = self._rms_detector.valley_score(rms, ts)
            duration_error = abs(ts - expected_time)

            # Agreement-first candidate score: duration fit + silence + RMS valley.
            duration_fit = float(np.exp(-duration_error / 6.0))
            overall = 0.40 * duration_fit + 0.35 * silence_score + 0.25 * valley_score

            candidates.append(
                BoundaryCandidate(
                    timestamp=float(ts),
                    silence_score=silence_score,
                    rms_valley_score=valley_score,
                    duration_error=duration_error,
                    overall_score=float(overall),
                    duration_fit=duration_fit,
                )
            )

        for ts in sorted(nearby_source_timestamps):
            if window_start <= ts <= window_end:
                continue
            idx = self._time_to_index(rms, ts)
            value = float(rms.values[idx])
            silence_score = float(np.clip(1.0 - (value / max(max_rms, 1e-9)), 0.0, 1.0))
            valley_score = self._rms_detector.valley_score(rms, ts)
            duration_error = abs(ts - expected_time)
            duration_fit = float(np.exp(-duration_error / 6.0))
            overall = 0.40 * duration_fit + 0.35 * silence_score + 0.25 * valley_score

            candidate = BoundaryCandidate(
                timestamp=float(ts),
                silence_score=silence_score,
                rms_valley_score=valley_score,
                duration_error=duration_error,
                overall_score=float(overall),
                duration_fit=duration_fit,
            )
            if outside_best is None or candidate.overall_score > outside_best.overall_score:
                outside_best = candidate

        # Keep top candidates to control combinatorial cost while preserving diversity.
        candidates.sort(key=lambda c: c.overall_score, reverse=True)
        all_candidates_sorted = list(candidates)
        trimmed = candidates[:12]

        discarded: list[str] = []
        for candidate in candidates[12:]:
            discarded.append(
                "trimmed_by_top_k "
                f"time={candidate.timestamp:.2f} score={candidate.overall_score:.3f}"
            )

        meta = CandidateDiscoveryDiagnostics(
            track_number=track_number,
            expected_timestamp=expected_time,
            original_expected_timestamp=original_expected_time,
            drift_applied_seconds=drift_applied_seconds,
            original_window_start=original_window_start,
            original_window_end=original_window_end,
            window_start=window_start,
            window_end=window_end,
            first_candidate=merged_by_time[0] if merged_by_time else None,
            last_candidate=merged_by_time[-1] if merged_by_time else None,
            best_outside_window_timestamp=(
                outside_best.timestamp if outside_best is not None else None
            ),
            best_outside_window_score=(
                outside_best.overall_score if outside_best is not None else None
            ),
            silence_candidates=silence_candidates,
            rms_valley_candidates=valley_candidates,
            merged_candidates=len(merged_by_time),
            entering_candidates=entering_candidates,
            leaving_candidates=len(trimmed),
            all_candidates_sorted=all_candidates_sorted,
            discarded_candidates=discarded,
        )

        return trimmed, meta

    def rms_valley_timestamps(self, rms: RMSAnalysis) -> list[float]:
        values = rms.values
        if len(values) < 3:
            return []

        timestamps: list[float] = []
        for idx in range(1, len(values) - 1):
            if values[idx] <= values[idx - 1] and values[idx] <= values[idx + 1]:
                timestamps.append(round(idx * rms.window_seconds, 3))
        return timestamps

    @staticmethod
    def _time_to_index(rms: RMSAnalysis, time_seconds: float) -> int:
        idx = int(time_seconds / rms.window_seconds)
        return int(np.clip(idx, 0, len(rms.values) - 1))
