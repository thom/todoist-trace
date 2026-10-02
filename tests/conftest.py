"""
Shared fixtures and test configuration for todoist-trace test suite.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List
import pytest

# Ensure project root is on sys.path for direct imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def sample_filter_records() -> List[Dict[str, Any]]:
    """Sample records for filtering tests."""
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


@pytest.fixture
def sample_exporter_records() -> List[Dict[str, Any]]:
    """Sample records for CSV and Markdown exporter tests."""
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
