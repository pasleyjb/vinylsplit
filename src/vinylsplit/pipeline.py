from pathlib import Path

from vinylsplit.album_identifier import AlbumIdentifier
from vinylsplit.audio import read_audio
from vinylsplit.boundary_optimizer import BoundaryOptimizer
from vinylsplit.album_resolver import AlbumResolver
from vinylsplit.detection import TrackBoundary, TrackDetector
from vinylsplit.embedder import ArtworkEmbedder
from vinylsplit.fingerprint import Fingerprinter
from vinylsplit.lookup import AlbumLookup, AlbumMatch
from vinylsplit.models import AudioInfo
from vinylsplit.services.coverart import CoverArtService
from vinylsplit.smart_identifier import SmartIdentifier
from vinylsplit.splitter import SplitTrack, TrackSplitter
from vinylsplit.ui.dashboard import Dashboard
from vinylsplit.ui.progress import ProcessingProgress
from vinylsplit.utils import sanitize_filename


class Pipeline:
    """Coordinates VinylSplit operations."""

    def __init__(self) -> None:
        self.fingerprinter = Fingerprinter()
        self.identifier = SmartIdentifier()
        self.album_identifier = AlbumIdentifier()
        self.detector = TrackDetector()
        self.optimizer = BoundaryOptimizer()
        self.splitter = TrackSplitter()
        self.resolver = AlbumResolver()
        self.coverart = CoverArtService()
        self.embedder = ArtworkEmbedder()

    def inspect(self, filename: str) -> AudioInfo:
        path = Path(filename)
        if not path.exists():
            raise FileNotFoundError(path)
        return read_audio(str(path))

    def identify(self, filename: str) -> AlbumMatch:
        fingerprint = self.fingerprinter.fingerprint(filename)
        lookup = AlbumLookup()
        return lookup.identify(fingerprint)

    def analyze(self, filename: str) -> list[TrackBoundary]:
        return self.detector.detect(filename)

    def split(self, filename: str, output_directory: str) -> list[SplitTrack]:
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
        progress = ProcessingProgress()
        dashboard = Dashboard(progress)
        dashboard.set_album(input_filename=filename)
        dashboard.set_output(output_directory)
        dashboard.set_stage("Preparing", "Preparing")
        dashboard.set_status("Preparing")
        dashboard.start()

        try:
            overall_stages = (
                "analyze_audio",
                "write_tracks",
                "identify_tracks",
                "resolve_album",
                "organize_tracks",
                "artwork",
            )

            progress.update("overall", completed=0, total=len(overall_stages))
            progress.update("analyze_audio", completed=0, total=1)
            progress.update(
                "detect_silence",
                completed=0,
                total=None,
                description="Detect Silence",
            )
            progress.update("write_tracks", completed=0)
            dashboard.set_stage("Analyzing Audio", "Reading audio")
            dashboard.set_status("Analyzing audio")

            album_info = self.album_identifier.identify(filename)

            if album_info:
                dashboard.set_album(
                    title=album_info.album,
                    artist=album_info.artist,
                    year=album_info.year,
                    input_filename=filename,
                )

                dashboard.set_status(
                    f"Album identified: {album_info.artist} - {album_info.album}",
                    "success",
                )

            boundaries = self.analyze(filename)

            if album_info:
                boundaries = self.optimizer.optimize(
                    boundaries=boundaries,
                    expected_tracks=album_info.track_count,
            )
            progress.update("analyze_audio", completed=1)
            progress.advance("overall", 1)
            dashboard.refresh()
            dashboard.refresh()

            written_tracks = 0

            def set_write_total(total: int) -> None:
                dashboard.set_stage("Write Tracks", "Preparing track exports")
                dashboard.set_track(completed=0, total=total)
                progress.update(
                    "write_tracks",
                    completed=0,
                    total=total,
                )
                dashboard.refresh()

            def track_written(track: SplitTrack) -> None:
                nonlocal written_tracks

                written_tracks += 1
                dashboard.set_track(
                    current_track=track.path.name,
                    completed=written_tracks,
                )
                progress.advance("write_tracks", 1)
                dashboard.refresh()

            dashboard.set_stage("Write Tracks", "Writing track files")
            dashboard.set_status("Writing tracks")
            tracks = self.splitter.split(
                filename=filename,
                boundaries=boundaries,
                output_directory=output_directory,
                total_callback=set_write_total,
                track_callback=track_written,
            )
            progress.update("write_tracks", total=len(tracks))
            progress.advance("overall", 1)
            dashboard.set_track(completed=len(tracks), total=len(tracks))
            dashboard.refresh()

            results: list[tuple[SplitTrack, AlbumMatch]] = []
            failed: list[SplitTrack] = []
            identified_tracks = 0

            dashboard.set_stage("Identifying Tracks", "Identifying exported tracks")
            dashboard.set_status("Identifying tracks")
            dashboard.set_track(completed=0, total=len(tracks))
            for track in tracks:
                print(f"IDENTIFYING: {track.path.name}")
                dashboard.set_track(current_track=track.path.name)

                try:
                    match = self.identifier.identify(
                        source_file=filename,
                        track=track,
                    )
                    results.append((track, match))
                except RuntimeError as exc:
                    print(f"\nFAILED: {track.path.name}")
                    print(exc)

                    dashboard.set_status(
                        f"Could not identify {track.path.name}",
                        "warning",
                    )
                    failed.append(track)
                identified_tracks += 1
                dashboard.set_track(
                    current_track=track.path.name,
                    completed=identified_tracks,
                    total=len(tracks),
                )

            progress.advance("overall", 1)
            dashboard.set_status(
                f"Successfully identified {len(results)} of {len(tracks)} tracks.",
                "success",
            )

            if failed:
                dashboard.set_status("Tracks require manual review", "warning")

            dashboard.set_stage("Resolving Album", "Resolving album consensus")
            dashboard.set_status("Resolving album")
            album, official_tracks = self.resolver.resolve(results)
            progress.advance("overall", 1)

            cover = None
            if album:
                dashboard.set_album(
                    title=album.album,
                    artist=album.artist,
                    year=album.year,
                    input_filename=filename,
                )
                dashboard.set_stage("Downloading Artwork", "Downloading album artwork")
                dashboard.set_status("Downloading album artwork")
                try:
                    cover = self.coverart.download(album.release_id)
                    dashboard.set_status("Album artwork downloaded", "success")
                except Exception:
                    cover = None

            dashboard.set_stage("Organize Tracks", "Renaming identified tracks")
            dashboard.set_status("Organizing tracks")
            for track, match in results:
                dashboard.set_track(current_track=track.path.name)
                new_name = (
                    f"{track.track_number:02d} - "
                    f"{sanitize_filename(match.title)}.flac"
                )
                new_path = track.path.with_name(new_name)
                track.path.rename(new_path)
                track.path = new_path

            if album and failed:
                dashboard.set_stage(
                    "Organize Tracks",
                    "Recovering track names",
                )
                for track in failed:
                    dashboard.set_track(current_track=track.path.name)
                    number = track.track_number
                    if number > len(official_tracks):
                        continue

                    title = official_tracks[number - 1]
                    new_name = f"{number:02d} - {sanitize_filename(title)}.flac"
                    new_path = track.path.with_name(new_name)
                    track.path.rename(new_path)
                    track.path = new_path
                    dashboard.set_status(f"{number:02d} → {title}", "success")

            progress.advance("overall", 1)

            if cover:
                dashboard.set_stage("Embedding Artwork", "Embedding album artwork")
                dashboard.set_status("Embedding album artwork")

                for track, _ in results:
                    dashboard.set_track(current_track=track.path.name)
                    try:
                        self.embedder.embed(str(track.path), cover)
                        dashboard.set_status(track.path.name, "success")
                    except Exception as exc:
                        dashboard.set_status(str(exc), "error")

                for track in failed:
                    dashboard.set_track(current_track=track.path.name)
                    try:
                        self.embedder.embed(str(track.path), cover)
                        dashboard.set_status(track.path.name, "success")
                    except Exception as exc:
                        dashboard.set_status(str(exc), "error")

            progress.advance("overall", 1)
            dashboard.set_stage("Complete", "Finished")
            dashboard.set_status("Success", "success")
            dashboard.refresh()

            return results
        except Exception as exc:
            dashboard.set_status(str(exc), "error")
            dashboard.refresh()
            raise
        finally:
            dashboard.stop()
