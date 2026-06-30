from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from vinylsplit.optimization.cost_function import RegionCostFunction, RegionLayoutCost
from vinylsplit.optimization.diagnostics import (
    BoundaryCandidate,
    OptimizationRegion,
    RegionOptimizationDiagnostics,
)


@dataclass(slots=True)
class RegionOptimizationResult:
    """Optimization result for one region."""

    selected_candidates: list[BoundaryCandidate]
    cost: RegionLayoutCost
    diagnostics: RegionOptimizationDiagnostics


class RegionOptimizer:
    """Optimize complete boundary arrangements for a region (non-greedy)."""

    def __init__(
        self,
        cost_function: RegionCostFunction,
        max_layouts_to_score: int = 25000,
    ) -> None:
        self._cost = cost_function
        self._max_layouts_to_score = max(500, max_layouts_to_score)

    def optimize(
        self,
        region: OptimizationRegion,
        candidates_by_boundary: dict[int, list[BoundaryCandidate]],
        current_layout: list[BoundaryCandidate],
    ) -> RegionOptimizationResult:
        candidate_lists = [
            candidates_by_boundary.get(boundary_index, [])
            for boundary_index in region.boundary_indices
        ]

        # Guarantee a candidate for each boundary by falling back to current layout.
        for idx, candidates in enumerate(candidate_lists):
            if candidates:
                continue
            fallback = current_layout[idx]
            candidate_lists[idx] = [fallback]

        baseline_cost = self._cost.evaluate(region, current_layout)

        best_layout = list(current_layout)
        best_cost = baseline_cost
        evaluated = 0

        total_product = 1
        for candidates in candidate_lists:
            total_product *= max(1, len(candidates))

        if total_product <= self._max_layouts_to_score:
            iterator = product(*candidate_lists)
            for combo in iterator:
                layout = list(combo)
                evaluated += 1
                score = self._cost.evaluate(region, layout)
                if score.total_cost < best_cost.total_cost:
                    best_cost = score
                    best_layout = layout
        else:
            # Beam-style dynamic pruning keeps a region-wide objective while
            # avoiding independent greedy picks.
            beam: list[list[BoundaryCandidate]] = [[]]
            beam_width = 64
            for candidates in candidate_lists:
                expanded: list[tuple[float, list[BoundaryCandidate]]] = []
                for partial in beam:
                    for candidate in candidates:
                        layout = partial + [candidate]
                        if len(layout) > 1 and layout[-1].timestamp <= layout[-2].timestamp:
                            continue

                        # Partial proxy score from candidate quality.
                        proxy_cost = -sum(c.overall_score for c in layout) / max(1, len(layout))
                        expanded.append((proxy_cost, layout))

                expanded.sort(key=lambda item: item[0])
                beam = [layout for _, layout in expanded[:beam_width]]

            for layout in beam:
                evaluated += 1
                score = self._cost.evaluate(region, layout)
                if score.total_cost < best_cost.total_cost:
                    best_cost = score
                    best_layout = layout

        moved = sum(
            1 for old, new in zip(current_layout, best_layout)
            if abs(old.timestamp - new.timestamp) >= 0.01
        )

        diagnostics = RegionOptimizationDiagnostics(
            first_track=region.start_index + 1,
            last_track=region.end_index,
            expected_boundaries=len(region.expected_boundaries),
            candidates_evaluated=evaluated,
            initial_region_score=baseline_cost.normalized_score,
            optimized_region_score=best_cost.normalized_score,
            average_duration_error_before=baseline_cost.average_duration_error,
            average_duration_error_after=best_cost.average_duration_error,
            boundaries_moved=moved,
            overall_improvement=best_cost.normalized_score - baseline_cost.normalized_score,
        )

        return RegionOptimizationResult(
            selected_candidates=best_layout,
            cost=best_cost,
            diagnostics=diagnostics,
        )
