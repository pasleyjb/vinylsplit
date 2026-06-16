from pathlib import Path
from pathlib import Path

from vinylsplit.audio import read_audio
from vinylsplit.models import AudioInfo


class Pipeline:
    """Coordinates VinylSplit operations."""

    def inspect(self, filename: str) -> AudioInfo:
        """Read information about an audio file."""

        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(path)

        return read_audio(str(path))