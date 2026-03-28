from typing import Optional

from rich import print as rprint

from music_pipeline.models import SourceResult, TrackTags

_INITIALIZED = False


def _ensure_init():
    global _INITIALIZED
    if _INITIALIZED:
        return

    try:
        import musicbrainzngs
        musicbrainzngs.set_useragent(
            "music-pipeline", "0.1.0", "https://github.com/a-m-brewer/music-pipeline"
        )
        _INITIALIZED = True
    except ImportError:
        rprint("[yellow]musicbrainzngs not installed — skipping MusicBrainz.[/yellow]")


def lookup_by_recording_id(recording_id: str) -> Optional[SourceResult]:
    """Fetch full metadata for a MusicBrainz recording ID."""
    _ensure_init()

    try:
        import musicbrainzngs
    except ImportError:
        return None

    try:
        result = musicbrainzngs.get_recording_by_id(
            recording_id,
            includes=["artists", "releases", "tags"],
        )
    except Exception as e:
        rprint(f"[yellow]MusicBrainz lookup error: {e}[/yellow]")
        return None

    recording = result.get("recording", {})
    tags = TrackTags(title=recording.get("title"))

    artist_credit = recording.get("artist-credit", [])
    if artist_credit:
        tags.artist = artist_credit[0].get("name") or artist_credit[0].get("artist", {}).get("name")

    releases = recording.get("release-list", [])
    if releases:
        release = releases[0]
        tags.album = release.get("title")
        tags.year = release.get("date", "")[:4] or None

        # Try to get track number from medium-list
        medium_list = release.get("medium-list", [])
        if medium_list:
            medium = medium_list[0]
            tags.disc_number = str(medium.get("position", ""))
            track_list = medium.get("track-list", [])
            if track_list:
                tags.track_number = str(track_list[0].get("position", ""))

    mb_tags = recording.get("tag-list", [])
    if mb_tags:
        sorted_tags = sorted(mb_tags, key=lambda t: int(t.get("count", 0)), reverse=True)
        tags.genre = sorted_tags[0].get("name")

    return SourceResult(
        source="musicbrainz",
        tags=tags,
        confidence=0.8,
        raw_data={"recording_id": recording_id, "recording": recording},
    )


def search_by_metadata(
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
) -> list[SourceResult]:
    """Search MusicBrainz by title/artist/album."""
    _ensure_init()

    try:
        import musicbrainzngs
    except ImportError:
        return []

    query_parts = []
    if title:
        query_parts.append(f'recording:"{title}"')
    if artist:
        query_parts.append(f'artist:"{artist}"')
    if album:
        query_parts.append(f'release:"{album}"')

    if not query_parts:
        return []

    try:
        result = musicbrainzngs.search_recordings(
            query=" AND ".join(query_parts),
            limit=5,
        )
    except Exception as e:
        rprint(f"[yellow]MusicBrainz search error: {e}[/yellow]")
        return []

    results = []
    for recording in result.get("recording-list", []):
        score = int(recording.get("ext:score", 0)) / 100.0

        tags = TrackTags(title=recording.get("title"))

        artist_credit = recording.get("artist-credit", [])
        if artist_credit:
            tags.artist = artist_credit[0].get("name") or artist_credit[0].get("artist", {}).get("name")

        releases = recording.get("release-list", [])
        if releases:
            tags.album = releases[0].get("title")
            tags.year = releases[0].get("date", "")[:4] or None

        results.append(
            SourceResult(
                source="musicbrainz",
                tags=tags,
                confidence=score,
                raw_data={"recording": recording},
            )
        )

    return results
