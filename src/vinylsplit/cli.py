import typer

from vinylsplit.audio import inspect_file

app = typer.Typer(
    help="Split full-album vinyl recordings into individual tagged FLAC tracks."
)


@app.command()
def inspect(filename: str) -> None:
    """Inspect a FLAC file."""
    inspect_file(filename)


@app.command()
def version() -> None:
    """Show the application version."""
    print("VinylSplit 0.1.0")


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()