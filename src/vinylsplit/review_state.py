"""Adaptive review session state model.

``AdaptiveReviewState`` is the single source of truth for the review workflow.
It is designed to be serializable and supports immutable snapshots for
undo/redo without custom reverse logic.

Architecture
------------
- Boundaries are stored as a list; ordering is maintained by sort on
  ``start_time`` after every mutation.
- ``Suggestion`` objects are informational only; they never modify boundaries.
- The undo/redo stacks store complete frozen snapshots of the boundary list
  so that undo always restores the exact prior state, including states,
  confidence values, and reasons.
- Business logic (local reanalysis, validation) lives in separate modules.
  This class only stores and mutates state.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from vinylsplit.boundary_states import BoundaryState
from vinylsplit.models import Boundary
from vinylsplit.suggestions import Suggestion


@dataclass
class AdaptiveReviewState:
    """Mutable session state for the adaptive review workflow.

    Parameters
    ----------
    source_file:
        Path to the source audio file.
    boundaries:
        Current boundary list.  Always sorted by ``start_time``.
    suggestions:
        Current improvement suggestions.  Replaced after each local
        reanalysis.  Suggestions are never applied automatically.
    album_artist, album_title, album_year, release_id, track_titles:
        Album metadata used for display.

    Notes
    -----
    The undo/redo stacks are not included in the constructor signature to
    keep construction simple. They are populated automatically by
    ``apply_edit()``.
    """

    source_file: str
    boundaries: list[Boundary]
    suggestions: list[Suggestion] = field(default_factory=list)
    album_artist: str | None = None
    album_title: str | None = None
    album_year: str | None = None
    release_id: str | None = None
    track_titles: list[str] = field(default_factory=list)
    expected_track_durations_seconds: list[float] = field(default_factory=list)
    completed: bool = False

    # Internal undo/redo stacks.  Each entry is a frozen snapshot of the
    # boundary list taken immediately BEFORE the corresponding edit.
    _undo_stack: list[list[Boundary]] = field(default_factory=list, repr=False)
    _redo_stack: list[list[Boundary]] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def _snapshot(self) -> list[Boundary]:
        """Return a deep copy of the current boundary list."""
        return copy.deepcopy(self.boundaries)

    def _restore(self, snapshot: list[Boundary]) -> None:
        """Replace the current boundary list with a snapshot."""
        self.boundaries = copy.deepcopy(snapshot)
        self._normalize()

    # ------------------------------------------------------------------
    # Edit primitives (all edits go through apply_edit so stacks stay in sync)
    # ------------------------------------------------------------------

    def apply_edit(self, mutate_fn: "Callable[[AdaptiveReviewState], None]") -> None:
        """Apply a mutation function and save an undo snapshot.

        Parameters
        ----------
        mutate_fn:
            A callable that receives *this* state and performs mutations.
            It must not modify ``_undo_stack`` or ``_redo_stack``.
        """
        snapshot = self._snapshot()
        mutate_fn(self)
        self._normalize()
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Restore the previous boundary state.

        Returns True if an undo was available, False otherwise.
        """
        if not self._undo_stack:
            return False

        redo_snapshot = self._snapshot()
        snapshot = self._undo_stack.pop()
        self._restore(snapshot)
        self._redo_stack.append(redo_snapshot)
        return True

    def redo(self) -> bool:
        """Re-apply the most recently undone edit.

        Returns True if a redo was available, False otherwise.
        """
        if not self._redo_stack:
            return False

        undo_snapshot = self._snapshot()
        snapshot = self._redo_stack.pop()
        self._restore(snapshot)
        self._undo_stack.append(undo_snapshot)
        return True

    # ------------------------------------------------------------------
    # Boundary mutations (called from within mutate_fn)
    # ------------------------------------------------------------------

    def move_boundary(self, track_number: int, new_time: float) -> Boundary:
        """Move a boundary start time and lock it.

        Raises
        ------
        ValueError
            If the track does not exist or the boundary is already VERIFIED.
        """
        boundary = self._find_boundary(track_number)
        if boundary.state is BoundaryState.VERIFIED:
            raise ValueError(
                f"Track {track_number} is verified and cannot be moved. "
                "Use 'delete' and 're-add' if you need to change it."
            )
        boundary.start_time = new_time
        boundary.edited_boundary = new_time
        boundary.state = BoundaryState.LOCKED
        return boundary

    def add_boundary(
        self, start_time: float, reasons: list[str] | None = None
    ) -> Boundary:
        """Insert a new manually-placed boundary."""
        next_number = len(self.boundaries) + 1
        boundary = Boundary(
            track_number=next_number,
            start_time=start_time,
            reasons=reasons or ["Manually inserted"],
            state=BoundaryState.LOCKED,
        )
        self.boundaries.append(boundary)
        return boundary

    def remove_boundary(self, track_number: int) -> Boundary:
        """Remove a boundary by track number.

        Raises
        ------
        ValueError
            If the boundary is the first track (locked start) or VERIFIED.
        """
        boundary = self._find_boundary(track_number)
        if boundary.state is BoundaryState.VERIFIED:
            raise ValueError(
                f"Track {track_number} is verified. Unverify it before deleting."
            )
        self.boundaries.remove(boundary)
        return boundary

    def verify_boundary(self, track_number: int) -> Boundary:
        """Explicitly verify (accept) a boundary."""
        boundary = self._find_boundary(track_number)
        boundary.state = BoundaryState.VERIFIED
        return boundary

    def accept_all(self) -> None:
        """Mark all non-LOCKED boundaries as VERIFIED and close the session."""
        for boundary in self.boundaries:
            if boundary.state not in {BoundaryState.LOCKED, BoundaryState.VERIFIED}:
                boundary.state = BoundaryState.VERIFIED
        self.completed = True

    # ------------------------------------------------------------------
    # Suggestion management
    # ------------------------------------------------------------------

    def set_suggestions(self, suggestions: list[Suggestion]) -> None:
        """Replace the current suggestion list (called after local reanalysis)."""
        self.suggestions = suggestions

    def clear_suggestions(self) -> None:
        """Remove all current suggestions."""
        self.suggestions = []

    def apply_suggestion(self, track_number: int) -> Suggestion | None:
        """Apply a suggestion for the given track.

        The suggestion is applied as a regular edit (snapshotted for undo).

        Returns the applied suggestion, or None if no suggestion exists
        for that track.
        """
        suggestion = self._find_suggestion(track_number)
        if suggestion is None:
            return None

        def _apply(state: AdaptiveReviewState) -> None:
            boundary = state._find_boundary(suggestion.track_number)
            boundary.start_time = suggestion.suggested_position
            boundary.edited_boundary = suggestion.suggested_position
            boundary.state = BoundaryState.LOCKED

        self.apply_edit(_apply)
        # Remove the applied suggestion.
        self.suggestions = [s for s in self.suggestions if s.track_number != track_number]
        return suggestion

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def boundary_for_track(self, track_number: int) -> Boundary | None:
        """Return the boundary for a track number, or None."""
        for boundary in self.boundaries:
            if boundary.track_number == track_number:
                return boundary
        return None

    def sorted_boundaries(self) -> list[Boundary]:
        """Return boundaries sorted by start_time."""
        return sorted(self.boundaries, key=lambda b: b.start_time)

    def has_suggestions(self) -> bool:
        """Return True when there are pending suggestions."""
        return bool(self.suggestions)

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @classmethod
    def from_review_session(
        cls,
        review_session: "vinylsplit.models.ReviewSession",  # type: ignore[name-defined]
    ) -> "AdaptiveReviewState":
        """Construct an ``AdaptiveReviewState`` from an existing ``ReviewSession``."""
        return cls(
            source_file=review_session.source_file,
            boundaries=copy.deepcopy(review_session.boundaries),
            album_artist=review_session.album_artist,
            album_title=review_session.album_title,
            album_year=review_session.album_year,
            release_id=review_session.release_id,
            track_titles=list(review_session.track_titles),
            expected_track_durations_seconds=list(
                getattr(review_session, "expected_track_durations_seconds", [])
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_boundary(self, track_number: int) -> Boundary:
        boundary = self.boundary_for_track(track_number)
        if boundary is None:
            raise ValueError(f"Track {track_number} does not exist.")
        return boundary

    def _find_suggestion(self, track_number: int) -> Suggestion | None:
        for suggestion in self.suggestions:
            if suggestion.track_number == track_number:
                return suggestion
        return None

    def _normalize(self) -> None:
        """Sort boundaries and renumber them."""
        self.boundaries.sort(key=lambda b: b.start_time)
        for number, boundary in enumerate(self.boundaries, start=1):
            boundary.track_number = number


# Keep the Callable import accessible without forcing it into the main namespace.
from typing import Callable  # noqa: E402  (local import for annotation only)
