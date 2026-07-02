from pathlib import Path
from collections.abc import Callable

from mutagen import File as MutagenFile
from vinylsplit.audio import read_audio
from vinylsplit.album_resolver import AlbumResolver
from vinylsplit.boundary_validation import BoundaryValidator
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
from vinylsplit.adaptive_analysis import build_local_analyzer
from vinylsplit.boundary_states import BoundaryState
from vinylsplit.models import AudioInfo, Boundary, ReviewSession as ReviewState
from vinylsplit.review_state import AdaptiveReviewState
from vinylsplit.services.coverart import CoverArtService
from vinylsplit.smart_identifier import SmartIdentifier
from vinylsplit.splitter import SplitTrack, TrackSplitter
from vinylsplit.review_session import ReviewCancelledError
from vinylsplit.review_session import ReviewSession as InteractiveReviewSession
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
        self.review_validator = BoundaryValidator()
        self.review_session: AdaptiveReviewState | None = None
        
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

    def _read_embedded_metadata(self, filename: str) -> tuple[str | None, str | None, str | None]:
        """Read artist, album, and year from embedded tags when available."""

        try:
            audio = MutagenFile(filename)
        except Exception:
            return None, None, None

        if audio is None or not getattr(audio, "tags", None):
            return None, None, None

        tags = audio.tags

        def first_value(keys: tuple[str, ...]) -> str | None:
            for key in keys:
                values = tags.get(key)
                if values:
                    value = values[0]
                    if value:
                        return str(value)
            return None

        artist = first_value(("artist", "ARTIST", "albumartist", "ALBUMARTIST"))
        album = first_value(("album", "ALBUM"))
        year = first_value(("date", "DATE", "year", "YEAR"))

        if year:
            year = year[:4]

        return artist, album, year

    def _lookup_release_guidance(
        self,
        filename: str,
        artist: str | None,
        album: str | None,
        dashboard: Dashboard,
    ) -> tuple[int | None, list[float] | None, MusicBrainzService.ReleaseMatch | None]:
        """Look up MusicBrainz guidance used by metadata-aware boundary detection."""

        expected_track_count: int | None = None
        expected_boundary_times: list[float] | None = None
        release_from_hints: MusicBrainzService.ReleaseMatch | None = None

        if not artist and not album:
            embedded_artist, embedded_album, _ = self._read_embedded_metadata(filename)
            artist = embedded_artist
            album = embedded_album

        if artist or album:
            try:
                mb = MusicBrainzService()
                release_from_hints = mb.search_release(artist, album)

                print(f"LOOKUP DEBUG: release={release_from_hints!r}")

                if release_from_hints:
                    if release_from_hints.track_durations_seconds:
                        expected_track_count = len(
                            release_from_hints.track_durations_seconds
                        )
                        expected_boundary_times = mb.expected_boundary_times(
                            release_from_hints.track_durations_seconds
                        )
                    else:
                        expected_track_count = len(release_from_hints.tracklist)

                    dashboard.set_status(
                        f"Using MusicBrainz guidance ({expected_track_count} tracks)",
                        "success",
                    )
            except Exception as exc:
                print(f"LOOKUP EXCEPTION: {type(exc).__name__}: {exc}")
                dashboard.set_status(f"MusicBrainz guidance unavailable: {exc}", "warning")

        return expected_track_count, expected_boundary_times, release_from_hints

    def _run_boundary_review(
        self,
        filename: str,
        review_session: AdaptiveReviewState,
        expected_track_count: int | None,
        dashboard: Dashboard,
    ) -> list[Boundary] | None:
        """Run interactive boundary review and return approved boundaries."""

        info = self.inspect(filename)
        analyzer = build_local_analyzer(filename)

        dashboard.set_stage("Interactive Review", "Awaiting boundary approval")
        dashboard.set_status("Review detected boundaries")
        dashboard.stop()

        reviewer = InteractiveReviewSession(
            state=review_session,
            validator=self.review_validator,
            duration_seconds=info.duration,
            expected_track_count=expected_track_count,
            analyzer=analyzer,
        )

        try:
            boundaries = reviewer.run()
            dashboard.start()
            return boundaries
        except ReviewCancelledError:
            dashboard.set_status("Cancelled before writing files", "warning")
            dashboard.refresh()
            return None

    def inspect(self, filename: str) -> AudioInfo:
        path = Path(filename)
        if not path.exists():
            raise FileNotFoundError(path)
        return read_audio(str(path))

    def identify(self, filename: str) -> AlbumMatch:
        embedded_artist, embedded_album, embedded_year = self._read_embedded_metadata(filename)

        if embedded_artist or embedded_album:
            try:
                mb = MusicBrainzService()
                release = mb.search_release(embedded_artist, embedded_album)
                if release is not None:
                    return AlbumMatch(
                        artist=release.artist,
                        title="",
                        album=release.album,
                        year=release.year,
                        release_id=release.release_id,
                        confidence=1.0,
                    )
            except Exception:
                pass

        fingerprint = self.fingerprinter.fingerprint(filename)
        lookup = AlbumLookup()
        match = lookup.identify(fingerprint)

        if match is not None and embedded_year and not match.year:
            match.year = embedded_year

        return match

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
    ) -> AdaptiveReviewState:
        """Analyze audio and return an adaptive review session."""

        print(f"PIPELINE DEBUG: detector type = {type(self.detector).__name__}")
        print("PIPELINE DEBUG: calling TrackDetector.detect()")

        boundaries = self.detector.detect(
            filename,
            expected_track_count=expected_track_count,
            expected_boundary_times=expected_boundary_times,
            diagnostics=diagnostics,
        )

        print(f"PIPELINE DEBUG: detector returned {len(boundaries)} boundaries")

        boundary_list = list(boundaries)
        if boundary_list and boundary_list[0].start_time == 0.0:
            boundary_list[0].state = BoundaryState.LOCKED
            if not boundary_list[0].reasons:
                boundary_list[0].reasons = ["Recording start boundary"]

        session = AdaptiveReviewState(
            source_file=filename,
            boundaries=boundary_list,
        )
        self.review_session = session
        return session

    def split(self, filename: str, output_directory: str, output_format: str = "flac") -> list[SplitTrack]:
        boundaries = self.analyze(filename)
        return self.splitter.split(
            filename=filename,
            boundaries=boundaries,
            output_directory=output_directory,
            output_format=output_format,
        )

    async def process(
        self,
        filename: str,
        output_directory: str,
        output_format: str = "flac",
        artist: str | None = None,
        album: str | None = None,
        release: MusicBrainzService.ReleaseMatch | None = None,
        review_session: AdaptiveReviewState | None = None,
        progress_callback: Callable[[str, str, int | None, int | None], None] | None = None,
    ) -> list[tuple[SplitTrack, AlbumMatch]]:
        progress = ProcessingProgress()
        dashboard = Dashboard(progress)

        def emit_progress(
            stage: str,
            description: str,
            completed: int | None = None,
            total: int | None = None,
        ) -> None:
            if progress_callback is not None:
                progress_callback(stage, description, completed, total)

        dashboard.set_album(input_filename=filename)
        dashboard.set_output(output_directory)
        dashboard.set_stage("Preparing", "Preparing")
        dashboard.set_status("Preparing")
        emit_progress("Preparing", "Preparing", 0, 6)
        dashboard.start()

        # Preserve user-supplied fallback hints before local variables shadow them
        user_artist = artist
        user_album = album

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

            if release is not None:
                release_from_hints = release
                expected_track_count = len(release.track_durations_seconds) if release.track_durations_seconds else len(release.tracklist)
                expected_boundary_times = (
                    MusicBrainzService().expected_boundary_times(release.track_durations_seconds)
                    if release.track_durations_seconds else None
                )
                dashboard.set_status(
                    f"Using selected MusicBrainz release ({expected_track_count} tracks)",
                    "success",
                )
            else:
                expected_track_count, expected_boundary_times, release_from_hints = self._lookup_release_guidance(
                    filename,
                    user_artist,
                    user_album,
                    dashboard,
                )

            dashboard.set_stage("Analyzing Audio", "Reading audio")
            dashboard.set_status("Analyzing audio")
            emit_progress("Analyzing Audio", "Analyzing audio", 0, 1)

            active_review_session = review_session
            if active_review_session is None:
                active_review_session = self.create_review_session(
                    filename,
                    expected_track_count=expected_track_count,
                    expected_boundary_times=expected_boundary_times,
                )
            self.review_session = active_review_session

            if release_from_hints:
                active_review_session.album_artist = getattr(release_from_hints, "artist", None)
                active_review_session.album_title = getattr(release_from_hints, "album", None)
                active_review_session.album_year = getattr(release_from_hints, "year", None)
                active_review_session.release_id = getattr(release_from_hints, "release_id", None)
                tracklist = getattr(release_from_hints, "tracklist", None)
                if tracklist:
                    active_review_session.track_titles = list(tracklist)
                durations = getattr(release_from_hints, "track_durations_seconds", None)
                if durations:
                    active_review_session.expected_track_durations_seconds = list(durations)

            if review_session is None:
                boundaries = self._run_boundary_review(
                    filename,
                    active_review_session,
                    expected_track_count,
                    dashboard,
                )
            else:
                boundaries = list(active_review_session.boundaries)
                dashboard.set_stage("Interactive Review", "Using approved boundaries")
                dashboard.set_status("Using approved boundaries", "success")
                emit_progress("Interactive Review", "Using approved boundaries", 1, 1)

            if boundaries is None:
                return []

            # Create album folder only after approval to avoid partial outputs.
            album_folder = self.artwork.create_album_folder(
                output_directory=output_directory,
                artist=user_artist,
                album=user_album,
            )
            progress.update("analyze_audio", completed=1)
            progress.advance("overall", 1)
            emit_progress("Analyzing Audio", "Analysis complete", 1, 1)
            dashboard.refresh()

            written_tracks = 0

            def set_write_total(total: int) -> None:
                dashboard.set_stage("Write Tracks", "Preparing track exports")
                dashboard.set_track(completed=0, total=total)
                emit_progress("Write Tracks", "Preparing track exports", 0, total)
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
                emit_progress("Write Tracks", f"Writing {track.path.name}", written_tracks, len(boundaries))
                progress.advance("write_tracks", 1)
                dashboard.refresh()

            dashboard.set_stage("Write Tracks", "Writing track files")
            dashboard.set_status("Writing tracks")
            tracks = self.splitter.split(
                filename=filename,
                boundaries=boundaries,
                output_directory=str(album_folder),
                output_format=output_format,
                total_callback=set_write_total,
                track_callback=track_written,
            )
            progress.update("write_tracks", total=len(tracks))
            progress.advance("overall", 1)
            dashboard.set_track(completed=len(tracks), total=len(tracks))
            emit_progress("Write Tracks", "Track writing complete", len(tracks), len(tracks))
            dashboard.refresh()

            results: list[tuple[SplitTrack, AlbumMatch]] = []
            failed: list[SplitTrack] = []
            identified_tracks = 0

            dashboard.set_stage("Identifying Tracks", "Identifying exported tracks")
            dashboard.set_status("Identifying tracks")
            emit_progress("Identifying Tracks", "Identifying tracks", 0, len(tracks))
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
                emit_progress("Identifying Tracks", f"Identified {track.path.name}", identified_tracks, len(tracks))

            progress.advance("overall", 1)
            dashboard.set_status(
                f"Successfully identified {len(results)} of {len(tracks)} tracks.",
                "success",
            )

            if failed:
                dashboard.set_status("Tracks require manual review", "warning")

            dashboard.set_stage("Resolving Album", "Resolving album consensus")
            dashboard.set_status("Resolving album")
            emit_progress("Resolving Album", "Resolving album consensus", 0, 1)
            album, official_tracks = self.resolver.resolve(results)
            progress.advance("overall", 1)
            emit_progress("Resolving Album", "Album resolution complete", 1, 1)

            if album:
                active_review_session.album_artist = album.artist
                active_review_session.album_title = album.album
                active_review_session.album_year = album.year
                active_review_session.release_id = album.release_id

            if official_tracks:
                active_review_session.track_titles = list(official_tracks)
                for index, boundary in enumerate(active_review_session.boundaries):
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
                emit_progress("Downloading Artwork", "Downloading album artwork", 0, 1)
                try:
                    cover = self.artwork.download_artwork(album.release_id)
                    if cover:
                        cover_path = self.artwork.save_cover_file(album_folder, cover)
                        dashboard.set_status("Album artwork downloaded", "success")
                        emit_progress("Downloading Artwork", "Artwork downloaded", 1, 1)
                    else:
                        dashboard.set_status("No cover art available", "warning")
                        emit_progress("Downloading Artwork", "No artwork available", 1, 1)
                except Exception:
                    cover = None
                    dashboard.set_status("Artwork download failed (continuing)", "warning")
                    emit_progress("Downloading Artwork", "Artwork download failed", 1, 1)

            dashboard.set_stage("Organize Tracks", "Renaming tracks using best metadata")
            dashboard.set_status("Organizing tracks")
            emit_progress("Organize Tracks", "Organizing track metadata", 0, len(tracks))

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
                    track_extension = track.path.suffix or ".flac"
                    new_name = f"{track.track_number:02d} - {sanitize_filename(chosen_title)}{track_extension}"
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

                # Write tags where format support is available.
                try:
                    suffix = track.path.suffix.lower()
                    if suffix == ".flac":
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
                    else:
                        audio = MutagenFile(str(track.path), easy=True)
                        if audio is None:
                            raise ValueError("Tagging is unavailable for this output format")

                        title_value = chosen_title or f"Track {track.track_number}"
                        audio["title"] = [title_value]

                        if album:
                            audio["album"] = [album.album]
                            audio["artist"] = [album.artist]
                            if album.year:
                                audio["date"] = [album.year]
                        else:
                            match = match_by_number.get(track.track_number)
                            if match:
                                if match.album:
                                    audio["album"] = [match.album]
                                if match.artist:
                                    audio["artist"] = [match.artist]
                                if match.year:
                                    audio["date"] = [match.year]

                        audio["tracknumber"] = [str(track.track_number)]
                        audio.save()

                    dashboard.set_status("Tagged", "success")
                except Exception as exc:
                    dashboard.set_status(f"Tagging failed: {exc}", "warning")
                emit_progress("Organize Tracks", f"Tagged {track.path.name}", track.track_number, len(tracks))

            progress.advance("overall", 1)

            if cover:
                dashboard.set_stage("Embedding Artwork", "Embedding album artwork")
                dashboard.set_status("Embedding album artwork")
                emit_progress("Embedding Artwork", "Embedding album artwork", 0, len(tracks))

                for track, _ in results:
                    dashboard.set_track(current_track=track.path.name)
                    if self.artwork.embed_artwork(track.path, cover):
                        dashboard.set_status("Artwork embedded", "success")
                    else:
                        dashboard.set_status("Embed failed (continuing)", "warning")
                    emit_progress("Embedding Artwork", f"Embedded {track.path.name}", track.track_number, len(tracks))

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
                    emit_progress("Finalizing", "Setting folder icon", 0, 1)
                    self.artwork.set_folder_icon_linux(album_folder, cover_path)
                    emit_progress("Finalizing", "Folder icon set", 1, 1)

            progress.advance("overall", 1)
            dashboard.set_stage("Complete", "Finished")
            dashboard.set_status("Success", "success")
            emit_progress("Complete", "Finished", 1, 1)
            dashboard.refresh()

            return results
        except Exception as exc:
            dashboard.set_status(str(exc), "error")
            dashboard.refresh()
            raise
        finally:
            dashboard.stop()
