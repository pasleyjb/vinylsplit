from dataclasses import dataclass

import requests

from vinylsplit.config import settings
from vinylsplit.fingerprint import Fingerprint


@dataclass
class AcoustIDResult:
    """Result returned from the AcoustID API."""

    score: float
    artist: str
    album: str
    year: str


class AcoustIDService:
    """Look up albums using the AcoustID web service."""

    URL = "https://api.acoustid.org/v2/lookup"

    def lookup(self, fingerprint: Fingerprint) -> AcoustIDResult:
        """Look up an acoustic fingerprint."""

        response = requests.get(
            self.URL,
            params={
                "format": "json",
                "client": settings.acoustid_api_key,
                "duration": fingerprint.duration,
                "fingerprint": fingerprint.fingerprint,
                "meta": "recordings releases",
            },
            timeout=30,
        )

        print("Status:", response.status_code)
        print("Response:")
        print(response.text)

        response.raise_for_status()

        data = response.json()

        results = data.get("results", [])

        if not results:
            raise RuntimeError("No AcoustID matches were found.")

        best = results[0]

        score = best.get("score", 0.0)

        artist = "Unknown Artist"
        album = "Unknown Album"
        year = "----"

        recordings = best.get("recordings", [])

        if recordings:
            recording = recordings[0]

            artists = recording.get("artists", [])
            if artists:
                artist = artists[0].get("name", artist)

            releases = recording.get("releases", [])
            if releases:
                release = releases[0]

                album = release.get("title", album)

                date = release.get("date", "")
                if date:
                    year = date[:4]

        return AcoustIDResult(
            score=score,
            artist=artist,
            album=album,
            year=year,
        )