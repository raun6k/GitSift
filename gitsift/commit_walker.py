"""commit_walker.py — iterate Git history and extract per-commit diff stats."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Iterator, Optional

import git
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn


@dataclass
class FileChange:
    """Lines added/deleted for a single file in one commit."""

    path: str
    lines_added: int
    lines_deleted: int


@dataclass
class CommitInfo:
    """Metadata and diff stats for a single commit."""

    hash: str
    author_name: str
    author_email: str
    datetime: datetime.datetime
    files_changed: list[FileChange] = field(default_factory=list)


def _parse_diff_stats(commit: git.Commit) -> list[FileChange]:
    """Return per-file line-change counts for *commit*.

    Uses ``commit.stats.files`` (equivalent to ``git show --stat``) which is
    fast and works correctly for both normal commits and the initial commit.
    Merge commits (more than one parent) are skipped to avoid double-counting.
    """
    if len(commit.parents) > 1:
        return []

    changes: list[FileChange] = []
    try:
        for filepath, stat in commit.stats.files.items():
            changes.append(FileChange(
                path=filepath,
                lines_added=stat.get("insertions", 0),
                lines_deleted=stat.get("deletions", 0),
            ))
    except Exception:
        pass

    return changes


def walk_commits(
    repo_path: str,
    since: Optional[datetime.datetime] = None,
    until: Optional[datetime.datetime] = None,
    show_progress: bool = True,
) -> list[CommitInfo]:
    """Walk all commits in *repo_path* and return a list of :class:`CommitInfo`.

    Args:
        repo_path: Path to the local Git repository (the working tree root or .git dir).
        since: If provided, only include commits on or after this datetime (UTC-aware or naive).
        until: If provided, only include commits on or before this datetime.
        show_progress: Show a Rich progress bar while walking.

    Returns:
        List of :class:`CommitInfo` objects ordered newest-first (default Git log order).
    """
    repo = git.Repo(repo_path, search_parent_directories=True)

    # Collect commits lazily; we need the total for the progress bar.
    all_commits: list[git.Commit] = list(repo.iter_commits())
    total = len(all_commits)

    results: list[CommitInfo] = []

    def _within_window(commit: git.Commit) -> bool:
        # Normalise to naive UTC so comparisons always work regardless of
        # whether the caller supplied a tz-aware or tz-naive datetime.
        committed_dt = commit.committed_datetime
        if committed_dt.tzinfo is not None:
            committed_dt = committed_dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)

        if since is not None:
            since_naive = since.replace(tzinfo=None) if since.tzinfo is not None else since
            if committed_dt < since_naive:
                return False
        if until is not None:
            until_naive = until.replace(tzinfo=None) if until.tzinfo is not None else until
            if committed_dt > until_naive:
                return False
        return True

    if show_progress:
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} commits"),
            TimeElapsedColumn(),
        )
        task = progress.add_task("Analysing commits…", total=total)
        progress.start()
    else:
        progress = None
        task = None

    try:
        for commit in all_commits:
            if progress:
                progress.advance(task)  # type: ignore[arg-type]

            if not _within_window(commit):
                continue

            committed_dt = commit.committed_datetime
            # Store as naive UTC for simplicity downstream.
            if committed_dt.tzinfo is not None:
                committed_dt = committed_dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)

            info = CommitInfo(
                hash=commit.hexsha,
                author_name=commit.author.name or "",
                author_email=commit.author.email or "",
                datetime=committed_dt,
                files_changed=_parse_diff_stats(commit),
            )
            results.append(info)
    finally:
        if progress:
            progress.stop()

    return results
