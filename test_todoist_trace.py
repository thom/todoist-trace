"""
Unit tests for todoist-trace project.
Covers:
1. Multi-level project tree resolution (depths 1 to 5+ and archived projects).
2. Category and date range filtering logic.
3. Multi-level task hierarchy traversal and task_path generation.
4. Persistent cache operations.
5. CLI argument parsing and configuration resolution.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from todoist_trace import (
    ProjectTreeResolver,
    TaskHierarchyResolver,
    TraceCache,
    build_trace_records,
    export_csv,
    export_markdown,
    filter_records,
    generate_csv,
    generate_markdown,
    parse_args,
    resolve_settings,
)


# ==============================================================================
# 1. Project Tree Resolution Tests
# ==============================================================================

class TestProjectTreeResolver:
    """Test suite for ProjectTreeResolver."""

    def test_single_root_project(self):
        projects = [
            {"id": "p1", "name": "Inbox", "parent_id": None},
            {"id": "p2", "name": "work-areas", "parent_id": None},
        ]
        resolver = ProjectTreeResolver(projects)

        res1 = resolver.resolve("p1")
        assert res1["top_level_project"] == "Inbox"
        assert res1["project_path"] == ""
        assert res1["project_levels"] == []

        res2 = resolver.resolve("p2")
        assert res2["top_level_project"] == "work-areas"
        assert res2["project_path"] == ""
        assert res2["project_levels"] == []

    def test_two_level_project(self):
        projects = [
            {"id": "p1", "name": "work-areas", "parent_id": None},
            {"id": "p2", "name": "admin", "parent_id": "p1"},
        ]
        resolver = ProjectTreeResolver(projects)

        res = resolver.resolve("p2")
        assert res["top_level_project"] == "work-areas"
        assert res["project_path"] == "admin"
        assert res["project_levels"] == ["admin"]

    def test_deep_project_hierarchy_five_plus_levels(self):
        projects = [
            {"id": "p1", "name": "work", "parent_id": None},
            {"id": "p2", "name": "engineering", "parent_id": "p1"},
            {"id": "p3", "name": "infrastructure", "parent_id": "p2"},
            {"id": "p4", "name": "storage", "parent_id": "p3"},
            {"id": "p5", "name": "database", "parent_id": "p4"},
            {"id": "p6", "name": "ops", "parent_id": "p5"},
        ]
        resolver = ProjectTreeResolver(projects)

        res = resolver.resolve("p6")
        assert res["top_level_project"] == "work"
        assert res["project_path"] == "engineering/infrastructure/storage/database/ops"
        assert res["project_levels"] == [
            "engineering",
            "infrastructure",
            "storage",
            "database",
            "ops",
        ]

    def test_archived_projects(self):
        projects = [
            {"id": "p1", "name": "archive-root", "parent_id": None, "is_archived": True},
            {"id": "p2", "name": "old-project", "parent_id": "p1", "is_archived": True},
        ]
        resolver = ProjectTreeResolver(projects)

        res = resolver.resolve("p2")
        assert res["top_level_project"] == "archive-root"
        assert res["project_path"] == "old-project"
        assert res["project_levels"] == ["old-project"]

    def test_unknown_and_none_project_id(self):
        projects = [{"id": "p1", "name": "work", "parent_id": None}]
        resolver = ProjectTreeResolver(projects)

        res_none = resolver.resolve(None)
        assert res_none["top_level_project"] == "Unknown"
        assert res_none["project_path"] == ""

        res_unknown = resolver.resolve("non_existent_id")
        assert res_unknown["top_level_project"] == "Unknown"
        assert res_unknown["project_path"] == ""

    def test_cycle_detection(self):
        # A cycle: p1 -> p2 -> p3 -> p1
        projects = [
            {"id": "p1", "name": "Cycle1", "parent_id": "p3"},
            {"id": "p2", "name": "Cycle2", "parent_id": "p1"},
            {"id": "p3", "name": "Cycle3", "parent_id": "p2"},
        ]
        resolver = ProjectTreeResolver(projects)
        # Should not crash or infinite loop
        res = resolver.resolve("p1")
        assert res["top_level_project"] in ["Cycle1", "Cycle2", "Cycle3"]


# ==============================================================================
# 2. Filtering Logic Tests
# ==============================================================================

class TestFiltering:
    """Test suite for category and date filtering."""

    @pytest.fixture
    def sample_records(self):
        return [
            {
                "top_level_project": "work-areas",
                "project_path": "admin",
                "date": "2026-10-01",
                "task_path": "Task 1",
            },
            {
                "top_level_project": "Work",
                "project_path": "ai",
                "date": "2026-10-02",
                "task_path": "Task 2",
            },
            {
                "top_level_project": "personal-areas",
                "project_path": "finance",
                "date": "2026-10-01",
                "task_path": "Task 3",
            },
            {
                "top_level_project": "Personal",
                "project_path": "health",
                "date": "2026-09-30",
                "task_path": "Task 4",
            },
            {
                "top_level_project": "Inbox",
                "project_path": "",
                "date": "2026-10-02",
                "task_path": "Task 5",
            },
        ]

    def test_category_work_matching(self, sample_records):
        filtered = filter_records(sample_records, category="work")
        assert len(filtered) == 2
        assert {r["task_path"] for r in filtered} == {"Task 1", "Task 2"}

    def test_category_personal_matching(self, sample_records):
        filtered = filter_records(sample_records, category="personal")
        assert len(filtered) == 2
        assert {r["task_path"] for r in filtered} == {"Task 3", "Task 4"}

    def test_category_all(self, sample_records):
        filtered = filter_records(sample_records, category="all")
        assert len(filtered) == 5

    def test_date_range_inclusive(self, sample_records):
        filtered = filter_records(
            sample_records,
            category="all",
            start_date="2026-10-01",
            end_date="2026-10-02",
        )
        assert len(filtered) == 4
        assert "Task 4" not in {r["task_path"] for r in filtered}

    def test_start_date_only(self, sample_records):
        filtered = filter_records(
            sample_records,
            category="all",
            start_date="2026-10-02",
        )
        assert len(filtered) == 2
        assert {r["task_path"] for r in filtered} == {"Task 2", "Task 5"}

    def test_combined_category_and_date(self, sample_records):
        filtered = filter_records(
            sample_records,
            category="work",
            start_date="2026-10-02",
            end_date="2026-10-02",
        )
        assert len(filtered) == 1
        assert filtered[0]["task_path"] == "Task 2"


# ==============================================================================
# 3. Task Hierarchy Resolution Tests
# ==============================================================================

class TestTaskHierarchyResolver:
    """Test suite for TaskHierarchyResolver."""

    def test_top_level_task_without_parent(self):
        resolver = TaskHierarchyResolver(token="dummy_token")
        event = {
            "id": "e1",
            "object_id": "t1",
            "parent_project_id": "p1",
            "event_date": "2026-10-02T12:00:00Z",
            "extra_data": {
                "content": "Single standalone task",
                "parent_id": None,
            },
        }
        res = resolver.resolve(event)
        assert res["task_path"] == "Single standalone task"
        assert res["task_levels"] == ["Single standalone task"]
        assert res["parent_task_id"] == ""
        assert res["date"] == "2026-10-02"
        assert res["time"] == "12:00:00"

    @patch("todoist_trace.requests.get")
    def test_multi_level_subtask_resolution(self, mock_get):
        # Grandparent -> Parent -> Leaf
        def side_effect(url, headers=None, timeout=None):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "t_parent" in url:
                mock_resp.json.return_value = {
                    "id": "t_parent",
                    "content": "Parent Task",
                    "parent_id": "t_grandparent",
                }
            elif "t_grandparent" in url:
                mock_resp.json.return_value = {
                    "id": "t_grandparent",
                    "content": "Grandparent Task",
                    "parent_id": None,
                }
            else:
                mock_resp.status_code = 404
            return mock_resp

        mock_get.side_effect = side_effect

        resolver = TaskHierarchyResolver(token="dummy_token")
        event = {
            "id": "e100",
            "object_id": "t_leaf",
            "parent_project_id": "p1",
            "event_date": "2026-10-02T14:30:15.123456Z",
            "extra_data": {
                "content": "Leaf Completed Task",
                "parent_id": "t_parent",
            },
        }

        res = resolver.resolve(event)
        assert res["task_path"] == "Grandparent Task / Parent Task / Leaf Completed Task"
        assert res["task_levels"] == [
            "Grandparent Task",
            "Parent Task",
            "Leaf Completed Task",
        ]
        assert res["parent_task_id"] == "t_parent"
        assert res["date"] == "2026-10-02"
        assert res["time"] == "14:30:15"

    @patch("todoist_trace.requests.get")
    def test_missing_parent_graceful_fallback(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        resolver = TaskHierarchyResolver(token="dummy_token")
        event = {
            "id": "e2",
            "object_id": "t2",
            "event_date": "2026-10-02T10:00:00Z",
            "extra_data": {
                "content": "Orphan Subtask",
                "parent_id": "deleted_parent_999",
            },
        }

        res = resolver.resolve(event)
        assert "[Task deleted_parent_999] / Orphan Subtask" == res["task_path"]
        assert res["parent_task_id"] == "deleted_parent_999"


# ==============================================================================
# 4. Persistent Cache Tests
# ==============================================================================

class TestTraceCache:
    """Test suite for TraceCache functionality."""

    def test_cache_save_and_load(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = TraceCache(cache_file=str(cache_file), enabled=True)

        cache.projects = [{"id": "p1", "name": "Work"}]
        cache.tasks = {"t1": {"content": "Task 1", "parent_id": None}}
        cache.merge_events([
            {"id": "e1", "event_date": "2026-10-01T10:00:00Z", "extra_data": {"content": "E1"}},
            {"id": "e2", "event_date": "2026-10-02T12:00:00Z", "extra_data": {"content": "E2"}},
        ])
        cache.save()

        # Reload in a new instance
        reloaded = TraceCache(cache_file=str(cache_file), enabled=True)
        assert len(reloaded.projects) == 1
        assert reloaded.projects[0]["name"] == "Work"
        assert reloaded.tasks["t1"]["content"] == "Task 1"
        assert len(reloaded.events) == 2
        assert reloaded.get_latest_event_date() == "2026-10-02T12:00:00Z"
        assert [e["id"] for e in reloaded.get_all_events()] == ["e2", "e1"]

    def test_disabled_cache(self, tmp_path):
        cache_file = tmp_path / "disabled_cache.json"
        cache = TraceCache(cache_file=str(cache_file), enabled=False)
        cache.projects = [{"id": "p1"}]
        cache.save()
        assert not cache_file.exists()


# ==============================================================================
# 5. CLI & Settings Precedence Tests
# ==============================================================================

class TestCLIAndSettings:
    """Test CLI parsing and configuration precedence."""

    def test_cli_flags_override_defaults(self):
        args = parse_args([
            "-f", "markdown",
            "-c", "work",
            "-s", "2026-09-01",
            "-e", "2026-09-30",
            "-o", "custom.md",
            "-t", "test_token_123",
            "--markdown-style", "flat",
        ])
        settings = resolve_settings(args)

        assert settings["format"] == "markdown"
        assert settings["category"] == "work"
        assert settings["start_date"] == "2026-09-01"
        assert settings["end_date"] == "2026-09-30"
        assert settings["output"] == "custom.md"
        assert settings["token"] == "test_token_123"
        assert settings["markdown_style"] == "flat"

    def test_md_alias_normalizes_to_markdown(self):
        args = parse_args(["-f", "md"])
        settings = resolve_settings(args)
        assert settings["format"] == "markdown"
        assert settings["output"] == "todoist_trace_export.md"

    def test_default_cache_path_in_dotdir(self):
        args = parse_args([])
        settings = resolve_settings(args)
        assert ".todoist-trace/cache.json" in settings["cache_file"]

    def test_cache_save_creates_parent_directory(self, tmp_path):
        nested_cache_file = tmp_path / "new_dir" / "sub" / "cache.json"
        cache = TraceCache(cache_file=str(nested_cache_file), enabled=True)
        cache.projects = [{"id": "p1"}]
        cache.save()
        assert nested_cache_file.is_file()


# ==============================================================================
# 6. Exporter Tests (CSV & Markdown)
# ==============================================================================

class TestExporters:
    """Test suite for CSV and Markdown exporters."""

    @pytest.fixture
    def sample_records(self):
        return [
            {
                "top_level_project": "work-areas",
                "project_path": "admin/email",
                "project_levels": ["admin", "email"],
                "date": "2026-09-15",
                "time": "14:20:00",
                "task_path": "Check inbox filters / triage / urgent",
                "parent_task_id": "p_task_1",
                "project_id": "proj_123",
                "event_id": "ev_001",
            },
            {
                "top_level_project": "work-areas",
                "project_path": "admin/email",
                "project_levels": ["admin", "email"],
                "date": "2026-09-15",
                "time": "14:25:00",
                "task_path": "Reply to vendor requests",
                "parent_task_id": "",
                "project_id": "proj_123",
                "event_id": "ev_002",
            },
            {
                "top_level_project": "personal",
                "project_path": "",
                "project_levels": [],
                "date": "2026-09-15",
                "time": "18:00:00",
                "task_path": 'Buy "groceries", apples & milk',
                "parent_task_id": "",
                "project_id": "proj_personal",
                "event_id": "ev_003",
            },
        ]

    def test_generate_csv(self, sample_records):
        csv_out = generate_csv(sample_records)
        lines = csv_out.strip().split("\n")

        # Verify header
        expected_header = "top_level_project,project_path,date,time,task_path,parent_task_id,project_id,event_id"
        assert lines[0] == expected_header
        assert len(lines) == 4

        # Verify RFC 4180 escaping on quotes & commas
        assert '"Buy ""groceries"", apples & milk"' in lines[3]
        assert "work-areas,admin/email,2026-09-15,14:25:00,Reply to vendor requests,,proj_123,ev_002" in lines[1] or lines[2]

    def test_export_csv_file_creation(self, sample_records, tmp_path):
        out_file = tmp_path / "subdir" / "export.csv"
        export_csv(sample_records, str(out_file))

        assert out_file.is_file()
        content = out_file.read_text(encoding="utf-8")
        assert "top_level_project,project_path,date" in content
        assert "ev_001" in content

    def test_generate_markdown_nested_style(self, sample_records):
        md_out = generate_markdown(sample_records, style="nested")

        # Check date heading
        assert "## 2026-09-15" in md_out

        # Check progressive headings
        assert "### work-areas" in md_out
        assert "#### admin" in md_out
        assert "##### email" in md_out

        # Check task bullets
        assert "- Check inbox filters / triage / urgent" in md_out
        assert "- Reply to vendor requests" in md_out

        # Check direct task under root project
        assert "### personal" in md_out
        assert '- Buy "groceries", apples & milk' in md_out

    def test_generate_markdown_flat_style(self, sample_records):
        md_out = generate_markdown(sample_records, style="flat")

        # Check date heading
        assert "## 2026-09-15" in md_out

        # Check flat project path heading
        assert "### work-areas" in md_out
        assert "#### admin/email" in md_out
        assert "#### admin\n" not in md_out

        # Check task bullets
        assert "- Check inbox filters / triage / urgent" in md_out
        assert "- Reply to vendor requests" in md_out

        # Check root project without sub-heading
        assert "### personal" in md_out
        assert '- Buy "groceries", apples & milk' in md_out

    def test_export_markdown_file_creation(self, sample_records, tmp_path):
        out_file = tmp_path / "nested" / "export.md"
        export_markdown(sample_records, str(out_file), style="nested")

        assert out_file.is_file()
        content = out_file.read_text(encoding="utf-8")
        assert "## 2026-09-15" in content
        assert "### work-areas" in content

    def test_empty_records(self, tmp_path):
        assert generate_markdown([]) == ""
        csv_empty = generate_csv([])
        assert csv_empty.strip() == "top_level_project,project_path,date,time,task_path,parent_task_id,project_id,event_id"


