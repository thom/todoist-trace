"""
Filtering logic for todoist-trace records.
Supports filtering by category (work, personal, others, all) and date ranges.
"""

from typing import Any, Dict, List, Optional, Tuple
from .config import get_project_category


def deduplicate_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate same-day task completions by (date, task_id).
    When a task is checked off, renamed, and checked off again on the same day,
    preserves only the latest completion event while maintaining original order.
    """
    if not records:
        return []

    # Map each (date, task_id) to the latest completion event
    best_event_for_key: Dict[Tuple[str, str], Tuple[Tuple[str, str, str], Any]] = {}
    for r in records:
        tid = str(r.get("task_id") or "").strip()
        dt = str(r.get("date") or "").strip()
        if tid and dt:
            key = (dt, tid)
            ts = (str(r.get("date") or ""), str(r.get("time") or ""), str(r.get("event_date") or ""))
            if key not in best_event_for_key or ts > best_event_for_key[key][0]:
                best_event_for_key[key] = (ts, r.get("event_id"))

    # Filter records preserving original sequence
    deduped: List[Dict[str, Any]] = []
    seen: set = set()
    for r in records:
        tid = str(r.get("task_id") or "").strip()
        dt = str(r.get("date") or "").strip()
        if tid and dt:
            key = (dt, tid)
            best_ts, best_eid = best_event_for_key[key]
            if r.get("event_id") != best_eid:
                continue
            if key in seen:
                continue
            seen.add(key)
        deduped.append(r)
    return deduped


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
            elif rec_cat != cat_lower:
                continue

        # Date range check
        rec_date = r.get("date", "")
        if start_date and rec_date < start_date:
            continue
        if end_date and rec_date > end_date:
            continue

        filtered.append(r)

    return deduplicate_records(filtered)
