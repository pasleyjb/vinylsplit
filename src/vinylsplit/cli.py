import typer

from vinylsplit.pipeline import Pipeline
from vinylsplit.ui import ui
from vinylsplit.version import __version__

app = typer.Typer(
    help="Inspect, identify, and process audio album recordings."
)

pipeline = Pipeline()


@app.command()
def inspect(filename: str) -> None:
    """Inspect an audio file."""

    info = pipeline.inspect(filename)
    ui.audio_info(info)


@app.command()
def identify(filename: str) -> None:
    """Identify an audio recording."""

    match = pipeline.identify(filename)
    ui.album(match)


@app.command()
def analyze(filename: str) -> None:
    """Analyze an album recording."""

    tracks = pipeline.analyze(filename)
    ui.tracks(tracks)


@app.command()
def process(
    filename: str,
    output: str = typer.Option(
        "output",
        "--output",
        "-o",
        help="Output directory",
    ),
) -> None:
    """Process an album recording."""

    ui.info("Processing album...")

    results = pipeline.process(
        filename=filename,
        output_directory=output,
    )

    ui.success(
        f"Finished. Successfully processed {len(results)} tracks."
    )


@app.command()
def version() -> None:
    """Show application version."""

    ui.banner(__version__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()