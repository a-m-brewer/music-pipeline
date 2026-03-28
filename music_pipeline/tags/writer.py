import os
import shutil
from pathlib import Path
from typing import Optional

from mutagen import File
from mutagen.id3 import ID3Tags, TIT2, TPE1, TALB, TDRC, TRCK, TCON, COMM, TPE2, TCOM, TPOS

from music_pipeline.models import TrackTags


def write_tags(file_path: str, tags: TrackTags) -> bool:
    """Write ID3 tags to an audio file. Returns True on success."""
    try:
        audio = File(file_path)
    except Exception:
        return False

    if audio is None:
        return False

    if audio.tags is None:
        audio.add_tags()

    if not isinstance(audio.tags, ID3Tags):
        return False

    tag_mapping = [
        ("TIT2", tags.title, TIT2),
        ("TPE1", tags.artist, TPE1),
        ("TALB", tags.album, TALB),
        ("TPE2", tags.album_artist, TPE2),
        ("TCOM", tags.composer, TCOM),
        ("TRCK", tags.track_number, TRCK),
        ("TPOS", tags.disc_number, TPOS),
    ]

    for frame_id, value, frame_cls in tag_mapping:
        if value and value.strip():
            frame = frame_cls()
            frame.text = [value.strip()]
            audio.tags.setall(frame_id, [frame])

    if tags.year and tags.year.strip():
        tdrc = TDRC()
        tdrc.text = [tags.year.strip()]
        audio.tags.setall("TDRC", [tdrc])

    if tags.genre and tags.genre.strip():
        tcon = TCON()
        tcon.genres = [tags.genre.strip()]
        audio.tags.setall("TCON", [tcon])

    if tags.comment and tags.comment.strip():
        comm = COMM()
        comm.text = [tags.comment.strip()]
        audio.tags.setall("COMM", [comm])

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
