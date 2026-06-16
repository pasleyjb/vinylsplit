from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from vinylsplit.detection import TrackBoundary


@dataclass
class SplitTrack:
    """Represents an exported track."""

    filename: str
    start_time: float
    end_time: float


class TrackSplitter:
    """Split a recording into individual tracks."""

    def split(
        self,
        filename: str,
        boundaries: list[TrackBoundary],
        output_directory: str,
    ) -> list[SplitTrack]:
        """
        Split an audio file.

        Version 1:
        Creates the output directory and validates the audio.
        Actual audio splitting will be added next.
        """

        source = Path(filename)

        if not source.exists():
            raise FileNotFoundError(source)

        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)

        info = sf.info(str(source))

        duration = info.frames / info.samplerate

        tracks: list[SplitTrack] = []

        for index, boundary in enumerate(boundaries):

            start = boundary.start_time

            if index + 1 < len(boundaries):
                end = boundaries[index + 1].start_time
            else:
                end = duration

            tracks.append(
                SplitTrack(
                    filename=f"Track {boundary.track_number:02d}.flac",
                    start_time=start,
                    end_time=end,
                )
            )

        return tracks