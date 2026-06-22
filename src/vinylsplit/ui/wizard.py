"""Interactive wizard for VinylSplit."""

import asyncio
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from vinylsplit.pipeline import Pipeline
from vinylsplit.services.musicbrainz import MusicBrainzService
from vinylsplit.audio import read_audio
from vinylsplit.ui.banner import show_banner
from vinylsplit.ui.console import console
from vinylsplit.ui.tables import audio_info_table, album_table


class InteractiveWizard:
    """Interactive wizard for processing audio files."""

    def __init__(self):
        self.pipeline = Pipeline()
        self.musicbrainz = MusicBrainzService()
        self.console = console
        self.selected_file: Path | None = None
        self.selected_artist: str | None = None
        self.selected_album: str | None = None
        self.selected_release = None

    def run(self) -> None:
        """Run the interactive wizard."""
        try:
            self._welcome()
            self._select_file()
            self._inspect_file()
            self._collect_metadata()
            self._search_musicbrainz()
            self._select_release()
            self._confirm_and_process()
            self._success()
        except KeyboardInterrupt:
            self.console.print("\n[warning]Cancelled by user[/warning]")
        except Exception as e:
            self.console.print(f"\n[error]Error[/error]: {e}")
            raise

    def _welcome(self) -> None:
        """Display welcome message."""
        show_banner("Interactive Mode")
        self.console.print(
            Panel(
                "Welcome to [cyan]VinylSplit[/cyan]!\n\n"
                "This wizard will help you split and tag your vinyl album recordings.\n\n"
                "Let's start by selecting an audio file.",
                title="[bold]Getting Started[/bold]",
                expand=False,
            )
        )

    def _select_file(self) -> None:
        """Prompt user to select an audio file."""
        while True:
            file_prompt = Prompt.ask(
                "[bold]Audio file path[/bold]",
                default="",
            )

            # Handle quit commands
            if file_prompt.lower() in ("quit", "exit", "q"):
                raise KeyboardInterrupt()

            if not file_prompt:
                self.console.print("[warning]File path cannot be empty[/warning]")
                continue

            # Strip surrounding single or double quotes (from drag-and-drop)
            file_path = file_prompt.strip().strip("'\"")

            # Expand home directory and resolve to absolute normalized path
            path = Path(file_path).expanduser().resolve()

            if not path.exists():
                self.console.print(
                    f"[warning]File not found:[/warning] {path}\n"
                    "[dim]Tip: Use full paths or ~/relative/to/home[/dim]"
                )
                continue

            if not path.is_file():
                self.console.print(
                    f"[warning]Path is not a file:[/warning] {path}\n"
                    "[dim]Tip: Path exists but is a directory[/dim]"
                )
                continue

            self.selected_file = path
            self.console.print(f"[success]Selected:[/success] {path}")
            break

    def _inspect_file(self) -> None:
        """Inspect and display audio file information."""
        if not self.selected_file:
            return

        try:
            info = self.pipeline.inspect(str(self.selected_file))
            self.console.print()
            self.console.print(Panel(audio_info_table(info), title="[bold]Audio Information[/bold]"))
        except Exception as e:
            self.console.print(f"[error]Could not inspect file:[/error] {e}")
            raise

    def _collect_metadata(self) -> None:
        """Collect metadata from user input or file tags."""
        self.console.print()

        # Try to read embedded metadata
        embedded_artist = None
        embedded_album = None

        try:
            if self.selected_file:
                from mutagen.flac import FLAC

                audio = FLAC(str(self.selected_file))
                embedded_artist = audio.get("artist", [None])[0]
                embedded_album = audio.get("album", [None])[0]
        except Exception:
            pass

        # Display embedded metadata if found
        if embedded_artist or embedded_album:
            self.console.print("[cyan]Found embedded metadata:[/cyan]")
            if embedded_artist:
                self.console.print(f"  Artist: {embedded_artist}")
            if embedded_album:
                self.console.print(f"  Album: {embedded_album}")

            use_embedded = Confirm.ask("\n[bold]Use this metadata?[/bold]", default=True)

            if use_embedded and embedded_artist and embedded_album:
                self.selected_artist = embedded_artist
                self.selected_album = embedded_album
                return

        # Prompt for artist and album
        self.console.print()
        self.selected_artist = Prompt.ask("[bold]Artist name[/bold]")
        self.selected_album = Prompt.ask("[bold]Album title[/bold]")

    def _search_musicbrainz(self) -> None:
        """Search MusicBrainz for matching releases."""
        self.console.print()
        self.console.print(
            f"[cyan]Searching MusicBrainz for '{self.selected_album}' by '{self.selected_artist}'...[/cyan]"
        )

        try:
            release = self.musicbrainz.search_release(
                self.selected_artist,
                self.selected_album,
            )

            if not release:
                self.console.print("[warning]No matching release found in MusicBrainz[/warning]")
                self.selected_release = None
                return

            self.selected_release = release
            self.console.print(
                f"[success]Found:[/success] {release.album} ({release.year}) - {len(release.tracklist)} tracks"
            )
        except Exception as e:
            self.console.print(f"[error]Search failed:[/error] {e}")
            self.selected_release = None

    def _select_release(self) -> None:
        """Display release and allow user to confirm or search alternatives."""
        if not self.selected_release:
            self.console.print(
                "[warning]Proceeding without MusicBrainz metadata. Tracks will use generic names.[/warning]"
            )
            return

        self.console.print()
        self.console.print(
            Panel(
                album_table(
                    type(
                        "AlbumMatch",
                        (),
                        {
                            "artist": self.selected_release.artist,
                            "album": self.selected_release.album,
                            "year": self.selected_release.year,
                            "release_id": self.selected_release.release_id,
                            "title": "",
                            "confidence": 1.0,
                        },
                    )()
                ),
                title="[bold]Selected Release[/bold]",
            )
        )

        if self.selected_release.tracklist:
            self.console.print("[cyan]Track list:[/cyan]")
            for i, title in enumerate(self.selected_release.tracklist, start=1):
                self.console.print(f"  {i:02d}. {title}")

    def _confirm_and_process(self) -> None:
        """Display confirmation and start processing."""
        self.console.print()

        confirm = Confirm.ask(
            "[bold]Ready to process?[/bold]",
            default=True,
        )

        if not confirm:
            raise KeyboardInterrupt()

        # Determine output directory
        output_dir = Prompt.ask(
            "[bold]Output directory[/bold]",
            default="output",
        )

        # Run pipeline
        self.console.print()
        self.console.print("[cyan]Starting pipeline...[/cyan]")

        try:
            results = asyncio.run(
                self.pipeline.process(
                    filename=str(self.selected_file),
                    output_directory=output_dir,
                    artist=self.selected_artist,
                    album=self.selected_album,
                )
            )

            return results
        except Exception as e:
            self.console.print(f"[error]Pipeline failed:[/error] {e}")
            raise

    def _success(self) -> None:
        """Display success message."""
        self.console.print()
        self.console.print(
            Panel(
                "[success]✓ Done![/success] Your album has been split and tagged.",
                title="[bold]Complete[/bold]",
            )
        )


def run_interactive_wizard() -> None:
    """Entry point for interactive mode."""
    wizard = InteractiveWizard()
    wizard.run()
