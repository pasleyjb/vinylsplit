from pathlib import Path


class Fingerprinter:
    """Generate acoustic fingerprints."""

    def fingerprint(self, filename: str) -> str:
        """
        Placeholder implementation.

        Future versions will generate a Chromaprint fingerprint.
        """

        path = Path(filename)

        if not path.exists():
            raise FileNotFoundError(path)

        return "fingerprint-not-implemented"