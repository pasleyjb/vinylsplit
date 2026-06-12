import typer
from rich import print

app = typer.Typer(
    help="Split full-album vinyl recordings into individual tagged tracks."
)


@app.command()
def version() -> None:
    """Display the VinylSplit version."""
    print("[bold green]VinylSplit[/bold green] 0.1.0")


def main() -> None:
    """Application entry point."""
    app()


if __name__ == "__main__":
    main()