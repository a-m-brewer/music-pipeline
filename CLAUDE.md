# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
just setup
brew install chromaprint          # for AcoustID audio fingerprinting (optional but recommended)
cp config.example.yaml config.yaml  # then fill in API keys
```

## Running

```bash
just          # full pipeline (identify + move)
just scan     # identify without moving files
just review   # review previously identified files
just stats    # show statistics
```

Or directly:
```bash
python -m music_pipeline.main --threshold 80 --source /path/to/music
```

## Architecture

The pipeline processes files in 5 sequential stages, all orchestrated by `pipeline/identifier.py`:

1. **Tag extraction** (`tags/reader.py`) — reads existing ID3 tags and parses clues from filename/parent directory
2. **Fingerprinting** (`pipeline/fingerprint.py`) — AcoustID/Chromaprint audio fingerprint lookup, returns MusicBrainz recording IDs
3. **Database lookups** (`pipeline/musicbrainz.py`, `pipeline/spotify.py`) — metadata enrichment; uses recording IDs from step 2 when available
4. **Web search** (`pipeline/brave_search.py`) — Brave Search targeted at music sites (Spotify, Soundcloud, Discogs); key differentiator for obscure/unlabelled tracks
5. **LLM synthesis** (`pipeline/llm.py`) — sends all gathered data to an OpenAI-compatible LLM, which returns tags + a 0-100 confidence score + reasoning

After identification, `main.py` applies the confidence thresholds from `config.yaml`:
- **≥90**: auto-approve and move
- **70-89**: quick Y/N review
- **<70**: full interactive review with tag editing

All file progress is tracked in a SQLite database (`pipeline_state.db` by default) via `state/db.py`. The pipeline is fully resumable — restarting skips files whose status is not `pending`.

## Key Conventions

**File naming** (matches the original `tag_and_move.py`):
- Filename: `[TRACK_NUMBER] - [TITLE] - [ALBUM] - [ALBUM_ARTIST]` (only present fields included, joined with ` - `)
- Track number zero-padded to 2 digits when numeric
- Directory: `[FIRST_LETTER_OF_ARTIST]/[ALBUM_ARTIST]/[ALBUM]/`
- Discard directory always uses `unknown/` subdirectory

These conventions live in `utils/paths.py`.

**Every identification source is optional** — missing API keys or unavailable services are silently skipped (printed as yellow warnings). The LLM can still synthesize from whatever sources are available; if even the LLM is unavailable, it falls back to the highest-confidence source result directly.

**Shared data models** are in `models.py`: `TrackTags`, `FileInfo`, `SourceResult`, `IdentificationResult`.

## Configuration

`config.yaml` (gitignored) uses `${ENV_VAR}` syntax for API keys. Required keys:
- `LLM_API_KEY` + `llm.base_url` / `llm.model` (any OpenAI-compatible endpoint)
- `BRAVE_API_KEY` for web search
- `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` for Spotify
- `ACOUSTID_API_KEY` for fingerprinting
