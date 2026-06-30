from __future__ import annotations

from abc import ABC, abstractmethod


class PlaybackProvider(ABC):
    """Abstract playback extension contract for Studio workspace integration."""

    @abstractmethod
    def play(self) -> None:
        """Start playback."""

    @abstractmethod
    def pause(self) -> None:
        """Pause playback."""

    @abstractmethod
    def stop(self) -> None:
        """Stop playback."""

    @abstractmethod
    def seek(self, seconds: float) -> None:
        """Seek playback cursor to a timestamp."""

    @abstractmethod
    def play_region(self, start: float, end: float) -> None:
        """Play a time region once."""

    @abstractmethod
    def loop_region(self, start: float, end: float) -> None:
        """Loop a time region until stopped."""
