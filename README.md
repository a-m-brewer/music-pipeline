# music-pipeline

An AI-powered music organization pipeline that identifies untagged or poorly-tagged audio files and organizes them into a clean directory structure. Combines audio fingerprinting, music databases, web search, and an LLM to handle even obscure or unlabelled tracks.

## How it works

Each file passes through up to five identification stages:

1. **Tag extraction** — reads existing ID3 tags and parses clues from the filename and parent directory
2. **Fingerprinting** — AcoustID/Chromaprint audio fingerprint lookup, returns MusicBrainz recording IDs
3. **Database lookups** — MusicBrainz and Spotify API metadata enrichment
4. **Web search** — Brave Search targeting Spotify, SoundCloud, Discogs, and Beatport
5. **LLM synthesis** — sends all gathered data to an OpenAI-compatible LLM, which returns tags + a 0–100 confidence score + reasoning

After identification, files are triaged by confidence:

| Score | Action |
|-------|--------|
| ≥90 | Auto-approved — tags written and file moved |
| 70–89 | Quick Y/N review |
| <70 | Full interactive review with tag editing |

All progress is saved to a SQLite database so the pipeline is fully resumable — restarting skips files that have already been processed.

## Installation

**Requirements:** Python 3.11+, [just](https://github.com/casey/just)

```bash
just setup
```

`just setup` installs Chromaprint automatically (macOS via Homebrew, Debian/Ubuntu via apt, Fedora via dnf). On other Linux distributions, install `chromaprint-tools` manually.

Then copy and fill in the config:

```bash
cp config.example.yaml config.yaml
```

## Configuration

Edit `config.yaml` — API keys can be set inline or as environment variables using `${VAR_NAME}` syntax.

```yaml
paths:
  source: /Volumes/Media/Music Old       # Where to read files from
  destination: /Volumes/Media/Music       # Where organized files go
  discard: /Volumes/Media/Music Discard  # Where unwanted files go

api_keys:
  acoustid: ${ACOUSTID_API_KEY}
  spotify_client_id: ${SPOTIFY_CLIENT_ID}
  spotify_client_secret: ${SPOTIFY_CLIENT_SECRET}
  brave: ${BRAVE_API_KEY}

llm:
  base_url: https://api.openai.com/v1   # Any OpenAI-compatible endpoint
  api_key: ${LLM_API_KEY}
  model: gpt-4o

thresholds:
  auto_approve: 90
  quick_review: 70
```

**All API keys are optional.** Missing keys silently skip that identification stage — the LLM can still synthesize a result from whatever sources are available. However, more sources = better accuracy, especially for obscure tracks.

### Getting API keys

| Service | Purpose | Link |
|---------|---------|------|
| AcoustID | Audio fingerprinting | [acoustid.org/login](https://acoustid.org/login) |
| Spotify | Track/album metadata | [developer.spotify.com](https://developer.spotify.com/dashboard) |
| Brave Search | Web search for obscure tracks | [brave.com/search/api](https://brave.com/search/api/) |
| OpenAI / LLM | Final synthesis + confidence scoring | Any OpenAI-compatible endpoint |

## Usage

```bash
just          # full pipeline: identify + move files
just scan     # identify only, no files moved (safe to run first)
just review   # review previously identified files below your threshold
just stats    # show status counts and API usage
```

Or with the Python module directly for more control:

```bash
python -m music_pipeline.main --source /path/to/music --threshold 80
python -m music_pipeline.main --limit 100   # process 100 files then stop
python -m music_pipeline.main --config other-config.yaml
```

All CLI flags:

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to config file (default: `config.yaml`) |
| `--source DIR` | Override source directory from config |
| `--destination DIR` | Override destination directory from config |
| `--threshold N` | Override auto-approve threshold |
| `--db PATH` | Path to state database (default: `pipeline_state.db`) |
| `--limit N` | Stop after processing N files — useful for large libraries |
| `--scan-only` | Identify files but do not move them |
| `--review` | Review previously identified files |
| `--stats` | Show statistics and exit |

## Output structure

Files are organized in the destination directory as:

```
destination/
└── A/
    └── Artist Name/
        └── Album Title/
            ├── 01 - Track One - Album Title - Artist Name.mp3
            └── 02 - Track Two - Album Title - Artist Name.flac
```

- Directory: `[FIRST_LETTER]/[ALBUM_ARTIST]/[ALBUM]/`
- Filename: `[TRACK_NUMBER] - [TITLE] - [ALBUM] - [ALBUM_ARTIST]` (only present fields included)
- Track numbers are zero-padded to 2 digits
- Discarded files go to `discard/unknown/`

## Interactive review

During review, each file is shown with a side-by-side comparison of existing and proposed tags, the LLM's reasoning, confidence score, and the sources that contributed.

```
(A)pprove   apply tags and move the file
(E)dit      edit individual tag fields before approving
(D)iscard   move to discard directory
(S)kip      leave for later
(P)lay      play the audio file
st(O)p      stop playback
(Q)uit      exit review session
```

## Supported formats

MP3, FLAC, OGG, WAV, AAC, M4A, WMA, Opus, AIFF, APE, ALAC, DSF, DSD

## Tips for large libraries

- Run `just scan` first — identifies everything without moving files, so you can review results before committing
- Use `--limit 200` to process in chunks if your library is large or you want to stay within API rate limits
- The database (`pipeline_state.db`) tracks everything — you can safely stop and restart at any time
- Run `just stats` to see how many files are pending, identified, approved, moved, etc.
- If a file was processed incorrectly, you can manually update its status in the database to `pending` to reprocess it
