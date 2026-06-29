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

        # Regions are open intervals between immutable separators.
        separators = [-1] + anchor_indexes + [len(boundaries)]
        regions: list[list[int]] = []
        for left, right in zip(separators[:-1], separators[1:]):
            idxs = [
                i for i in range(left + 1, right)
                if i > 0 and i < len(boundaries) and boundaries[i].state is BoundaryState.AUTO
            ]
            if idxs:
                regions.append(idxs)

        # No anchors still means one region over all movable AUTO boundaries.
        if not anchor_indexes and not regions:
            idxs = [
                i for i in range(1, len(boundaries))
                if boundaries[i].state is BoundaryState.AUTO
            ]
            if idxs:
                regions.append(idxs)

        improved = 0

        for region in regions:
            for idx in region:
                boundary = boundaries[idx]
                original_time = boundary.start_time

                prev_time = boundaries[idx - 1].start_time
                next_time = (
                    boundaries[idx + 1].start_time
                    if idx + 1 < len(boundaries)
                    else duration_seconds
                )

                prediction = self._predicted_time(state, idx, original_time)

                candidate_time, candidate_score = self._search_best_candidate(
                    predicted_time=prediction,
                    original_time=original_time,
                    expected_time=self._expected_time(state, idx),
                    prev_time=prev_time,
                    next_time=next_time,
                    min_spacing=minimum_spacing_seconds,
                    detector_confidence=boundary.detector_confidence,
                )

                if (
                    candidate_time is not None
                    and abs(candidate_time - original_time) >= _REFINE_MIN_MOVEMENT_SECONDS
                ):
                    boundary.start_time = candidate_time
                    # Confidence now reflects the refinement score.
                    boundary.detector_confidence = float(max(0.0, min(1.0, candidate_score)))
                    boundary.reasons = [
                        "Refined from anchors",
                        "Weighted candidate scoring",
                    ]
                    improved += 1

        return RefinementSummary(
            anchors=len(anchor_indexes),
            regions_analyzed=len(regions),
            boundaries_improved=improved,
        )

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
