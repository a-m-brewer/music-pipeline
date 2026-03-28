#!/usr/bin/env python3

import argparse
import os
import sys

import pygame
from prompt_toolkit import PromptSession
from rich import print as rprint
from rich.prompt import Confirm

from music_pipeline.config import Config, load_config
from music_pipeline.models import IdentificationResult, TrackTags
from music_pipeline.pipeline.identifier import identify_track
from music_pipeline.pipeline.scanner import scan_source
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
    # Write tags
    rprint("[dim]Writing tags...[/dim]")
    if not write_tags(file_info.file_path, tags):
        rprint("[red]Failed to write tags.[/red]")
        db.update_status(file_info.file_path, FileStatus.ERROR)
        return

    # Determine destination
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

    # Move file
    rprint(f"[dim]Moving to: {dest_path}[/dim]")
    actual_path = move_file(file_info.file_path, dest_dir, dest_path)
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
            try:
                pygame.mixer.music.load(file_info.file_path)
                pygame.mixer.music.play(start=0.0)
            except Exception as e:
                rprint(f"[red]Playback error: {e}[/red]")
            continue

        if action == ReviewAction.STOP:
            pygame.mixer.music.stop()
            continue

        if action == ReviewAction.QUIT:
            return False

        if action == ReviewAction.SKIP:
            db.update_status(file_info.file_path, FileStatus.SKIPPED)
            return True

        if action == ReviewAction.APPROVE:
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
            if scan_only:
                db.update_status(file_info.file_path, FileStatus.DISCARDED)
            else:
                process_file(file_info, result, result.tags, config, db, is_discard=True)
            return True

    return True


def run_pipeline(config: Config, db: StateDB, scan_only: bool = False):
    """Main pipeline: scan, identify, review, and move files."""
    rprint("[bold]Scanning source directory...[/bold]")

    # Register all files first
    file_infos = []
    for file_info in scan_source(config.paths.source):
        db.add_file(file_info.file_path)
        file_infos.append(file_info)

    total = len(file_infos)
    rprint(f"[bold]Found {total} audio files.[/bold]")

    # Filter to only pending files
    pending_paths = {f["file_path"] for f in db.get_pending_files()}
    file_infos = [f for f in file_infos if f.file_path in pending_paths]
    rprint(f"[bold]{len(file_infos)} files need processing.[/bold]")

    if not file_infos:
        rprint("[green]All files have been processed![/green]")
        return

    pygame.mixer.init()
    session = PromptSession()
    processed = total - len(file_infos)

    for file_info in file_infos:
        processed += 1
        display_progress(processed, total)

        rprint(f"\n[bold]Identifying:[/bold] {os.path.basename(file_info.file_path)}")

        result = identify_track(file_info, config, db)

        if result is None:
            rprint("[yellow]Could not identify this file.[/yellow]")
            db.update_status(file_info.file_path, FileStatus.ERROR)
            continue

        # Save identification to DB
        db.save_identification(file_info.file_path, result)

        # Check auto-approve threshold
        if result.confidence >= config.thresholds.auto_approve and not result.is_dj_mix:
            display_identification(file_info, result, auto_approved=True)
            if not scan_only:
                process_file(file_info, result, result.tags, config, db)
            else:
                db.update_status(file_info.file_path, FileStatus.APPROVED)
            continue

        # Show result and prompt for review
        display_identification(file_info, result)

        if not handle_review(file_info, result, config, db, session, scan_only):
            rprint("[bold]Bye...[/bold]")
            break

    pygame.mixer.quit()
    rprint("\n[bold green]Session complete.[/bold green]")
    display_stats(db.get_stats())


def run_review(config: Config, db: StateDB):
    """Review previously identified files that haven't been moved yet."""
    identified = db.get_identified_files()
    if not identified:
        rprint("[green]No files pending review.[/green]")
        return

    rprint(f"[bold]{len(identified)} files pending review.[/bold]")

    pygame.mixer.init()
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

    pygame.mixer.quit()
    display_stats(db.get_stats())


def main():
    args = parse_args()

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        rprint(f"[red]{e}[/red]")
        sys.exit(1)

    # Apply CLI overrides
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
            run_pipeline(config, db, scan_only=args.scan_only)
    finally:
        db.close()


if __name__ == "__main__":
    main()
