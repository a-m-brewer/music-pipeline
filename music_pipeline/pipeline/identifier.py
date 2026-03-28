from typing import Optional

from rich import print as rprint

from music_pipeline.config import Config
from music_pipeline.models import FileInfo, IdentificationResult, SourceResult
from music_pipeline.pipeline.brave_search import search_for_track
from music_pipeline.pipeline.fingerprint import get_musicbrainz_ids, lookup_acoustid
from music_pipeline.pipeline.llm import synthesize_with_llm
from music_pipeline.pipeline.musicbrainz import (
    lookup_by_recording_id,
    search_by_metadata,
)
from music_pipeline.pipeline.spotify import search_spotify
from music_pipeline.state.db import StateDB
from music_pipeline.tags.reader import parse_filename
from music_pipeline.utils.paths import extract_primary_artist


def identify_track(
    file_info: FileInfo,
    config: Config,
    db: StateDB,
) -> Optional[IdentificationResult]:
    """Run the full identification pipeline for a single track.

    Stages:
    1. Extract clues from existing tags + filename
    2. AcoustID fingerprint lookup
    3. MusicBrainz + Spotify database lookups
    4. Brave web search
    5. LLM synthesis of all results
    """
    file_record = db.get_file(file_info.file_path)
    file_id = file_record["id"] if file_record else None

    source_results: list[SourceResult] = []

    # --- Clues from existing data ---
    existing = file_info.existing_tags
    filename_tags = parse_filename(file_info.filename)
    search_title = (existing and existing.title) or filename_tags.title
    search_artist = (existing and existing.artist) or filename_tags.artist
    search_album = existing and existing.album

    # --- Stage 2: AcoustID fingerprint ---
    rprint("[dim]  AcoustID fingerprint...[/dim]")
    acoustid_results = lookup_acoustid(
        file_info.file_path, config.api_keys.acoustid
    )
    source_results.extend(acoustid_results)
    db.log_api_call("acoustid", file_id)

    # --- Stage 3a: MusicBrainz ---
    rprint("[dim]  MusicBrainz lookup...[/dim]")
    mb_ids = get_musicbrainz_ids(acoustid_results)
    for mb_id in mb_ids[:3]:  # Limit to top 3
        mb_result = lookup_by_recording_id(mb_id)
        if mb_result:
            source_results.append(mb_result)
    db.log_api_call("musicbrainz", file_id)

    # Also search by metadata if we have clues
    if search_title or search_artist:
        mb_search_results = search_by_metadata(
            title=search_title, artist=search_artist, album=search_album
        )
        source_results.extend(mb_search_results[:3])

    # --- Stage 3b: Spotify ---
    rprint("[dim]  Spotify search...[/dim]")
    spotify_results = search_spotify(
        title=search_title,
        artist=search_artist,
        album=search_album,
        client_id=config.api_keys.spotify_client_id,
        client_secret=config.api_keys.spotify_client_secret,
    )
    source_results.extend(spotify_results)
    db.log_api_call("spotify", file_id)

    # --- Stage 4: Brave web search ---
    rprint("[dim]  Web search...[/dim]")
    brave_results = search_for_track(
        title=search_title,
        artist=search_artist,
        filename=file_info.filename,
        api_key=config.api_keys.brave,
    )
    db.log_api_call("brave", file_id)

    # --- Stage 5: LLM synthesis ---
    rprint("[dim]  LLM synthesis...[/dim]")
    llm_result = synthesize_with_llm(
        file_info=file_info,
        source_results=source_results,
        brave_results=brave_results,
        config=config.llm,
    )

    if llm_result is None:
        # If LLM fails, try to build a result from the best source
        return _fallback_result(source_results)

    result, tokens_used = llm_result
    db.log_api_call("llm", file_id, tokens_used)

    return _normalize_result(result)


def _normalize_result(result: IdentificationResult) -> IdentificationResult:
    """Enforce album_artist = single primary artist only (no features/collaborators)."""
    if result.tags.album_artist:
        result.tags.album_artist = extract_primary_artist(result.tags.album_artist)
    return result


def _fallback_result(
    source_results: list[SourceResult],
) -> Optional[IdentificationResult]:
    """Build a basic result from source data when LLM is unavailable."""
    if not source_results:
        return None

    # Pick the highest confidence source result
    best = max(source_results, key=lambda r: r.confidence)

    return _normalize_result(IdentificationResult(
        tags=best.tags,
        confidence=int(best.confidence * 100),
        reasoning=f"Fallback: best match from {best.source} (LLM unavailable)",
        sources_used=[best.source],
        source_results=source_results,
    ))
