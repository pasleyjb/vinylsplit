import asyncio

import typer

from vinylsplit.application import build_application_context
from vinylsplit.ui import ui
from vinylsplit.ui.wizard import run_interactive_wizard
from vinylsplit.version import __version__

app = typer.Typer(help="Inspect, identify, and process audio album recordings.")

application = build_application_context()


@app.callback(invoke_without_command=True)
def callback(ctx: typer.Context) -> None:
    """Handle default behavior when no subcommand is provided."""
    if ctx.invoked_subcommand is None:
        run_interactive_wizard()


@app.command()
def inspect(filename: str) -> None:
    """Inspect an audio file."""

    info = application.analyze_controller.inspect(filename)
    ui.audio_info(info)


@app.command()
def identify(filename: str) -> None:
    """Identify an audio recording."""

    metadata = application.analyze_controller.lookup_metadata(filename)
    match = metadata.match
    if match is None:
        ui.warning(
            "No AcoustID match was found for this recording. "
            "The fingerprint was generated successfully, but no matching recording exists in the AcoustID database. "
            "You can still use `vinylsplit process` to split the recording, "
            "or in the future provide `--artist` and `--album` to recover metadata."
        )
        return

    ui.album(match)


@app.command()
def analyze(filename: str) -> None:
    """Analyze an album recording."""

    tracks = application.analyze_controller.analyze_file(filename).boundaries
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
    artist: str | None = typer.Option(
        None,
        "--artist",
        help="Artist name to use when AcoustID lookup fails.",
    ),
    album: str | None = typer.Option(
        None,
        "--album",
        help="Album title to use when AcoustID lookup fails.",
    ),
) -> None:
    """Process an album recording with interactive track review before export."""

    ui.info("Processing album...")

    results = asyncio.run(
        application.export_controller.export(
            filename=filename,
            output_directory=output,
            artist=artist,
            album=album,
        )
    )

    if results.stopped:
        ui.warning("Processing stopped before export.")
        return

    ui.success(f"Finished. Successfully processed {len(results.results)} tracks.")


@app.command()
def version() -> None:
    """Show application version."""

    ui.banner(__version__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
