# GitSift - agents.md

## Project Overview
GitSift is a Python CLI tool that analyzes local Git repositories and generates developer
activity reports with code churn metrics, contributor stats, and commit frequency analysis.

## Architecture
- `commit_walker.py`: GitPython-based commit iteration with diff parsing
- `aggregator.py`: Per-file churn, per-author stats, time-series grouping, hotspot detection
- `renderers.py`: Rich tables (terminal), matplotlib charts (PNG), JSON output
- `cli.py`: argparse entry point

## Tech Constraints
- Pure Python, no external APIs or services
- GitPython for repository access (no subprocess git calls)
- Must handle repos with 10,000+ commits without excessive memory usage
- All output modes (terminal, charts, JSON) share the same aggregated data

## Code Conventions
- Type hints on all functions
- Docstrings on all public functions
- dataclasses for structured data (CommitInfo, FileChurn, AuthorStats)
- No global state; all functions take explicit inputs
- pytest with tmp_path fixtures for testing
- Rich console output should degrade gracefully if terminal doesn't support color

## File Structure
- `gitsift/` - main package (cli, commit_walker, aggregator, renderers)
- `tests/` - pytest tests with temp repo fixtures

## Key Decisions
- GitPython over subprocess because it provides structured access to commit objects and diffs
- Rich over tabulate for terminal output because of progress bars during long repo walks
- argparse over click to minimize dependencies
- Hotspot detection uses mean + 2*stddev rather than fixed thresholds to adapt to repo size
- JSON output goes to stdout (not a file) so it can be piped to jq or other tools
