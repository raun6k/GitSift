"""cli.py — argparse entry point for the gitsift command."""

from __future__ import annotations

import argparse
import datetime
import sys
from typing import Optional

from rich.console import Console

from gitsift.commit_walker import walk_commits
from gitsift.aggregator import analyse
from gitsift import renderers


def _parse_date(value: str) -> datetime.datetime:
    """Parse an ISO date string (YYYY-MM-DD or full ISO-8601) into a datetime."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Invalid date format: '{value}'. Expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS."
    )


def build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser."""
    parser = argparse.ArgumentParser(
        prog="gitsift",
        description="Analyse a Git repository and surface churn, contributor, and activity insights.",
    )
    parser.add_argument(
        "--repo",
        metavar="PATH",
        default=".",
        help="Path to the Git repository to analyse (default: current directory).",
    )
    parser.add_argument(
        "--since",
        metavar="DATE",
        type=_parse_date,
        default=None,
        help="Only include commits on or after this date (ISO format: YYYY-MM-DD).",
    )
    parser.add_argument(
        "--until",
        metavar="DATE",
        type=_parse_date,
        default=None,
        help="Only include commits on or before this date (ISO format: YYYY-MM-DD).",
    )
    parser.add_argument(
        "--top",
        metavar="N",
        type=int,
        default=20,
        help="Number of results to show in each table (default: 20).",
    )
    parser.add_argument(
        "--charts",
        action="store_true",
        help="Generate PNG chart files in the current directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Output analysis as structured JSON to stdout instead of tables.",
    )
    parser.add_argument(
        "--group-by",
        choices=["day", "week", "month"],
        default="week",
        dest="group_by",
        help="Time-series grouping granularity (default: week).",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        default=".",
        help="Directory to save PNG charts (default: current directory).",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable the progress bar (useful in non-interactive environments).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    """Entry point for the gitsift CLI command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    console = Console(stderr=True)  # status/progress goes to stderr; data to stdout

    # --- Walk commits ---
    try:
        commits = walk_commits(
            repo_path=args.repo,
            since=args.since,
            until=args.until,
            show_progress=not args.no_progress and not args.output_json,
        )
    except Exception as exc:
        console.print(f"[bold red]Error reading repository:[/bold red] {exc}")
        sys.exit(1)

    if not commits:
        console.print("[yellow]No commits found for the given filters.[/yellow]")
        sys.exit(0)

    # --- Aggregate ---
    result = analyse(commits, group_by=args.group_by)

    # Attach raw datetimes for the heatmap renderer.
    result._commit_datetimes = [c.datetime for c in commits]  # type: ignore[attr-defined]

    # --- Render ---
    if args.output_json:
        print(renderers.render_json(result))
    elif args.charts:
        paths = renderers.render_charts(result, top=args.top, output_dir=args.output_dir)
        for p in paths:
            console.print(f"[green]Chart saved:[/green] {p}")
        # Also print terminal tables for context
        renderers.render_terminal(result, top=args.top, console=Console())
    else:
        renderers.render_terminal(result, top=args.top, console=Console())


if __name__ == "__main__":
    main()
