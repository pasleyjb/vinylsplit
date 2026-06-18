from .banner import show_banner
from .console import console
from .tables import (
    album_table,
    audio_info_table,
    track_table,
)


class UI:
    def banner(self, version: str):
        show_banner(version)

    def print(self, obj):
        console.print(obj)

    def info(self, text: str):
        console.print(f"[cyan]ℹ[/] {text}")

    def success(self, text: str):
        console.print(f"[green]✓[/] {text}")

    def warning(self, text: str):
        console.print(f"[yellow]⚠[/] {text}")

    def error(self, text: str):
        console.print(f"[red]✗[/] {text}")

    def audio_info(self, info):
        console.print(audio_info_table(info))

    def album(self, match):
        console.print(album_table(match))

    def tracks(self, tracks):
        console.print(track_table(tracks))


ui = UI()