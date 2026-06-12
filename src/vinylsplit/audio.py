from pathlib import Path

from mutagen.flac import FLAC


def inspect_file(filename: str) -> None:
    """Display information about a FLAC file."""

    path = Path(filename)

    if not path.exists():
        print(f"File not found: {filename}")
        return

    audio = FLAC(path)

    info = audio.info

    print(f"File: {path.name}")
    print(f"Sample Rate : {info.sample_rate}")
    print(f"Channels    : {info.channels}")
    print(f"Length      : {info.length:.2f} seconds")
    print()

    print("Tags")

    for key, value in audio.tags.items():
        print(f"{key}: {value}")