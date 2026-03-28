import os
from enum import StrEnum
from typing import Optional

from prompt_toolkit import PromptSession
from rich import print as rprint
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from music_pipeline.models import FileInfo, IdentificationResult, TrackTags


class ReviewAction(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    DISCARD = "discard"
    SKIP = "skip"
    PLAY = "play"
    STOP = "stop"
    QUIT = "quit"


def display_identification(
    file_info: FileInfo,
    result: IdentificationResult,
    auto_approved: bool = False,
    queued_for_review: bool = False,
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

    # Show existing vs proposed tags side by side
    table = Table(title=f"Identification [{conf_color}]({result.confidence}% confidence)[/{conf_color}] {status}")
    table.add_column("Tag", style="cyan")
    table.add_column("Existing", style="dim")
    table.add_column("Proposed", style="bold magenta")

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

    for label, old, new in tag_fields:
        old_str = old or "[dim]-[/dim]"
        new_str = new or "[dim]-[/dim]"
        # Highlight changes
        if old != new and new:
            new_str = f"[bold green]{new}[/bold green]"
        table.add_row(label, old_str, new_str)

    rprint(table)

    # Show reasoning
    rprint(f"\n[bold]Reasoning:[/bold] {result.reasoning}")
    rprint(f"[bold]Sources:[/bold] {', '.join(result.sources_used)}")

    if result.is_dj_mix:
        rprint("[bold yellow]  This appears to be a DJ mix.[/bold yellow]")


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

    rprint()
    rprint(
        "[bold green](A)[/bold green]pprove, "
        "[bold blue](E)[/bold blue]dit, "
        "[bold red](D)[/bold red]iscard, "
        "[bold yellow](S)[/bold yellow]kip, "
        "[bold blue](P)[/bold blue]lay, "
        "st[bold red](o)[/bold red]p, "
        "[bold red](Q)[/bold red]uit"
    )

    choice = Prompt.ask("> ", choices=["a", "e", "d", "s", "p", "o", "q"], default="a")

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
