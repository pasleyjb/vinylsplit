"""Interactive track review workflow.

``ReviewSession`` is a thin interaction layer.  All business logic lives in:

- ``AdaptiveReviewState``  — boundary mutations, undo/redo, suggestions
- ``BoundaryValidator``    — validation rules and warnings
- ``LocalAnalyzer``        — post-edit local reanalysis
- ``BoundaryCommandParser``— raw text → structured command

``ReviewSession`` is responsible only for:

- reading user input
- calling the appropriate state method
- rendering the updated review to the terminal
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from vinylsplit.adaptive_analysis import LocalAnalyzer, RefinementSummary
from vinylsplit.boundary_states import BoundaryState
from vinylsplit.boundary_validation import BoundaryValidationResult, BoundaryValidator
from vinylsplit.formatting import format_duration
from vinylsplit.review_state import AdaptiveReviewState
from vinylsplit.timestamps import parse_timestamp
from vinylsplit.ui.console import console


class ReviewCancelledError(Exception):
    """Raised when the user cancels track review."""


@dataclass(slots=True)
class CommandAction:
    """Structured command output from the parser."""

    name: str
    args: list[str]


class BoundaryCommandParser:
    """Parse raw command input for review actions."""

    SUPPORTED = {
        "split", "accept", "cancel", "edit", "delete", "add",
        "list", "help", "undo", "redo", "verify", "refine",
    }
    ALIASES = {
        "quit": "cancel",
        "exit": "cancel",
        "q": "cancel",
        "apply": "verify",
    }

    def parse(self, raw_command: str) -> CommandAction:
        """Parse a command string into a command action."""

        command = raw_command.strip()
        if not command:
            raise ValueError("Command cannot be empty.")

        parts = command.split()
        name = parts[0].lower()
        name = self.ALIASES.get(name, name)
        args = parts[1:]

        if name not in self.SUPPORTED:
            raise ValueError(f"Unsupported command: {name!r}")

        if name == "accept":
            name = "split"

        return CommandAction(name=name, args=args)


class ReviewSession:
    """Interactive Rich-based adaptive review workflow.

    Parameters
    ----------
    state:
        The adaptive session state to mutate.
    validator:
        Boundary validation rules.
    duration_seconds:
        Total duration of the source recording.
    expected_track_count:
        Number of tracks expected from album metadata (optional).
    analyzer:
        Local reanalysis engine (optional).  When ``None`` local reanalysis
        is skipped after edits and no suggestions are generated.
    input_func:
        Override for terminal input; used in tests.
    """

    def __init__(
        self,
        state: AdaptiveReviewState,
        validator: BoundaryValidator,
        duration_seconds: float,
        expected_track_count: int | None = None,
        analyzer: LocalAnalyzer | None = None,
        input_func: Callable[[str], str] | None = None,
    ) -> None:
        self._state = state
        self._validator = validator
        self._duration = duration_seconds
        self._expected_track_count = expected_track_count
        self._analyzer = analyzer
        self._input_func = input_func
        self._parser = BoundaryCommandParser()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> list:
        """Run the interactive review loop and return approved boundaries."""

        self._render()

        while True:
            command_text = self._prompt()

            try:
                action = self._parser.parse(command_text)
                result = self._dispatch(action)
            except KeyboardInterrupt as exc:
                self._on_cancel()
                raise ReviewCancelledError("Review cancelled by user.") from exc
            except Exception as exc:
                console.print(f"[warning]{exc}[/warning]")
                continue

            if result == "split":
                self._state.accept_all()
                console.print("[success]✓ Review accepted. Starting export…[/success]")
                return self._state.boundaries

            if result == "cancel":
                self._on_cancel()
                raise ReviewCancelledError("Review cancelled by user.")

    # ------------------------------------------------------------------
    # Input / prompt
    # ------------------------------------------------------------------

    def _prompt(self) -> str:
        if self._input_func is not None:
            return self._input_func("Track Review > ")

        return console.input("[accent]Track Review >[/accent] ")

    # ------------------------------------------------------------------
    # Command dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self, action: CommandAction) -> str | None:
        handlers: dict[str, Callable] = {
            "help":   self._cmd_help,
            "list":   self._cmd_list,
            "split":  self._cmd_split,
            "cancel": self._cmd_cancel,
            "edit":   self._cmd_edit,
            "delete": self._cmd_delete,
            "add":    self._cmd_add,
            "undo":   self._cmd_undo,
            "redo":   self._cmd_redo,
            "verify": self._cmd_verify,
            "refine": self._cmd_refine,
        }
        handler = handlers.get(action.name)
        if handler is None:
            raise ValueError(f"Unsupported command: {action.name!r}")
        return handler(action.args)

    # ------------------------------------------------------------------
    # Command implementations
    # ------------------------------------------------------------------

    def _cmd_help(self, _args: list[str]) -> None:
        self._render_commands_panel()

    def _cmd_list(self, _args: list[str]) -> None:
        self._render()

    def _cmd_split(self, _args: list[str]) -> str:
        return "split"

    def _cmd_cancel(self, _args: list[str]) -> str:
        return "cancel"

    def _cmd_edit(self, args: list[str]) -> None:
        if len(args) != 3:
            raise ValueError("Usage: edit <track> start|end <timestamp>")

        track_number = _parse_track_number(args[0])
        edge = _parse_edge(args[1])
        timestamp = parse_timestamp(args[2])

        boundaries = self._state.sorted_boundaries()
        if track_number < 1 or track_number > len(boundaries):
            raise ValueError(f"Track {track_number} does not exist.")

        if edge == "start":
            target_track = track_number
        else:
            if track_number >= len(boundaries):
                raise ValueError("The final track end is at EOF and cannot be moved.")
            target_track = track_number + 1

        self._validate_position(target_track, timestamp)

        def _mutate(state: AdaptiveReviewState) -> None:
            state.move_boundary(target_track, timestamp)

        self._state.apply_edit(_mutate)

        mm = int(timestamp // 60)
        ss = timestamp % 60
        label = "begins at" if edge == "start" else "ends at"
        console.print(
            f"[success]✓ Track {track_number} now {label} "
            f"{mm:02d}:{ss:06.3f}.[/success]"
        )

        self._after_edit(target_track)
        self._render()

    def _cmd_delete(self, args: list[str]) -> None:
        if len(args) != 1:
            raise ValueError("Usage: delete <track>")

        track_number = _parse_track_number(args[0])
        boundaries = self._state.sorted_boundaries()

        if track_number < 1 or track_number > len(boundaries):
            raise ValueError(f"Track {track_number} does not exist.")

        target = self._state.boundary_for_track(track_number)
        if target and target.start_time == 0.0:
            raise ValueError("Cannot delete the recording start marker.")

        def _mutate(state: AdaptiveReviewState) -> None:
            state.remove_boundary(track_number)

        self._state.apply_edit(_mutate)
        console.print(f"[success]✓ Track {track_number} removed.[/success]")
        self._render()

    def _cmd_add(self, args: list[str]) -> None:
        if len(args) != 1:
            raise ValueError("Usage: add <timestamp>")

        timestamp = parse_timestamp(args[0])
        self._validate_new_timestamp(timestamp)

        def _mutate(state: AdaptiveReviewState) -> None:
            state.add_boundary(timestamp)

        self._state.apply_edit(_mutate)

        mm = int(timestamp // 60)
        ss = timestamp % 60
        console.print(f"[success]✓ Track added at {mm:02d}:{ss:06.3f}.[/success]")
        self._render()

    def _cmd_undo(self, _args: list[str] | None = None) -> None:
        if self._state.undo():
            console.print("[success]✓ Undo complete.[/success]")
        else:
            console.print("[warning]Nothing to undo.[/warning]")
        self._render()

    def _cmd_redo(self, _args: list[str] | None = None) -> None:
        if self._state.redo():
            console.print("[success]✓ Redo complete.[/success]")
        else:
            console.print("[warning]Nothing to redo.[/warning]")
        self._render()

    def _cmd_verify(self, args: list[str]) -> None:
        if len(args) != 1:
            raise ValueError("Usage: verify <track>")

        track_number = _parse_track_number(args[0])

        suggestion = self._state._find_suggestion(track_number)
        if suggestion is not None:
            applied = self._state.apply_suggestion(track_number)
            if applied:
                mm = int(applied.suggested_position // 60)
                ss = applied.suggested_position % 60
                console.print(
                    f"[success]✓ Suggestion applied: Track {track_number} "
                    f"moved to {mm:02d}:{ss:06.3f}.[/success]"
                )
        else:
            def _mutate(state: AdaptiveReviewState) -> None:
                state.verify_boundary(track_number)

            self._state.apply_edit(_mutate)
            console.print(f"[success]✓ Track {track_number} verified.[/success]")

        self._render()

    def _cmd_refine(self, args: list[str]) -> None:
        if args:
            raise ValueError("Usage: refine")

        if self._analyzer is None:
            console.print("[warning]Refinement unavailable for this session.[/warning]")
            self._render()
            return

        summary = RefinementSummary(anchors=0, regions_analyzed=0, boundaries_improved=0)

        def _mutate(state: AdaptiveReviewState) -> None:
            nonlocal summary
            summary = self._analyzer.refine_boundaries(
                state=state,
                duration_seconds=self._duration,
                minimum_spacing_seconds=self._validator.config.minimum_spacing_seconds,
            )

        self._state.apply_edit(_mutate)

        validation = self._validation()
        summary.validation_warnings = len(validation.warnings)

        lines = [
            "[success]Refinement Complete[/success]",
            "",
            f"Anchors: {summary.anchors}",
            f"Regions analyzed: {summary.regions_analyzed}",
            f"Boundaries improved: {summary.boundaries_improved}",
            f"Validation warnings: {summary.validation_warnings}",
        ]
        console.print(Panel("\n".join(lines), title="Refinement", border_style="accent"))

        self._render()

    # ------------------------------------------------------------------
    # Post-edit reanalysis
    # ------------------------------------------------------------------

    def _after_edit(self, edited_track_number: int) -> None:
        """Run local reanalysis after an edit and update suggestions."""
        if self._analyzer is None:
            return

        try:
            suggestions = self._analyzer.analyze_neighborhood(
                self._state, edited_track_number
            )
            self._state.set_suggestions(suggestions)
        except Exception:
            self._state.clear_suggestions()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        validation = self._validation()

        self._render_header(validation)

        if validation.warnings:
            warning_text = "\n".join(f"- {w.message}" for w in validation.warnings)
            console.print(Panel(warning_text, title="Validation Warnings", border_style="warning"))

        self._render_track_table()

        if self._state.has_suggestions():
            self._render_suggestions_panel()

        self._render_commands_panel()

    def _render_header(self, validation: BoundaryValidationResult) -> None:
        album = self._state.album_title or "Unknown Album"
        artist = self._state.album_artist or "Unknown Artist"

        summary_lines = [
            f"[header]Album[/header]: {album}",
            f"[header]Artist[/header]: {artist}",
            f"[header]Expected tracks[/header]: {validation.expected_track_count or 'Unknown'}",
            f"[header]Detected tracks[/header]: {validation.detected_track_count}",
            f"[header]Overall confidence[/header]: {validation.overall_confidence * 100:.0f}%",
        ]

        console.print(Rule("Track Review"))
        console.print(Panel("\n".join(summary_lines), title="Review Summary", border_style="accent"))

        warning_count = len(validation.warnings)
        suggestion_count = len(self._state.suggestions)
        status_lines = [
            "[success]✓ Album identified[/success]"
            if self._state.album_title
            else "[warning]⚠ Album not identified[/warning]",

            "[success]✓ Metadata loaded[/success]"
            if self._state.track_titles
            else "[warning]⚠ Metadata not loaded[/warning]",

            f"[success]✓ {validation.detected_track_count} tracks[/success]",

            (
                f"[warning]⚠ {warning_count} validation warning{'s' if warning_count != 1 else ''}[/warning]"
                if warning_count
                else "[success]✓ No validation warnings[/success]"
            ),

            (
                f"[warning]⚠ {suggestion_count} suggestion{'s' if suggestion_count != 1 else ''} available[/warning]"
                if suggestion_count
                else "[dim]No suggestions[/dim]"
            ),

            "",
            "[header]Next step:[/header]",
            'Type "split" when ready to export, or "help" for commands.',
        ]
        console.print(Panel("\n".join(status_lines), title="Review Status", border_style="accent"))

    def _render_track_table(self) -> None:
        table = Table(title="Detected Tracks")
        table.add_column("Track", justify="right")
        table.add_column("Title", justify="left", no_wrap=True, overflow="ellipsis", max_width=34)
        table.add_column("Start", justify="right")
        table.add_column("End", justify="right")
        table.add_column("Length", justify="right")
        table.add_column("Status", justify="left")

        sorted_b = self._state.sorted_boundaries()

        for index, boundary in enumerate(sorted_b):
            start = boundary.start_time

            if index + 1 < len(sorted_b):
                end = sorted_b[index + 1].start_time
                end_text = format_duration(end)
                length_text = format_duration(max(0.0, end - start))
            else:
                end = self._duration
                end_text = "EOF"
                length_text = format_duration(max(0.0, end - start))

            status_text = boundary.state.display_label(boundary.detector_confidence)

            if boundary.state is BoundaryState.LOCKED:
                status_cell = Text(status_text, style="bold yellow")
            elif boundary.state is BoundaryState.VERIFIED:
                status_cell = Text(status_text, style="bold green")
            else:
                status_cell = Text(status_text, style="dim")

            table.add_row(
                str(boundary.track_number),
                self._display_track_title(boundary.track_number, boundary.track_title),
                format_duration(start),
                end_text,
                length_text,
                status_cell,
            )

        console.print(table)

    def _render_suggestions_panel(self) -> None:
        lines: list[str] = []
        for s in self._state.suggestions:
            mm = int(s.suggested_position // 60)
            ss = s.suggested_position % 60
            lines.append(
                f"Track {s.track_number}: stronger transition at {mm:02d}:{ss:06.3f} "
                f"({s.distance_ms:.0f} ms away)\n"
                f"  {s.reason}\n"
                f'  Type "verify {s.track_number}" to apply, or continue editing.'
            )
        console.print(
            Panel("\n\n".join(lines), title="Suggested Improvements", border_style="warning")
        )

    def _render_commands_panel(self) -> None:
        content = (
            "split / accept\n"
            "    Approve the review and begin export.\n\n"
            "cancel / quit / exit / q\n"
            "    Exit without writing files.\n\n"
            "edit <track> start <time>\n"
            "    Move the start of a track.  Locks the boundary.\n\n"
            "edit <track> end <time>\n"
            "    Move the end of a track.  Locks the next boundary.\n\n"
            "verify <track>\n"
            "    Mark a boundary as verified, or apply a pending suggestion.\n\n"
            "refine\n"
            "    Improve AUTO boundaries using locked anchors.\n\n"
            "add <time>\n"
            "    Insert a track at the given time.\n\n"
            "delete <track>\n"
            "    Remove a track.\n\n"
            "undo\n"
            "    Undo the last edit.\n\n"
            "redo\n"
            "    Redo the last undone edit.\n\n"
            "list\n"
            "    Redisplay the review.\n\n"
            "help\n"
            "    Show this command reference."
        )
        console.print(Panel(content, title="Available Commands", border_style="accent"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validation(self) -> BoundaryValidationResult:
        return self._validator.validate(
            boundaries=self._state.boundaries,
            duration_seconds=self._duration,
            expected_track_count=self._expected_track_count,
        )

    def _display_track_title(self, track_number: int, boundary_title: str | None) -> str:
        """Resolve the title displayed in the review table for a track."""

        if boundary_title and boundary_title.strip():
            return boundary_title.strip()

        index = track_number - 1
        if 0 <= index < len(self._state.track_titles):
            title = self._state.track_titles[index]
            if title and title.strip():
                return title.strip()

        return "<Unknown>"

    def _validate_new_timestamp(self, timestamp: float) -> None:
        if timestamp <= 0.0:
            raise ValueError("Timestamp must be greater than 0.")
        if timestamp >= self._duration:
            raise ValueError("Timestamp must be inside the recording duration.")
        for b in self._state.boundaries:
            if abs(b.start_time - timestamp) < 0.001:
                raise ValueError("A track already starts at that time.")

    def _validate_position(self, target_track: int, timestamp: float) -> None:
        self._validate_new_timestamp(timestamp)

        sorted_b = self._state.sorted_boundaries()
        idx = next(
            (i for i, b in enumerate(sorted_b) if b.track_number == target_track),
            None,
        )
        if idx is None:
            return

        if idx > 0 and timestamp <= sorted_b[idx - 1].start_time:
            raise ValueError("Timestamp must remain after the previous track start.")

        if idx + 1 < len(sorted_b) and timestamp >= sorted_b[idx + 1].start_time:
            raise ValueError("Timestamp must remain before the next track start.")

    def _on_cancel(self) -> None:
        console.print("[success]✓ Review cancelled.[/success]")
        console.print("[warning]No files were written.[/warning]")


# ---------------------------------------------------------------------------
# Module-level helpers (shared with tests)
# ---------------------------------------------------------------------------

def _parse_track_number(text: str) -> int:
    try:
        n = int(text)
    except ValueError as exc:
        raise ValueError(f'Invalid track number: "{text}"') from exc
    if n < 1:
        raise ValueError("Track number must be at least 1.")
    return n


def _parse_edge(text: str) -> str:
    edge = text.strip().lower()
    if edge not in {"start", "end"}:
        raise ValueError('Edit target must be "start" or "end".')
    return edge
