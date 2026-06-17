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
    """Retrieve recording metadata from MusicBrainz."""

    URL = "https://musicbrainz.org/ws/2/recording"

    def lookup(self, recording_id: str) -> MusicBrainzRecording:
        """Look up a recording by MusicBrainz recording ID."""

        response = requests.get(
            f"{self.URL}/{recording_id}",
            params={
                "fmt": "json",
                "inc": "artists+releases",
            },
            headers={
                "User-Agent": "VinylSplit/0.1 (https://github.com/)"
            },
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

            album = release.get("title", album)
            release_id = release.get("id", "")

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