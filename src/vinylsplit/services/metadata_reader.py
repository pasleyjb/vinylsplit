"""Read metadata from the original recording."""

from pathlib import Path

from mutagen import File

from vinylsplit.metadata import RecordingMetadata


class MetadataReader:
    """Reads embedded metadata from an audio recording."""

    def read(self, filename: str) -> RecordingMetadata:

        audio = File(filename)

        metadata = RecordingMetadata(path=Path(filename))

        if audio is None:
            return metadata

        metadata.artist = self._tag(audio, "artist")
        metadata.album = self._tag(audio, "album")
        metadata.album_artist = self._tag(audio, "albumartist")
        metadata.title = self._tag(audio, "title")
        metadata.genre = self._tag(audio, "genre")
        metadata.year = self._tag(audio, "date")
        metadata.comment = self._tag(audio, "comment")

        if hasattr(audio.info, "length"):
            metadata.duration = audio.info.length

        if hasattr(audio.info, "sample_rate"):
            metadata.sample_rate = audio.info.sample_rate

        if hasattr(audio.info, "channels"):
            metadata.channels = audio.info.channels

        if hasattr(audio.info, "bits_per_sample"):
            metadata.bits_per_sample = audio.info.bits_per_sample

        metadata.track_total = self._track_total(audio)
        metadata.disc_number = self._disc_number(audio)
        metadata.has_artwork = self._has_artwork(audio)

        return metadata

    def _tag(self, audio, key: str) -> str:
        value = audio.get(key)

        if not value:
            return ""

        return str(value[0])

    def _track_total(self, audio) -> int:
        value = audio.get("tracktotal")

        if value:
            return int(value[0])

        value = audio.get("tracknumber")

        if value and "/" in str(value[0]):
            return int(str(value[0]).split("/")[1])

        return 0

    def _disc_number(self, audio) -> int:
        value = audio.get("discnumber")

        if not value:
            return 1

        return int(str(value[0]).split("/")[0])

    def _has_artwork(self, audio) -> bool:
        return hasattr(audio, "pictures") and len(audio.pictures) > 0