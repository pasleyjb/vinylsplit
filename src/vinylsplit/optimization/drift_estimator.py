from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vinylsplit.analysis.rms import RMSAnalysis
from vinylsplit.analysis.report import SilenceRegion
from vinylsplit.optimization.diagnostics import DriftAnalysisDiagnostics, OptimizationRegion


@dataclass(slots=True)
class DriftEstimationResult:
    """Drift estimation output for one optimization region."""

    estimated_drift_seconds: float
    applied_drift_seconds: float
    confidence: float
    offsets_seconds: list[float]
    corrected_expected_boundaries: list[float]
    diagnostics: DriftAnalysisDiagnostics


class RegionDriftEstimator:
    """Estimate systematic timing drift for one unlocked region."""

    def __init__(self, search_window_seconds: float = 15.0) -> None:
        self._search_window = search_window_seconds

    def estimate(
        self,
        region: OptimizationRegion,
        rms: RMSAnalysis,
        silence_regions: list[SilenceRegion],
        rms_valley_timestamps: list[float],
    ) -> DriftEstimationResult:
        offsets: list[float] = []
        agreement_scores: list[float] = []

        for expected in region.expected_boundaries:
            silence = self._nearest_within_window(
                expected_time=expected,
                values=[r.center_window * rms.window_seconds for r in silence_regions],
                window=self._search_window * 2.0,
            )
            valley = self._nearest_within_window(
                expected_time=expected,
                values=rms_valley_timestamps,
                window=self._search_window * 2.0,
            )

            evidence_offsets: list[float] = []
            if silence is not None:
                evidence_offsets.append(silence - expected)
            if valley is not None:
                evidence_offsets.append(valley - expected)

            if not evidence_offsets:
                continue

            offsets.append(float(np.median(np.asarray(evidence_offsets, dtype=float))))

            if silence is not None and valley is not None:
                agreement_scores.append(float(np.exp(-abs(silence - valley) / 2.5)))
            else:
                agreement_scores.append(0.6)

        if offsets:
            offset_array = np.asarray(offsets, dtype=float)
            mean_offset = float(np.mean(offset_array))
            median_offset = float(np.median(offset_array))
            std_offset = float(np.std(offset_array))
            avg_duration_error = float(np.mean(np.abs(offset_array)))
            median_duration_error = float(np.median(np.abs(offset_array)))
        else:
            mean_offset = 0.0
            median_offset = 0.0
            std_offset = 0.0
            avg_duration_error = 0.0
            median_duration_error = 0.0

        supporting = len(offsets)
        expected_count = max(1, len(region.expected_boundaries))

        count_strength = min(1.0, supporting / expected_count)
        consistency = float(np.exp(-std_offset / 2.0))
        agreement = float(np.mean(np.asarray(agreement_scores, dtype=float))) if agreement_scores else 0.0

        confidence = float(np.clip(0.45 * consistency + 0.30 * count_strength + 0.25 * agreement, 0.0, 1.0))

        # Low-confidence regions get conservative correction to avoid overfitting noise.
        if supporting == 0:
            applied_drift = 0.0
        elif confidence < 0.35:
            applied_drift = 0.0
        elif confidence < 0.65:
            applied_drift = median_offset * 0.5
        else:
            applied_drift = median_offset

        corrected = [expected + applied_drift for expected in region.expected_boundaries]

        if offsets:
            predicted_error = float(np.mean(np.abs(offset_array - applied_drift)))
        else:
            predicted_error = 0.0

        diagnostics = DriftAnalysisDiagnostics(
            region_id=f"tracks-{region.start_index + 1}-{region.end_index}",
            average_offset=mean_offset,
            median_offset=median_offset,
            standard_deviation=std_offset,
            supporting_boundaries=supporting,
            confidence=confidence,
            applied_drift=applied_drift,
            average_duration_error=avg_duration_error,
            median_duration_error=median_duration_error,
            predicted_duration_error=predicted_error,
        )

        return DriftEstimationResult(
            estimated_drift_seconds=median_offset,
            applied_drift_seconds=applied_drift,
            confidence=confidence,
            offsets_seconds=offsets,
            corrected_expected_boundaries=corrected,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _nearest_within_window(
        expected_time: float,
        values: list[float],
        window: float,
    ) -> float | None:
        if not values:
            return None

        nearest = min(values, key=lambda value: abs(value - expected_time))
        if abs(nearest - expected_time) <= window:
            return float(nearest)
        return None
