from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AnalyzeRequest:
    """Input contract for analysis orchestration."""

    filename: str
    expected_track_count: int | None = None
    expected_boundary_times: tuple[float, ...] | None = None
    diagnostics: bool = False
