"""Adaptive local reanalysis and anchored refinement for review.

This module provides two related capabilities used by the interactive
review session:

1. Local suggestion generation after a manual edit.
2. Anchored refinement (`refine`) that improves AUTO boundaries while
   preserving user anchors.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vinylsplit.analysis.rms import RMSAnalyzer, RMSAnalysis
from vinylsplit.analysis.silence import SilenceDetector
from vinylsplit.boundary_states import BoundaryState
from vinylsplit.models import Boundary
from vinylsplit.optimization.candidate_generator import CandidateGenerator
from vinylsplit.optimization.cost_function import RegionCostFunction
from vinylsplit.optimization.drift_estimator import RegionDriftEstimator
from vinylsplit.optimization.diagnostics import (
    BoundaryDebugReport,
    BoundaryDecisionDiagnostics,
    BoundaryCandidate,
    CandidateGenerationResult,
    OptimizationRegion,
    RefinementDiagnostics,
)
from vinylsplit.optimization.region_optimizer import RegionOptimizer
from vinylsplit.optimization.rms_detector import RMSValleyDetector
from vinylsplit.review_state import AdaptiveReviewState
from vinylsplit.suggestions import Suggestion

# Neighborhood suggestion constants.
_NEIGHBORHOOD_PAD_SECONDS = 30.0
_MIN_CONFIDENCE_DELTA = 0.05
_MAX_SUGGESTION_DISTANCE_SECONDS = 2.0

# Refinement constants.
_REFINE_INITIAL_WINDOW_SECONDS = 8.0
_REFINE_WINDOW_STEPS_SECONDS = (8.0, 14.0, 20.0, 28.0)
_REFINE_MIN_SCORE = 0.08
_REFINE_MIN_MOVEMENT_SECONDS = 0.01


@dataclass(slots=True)
class RefinementSummary:
    """Summary of one anchored refinement pass."""

    anchors: int
    regions_analyzed: int
    boundaries_improved: int
    validation_warnings: int = 0
    diagnostics: list[str] | None = None


class LocalAnalyzer:
    """Perform neighborhood analysis and anchored refinement over source audio."""

    def __init__(self, audio: np.ndarray, sample_rate: int) -> None:
        self._audio = audio
        self._sample_rate = sample_rate
        self._rms_analyzer = RMSAnalyzer(window_seconds=0.050)
        self._silence_detector = SilenceDetector(minimum_silence_seconds=1.0)

        self._rms = self._rms_analyzer.calculate(self._audio, self._sample_rate)
        _, self._silence_regions = self._silence_detector.detect(self._rms)

        # Precompute signal features used in refinement scoring.
        self._rms_gradient = self._compute_rms_gradient(self._rms.values)
        self._spectral_flux = self._compute_spectral_flux(
            self._audio,
            self._sample_rate,
            self._rms.window_seconds,
        )

        self._max_rms = float(np.max(self._rms.values)) if len(self._rms.values) else 1.0
        self._max_grad = float(np.max(self._rms_gradient)) if len(self._rms_gradient) else 1.0
        self._max_flux = float(np.max(self._spectral_flux)) if len(self._spectral_flux) else 1.0

        # Milestone 3.1 region reconstruction components.
        self._rms_valley_detector = RMSValleyDetector(lookaround_windows=6)
        self._candidate_generator = CandidateGenerator(
            silence_detector=self._silence_detector,
            rms_detector=self._rms_valley_detector,
            search_window_seconds=15.0,
            sample_step_seconds=0.5,
        )
        self._drift_estimator = RegionDriftEstimator(search_window_seconds=15.0)

    # ------------------------------------------------------------------
    # Existing neighborhood suggestion flow
    # ------------------------------------------------------------------

    def analyze_neighborhood(
        self,
        state: AdaptiveReviewState,
        edited_track_number: int,
    ) -> list[Suggestion]:
        boundaries = state.sorted_boundaries()
        if not boundaries:
            return []

        edited_boundary = state.boundary_for_track(edited_track_number)
        if edited_boundary is None:
            return []

        idx = boundaries.index(edited_boundary)
        total_duration = len(self._audio) / self._sample_rate

        window_start = max(
            0.0,
            boundaries[idx - 1].start_time if idx > 0 else 0.0,
        ) - _NEIGHBORHOOD_PAD_SECONDS
        window_start = max(0.0, window_start)

        window_end = min(
            total_duration,
            boundaries[idx + 1].start_time if idx + 1 < len(boundaries) else total_duration,
        ) + _NEIGHBORHOOD_PAD_SECONDS
        window_end = min(total_duration, window_end)

        if window_end <= window_start:
            return []

        start_sample = int(window_start * self._sample_rate)
        end_sample = int(window_end * self._sample_rate)
        audio_slice = self._audio[start_sample:end_sample]

        if len(audio_slice) == 0:
            return []

        rms = self._rms_analyzer.calculate(audio_slice, self._sample_rate)
        _, silence_regions = self._silence_detector.detect(rms)

        if not silence_regions:
            return []

        engine = SuggestionEngine()
        return engine.generate(
            edited_boundary=edited_boundary,
            silence_regions=silence_regions,
            rms=rms,
            window_offset_seconds=window_start,
        )

    # ------------------------------------------------------------------
    # Milestone 3.0 anchored refinement
    # ------------------------------------------------------------------

    def refine_boundaries(
        self,
        state: AdaptiveReviewState,
        duration_seconds: float,
        minimum_spacing_seconds: float = 10.0,
        debug: bool = False,
    ) -> RefinementSummary:
        """Improve AUTO boundaries using locked/verified boundaries as anchors.

        Rules enforced:
        - Anchors are immutable.
        - Only AUTO boundaries may move.
        - Track count is preserved (in-place movement only).
        - Search windows expand gradually when no strong candidate is found.
        """
        boundaries = state.sorted_boundaries()
        if len(boundaries) < 2:
            return RefinementSummary(anchors=0, regions_analyzed=0, boundaries_improved=0)

        anchor_indexes = [
            i for i, b in enumerate(boundaries)
            if b.state in {BoundaryState.LOCKED, BoundaryState.VERIFIED}
        ]

        regions = self._build_optimization_regions(
            state=state,
            boundaries=boundaries,
            duration_seconds=duration_seconds,
        )

        cost_function = RegionCostFunction(minimum_spacing_seconds=minimum_spacing_seconds)
        optimizer = RegionOptimizer(cost_function=cost_function)

        diagnostics = RefinementDiagnostics()
        improved = 0

        for region in regions:
            drift = self._drift_estimator.estimate(
                region=region,
                rms=self._rms,
                silence_regions=self._silence_regions,
                rms_valley_timestamps=self._candidate_generator.rms_valley_timestamps(self._rms),
            )
            aligned_region = OptimizationRegion(
                start_index=region.start_index,
                end_index=region.end_index,
                start_time=region.start_time,
                end_time=region.end_time,
                boundary_indices=list(region.boundary_indices),
                expected_boundaries=list(drift.corrected_expected_boundaries),
            )

            generation = self._candidate_generator.generate_region_candidates(
                region=aligned_region,
                rms=self._rms,
                original_expected_boundaries=region.expected_boundaries,
                drift_applied_seconds=drift.applied_drift_seconds,
            )
            candidates_by_boundary = generation.candidates_by_boundary

            current_layout = [
                self._current_candidate(boundaries[idx], aligned_region.expected_boundaries[pos])
                for pos, idx in enumerate(region.boundary_indices)
            ]

            result = optimizer.optimize(
                region=aligned_region,
                candidates_by_boundary=candidates_by_boundary,
                current_layout=current_layout,
            )

            if debug:
                diagnostics.drift_reports.append(drift.diagnostics)
                diagnostics.boundary_reports.extend(
                    self._build_boundary_debug_reports(
                        region=aligned_region,
                        generation=generation,
                        selected_layout=result.selected_candidates,
                        selected_region_cost=result.cost.total_cost,
                        cost_function=cost_function,
                    )
                )

            for boundary_index, candidate in zip(region.boundary_indices, result.selected_candidates):
                boundary = boundaries[boundary_index]
                original_time = boundary.start_time

                if abs(candidate.timestamp - original_time) >= _REFINE_MIN_MOVEMENT_SECONDS:
                    improved += 1

                boundary.start_time = candidate.timestamp
                # Confidence is now agreement between independent signals.
                boundary.detector_confidence = float(max(0.0, min(1.0, candidate.overall_score)))
                boundary.reasons = [
                    "Region reconstruction",
                    "Duration/silence/RMS agreement",
                ]

            diagnostics.regions.append(result.diagnostics)

        return RefinementSummary(
            anchors=len(anchor_indexes),
            regions_analyzed=len(regions),
            boundaries_improved=improved,
            diagnostics=diagnostics.to_debug_lines() if debug else None,
        )

    def _build_optimization_regions(
        self,
        state: AdaptiveReviewState,
        boundaries: list[Boundary],
        duration_seconds: float,
    ) -> list[OptimizationRegion]:
        separators = [-1] + [
            i for i, b in enumerate(boundaries)
            if b.state in {BoundaryState.LOCKED, BoundaryState.VERIFIED}
        ] + [len(boundaries)]

        regions: list[OptimizationRegion] = []
        for left, right in zip(separators[:-1], separators[1:]):
            boundary_indices = [
                i for i in range(left + 1, right)
                if i > 0 and i < len(boundaries) and boundaries[i].state is BoundaryState.AUTO
            ]
            if not boundary_indices:
                continue

            region_start_time = boundaries[left].start_time if left >= 0 else 0.0
            region_end_time = boundaries[right].start_time if right < len(boundaries) else duration_seconds

            expected_boundaries = [
                self._predicted_time(state, idx, boundaries[idx].start_time)
                for idx in boundary_indices
            ]

            regions.append(
                OptimizationRegion(
                    start_index=max(0, left + 1),
                    end_index=min(len(boundaries), right),
                    start_time=region_start_time,
                    end_time=region_end_time,
                    boundary_indices=boundary_indices,
                    expected_boundaries=expected_boundaries,
                )
            )

        if regions:
            return regions

        # No anchors still yields one full-region reconstruction problem.
        full_region_indices = [
            i for i in range(1, len(boundaries))
            if boundaries[i].state is BoundaryState.AUTO
        ]
        if not full_region_indices:
            return []

        expected_boundaries = [
            self._predicted_time(state, idx, boundaries[idx].start_time)
            for idx in full_region_indices
        ]

        return [
            OptimizationRegion(
                start_index=1,
                end_index=len(boundaries),
                start_time=0.0,
                end_time=duration_seconds,
                boundary_indices=full_region_indices,
                expected_boundaries=expected_boundaries,
            )
        ]

    def _current_candidate(self, boundary: Boundary, expected_time: float) -> BoundaryCandidate:
        timestamp = boundary.start_time
        rms_idx = self._time_to_rms_index(timestamp)

        rms_value = float(self._rms.values[rms_idx])
        silence_score = 1.0 - min(1.0, rms_value / max(self._max_rms, 1e-9))
        valley_score = self._rms_valley_detector.valley_score(self._rms, timestamp)
        duration_error = abs(timestamp - expected_time)

        duration_fit = float(np.exp(-duration_error / 6.0))
        overall = 0.40 * duration_fit + 0.35 * silence_score + 0.25 * valley_score

        return BoundaryCandidate(
            timestamp=timestamp,
            silence_score=float(silence_score),
            rms_valley_score=float(valley_score),
            duration_error=float(duration_error),
            overall_score=float(max(0.0, min(1.0, overall))),
            duration_fit=duration_fit,
        )

    def _build_boundary_debug_reports(
        self,
        region: OptimizationRegion,
        generation: CandidateGenerationResult,
        selected_layout: list[BoundaryCandidate],
        selected_region_cost: float,
        cost_function: RegionCostFunction,
    ) -> list[BoundaryDebugReport]:
        reports: list[BoundaryDebugReport] = []

        region_id = f"tracks-{region.start_index + 1}-{region.end_index}"
        for local_idx, boundary_index in enumerate(region.boundary_indices):
            candidates = list(generation.candidates_by_boundary.get(boundary_index, []))
            discovery = generation.discovery_by_boundary[boundary_index]
            selected = selected_layout[local_idx]

            ranked_for_optimizer = (
                sorted(candidates, key=lambda c: c.overall_score, reverse=True)
                if candidates
                else [selected]
            )
            ranked_all_generated = (
                list(discovery.all_candidates_sorted)
                if discovery.all_candidates_sorted
                else list(ranked_for_optimizer)
            )

            top_five = ranked_for_optimizer[:5]

            strongest_silence = max(ranked_all_generated, key=lambda c: c.silence_score)
            deepest_valley = max(ranked_all_generated, key=lambda c: c.rms_valley_score)
            local_best = ranked_for_optimizer[0]

            chronology_rejected = False
            better_candidate_found = False
            better_outside_window = (
                discovery.best_outside_window_score is not None
                and discovery.best_outside_window_score > selected.overall_score
            )
            lower_cost_possible = False
            for candidate in ranked_for_optimizer:
                if candidate.timestamp == selected.timestamp:
                    continue

                if candidate.overall_score > selected.overall_score:
                    better_candidate_found = True

                test_layout = list(selected_layout)
                test_layout[local_idx] = candidate
                if not self._layout_chronological(test_layout):
                    chronology_rejected = True
                    continue

                test_cost = cost_function.evaluate(region, test_layout).total_cost
                if test_cost < selected_region_cost:
                    lower_cost_possible = True

            highest_silence_rejected = strongest_silence.timestamp != selected.timestamp
            if not highest_silence_rejected:
                silence_rejection_reason = "Not rejected."
            elif not self._is_in_window(strongest_silence.timestamp, discovery.window_start, discovery.window_end):
                silence_rejection_reason = "Outside search window."
            elif chronology_rejected:
                silence_rejection_reason = "Rejected by chronology constraints."
            else:
                silence_rejection_reason = "Rejected by lower overall region score."

            selected_near_edge = min(
                abs(selected.timestamp - discovery.window_start),
                abs(discovery.window_end - selected.timestamp),
            ) <= 0.75

            decision = BoundaryDecisionDiagnostics(
                track_number=boundary_index + 1,
                expected_timestamp=discovery.expected_timestamp,
                window_start=discovery.window_start,
                window_end=discovery.window_end,
                selected_timestamp=selected.timestamp,
                selected_reason="Highest overall region score.",
                selected_score=selected.overall_score,
                selected_silence=selected.silence_score,
                selected_rms_valley=selected.rms_valley_score,
                selected_duration_fit=selected.duration_fit,
                stronger_silence_found=strongest_silence.silence_score > selected.silence_score,
                deeper_rms_found=deepest_valley.rms_valley_score > selected.rms_valley_score,
                lower_region_cost_possible=lower_cost_possible,
                highest_silence_rejected=highest_silence_rejected,
                highest_silence_rejection_reason=silence_rejection_reason,
                duration_weighting_overrode_audio=(
                    local_best.timestamp != selected.timestamp
                    and local_best.silence_score > selected.silence_score
                    and local_best.rms_valley_score > selected.rms_valley_score
                    and local_best.duration_fit < selected.duration_fit
                ),
                better_candidate_outside_window=better_outside_window,
                chronology_rejected_better_candidate=chronology_rejected,
                region_optimizer_rejected_locally_better_candidate=(
                    better_candidate_found and local_best.timestamp != selected.timestamp
                ),
                selected_near_window_edge=selected_near_edge,
            )

            reports.append(
                BoundaryDebugReport(
                    region_id=region_id,
                    discovery=discovery,
                    candidates_sorted=ranked_all_generated,
                    top_ranked=top_five,
                    decision=decision,
                )
            )

        return reports

    @staticmethod
    def _layout_chronological(layout: list[BoundaryCandidate]) -> bool:
        return all(
            left.timestamp < right.timestamp
            for left, right in zip(layout[:-1], layout[1:])
        )

    @staticmethod
    def _is_in_window(timestamp: float, window_start: float, window_end: float) -> bool:
        return window_start <= timestamp <= window_end

    # ------------------------------------------------------------------
    # Refinement scoring helpers
    # ------------------------------------------------------------------

    def _search_best_candidate(
        self,
        predicted_time: float,
        original_time: float,
        expected_time: float | None,
        prev_time: float,
        next_time: float,
        min_spacing: float,
        detector_confidence: float | None,
    ) -> tuple[float | None, float]:
        best_time: float | None = None
        best_score = -1.0

        for window in _REFINE_WINDOW_STEPS_SECONDS:
            lo = max(prev_time + min_spacing, predicted_time - window)
            hi = min(next_time - min_spacing, predicted_time + window)
            if hi <= lo:
                continue

            candidates = self._silence_candidates_in_window(lo, hi)
            candidates.append(float(np.clip(predicted_time, lo, hi)))
            candidates.append(float(np.clip(original_time, lo, hi)))

            # Deterministic ordering and dedupe.
            unique_candidates = sorted({round(c, 3) for c in candidates})

            for candidate in unique_candidates:
                score = self._weighted_score(
                    candidate_time=candidate,
                    expected_time=expected_time,
                    original_time=original_time,
                    prev_time=prev_time,
                    next_time=next_time,
                    min_spacing=min_spacing,
                    detector_confidence=detector_confidence,
                )
                if score > best_score:
                    best_score = score
                    best_time = candidate

            if best_score >= _REFINE_MIN_SCORE:
                break

        if best_time is None:
            return None, 0.0

        return best_time, best_score

    def _weighted_score(
        self,
        candidate_time: float,
        expected_time: float | None,
        original_time: float,
        prev_time: float,
        next_time: float,
        min_spacing: float,
        detector_confidence: float | None,
    ) -> float:
        rms_idx = self._time_to_rms_index(candidate_time)

        # Signal 1: silence score (lower RMS -> better boundary).
        rms_value = float(self._rms.values[rms_idx])
        silence_score = 1.0 - min(1.0, rms_value / max(self._max_rms, 1e-9))

        # Signal 2: RMS energy change.
        grad_score = min(1.0, float(self._rms_gradient[rms_idx]) / max(self._max_grad, 1e-9))

        # Signal 3: spectral transition.
        flux_idx = min(rms_idx, len(self._spectral_flux) - 1)
        spectral_score = min(1.0, float(self._spectral_flux[flux_idx]) / max(self._max_flux, 1e-9))

        # Signal 4: expected duration guidance (soft, never forced).
        expected_score = 0.0
        if expected_time is not None:
            delta = abs(candidate_time - expected_time)
            expected_score = float(np.exp(-delta / 6.0))

        # Signal 5: spacing viability.
        left_gap = candidate_time - prev_time
        right_gap = next_time - candidate_time
        min_gap = min(left_gap, right_gap)
        spacing_score = max(0.0, min(1.0, min_gap / max(min_spacing, 1e-6)))

        # Signal 6: original detector confidence influence.
        conf_base = detector_confidence if detector_confidence is not None else 0.5
        original_proximity = float(np.exp(-abs(candidate_time - original_time) / 8.0))
        original_conf_score = conf_base * original_proximity

        # Weighted sum as requested.
        return (
            0.28 * silence_score
            + 0.20 * grad_score
            + 0.20 * spectral_score
            + 0.14 * expected_score
            + 0.10 * spacing_score
            + 0.08 * original_conf_score
        )

    def _predicted_time(self, state: AdaptiveReviewState, boundary_index: int, fallback: float) -> float:
        expected = self._expected_time(state, boundary_index)
        if expected is not None:
            return expected
        return fallback

    def _expected_time(self, state: AdaptiveReviewState, boundary_index: int) -> float | None:
        durations = state.expected_track_durations_seconds
        if not durations:
            return None

        # Boundary index i (0-based) is the start of track i+1.
        if boundary_index <= 0:
            return 0.0

        if boundary_index > len(durations):
            return None

        return float(sum(durations[:boundary_index]))

    def _silence_candidates_in_window(self, lo: float, hi: float) -> list[float]:
        candidates: list[float] = []
        for region in self._silence_regions:
            center_time = region.center_window * self._rms.window_seconds
            if lo <= center_time <= hi:
                candidates.append(center_time)
        return candidates

    def _time_to_rms_index(self, time_seconds: float) -> int:
        idx = int(time_seconds / self._rms.window_seconds)
        return int(np.clip(idx, 0, len(self._rms.values) - 1))

    @staticmethod
    def _compute_rms_gradient(values: np.ndarray) -> np.ndarray:
        if len(values) <= 1:
            return np.zeros_like(values)
        grad = np.abs(np.diff(values, prepend=values[0]))
        return grad

    @staticmethod
    def _compute_spectral_flux(audio: np.ndarray, sample_rate: int, window_seconds: float) -> np.ndarray:
        window_size = max(1, int(sample_rate * window_seconds))
        flux_values: list[float] = []
        prev_spec: np.ndarray | None = None

        for start in range(0, len(audio), window_size):
            frame = audio[start : start + window_size]
            if len(frame) == 0:
                continue
            if len(frame) < window_size:
                padded = np.zeros(window_size, dtype=np.float32)
                padded[: len(frame)] = frame
                frame = padded

            windowed = frame * np.hanning(len(frame))
            spec = np.abs(np.fft.rfft(windowed))
            if prev_spec is None:
                flux_values.append(0.0)
            else:
                diff = spec - prev_spec
                flux_values.append(float(np.sum(np.maximum(diff, 0.0))))
            prev_spec = spec

        if not flux_values:
            return np.zeros(1, dtype=np.float32)

        return np.asarray(flux_values, dtype=np.float32)


class SuggestionEngine:
    """Evaluate silence candidates and generate improvement suggestions."""

    def generate(
        self,
        edited_boundary: Boundary,
        silence_regions: list,
        rms: RMSAnalysis,
        window_offset_seconds: float,
    ) -> list[Suggestion]:
        current_pos = edited_boundary.start_time
        suggestions: list[Suggestion] = []

        for region in silence_regions:
            region_center = (
                region.center_window * rms.window_seconds + window_offset_seconds
            )
            distance = abs(region_center - current_pos)

            if distance < 0.01:
                continue
            if distance > _MAX_SUGGESTION_DISTANCE_SECONDS:
                continue

            region_values = rms.values[region.start_window : region.end_window + 1]
            region_rms_mean = float(np.mean(region_values)) if len(region_values) else 0.0
            silence_strength = max(0.0, 1.0 - region_rms_mean * 100.0)
            confidence_delta = min(0.3, silence_strength * 0.3)

            if confidence_delta < _MIN_CONFIDENCE_DELTA:
                continue

            suggestion = Suggestion.from_positions(
                track_number=edited_boundary.track_number,
                current_position=current_pos,
                suggested_position=region_center,
                reason="Stronger silence transition found nearby during local reanalysis.",
                confidence_delta=confidence_delta,
            )
            suggestions.append(suggestion)

        suggestions.sort(key=lambda s: s.confidence_delta, reverse=True)
        return suggestions[:1]


def build_local_analyzer(source_file: str) -> LocalAnalyzer | None:
    """Construct a ``LocalAnalyzer`` from a source file path."""
    try:
        import soundfile as sf  # type: ignore[import]

        audio, sample_rate = sf.read(source_file, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return LocalAnalyzer(audio=audio, sample_rate=sample_rate)
    except Exception:
        return None
