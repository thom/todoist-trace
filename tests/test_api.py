"""
Unit tests for Todoist REST API client functions, specifically sections.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from todoist_trace.api import (
    fetch_completed_activities,
    fetch_labels,
    fetch_projects,
    fetch_section,
    fetch_sections,
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

