from pathlib import Path

from vinylsplit.lookup import AlbumLookup, AlbumMatch
from vinylsplit.retry_generator import RetryGenerator
from vinylsplit.splitter import SplitTrack


class SmartIdentifier:
    """Attempts multiple strategies to identify a track."""

    def __init__(self) -> None:
        self.lookup = AlbumLookup()
        self.retry = RetryGenerator()

    def identify(
        self,
        source_file: str,
        track: SplitTrack,
    ) -> AlbumMatch:
        """Identify a track using several strategies."""

        #
        # First attempt
        #
        try:
            return self.lookup.identify_file(str(track.path))

        except Exception:
            print(f"Retrying Track {track.track_number}...")

        #
        # Retry offsets
        #
        for offset in (
            -0.50,
            -0.25,
            0.25,
            0.50,
        ):
            temp_file = None

            try:
                print(f"  Trying {offset:+.2f} seconds...")

                temp_file = self.retry.generate(
                    source_file=source_file,
                    track=track,
                    offset_seconds=offset,
                )

                match = self.lookup.identify_file(str(temp_file))

                Path(temp_file).unlink(missing_ok=True)

                print(f"  Success using {offset:+.2f}")

                return match

            except Exception:
                if temp_file is not None and Path(temp_file).exists():
                    Path(temp_file).unlink()

        raise RuntimeError("Unable to identify track.")
