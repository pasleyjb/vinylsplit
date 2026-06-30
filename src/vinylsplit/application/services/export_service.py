from __future__ import annotations

from vinylsplit.application.dto.export_result import ExportResult
from vinylsplit.application.interfaces.services import ExportServiceInterface
from vinylsplit.pipeline import Pipeline


class ExportService(ExportServiceInterface):
    """Application service for end-to-end export workflows."""

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    async def export(
        self,
        filename: str,
        output_directory: str,
        artist: str | None = None,
        album: str | None = None,
    ) -> ExportResult:
        """Run the existing processing pipeline and return summary output."""

        if not filename.strip():
            raise ValueError("filename must not be empty")
        if not output_directory.strip():
            raise ValueError("output_directory must not be empty")

        results = await self._pipeline.process(
            filename=filename,
            output_directory=output_directory,
            artist=artist,
            album=album,
        )
        return ExportResult(
            source_file=filename,
            output_directory=output_directory,
            results=tuple(results),
            exported_tracks=len(results),
            stopped=not results,
        )
