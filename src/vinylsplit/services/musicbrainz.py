from dataclasses import dataclass

import requests


@dataclass
class MusicBrainzRecording:
    """Metadata returned from MusicBrainz."""

    artist: str
    title: str
    album: str
    year: str
    release_id: str


class MusicBrainzService:
    """Retrieve metadata from MusicBrainz."""

    URL = "https://musicbrainz.org/ws/2"

    HEADERS = {"User-Agent": "VinylSplit/0.1 (https://github.com/)"}

    def lookup(self, recording_id: str) -> MusicBrainzRecording:
        """Look up a recording."""

        response = requests.get(
            f"{self.URL}/recording/{recording_id}",
            params={
                "fmt": "json",
                "inc": "artists+releases",
            },
            headers=self.HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        artist = "Unknown Artist"
        title = data.get("title", "Unknown Title")
        album = "Unknown Album"
        year = "----"
        release_id = ""

        artists = data.get("artist-credit", [])

        if artists:
            artist = artists[0]["artist"]["name"]

        releases = data.get("releases", [])

        if releases:
            release = releases[0]

            album = release.get(
                "title",
                album,
            )

            release_id = release.get(
                "id",
                "",
            )

            date = release.get("date", "")

            if date:
                year = date[:4]

        return MusicBrainzRecording(
            artist=artist,
            title=title,
            album=album,
            year=year,
            release_id=release_id,
        )

    def tracklist(
        self,
        release_id: str,
    ) -> list[str]:
        """
        Return the official track list for a release.
        """

        response = requests.get(
            f"{self.URL}/release/{release_id}",
            params={
                "fmt": "json",
                "inc": "recordings",
            },
            headers=self.HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        titles: list[str] = []

        for medium in data.get("media", []):
            for track in medium.get("tracks", []):
                titles.append(track["title"])

        return titles
