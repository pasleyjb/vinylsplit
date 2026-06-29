from dataclasses import dataclass, field

from vinylsplit.models import Boundary


@dataclass(slots=True)
class BoundaryValidationConfig:
    """Validation settings for interactive boundary review."""

    minimum_track_seconds: float = 45.0
    maximum_track_seconds: float = 1800.0
    minimum_spacing_seconds: float = 10.0
    low_confidence_threshold: float = 0.60


@dataclass(slots=True)
class ValidationWarning:
    """Represents one boundary or session validation warning."""

    code: str
    message: str
    boundary_index: int | None = None


@dataclass(slots=True)
class BoundaryValidationResult:
    """Validation output for review presentation and approval checks."""

    boundaries: list[Boundary]
    warnings: list[ValidationWarning] = field(default_factory=list)
    expected_track_count: int | None = None
    detected_track_count: int = 0
    average_confidence: float = 1.0
    overall_confidence: float = 1.0


class BoundaryValidator:
    """Validate detected boundaries before user approval."""

    def __init__(self, config: BoundaryValidationConfig | None = None) -> None:
        self.config = config or BoundaryValidationConfig()

    def validate(
        self,
        boundaries: list[Boundary],
        duration_seconds: float,
        expected_track_count: int | None = None,
    ) -> BoundaryValidationResult:
        """Validate boundaries and return a summary with warnings."""

        warnings: list[ValidationWarning] = []
        ordered = sorted(boundaries, key=lambda boundary: boundary.start_time)

        if not ordered:
            warnings.append(
                ValidationWarning(
                    code="missing_start",
                    message="No boundaries detected.",
                )
            )
            return BoundaryValidationResult(
                boundaries=ordered,
                warnings=warnings,
                expected_track_count=expected_track_count,
                detected_track_count=0,
                average_confidence=0.0,
                overall_confidence=0.0,
            )

        if ordered[0].start_time != 0.0:
            warnings.append(
                ValidationWarning(
                    code="missing_start",
                    message=(
                        "Missing track start at 00:00.\n"
                        "The recording should begin with a track at the start of the file."
                    ),
                )
            )

        if ordered[-1].start_time >= duration_seconds:
            warnings.append(
                ValidationWarning(
                    code="missing_end",
                    message=(
                        "The final track end is outside the recording duration.\n"
                        "Adjust or remove it before export."
                    ),
                    boundary_index=ordered[-1].track_number,
                )
            )

        if expected_track_count is not None and len(ordered) != expected_track_count:
            warnings.append(
                ValidationWarning(
                    code="count_mismatch",
                    message=(
                        f"Detected {len(ordered)} tracks, but metadata expects {expected_track_count}.\n"
                        "This can happen with hidden tracks, indexing differences, or incorrect detection."
                    ),
                )
            )

        seen_times: set[float] = set()

        for index, boundary in enumerate(ordered):
            rounded_time = round(boundary.start_time, 3)
            if rounded_time in seen_times:
                warnings.append(
                    ValidationWarning(
                        code="duplicate_boundary",
                        message=(
                                f"Two tracks share {boundary.start_time:.2f} seconds.\n"
                                "Remove or move one track start to keep the album in order."
                        ),
                        boundary_index=boundary.track_number,
                    )
                )
            seen_times.add(rounded_time)

            confidence = boundary.confidence
            if confidence < self.config.low_confidence_threshold:
                warnings.append(
                    ValidationWarning(
                        code="low_confidence",
                        message=(
                            f"Track {boundary.track_number} is low confidence ({confidence * 100:.0f}%).\n"
                            "Review this track before exporting."
                        ),
                        boundary_index=boundary.track_number,
                    )
                )

            if index == 0:
                continue

            previous = ordered[index - 1]
            spacing = boundary.start_time - previous.start_time

            if spacing < self.config.minimum_spacing_seconds:
                warnings.append(
                    ValidationWarning(
                        code="min_spacing",
                        message=(
                            f"Tracks {previous.track_number} and {boundary.track_number} are only {spacing:.2f} seconds apart.\n"
                            f"Configured minimum spacing is {self.config.minimum_spacing_seconds:.2f} seconds."
                        ),
                        boundary_index=boundary.track_number,
                    )
                )

            if spacing < self.config.minimum_track_seconds:
                warnings.append(
                    ValidationWarning(
                        code="track_too_short",
                        message=(
                            f"⚠ Track {previous.track_number} is {spacing:.2f} seconds long.\n"
                            f"This is shorter than the configured minimum of {self.config.minimum_track_seconds:.2f} seconds.\n"
                            "Short tracks are common on some albums. Review if necessary."
                        ),
                        boundary_index=previous.track_number,
                    )
                )

            if spacing > self.config.maximum_track_seconds:
                warnings.append(
                    ValidationWarning(
                        code="track_too_long",
                        message=(
                            f"⚠ Track {previous.track_number} is {spacing:.2f} seconds long.\n"
                            f"This exceeds the configured maximum of {self.config.maximum_track_seconds:.2f} seconds.\n"
                            "Long tracks can be valid on some albums. Review if necessary."
                        ),
                        boundary_index=previous.track_number,
                    )
                )

        confidences = [boundary.confidence for boundary in ordered]
        average_confidence = sum(confidences) / len(confidences)

        penalty = min(0.8, 0.05 * len(warnings))
        overall_confidence = max(0.0, average_confidence - penalty)

        return BoundaryValidationResult(
            boundaries=ordered,
            warnings=warnings,
            expected_track_count=expected_track_count,
            detected_track_count=len(ordered),
            average_confidence=average_confidence,
            overall_confidence=overall_confidence,
        )
