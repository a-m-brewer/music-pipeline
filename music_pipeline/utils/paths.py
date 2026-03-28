import os
import re
from pathlib import Path
from typing import Optional

from music_pipeline.models import TrackTags


# Characters not allowed in filenames
INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')

# Separators that introduce collaborators/features in artist strings
_COLLABORATOR_SPLIT = re.compile(
    r'\s+(?:feat\.?|ft\.?|featuring|vs\.?|&|and|x)\s+.*',
    flags=re.IGNORECASE,
)


def sanitize_filename(name: str) -> str:
    """Remove or replace characters that are invalid in filenames."""
    sanitized = INVALID_CHARS.sub("", name)
    sanitized = sanitized.strip(". ")
    return sanitized if sanitized else "unknown"


def extract_primary_artist(album_artist: str) -> str:
    """Strip collaborators/features from an album_artist string, returning only the primary artist.

    e.g. "Artist ft Other" -> "Artist"
         "Artist A & Artist B" -> "Artist A"
    """
    return _COLLABORATOR_SPLIT.sub("", album_artist).strip()


def build_new_filename(tags: TrackTags, extension: str) -> str:
    """Build filename from tags, matching tag_and_move.py convention.

    Pattern: [TRACK_NUMBER] - [TITLE] - [ALBUM] - [ALBUM_ARTIST]
    Parts are only included if present. Joined with ' - '.
    """
    parts = []

    if tags.track_number and tags.track_number.strip().isdigit():
        parts.append(f"{int(tags.track_number):02d}")

    if tags.title:
        parts.append(tags.title.strip())

    if tags.album:
        parts.append(tags.album.strip())

    if tags.album_artist:
        parts.append(tags.album_artist.strip())

    name = " - ".join(parts) if parts else "unknown"
    name = sanitize_filename(name)

    return f"{name}{extension}"


def build_destination_subdir(tags: TrackTags) -> str:
    """Build destination subdirectory from tags, matching tag_and_move.py convention.

    Pattern: [FIRST_LETTER_OF_ARTIST]/[ALBUM_ARTIST]/[ALBUM]/
    """
    parts = []

    if tags.album_artist and tags.album_artist.strip():
        album_artist = tags.album_artist.strip()
        first_letter = sanitize_filename(album_artist[0].upper())
        parts.append(first_letter)
        parts.append(sanitize_filename(album_artist))

    if tags.album and tags.album.strip():
        parts.append(sanitize_filename(tags.album.strip()))

    return os.path.join(*parts) if parts else "unknown"


def build_full_destination(
    base_dir: str, tags: TrackTags, extension: str
) -> tuple[str, str]:
    """Build the full destination path for a file.

    Returns (directory_path, full_file_path).
    """
    subdir = build_destination_subdir(tags)
    filename = build_new_filename(tags, extension)
    dir_path = os.path.join(base_dir, subdir)
    full_path = os.path.join(dir_path, filename)
    return dir_path, full_path


def build_discard_path(
    discard_dir: str, tags: TrackTags, extension: str
) -> tuple[str, str]:
    """Build the discard path for a file.

    Returns (directory_path, full_file_path).
    """
    filename = build_new_filename(tags, extension)
    dir_path = os.path.join(discard_dir, "unknown")
    full_path = os.path.join(dir_path, filename)
    return dir_path, full_path
