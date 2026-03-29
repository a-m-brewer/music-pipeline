import os
from enum import StrEnum
from typing import Optional

from prompt_toolkit import PromptSession
from rich import print as rprint
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from music_pipeline.models import FileInfo, IdentificationResult, SourceResult, TrackTags


class ReviewAction(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    USE_SOURCE = "use_source"
    CLARIFY = "clarify"
    DISCARD = "discard"
    SKIP = "skip"
    PLAY = "play"
    STOP = "stop"
    QUIT = "quit"
    COMPACT_VIEW = "compact_view"


def _normalize_str(s: str) -> str:
    import re
    return re.sub(r'\s+', ' ', s.strip().lower())


def _compute_source_agreement(result: IdentificationResult) -> dict[str, str]:
    """Return per-field agreement strings, e.g. {"title": "3/4", "artist": "2/4"}.

    Empty dict when source_results is unavailable.
    """
    if not result.source_results:
        return {}
    fields = {"title": result.tags.title, "artist": result.tags.artist}
    agreement: dict[str, str] = {}
    for field_name, llm_value in fields.items():
        if not llm_value:
            continue
        norm_llm = _normalize_str(llm_value)
        sources_with_data = [
            sr for sr in result.source_results
            if getattr(sr.tags, field_name) is not None
        ]
        if not sources_with_data:
            continue
        matching = sum(
            1 for sr in sources_with_data
            if _normalize_str(getattr(sr.tags, field_name) or "") == norm_llm
        )
        agreement[field_name] = f"{matching}/{len(sources_with_data)}"
    return agreement


def display_identification(
    file_info: FileInfo,
    result: IdentificationResult,
    auto_approved: bool = False,
    queued_for_review: bool = False,
    compact: bool = False,  # True = show only changed fields
):
    """Display the identification result for a file."""
    # Confidence color
    if result.confidence >= 90:
        conf_color = "green"
    elif result.confidence >= 70:
        conf_color = "yellow"
    else:
        conf_color = "red"

    if auto_approved:
        status = "[bold green]AUTO-APPROVED[/bold green]"
    elif queued_for_review:
        status = "[bold yellow]QUEUED FOR REVIEW[/bold yellow]"
    else:
        status = ""

    rprint()
    rprint(
        Panel(
            f"[bold]{os.path.basename(file_info.file_path)}[/bold]\n"
            f"[dim]{file_info.file_path}[/dim]\n"
            f"Duration: {file_info.duration:.1f}s" if file_info.duration else "",
            title="File",
        )
    )

    existing = file_info.existing_tags or TrackTags()

    tag_fields = [
        ("Title", existing.title, result.tags.title),
        ("Artist", existing.artist, result.tags.artist),
        ("Album", existing.album, result.tags.album),
        ("Album Artist", existing.album_artist, result.tags.album_artist),
        ("Year", existing.year, result.tags.year),
        ("Track #", existing.track_number, result.tags.track_number),
        ("Genre", existing.genre, result.tags.genre),
        ("Composer", existing.composer, result.tags.composer),
        ("Disc #", existing.disc_number, result.tags.disc_number),
    ]

    # Source agreement (only shown when source_results available)
    agreement = _compute_source_agreement(result)
    agreement_parts = [f"{k.title()}: {v} agree" for k, v in agreement.items()]
    agreement_str = (" | " + " | ".join(agreement_parts)) if agreement_parts else ""

    title_str = (
        f"Identification [{conf_color}]({result.confidence}%)[/{conf_color}]"
        f"{agreement_str} {status}"
    )

    # In compact mode, only show rows that differ; show a summary of changed fields
    changed = [label for label, old, new in tag_fields if old != new and new]

    if compact and changed:
        rprint(f"[dim]{len(changed)} field(s) changed:[/dim] {', '.join(changed)}")
    elif compact:
        rprint("[dim]No tag changes proposed.[/dim]")

    visible_fields = (
        [(label, old, new) for label, old, new in tag_fields if old != new and new]
        if compact
        else tag_fields
    )

    table = Table(title=title_str)
    table.add_column("Tag", style="cyan")
    table.add_column("Existing", style="dim")
    table.add_column("Proposed", style="bold magenta")

    for label, old, new in visible_fields:
        old_str = old or "[dim]-[/dim]"
        new_str = new or "[dim]-[/dim]"
        if old != new and new:
            new_str = f"[bold green]{new}[/bold green]"
        table.add_row(label, old_str, new_str)

    rprint(table)

    if result.source_results:
        display_source_results(result.source_results)

    # Show reasoning
    rprint(f"\n[bold]Reasoning:[/bold] {result.reasoning}")
    rprint(f"[bold]Sources:[/bold] {', '.join(result.sources_used)}")

    if result.is_dj_mix:
        rprint("[bold yellow]  This appears to be a DJ mix.[/bold yellow]")


def display_source_results(source_results: list[SourceResult]):
    """Display a compact table of per-source tag data the LLM received."""
    table = Table(title="Source Data (what the LLM saw)")
    table.add_column("#", style="dim", width=3)
    table.add_column("Source", style="cyan")
    table.add_column("Conf", style="yellow", justify="right")
    table.add_column("Title", style="white")
    table.add_column("Artist", style="white")
    table.add_column("Album", style="white")
    table.add_column("Year", style="white")
    table.add_column("Genre", style="white")

    for i, sr in enumerate(source_results, 1):
        table.add_row(
            str(i),
            sr.source,
            f"{sr.confidence:.0%}",
            sr.tags.title or "[dim]-[/dim]",
            sr.tags.artist or "[dim]-[/dim]",
            sr.tags.album or "[dim]-[/dim]",
            sr.tags.year or "[dim]-[/dim]",
            sr.tags.genre or "[dim]-[/dim]",
        )

    rprint(table)


def select_source_tags(
    source_results: list[SourceResult],
    session: PromptSession,
) -> Optional[TrackTags]:
    """Prompt the user to pick a source result; returns its TrackTags or None to cancel."""
    rprint(f"\n[bold]Pick a source[/bold] (1-{len(source_results)}, or 0 to cancel):")
    raw = session.prompt("  > ").strip()
    try:
        choice = int(raw)
    except ValueError:
        return None
    if choice == 0 or choice > len(source_results):
        return None
    return source_results[choice - 1].tags


def prompt_review(
    file_info: FileInfo,
    result: IdentificationResult,
    session: Optional[PromptSession] = None,
) -> tuple[ReviewAction, Optional[TrackTags]]:
    """Prompt the user to review an identification result.

    Returns (action, edited_tags). edited_tags is only set if action is EDIT.
    """
    if session is None:
        session = PromptSession()

    has_sources = bool(result.source_results)

    rprint()
    rprint(
        "[bold green](A)[/bold green]pprove, "
        "[bold blue](E)[/bold blue]dit, "
        + ("[bold magenta](U)[/bold magenta]se source, " if has_sources else "")
        + "[bold cyan](R)[/bold cyan]efine with LLM, "
        "[bold red](D)[/bold red]iscard, "
        "[bold yellow](S)[/bold yellow]kip, "
        "[bold white](C)[/bold white]ompact, "
        "[bold blue](P)[/bold blue]lay, "
        "st[bold red](o)[/bold red]p, "
        "[bold red](Q)[/bold red]uit"
    )

    choices = ["a", "e", "r", "d", "s", "c", "p", "o", "q"]
    if has_sources:
        choices.append("u")

    choice = Prompt.ask("> ", choices=choices, default="a")

    if choice == "a":
        return ReviewAction.APPROVE, None
    elif choice == "d":
        if Confirm.ask("Discard this file?", default=False):
            return ReviewAction.DISCARD, None
        return prompt_review(file_info, result, session)
    elif choice == "s":
        return ReviewAction.SKIP, None
    elif choice == "p":
        return ReviewAction.PLAY, None
    elif choice == "o":
        return ReviewAction.STOP, None
    elif choice == "q":
        return ReviewAction.QUIT, None
    elif choice == "e":
        edited = edit_tags(result.tags, session)
        return ReviewAction.EDIT, edited
    elif choice == "r":
        return ReviewAction.CLARIFY, None
    elif choice == "c":
        return ReviewAction.COMPACT_VIEW, None
    elif choice == "u":
        selected = select_source_tags(result.source_results, session)
        if selected:
            return ReviewAction.USE_SOURCE, selected
        return prompt_review(file_info, result, session)

    return ReviewAction.SKIP, None


def edit_tags(tags: TrackTags, session: PromptSession) -> TrackTags:
    """Interactive tag editing, pre-filled with proposed values."""
    rprint("\n[bold]Edit tags[/bold] (press Enter to keep current value):\n")

    fields = [
        ("Title", "title"),
        ("Artist", "artist"),
        ("Album", "album"),
        ("Album Artist", "album_artist"),
        ("Year", "year"),
        ("Track Number", "track_number"),
        ("Genre", "genre"),
        ("Composer", "composer"),
        ("Disc Number", "disc_number"),
    ]

    edited = TrackTags()
    for label, attr in fields:
        current = getattr(tags, attr) or ""
        value = session.prompt(f"  {label}: ", default=current)
        if value.strip():
            setattr(edited, attr, value.strip())

    return edited


def display_stats(stats: dict):
    """Display pipeline statistics."""
    table = Table(title="Pipeline Statistics")
    table.add_column("Status", style="cyan")
    table.add_column("Count", style="magenta", justify="right")

    status_labels = {
        "pending": "Pending",
        "identified": "Queued for Review",
        "approved": "Approved",
        "moved": "Moved",
        "discarded": "Discarded",
        "skipped": "Skipped",
        "error": "Error",
    }
    for status, label in status_labels.items():
        count = stats.get(status, 0)
        if count > 0:
            table.add_row(label, str(count))

    total = stats.get("total", 0)
    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")

    rprint(table)

    # API call stats
    api_calls = stats.get("api_calls", {})
    if api_calls:
        api_table = Table(title="API Usage")
        api_table.add_column("Service", style="cyan")
        api_table.add_column("Calls", style="magenta", justify="right")
        api_table.add_column("Tokens", style="yellow", justify="right")

        for service, data in api_calls.items():
            api_table.add_row(
                service,
                str(data["count"]),
                str(data["tokens"]) if data["tokens"] else "-",
            )
        rprint(api_table)


def display_progress(current: int, total: int, status: str = ""):
    """Display a simple progress indicator."""
    pct = (current / total * 100) if total > 0 else 0
    rprint(f"[bold]Progress:[/bold] {current}/{total} ({pct:.1f}%) {status}")
