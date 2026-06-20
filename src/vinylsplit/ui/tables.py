from rich.table import Table

from vinylsplit.formatting import (
    format_channels,
    format_duration,
    format_file_size,
    format_sample_rate,
)


def audio_info_table(info):
    table = Table(title="🎵 Audio Information")

    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Filename", info.filename)
    table.add_row("Format", info.codec)
    table.add_row("Sample Rate", format_sample_rate(info.sample_rate))
    table.add_row("Channels", format_channels(info.channels))
    table.add_row("Duration", format_duration(info.duration))

    if info.bits_per_sample:
        table.add_row("Bit Depth", f"{info.bits_per_sample}-bit")

    table.add_row("File Size", format_file_size(info.file_size))

    return table


def album_table(match):
    table = Table(title="💿 Album Identification")

    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Artist", match.artist)
    table.add_row("Title", match.title)
    table.add_row("Album", match.album)
    table.add_row("Year", match.year)
    table.add_row("Confidence", f"{match.confidence:.0%}")

    return table


def track_table(tracks):
    table = Table(title="🎼 Track Analysis")

    table.add_column("#", style="cyan")
    table.add_column("Start Time", style="green")

    for track in tracks:
        minutes = int(track.start_time // 60)
        seconds = int(track.start_time % 60)

        table.add_row(
            str(track.track_number),
            f"{minutes:02}:{seconds:02}",
        )

    return table
