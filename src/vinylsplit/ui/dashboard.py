from pathlib import Path
from time import monotonic
from typing import Literal

from rich import box
from rich.align import Align
from rich.console import Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from vinylsplit.ui.console import console
from vinylsplit.ui.progress import ProcessingProgress


class Dashboard:
    """Render a live Rich dashboard for VinylSplit processing."""

    def __init__(
        self,
        progress: ProcessingProgress | None = None,
    ) -> None:
        """Initialize the dashboard.

        Args:
            progress: Existing progress manager to display in the dashboard.
        """
        self._progress = progress or ProcessingProgress()
        self._live: Live | None = None
        self._started_at: float | None = None

        self._album_title = "Unknown Album"
        self._artist = "Unknown Artist"
        self._year = "Unknown"
        self._input_filename = "Not selected"

        self._current_stage = "Waiting"
        self._current_track = "None"
        self._tracks_completed = 0
        self._tracks_total = 0
        self._current_operation = "Idle"

        self._elapsed = "00:00"
        self._eta = "Unknown"
        self._output_directory = "Not selected"
        self._status_kind: Literal["success", "warning", "error", "info"] = "info"
        self._status_message = "Ready"

    def set_album(
        self,
        title: str | None = None,
        artist: str | None = None,
        year: int | str | None = None,
        input_filename: str | Path | None = None,
    ) -> None:
        """Update album metadata displayed by the dashboard.

        Args:
            title: Album title.
            artist: Album artist.
            year: Album release year.
            input_filename: Current source audio filename.
        """
        if title is not None:
            self._album_title = title
        if artist is not None:
            self._artist = artist
        if year is not None:
            self._year = str(year)
        if input_filename is not None:
            self._input_filename = str(input_filename)

        self.refresh()

    def set_progress(self, progress: ProcessingProgress) -> None:
        """Set the progress manager rendered by the dashboard.

        Args:
            progress: Progress manager to display.
        """
        self._progress = progress
        self.refresh()

    def set_stage(
        self,
        stage: str,
        operation: str | None = None,
    ) -> None:
        """Update the current processing stage.

        Args:
            stage: Current user-visible stage.
            operation: Current low-level operation.
        """
        self._current_stage = stage
        if operation is not None:
            self._current_operation = operation

        self.refresh()

    def set_track(
        self,
        current_track: str | None = None,
        completed: int | None = None,
        total: int | None = None,
    ) -> None:
        """Update current track progress details.

        Args:
            current_track: Current track name or number.
            completed: Number of completed tracks.
            total: Total number of tracks.
        """
        if current_track is not None:
            self._current_track = current_track
        if completed is not None:
            self._tracks_completed = completed
        if total is not None:
            self._tracks_total = total

        self.refresh()

    def set_timing(
        self,
        elapsed: str | None = None,
        eta: str | None = None,
    ) -> None:
        """Update timing information.

        Args:
            elapsed: Elapsed time label.
            eta: Estimated remaining time label.
        """
        if elapsed is not None:
            self._elapsed = elapsed
        if eta is not None:
            self._eta = eta

        self.refresh()

    def set_output(self, output_directory: str | Path) -> None:
        """Update the output directory.

        Args:
            output_directory: Destination directory for generated tracks.
        """
        self._output_directory = str(output_directory)
        self.refresh()

    def set_status(
        self,
        message: str,
        kind: Literal["success", "warning", "error", "info"] = "info",
    ) -> None:
        """Update the dashboard status message.

        Args:
            message: Status text to display.
            kind: Status category used for styling.
        """
        self._status_message = message
        self._status_kind = kind
        self.refresh()

    def start(self) -> None:
        """Start live dashboard rendering."""
        if self._live is not None:
            return

        self._started_at = monotonic()
        self._ensure_progress_tasks()
        self._live = Live(
            self._layout(),
            console=console,
            refresh_per_second=20,
            screen=True,
        )
        self._live.start()

    def stop(self) -> None:
        """Stop live dashboard rendering."""
        if self._live is None:
            return

        self._live.stop()
        self._live = None

    def refresh(self) -> None:
        """Refresh the live dashboard renderable."""
        self._update_elapsed_time()
        if self._live is not None:
            self._live.update(self._layout())

    def _layout(self) -> Layout:
        """Build the dashboard layout."""
        root = Layout(name="root")
        root.split_column(
            Layout(self._header(), name="header", size=4),
            Layout(name="main", size=20),
            Layout(self._footer(), name="footer", size=3),
        )

        root["main"].split_row(
            Layout(self._summary_panel(), name="summary", ratio=2),
            Layout(self._progress_panel(), name="progress", ratio=3),
        )

        return root

    def _header(self) -> Panel:
        """Build the header panel."""
        title = Text("VINYLSPLIT", style="title", justify="center")
        subtitle = Text(
            "Splitting, identifying, and organizing your vinyl",
            style="dim",
            justify="center",
        )
        return Panel(
            Align.center(Group(title, subtitle), vertical="middle"),
            box=box.SIMPLE,
            border_style="accent",
            padding=(0, 1),
        )

    def _summary_panel(self) -> Panel:
        """Build the compact album, status, and timing summary."""
        table = Table.grid(padding=(0, 1))
        table.add_column(style="dim", no_wrap=True)
        table.add_column(ratio=1, overflow="fold")
        table.add_row("🎵 Album", self._album_title)
        table.add_row("Artist", self._artist)
        table.add_row("Year", self._year)
        table.add_row("📀 Input", self._input_filename)
        table.add_row("", "")
        table.add_row("Stage", self._current_stage)
        table.add_row("Track", self._current_track)
        table.add_row("Done", self._track_count_text())
        table.add_row("Now", self._current_operation)
        table.add_row("", "")
        table.add_row("⏱ Time", self._elapsed)
        table.add_row("ETA", self._eta)
        return Panel(
            table,
            title="Now",
            box=box.SIMPLE,
            border_style="accent",
            padding=(0, 1),
        )

    def _progress_panel(self) -> Panel:
        """Build the progress panel."""
        return Panel(
            self._progress_renderable(),
            title="Progress",
            box=box.SIMPLE,
            border_style="accent",
            padding=(0, 1),
        )

    def _footer(self) -> Panel:
        """Build the footer panel."""
        status = Text.assemble(
            (self._status_icon(), self._status_kind),
            (" ", "dim"),
            (self._status_message, self._status_kind),
        )
        output = Text.assemble(("📁 Output  ", "dim"), self._output_directory)
        return Panel(
            Group(output, status),
            box=box.SIMPLE,
            border_style=self._status_kind,
            padding=(0, 1),
        )

    def _progress_renderable(self) -> RenderableType:
        """Return the existing processing progress renderable."""
        self._ensure_progress_tasks()
        return self._progress._progress.get_renderable()

    def _ensure_progress_tasks(self) -> None:
        """Ensure the progress manager has created its tasks."""
        self._progress._ensure_tasks()

    def _track_count_text(self) -> str:
        """Return the formatted track count."""
        if self._tracks_total == 0:
            return f"{self._tracks_completed} / unknown"

        return f"{self._tracks_completed} / {self._tracks_total}"

    def _status_icon(self) -> str:
        """Return the icon for the current status kind."""
        return {
            "success": "✓",
            "warning": "⚠",
            "error": "✖",
            "info": "⏱",
        }[self._status_kind]

    def _update_elapsed_time(self) -> None:
        """Refresh elapsed time from the dashboard start time."""
        if self._started_at is None:
            return

        elapsed_seconds = int(monotonic() - self._started_at)
        minutes, seconds = divmod(elapsed_seconds, 60)
        hours, minutes = divmod(minutes, 60)

        if hours:
            self._elapsed = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            self._elapsed = f"{minutes:02d}:{seconds:02d}"
