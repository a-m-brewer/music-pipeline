from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrackTags:
    """Represents the ID3 tags for a track."""
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    year: Optional[str] = None
    track_number: Optional[str] = None
    genre: Optional[str] = None
    comment: Optional[str] = None
    composer: Optional[str] = None
    disc_number: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def summary(self) -> str:
        parts = []
        if self.artist:
            parts.append(self.artist)
        if self.title:
            parts.append(self.title)
        if self.album:
            parts.append(self.album)
        return " - ".join(parts) if parts else "(no tags)"


@dataclass
class FileInfo:
    """Information about an audio file before identification."""
    file_path: str
    filename: str
    parent_dir: str
    extension: str
    duration: Optional[float] = None
    existing_tags: Optional[TrackTags] = None


@dataclass
class SourceResult:
    """Result from a single identification source."""
    source: str  # 'acoustid', 'musicbrainz', 'spotify', 'brave'
    tags: TrackTags
    confidence: float  # 0.0 - 1.0
    raw_data: Optional[dict] = None


@dataclass
class IdentificationResult:
    """Final identification result after LLM synthesis."""
    tags: TrackTags
    confidence: int  # 0-100
    reasoning: str
    is_dj_mix: bool = False
    sources_used: list[str] = field(default_factory=list)
    source_results: list[SourceResult] = field(default_factory=list)
