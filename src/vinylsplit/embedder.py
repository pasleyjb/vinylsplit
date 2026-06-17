from mutagen.flac import FLAC, Picture


class ArtworkEmbedder:

    def embed(
        self,
        filename: str,
        image: bytes,
    ):

        audio = FLAC(filename)

        picture = Picture()

        picture.type = 3          # Front Cover
        picture.mime = "image/jpeg"
        picture.data = image

        audio.clear_pictures()
        audio.add_picture(picture)

        audio.save()