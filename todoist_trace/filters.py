"""
Filtering logic for todoist-trace records.
Supports filtering by category (work, personal, others, all) and date ranges.
"""

from typing import Any, Dict, List, Optional
from .config import get_project_category


def filter_records(
    records: List[Dict[str, Any]],
    category: str = "all",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    categories_config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Filter records by category and date range.
    - category: 'work', 'personal', 'others', or 'all'
    - start_date: 'YYYY-MM-DD' (inclusive)
    - end_date: 'YYYY-MM-DD' (inclusive)
    - categories_config: optional dict mapping category names to project patterns
    """
    if start_date and end_date and start_date > end_date:
        return []

    filtered = []
    cat_lower = (category or "all").lower()

    for r in records:
        top_proj = r.get("top_level_project", "")
        rec_cat = get_project_category(top_proj, categories_config)

        # Category check
        if cat_lower != "all":
            if cat_lower == "others":
                if rec_cat != "others":
                    continue
            else:
                r_direct = (r.get("category") or "").lower()
                if rec_cat != cat_lower and r_direct != cat_lower:
                    continue

        # Date range check
        rec_date = r.get("date", "")
        if start_date and rec_date < start_date:
            continue
        if end_date and rec_date > end_date:
            continue

        filtered.append(r)

    return filtered
