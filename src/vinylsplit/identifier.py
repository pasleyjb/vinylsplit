from pathlib import Path

from vinylsplit.lookup import AlbumLookup


class TrackIdentifier:
    """
    Identify every FLAC track in a directory.
    """

    def __init__(self) -> None:
        self.lookup = AlbumLookup()

    def identify_folder(self, directory: str) -> list:
        """
        Identify every FLAC file in a folder.
        """

        path = Path(directory)

        if not path.exists():
            raise FileNotFoundError(path)

        tracks = []

        for file in sorted(path.glob("*.flac")):
            print(f"Identifying {file.name}...")

            match = self.lookup.identify_file(str(file))

            tracks.append(match)

        return tracks
