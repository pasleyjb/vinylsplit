from datetime import timedelta


def format_duration(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""

    total = int(round(seconds))
    duration = timedelta(seconds=total)

    text = str(duration)

    if text.startswith("0:"):
        return text[2:]

    return text


def format_sample_rate(rate: int) -> str:
    """Format sample rate."""

    return f"{rate / 1000:.1f} kHz"


def format_channels(channels: int) -> str:
    """Format channel count."""

    names = {
        1: "Mono",
        2: "Stereo",
    }

    return names.get(channels, str(channels))


def format_file_size(size: int) -> str:
    """Format bytes as MiB."""

    mib = size / (1024 * 1024)
    return f"{mib:.1f} MiB"
