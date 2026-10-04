"""
Unit tests for modular package structure and direct submodule imports.
"""

class TestModularPackageStructure:
    """Ensure all submodules in todoist_trace package can be imported directly."""

    def test_package_exports(self):
        import todoist_trace
        expected_exports = [
            "DEFAULT_APP_DIR",
            "DEFAULT_CACHE_PATH",
            "DEFAULT_CONFIG_PATH",
            "ProjectTreeResolver",
            "SQLiteTraceCache",
            "SectionCacheDict",
            "SectionResolver",
            "TaskCacheDict",
            "TaskHierarchyResolver",
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
        for name in expected_exports:
            assert hasattr(todoist_trace, name), f"Missing export: {name}"

    def test_direct_submodule_imports(self):
        from todoist_trace.api import (
            fetch_completed_activities,
            fetch_projects,
            fetch_section,
            fetch_sections,
        )
        from todoist_trace.cache import (
            SQLiteTraceCache,
            SectionCacheDict,
            TaskCacheDict,
            create_cache,
        )
        from todoist_trace.cli import parse_args, resolve_settings
        from todoist_trace.config import DEFAULT_APP_DIR, load_config
        from todoist_trace.exporters import export_csv, export_markdown, format_task_bullets
        from todoist_trace.filters import filter_records
        from todoist_trace.main import main
        from todoist_trace.resolvers import (
            ProjectTreeResolver,
            SectionResolver,
            TaskHierarchyResolver,
        )

        assert callable(fetch_projects)
        assert callable(fetch_completed_activities)
        assert callable(fetch_sections)
        assert callable(fetch_section)
        assert callable(create_cache)
        assert callable(parse_args)
        assert callable(resolve_settings)
        assert callable(load_config)
        assert callable(export_csv)
        assert callable(export_markdown)
        assert callable(format_task_bullets)
        assert callable(filter_records)
        assert callable(main)
        assert callable(ProjectTreeResolver)
        assert callable(SectionResolver)
        assert callable(TaskHierarchyResolver)
