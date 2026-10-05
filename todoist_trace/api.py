"""
Todoist REST API v1 client for todoist-trace.
Strictly read-only and non-destructive: only HTTP GET requests are performed.
"""

import time
from typing import Any, Callable, Dict, List, Optional
import requests


def _request_with_retry(
    url: str,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
    max_retries: int = 4,
) -> requests.Response:
    """Execute a strictly read-only HTTP GET request with retry on HTTP 429 and transient errors."""
    kwargs: Dict[str, Any] = {"headers": headers, "timeout": timeout}
    if params is not None:
        kwargs["params"] = params

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, **kwargs)
            if resp.status_code == 429:
                retry_after_str = resp.headers.get("Retry-After")
                try:
                    retry_sec = float(retry_after_str) if retry_after_str else (1.5 * (attempt + 1))
                except (ValueError, TypeError):
                    retry_sec = 1.5 * (attempt + 1)
                time.sleep(min(retry_sec, 30.0))
                continue
            return resp
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(1.0 * (attempt + 1))
    return resp



def fetch_projects(
    token: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> List[Dict[str, Any]]:
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
            resp = _request_with_retry(url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error communicating with Todoist API: {e}") from e

        if resp.status_code == 401:
            raise ValueError("Invalid Todoist API token. Please check your credentials.")
        if resp.status_code != 200:
            raise RuntimeError(f"Todoist API returned HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        all_projects.extend(results)

        if progress_cb:
            progress_cb(len(all_projects), 0)

        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        if not cursor:
            break

    active_count = len(all_projects)

    # 2. Fetch archived projects
    archived_url = "https://api.todoist.com/api/v1/projects/archived"
    cursor = None
    archived_count = 0
    while True:
        params = {"cursor": cursor} if cursor else {}
        try:
            resp = _request_with_retry(archived_url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error fetching archived projects: {e}") from e

        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for p in results:
                p["is_archived"] = True
            all_projects.extend(results)
            archived_count += len(results)

            if progress_cb:
                progress_cb(active_count, archived_count)

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
    progress_cb: Optional[Callable[[int, Optional[str]], None]] = None,
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
            resp = _request_with_retry(url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error fetching activity logs: {e}") from e

        if resp.status_code == 401:
            raise ValueError("Invalid Todoist API token.")
        if resp.status_code != 200:
            raise RuntimeError(f"Todoist API returned HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        events.extend(results)

        oldest_date = results[-1].get("event_date") if results and isinstance(results[-1], dict) else None
        if progress_cb:
            progress_cb(len(events), oldest_date)

        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        page += 1
        if not cursor or (max_pages and page >= max_pages):
            break

    return events


def fetch_sections(token: str) -> List[Dict[str, Any]]:
    """
    Fetch all active sections from the Todoist API using strictly read-only HTTP GET.
    Endpoint: https://api.todoist.com/api/v1/sections
    """
    url = "https://api.todoist.com/api/v1/sections"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    try:
        resp = _request_with_retry(url, headers=headers, timeout=15)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error fetching sections: {e}") from e

    if resp.status_code == 401:
        raise ValueError("Invalid Todoist API token.")
    if resp.status_code != 200:
        raise RuntimeError(f"Todoist API returned HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("results", [])
    return []


def fetch_section(token: str, section_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single section by its ID using strictly read-only HTTP GET.
    Endpoint: https://api.todoist.com/api/v1/sections/{section_id}
    """
    url = f"https://api.todoist.com/api/v1/sections/{section_id}"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    try:
        resp = _request_with_retry(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException:
        return None

    if resp.status_code == 200:
        data = resp.json()
        return data if isinstance(data, dict) else None
    return None


def fetch_labels(token: str) -> List[Dict[str, Any]]:
    """
    Fetch all labels from the Todoist API using strictly read-only HTTP GET.
    Endpoint: https://api.todoist.com/api/v1/labels
    """
    url = "https://api.todoist.com/api/v1/labels"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    all_labels: List[Dict[str, Any]] = []
    cursor = None
    while True:
        params = {"cursor": cursor} if cursor else {}
        try:
            resp = _request_with_retry(url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error fetching labels: {e}") from e

        if resp.status_code == 401:
            raise ValueError("Invalid Todoist API token.")
        if resp.status_code != 200:
            raise RuntimeError(f"Todoist API returned HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        if isinstance(data, list):
            all_labels.extend(data)
            break
        elif isinstance(data, dict):
            results = data.get("results", [])
            all_labels.extend(results)
            cursor = data.get("next_cursor")
            if not cursor:
                break
        else:
            break

    return all_labels


def fetch_tasks(token: str, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch active tasks from the Todoist API using strictly read-only HTTP GET.
    Endpoint: https://api.todoist.com/api/v1/tasks
    """
    url = "https://api.todoist.com/api/v1/tasks"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    all_tasks: List[Dict[str, Any]] = []
    cursor = None
    while True:
        params: Dict[str, Any] = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        if project_id:
            params["project_id"] = project_id
        try:
            resp = _request_with_retry(url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error fetching active tasks: {e}") from e

        if resp.status_code == 401:
            raise ValueError("Invalid Todoist API token.")
        if resp.status_code != 200:
            break

        data = resp.json()
        if isinstance(data, list):
            all_tasks.extend(data)
            break
        elif isinstance(data, dict):
            results = data.get("results", [])
            all_tasks.extend(results)
            cursor = data.get("next_cursor")
            if not cursor:
                break
        else:
            break

    return all_tasks


def fetch_task(token: str, task_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single task by its ID using strictly read-only HTTP GET.
    Endpoint: https://api.todoist.com/api/v1/tasks/{task_id}
    """
    url = f"https://api.todoist.com/api/v1/tasks/{task_id}"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    try:
        resp = _request_with_retry(url, headers=headers, timeout=10)
    except requests.exceptions.RequestException:
        return None

    if resp.status_code == 200:
        data = resp.json()
        return data if isinstance(data, dict) else None
    return None


def fetch_completed_tasks_by_date(
    token: str,
    since: str,
    until: str,
    project_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """
    Fetch completed tasks for a completion date range (split into <=88 day windows).
    Endpoint: https://api.todoist.com/api/v1/tasks/completed/by_completion_date
    """
    from datetime import datetime, timezone, timedelta

    def _parse_iso(s: str) -> datetime:
        clean = s.replace("Z", "+00:00")
        if "T" not in clean:
            clean = f"{clean}T00:00:00+00:00"
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    try:
        s_dt = _parse_iso(since)
        u_dt = _parse_iso(until)
    except Exception:
        return []

    if s_dt >= u_dt:
        u_dt = s_dt + timedelta(days=1)

    windows = []
    curr = s_dt
    while curr < u_dt:
        nxt = min(curr + timedelta(days=88), u_dt)
        windows.append((curr.strftime("%Y-%m-%dT%H:%M:%SZ"), nxt.strftime("%Y-%m-%dT%H:%M:%SZ")))
        curr = nxt

    url = "https://api.todoist.com/api/v1/tasks/completed/by_completion_date"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    all_items: List[Dict[str, Any]] = []

    for w_start, w_end in windows:
        cursor = None
        while True:
            params: Dict[str, Any] = {
                "since": w_start,
                "until": w_end,
                "limit": min(limit, 200),
            }
            if cursor:
                params["cursor"] = cursor
            if project_id:
                params["project_id"] = project_id

            try:
                resp = _request_with_retry(url, headers=headers, params=params, timeout=15)
            except requests.exceptions.RequestException:
                break

            if resp.status_code != 200:
                break

            data = resp.json()
            items = data.get("items", []) if isinstance(data, dict) else []
            all_items.extend(items)
            cursor = data.get("next_cursor") if isinstance(data, dict) else None
            if not cursor:
                break

    return all_items
