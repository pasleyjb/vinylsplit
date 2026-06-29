"""Timestamp parsing helpers used by the interactive review workflow."""


def parse_timestamp(text: str) -> float:
    """Parse a human-friendly timestamp into floating-point seconds.

    Supported formats:
    - seconds: ``232`` or ``232.5``
    - minutes:seconds: ``3:52`` or ``03:52.500``
    - hours:minutes:seconds: ``00:03:52`` or ``00:03:52.500``

    Raises
    ------
    ValueError
        If the timestamp is empty or not one of the supported formats.
    """

    raw = text.strip()
    if not raw:
        raise ValueError(_invalid_timestamp_message(text))

    if ":" not in raw:
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(_invalid_timestamp_message(text)) from exc

    parts = raw.split(":")
    if len(parts) == 2:
        minutes_text, seconds_text = parts
        hours_text = None
    elif len(parts) == 3:
        hours_text, minutes_text, seconds_text = parts
    else:
        raise ValueError(_invalid_timestamp_message(text))

    if not minutes_text or not seconds_text or any(part == "" for part in parts):
        raise ValueError(_invalid_timestamp_message(text))

    try:
        seconds = float(seconds_text)
    except ValueError as exc:
        raise ValueError(_invalid_timestamp_message(text)) from exc

    if seconds < 0.0 or seconds >= 60.0:
        raise ValueError(_invalid_timestamp_message(text))

    try:
        minutes = int(minutes_text)
    except ValueError as exc:
        raise ValueError(_invalid_timestamp_message(text)) from exc

    if minutes < 0:
        raise ValueError(_invalid_timestamp_message(text))

    total = minutes * 60.0 + seconds

    if hours_text is None:
        return total

    try:
        hours = int(hours_text)
    except ValueError as exc:
        raise ValueError(_invalid_timestamp_message(text)) from exc

    if hours < 0:
        raise ValueError(_invalid_timestamp_message(text))

    return (hours * 3600.0) + total


def _invalid_timestamp_message(text: str) -> str:
    supported = (
        "Supported formats include:\n"
        "232\n"
        "232.5\n"
        "3:52\n"
        "03:52\n"
        "03:52.500\n"
        "00:03:52\n"
        "00:03:52.500"
    )
    return f'Invalid timestamp: "{text}"\n{supported}'