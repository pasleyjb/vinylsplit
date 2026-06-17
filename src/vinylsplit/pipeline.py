from pathlib import Path

from vinylsplit.audio import read_audio
from vinylsplit.album_resolver import AlbumResolver
from vinylsplit.detection import TrackBoundary, TrackDetector
from vinylsplit.embedder import ArtworkEmbedder
from vinylsplit.fingerprint import Fingerprinter
from vinylsplit.lookup import AlbumLookup, AlbumMatch
from vinylsplit.models import AudioInfo
from vinylsplit.services.coverart import CoverArtService
from vinylsplit.smart_identifier import SmartIdentifier
from vinylsplit.splitter import SplitTrack, TrackSplitter
from vinylsplit.utils import sanitize_filename


class Pipeline:
    """Coordinates VinylSplit operations."""

    def __init__(self) -> None:
        self.fingerprinter = Fingerprinter()
        self.identifier = SmartIdentifier()
        self.detector = TrackDetector()
        self.splitter = TrackSplitter()
        self.resolver = AlbumResolver()

        self.coverart = CoverArtService()
        self.embedder = ArtworkEmbedder()

    def inspect(self, filename: str) -> AudioInfo:
        """Read information about an audio file."""

        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(path)

        return read_audio(str(path))

    def identify(self, filename: str) -> AlbumMatch:
        """Identify an audio recording."""

        fingerprint = self.fingerprinter.fingerprint(filename)

        lookup = AlbumLookup()

        return lookup.identify(fingerprint)

    def analyze(self, filename: str) -> list[TrackBoundary]:
        """Analyze an audio file for track boundaries."""

        return self.detector.detect(filename)

    def split(
        self,
        filename: str,
        output_directory: str,
    ) -> list[SplitTrack]:
        """Analyze and split an audio recording."""

        boundaries = self.analyze(filename)

        return self.splitter.split(
            filename=filename,
            boundaries=boundaries,
            output_directory=output_directory,
        )

    def process(
        self,
        filename: str,
        output_directory: str,
    ) -> list[tuple[SplitTrack, AlbumMatch]]:
        """
        Complete VinylSplit workflow.

        1. Detect track boundaries
        2. Split the recording
        3. Identify tracks
        4. Resolve album
        5. Rename tracks
        6. Recover missing titles
        7. Download artwork
        8. Embed artwork
        """

        #
        # Split the album
        #
        tracks = self.split(
            filename=filename,
            output_directory=output_directory,
        )

        results: list[tuple[SplitTrack, AlbumMatch]] = []
        failed: list[SplitTrack] = []

        #
        # Identify every track
        #
        for track in tracks:

            print(f"Identifying {track.path.name}...")

            try:

                match = self.identifier.identify(
                    source_file=filename,
                    track=track,
                )

                results.append(
                    (
                        track,
                        match,
                    )
                )

            except RuntimeError:

                print(
                    f"  Could not identify {track.path.name}"
                )

                failed.append(track)

        print()

        print(
            f"Successfully identified "
            f"{len(results)} of {len(tracks)} tracks."
        )

        if failed:

            print()
            print("Tracks requiring manual review:")

            for track in failed:
                print(f"  {track.path.name}")

        #
        # Determine the album
        #
        print()

        album, official_tracks = self.resolver.resolve(
            results
        )

        #
        # Download artwork
        #
        cover = None

        if album:

            try:

                cover = self.coverart.download(
                    album.release_id
                )

                print()
                print("Album artwork downloaded.")

            except Exception:

                cover = None

        #
        # Rename identified tracks
        #
        for track, match in results:

            new_name = (
                f"{track.track_number:02d} - "
                f"{sanitize_filename(match.title)}.flac"
            )

            new_path = track.path.with_name(
                new_name
            )

            track.path.rename(new_path)
            track.path = new_path

        #
        # Recover unidentified tracks
        #
        if album and failed:

            print()
            print("Recovering track names:")

            for track in failed:

                number = track.track_number

                if number > len(official_tracks):
                    continue

                title = official_tracks[number - 1]

                new_name = (
                    f"{number:02d} - "
                    f"{sanitize_filename(title)}.flac"
                )

                new_path = track.path.with_name(
                    new_name
                )

                track.path.rename(new_path)
                track.path = new_path

                print(
                    f"{number:02d} -> {title}"
                )

        #
        # Embed artwork into every exported track
        #
        if cover:

            print()
            print("Embedding album artwork...")

            #
            # Successfully identified tracks
            #
            for track, _ in results:

                try:

                    self.embedder.embed(
                        str(track.path),
                        cover,
                    )

                    print(
                        f"  ✓ {track.path.name}"
                    )

                except Exception as exc:

                    print(
                        f"  ✗ {track.path.name}: {exc}"
                    )

            #
            # Recovered tracks
            #
            for track in failed:

                try:

                    self.embedder.embed(
                        str(track.path),
                        cover,
                    )

                    print(
                        f"  ✓ {track.path.name}"
                    )

                except Exception as exc:

                    print(
                        f"  ✗ {track.path.name}: {exc}"
                    )

        return results