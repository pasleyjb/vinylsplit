from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class BoundaryCandidate:
    """Candidate boundary evidence near one expected boundary position."""

    timestamp: float
    silence_score: float
    rms_valley_score: float
    duration_error: float
    overall_score: float
    duration_fit: float = 0.0


@dataclass(slots=True)
class OptimizationRegion:
    """One unlocked region bounded by immutable anchors."""

    start_index: int
    end_index: int
    start_time: float
    end_time: float
    boundary_indices: list[int]
    expected_boundaries: list[float]

    @property
    def track_count(self) -> int:
        return len(self.boundary_indices)


@dataclass(slots=True)
class RegionOptimizationDiagnostics:
    """Diagnostics emitted for one optimized region."""

    first_track: int
    last_track: int
    expected_boundaries: int
    candidates_evaluated: int
    initial_region_score: float
    optimized_region_score: float
    average_duration_error_before: float
    average_duration_error_after: float
    boundaries_moved: int
    overall_improvement: float

    def summary_lines(self) -> list[str]:
        return [
            f"Region: Tracks {self.first_track}-{self.last_track}",
            f"Expected boundaries: {self.expected_boundaries}",
            f"Candidates evaluated: {self.candidates_evaluated}",
            f"Initial region score: {self.initial_region_score:.1f}",
            f"Optimized region score: {self.optimized_region_score:.1f}",
            (
                "Average duration error: "
                f"{self.average_duration_error_before:.1f}s -> "
                f"{self.average_duration_error_after:.1f}s"
            ),
            f"Boundaries moved: {self.boundaries_moved}",
            f"Overall improvement: {self.overall_improvement:+.1f}",
        ]


@dataclass(slots=True)
class CandidateDiscoveryDiagnostics:
    """Candidate discovery details for one expected boundary."""

    track_number: int
    expected_timestamp: float
    original_expected_timestamp: float
    drift_applied_seconds: float
    original_window_start: float
    original_window_end: float
    window_start: float
    window_end: float
    first_candidate: float | None
    last_candidate: float | None
    best_outside_window_timestamp: float | None
    best_outside_window_score: float | None
    silence_candidates: int
    rms_valley_candidates: int
    merged_candidates: int
    entering_candidates: int
    leaving_candidates: int
    all_candidates_sorted: list[BoundaryCandidate] = field(default_factory=list)
    discarded_candidates: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BoundaryDecisionDiagnostics:
    """Decision trace for one optimized boundary."""

    track_number: int
    expected_timestamp: float
    window_start: float
    window_end: float
    selected_timestamp: float
    selected_reason: str
    selected_score: float
    selected_silence: float
    selected_rms_valley: float
    selected_duration_fit: float
    stronger_silence_found: bool
    deeper_rms_found: bool
    lower_region_cost_possible: bool
    highest_silence_rejected: bool
    highest_silence_rejection_reason: str
    duration_weighting_overrode_audio: bool
    better_candidate_outside_window: bool
    chronology_rejected_better_candidate: bool
    region_optimizer_rejected_locally_better_candidate: bool
    selected_near_window_edge: bool


@dataclass(slots=True)
class BoundaryDebugReport:
    """Full debug report for one boundary in one region."""

    region_id: str
    discovery: CandidateDiscoveryDiagnostics
    candidates_sorted: list[BoundaryCandidate]
    top_ranked: list[BoundaryCandidate]
    decision: BoundaryDecisionDiagnostics

    def to_lines(self) -> list[str]:
        d = self.discovery
        q = self.decision
        lines = [
            f"Timestamp: {utc_now_text()}",
            f"Region ID: {self.region_id}",
            f"Track: {d.track_number}",
            f"Expected Boundary: {format_timestamp(d.expected_timestamp)}",
            "Original Search Window",
            f"{format_timestamp(d.original_window_start)} -> {format_timestamp(d.original_window_end)}",
            "Drift Applied",
            f"{d.drift_applied_seconds:+.2f} sec",
            "Corrected Search Window",
            f"{format_timestamp(d.window_start)} -> {format_timestamp(d.window_end)}",
            f"Candidates Found: {d.leaving_candidates}",
            "",
            "Candidate Discovery:",
            f"Original expected timestamp: {format_timestamp(d.original_expected_timestamp)}",
            f"Corrected expected timestamp: {format_timestamp(d.expected_timestamp)}",
            (
                "Search window: "
                f"{format_timestamp(d.window_start)} -> {format_timestamp(d.window_end)}"
            ),
            (
                "First candidate: "
                f"{format_timestamp(d.first_candidate) if d.first_candidate is not None else 'n/a'}"
            ),
            (
                "Last candidate: "
                f"{format_timestamp(d.last_candidate) if d.last_candidate is not None else 'n/a'}"
            ),
            (
                "Best outside-window candidate: "
                f"{format_timestamp(d.best_outside_window_timestamp) if d.best_outside_window_timestamp is not None else 'n/a'}"
            ),
            (
                "Best outside-window score: "
                f"{d.best_outside_window_score:.3f}"
                if d.best_outside_window_score is not None
                else "Best outside-window score: n/a"
            ),
            f"Silence candidates: {d.silence_candidates}",
            f"RMS valley candidates: {d.rms_valley_candidates}",
            f"Merged candidates: {d.merged_candidates}",
            (
                "Pipeline stage Candidate Generation: "
                f"in={d.entering_candidates}, out={d.merged_candidates}"
            ),
            (
                "Pipeline stage Candidate Filtering: "
                f"in={d.merged_candidates}, out={d.leaving_candidates}"
            ),
            "Pipeline stage Scoring: "
            f"in={d.leaving_candidates}, out={d.leaving_candidates}",
            (
                "Pipeline stage Region Optimization: "
                f"in={d.leaving_candidates}, out=1"
            ),
        ]

        if d.silence_candidates == 0:
            lines.append("No silence candidates found.")
        if d.rms_valley_candidates == 0:
            lines.append("No RMS valley candidates found.")
        if d.leaving_candidates == 0:
            lines.append("No valid optimization candidates.")

        if d.discarded_candidates:
            lines.append("Discarded candidates:")
            lines.extend(d.discarded_candidates)

        lines.extend(["", "Candidates (sorted by combined score):"])
        for candidate in self.candidates_sorted:
            lines.extend(
                [
                    f"Candidate: {format_timestamp(candidate.timestamp)}",
                    f"Duration Fit: {candidate.duration_fit:.3f}",
                    f"Silence Score: {candidate.silence_score:.3f}",
                    f"RMS Valley Score: {candidate.rms_valley_score:.3f}",
                    f"Duration Error: {candidate.duration_error:+.2f} sec",
                    f"Combined Score: {candidate.overall_score:.3f}",
                    "",
                ]
            )

        lines.append("Top 5 candidates:")
        lines.append("Rank  Time        Score")
        for rank, candidate in enumerate(self.top_ranked, start=1):
            lines.append(
                f"{rank:<5} {format_timestamp(candidate.timestamp):<11} {candidate.overall_score:.3f}"
            )

        lines.extend(
            [
                "",
                f"Selected Boundary: {format_timestamp(q.selected_timestamp)}",
                f"Reason: {q.selected_reason}",
                f"Selected Duration Fit: {q.selected_duration_fit:.3f}",
                f"Selected Silence: {q.selected_silence:.3f}",
                f"Selected RMS Valley: {q.selected_rms_valley:.3f}",
                f"Selected Combined Score: {q.selected_score:.3f}",
                (
                    "WARNING: Boundary selected near search window limit."
                    if q.selected_near_window_edge
                    else ""
                ),
                f"Was a stronger silence candidate discovered? {_yn(q.stronger_silence_found)}",
                f"Was a deeper RMS valley discovered? {_yn(q.deeper_rms_found)}",
                f"Was a lower region cost possible? {_yn(q.lower_region_cost_possible)}",
                f"Was the highest-scoring silence rejected? {_yn(q.highest_silence_rejected)}",
                f"If rejected, why? {q.highest_silence_rejection_reason}",
                (
                    "Did duration weighting override stronger audio evidence? "
                    f"{_yn(q.duration_weighting_overrode_audio)}"
                ),
                (
                    "Was the better candidate outside the search window? "
                    f"{_yn(q.better_candidate_outside_window)}"
                ),
                (
                    "Did chronology constraints reject a better candidate? "
                    f"{_yn(q.chronology_rejected_better_candidate)}"
                ),
                (
                    "Did region optimization reject a locally better candidate? "
                    f"{_yn(q.region_optimizer_rejected_locally_better_candidate)}"
                ),
            ]
        )

        return [line for line in lines if line != ""]


@dataclass(slots=True)
class CandidateGenerationResult:
    """Candidates and discovery diagnostics keyed by boundary index."""

    candidates_by_boundary: dict[int, list[BoundaryCandidate]]
    discovery_by_boundary: dict[int, CandidateDiscoveryDiagnostics]


@dataclass(slots=True)
class DriftAnalysisDiagnostics:
    """Region-level drift analysis output for debug mode."""

    region_id: str
    average_offset: float
    median_offset: float
    standard_deviation: float
    supporting_boundaries: int
    confidence: float
    applied_drift: float
    average_duration_error: float
    median_duration_error: float
    predicted_duration_error: float

    def summary_lines(self) -> list[str]:
        return [
            "Region Drift Analysis",
            f"Average Offset: {self.average_offset:+.2f} sec",
            f"Median Offset: {self.median_offset:+.2f} sec",
            f"Standard Deviation: {self.standard_deviation:.2f} sec",
            f"Supporting Boundaries: {self.supporting_boundaries}",
            f"Confidence: {self.confidence * 100:.0f}%",
            f"Applied Drift: {self.applied_drift:+.2f} sec",
            "",
            "Region Summary",
            f"Average Duration Error: {self.average_duration_error:.2f} sec",
            f"Median Duration Error: {self.median_duration_error:.2f} sec",
            f"Estimated Drift: {self.median_offset:+.2f} sec",
            f"Applied Drift: {self.applied_drift:+.2f} sec",
            f"Predicted Duration Error: {self.predicted_duration_error:.2f} sec",
        ]


@dataclass(slots=True)
class RefinementDiagnostics:
    """Container for all region diagnostics in one refine pass."""

    regions: list[RegionOptimizationDiagnostics] = field(default_factory=list)
    boundary_reports: list[BoundaryDebugReport] = field(default_factory=list)
    drift_reports: list[DriftAnalysisDiagnostics] = field(default_factory=list)

    def to_lines(self) -> list[str]:
        if not self.regions:
            return []

        lines: list[str] = []
        for idx, region in enumerate(self.regions, start=1):
            if idx > 1:
                lines.append("")
            lines.append(f"Region {idx}")
            lines.extend(region.summary_lines())
        return lines

    def to_debug_lines(self) -> list[str]:
        lines: list[str] = []
        for report in self.drift_reports:
            if lines:
                lines.append("")
            lines.append(f"Region ID: {report.region_id}")
            lines.extend(report.summary_lines())

        for report in self.boundary_reports:
            if lines:
                lines.append("")
            lines.extend(report.to_lines())

        if self.regions:
            if lines:
                lines.append("")
            lines.append("Region Diagnostics")
            for idx, region in enumerate(self.regions, start=1):
                lines.append(f"Region {idx}")
                lines.extend(region.summary_lines())
                if idx < len(self.regions):
                    lines.append("")

        return lines


def format_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    minutes = int(seconds // 60)
    rem = seconds - (minutes * 60)
    return f"{minutes:02d}:{rem:05.2f}"


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _yn(value: bool) -> str:
    return "Yes" if value else "No"
