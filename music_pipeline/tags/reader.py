import re
from pathlib import Path
from typing import Optional

from mutagen import File
from mutagen.id3 import ID3Tags
from mutagen.mp3 import HeaderNotFoundError

from music_pipeline.models import FileInfo, TrackTags


# Common filename patterns: "Artist - Title", "01 - Title", "01. Title", etc.
FILENAME_PATTERNS = [
    # "01 - Artist - Title"
    re.compile(r"^(\d{1,3})\s*[-._]\s*(.+?)\s*[-._]\s*(.+)$"),
    # "Artist - Title"
    re.compile(r"^(.+?)\s*[-_]\s*(.+)$"),
    # "01. Title" or "01 Title"
    re.compile(r"^(\d{1,3})[.\s]\s*(.+)$"),
]


def _extract_tags(audio) -> TrackTags:
    """Extract TrackTags from an already-opened mutagen File object."""
    if audio.tags is None or not isinstance(audio.tags, ID3Tags):
        return TrackTags()

    def get_tag(frame_id: str) -> Optional[str]:
        frames = audio.tags.getall(frame_id)
        if frames and len(frames[0].text) > 0:
            val = str(frames[0].text[0])
            return val if val.strip() else None
        return None

    def get_genres() -> Optional[str]:
        frames = audio.tags.getall("TCON")
        if not frames:
            return None
        genres = frames[0].genres
        if not genres:
            return None
        joined = ", ".join(g for g in genres if g.strip())
        return joined if joined else None

    return TrackTags(
        title=get_tag("TIT2"),
        artist=get_tag("TPE1"),
        album=get_tag("TALB"),
        album_artist=get_tag("TPE2"),
        year=get_tag("TDRC") or get_tag("TYER"),
        track_number=get_tag("TRCK"),
        genre=get_genres(),
        comment=get_tag("COMM"),
        composer=get_tag("TCOM"),
        disc_number=get_tag("TPOS"),
    )


def read_tags(file_path: str) -> Optional[TrackTags]:
    """Read ID3 tags from an audio file. Returns None if file can't be read."""
    try:
        audio = File(file_path)
    except (HeaderNotFoundError, Exception):
        return None

    if audio is None:
        return None

    return _extract_tags(audio)


def get_duration(file_path: str) -> Optional[float]:
    """Get audio duration in seconds."""
    try:
        audio = File(file_path)
        if audio and audio.info:
            return audio.info.length
    except Exception:
        pass
    return None


def parse_filename(filename: str) -> TrackTags:
    """Extract clues from a filename (without extension)."""
    tags = TrackTags()

    for pattern in FILENAME_PATTERNS:
        match = pattern.match(filename)
        if not match:
            continue

        groups = match.groups()
        if len(groups) == 3:
            # "01 - Artist - Title" pattern
            tags.track_number = groups[0].strip()
            tags.artist = groups[1].strip()
            tags.title = groups[2].strip()
        elif len(groups) == 2:
            first, second = groups[0].strip(), groups[1].strip()
            if first.isdigit():
                # "01. Title" pattern
                tags.track_number = first
                tags.title = second
            else:
                # "Artist - Title" pattern
                tags.artist = first
                tags.title = second
        break

    if not tags.title:
        tags.title = filename.strip()

    return tags


def build_file_info(file_path: str) -> Optional[FileInfo]:
    """Build a complete FileInfo object for an audio file."""
    path = Path(file_path)

    try:
        audio = File(file_path)
    except (HeaderNotFoundError, Exception):
        return None

    if audio is None:
        return None

    existing_tags = _extract_tags(audio)
    duration = audio.info.length if audio.info else None

    return FileInfo(
        file_path=file_path,
        filename=path.stem,
        parent_dir=path.parent.name,
        extension=path.suffix,
        duration=duration,
        existing_tags=existing_tags,
    )
