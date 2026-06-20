from collections.abc import Mapping
from types import TracebackType
from typing import Self

from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


class ProcessingProgress:
    """Manage VinylSplit processing progress bars.

    The manager displays four simultaneous Rich progress bars for the main
    processing stages:

    * Overall
    * Analyze Audio
    * Detect Silence
    * Write Tracks
    """

    def __init__(self) -> None:
        """Initialize the progress manager."""
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            expand=True,
            refresh_per_second=20,
        )
        self._task_ids: dict[str, TaskID] = {}

    def __enter__(self) -> Self:
        """Start progress rendering and return this manager."""
        self.start()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        """Stop progress rendering when leaving a context."""
        self.stop()

    def start(self) -> None:
        """Start rendering progress bars."""
        self._ensure_tasks()
        self._progress.start()

    def stop(self) -> None:
        """Stop rendering progress bars."""
        self._progress.stop()

    def advance(self, task_name: str, amount: float) -> None:
        """Advance a named task by an amount.

        Args:
            task_name: Name of the task to advance.
            amount: Amount of progress to add.

        Raises:
            KeyError: If ``task_name`` does not match a managed task.
        """
        self._progress.advance(self._get_task_id(task_name), amount)

    def update(
        self,
        task_name: str,
        completed: float | None = None,
        total: float | None = None,
        description: str | None = None,
    ) -> None:
        """Update a named task.

        Args:
            task_name: Name of the task to update.
            completed: Completed progress value for the task.
            total: Total progress value for the task.
            description: Description to display for the task.

        Raises:
            KeyError: If ``task_name`` does not match a managed task.
        """
        self._progress.update(
            self._get_task_id(task_name),
            completed=completed,
            total=total,
            description=description,
        )

    def _ensure_tasks(self) -> None:
        """Create task bars once before progress starts."""
        if self._task_ids:
            return

        for task_name, description in self._task_descriptions().items():
            self._task_ids[task_name] = self._progress.add_task(
                description,
                total=100,
            )

    def _get_task_id(self, task_name: str) -> TaskID:
        """Return the Rich task ID for a managed task."""
        self._ensure_tasks()

        try:
            return self._task_ids[task_name]
        except KeyError as exc:
            valid_tasks = ", ".join(self._task_descriptions())
            message = (
                f"Unknown progress task '{task_name}'. "
                f"Expected one of: {valid_tasks}."
            )
            raise KeyError(message) from exc

    @staticmethod
    def _task_descriptions() -> Mapping[str, str]:
        """Return task names and their display descriptions."""
        return {
            "overall": "Overall",
            "analyze_audio": "Analyze Audio",
            "detect_silence": "Detect Silence",
            "write_tracks": "Write Tracks",
        }
