import typer
from rich.console import Console
from rich.table import Table

from vinylsplit.pipeline import Pipeline

app = typer.Typer(
    help="Inspect, identify, and process audio album recordings."
)

console = Console()
pipeline = Pipeline()


@app.command()
def inspect(filename: str) -> None:
    """Inspect an audio file."""

    info = pipeline.inspect(filename)

    table = Table(title="Audio Information")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Filename", info.filename)
    table.add_row("Format", info.codec)
    table.add_row("Sample Rate", f"{info.sample_rate:,} Hz")
    table.add_row(
        "Channels",
        "Stereo" if info.channels == 2 else str(info.channels),
    )
    table.add_row("Duration", f"{info.duration:.2f} seconds")

    if info.bits_per_sample:
        table.add_row("Bit Depth", f"{info.bits_per_sample}-bit")

    table.add_row(
        "File Size",
        f"{info.file_size / (1024 * 1024):.1f} MB",
    )

    console.print(table)


@app.command()
def version() -> None:
    """Show the application version."""

    console.print("[bold green]🎵 VinylSplit[/bold green] 0.1.0")


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()