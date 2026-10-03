"""
Command-line argument parsing and settings resolution for todoist-trace.
"""

import argparse
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .config import DEFAULT_CACHE_PATH, load_config, resolve_timezone


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="todoist-trace",
        description="Export Todoist activity logs into structured CSV or Markdown files with project and task hierarchy resolution.",
    )
    parser.add_argument(
        "-z", "--timezone",
        type=str,
        default=None,
        help="Timezone for daily overview and exports (e.g. 'Europe/Zurich', 'UTC', or 'local') (default: local)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["csv", "markdown", "md"],
        default=None,
        help="Output format: csv or markdown / md (default: csv)",
    )
    parser.add_argument(
        "-s", "--start-date",
        type=str,
        default=None,
        help="Start date filter in YYYY-MM-DD format (inclusive)",
    )
    parser.add_argument(
        "-e", "--end-date",
        type=str,
        default=None,
        help="End date filter in YYYY-MM-DD format (inclusive)",
    )
    parser.add_argument(
        "-c", "--category",
        choices=["work", "personal", "all"],
        default=None,
        help="Top-level project filter: work, personal, or all (default: all)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output file path (default: todoist_trace_export.csv or .md)",
    )
    parser.add_argument(
        "-t", "--token",
        type=str,
        default=None,
        help="Todoist API token (falls back to TODOIST_API_TOKEN env var or config file)",
    )
    parser.add_argument(
        "--markdown-style",
        choices=["nested", "flat"],
        default=None,
        help="Markdown project heading style: nested (#### admin / ##### email) or flat (#### admin/email) (default: nested)",
    )
    parser.add_argument(
        "--task-style",
        choices=["nested", "flat"],
        default=None,
        help="Markdown task bullet style: nested (bullet hierarchy) or flat (slash-separated) (default: nested)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to custom config file (JSON or .env)",
    )
    parser.add_argument(
        "--cache-file",
        type=str,
        default=None,
        help="Path to local cache file (default: ~/.todoist-trace/cache.db)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable persistent local cache",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Force re-fetching all data from the API and refresh cache",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        default=False,
        help="Suppress progress updates and non-error messages",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable ANSI colors in terminal output",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        default=False,
        help="Use clean plain-text progress updates (no in-place cursor overwrites)",
    )
    parser.add_argument(
        "--labels", "--include-labels",
        dest="include_labels",
        action="store_true",
        default=None,
        help="Include task labels in exports (default: false)",
    )
    parser.add_argument(
        "--descriptions", "--include-descriptions",
        dest="include_descriptions",
        action="store_true",
        default=None,
        help="Include task descriptions/notes in exports (default: false)",
    )
    parser.add_argument(
        "--priorities", "--include-priorities",
        dest="include_priorities",
        action="store_true",
        default=None,
        help="Include task priorities (p1-p4) in exports (default: false)",
    )
    return parser.parse_args(argv)


def resolve_settings(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Resolve final settings by merging CLI arguments, environment variables,
    config file values, and defaults in order of precedence:
    1. CLI argument (if provided)
    2. Environment variable
    3. Config file
    4. Default value
    """
    file_cfg = load_config(args.config)

    # 1. Token
    token = args.token or os.environ.get("TODOIST_API_TOKEN") or file_cfg.get("token")

    # 2. Format
    raw_format = args.format or os.environ.get("TODOIST_TRACE_FORMAT") or file_cfg.get("format") or "csv"
    output_format = "markdown" if raw_format.lower() in ("md", "markdown") else "csv"

    # 3. Category
    category = (args.category or os.environ.get("TODOIST_TRACE_CATEGORY") or file_cfg.get("category") or "all").lower()

    # 4. Markdown Style
    markdown_style = (args.markdown_style or os.environ.get("TODOIST_TRACE_MARKDOWN_STYLE") or file_cfg.get("markdown_style") or "nested").lower()

    # 4b. Task Style (nested bullet hierarchy or flat slash-separated)
    task_style = (args.task_style or os.environ.get("TODOIST_TRACE_TASK_STYLE") or file_cfg.get("task_style") or "nested").lower()

    # 5. Dates
    start_date = args.start_date or os.environ.get("TODOIST_TRACE_START_DATE") or file_cfg.get("start_date")
    end_date = args.end_date or os.environ.get("TODOIST_TRACE_END_DATE") or file_cfg.get("end_date")
    if start_date and end_date and start_date > end_date:
        raise ValueError(f"Start date ({start_date}) cannot be after end date ({end_date}).")

    # 6. Output path
    output = args.output or os.environ.get("TODOIST_TRACE_OUTPUT") or file_cfg.get("output")
    if not output:
        output = "todoist_trace_export.csv" if output_format == "csv" else "todoist_trace_export.md"

    # 7. Cache settings
    cache_enabled = not args.no_cache and file_cfg.get("cache_enabled", True)
    raw_cache = args.cache_file or file_cfg.get("cache_file")
    if raw_cache:
        cache_file = str(Path(raw_cache).expanduser())
    elif Path(".todoist_cache.db").is_file():
        cache_file = ".todoist_cache.db"
    elif Path(".todoist_cache.json").is_file():
        cache_file = ".todoist_cache.json"
    else:
        cache_file = str(DEFAULT_CACHE_PATH)
    refresh = args.refresh

    # 8. Timezone
    raw_tz = args.timezone or os.environ.get("TODOIST_TRACE_TIMEZONE") or file_cfg.get("timezone") or "local"
    tz = resolve_timezone(raw_tz)

    # 9. Terminal output & progress
    quiet = bool(args.quiet or os.environ.get("TODOIST_TRACE_QUIET") or file_cfg.get("quiet", False))
    no_color = bool(args.no_color or os.environ.get("NO_COLOR") or file_cfg.get("no_color", False))
    plain = bool(args.plain or os.environ.get("TODOIST_TRACE_PLAIN") or file_cfg.get("plain", False))

    # 10. Extended metadata (labels & descriptions)
    if args.include_labels is not None:
        include_labels = bool(args.include_labels)
    elif "TODOIST_TRACE_LABELS" in os.environ:
        include_labels = os.environ["TODOIST_TRACE_LABELS"].lower() in ("1", "true", "yes")
    elif "TODOIST_TRACE_INCLUDE_LABELS" in os.environ:
        include_labels = os.environ["TODOIST_TRACE_INCLUDE_LABELS"].lower() in ("1", "true", "yes")
    else:
        include_labels = bool(file_cfg.get("include_labels", file_cfg.get("labels", False)))

    if args.include_descriptions is not None:
        include_descriptions = bool(args.include_descriptions)
    elif "TODOIST_TRACE_DESCRIPTIONS" in os.environ:
        include_descriptions = os.environ["TODOIST_TRACE_DESCRIPTIONS"].lower() in ("1", "true", "yes")
    elif "TODOIST_TRACE_INCLUDE_DESCRIPTIONS" in os.environ:
        include_descriptions = os.environ["TODOIST_TRACE_INCLUDE_DESCRIPTIONS"].lower() in ("1", "true", "yes")
    else:
        include_descriptions = bool(file_cfg.get("include_descriptions", file_cfg.get("descriptions", False)))

    if args.include_priorities is not None:
        include_priorities = bool(args.include_priorities)
    elif "TODOIST_TRACE_PRIORITIES" in os.environ:
        include_priorities = os.environ["TODOIST_TRACE_PRIORITIES"].lower() in ("1", "true", "yes")
    elif "TODOIST_TRACE_INCLUDE_PRIORITIES" in os.environ:
        include_priorities = os.environ["TODOIST_TRACE_INCLUDE_PRIORITIES"].lower() in ("1", "true", "yes")
    else:
        include_priorities = bool(file_cfg.get("include_priorities", file_cfg.get("priorities", False)))

    return {
        "token": token,
        "format": output_format,
        "category": category,
        "markdown_style": markdown_style,
        "task_style": task_style,
        "start_date": start_date,
        "end_date": end_date,
        "output": output,
        "cache_enabled": cache_enabled,
        "cache_file": cache_file,
        "refresh": refresh,
        "timezone": raw_tz,
        "tz": tz,
        "quiet": quiet,
        "no_color": no_color,
        "plain": plain,
        "include_labels": include_labels,
        "include_descriptions": include_descriptions,
        "include_priorities": include_priorities,
    }
