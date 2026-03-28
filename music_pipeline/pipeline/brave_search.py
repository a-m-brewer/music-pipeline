from typing import Optional

import httpx
from rich import print as rprint

from music_pipeline.models import SourceResult, TrackTags

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def search_brave(
    query: str,
    api_key: Optional[str] = None,
    count: int = 5,
) -> list[dict]:
    """Perform a Brave web search and return raw results."""
    if not api_key:
        return []

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }

    params = {"q": query, "count": count}

    try:
        response = httpx.get(BRAVE_SEARCH_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("web", {}).get("results", [])
    except Exception as e:
        rprint(f"[yellow]Brave search error: {e}[/yellow]")
        return []


def search_for_track(
    title: Optional[str] = None,
    artist: Optional[str] = None,
    filename: Optional[str] = None,
    api_key: Optional[str] = None,
) -> list[dict]:
    """Search for a music track using Brave Search.

    Constructs targeted queries and returns combined results.
    """
    if not api_key:
        return []

    all_results = []

    # Query 1: Targeted music site search
    search_term = ""
    if artist and title:
        search_term = f'"{artist}" "{title}"'
    elif title:
        search_term = f'"{title}"'
    elif filename:
        search_term = f'"{filename}"'

    if search_term:
        site_query = f"{search_term} site:spotify.com OR site:soundcloud.com OR site:discogs.com OR site:beatport.com"
        all_results.extend(search_brave(site_query, api_key, count=5))

        # Query 2: General music search
        general_query = f"{search_term} music track"
        all_results.extend(search_brave(general_query, api_key, count=5))

    return all_results


def format_search_results(results: list[dict]) -> str:
    """Format Brave search results into a text summary for the LLM."""
    if not results:
        return "No web search results found."

    lines = []
    seen_urls = set()
    for r in results:
        url = r.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title = r.get("title", "")
        description = r.get("description", "")
        lines.append(f"- [{title}]({url}): {description}")

    return "\n".join(lines) if lines else "No web search results found."
