from pathlib import Path

from vinylsplit.audio import read_audio
from vinylsplit.album_resolver import AlbumResolver
from vinylsplit.services.musicbrainz import MusicBrainzService
from vinylsplit.detection import TrackDetector
from vinylsplit.embedder import ArtworkEmbedder
from vinylsplit.services.artwork import ArtworkService
from mutagen.flac import FLAC
from vinylsplit.fingerprint import Fingerprinter
from vinylsplit.lookup import AlbumLookup, AlbumMatch
from vinylsplit.metadata_verifier import (
    AcoustIDMetadataProvider,
    EmbeddedMetadataProvider,
    FilePropertiesProvider,
    MetadataContext,
    MetadataVerifier,
    MetadataVerifierConfig,
    MusicBrainzProvider,
    UserInputMetadataProvider,
    display_verification_report,
)
from vinylsplit.models import AudioInfo, Boundary
from vinylsplit.services.coverart import CoverArtService
from vinylsplit.smart_identifier import SmartIdentifier
from vinylsplit.splitter import SplitTrack, TrackSplitter
from vinylsplit.review_session import ReviewSession
from vinylsplit.ui.dashboard import Dashboard
from vinylsplit.ui.progress import ProcessingProgress
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
        self.artwork = ArtworkService()
        self.review_session: ReviewSession | None = None
        
        # Initialize MetadataVerifier with default config
        self.verifier_config = MetadataVerifierConfig(
            auto_proceed_threshold=0.80,
            interactive_mode=True,
        )
        self.verifier = MetadataVerifier(self.verifier_config)
        self._register_metadata_providers()

    def _register_metadata_providers(self) -> None:
        """Register all metadata source providers."""
        self.verifier.register_provider(UserInputMetadataProvider())
        self.verifier.register_provider(EmbeddedMetadataProvider())
        self.verifier.register_provider(AcoustIDMetadataProvider())
        self.verifier.register_provider(MusicBrainzProvider())
        self.verifier.register_provider(FilePropertiesProvider())

    def inspect(self, filename: str) -> AudioInfo:
        path = Path(filename)
        if not path.exists():
            raise FileNotFoundError(path)
        return read_audio(str(path))

    def identify(self, filename: str) -> AlbumMatch:
        fingerprint = self.fingerprinter.fingerprint(filename)
        lookup = AlbumLookup()
        return lookup.identify(fingerprint)

    def analyze(
        self,
        filename: str,
        expected_track_count: int | None = None,
        expected_boundary_times: list[float] | None = None,
        diagnostics: bool = False,
    ) -> list[Boundary]:
        review_session = self.create_review_session(
            filename,
            expected_track_count=expected_track_count,
            expected_boundary_times=expected_boundary_times,
            diagnostics=diagnostics,
        )
        return review_session.boundaries

    def create_review_session(
        self,
        filename: str,
        expected_track_count: int | None = None,
        expected_boundary_times: list[float] | None = None,
        diagnostics: bool = False,
    ) -> ReviewSession:
        """Analyze audio and store the resulting review session."""

        boundaries = self.detector.detect(
            filename,
            expected_track_count=expected_track_count,
            expected_boundary_times=expected_boundary_times,
            diagnostics=diagnostics,
        )

        session = ReviewSession(source_file=filename, boundaries=list(boundaries))
        self.review_session = session
        return session

    def split(self, filename: str, output_directory: str) -> list[SplitTrack]:
        boundaries = self.analyze(filename)
        return self.splitter.split(
            filename=filename,
            boundaries=boundaries,
            output_directory=output_directory,
        )

    async def process(
        self,
        filename: str,
        output_directory: str,
        artist: str | None = None,
        album: str | None = None,
    ) -> list[tuple[SplitTrack, AlbumMatch]]:
        progress = ProcessingProgress()
        dashboard = Dashboard(progress)
        dashboard.set_album(input_filename=filename)
        dashboard.set_output(output_directory)
        dashboard.set_stage("Preparing", "Preparing")
        dashboard.set_status("Preparing")
        dashboard.start()

        # Preserve user-supplied fallback hints before local variables shadow them
        user_artist = artist
        user_album = album

        # Create album folder that will hold all exports
        album_folder = self.artwork.create_album_folder(
            output_directory=output_directory,
            artist=user_artist,
            album=user_album,
        )

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

            expected_track_count: int | None = None
            expected_boundary_times: list[float] | None = None
            release_from_hints: MusicBrainzService.ReleaseMatch | None = None

            if user_artist or user_album:
                try:
                    mb = MusicBrainzService()
                    release_from_hints = mb.search_release(user_artist, user_album)

                    if release_from_hints and release_from_hints.track_durations_seconds:
                        expected_track_count = len(release_from_hints.track_durations_seconds)
                        expected_boundary_times = mb.expected_boundary_times(
                            release_from_hints.track_durations_seconds
                        )
                        dashboard.set_status(
                            f"Using MusicBrainz duration guidance ({expected_track_count} tracks)",
                            "success",
                        )
                    elif release_from_hints:
                        dashboard.set_status(
                            "MusicBrainz release found without usable durations (fallback to audio-only)",
                            "warning",
                        )
                except Exception as exc:
                    dashboard.set_status(f"MusicBrainz guidance unavailable: {exc}", "warning")

            dashboard.set_stage("Analyzing Audio", "Reading audio")
            dashboard.set_status("Analyzing audio")
            review_session = self.create_review_session(
                filename,
                expected_track_count=expected_track_count,
                expected_boundary_times=expected_boundary_times,
            )
            boundaries = review_session.boundaries
            progress.update("analyze_audio", completed=1)
            progress.advance("overall", 1)
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
                output_directory=str(album_folder),
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
                dashboard.set_track(current_track=track.path.name)

                try:
                    # Use MetadataVerifier instead of SmartIdentifier
                    context = MetadataContext(
                        source_file=str(track.path),
                        split_track=track,
                        user_artist=user_artist,
                        user_album=user_album,
                        previous_evidence=[],
                        config=self.verifier_config,
                    )
                    evidence, report = await self.verifier.process_track(context)

                    # Display verification report
                    display_verification_report(report)

                    # If we have evidence, convert to AlbumMatch
                    if evidence:
                        # Prefer a best-available track title from the evidence
                        title = None
                        if evidence.best_tracklist and len(evidence.best_tracklist) >= track.track_number:
                            title = evidence.best_tracklist[track.track_number - 1]

                        if not title:
                            title = f"Track {track.track_number}"

                        match = AlbumMatch(
                            artist=evidence.consensus_artist,
                            title=title,
                            album=evidence.consensus_album_title,
                            year=evidence.consensus_year,
                            release_id=evidence.canonical_release_id or "",
                            confidence=evidence.overall_confidence,
                        )

                        results.append((track, match))
                    else:
                        dashboard.set_status(f"Could not verify {track.path.name}", "warning")
                        failed.append(track)
                        
                except Exception as exc:
                    dashboard.set_status(
                        f"Could not identify {track.path.name}: {exc}",
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

            if album:
                review_session.album_artist = album.artist
                review_session.album_title = album.album
                review_session.album_year = album.year
                review_session.release_id = album.release_id

            if official_tracks:
                review_session.track_titles = list(official_tracks)
                for index, boundary in enumerate(review_session.boundaries):
                    if index < len(official_tracks):
                        boundary.track_title = official_tracks[index]

            # If no album was identified via AcoustID, and the user supplied
            # fallback hints, try searching MusicBrainz by artist/album.
            if album is None and (user_artist or user_album):
                try:
                    release = release_from_hints
                    if release is None:
                        mb = MusicBrainzService()
                        release = mb.search_release(user_artist, user_album)

                    if release:
                        # Construct an AlbumMatch-like object for downstream usage
                        album = AlbumMatch(
                            artist=release.artist,
                            title="",
                            album=release.album,
                            year=release.year,
                            release_id=release.release_id,
                            confidence=1.0,
                        )
                        official_tracks = release.tracklist

                        dashboard.set_status(
                            f"Found MusicBrainz release: '{release.album}' by {release.artist} ({release.year}) — {len(release.tracklist)} tracks",
                            "success",
                        )
                    else:
                        dashboard.set_status(
                            "No MusicBrainz release matched the provided artist/album.",
                            "warning",
                        )

                except Exception as exc:
                    dashboard.set_status(f"MusicBrainz search failed: {exc}", "error")

                dashboard.refresh()

            cover = None
            cover_path = None
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
                    cover = self.artwork.download_artwork(album.release_id)
                    if cover:
                        cover_path = self.artwork.save_cover_file(album_folder, cover)
                        dashboard.set_status("Album artwork downloaded", "success")
                    else:
                        dashboard.set_status("No cover art available", "warning")
                except Exception:
                    cover = None
                    dashboard.set_status("Artwork download failed (continuing)", "warning")

            dashboard.set_stage("Organize Tracks", "Renaming tracks using best metadata")
            dashboard.set_status("Organizing tracks")

            # Build quick lookup of per-track matches by track number
            match_by_number: dict[int, AlbumMatch] = {t.track_number: m for t, m in results}

            total_tracks = len(tracks)

            for track in tracks:
                dashboard.set_track(current_track=track.path.name)

                # Decide the best title for this track (priority order):
                # 1) official MusicBrainz tracklist (if available)
                # 2) per-track match title from evidence
                # 3) leave generic name
                chosen_title = None

                if official_tracks and track.track_number <= len(official_tracks):
                    chosen_title = official_tracks[track.track_number - 1]
                else:
                    match = match_by_number.get(track.track_number)
                    if match and match.title:
                        chosen_title = match.title

                if chosen_title:
                    new_name = f"{track.track_number:02d} - {sanitize_filename(chosen_title)}.flac"
                    new_path = track.path.with_name(new_name)
                    try:
                        track.path.rename(new_path)
                        track.path = new_path
                        dashboard.set_status(f"Renamed → {chosen_title}", "success")
                    except Exception as exc:
                        dashboard.set_status(str(exc), "error")
                else:
                    # Keep generic name (already written as NN Track.flac)
                    dashboard.set_status("Left generic name", "warning")

                # Write tags for every exported FLAC when metadata is available
                try:
                    audio = FLAC(str(track.path))

                    # Title
                    if chosen_title:
                        audio["title"] = chosen_title
                    else:
                        audio.setdefault("title", [f"Track {track.track_number}"])

                    # Album-level metadata
                    if album:
                        audio["album"] = album.album
                        audio["artist"] = album.artist
                        if album.year:
                            audio["date"] = album.year
                        if album.release_id:
                            audio["musicbrainz_releaseid"] = album.release_id
                    else:
                        # Populate from per-track match if available
                        match = match_by_number.get(track.track_number)
                        if match:
                            if match.album:
                                audio["album"] = match.album
                            if match.artist:
                                audio["artist"] = match.artist
                            if match.year:
                                audio["date"] = match.year

                    # Track numbers
                    audio["tracknumber"] = str(track.track_number)
                    audio["totaltracks"] = str(total_tracks)

                    audio.save()
                    dashboard.set_status("Tagged", "success")
                except Exception as exc:
                    dashboard.set_status(f"Tagging failed: {exc}", "warning")

            progress.advance("overall", 1)

            if cover:
                dashboard.set_stage("Embedding Artwork", "Embedding album artwork")
                dashboard.set_status("Embedding album artwork")

                for track, _ in results:
                    dashboard.set_track(current_track=track.path.name)
                    if self.artwork.embed_artwork(track.path, cover):
                        dashboard.set_status("Artwork embedded", "success")
                    else:
                        dashboard.set_status("Embed failed (continuing)", "warning")

                for track in failed:
                    dashboard.set_track(current_track=track.path.name)
                    if self.artwork.embed_artwork(track.path, cover):
                        dashboard.set_status("Artwork embedded", "success")
                    else:
                        dashboard.set_status("Embed failed (continuing)", "warning")

                # Set folder icon on Linux if available
                if cover_path:
                    dashboard.set_stage("Finalizing", "Setting folder icon")
                    dashboard.set_status("Setting folder icon...")
                    self.artwork.set_folder_icon_linux(album_folder, cover_path)

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
