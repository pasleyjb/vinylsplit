from rich.panel import Panel
from rich.text import Text

from .console import console


def show_banner(version: str) -> None:
    """Display the VinylSplit application banner."""

    title = Text("VinylSplit", style="title", justify="center")
    subtitle = Text(
        "Intelligent Vinyl Track Splitter",
        style="accent",
        justify="center",
    )
    version_text = Text(
        f"Version {version}",
        style="dim",
        justify="center",
    )

    content = Text.assemble(
        title,
        "\n",
        subtitle,
        "\n\n",
        version_text,
    )

    console.print()
    console.print(
        Panel.fit(
            content,
            border_style="header",
            padding=(1, 4),
        )
    )
    console.print()
