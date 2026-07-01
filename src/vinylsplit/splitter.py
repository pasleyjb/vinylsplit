from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import soundfile as sf

from vinylsplit.models import Boundary


@dataclass
class SplitTrack:
    """Represents an exported track."""

    track_number: int
    path: Path
    start_time: float
    end_time: float


class TrackSplitter:
    """Split a recording into individual tracks."""

    _FORMAT_MAP = {
        "flac": ("FLAC", ".flac"),
        "wav": ("WAV", ".wav"),
        "mp3": ("MP3", ".mp3"),
    }

    def split(
        self,
        filename: str,
        boundaries: list[Boundary],
        output_directory: str,
        output_format: str = "flac",
        total_callback: Callable[[int], None] | None = None,
        track_callback: Callable[[SplitTrack], None] | None = None,
    ) -> list[SplitTrack]:
        """
        Split an audio recording into separate files.

        Audio quality is preserved because samples are copied directly
        from the original recording.
        """

        normalized_format = output_format.strip().lower()
        if normalized_format not in self._FORMAT_MAP:
            raise ValueError(f"Unsupported output format: {output_format}")
        writer_format, extension = self._FORMAT_MAP[normalized_format]

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

        pending_tracks: list[SplitTrack] = []

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

            output_path = output / f"{boundary.track_number:02d} Track{extension}"

            pending_tracks.append(
                SplitTrack(
                    track_number=boundary.track_number,
                    path=output_path,
                    start_time=start_time,
                    end_time=end_time,
                )
            )

        if total_callback:
            total_callback(len(pending_tracks))

        tracks: list[SplitTrack] = []

        for track in pending_tracks:
            start_sample = max(
                0,
                int(round(track.start_time * samplerate)),
            )

            end_sample = min(
                total_samples,
                int(round(track.end_time * samplerate)),
            )

            track_audio = audio[start_sample:end_sample]

            sf.write(
                file=str(track.path),
                data=track_audio,
                samplerate=samplerate,
                format=writer_format,
            )

            tracks.append(track)

            if track_callback:
                track_callback(track)

        return tracks
