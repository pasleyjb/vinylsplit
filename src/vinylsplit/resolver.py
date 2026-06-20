from collections import Counter

from vinylsplit.metadata import AlbumMetadata


class AlbumResolver:
    """
    Chooses the most likely album from multiple track matches.
    """

    def resolve(
        self,
        albums: list[AlbumMetadata],
    ) -> AlbumMetadata:
        """
        Return the album that appears most often.
        """

        if not albums:
            raise ValueError("No album candidates were provided.")

        votes = Counter()

        for album in albums:
            key = (
                album.artist,
                album.title,
                album.year,
            )

            votes[key] += 1

        winner = votes.most_common(1)[0][0]

        for album in albums:
            if (
                album.artist,
                album.title,
                album.year,
            ) == winner:
                return album

        raise RuntimeError("Unable to resolve album.")
