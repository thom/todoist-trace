"""
Filtering logic for todoist-trace records.
Supports filtering by category (work, personal, all) and date ranges.
"""

from typing import Any, Dict, List, Optional


def filter_records(
    records: List[Dict[str, Any]],
    category: str = "all",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Filter records by category and date range.
    - category: 'work' (matches 'work' or 'work-areas'), 'personal' (matches 'personal' or 'personal-areas'), or 'all'
    - start_date: 'YYYY-MM-DD' (inclusive)
    - end_date: 'YYYY-MM-DD' (inclusive)
    """
    if start_date and end_date and start_date > end_date:
        return []

    filtered = []
    cat_lower = (category or "all").lower()

    for r in records:
        top_lower = r.get("top_level_project", "").lower()

        # Category check
        if cat_lower == "work":
            if not (top_lower.startswith("work") or top_lower.startswith("work-areas")):
                continue
        elif cat_lower == "personal":
            if not (top_lower.startswith("personal") or top_lower.startswith("personal-areas")):
                continue

        # Date range check
        rec_date = r.get("date", "")
        if start_date and rec_date < start_date:
            continue
        if end_date and rec_date > end_date:
            continue

        filtered.append(r)

    return filtered
