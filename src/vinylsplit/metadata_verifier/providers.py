"""Built-in metadata source providers."""

import time
from pathlib import Path

from vinylsplit.lookup import AlbumLookup
from vinylsplit.metadata_verifier.models import (
    MetadataContext,
    MetadataEvidence,
    MetadataSource,
    MetadataSourceProvider,
)
from vinylsplit.services.musicbrainz import MusicBrainzService


class UserInputMetadataProvider(MetadataSourceProvider):
    """Metadata from user CLI arguments."""

    @property
    def source_type(self) -> MetadataSource:
        return MetadataSource.USER_INPUT

    @property
    def default_confidence(self) -> float:
        # User may make typos but high intent signal
        return 0.70

    async def gather(self, context: MetadataContext) -> MetadataEvidence | None:
        """Use MusicBrainz to search for releases matching user input."""
        if not context.user_artist and not context.user_album:
            return None

        try:
            mb = MusicBrainzService()
            release = mb.search_release(context.user_artist, context.user_album)

            if release is None:
                return None

            return MetadataEvidence(
                source=self.source_type,
                release_id=release.release_id,
                artist=release.artist,
                album_title=release.album,
                year=release.year,
                track_count=len(release.tracklist) if release.tracklist else None,
                tracklist=release.tracklist,
                confidence=self.default_confidence,
                reasoning=f"User provided --artist={context.user_artist} --album={context.user_album}",
                timestamp=time.monotonic(),
            )
        except Exception as exc:
            print(f"UserInputMetadataProvider error: {exc}")
            return None


class EmbeddedMetadataProvider(MetadataSourceProvider):
    """Metadata from embedded FLAC/Vorbis tags."""

    @property
    def source_type(self) -> MetadataSource:
        return MetadataSource.EMBEDDED_TAGS

    @property
    def default_confidence(self) -> float:
        # May be outdated or incorrect
        return 0.65

    async def gather(self, context: MetadataContext) -> MetadataEvidence | None:
        """Extract metadata from FLAC tags."""
        try:
            from mutagen.flac import FLAC

            flac = FLAC(context.source_file)

            artist = None
            album = None
            year = None
            track_count = None

            if "ARTIST" in flac:
                artist = flac["ARTIST"][0]
            if "ALBUM" in flac:
                album = flac["ALBUM"][0]
            if "DATE" in flac:
                date_str = flac["DATE"][0]
                year = date_str[:4] if len(date_str) >= 4 else None
            if "TRACKTOTAL" in flac:
                try:
                    track_count = int(flac["TRACKTOTAL"][0])
                except (ValueError, IndexError):
                    pass

            if not any([artist, album, year, track_count]):
                return None

            return MetadataEvidence(
                source=self.source_type,
                release_id=None,
                artist=artist,
                album_title=album,
                year=year,
                track_count=track_count,
                tracklist=None,
                confidence=self.default_confidence,
                reasoning="Extracted from FLAC Vorbis comments",
                timestamp=time.monotonic(),
            )
        except Exception as exc:
            print(f"EmbeddedMetadataProvider error: {exc}")
            return None


class AcoustIDMetadataProvider(MetadataSourceProvider):
    """Metadata from AcoustID fingerprint matching."""

    @property
    def source_type(self) -> MetadataSource:
        return MetadataSource.ACOUSTID

    @property
    def default_confidence(self) -> float:
        # Fingerprint is strong, but can fail on noisy vinyl
        return 0.85

    async def gather(self, context: MetadataContext) -> MetadataEvidence | None:
        """Fingerprint and identify via AcoustID."""
        try:
            lookup = AlbumLookup()
            match = lookup.identify_file(context.source_file)

            if match is None:
                return None

            return MetadataEvidence(
                source=self.source_type,
                release_id=match.release_id,
                artist=match.artist,
                album_title=match.album,
                year=match.year,
                track_count=None,
                tracklist=None,
                confidence=self.default_confidence * match.confidence,
                reasoning=f"AcoustID fingerprint match (score: {match.confidence:.0%})",
                timestamp=time.monotonic(),
                extra={"acoustid_score": match.confidence},
            )
        except Exception as exc:
            print(f"AcoustIDMetadataProvider error: {exc}")
            return None


class MusicBrainzProvider(MetadataSourceProvider):
    """Direct MusicBrainz release lookup."""

    @property
    def source_type(self) -> MetadataSource:
        return MetadataSource.MUSICBRAINZ

    @property
    def default_confidence(self) -> float:
        # Official DB, but may lack obscure releases
        return 0.90

    async def gather(self, context: MetadataContext) -> MetadataEvidence | None:
        """Search MusicBrainz using user hints."""
        if not context.user_artist and not context.user_album:
            return None

        try:
            mb = MusicBrainzService()
            release = mb.search_release(context.user_artist, context.user_album)

            if release is None:
                return None

            return MetadataEvidence(
                source=self.source_type,
                release_id=release.release_id,
                artist=release.artist,
                album_title=release.album,
                year=release.year,
                track_count=len(release.tracklist) if release.tracklist else None,
                tracklist=release.tracklist,
                confidence=self.default_confidence,
                reasoning="MusicBrainz release search",
                timestamp=time.monotonic(),
            )
        except Exception as exc:
            print(f"MusicBrainzProvider error: {exc}")
            return None


class AlbumResolverProvider(MetadataSourceProvider):
    """Metadata from album resolver consensus."""

    @property
    def source_type(self) -> MetadataSource:
        return MetadataSource.ALBUM_RESOLVER

    @property
    def default_confidence(self) -> float:
        # Consensus of multiple track IDs
        return 0.80

    async def gather(self, context: MetadataContext) -> MetadataEvidence | None:
        """Use album resolver to find consensus from previous track IDs."""
        # This provider is typically used after multiple tracks have been identified.
        # For now, return None as it's usually called from pipeline context.
        return None


class FilePropertiesProvider(MetadataSourceProvider):
    """Metadata from file properties."""

    @property
    def source_type(self) -> MetadataSource:
        return MetadataSource.FILE_PROPERTIES

    @property
    def default_confidence(self) -> float:
        # File properties (track count, duration) are certain
        return 0.95

    @property
    def is_required(self) -> bool:
        """File properties are required; failure is a pipeline error."""
        return True

    async def gather(self, context: MetadataContext) -> MetadataEvidence | None:
        """Extract file properties: track count, duration."""
        try:
            from mutagen.flac import FLAC

            flac = FLAC(context.source_file)

            # Track count from split metadata if available
            track_number = context.split_track.track_number if context.split_track else None
            duration_seconds = context.split_track.end_time - context.split_track.start_time

            return MetadataEvidence(
                source=self.source_type,
                release_id=None,
                artist=None,
                album_title=None,
                year=None,
                track_count=track_number,
                tracklist=None,
                confidence=self.default_confidence,
                reasoning=f"File properties: duration={duration_seconds:.1f}s",
                timestamp=time.monotonic(),
                extra={
                    "duration_seconds": duration_seconds,
                },
            )
        except Exception as exc:
            print(f"FilePropertiesProvider error: {exc}")
            return None
