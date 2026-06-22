from dataclasses import dataclass

import requests


@dataclass(slots=True)
class MusicBrainzRecording:
    """Metadata returned from MusicBrainz."""

    artist: str
    title: str
    album: str
    year: str
    release_id: str


@dataclass(slots=True)
class MusicBrainzAlbum:
    """Album returned from an album search."""

    artist: str
    album: str
    year: str
    release_id: str
    track_count: int


class MusicBrainzService:
    """Retrieve metadata from MusicBrainz."""

    URL = "https://musicbrainz.org/ws/2"

    HEADERS = {
        "User-Agent": "VinylSplit/1.0 (https://github.com/pasleyjb/vinylsplit)"
    }

    def lookup(self, recording_id: str) -> MusicBrainzRecording:
        """Look up a recording by MusicBrainz recording ID."""

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

    def search_album(
        self,
        artist: str,
        album: str,
    ) -> MusicBrainzAlbum | None:
        """
        Search MusicBrainz for an album using artist and album name.

        Returns None if no suitable release is found.
        """

        response = requests.get(
            f"{self.URL}/release",
            params={
                "fmt": "json",
                "query": f'artist:"{artist}" release:"{album}"',
                "limit": 1,
            },
            headers=self.HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        releases = data.get("releases", [])

        if not releases:
            return None

        release = releases[0]

        year = "----"

        if release.get("date"):
            year = release["date"][:4]

        track_count = 0

        media = release.get("media", [])

        if media:
            track_count = media[0].get("track-count", 0)

        return MusicBrainzAlbum(
            artist=artist,
            album=release.get("title", album),
            year=year,
            release_id=release["id"],
            track_count=track_count,
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