import shutil
from typing import Optional

from rich import print as rprint

from music_pipeline.models import SourceResult, TrackTags

FPCALC_AVAILABLE = shutil.which("fpcalc") is not None


def lookup_acoustid(
    file_path: str, api_key: Optional[str] = None
) -> list[SourceResult]:
    """Look up a track using AcoustID audio fingerprinting.

    Requires fpcalc (Chromaprint) to be installed.
    Returns a list of potential matches with confidence scores.
    """
    if not api_key:
        return []

    if not FPCALC_AVAILABLE:
        rprint("[yellow]fpcalc not found — skipping AcoustID fingerprinting.[/yellow]")
        rprint("[yellow]Install Chromaprint: brew install chromaprint[/yellow]")
        return []

    try:
        import acoustid
    except ImportError:
        rprint("[yellow]pyacoustid not installed — skipping AcoustID.[/yellow]")
        return []

    results = []
    try:
        matches = acoustid.match(api_key, file_path, parse=False)

        if not matches or "results" not in matches:
            return []

        for match in matches.get("results", []):
            score = match.get("score", 0)
            recordings = match.get("recordings", [])

            for recording in recordings:
                tags = TrackTags(title=recording.get("title"))

                artists = recording.get("artists", [])
                if artists:
                    tags.artist = artists[0].get("name")

                release_groups = recording.get("releasegroups", [])
                if release_groups:
                    rg = release_groups[0]
                    tags.album = rg.get("title")
                    if rg.get("type") == "Album" and rg.get("artists"):
                        tags.album_artist = rg["artists"][0].get("name")

                results.append(
                    SourceResult(
                        source="acoustid",
                        tags=tags,
                        confidence=score,
                        raw_data={
                            "acoustid_id": match.get("id"),
                            "recording_id": recording.get("id"),
                            "score": score,
                        },
                    )
                )

    except acoustid.WebServiceError as e:
        rprint(f"[yellow]AcoustID error: {e}[/yellow]")
    except Exception as e:
        rprint(f"[yellow]AcoustID unexpected error: {e}[/yellow]")

    return results


def get_musicbrainz_ids(results: list[SourceResult]) -> list[str]:
    """Extract MusicBrainz recording IDs from AcoustID results."""
    ids = []
    for r in results:
        if r.raw_data and r.raw_data.get("recording_id"):
            ids.append(r.raw_data["recording_id"])
    return ids
