from dataclasses import dataclass


@dataclass
class AudioInfo:
    """Information about an audio file."""

    filename: str
    codec: str
    sample_rate: int
    channels: int
    duration: float
    bits_per_sample: int | None
    file_size: int
    tags: dict[str, list[str]]