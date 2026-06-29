from dataclasses import dataclass, field

from vinylsplit.boundary_states import BoundaryState


@dataclass(slots=True)
class Boundary:
    """Represents one track boundary in a review session."""

    track_number: int
    start_time: float
    track_title: str | None = None
    expected_boundary: float | None = None
    detected_boundary: float | None = None
    edited_boundary: float | None = None
    detector_confidence: float | None = None
    silence_duration: float | None = None
    detector_score: float | None = None
    reasons: list[str] = field(default_factory=list)
    state: BoundaryState = field(default_factory=lambda: BoundaryState.AUTO)

    # ---------------------------------------------------------------------------
    # Backward-compatible shims — callers that set locked=True or read
    # review_status still work, but new code should use .state directly.
    # ---------------------------------------------------------------------------

    @property
    def locked(self) -> bool:
        """True when this boundary is user-controlled and must not be moved."""
        return self.state.is_user_controlled()

    @locked.setter
    def locked(self, value: bool) -> None:
        if value:
            self.state = BoundaryState.LOCKED
        elif self.state is BoundaryState.LOCKED:
            self.state = BoundaryState.AUTO

    @property
    def review_status(self) -> str:
        """Legacy string review status derived from current state."""
        _map = {
            BoundaryState.AUTO: "automatic",
            BoundaryState.LOCKED: "edited",
            BoundaryState.VERIFIED: "accepted",
            BoundaryState.SUGGESTED: "suggested",
        }
        return _map[self.state]

    @review_status.setter
    def review_status(self, value: str) -> None:
        _map = {
            "automatic": BoundaryState.AUTO,
            "edited": BoundaryState.LOCKED,
            "accepted": BoundaryState.VERIFIED,
            "suggested": BoundaryState.SUGGESTED,
        }
        self.state = _map.get(value, BoundaryState.AUTO)

    def __post_init__(self) -> None:
        if self.detected_boundary is None:
            self.detected_boundary = self.start_time

    @property
    def selected_boundary(self) -> float:
        """Return the boundary time currently used for export."""

        if self.edited_boundary is not None:
            return self.edited_boundary

        return self.start_time

    @property
    def index(self) -> int:
        """Compatibility alias for the boundary index."""

        return self.track_number

    @property
    def timestamp(self) -> float:
        """Compatibility alias for the boundary timestamp."""

        return self.start_time

    @property
    def confidence(self) -> float:
        """Return normalized confidence value for review and validation."""

        if self.detector_confidence is None:
            return 1.0

        return self.detector_confidence

    def move_to(self, new_time: float) -> None:
        """Update the boundary after a user edit and lock it."""

        self.start_time = new_time
        self.edited_boundary = new_time
        self.state = BoundaryState.LOCKED

    def accept(self) -> None:
        """Mark the boundary as user-verified."""

        self.state = BoundaryState.VERIFIED


@dataclass(slots=True)
class ReviewSession:
    """Own the editable boundaries for a processed album."""

    source_file: str
    boundaries: list[Boundary]
    selected_boundary_index: int = 0
    album_artist: str | None = None
    album_title: str | None = None
    album_year: str | None = None
    release_id: str | None = None
    track_titles: list[str] = field(default_factory=list)
    completed: bool = False

    @property
    def selected_boundary(self) -> Boundary | None:
        """Return the currently selected boundary, if any."""

        if not self.boundaries:
            return None

        if self.selected_boundary_index < 0:
            return None

        if self.selected_boundary_index >= len(self.boundaries):
            return None

        return self.boundaries[self.selected_boundary_index]

    def select_boundary(self, index: int) -> Boundary:
        """Select a boundary by index."""

        if index < 0 or index >= len(self.boundaries):
            raise IndexError(index)

        self.selected_boundary_index = index
        return self.boundaries[index]

    def move_boundary(self, index: int, new_time: float) -> Boundary:
        """Move a boundary and lock it."""

        boundary = self.boundaries[index]
        if boundary.locked:
            raise ValueError("Cannot move a locked boundary")
        boundary.move_to(new_time)
        self.selected_boundary_index = index
        return boundary

    def accept_boundary(self, index: int) -> Boundary:
        """Accept a boundary."""

        boundary = self.boundaries[index]
        boundary.accept()
        self.selected_boundary_index = index
        return boundary

    def accept_remaining(self) -> None:
        """Accept all remaining boundaries."""

        for boundary in self.boundaries:
            if boundary.state not in {BoundaryState.VERIFIED, BoundaryState.LOCKED}:
                boundary.accept()

        self.completed = True

    def next_low_confidence(self, threshold: float = 0.6) -> Boundary | None:
        """Return the next low-confidence boundary after the current selection."""

        for index in range(self.selected_boundary_index + 1, len(self.boundaries)):
            boundary = self.boundaries[index]
            if boundary.detector_confidence is not None and boundary.detector_confidence < threshold:
                self.selected_boundary_index = index
                return boundary

        return None

    def edited_boundaries(self) -> list[Boundary]:
        """Return boundaries the user has manually positioned."""

        return [boundary for boundary in self.boundaries if boundary.state is BoundaryState.LOCKED]

    def normalize_track_numbers(self) -> None:
        """Normalize track numbers to reflect sorted boundary order."""

        self.boundaries.sort(key=lambda boundary: boundary.start_time)

        for number, boundary in enumerate(self.boundaries, start=1):
            boundary.track_number = number


@dataclass
class AudioInfo:
    """Information about an audio file."""

    filename: str
    codec: str
    sample_rate: int
    channels: int
    duration: float
    bits_per_sample: int | None
    file_size: int
    tags: dict[str, list[str]]
