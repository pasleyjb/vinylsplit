import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings."""

    @property
    def acoustid_api_key(self) -> str:
        """Return the AcoustID API key."""

        key = os.getenv("ACOUSTID_API_KEY")

        if not key:
            raise RuntimeError(
                "ACOUSTID_API_KEY not found. Please create a .env file."
            )

        return key


settings = Settings()