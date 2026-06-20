from dataclasses import dataclass

from vinylsplit.analysis.report import SilenceRegion
from vinylsplit.detection import TrackBoundary


@dataclass(slots=True)
class BoundaryBuilder:
    """
    Convert silence regions into track boundaries.

    Applies several rules to eliminate false positives.
    """

    window_seconds: float

    ignore_start_seconds: float = 5.0
    ignore_end_seconds: float = 5.0
    minimum_track_seconds: float = 60.0

    def build(
        self,
        regions: list[SilenceRegion],
        duration: float,
    ) -> list[TrackBoundary]:

        boundaries = [
            TrackBoundary(
                track_number=1,
                start_time=0.0,
            )
        ]

        last_boundary = 0.0

        for region in regions:
            boundary = region.center_window * self.window_seconds

            #
            # Ignore the needle drop
            #
            if boundary < self.ignore_start_seconds:
                continue

            #
            # Ignore the run-out groove
            #
            if boundary > (duration - self.ignore_end_seconds):
                continue

            #
            # Ignore impossibly short tracks
            #
            if (boundary - last_boundary) < self.minimum_track_seconds:
                continue

            boundaries.append(
                TrackBoundary(
                    track_number=len(boundaries) + 1,
                    start_time=boundary,
                )
            )

            last_boundary = boundary

        return boundaries
