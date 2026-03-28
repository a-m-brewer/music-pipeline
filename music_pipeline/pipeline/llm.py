import json
from typing import Optional

from rich import print as rprint

from music_pipeline.config import LlmConfig
from music_pipeline.models import (
    FileInfo,
    IdentificationResult,
    SourceResult,
    TrackTags,
)
from music_pipeline.pipeline.brave_search import format_search_results

SYSTEM_PROMPT = """You are a music identification assistant. Your job is to determine the correct metadata tags for audio files by analyzing all available information.

You specialize in electronic music, DJ culture, and obscure tracks that may not appear in mainstream databases. You understand that filenames, folder names, and partial tags can all provide valuable clues.

Always respond with valid JSON matching the specified schema. Be conservative with confidence scores — only rate highly when multiple sources agree or you have strong evidence."""

USER_PROMPT_TEMPLATE = """Identify this audio file and determine the correct metadata tags.

**File info:**
- Filename: {filename}
- Parent directory: {parent_dir}
- Duration: {duration}
- File extension: {extension}

**Existing ID3 tags:**
{existing_tags}

**AcoustID/fingerprint matches:**
{acoustid_results}

**MusicBrainz results:**
{musicbrainz_results}

**Spotify results:**
{spotify_results}

**Web search results:**
{brave_results}

Based on ALL available information, determine the most likely correct tags. Cross-reference sources where possible. If sources disagree, explain why you chose one over another.

Respond with ONLY valid JSON (no markdown code fences):
{{
  "title": "track title or null",
  "artist": "artist name or null",
  "album": "album name or null",
  "album_artist": "album artist or null",
  "year": "release year or null",
  "track_number": "track number or null",
  "genre": "genre or null",
  "composer": "composer or null",
  "disc_number": "disc number or null",
  "confidence": 0-100,
  "is_dj_mix": false,
  "reasoning": "brief explanation of how you identified this track and why you chose these tags",
  "sources_used": ["list", "of", "sources", "that", "contributed"]
}}"""


def _format_tags(tags: Optional[TrackTags]) -> str:
    if not tags:
        return "None available"
    d = tags.to_dict()
    if not d:
        return "None available"
    return "\n".join(f"  - {k}: {v}" for k, v in d.items())


def _format_source_results(results: list[SourceResult], source_name: str) -> str:
    filtered = [r for r in results if r.source == source_name]
    if not filtered:
        return "No results"

    lines = []
    for i, r in enumerate(filtered, 1):
        lines.append(f"  Match {i} (confidence: {r.confidence:.2f}):")
        for k, v in r.tags.to_dict().items():
            lines.append(f"    {k}: {v}")
    return "\n".join(lines)


def synthesize_with_llm(
    file_info: FileInfo,
    source_results: list[SourceResult],
    brave_results: list[dict],
    config: LlmConfig,
) -> Optional[tuple[IdentificationResult, int]]:
    """Send all gathered data to LLM for synthesis and tag determination."""
    if not config.api_key:
        rprint("[yellow]No LLM API key configured — skipping LLM synthesis.[/yellow]")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        rprint("[yellow]openai package not installed — skipping LLM synthesis.[/yellow]")
        return None

    client = OpenAI(base_url=config.base_url, api_key=config.api_key)

    duration_str = f"{file_info.duration:.1f}s" if file_info.duration else "unknown"

    prompt = USER_PROMPT_TEMPLATE.format(
        filename=file_info.filename,
        parent_dir=file_info.parent_dir,
        duration=duration_str,
        extension=file_info.extension,
        existing_tags=_format_tags(file_info.existing_tags),
        acoustid_results=_format_source_results(source_results, "acoustid"),
        musicbrainz_results=_format_source_results(source_results, "musicbrainz"),
        spotify_results=_format_source_results(source_results, "spotify"),
        brave_results=format_search_results(brave_results),
    )

    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
    except Exception as e:
        rprint(f"[red]LLM API error: {e}[/red]")
        return None

    content = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        content = "\n".join(lines)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        rprint(f"[red]LLM returned invalid JSON: {e}[/red]")
        rprint(f"[dim]{content}[/dim]")
        return None

    tags = TrackTags(
        title=data.get("title"),
        artist=data.get("artist"),
        album=data.get("album"),
        album_artist=data.get("album_artist"),
        year=data.get("year"),
        track_number=data.get("track_number"),
        genre=data.get("genre"),
        composer=data.get("composer"),
        disc_number=data.get("disc_number"),
    )

    tokens_used = 0
    if response.usage:
        tokens_used = response.usage.total_tokens

    return IdentificationResult(
        tags=tags,
        confidence=data.get("confidence", 0),
        reasoning=data.get("reasoning", ""),
        is_dj_mix=data.get("is_dj_mix", False),
        sources_used=data.get("sources_used", []),
        source_results=source_results,
    ), tokens_used
