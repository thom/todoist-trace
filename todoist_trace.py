#!/usr/bin/env python3
"""
todoist-trace: Export Todoist activity logs with multi-level project
and task hierarchy resolution.
"""

import sys
from todoist_trace import (
    DEFAULT_APP_DIR,
    DEFAULT_CACHE_PATH,
    DEFAULT_CONFIG_PATH,
    DEFAULT_JSON_CACHE_PATH,
    ProjectTreeResolver,
    SQLiteTraceCache,
    TaskCacheDict,
    TaskHierarchyResolver,
    TraceCache,
    build_trace_records,
    calculate_missing_intervals,
    coalesce_intervals,
    create_cache,
    export_csv,
    export_markdown,
    fetch_completed_activities,
    fetch_projects,
    filter_records,
    format_event_datetime,
    format_task_bullets,
    generate_csv,
    generate_markdown,
    load_config,
    load_env_file,
    main,
    parse_args,
    resolve_settings,
    resolve_timezone,
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
    "calculate_missing_intervals",
    "coalesce_intervals",
    "create_cache",
    "export_csv",
    "export_markdown",
    "fetch_completed_activities",
    "fetch_projects",
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

if __name__ == "__main__":
    sys.exit(main())
