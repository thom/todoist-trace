"""
Command-line argument parsing and settings resolution for todoist-trace.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .config import DEFAULT_CACHE_PATH, load_config, resolve_timezone


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add configuration, cache, and terminal output options common to commands."""
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


def _add_date_arguments(parser: argparse.ArgumentParser) -> None:
    """Add date range and timezone options."""
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
        "-z", "--timezone",
        type=str,
        default=None,
        help="Timezone for dates and exports (e.g. 'Europe/Zurich', 'UTC', or 'local') (default: local)",
    )


def _add_sync_only_arguments(parser: argparse.ArgumentParser) -> None:
    """Add options specific to API synchronization."""
    parser.add_argument(
        "-t", "--token",
        type=str,
        default=None,
        help="Todoist API token (falls back to TODOIST_API_TOKEN env var or config file)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Force re-fetching all data from the API and refresh cache",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable persistent local cache",
    )


def _add_export_only_arguments(parser: argparse.ArgumentParser) -> None:
    """Add options specific to formatting and filtering exports."""
    parser.add_argument(
        "-c", "--category",
        choices=["work", "personal", "all"],
        default=None,
        help="Top-level project filter: work, personal, or all (default: all)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["csv", "markdown", "md", "html", "htm"],
        default=None,
        help="Output format: csv, markdown / md, or html (default: csv)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output file path (default: todoist_trace_export.csv, .md, or .html)",
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
    parser.add_argument(
        "--due-dates", "--include-due-dates",
        dest="include_due_dates",
        action="store_true",
        default=None,
        help="Include original due dates and completion variance in exports (default: false)",
    )
    parser.add_argument(
        "--all-fields",
        action="store_true",
        default=False,
        help="Include all extended metadata fields (labels, descriptions, priorities, due dates)",
    )


def create_parser() -> argparse.ArgumentParser:
    """Create top-level argument parser with git-style subcommands."""
    parser = argparse.ArgumentParser(
        prog="todoist-trace",
        description="Sync and export Todoist activity logs with project, section, and task hierarchy resolution.",
    )
    _add_common_arguments(parser)

    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # 1. sync
    sync_p = subparsers.add_parser(
        "sync",
        help="Synchronize activity logs, projects, sections, and task metadata to SQLite cache",
        description="Retrieve projects, sections, labels, activities, and task hierarchies from Todoist API and store into cache.",
    )
    _add_common_arguments(sync_p)
    _add_date_arguments(sync_p)
    _add_sync_only_arguments(sync_p)

    # 2. export
    export_p = subparsers.add_parser(
        "export",
        help="Export cached activity records to CSV or Markdown",
        description="Filter and format cached records into Markdown or CSV reports (operates offline on local cache).",
    )
    _add_common_arguments(export_p)
    _add_date_arguments(export_p)
    _add_export_only_arguments(export_p)
    export_p.add_argument(
        "-t", "--token",
        type=str,
        default=None,
        help="Todoist API token for on-demand task hierarchy lookups (optional for export)",
    )

    # 3. status
    status_p = subparsers.add_parser(
        "status",
        help="Show SQLite cache summary, synchronized ranges, and statistics",
        description="Inspect local SQLite cache database: statistics, last sync time, and covered date ranges.",
    )
    _add_common_arguments(status_p)

    # 4. run (combined sync + export)
    run_p = subparsers.add_parser(
        "run",
        help="Run sync followed immediately by export (single-pass operation)",
        description="Convenience command running sync and export in a single pass.",
    )
    _add_common_arguments(run_p)
    _add_date_arguments(run_p)
    _add_sync_only_arguments(run_p)
    _add_export_only_arguments(run_p)

    return parser


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """
    Parse command-line arguments.
    Supports git-style subcommands: 'sync', 'export', 'status', 'run'.
    If invoked without a subcommand or directly with option flags, defaults to 'run'.
    """
    parser = create_parser()
    args_list = list(sys.argv[1:]) if argv is None else list(argv)

    subcommands = {"sync", "export", "status", "run"}
    if not args_list:
        args_list = ["run"]
    elif args_list[0] not in subcommands and args_list[0] not in ("-h", "--help"):
        args_list.insert(0, "run")

    args = parser.parse_args(args_list)
    if not getattr(args, "command", None):
        args.command = "run"
    return args


def resolve_settings(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Resolve final settings by merging CLI arguments, environment variables,
    config file values, and defaults in order of precedence:
    1. CLI argument (if provided)
    2. Environment variable
    3. Config file
    4. Default value
    """
    config_path = getattr(args, "config", None)
    file_cfg = load_config(config_path)

    # 0. Command
    command = getattr(args, "command", "run") or "run"

    # 1. Token
    token = getattr(args, "token", None) or os.environ.get("TODOIST_API_TOKEN") or file_cfg.get("token")

    # 2. Format
    raw_format = (getattr(args, "format", None) or os.environ.get("TODOIST_TRACE_FORMAT") or file_cfg.get("format") or "csv").lower()
    if raw_format in ("md", "markdown"):
        output_format = "markdown"
    elif raw_format in ("html", "htm"):
        output_format = "html"
    else:
        output_format = "csv"

    # 3. Category
    category = (getattr(args, "category", None) or os.environ.get("TODOIST_TRACE_CATEGORY") or file_cfg.get("category") or "all").lower()

    # 4. Markdown Style
    markdown_style = (getattr(args, "markdown_style", None) or os.environ.get("TODOIST_TRACE_MARKDOWN_STYLE") or file_cfg.get("markdown_style") or "nested").lower()

    # 4b. Task Style (nested bullet hierarchy or flat slash-separated)
    task_style = (getattr(args, "task_style", None) or os.environ.get("TODOIST_TRACE_TASK_STYLE") or file_cfg.get("task_style") or "nested").lower()

    # 5. Dates
    start_date = getattr(args, "start_date", None) or os.environ.get("TODOIST_TRACE_START_DATE") or file_cfg.get("start_date")
    end_date = getattr(args, "end_date", None) or os.environ.get("TODOIST_TRACE_END_DATE") or file_cfg.get("end_date")
    if start_date and end_date and start_date > end_date:
        raise ValueError(f"Start date ({start_date}) cannot be after end date ({end_date}).")

    # 6. Output path
    output = getattr(args, "output", None) or os.environ.get("TODOIST_TRACE_OUTPUT") or file_cfg.get("output")
    if not output:
        if output_format == "csv":
            output = "todoist_trace_export.csv"
        elif output_format == "html":
            output = "todoist_trace_export.html"
        else:
            output = "todoist_trace_export.md"

    # 7. Cache settings
    cache_enabled = not getattr(args, "no_cache", False) and file_cfg.get("cache_enabled", True)
    raw_cache = getattr(args, "cache_file", None) or file_cfg.get("cache_file")
    if raw_cache:
        cache_file = str(Path(raw_cache).expanduser())
    elif Path(".todoist_cache.db").is_file():
        cache_file = ".todoist_cache.db"
    elif Path(".todoist_cache.json").is_file():
        cache_file = ".todoist_cache.json"
    else:
        cache_file = str(DEFAULT_CACHE_PATH)
    refresh = getattr(args, "refresh", False)

    # 8. Timezone
    raw_tz = getattr(args, "timezone", None) or os.environ.get("TODOIST_TRACE_TIMEZONE") or file_cfg.get("timezone") or "local"
    tz = resolve_timezone(raw_tz)

    # 9. Terminal output & progress
    quiet = bool(getattr(args, "quiet", False) or os.environ.get("TODOIST_TRACE_QUIET") or file_cfg.get("quiet", False))
    no_color = bool(getattr(args, "no_color", False) or os.environ.get("NO_COLOR") or file_cfg.get("no_color", False))
    plain = bool(getattr(args, "plain", False) or os.environ.get("TODOIST_TRACE_PLAIN") or file_cfg.get("plain", False))

    # 10. Extended metadata fields
    all_fields = getattr(args, "all_fields", False)

    def _resolve_bool_flag(cli_val: Optional[bool], env_names: list, cfg_names: list, default: bool = False) -> bool:
        if all_fields:
            return True
        if cli_val is not None:
            return bool(cli_val)
        for env_name in env_names:
            if env_name in os.environ:
                return os.environ[env_name].lower() in ("1", "true", "yes")
        for cfg_name in cfg_names:
            if cfg_name in file_cfg:
                return bool(file_cfg[cfg_name])
        return default

    include_labels = _resolve_bool_flag(
        getattr(args, "include_labels", None),
        ["TODOIST_TRACE_LABELS", "TODOIST_TRACE_INCLUDE_LABELS"],
        ["include_labels", "labels"],
    )
    include_descriptions = _resolve_bool_flag(
        getattr(args, "include_descriptions", None),
        ["TODOIST_TRACE_DESCRIPTIONS", "TODOIST_TRACE_INCLUDE_DESCRIPTIONS"],
        ["include_descriptions", "descriptions"],
    )
    include_priorities = _resolve_bool_flag(
        getattr(args, "include_priorities", None),
        ["TODOIST_TRACE_PRIORITIES", "TODOIST_TRACE_INCLUDE_PRIORITIES"],
        ["include_priorities", "priorities"],
    )
    include_due_dates = _resolve_bool_flag(
        getattr(args, "include_due_dates", None),
        ["TODOIST_TRACE_DUE_DATES", "TODOIST_TRACE_INCLUDE_DUE_DATES"],
        ["include_due_dates", "due_dates"],
    )

    return {
        "command": command,
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
        "include_due_dates": include_due_dates,
        "all_fields": all_fields,
    }
