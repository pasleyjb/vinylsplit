from vinylsplit.lookup import AlbumLookup, AlbumMatch


class SmartIdentifier:
    """Attempts multiple strategies to identify a track."""

    def __init__(self) -> None:
        self.lookup = AlbumLookup()

    def identify(self, filename: str) -> AlbumMatch:
        """
        Identify a track.

        Currently this performs one lookup.
        Retry strategies will be added here.
        """

        return self.lookup.identify_file(filename)