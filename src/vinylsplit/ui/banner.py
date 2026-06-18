from rich.panel import Panel
from rich.text import Text

from .console import console


def show_banner(version: str) -> None:
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

    console.print()

    console.print(
        Panel.fit(
            Text.assemble(
                title,
                "\n",
                subtitle,
                "\n\n",
                version_text,
            ),
            border_style="header",
        )
    )

    console.print()