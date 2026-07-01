from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vinylsplit.optimization.diagnostics import BoundaryCandidate, OptimizationRegion


@dataclass(slots=True)
class RegionLayoutCost:
    """Raw and normalized costs for one complete region layout."""

    total_cost: float
    average_duration_error: float
    normalized_score: float


class RegionCostFunction:
    """Evaluate complete region layouts with chronology and spacing constraints."""

    def __init__(self, minimum_spacing_seconds: float = 10.0) -> None:
        self._minimum_spacing = minimum_spacing_seconds

    def evaluate(
        self,
        region: OptimizationRegion,
        ordered_candidates: list[BoundaryCandidate],
    ) -> RegionLayoutCost:
        if not ordered_candidates:
            return RegionLayoutCost(
                total_cost=1e9,
                average_duration_error=0.0,
                normalized_score=0.0,
            )

        if not self._is_valid_layout(region, ordered_candidates):
            return RegionLayoutCost(
                total_cost=1e9,
                average_duration_error=1e6,
                normalized_score=0.0,
            )

        duration_errors = np.array([c.duration_error for c in ordered_candidates], dtype=float)
        silence_weakness = np.array([1.0 - c.silence_score for c in ordered_candidates], dtype=float)
        valley_weakness = np.array([1.0 - c.rms_valley_score for c in ordered_candidates], dtype=float)

        spacing_penalty = 0.0
        full_times = [region.start_time] + [c.timestamp for c in ordered_candidates] + [region.end_time]
        for left, right in zip(full_times[:-1], full_times[1:]):
            spacing = right - left
            if spacing < self._minimum_spacing:
                spacing_penalty += (self._minimum_spacing - spacing) * 3.0

        # Region inconsistency: adjacent duration errors fluctuating wildly.
        inconsistency = 0.0
        if len(duration_errors) > 1:
            inconsistency = float(np.mean(np.abs(np.diff(duration_errors))))

        total_cost = (
            1.25 * float(np.mean(duration_errors))
            + 0.85 * float(np.mean(silence_weakness))
            + 0.75 * float(np.mean(valley_weakness))
            + 0.60 * spacing_penalty
            + 0.40 * inconsistency
        )

        # Higher score is better; map cost to a bounded confidence-style score.
        normalized = float(100.0 * np.exp(-total_cost / 6.0))

        return RegionLayoutCost(
            total_cost=total_cost,
            average_duration_error=float(np.mean(duration_errors)),
            normalized_score=normalized,
        )

    def _is_valid_layout(
        self,
        region: OptimizationRegion,
        ordered_candidates: list[BoundaryCandidate],
    ) -> bool:
        if len(ordered_candidates) != len(region.boundary_indices):
            return False

        times = [c.timestamp for c in ordered_candidates]
        if times != sorted(times):
            return False

        if any(t <= region.start_time for t in times):
            return False

        if any(t >= region.end_time for t in times):
            return False

        return True
