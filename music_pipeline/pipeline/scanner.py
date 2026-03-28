import glob
import os
from collections.abc import Generator

from rich import print as rprint

from music_pipeline.models import FileInfo
from music_pipeline.tags.reader import build_file_info


def scan_source(source_dir: str) -> Generator[FileInfo, None, None]:
    """Recursively scan source directory for audio files.

    Yields FileInfo objects for each valid audio file found.
    """
    for file_path in glob.iglob(f"{source_dir}/**/*", recursive=True):
        if not os.path.isfile(file_path):
            continue

        file_info = build_file_info(file_path)
        if file_info is not None:
            yield file_info


def count_audio_files(source_dir: str) -> int:
    """Count the total number of audio files in the source directory."""
    count = 0
    for file_path in glob.iglob(f"{source_dir}/**/*", recursive=True):
        if os.path.isfile(file_path):
            try:
                from mutagen import File
                if File(file_path) is not None:
                    count += 1
            except Exception:
                continue
    return count
