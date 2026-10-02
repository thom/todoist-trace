"""
Unit tests for ProjectTreeResolver and TaskHierarchyResolver.
"""

from unittest.mock import MagicMock, patch
import pytest

from todoist_trace.resolvers import (
    ProjectTreeResolver,
    TaskHierarchyResolver,
    build_trace_records,
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
