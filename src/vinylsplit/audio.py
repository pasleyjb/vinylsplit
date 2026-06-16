from pathlib import Path

from mutagen.flac import FLAC

from vinylsplit.models import AudioInfo


def inspect_file(filename: str) -> AudioInfo:
    """Read information from a FLAC file."""

    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(path)

    audio = FLAC(path)
    info = audio.info

    return AudioInfo(
        filename=path.name,
        codec="FLAC",
        sample_rate=info.sample_rate,
        channels=info.channels,
        duration=info.length,
        bits_per_sample=getattr(info, "bits_per_sample", None),
        file_size=path.stat().st_size,
        tags=dict(audio.tags),
    )