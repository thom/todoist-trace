"""
todoist-trace: Export Todoist activity logs with multi-level project
and task hierarchy resolution.
"""

import requests

from .api import (
    fetch_completed_activities,
    fetch_projects,
    fetch_section,
    fetch_sections,
)
from .cache import (
    SQLiteTraceCache,
    SectionCacheDict,
    TaskCacheDict,
    TraceCache,
    calculate_missing_intervals,
    coalesce_intervals,
    create_cache,
)
from .cli import parse_args, resolve_settings
from .config import (
    DEFAULT_APP_DIR,
    DEFAULT_CACHE_PATH,
    DEFAULT_CONFIG_PATH,
    DEFAULT_JSON_CACHE_PATH,
    load_config,
    load_env_file,
    resolve_timezone,
)
from .exporters import (
    export_csv,
    export_markdown,
    format_task_bullets,
    generate_csv,
    generate_markdown,
)
from .filters import filter_records
from .main import main
from .progress import (
    FancyProgressReporter,
    format_duration,
    render_progress_bar,
    supports_color,
)
from .resolvers import (
    ProjectTreeResolver,
    SectionResolver,
    TaskHierarchyResolver,
    build_trace_records,
    format_event_datetime,
)

__all__ = [
    "DEFAULT_APP_DIR",
    "DEFAULT_CACHE_PATH",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_JSON_CACHE_PATH",
    "FancyProgressReporter",
    "ProjectTreeResolver",
    "SQLiteTraceCache",
    "SectionCacheDict",
    "SectionResolver",
    "TaskCacheDict",
    "TaskHierarchyResolver",
    "TraceCache",
    "build_trace_records",
    "calculate_missing_intervals",
    "coalesce_intervals",
    "create_cache",
    "export_csv",
    "export_markdown",
    "fetch_completed_activities",
    "fetch_projects",
    "fetch_section",
    "fetch_sections",
    "filter_records",
    "format_event_datetime",
    "format_task_bullets",
    "generate_csv",
    "generate_markdown",
    "load_config",
    "load_env_file",
    "main",
    "parse_args",
    "resolve_settings",
    "resolve_timezone",
]
