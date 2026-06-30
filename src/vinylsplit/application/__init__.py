from __future__ import annotations

from dataclasses import dataclass

from vinylsplit.application.controllers import AnalyzeController, ExportController, ReviewController
from vinylsplit.application.services import AnalyzeService, ExportService, MetadataService, ReviewService
from vinylsplit.pipeline import Pipeline


@dataclass(frozen=True, slots=True)
class ApplicationContext:
    """Container for application-layer services and controllers."""

    pipeline: Pipeline
    analyze_controller: AnalyzeController
    review_controller: ReviewController
    export_controller: ExportController


def build_application_context(pipeline: Pipeline | None = None) -> ApplicationContext:
    """Build the default application-layer composition graph."""

    bound_pipeline = pipeline or Pipeline()

    analyze_service = AnalyzeService(bound_pipeline)
    metadata_service = MetadataService(bound_pipeline)
    review_service = ReviewService(bound_pipeline)
    export_service = ExportService(bound_pipeline)

    analyze_controller = AnalyzeController(
        analyze_service=analyze_service,
        metadata_service=metadata_service,
    )
    review_controller = ReviewController(review_service=review_service)
    export_controller = ExportController(export_service=export_service)

    return ApplicationContext(
        pipeline=bound_pipeline,
        analyze_controller=analyze_controller,
        review_controller=review_controller,
        export_controller=export_controller,
    )


__all__ = [
    "ApplicationContext",
    "build_application_context",
]
