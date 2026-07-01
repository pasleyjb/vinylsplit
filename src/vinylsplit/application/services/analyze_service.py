from __future__ import annotations

from vinylsplit.application.dto.analyze_request import AnalyzeRequest
from vinylsplit.application.dto.analyze_result import AnalyzeResult
from vinylsplit.application.interfaces.services import AnalyzeServiceInterface
from vinylsplit.models import AudioInfo
from vinylsplit.pipeline import Pipeline


class AnalyzeService(AnalyzeServiceInterface):
    """Application service for audio inspection and analysis workflows."""

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    def inspect(self, filename: str) -> AudioInfo:
        """Inspect the input audio file using the existing pipeline."""

        self._validate_filename(filename)
        return self._pipeline.inspect(filename)

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResult:
        """Run boundary analysis using the existing pipeline."""

        self._validate_filename(request.filename)

        boundaries = self._pipeline.analyze(
            filename=request.filename,
            expected_track_count=request.expected_track_count,
            expected_boundary_times=list(request.expected_boundary_times)
            if request.expected_boundary_times is not None
            else None,
            diagnostics=request.diagnostics,
        )
        return AnalyzeResult(
            filename=request.filename,
            boundaries=tuple(boundaries),
            expected_track_count=request.expected_track_count,
        )

    @staticmethod
    def _validate_filename(filename: str) -> None:
        if not filename.strip():
            raise ValueError("filename must not be empty")
