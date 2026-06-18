from pathlib import Path

import soundfile as sf

from vinylsplit.splitter import SplitTrack


class RetryGenerator:
    """Generate temporary retry tracks for identification."""

    def generate(
        self,
        source_file: str,
        track: SplitTrack,
        offset_seconds: float,
    ) -> Path:
        """
        Create a temporary version of a track using
        an adjusted start time.

        Returns the temporary filename.
        """

        audio, samplerate = sf.read(
            source_file,
            always_2d=False,
        )

        total_samples = len(audio)

        start_time = max(
            0.0,
            track.start_time + offset_seconds,
        )

        end_time = track.end_time

        start_sample = int(round(start_time * samplerate))

        end_sample = min(
            total_samples,
            int(round(end_time * samplerate)),
        )

        temp_audio = audio[start_sample:end_sample]

        temp_file = Path(track.path).parent / f".retry_{track.track_number}.flac"

        sf.write(
            str(temp_file),
            temp_audio,
            samplerate,
            format="FLAC",
        )

        return temp_file
