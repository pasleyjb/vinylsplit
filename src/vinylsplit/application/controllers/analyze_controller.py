from __future__ import annotations

from vinylsplit.application.dto.analyze_request import AnalyzeRequest
from vinylsplit.application.dto.analyze_result import AnalyzeResult
from vinylsplit.application.dto.metadata_result import MetadataResult
from vinylsplit.application.interfaces.services import AnalyzeServiceInterface, MetadataServiceInterface
from vinylsplit.models import AudioInfo


class AnalyzeController:
    """Translate presentation requests into analysis and metadata service calls."""

    def __init__(
        self,
        analyze_service: AnalyzeServiceInterface,
        metadata_service: MetadataServiceInterface,
    ) -> None:
        self._analyze_service = analyze_service
        self._metadata_service = metadata_service

    def inspect(self, filename: str) -> AudioInfo:
        """Inspect an audio file."""

        return self._analyze_service.inspect(filename)

    def analyze(self, request: AnalyzeRequest) -> AnalyzeResult:
        """Analyze an audio file from a structured request."""

        return self._analyze_service.analyze(request)

    def analyze_file(
        self,
        filename: str,
        expected_track_count: int | None = None,
        expected_boundary_times: tuple[float, ...] | None = None,
        diagnostics: bool = False,
    ) -> AnalyzeResult:
        """Analyze an audio file from primitive input values."""

        request = AnalyzeRequest(
            filename=filename,
            expected_track_count=expected_track_count,
            expected_boundary_times=expected_boundary_times,
            diagnostics=diagnostics,
        )
        return self._analyze_service.analyze(request)

    def lookup_metadata(self, filename: str) -> MetadataResult:
        """Lookup metadata for a source file."""

        return self._metadata_service.lookup(filename)
