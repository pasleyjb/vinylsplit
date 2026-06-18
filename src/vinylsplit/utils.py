import re


def sanitize_filename(name: str) -> str:
    """
    Make a string safe for use as a filename.
    """

    name = re.sub(r'[<>:"/\\|?*]', "-", name)

    name = re.sub(r"\s+", " ", name)

    return name.strip(" .")
