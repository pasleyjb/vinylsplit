from collections import Counter

from vinylsplit.lookup import AlbumMatch
from vinylsplit.services.musicbrainz import MusicBrainzService
from vinylsplit.splitter import SplitTrack


class AlbumResolver:
    """
    Determines the most likely album from the
    successfully identified tracks.
    """

    def __init__(self) -> None:
        self.musicbrainz = MusicBrainzService()

    def resolve(
        self,
        identified: list[tuple[SplitTrack, AlbumMatch]],
    ) -> tuple[AlbumMatch | None, list[str]]:

        # Filter out entries where the AlbumMatch is None (e.g. failed IDs).
        valid_matches = [match for _, match in identified if match is not None]

        if not valid_matches:
            return None, []

        # Count every release ID among valid matches
        counts = Counter(match.release_id for match in valid_matches)

        # Determine the most common release_id
        winner, votes = counts.most_common(1)[0]

        print()
        print(f"Album consensus: {votes}/{len(valid_matches)} tracks")

        album = None

        for match in valid_matches:
            if match.release_id == winner:
                album = match
                break

        if album is None:
            return None, []

        print(f"Album: {album.album}")
        print(f"Artist: {album.artist}")
        print(f"Release ID: {album.release_id}")

        try:
            tracklist = self.musicbrainz.tracklist(album.release_id)
        except Exception as e:
            print(f"Warning: MusicBrainz lookup failed: {e}")
            tracklist = []

        print()
        print("Official track list:")

        for number, title in enumerate(tracklist, start=1):
            print(f"{number:02d} {title}")

        return album, tracklist
