"""aggregator.py — transform raw commit data into per-file, per-author, and time-series stats."""

from __future__ import annotations

import datetime
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from gitsift.commit_walker import CommitInfo


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class FileChurn:
    """Aggregated churn statistics for a single file."""

    filepath: str
    total_adds: int
    total_deletes: int
    change_count: int
    churn_score: int          # total_adds + total_deletes
    is_hotspot: bool = False


@dataclass
class AuthorStats:
    """Aggregated activity statistics for a single contributor."""

    name: str
    email: str
    commit_count: int
    lines_added: int
    lines_deleted: int
    top_files: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Container returned by :func:`analyse` holding all aggregated data."""

    file_churn: list[FileChurn]          # sorted by churn_score desc
    author_stats: list[AuthorStats]      # sorted by commit_count desc
    time_series: dict[str, int]          # ISO-period-string → commit count
    hotspots: list[FileChurn]            # subset of file_churn where is_hotspot=True
    group_by: Literal["day", "week", "month"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _period_key(dt: datetime.datetime, group_by: Literal["day", "week", "month"]) -> str:
    """Return a sortable string key for *dt* bucketed by *group_by*."""
    if group_by == "day":
        return dt.strftime("%Y-%m-%d")
    if group_by == "week":
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    # month
    return dt.strftime("%Y-%m")


# ---------------------------------------------------------------------------
# Public aggregation functions
# ---------------------------------------------------------------------------

def compute_file_churn(commits: list[CommitInfo]) -> list[FileChurn]:
    """Compute per-file churn totals across all *commits*.

    Returns a list of :class:`FileChurn` objects sorted by churn_score descending.
    """
    adds: dict[str, int] = defaultdict(int)
    deletes: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)

    for commit in commits:
        for fc in commit.files_changed:
            adds[fc.path] += fc.lines_added
            deletes[fc.path] += fc.lines_deleted
            counts[fc.path] += 1

    result: list[FileChurn] = []
    for path in adds.keys() | deletes.keys():
        score = adds[path] + deletes[path]
        result.append(FileChurn(
            filepath=path,
            total_adds=adds[path],
            total_deletes=deletes[path],
            change_count=counts[path],
            churn_score=score,
        ))

    result.sort(key=lambda x: x.churn_score, reverse=True)
    return result


def detect_hotspots(file_churn: list[FileChurn]) -> list[FileChurn]:
    """Flag files whose churn_score exceeds mean + 2*stddev as hotspots.

    Modifies *file_churn* in-place (sets :attr:`FileChurn.is_hotspot`) and
    returns the subset of hotspot entries.
    """
    if len(file_churn) < 2:
        return []

    scores = [f.churn_score for f in file_churn]
    mean = statistics.mean(scores)
    stdev = statistics.stdev(scores)
    threshold = mean + 2 * stdev

    hotspots: list[FileChurn] = []
    for entry in file_churn:
        if entry.churn_score > threshold:
            entry.is_hotspot = True
            hotspots.append(entry)

    return hotspots


def compute_author_stats(commits: list[CommitInfo], top_files: int = 5) -> list[AuthorStats]:
    """Compute per-author activity stats across all *commits*.

    Returns a list of :class:`AuthorStats` sorted by commit_count descending.
    """
    commit_counts: dict[str, int] = defaultdict(int)
    lines_added: dict[str, int] = defaultdict(int)
    lines_deleted: dict[str, int] = defaultdict(int)
    emails: dict[str, str] = {}
    file_touches: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for commit in commits:
        key = commit.author_email or commit.author_name
        commit_counts[key] += 1
        emails[key] = commit.author_email
        for fc in commit.files_changed:
            lines_added[key] += fc.lines_added
            lines_deleted[key] += fc.lines_deleted
            file_touches[key][fc.path] += 1

    result: list[AuthorStats] = []
    for key, count in commit_counts.items():
        # Build top_files list sorted by touch frequency.
        touched = sorted(file_touches[key].items(), key=lambda x: x[1], reverse=True)
        top = [p for p, _ in touched[:top_files]]
        # Resolve display name from any commit with this email/key.
        name = key
        for commit in commits:
            if (commit.author_email or commit.author_name) == key:
                name = commit.author_name
                break
        result.append(AuthorStats(
            name=name,
            email=emails.get(key, ""),
            commit_count=count,
            lines_added=lines_added[key],
            lines_deleted=lines_deleted[key],
            top_files=top,
        ))

    result.sort(key=lambda x: x.commit_count, reverse=True)
    return result


def compute_time_series(
    commits: list[CommitInfo],
    group_by: Literal["day", "week", "month"] = "week",
) -> dict[str, int]:
    """Group commits by time period.

    Returns an ordered dict mapping ISO period strings (e.g. ``"2024-W03"``) to
    commit counts, sorted chronologically.
    """
    counts: dict[str, int] = defaultdict(int)
    for commit in commits:
        key = _period_key(commit.datetime, group_by)
        counts[key] += 1

    return dict(sorted(counts.items()))


def analyse(
    commits: list[CommitInfo],
    group_by: Literal["day", "week", "month"] = "week",
) -> AnalysisResult:
    """Run all aggregations on *commits* and return an :class:`AnalysisResult`.

    This is the single entry point that :mod:`gitsift.cli` calls.
    """
    file_churn = compute_file_churn(commits)
    hotspots = detect_hotspots(file_churn)
    author_stats = compute_author_stats(commits)
    time_series = compute_time_series(commits, group_by=group_by)

    return AnalysisResult(
        file_churn=file_churn,
        author_stats=author_stats,
        time_series=time_series,
        hotspots=hotspots,
        group_by=group_by,
    )
