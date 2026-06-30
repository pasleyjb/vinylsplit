from __future__ import annotations

from abc import ABC, abstractmethod

from vinylsplit.application.dto.analyze_request import AnalyzeRequest
from vinylsplit.application.dto.analyze_result import AnalyzeResult
from vinylsplit.application.dto.export_result import ExportResult
from vinylsplit.application.dto.metadata_result import MetadataResult
from vinylsplit.application.dto.review_result import ReviewResult
from vinylsplit.models import AudioInfo


class AnalyzeServiceInterface(ABC):
    """Contract for analysis orchestration."""

    @abstractmethod
    def inspect(self, filename: str) -> AudioInfo:
        """Inspect an audio file."""

    @abstractmethod
    def analyze(self, request: AnalyzeRequest) -> AnalyzeResult:
        """Analyze an audio file and return detected boundaries."""


class MetadataServiceInterface(ABC):
    """Contract for metadata lookup orchestration."""

    @abstractmethod
    def lookup(self, filename: str) -> MetadataResult:
        """Look up metadata for the input file."""


class ReviewServiceInterface(ABC):
    """Contract for review workflow orchestration."""

    @abstractmethod
    def review(
        self,
        filename: str,
        expected_track_count: int | None = None,
        expected_boundary_times: tuple[float, ...] | None = None,
        diagnostics: bool = False,
    ) -> ReviewResult:
        """Prepare a review session from detected boundaries."""


class ExportServiceInterface(ABC):
    """Contract for export workflow orchestration."""

    @abstractmethod
    async def export(
        self,
        filename: str,
        output_directory: str,
        artist: str | None = None,
        album: str | None = None,
    ) -> ExportResult:
        """Run the end-to-end processing and export workflow."""
