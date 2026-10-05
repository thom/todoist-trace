"""
Unit tests for ProjectTreeResolver and TaskHierarchyResolver.
"""

from unittest.mock import MagicMock, patch
import pytest

from todoist_trace.resolvers import (
    LabelResolver,
    ProjectTreeResolver,
    SectionResolver,
    TaskHierarchyResolver,
    build_trace_records,
    calculate_due_variance,
    format_priority,
)


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


class TestTaskHierarchyResolver:
    """Test suite for TaskHierarchyResolver."""

    def test_top_level_task_without_parent(self):
        resolver = TaskHierarchyResolver(token="dummy_token", tz="UTC")
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

    @patch("todoist_trace.resolvers.requests.get")
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

        resolver = TaskHierarchyResolver(token="dummy_token", tz="UTC")
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

    @patch("todoist_trace.resolvers.requests.get")
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

    def test_subtask_resolution_when_parent_id_in_cached_task(self):
        """When activity event extra_data lacks parent_id, use parent_id from cached task."""
        resolver = TaskHierarchyResolver(token="dummy_token")
        resolver.task_cache["t_child"] = {
            "content": "Child Subtask",
            "parent_id": "t_parent",
        }
        resolver.task_cache["t_parent"] = {
            "content": "Parent Task",
            "parent_id": None,
        }

        event = {
            "id": "e_cached",
            "object_id": "t_child",
            "parent_project_id": "p1",
            "event_date": "2026-10-02T12:00:00Z",
            "extra_data": {
                "content": "Child Subtask",
                # Note: No parent_id here, simulating older Todoist activity events
            },
        }

        res = resolver.resolve(event)
        assert res["task_path"] == "Parent Task / Child Subtask"
        assert res["task_levels"] == ["Parent Task", "Child Subtask"]
        assert res["parent_task_id"] == "t_parent"

    @patch("todoist_trace.resolvers.requests.get")
    def test_subtask_resolution_when_parent_id_from_task_lookup(self, mock_get):
        """When neither extra_data nor cache has parent_id, fetch task on-demand."""
        def side_effect(url, headers=None, timeout=None):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "t_child" in url:
                mock_resp.json.return_value = {
                    "id": "t_child",
                    "content": "Child Task",
                    "parent_id": "t_parent",
                }
            elif "t_parent" in url:
                mock_resp.json.return_value = {
                    "id": "t_parent",
                    "content": "Parent Task",
                    "parent_id": None,
                }
            else:
                mock_resp.status_code = 404
            return mock_resp

        mock_get.side_effect = side_effect

        resolver = TaskHierarchyResolver(token="dummy_token")
        event = {
            "id": "e_lookup",
            "object_id": "t_child",
            "parent_project_id": "p1",
            "event_date": "2026-10-02T12:00:00Z",
            "extra_data": {
                "content": "Child Task",
            },
        }

        res = resolver.resolve(event)
        assert res["task_path"] == "Parent Task / Child Task"
        assert res["task_levels"] == ["Parent Task", "Child Task"]
        assert res["parent_task_id"] == "t_parent"

    @patch("todoist_trace.resolvers.requests.get")
    def test_lookup_task_retries_on_rate_limit_and_resolves(self, mock_get):
        """Test that lookup_task retries on HTTP 429 and replaces fallback tasks."""
        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0.01"}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            "id": "t_retry_99",
            "content": "Resolved Parent Task",
            "parent_id": None,
        }

        mock_get.side_effect = [resp_429, resp_200]

        resolver = TaskHierarchyResolver(token="dummy_token")
        resolver.task_cache["t_retry_99"] = {"content": "[Task t_retry_99]", "parent_id": None}

        task = resolver.lookup_task("t_retry_99")
        assert task is not None
        assert task["content"] == "Resolved Parent Task"
        assert mock_get.call_count == 2


    def test_subtask_resolution_from_parent_item_id_in_event(self):
        """When parent_item_id is set at event root and not in extra_data."""
        resolver = TaskHierarchyResolver(token="dummy_token")
        resolver.task_cache["t_parent"] = {
            "content": "Parent Task",
            "parent_id": None,
        }

        event = {
            "id": "e_root_parent",
            "object_id": "t_child",
            "parent_item_id": "t_parent",
            "parent_project_id": "p1",
            "event_date": "2026-10-02T12:00:00Z",
            "extra_data": {
                "content": "Child Subtask",
            },
        }

        res = resolver.resolve(event)
        assert res["task_path"] == "Parent Task / Child Subtask"
        assert res["task_levels"] == ["Parent Task", "Child Subtask"]
        assert res["parent_task_id"] == "t_parent"

    def test_timezone_conversion_positive_offset_cross_midnight(self):
        """Task completed late evening in UTC belongs to the next day in Europe/Zurich (UTC+2)."""
        resolver = TaskHierarchyResolver(token="dummy_token", tz="Europe/Zurich")
        event = {
            "id": "e_zurich",
            "object_id": "t_zurich",
            "event_date": "2026-09-30T22:30:00Z",
            "extra_data": {"content": "Late Night Task", "parent_id": None},
        }
        res = resolver.resolve(event)
        assert res["date"] == "2026-10-01"
        assert res["time"] == "00:30:00"

    def test_timezone_conversion_negative_offset_cross_midnight(self):
        """Task completed early morning in UTC belongs to the previous day in America/Los_Angeles (UTC-7)."""
        resolver = TaskHierarchyResolver(token="dummy_token", tz="America/Los_Angeles")
        event = {
            "id": "e_la",
            "object_id": "t_la",
            "event_date": "2026-10-02T05:30:00Z",
            "extra_data": {"content": "Evening Task In LA", "parent_id": None},
        }
        res = resolver.resolve(event)
        assert res["date"] == "2026-10-01"
        assert res["time"] == "22:30:00"

    def test_timezone_default_to_system_local(self):
        """Defaulting tz to None or 'local' resolves against the host system timezone."""
        resolver = TaskHierarchyResolver(token="dummy_token")
        event = {
            "id": "e_local",
            "object_id": "t_local",
            "event_date": "2026-10-02T12:00:00Z",
            "extra_data": {"content": "Local Task", "parent_id": None},
        }
        res = resolver.resolve(event)
        assert len(res["date"]) == 10
        assert len(res["time"]) == 8

    def test_format_event_datetime_empty_and_corrupt(self):
        from todoist_trace.resolvers import format_event_datetime
        assert format_event_datetime("") == ("", "")
        assert format_event_datetime(None) == ("", "")
        assert format_event_datetime("corrupt-string") == ("", "")
        assert format_event_datetime("2026-10-02") == ("2026-10-02", "")

    def test_invalid_timezone_raises_value_error(self):
        import pytest
        with pytest.raises(ValueError, match="Invalid timezone"):
            TaskHierarchyResolver(token="dummy_token", tz="Invalid/Zone_Name")

    def test_task_hierarchy_resolver_extracts_section_id(self):
        resolver = TaskHierarchyResolver(token="dummy_token")
        event = {
            "id": "e_sec",
            "object_id": "t_sec",
            "event_date": "2026-10-02T12:00:00Z",
            "parent_project_id": "proj_1",
            "extra_data": {
                "content": "Sectioned Task",
                "parent_id": None,
                "section_id": "sec_123",
            },
        }
        res = resolver.resolve(event)
        assert res["section_id"] == "sec_123"

        # Direct event section_id fallback
        event_direct = {
            "id": "e_sec2",
            "object_id": "t_sec2",
            "event_date": "2026-10-02T12:00:00Z",
            "parent_project_id": "proj_1",
            "section_id": "sec_456",
            "extra_data": {"content": "Direct Sec Task"},
        }
        res2 = resolver.resolve(event_direct)
        assert res2["section_id"] == "sec_456"


class TestSectionResolver:
    """Test suite for SectionResolver."""

    def test_resolve_empty_and_none(self):
        from todoist_trace.resolvers import SectionResolver
        resolver = SectionResolver(token="dummy")
        assert resolver.resolve(None) == ""
        assert resolver.resolve("") == ""

    def test_resolve_from_preloaded_list(self):
        from todoist_trace.resolvers import SectionResolver
        sections = [
            {"id": "s1", "name": "Backlog", "project_id": "p1"},
            {"id": "s2", "name": "In Progress", "project_id": "p1"},
        ]
        resolver = SectionResolver(preloaded_sections=sections)
        assert resolver.resolve("s1") == "Backlog"
        assert resolver.resolve("s2") == "In Progress"
        assert resolver.resolve("s3") == "[Section s3]"

    def test_resolve_from_preloaded_dict(self):
        from todoist_trace.resolvers import SectionResolver
        sections = {
            "s1": {"id": "s1", "name": "Sprint 1", "project_id": "p1"},
        }
        resolver = SectionResolver(preloaded_sections=sections)
        assert resolver.resolve("s1") == "Sprint 1"

    @patch("requests.get")
    def test_lookup_section_api_success(self, mock_get):
        from todoist_trace.resolvers import SectionResolver
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "s_live",
            "project_id": "p1",
            "name": "Live Section",
        }
        mock_get.return_value = mock_resp

        cache_mock = MagicMock()
        cache_mock.sections = {}

        resolver = SectionResolver(token="dummy_token", cache=cache_mock)
        sec_name = resolver.resolve("s_live")

        assert sec_name == "Live Section"
        assert "s_live" in resolver.section_cache
        assert cache_mock.sections["s_live"]["name"] == "Live Section"

    @patch("requests.get")
    def test_lookup_section_api_404(self, mock_get):
        from todoist_trace.resolvers import SectionResolver
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        resolver = SectionResolver(token="dummy_token")
        sec_name = resolver.resolve("s_missing")

        assert sec_name == "[Section s_missing]"
        assert resolver.section_cache["s_missing"]["name"] == "[Section s_missing]"

    @patch("requests.get")
    def test_lookup_section_network_error(self, mock_get):
        from todoist_trace.resolvers import SectionResolver
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Timeout")

        resolver = SectionResolver(token="dummy_token")
        assert resolver.resolve("s_err") == "[Section s_err]"

    def test_lookup_section_without_token(self):
        from todoist_trace.resolvers import SectionResolver
        resolver = SectionResolver(token=None)
        assert resolver.resolve("s_no_token") == "[Section s_no_token]"

    def test_build_trace_records_with_section_resolver(self):
        from todoist_trace.resolvers import (
            ProjectTreeResolver,
            SectionResolver,
            TaskHierarchyResolver,
            build_trace_records,
        )
        projects = [{"id": "p1", "name": "Work", "parent_id": None}]
        p_resolver = ProjectTreeResolver(projects)
        t_resolver = TaskHierarchyResolver(token="dummy")
        s_resolver = SectionResolver(preloaded_sections=[{"id": "sec_1", "name": "Sprint 1"}])

        events = [
            {
                "id": "e1",
                "object_id": "t1",
                "event_date": "2026-10-02T10:00:00Z",
                "parent_project_id": "p1",
                "extra_data": {
                    "content": "Deploy release",
                    "section_id": "sec_1",
                },
            }
        ]
        records = build_trace_records(events, p_resolver, t_resolver, section_resolver=s_resolver)
        assert len(records) == 1
        assert records[0]["section"] == "Sprint 1"
        assert records[0]["section_id"] == "sec_1"
        assert records[0]["top_level_project"] == "Work"
        assert records[0]["task_path"] == "Deploy release"


class TestLabelResolver:
    """Test suite for LabelResolver."""

    def test_resolve_label_by_id_and_name(self):
        preloaded = [
            {"id": "lbl_1", "name": "work"},
            {"id": "lbl_2", "name": "urgent"},
        ]
        resolver = LabelResolver(preloaded_labels=preloaded)

        assert resolver.resolve_label("lbl_1") == "work"
        assert resolver.resolve_label("lbl_2") == "urgent"
        assert resolver.resolve_label("unknown") == "unknown"
        assert resolver.resolve_label("custom_name") == "custom_name"

    def test_resolve_labels_list(self):
        preloaded = {"lbl_1": {"name": "frontend"}, "lbl_2": {"name": "backend"}}
        resolver = LabelResolver(preloaded_labels=preloaded)

        assert resolver.resolve_labels(["lbl_1", "lbl_2"]) == ["frontend", "backend"]
        assert resolver.resolve_labels(["lbl_1", "infra"]) == ["frontend", "infra"]
        assert resolver.resolve_labels([]) == []

    def test_format_tags(self):
        resolver = LabelResolver()
        assert resolver.format_tags(["work", "urgent"]) == "[@work, @urgent]"
        assert resolver.format_tags(["@already_prefixed"]) == "[@already_prefixed]"
        assert resolver.format_tags([]) == ""


class TestPriorityAndDueVariance:
    """Test suite for format_priority and calculate_due_variance."""

    def test_format_priority(self):
        assert format_priority(4) == "p1"
        assert format_priority("4") == "p1"
        assert format_priority(3) == "p2"
        assert format_priority("3") == "p2"
        assert format_priority(2) == "p3"
        assert format_priority("2") == "p3"
        assert format_priority(1) == "p4"
        assert format_priority(None) == "p4"
        assert format_priority("invalid") == "p4"

    def test_calculate_due_variance_on_time(self):
        res = calculate_due_variance("2026-10-01", "2026-10-01")
        assert res["due_date"] == "2026-10-01"
        assert res["days_variance"] == 0
        assert res["status"] == "on_time"
        assert res["variance_desc"] == "on time"

    def test_calculate_due_variance_overdue(self):
        res = calculate_due_variance("2026-09-29", "2026-10-01")
        assert res["due_date"] == "2026-09-29"
        assert res["days_variance"] == 2
        assert res["status"] == "overdue"
        assert res["variance_desc"] == "+2d overdue"

    def test_calculate_due_variance_early(self):
        res = calculate_due_variance("2026-10-05", "2026-10-01")
        assert res["due_date"] == "2026-10-05"
        assert res["days_variance"] == -4
        assert res["status"] == "early"
        assert res["variance_desc"] == "-4d early"

    def test_calculate_due_variance_was_overdue_flag(self):
        # Even if dates are same day, was_overdue flag marks it overdue
        res = calculate_due_variance("2026-10-01", "2026-10-01", was_overdue=True)
        assert res["status"] == "overdue"
        assert res["variance_desc"] == "+1d overdue"

    def test_calculate_due_variance_undated_and_invalid(self):
        res_none = calculate_due_variance(None, "2026-10-01")
        assert res_none["status"] == "undated"
        assert res_none["variance_desc"] == ""
        assert res_none["due_date"] == ""

        res_inv = calculate_due_variance("not-a-date", "2026-10-01")
        assert res_inv["status"] == "undated"


class TestExtendedMetadataResolving:
    """Test suite for resolving extended metadata in task resolver and trace records."""

    def test_resolve_event_with_extra_data_metadata(self):
        resolver = TaskHierarchyResolver(token="dummy")
        event = {
            "id": "e_meta",
            "object_id": "t_meta",
            "event_date": "2026-10-02T15:30:00Z",
            "parent_project_id": "p1",
            "extra_data": {
                "content": "Prepare release",
                "description": "Ensure changelog is updated",
                "priority": 4,
                "labels": ["urgent", "release"],
                "due_date": "2026-10-01",
                "was_overdue": True,
            },
        }
        res = resolver.resolve(event)
        assert res["task_path"] == "Prepare release"
        assert res["description"] == "Ensure changelog is updated"
        assert res["priority"] == "p1"
        assert res["raw_priority"] == 4
        assert res["labels"] == ["urgent", "release"]
        assert res["due_date"] == "2026-10-01"
        assert res["due_status"] == "overdue"
        assert "+1d overdue" in res["due_variance"]

    def test_build_trace_records_full_extended_metadata(self):
        projects = [{"id": "p1", "name": "Work", "parent_id": None}]
        p_resolver = ProjectTreeResolver(projects)
        t_resolver = TaskHierarchyResolver(token="dummy")
        s_resolver = SectionResolver(preloaded_sections=[{"id": "sec_1", "name": "Sprint 1"}])
        l_resolver = LabelResolver(preloaded_labels=[{"id": "l1", "name": "backend"}])

        events = [
            {
                "id": "e10",
                "object_id": "t10",
                "event_date": "2026-10-02T12:00:00Z",
                "parent_project_id": "p1",
                "extra_data": {
                    "content": "Database migration",
                    "section_id": "sec_1",
                    "description": "Run alembic upgrade head",
                    "priority": 3,
                    "labels": ["l1", "db"],
                    "due_date": "2026-10-02",
                },
            }
        ]
        records = build_trace_records(
            events,
            p_resolver,
            t_resolver,
            section_resolver=s_resolver,
            label_resolver=l_resolver,
        )
        assert len(records) == 1
        r = records[0]
        assert r["top_level_project"] == "Work"
        assert r["section"] == "Sprint 1"
        assert r["task_path"] == "Database migration"
        assert r["description"] == "Run alembic upgrade head"
        assert r["priority"] == "p2"
        assert r["labels"] == ["backend", "db"]
        assert r["due_date"] == "2026-10-02"
        assert r["due_variance"] == "on time"

