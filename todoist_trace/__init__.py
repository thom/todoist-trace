"""
todoist-trace: Export Todoist activity logs with multi-level project
and task hierarchy resolution.
"""

import requests

from .api import fetch_completed_activities, fetch_projects
from .cache import (
    SQLiteTraceCache,
    TaskCacheDict,
    TraceCache,
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
from .resolvers import (
    ProjectTreeResolver,
    TaskHierarchyResolver,
    build_trace_records,
)

__all__ = [
    "DEFAULT_APP_DIR",
    "DEFAULT_CACHE_PATH",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_JSON_CACHE_PATH",
    "ProjectTreeResolver",
    "SQLiteTraceCache",
    "TaskCacheDict",
    "TaskHierarchyResolver",
    "TraceCache",
    "build_trace_records",
    "create_cache",
    "export_csv",
    "export_markdown",
    "fetch_completed_activities",
    "fetch_projects",
    "filter_records",
    "format_task_bullets",
    "generate_csv",
    "generate_markdown",
    "load_config",
    "load_env_file",
    "main",
    "parse_args",
    "resolve_settings",
]
