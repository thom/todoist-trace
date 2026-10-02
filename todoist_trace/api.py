"""
Todoist REST API v1 client for todoist-trace.
Strictly read-only and non-destructive: only HTTP GET requests are performed.
"""

from typing import Any, Dict, List, Optional
import requests


def fetch_projects(token: str) -> List[Dict[str, Any]]:
    """
    Fetch active and archived projects from the Todoist API.
    Handles cursor pagination across active and archived endpoints.
    Endpoint: https://api.todoist.com/api/v1/projects
    Archived endpoint: https://api.todoist.com/api/v1/projects/archived
    """
    headers = {
        "Authorization": f"Bearer {token}",
    }
    all_projects: List[Dict[str, Any]] = []

    # 1. Fetch active projects (paginated)
    url = "https://api.todoist.com/api/v1/projects"
    cursor = None
    while True:
        params = {"cursor": cursor} if cursor else {}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error communicating with Todoist API: {e}") from e

        if resp.status_code == 401:
            raise ValueError("Invalid Todoist API token. Please check your credentials.")
        if resp.status_code != 200:
            raise RuntimeError(f"Todoist API returned HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        all_projects.extend(results)

        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        if not cursor:
            break

    # 2. Fetch archived projects
    archived_url = "https://api.todoist.com/api/v1/projects/archived"
    cursor = None
    while True:
        params = {"cursor": cursor} if cursor else {}
        try:
            resp = requests.get(archived_url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error fetching archived projects: {e}") from e

        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for p in results:
                p["is_archived"] = True
            all_projects.extend(results)
            cursor = data.get("next_cursor") if isinstance(data, dict) else None
            if not cursor:
                break
        else:
            break

    return all_projects


def fetch_completed_activities(
    token: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch completed task activity records using strictly read-only HTTP GET.
    Endpoint: https://api.todoist.com/api/v1/activities
    """
    url = "https://api.todoist.com/api/v1/activities"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    events: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    page = 0

    while True:
        params: Dict[str, Any] = {
            "object_type": "item",
            "event_type": "completed",
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error fetching activity logs: {e}") from e

        if resp.status_code == 401:
            raise ValueError("Invalid Todoist API token.")
        if resp.status_code != 200:
            raise RuntimeError(f"Todoist API returned HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        events.extend(results)

        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        page += 1
        if not cursor or (max_pages and page >= max_pages):
            break

    return events
