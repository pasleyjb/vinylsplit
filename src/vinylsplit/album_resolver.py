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

        if not identified:
            return None, []

        #
        # Count every release ID
        #
        counts = Counter(
            match.release_id
            for _, match in identified
        )

        winner, votes = counts.most_common(1)[0]

        print()
        print(
            f"Album consensus: {votes}/{len(identified)} tracks"
        )

        album = None

        for _, match in identified:

            if match.release_id == winner:
                album = match
                break

        if album is None:
            return None, []

        print(f"Album: {album.album}")
        print(f"Artist: {album.artist}")
        print(f"Release ID: {album.release_id}")

        tracklist = self.musicbrainz.tracklist(
            album.release_id
        )

        print()
        print("Official track list:")

        for number, title in enumerate(tracklist, start=1):
            print(f"{number:02d} {title}")

        return album, tracklist