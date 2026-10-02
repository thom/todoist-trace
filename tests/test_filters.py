"""
Unit tests for record filtering (category and date range).
"""

from todoist_trace.filters import filter_records


class TestFiltering:
    """Test suite for category and date filtering."""

    def test_category_work_matching(self, sample_filter_records):
        filtered = filter_records(sample_filter_records, category="work")
        assert len(filtered) == 2
        assert {r["task_path"] for r in filtered} == {"Task 1", "Task 2"}

    def test_category_personal_matching(self, sample_filter_records):
        filtered = filter_records(sample_filter_records, category="personal")
        assert len(filtered) == 2
        assert {r["task_path"] for r in filtered} == {"Task 3", "Task 4"}

    def test_category_all(self, sample_filter_records):
        filtered = filter_records(sample_filter_records, category="all")
        assert len(filtered) == 5

    def test_date_range_inclusive(self, sample_filter_records):
        filtered = filter_records(
            sample_filter_records,
            category="all",
            start_date="2026-10-01",
            end_date="2026-10-02",
        )
        assert len(filtered) == 4
        assert "Task 4" not in {r["task_path"] for r in filtered}

    def test_start_date_only(self, sample_filter_records):
        filtered = filter_records(
            sample_filter_records,
            category="all",
            start_date="2026-10-02",
        )
        assert len(filtered) == 2
        assert {r["task_path"] for r in filtered} == {"Task 2", "Task 5"}

    def test_combined_category_and_date(self, sample_filter_records):
        filtered = filter_records(
            sample_filter_records,
            category="work",
            start_date="2026-10-02",
            end_date="2026-10-02",
        )
        assert len(filtered) == 1
        assert filtered[0]["task_path"] == "Task 2"

    def test_reversed_dates_returns_empty(self, sample_filter_records):
        filtered = filter_records(
            sample_filter_records,
            category="all",
            start_date="2026-10-10",
            end_date="2026-10-01",
        )
        assert filtered == []

    def test_future_start_date_returns_empty(self, sample_filter_records):
        filtered = filter_records(
            sample_filter_records,
            category="all",
            start_date="2099-01-01",
        )
        assert filtered == []

    def test_start_equals_end_date_exact_day(self, sample_filter_records):
        filtered = filter_records(
            sample_filter_records,
            category="all",
            start_date="2026-10-01",
            end_date="2026-10-01",
        )
        assert len(filtered) == 2
        assert {r["task_path"] for r in filtered} == {"Task 1", "Task 3"}
