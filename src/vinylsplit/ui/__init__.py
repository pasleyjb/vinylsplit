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
        console.print(f"[info]INFO[/info] {text}")

    def success(self, text: str):
        console.print(f"[success]SUCCESS[/success] {text}")

    def warning(self, text: str):
        console.print(f"[warning]WARNING[/warning] {text}")

    def error(self, text: str):
        console.print(f"[error]ERROR[/error] {text}")

    def audio_info(self, info):
        console.print(audio_info_table(info))

    def album(self, match):
        if match is None:
            self.warning(
                "No AcoustID match was found for this recording. "
                "The fingerprint was generated successfully, but no matching recording exists in the AcoustID database. "
                "You can still use `vinylsplit process` to split the recording, "
                "or in the future provide `--artist` and `--album` to recover metadata."
            )
            return

        console.print(album_table(match))

    def tracks(self, tracks):
        console.print(track_table(tracks))


ui = UI()
