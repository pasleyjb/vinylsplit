from pathlib import Path

from mutagen import File

from vinylsplit.models import AudioInfo


def read_audio(filename: str) -> AudioInfo:
    """Read information from a supported audio file."""

    path = Path(filename)

    if not path.exists():
        raise FileNotFoundError(path)

    audio = File(path)

    if audio is None:
        raise ValueError(f"Unsupported audio format: {path}")

    info = audio.info

    return AudioInfo(
        filename=path.name,
        codec=path.suffix.upper().replace(".", ""),
        sample_rate=getattr(info, "sample_rate", 0),
        channels=getattr(info, "channels", 0),
        duration=getattr(info, "length", 0.0),
        bits_per_sample=getattr(info, "bits_per_sample", None),
        file_size=path.stat().st_size,
        tags=dict(audio.tags) if audio.tags else {},
    )
