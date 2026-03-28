#!/usr/bin/env python3

import argparse
import os
import sys

from prompt_toolkit import PromptSession
from rich import print as rprint

from music_pipeline import audio
from music_pipeline.config import Config, load_config
from music_pipeline.models import IdentificationResult, TrackTags
from music_pipeline.pipeline.identifier import identify_track
from music_pipeline.pipeline.scanner import scan_paths
from music_pipeline.tags.reader import build_file_info
from music_pipeline.state.db import FileStatus, StateDB
from music_pipeline.tags.writer import move_file, write_tags
from music_pipeline.ui.terminal import (
    ReviewAction,
    display_identification,
    display_progress,
    display_stats,
    prompt_review,
)
from music_pipeline.utils.paths import build_discard_path, build_full_destination


def parse_args():
    parser = argparse.ArgumentParser(description="AI-powered music organization pipeline")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    parser.add_argument("--scan-only", action="store_true", help="Identify files but don't move them")
    parser.add_argument("--review", action="store_true", help="Review previously identified files")
    parser.add_argument("--stats", action="store_true", help="Show pipeline statistics")
    parser.add_argument("--source", type=str, help="Override source directory")
    parser.add_argument("--destination", type=str, help="Override destination directory")
    parser.add_argument("--threshold", type=int, help="Override auto-approve threshold")
    parser.add_argument("--db", type=str, default="pipeline_state.db", help="Path to state database")
    parser.add_argument("--limit", type=int, help="Max files to process this session (for chunking large libraries)")
    return parser.parse_args()


def validate_paths(config: Config):
    if not os.path.isdir(config.paths.source):
        rprint(f"[red]Source directory not found: {config.paths.source}[/red]")
        sys.exit(1)
    if not os.path.isdir(config.paths.destination):
        rprint(f"[red]Destination directory not found: {config.paths.destination}[/red]")
        sys.exit(1)
    if not os.path.isdir(config.paths.discard):
        rprint(f"[red]Discard directory not found: {config.paths.discard}[/red]")
        sys.exit(1)


def process_file(
    file_info,
    result: IdentificationResult,
    tags: TrackTags,
    config: Config,
    db: StateDB,
    is_discard: bool = False,
):
    """Apply tags and move a file to its destination."""
    rprint("[dim]Writing tags...[/dim]")
    if not write_tags(file_info.file_path, tags):
        rprint("[red]Failed to write tags.[/red]")
        db.update_status(file_info.file_path, FileStatus.ERROR)
        return

    if is_discard:
        dest_dir, dest_path = build_discard_path(
            config.paths.discard, tags, file_info.extension
        )
        status = FileStatus.DISCARDED
    else:
        dest_dir, dest_path = build_full_destination(
            config.paths.destination, tags, file_info.extension
        )
        status = FileStatus.MOVED

    rprint(f"[dim]Moving to: {dest_path}[/dim]")
    try:
        actual_path = move_file(file_info.file_path, dest_dir, dest_path)
    except PermissionError as e:
        rprint(f"[red]Permission denied moving file: {e}[/red]")
        db.update_status(file_info.file_path, FileStatus.PENDING)
        return
    db.save_destination(file_info.file_path, actual_path)
    db.update_status(file_info.file_path, status)
    rprint(f"[green]Done: {actual_path}[/green]")


def handle_review(
    file_info,
    result: IdentificationResult,
    config: Config,
    db: StateDB,
    session: PromptSession,
    scan_only: bool = False,
) -> bool:
    """Handle user review of an identification. Returns False if user wants to quit."""
    while True:
        action, edited_tags = prompt_review(file_info, result, session)

        if action == ReviewAction.PLAY:
            audio.play(file_info.file_path)
            continue

        if action == ReviewAction.STOP:
            audio.stop()
            continue

        if action == ReviewAction.QUIT:
            audio.stop()
            return False

        if action == ReviewAction.SKIP:
            db.update_status(file_info.file_path, FileStatus.SKIPPED)
            return True

        if action == ReviewAction.APPROVE:
            audio.stop()
            if scan_only:
                db.update_status(file_info.file_path, FileStatus.APPROVED)
            else:
                process_file(file_info, result, result.tags, config, db)
            return True

        if action == ReviewAction.EDIT:
            if edited_tags:
                result.tags = edited_tags
                display_identification(file_info, result)
            continue

        if action == ReviewAction.DISCARD:
            audio.stop()
            if scan_only:
                db.update_status(file_info.file_path, FileStatus.DISCARDED)
            else:
                process_file(file_info, result, result.tags, config, db, is_discard=True)
            return True

    return True


def run_pipeline(config: Config, db: StateDB, scan_only: bool = False, limit: int | None = None):
    """Main pipeline: scan, identify, review, and move files."""
    rprint("[bold]Scanning source directory...[/bold]")

    # Load non-pending paths once so we skip them during the fast path scan.
    # This avoids opening any file that's already been processed.
    skip = db.get_non_pending_paths()

    batch: list[str] = []
    _BATCH_SIZE = 500
    for file_path in scan_paths(config.paths.source, skip=skip):
        batch.append(file_path)
        if len(batch) >= _BATCH_SIZE:
            db.add_files_batch(batch)
            batch.clear()
    if batch:
        db.add_files_batch(batch)

    total = db.count_pending()
    rprint(f"[bold]{total} files need processing.[/bold]")

    if not total:
        rprint("[green]All files have been processed![/green]")
        return

    processed = 0

    for record in db.iter_pending_files():
        if limit is not None and processed >= limit:
            rprint(f"[yellow]Session limit of {limit} files reached.[/yellow]")
            break

        file_path = record["file_path"]

        if not os.path.exists(file_path):
            rprint(f"[yellow]File no longer exists: {file_path}[/yellow]")
            db.update_status(file_path, FileStatus.ERROR)
            continue

        file_info = build_file_info(file_path)
        if not file_info:
            db.update_status(file_path, FileStatus.ERROR)
            continue

        processed += 1
        display_progress(processed, total)

        rprint(f"\n[bold]Identifying:[/bold] {os.path.basename(file_path)}")

        result = identify_track(file_info, config, db)

        if result is None:
            rprint("[yellow]Could not identify this file.[/yellow]")
            db.update_status(file_path, FileStatus.ERROR)
            continue

        db.save_identification(file_path, result)

        if result.confidence >= config.thresholds.auto_approve and not result.is_dj_mix:
            display_identification(file_info, result, auto_approved=True)
            if not scan_only:
                process_file(file_info, result, result.tags, config, db)
            else:
                db.update_status(file_path, FileStatus.APPROVED)
            continue

        display_identification(file_info, result, queued_for_review=True)
        rprint("[yellow]Confidence below threshold — queued for review. Run `just review` when ready.[/yellow]")

    rprint("\n[bold green]Session complete.[/bold green]")
    display_stats(db.get_stats())


def run_review(config: Config, db: StateDB):
    """Review previously identified files that haven't been moved yet."""
    identified = db.get_identified_files()
    if not identified:
        rprint("[green]No files pending review.[/green]")
        return

    rprint(f"[bold]{len(identified)} files pending review.[/bold]")

    session = PromptSession()

    for record in identified:
        file_path = record["file_path"]
        if not os.path.exists(file_path):
            rprint(f"[yellow]File no longer exists: {file_path}[/yellow]")
            db.update_status(file_path, FileStatus.ERROR)
            continue

        from music_pipeline.tags.reader import build_file_info
        file_info = build_file_info(file_path)
        if not file_info:
            continue

        result = db.load_identification(file_path)
        if not result:
            continue

        display_identification(file_info, result)

        if not handle_review(file_info, result, config, db, session):
            rprint("[bold]Bye...[/bold]")
            break

    display_stats(db.get_stats())


def main():
    args = parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        rprint(f"[red]{e}[/red]")
        sys.exit(1)

    if args.source:
        config.paths.source = args.source
    if args.destination:
        config.paths.destination = args.destination
    if args.threshold:
        config.thresholds.auto_approve = args.threshold

    db = StateDB(args.db)

    try:
        if args.stats:
            display_stats(db.get_stats())
        elif args.review:
            validate_paths(config)
            run_review(config, db)
        else:
            validate_paths(config)
            run_pipeline(config, db, scan_only=args.scan_only, limit=args.limit)
    finally:
        db.close()


if __name__ == "__main__":
    main()
