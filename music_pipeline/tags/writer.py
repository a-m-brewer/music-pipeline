import os
import shutil
from pathlib import Path
from typing import Optional

from mutagen import File
from mutagen._vorbis import VComment
from mutagen.asf import ASFTags
from mutagen.id3 import ID3Tags, TIT2, TPE1, TALB, TDRC, TRCK, TCON, COMM, TPE2, TCOM, TPOS
from mutagen.mp4 import MP4Tags

from music_pipeline.models import TrackTags


def _parse_genres(genre_str: str) -> list[str]:
    """Split a comma-separated genre string into a list of trimmed genre names."""
    return [g.strip() for g in genre_str.split(",") if g.strip()]


def _write_id3_tags(audio, tags: TrackTags) -> bool:
    tag_mapping = [
        ("TIT2", tags.title, TIT2),
        ("TPE1", tags.artist, TPE1),
        ("TALB", tags.album, TALB),
        ("TPE2", tags.album_artist, TPE2),
        ("TCOM", tags.composer, TCOM),
        ("TRCK", tags.track_number and str(tags.track_number), TRCK),
        ("TPOS", tags.disc_number and str(tags.disc_number), TPOS),
    ]

    for frame_id, value, frame_cls in tag_mapping:
        if value and value.strip():
            frame = frame_cls()
            frame.text = [value.strip()]
            audio.tags.setall(frame_id, [frame])

    year_str = str(tags.year) if tags.year is not None else None
    if year_str and year_str.strip():
        tdrc = TDRC()
        tdrc.text = [year_str.strip()]
        audio.tags.setall("TDRC", [tdrc])

    if tags.genre and tags.genre.strip():
        tcon = TCON()
        tcon.genres = _parse_genres(tags.genre)
        audio.tags.setall("TCON", [tcon])

    if tags.comment and tags.comment.strip():
        comm = COMM()
        comm.text = [tags.comment.strip()]
        audio.tags.setall("COMM", [comm])

    return True


def _parse_number_pair(value: str) -> tuple[int, int]:
    """Parse 'n/total' or 'n' into (n, 0)."""
    parts = value.strip().split("/")
    try:
        num = int(parts[0])
        total = int(parts[1]) if len(parts) > 1 else 0
        return (num, total)
    except (ValueError, IndexError):
        return (0, 0)


def _write_mp4_tags(audio, tags: TrackTags) -> bool:
    """Covers M4A, MP4, ALAC."""
    t = audio.tags

    if tags.title and tags.title.strip():
        t["\xa9nam"] = [tags.title.strip()]
    if tags.artist and tags.artist.strip():
        t["\xa9ART"] = [tags.artist.strip()]
    if tags.album and tags.album.strip():
        t["\xa9alb"] = [tags.album.strip()]
    if tags.album_artist and tags.album_artist.strip():
        t["aART"] = [tags.album_artist.strip()]
    if tags.composer and tags.composer.strip():
        t["\xa9wrt"] = [tags.composer.strip()]
    if tags.year and str(tags.year).strip():
        t["\xa9day"] = [str(tags.year).strip()]
    if tags.genre and tags.genre.strip():
        t["\xa9gen"] = _parse_genres(tags.genre)
    if tags.comment and tags.comment.strip():
        t["\xa9cmt"] = [tags.comment.strip()]
    if tags.track_number and str(tags.track_number).strip():
        t["trkn"] = [_parse_number_pair(str(tags.track_number))]
    if tags.disc_number and str(tags.disc_number).strip():
        t["disk"] = [_parse_number_pair(str(tags.disc_number))]

    return True


def _write_vorbis_tags(audio, tags: TrackTags) -> bool:
    """Covers FLAC, OGG Vorbis, OGG Opus, Speex."""
    t = audio.tags
    mapping = [
        ("TITLE", tags.title),
        ("ARTIST", tags.artist),
        ("ALBUM", tags.album),
        ("ALBUMARTIST", tags.album_artist),
        ("COMPOSER", tags.composer),
        ("TRACKNUMBER", tags.track_number and str(tags.track_number)),
        ("DISCNUMBER", tags.disc_number and str(tags.disc_number)),
        ("DATE", str(tags.year) if tags.year is not None else None),
        ("COMMENT", tags.comment),
    ]
    for key, value in mapping:
        if value and value.strip():
            t[key] = [value.strip()]
    if tags.genre and tags.genre.strip():
        t["GENRE"] = _parse_genres(tags.genre)
    return True


def _write_asf_tags(audio, tags: TrackTags) -> bool:
    """Covers WMA / ASF."""
    t = audio.tags
    mapping = [
        ("Title", tags.title),
        ("Author", tags.artist),
        ("WM/AlbumTitle", tags.album),
        ("WM/AlbumArtist", tags.album_artist),
        ("WM/Composer", tags.composer),
        ("WM/TrackNumber", tags.track_number and str(tags.track_number)),
        ("WM/PartOfSet", tags.disc_number and str(tags.disc_number)),
        ("WM/Year", str(tags.year) if tags.year is not None else None),
        ("Description", tags.comment),
    ]
    for key, value in mapping:
        if value and value.strip():
            t[key] = [value.strip()]
    if tags.genre and tags.genre.strip():
        t["WM/Genre"] = _parse_genres(tags.genre)
    return True


def write_tags(file_path: str, tags: TrackTags) -> bool:
    """Write tags to an audio file. Returns True on success."""
    try:
        audio = File(file_path)
    except Exception:
        return False

    if audio is None:
        return False

    if audio.tags is None:
        audio.add_tags()

    if isinstance(audio.tags, MP4Tags):
        if not _write_mp4_tags(audio, tags):
            return False
    elif isinstance(audio.tags, ID3Tags):
        if not _write_id3_tags(audio, tags):
            return False
    elif isinstance(audio.tags, VComment):
        if not _write_vorbis_tags(audio, tags):
            return False
    elif isinstance(audio.tags, ASFTags):
        if not _write_asf_tags(audio, tags):
            return False
    else:
        return False

    audio.save()
    return True


def move_file(source_path: str, dest_dir: str, dest_path: str) -> str:
    """Move a file to a new location, creating directories as needed.

    Returns the actual destination path (handles conflicts by appending numbers).
    """
    os.makedirs(dest_dir, exist_ok=True)

    # Handle filename conflicts
    final_path = dest_path
    if os.path.exists(final_path):
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while os.path.exists(final_path):
            final_path = f"{base} ({counter}){ext}"
            counter += 1

    shutil.move(source_path, final_path)
    return final_path
