import os
from collections.abc import Generator
from pathlib import Path

from music_pipeline.models import FileInfo
from music_pipeline.tags.reader import build_file_info

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".ogg", ".wav", ".aac", ".m4a", ".wma",
    ".opus", ".aiff", ".ape", ".alac", ".dsf", ".dsd",
}


def scan_paths(source_dir: str, skip: set[str] | None = None) -> Generator[str, None, None]:
    """Yield audio file paths by extension check only — no file opens.

    skip: set of absolute paths to exclude (already-processed files from the DB).
    Uses os.walk which is faster than glob for recursive traversal.
    """
    skip = skip or set()
    for root, _dirs, files in os.walk(source_dir):
        for fname in files:
            file_path = os.path.join(root, fname)
            if file_path in skip:
                continue
            if Path(fname).suffix.lower() in AUDIO_EXTENSIONS:
                yield file_path


def scan_source(source_dir: str) -> Generator[FileInfo, None, None]:
    """Recursively scan source directory for audio files.

    Yields FileInfo objects for each valid audio file found.
    """
    for file_path in scan_paths(source_dir):
        file_info = build_file_info(file_path)
        if file_info is not None:
            yield file_info


def count_audio_files(source_dir: str) -> int:
    """Count the total number of audio files in the source directory."""
    return sum(1 for _ in scan_paths(source_dir))
