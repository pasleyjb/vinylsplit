from __future__ import annotations

from vinylsplit.application.dto.metadata_result import MetadataResult
from vinylsplit.application.interfaces.services import MetadataServiceInterface
from vinylsplit.pipeline import Pipeline


class MetadataService(MetadataServiceInterface):
    """Application service for metadata lookup workflows."""

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    def lookup(self, filename: str) -> MetadataResult:
        """Lookup metadata using existing pipeline identification behavior."""

        if not filename.strip():
            raise ValueError("filename must not be empty")

        match = self._pipeline.identify(filename)
        return MetadataResult(
            source_file=filename,
            match=match,
            found=match is not None,
        )
