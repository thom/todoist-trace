"""
todoist-trace: Export Todoist activity logs with multi-level project
and task hierarchy resolution.
"""

import requests

from .api import (
    fetch_completed_activities,
    fetch_completed_tasks_by_date,
    fetch_labels,
    fetch_projects,
    fetch_section,
    fetch_sections,
    fetch_task,
    fetch_tasks,
)
from .cache import (
    LabelCacheDict,
    SQLiteTraceCache,
    SectionCacheDict,
    TaskCacheDict,
    calculate_missing_intervals,
    coalesce_intervals,
    create_cache,
)
from .cli import create_parser, parse_args, resolve_settings
from .config import (
    DEFAULT_APP_DIR,
    DEFAULT_CACHE_PATH,
    DEFAULT_CONFIG_PATH,
    load_config,
    load_env_file,
    resolve_timezone,
)
from .exporters import (
    export_csv,
    export_html,
    export_markdown,
    format_task_bullets,
    generate_csv,
    generate_html,
    generate_markdown,
)
from .filters import filter_records
from .main import main, preload_tasks, run_export, run_status, run_sync
from .progress import (
    FancyProgressReporter,
    format_duration,
    render_progress_bar,
    supports_color,
)
from .resolvers import (
    LabelResolver,
    ProjectTreeResolver,
    SectionResolver,
    TaskHierarchyResolver,
    build_trace_records,
    calculate_due_variance,
    format_event_datetime,
    format_priority,
)

__all__ = [
    "DEFAULT_APP_DIR",
    "DEFAULT_CACHE_PATH",
    "DEFAULT_CONFIG_PATH",
    "FancyProgressReporter",
    "LabelCacheDict",
    "LabelResolver",
    "ProjectTreeResolver",
    "SQLiteTraceCache",
    "SectionCacheDict",
    "SectionResolver",
    "TaskCacheDict",
    "TaskHierarchyResolver",
    "build_trace_records",
    "calculate_due_variance",
    "calculate_missing_intervals",
    "coalesce_intervals",
    "create_cache",
    "create_parser",
    "export_csv",
    "export_html",
    "export_markdown",
    "fetch_completed_activities",
    "fetch_completed_tasks_by_date",
    "fetch_labels",
    "fetch_projects",
    "fetch_section",
    "fetch_sections",
    "fetch_task",
    "fetch_tasks",
    "filter_records",
    "format_event_datetime",
    "format_priority",
    "format_task_bullets",
    "generate_csv",
    "generate_html",
    "generate_markdown",
    "load_config",
    "load_env_file",
    "main",
    "parse_args",
    "preload_tasks",
    "resolve_settings",
    "resolve_timezone",
    "run_export",
    "run_status",
    "run_sync",
]
