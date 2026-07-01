from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WorkspaceViewState:
    """Shared presentation state preserved across workspace switches."""

    recording_path: str | None = None
    recording_info: str = "No recording selected"
    album_artist: str = "Unknown Artist"
    album_title: str = "Unknown Album"
    analysis_state: str = "Not started"
    review_state: str = "Not requested"
    status_message: str = "Drop a recording to begin."
    progress_value: int = 0
    progress_label: str = "Idle"
    track_list: tuple[str, ...] = field(default_factory=tuple)
    recent_projects: tuple[str, ...] = field(default_factory=tuple)
    active_workspace: str = "focused"
