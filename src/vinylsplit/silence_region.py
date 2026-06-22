from dataclasses import dataclass


@dataclass(slots=True)
class SilenceRegion:
    """Represents one detected silence region."""

    start_window: int
    end_window: int

    start_time: float
    end_time: float

    duration: float

    minimum_rms: float
    average_rms: float