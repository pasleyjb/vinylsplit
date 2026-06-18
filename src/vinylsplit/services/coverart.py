import requests


class CoverArtService:
    """Download album artwork from the Cover Art Archive."""

    URL = "https://coverartarchive.org/release"

    def download(self, release_id: str) -> bytes | None:

        response = requests.get(
            f"{self.URL}/{release_id}/front",
            timeout=30,
        )

        if response.status_code != 200:
            return None

        return response.content
