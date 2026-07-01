"""Region reconstruction optimization components.

These modules implement the Milestone 3.1 region-based refinement pipeline.
"""

from vinylsplit.optimization.candidate_generator import CandidateGenerator
from vinylsplit.optimization.cost_function import RegionCostFunction, RegionLayoutCost
from vinylsplit.optimization.drift_estimator import DriftEstimationResult, RegionDriftEstimator
from vinylsplit.optimization.diagnostics import (
    BoundaryCandidate,
    DriftAnalysisDiagnostics,
    OptimizationRegion,
    RegionOptimizationDiagnostics,
)
from vinylsplit.optimization.region_optimizer import RegionOptimizationResult, RegionOptimizer
from vinylsplit.optimization.rms_detector import RMSValleyDetector

__all__ = [
    "BoundaryCandidate",
    "CandidateGenerator",
    "DriftAnalysisDiagnostics",
    "DriftEstimationResult",
    "OptimizationRegion",
    "RegionDriftEstimator",
    "RegionCostFunction",
    "RegionLayoutCost",
    "RegionOptimizationDiagnostics",
    "RegionOptimizationResult",
    "RegionOptimizer",
    "RMSValleyDetector",
]
