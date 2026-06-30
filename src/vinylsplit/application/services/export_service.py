from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from vinylsplit.application.dto.export_result import ExportResult
from vinylsplit.application.events import ProgressUpdated
from vinylsplit.application.interfaces.services import ExportServiceInterface
from vinylsplit.pipeline import Pipeline
from vinylsplit.review_state import AdaptiveReviewState


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
        review_session: AdaptiveReviewState | None = None,
        progress_callback: Callable[[ProgressUpdated], None] | None = None,
    ) -> ExportResult:
        """Run the existing processing pipeline and return summary output."""

        if not filename.strip():
            raise ValueError("filename must not be empty")
        if not output_directory.strip():
            raise ValueError("output_directory must not be empty")

        def _forward_progress(
            stage: str,
            description: str,
            completed: int | None,
            total: int | None,
        ) -> None:
            if progress_callback is None:
                return

            progress_callback(
                ProgressUpdated(
                    stage=stage,
                    completed=completed or 0,
                    total=total,
                    description=description,
                )
            )

        results = await self._pipeline.process(
            filename=filename,
            output_directory=output_directory,
            artist=artist,
            album=album,
            review_session=review_session,
            progress_callback=_forward_progress,
        )
        exported_files = list(Path(output_directory).rglob("*.flac"))
        exported_track_count = len(exported_files)
        return ExportResult(
            source_file=filename,
            output_directory=output_directory,
            results=tuple(results),
            exported_tracks=exported_track_count,
            stopped=exported_track_count == 0,
        )
