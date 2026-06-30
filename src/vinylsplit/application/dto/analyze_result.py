from __future__ import annotations

from dataclasses import dataclass

from vinylsplit.models import Boundary


@dataclass(frozen=True, slots=True)
class AnalyzeResult:
    """Output contract for analysis orchestration."""

    filename: str
    boundaries: tuple[Boundary, ...]
    expected_track_count: int | None = None
