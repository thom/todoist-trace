"""
Unit tests for Todoist REST API client functions, specifically sections.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from todoist_trace.api import (
    fetch_archived_sections,
    fetch_completed_activities,
    fetch_completed_tasks_by_date,
    fetch_labels,
    fetch_projects,
    fetch_section,
    fetch_sections,
    fetch_task,
    fetch_tasks,
)


class TestApiSections:
    """Test suite for section-related API endpoints."""

    @patch("requests.get")
    def test_fetch_sections_success_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "s1", "name": "Backlog", "project_id": "p1"},
            {"id": "s2", "name": "In Progress", "project_id": "p1"},
        ]
        mock_get.return_value = mock_resp

        res = fetch_sections("dummy_token")
        assert len(res) == 2
        assert res[0]["name"] == "Backlog"
        mock_get.assert_called_once_with(
            "https://api.todoist.com/api/v1/sections",
            headers={"Authorization": "Bearer dummy_token"},
            timeout=15,
        )

    @patch("requests.get")
    def test_fetch_sections_success_dict(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [{"id": "s1", "name": "Sprint 1", "project_id": "p1"}]
        }
        mock_get.return_value = mock_resp

        res = fetch_sections("dummy_token")
        assert len(res) == 1
        assert res[0]["id"] == "s1"

    @patch("requests.get")
    def test_fetch_sections_cursor_pagination(self, mock_get):
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "results": [{"id": "s1", "name": "Sprint 1", "project_id": "p1"}],
            "next_cursor": "cursor_token_123",
        }
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "results": [{"id": "s2", "name": "Sprint 2", "project_id": "p1"}],
            "next_cursor": None,
        }
        mock_get.side_effect = [resp1, resp2]

        res = fetch_sections("dummy_token")
        assert len(res) == 2
        assert res[0]["id"] == "s1"
        assert res[1]["id"] == "s2"
        assert mock_get.call_count == 2

    @patch("requests.get")
    def test_fetch_archived_sections_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "sections": [
                {"id": "arch-sec-1", "name": "Sprint 0 (Archived)", "project_id": "p1"}
            ]
        }
        mock_get.return_value = mock_resp

        res = fetch_archived_sections("dummy_token", "p1")
        assert len(res) == 1
        assert res[0]["id"] == "arch-sec-1"
        mock_get.assert_called_once_with(
            "https://api.todoist.com/api/v1/sections/archived?project_id=p1",
            headers={"Authorization": "Bearer dummy_token"},
            timeout=15,
        )

    @patch("requests.get")
    def test_fetch_archived_sections_failure_graceful(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        res = fetch_archived_sections("dummy_token", "p1")
        assert res == []

    @patch("requests.get")
    def test_fetch_sections_unauthorized(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="Invalid Todoist API token"):
            fetch_sections("bad_token")

    @patch("requests.get")
    def test_fetch_sections_error_status(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        with pytest.raises(RuntimeError, match="HTTP 500"):
            fetch_sections("dummy_token")

    @patch("requests.get")
    def test_fetch_sections_network_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("Connection refused")

        with pytest.raises(RuntimeError, match="Network error fetching sections"):
            fetch_sections("dummy_token")

    @patch("requests.get")
    def test_fetch_section_single_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "s10",
            "name": "Design",
            "project_id": "p1",
        }
        mock_get.return_value = mock_resp

        res = fetch_section("dummy_token", "s10")
        assert res is not None
        assert res["name"] == "Design"
        mock_get.assert_called_once_with(
            "https://api.todoist.com/api/v1/sections/s10",
            headers={"Authorization": "Bearer dummy_token"},
            timeout=10,
        )

    @patch("requests.get")
    def test_fetch_section_single_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        res = fetch_section("dummy_token", "nonexistent")
        assert res is None

    @patch("requests.get")
    def test_fetch_section_single_network_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("Timeout")

        res = fetch_section("dummy_token", "s_err")
        assert res is None


class TestApiLabels:
    """Test suite for label-related API endpoints."""

    @patch("requests.get")
    def test_fetch_labels_success_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": "l1", "name": "work", "color": "charcoal"},
            {"id": "l2", "name": "urgent", "color": "red"},
        ]
        mock_get.return_value = mock_resp

        res = fetch_labels("dummy_token")
        assert len(res) == 2
        assert res[0]["name"] == "work"
        assert res[1]["color"] == "red"
        mock_get.assert_called_once_with(
            "https://api.todoist.com/api/v1/labels",
            headers={"Authorization": "Bearer dummy_token"},
            params={},
            timeout=15,
        )

    @patch("requests.get")
    def test_fetch_labels_paginated_dict(self, mock_get):
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "results": [{"id": "l1", "name": "work"}],
            "next_cursor": "cursor_page2",
        }

        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "results": [{"id": "l2", "name": "personal"}],
            "next_cursor": None,
        }

        mock_get.side_effect = [resp1, resp2]

        res = fetch_labels("dummy_token")
        assert len(res) == 2
        assert [l["name"] for l in res] == ["work", "personal"]
        assert mock_get.call_count == 2

    @patch("requests.get")
    def test_fetch_labels_unauthorized(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="Invalid Todoist API token"):
            fetch_labels("invalid_token")

    @patch("requests.get")
    def test_fetch_labels_server_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 502
        mock_resp.text = "Bad Gateway"
        mock_get.return_value = mock_resp

        with pytest.raises(RuntimeError, match="HTTP 502"):
            fetch_labels("dummy_token")

    @patch("requests.get")
    def test_fetch_labels_network_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")

        with pytest.raises(RuntimeError, match="Network error fetching labels"):
            fetch_labels("dummy_token")


class TestApiTasks:
    """Test suite for task-related API endpoints."""

    @patch("requests.get")
    def test_fetch_tasks_paginated(self, mock_get):
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "results": [{"id": "t1", "content": "Task Alpha", "parent_id": None}],
            "next_cursor": "cur_123",
        }

        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "results": [{"id": "t2", "content": "Task Beta", "parent_id": "t1"}],
            "next_cursor": None,
        }

        mock_get.side_effect = [resp1, resp2]

        tasks = fetch_tasks("dummy_token")
        assert len(tasks) == 2
        assert tasks[0]["id"] == "t1"
        assert tasks[1]["parent_id"] == "t1"
        assert mock_get.call_count == 2

    @patch("requests.get")
    def test_fetch_tasks_unauthorized(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        with pytest.raises(ValueError, match="Invalid Todoist API token"):
            fetch_tasks("invalid_token")

    @patch("requests.get")
    def test_fetch_task_single_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "t100",
            "content": "Single Task",
            "parent_id": "t_parent",
        }
        mock_get.return_value = mock_resp

        t = fetch_task("dummy_token", "t100")
        assert t is not None
        assert t["id"] == "t100"
        assert t["parent_id"] == "t_parent"

    @patch("requests.get")
    def test_fetch_task_single_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        assert fetch_task("dummy_token", "t_nonexistent") is None

    @patch("requests.get")
    def test_fetch_completed_tasks_by_date(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {"id": "c1", "content": "Completed Child", "parent_id": "p1"},
                {"id": "p1", "content": "Completed Parent", "parent_id": None},
            ],
            "next_cursor": None,
        }
        mock_get.return_value = mock_resp

        items = fetch_completed_tasks_by_date(
            "dummy_token",
            since="2026-01-01T00:00:00Z",
            until="2026-01-15T00:00:00Z",
            project_id="proj_1",
        )
        assert len(items) == 2
        assert items[0]["parent_id"] == "p1"
        mock_get.assert_called_once()


class TestPreloadTasks:
    """Test suite for preload_tasks orchestration."""

    @patch("todoist_trace.main.fetch_completed_tasks_by_date")
    @patch("todoist_trace.main.fetch_tasks")
    def test_preload_tasks_populates_cache(self, mock_active, mock_completed):
        from todoist_trace.main import preload_tasks

        mock_active.return_value = [
            {"id": "act-1", "content": "Active Task", "parent_id": None},
        ]
        mock_completed.return_value = [
            {"id": "comp-1", "content": "Completed Subtask", "parent_id": "comp-parent"},
        ]

        mock_cache = MagicMock()
        mock_cache.enabled = True

        projects = [{"id": "proj-archived", "is_archived": True}]
        events = [
            {"parent_project_id": "proj-archived", "event_date": "2026-02-01T10:00:00Z"},
        ]

        preload_tasks(
            token="dummy_token",
            cache=mock_cache,
            projects=projects,
            events=events,
            req_start="2026-01-01T00:00:00Z",
            req_end="2026-02-15T00:00:00Z",
        )

        mock_cache.save_tasks.assert_called_once()
        saved = mock_cache.save_tasks.call_args[0][0]
        assert "act-1" in saved
        assert "comp-1" in saved
        assert saved["comp-1"]["parent_id"] == "comp-parent"

    @patch("todoist_trace.main.fetch_completed_tasks_by_date")
    @patch("todoist_trace.main.fetch_tasks")
    def test_preload_tasks_pads_date_spans_for_archived_projects(self, mock_active, mock_completed):
        from todoist_trace.main import preload_tasks

        mock_active.return_value = []
        mock_completed.return_value = []

        mock_cache = MagicMock()
        mock_cache.enabled = True

        projects = [{"id": "proj-archived-99", "is_archived": True}]
        events = [
            {"parent_project_id": "proj-archived-99", "event_date": "2026-03-10T12:00:00Z"},
            {"parent_project_id": "proj-archived-99", "event_date": "2026-03-15T18:00:00Z"},
        ]

        preload_tasks(
            token="dummy_token",
            cache=mock_cache,
            projects=projects,
            events=events,
        )

        archived_calls = [
            call for call in mock_completed.call_args_list
            if call.kwargs.get("project_id") == "proj-archived-99"
        ]
        assert len(archived_calls) == 1
        args, kwargs = archived_calls[0]
        assert args[1].startswith("2026-03-08")
        assert args[2].startswith("2026-03-17")

    @patch("todoist_trace.main.fetch_archived_sections")
    @patch("todoist_trace.main.fetch_completed_tasks_by_date")
    @patch("todoist_trace.main.fetch_tasks")
    def test_preload_tasks_preloads_archived_sections_for_events(
        self, mock_active, mock_completed, mock_arch_secs
    ):
        from todoist_trace.main import preload_tasks

        mock_active.return_value = []
        mock_completed.return_value = []
        mock_arch_secs.return_value = [
            {"id": "arch-sec-abc", "name": "Sprint Alpha", "project_id": "proj-1"}
        ]

        sections_dict = {}
        mock_cache = MagicMock()
        mock_cache.enabled = True
        mock_cache.sections = sections_dict

        projects = [{"id": "proj-1", "is_archived": False}]
        events = [
            {
                "parent_project_id": "proj-1",
                "event_date": "2026-04-01T12:00:00Z",
                "extra_data": {"section_id": "arch-sec-abc"},
            }
        ]

        preload_tasks(
            token="dummy_token",
            cache=mock_cache,
            projects=projects,
            events=events,
        )

        mock_arch_secs.assert_called_once_with("dummy_token", "proj-1")
        assert "arch-sec-abc" in sections_dict
        assert sections_dict["arch-sec-abc"]["name"] == "Sprint Alpha"





