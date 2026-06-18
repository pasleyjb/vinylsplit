import typer

from vinylsplit.pipeline import Pipeline
from vinylsplit.ui import console, show_banner
from vinylsplit.ui.tables import (
    album_table,
    audio_info_table,
    track_table,
)
from vinylsplit.version import __version__

app = typer.Typer(
    help="Inspect, identify, and process audio album recordings."
)

pipeline = Pipeline()


@app.command()
def inspect(filename: str):
    """Inspect an audio file."""
    console.print(audio_info_table(pipeline.inspect(filename)))


@app.command()
def identify(filename: str):
    """Identify an audio recording."""
    console.print(album_table(pipeline.identify(filename)))


@app.command()
def analyze(filename: str):
    """Analyze an album recording."""
    console.print(track_table(pipeline.analyze(filename)))


@app.command()
def version():
    """Show application version."""
    show_banner(__version__)


def main():
    app()


if __name__ == "__main__":
    main()