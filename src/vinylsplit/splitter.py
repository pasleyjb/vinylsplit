from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from vinylsplit.detection import TrackBoundary


@dataclass
class SplitTrack:
    """Represents an exported track."""

    track_number: int
    path: Path
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
        Split an audio recording into separate FLAC files.

        Audio quality is preserved because samples are copied directly
        from the original recording.
        """

        source = Path(filename)

        if not source.exists():
            raise FileNotFoundError(source)

        output = Path(output_directory)
        output.mkdir(parents=True, exist_ok=True)

        audio, samplerate = sf.read(
            str(source),
            always_2d=False,
        )

        total_samples = len(audio)
        duration = total_samples / samplerate

        tracks: list[SplitTrack] = []

        for index, boundary in enumerate(boundaries):

            start_time = boundary.start_time

            if index + 1 < len(boundaries):
                end_time = boundaries[index + 1].start_time
            else:
                end_time = duration

            start_sample = max(
                0,
                int(round(start_time * samplerate)),
            )

            end_sample = min(
                total_samples,
                int(round(end_time * samplerate)),
            )

            if end_sample <= start_sample:
                continue

            track_audio = audio[start_sample:end_sample]

            output_path = (
                output /
                f"{boundary.track_number:02d} Track.flac"
            )

            sf.write(
                file=str(output_path),
                data=track_audio,
                samplerate=samplerate,
                format="FLAC",
            )

            tracks.append(
                SplitTrack(
                    track_number=boundary.track_number,
                    path=output_path,
                    start_time=start_time,
                    end_time=end_time,
                )
            )

        return tracks