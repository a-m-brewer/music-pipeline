from typing import Optional

from rich import print as rprint

from music_pipeline.models import SourceResult, TrackTags


def _get_client(client_id: Optional[str], client_secret: Optional[str]):
    """Create a Spotify client using client credentials flow."""
    if not client_id or not client_secret:
        return None

    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
    except ImportError:
        rprint("[yellow]spotipy not installed — skipping Spotify.[/yellow]")
        return None

    try:
        auth_manager = SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret
        )
        return spotipy.Spotify(auth_manager=auth_manager, retries=0, status_retries=0)
    except Exception as e:
        rprint(f"[yellow]Spotify auth error: {e}[/yellow]")
        return None


def search_spotify(
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> list[SourceResult]:
    """Search Spotify for track metadata."""
    sp = _get_client(client_id, client_secret)
    if not sp:
        return []

    query_parts = []
    if title:
        query_parts.append(f'track:"{title}"')
    if artist:
        query_parts.append(f'artist:"{artist}"')
    if album:
        query_parts.append(f'album:"{album}"')

    if not query_parts:
        return []

    query = " ".join(query_parts)

    try:
        response = sp.search(q=query, type="track", limit=5)
    except Exception as e:
        try:
            from spotipy.exceptions import SpotifyException
            if isinstance(e, SpotifyException) and e.http_status == 429:
                retry_after = getattr(e, "headers", {}) or {}
                retry_after = retry_after.get("Retry-After", "unknown")
                rprint(f"[yellow]Spotify rate limit hit — skipping (retry after {retry_after}s).[/yellow]")
                return []
        except ImportError:
            pass
        rprint(f"[yellow]Spotify search error: {e}[/yellow]")
        return []

    results = []
    tracks = response.get("tracks", {}).get("items", [])

    for i, track in enumerate(tracks):
        tags = TrackTags(
            title=track.get("name"),
            track_number=str(track.get("track_number", "")),
            disc_number=str(track.get("disc_number", "")),
        )

        artists = track.get("artists", [])
        if artists:
            tags.artist = artists[0].get("name")

        album_data = track.get("album", {})
        if album_data:
            tags.album = album_data.get("name")
            release_date = album_data.get("release_date", "")
            if release_date:
                tags.year = release_date[:4]

            album_artists = album_data.get("artists", [])
            if album_artists:
                tags.album_artist = album_artists[0].get("name")

        # Spotify doesn't return genre on track level, try artist
        if artists:
            try:
                artist_data = sp.artist(artists[0]["id"])
                genres = artist_data.get("genres", [])
                if genres:
                    tags.genre = genres[0].title()
            except Exception as e:
                try:
                    from spotipy.exceptions import SpotifyException
                    if isinstance(e, SpotifyException) and e.http_status == 429:
                        rprint("[yellow]Spotify rate limit hit during artist lookup — skipping genres.[/yellow]")
                except ImportError:
                    pass

        # Higher confidence for first result (most relevant)
        confidence = max(0.5, 0.9 - (i * 0.1))

        results.append(
            SourceResult(
                source="spotify",
                tags=tags,
                confidence=confidence,
                raw_data={
                    "spotify_id": track.get("id"),
                    "uri": track.get("uri"),
                    "popularity": track.get("popularity"),
                },
            )
        )

    return results
