from __future__ import annotations

from collections.abc import Callable

from vinylsplit.application.dto.export_result import ExportResult
from vinylsplit.application.events import ProgressUpdated
from vinylsplit.application.interfaces.services import ExportServiceInterface
from vinylsplit.review_state import AdaptiveReviewState


class ExportController:
    """Translate presentation requests into export service calls."""

    def __init__(self, export_service: ExportServiceInterface) -> None:
        self._export_service = export_service

    async def export(
        self,
        filename: str,
        output_directory: str,
        artist: str | None = None,
        album: str | None = None,
        review_session: AdaptiveReviewState | None = None,
        progress_callback: Callable[[ProgressUpdated], None] | None = None,
    ) -> ExportResult:
        """Run end-to-end processing for one source recording."""

        return await self._export_service.export(
            filename=filename,
            output_directory=output_directory,
            artist=artist,
            album=album,
            review_session=review_session,
            progress_callback=progress_callback,
        )
