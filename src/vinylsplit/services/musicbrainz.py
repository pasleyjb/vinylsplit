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

    @dataclass
    class ReleaseMatch:
        """A compact representation of a MusicBrainz release search result.

        Attributes:
            release_id: The MusicBrainz release UUID.
            artist: The release's primary artist name.
            album: The release title.
            year: The release year (YYYY) or '----' when unknown.
            tracklist: The official ordered list of track titles for the release.
        """

        release_id: str
        artist: str
        album: str
        year: str
        tracklist: list[str]

    def search_release(
        self,
        artist: str | None,
        album: str | None,
    ) -> ReleaseMatch | None:
        """Search for a MusicBrainz release by artist and/or album title.

        The method performs a MusicBrainz `release` search using the provided
        `artist` and/or `album` terms. It returns a `ReleaseMatch` for the best
        candidate found, including the official track list retrieved via
        `tracklist()`. If no suitable releases are found, or neither `artist`
        nor `album` are provided, the method returns `None`.

        Note: This method is intentionally isolated and does not alter any
        application state. It is safe to call from higher-level resolvers.
        """

        # Nothing to search for
        if not artist and not album:
            return None

        # Build a MusicBrainz Lucene-style query
        query_parts: list[str] = []

        if album:
            query_parts.append(f'release:"{album}"')

        if artist:
            query_parts.append(f'artist:"{artist}"')

        query = " AND ".join(query_parts)

        params = {
            "query": query,
            "fmt": "json",
            # fetch a larger candidate set to disambiguate singles vs albums
            "limit": 10,
            "inc": "recordings+artists",
        }

        response = requests.get(
            f"{self.URL}/release",
            params=params,
            headers=self.HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        releases = data.get("releases", [])

        if not releases:
            return None

        # Score each candidate by fetching full release metadata
        from difflib import SequenceMatcher

        def similarity(a: str | None, b: str | None) -> float:
            if not a or not b:
                return 0.0
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()

        candidates: list[tuple[float, dict]] = []

        for candidate in releases:
            rid = candidate.get("id", "")
            if not rid:
                continue

            # Fetch full release metadata including recordings and release-group
            try:
                r = requests.get(
                    f"{self.URL}/release/{rid}",
                    params={"fmt": "json", "inc": "recordings+artists+release-groups"},
                    headers=self.HEADERS,
                    timeout=30,
                )
                r.raise_for_status()
                full = r.json()
            except Exception:
                continue

            # Extract candidate values
            cand_title = full.get("title", "")
            cand_date = full.get("date", "")
            cand_year = cand_date[:4] if cand_date else "----"
            cand_status = full.get("status", "") or full.get("packaging", "")

            # Determine artist name
            cand_artist = "Unknown Artist"
            artists = full.get("artist-credit", [])
            if artists:
                try:
                    cand_artist = artists[0]["artist"]["name"]
                except Exception:
                    pass

            # Track count
            media = full.get("media", [])
            track_count = 0
            for m in media:
                track_count += len(m.get("tracks", []))

            # Release-group primary type (Album/Single/EP)
            rg_type = ""
            rg = full.get("release-group") or {}
            rg_type = rg.get("primary-type", "")

            # Compute score components
            artist_sim = similarity(artist, cand_artist) if artist else 1.0
            title_sim = similarity(album, cand_title) if album else 1.0

            # Track-count heuristic: prefer releases with multiple tracks (not singles)
            track_score = min(track_count / 12.0, 1.0)

            type_bonus = 1.0 if rg_type.lower() == "album" else (0.7 if rg_type.lower() == "ep" else 0.3)
            official_bonus = 1.0 if (full.get("status", "") or "").lower() == "official" else 0.5

            # Age factor: prefer more complete/dated releases? small bonus for having a date
            date_bonus = 1.0 if cand_date else 0.8

            # Weighted sum
            score = (
                0.40 * artist_sim
                + 0.40 * title_sim
                + 0.10 * track_score
                + 0.05 * (type_bonus)
                + 0.05 * (official_bonus * date_bonus)
            )

            candidates.append((score, full))

        if not candidates:
            return None

        # Pick the best-scoring candidate
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_full = candidates[0]

        release_id = best_full.get("id", "")

        # Extract artist name
        artist_name = "Unknown Artist"
        artists = best_full.get("artist-credit", [])
        if artists:
            try:
                artist_name = artists[0]["artist"]["name"]
            except Exception:
                pass

        title = best_full.get("title", "Unknown Album")

        date = best_full.get("date", "")
        year = date[:4] if date else "----"

        # Build tracklist from full metadata
        tracklist: list[str] = []
        for medium in best_full.get("media", []):
            for track in medium.get("tracks", []):
                tracklist.append(track.get("title", ""))

        return MusicBrainzService.ReleaseMatch(
            release_id=release_id,
            artist=artist_name,
            album=title,
            year=year,
            tracklist=tracklist,
        )
