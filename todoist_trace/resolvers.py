"""
Project and task hierarchy resolvers for todoist-trace.
Traces multi-level project trees and recursive parent-child task structures.
"""

from datetime import datetime, timezone, tzinfo
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import requests

from .config import resolve_timezone


def format_event_datetime(
    event_date_str: Optional[str],
    tz: Optional[Union[str, tzinfo]] = None,
) -> Tuple[str, str]:
    """
    Format a UTC ISO-8601 event date string into (local_date, local_time).
    Defaults to system local timezone if tz is None.
    Returns ("", "") if event_date_str is empty or unparseable.
    """
    if not event_date_str:
        return ("", "")

    # Date-only string (no time component)
    if "T" not in event_date_str:
        try:
            datetime.strptime(event_date_str[:10], "%Y-%m-%d")
            return (event_date_str[:10], "")
        except Exception:
            return ("", "")

    target_tz = resolve_timezone(tz)
    try:
        dt = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local_dt = dt.astimezone(target_tz)
        return (local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M:%S"))
    except Exception:
        return ("", "")


class ProjectTreeResolver:
    """Resolves project hierarchies into root ancestor and relative sub-project path."""

    def __init__(self, projects: List[Dict[str, Any]], hierarchy_store: Optional[Any] = None):
        self.hierarchy_store = hierarchy_store
        self.projects_by_id: Dict[str, Dict[str, Any]] = {
            str(p["id"]): dict(p) for p in projects if "id" in p
        }
        if self.hierarchy_store:
            for pid, hp in self.hierarchy_store.projects.items():
                if pid not in self.projects_by_id:
                    self.projects_by_id[pid] = {
                        "id": pid,
                        "name": hp.get("name", "Unnamed"),
                        "parent_id": hp.get("parent_id"),
                        "is_archived": hp.get("is_archived", False),
                        "is_deleted": hp.get("is_deleted", False),
                    }
                else:
                    if not self.projects_by_id[pid].get("parent_id") and hp.get("parent_id"):
                        self.projects_by_id[pid]["parent_id"] = hp["parent_id"]
        self.cache: Dict[str, Dict[str, Any]] = {}

    def resolve(self, project_id: Optional[Any]) -> Dict[str, Any]:
        """
        Recursively resolve project hierarchy.
        Returns:
            {
                "top_level_project": str,
                "project_path": str,
                "project_levels": List[str],
            }
        """
        if not project_id:
            return {
                "top_level_project": "Unknown",
                "project_path": "",
                "project_levels": [],
            }

        pid_str = str(project_id)
        if pid_str in self.cache:
            return self.cache[pid_str]

        chain: List[str] = []
        curr: Optional[str] = pid_str
        visited: set = set()

        while curr and curr in self.projects_by_id and curr not in visited:
            visited.add(curr)
            proj = self.projects_by_id[curr]
            chain.append(proj.get("name", "Unnamed"))
            parent = proj.get("parent_id")
            if not parent and self.hierarchy_store:
                parent = self.hierarchy_store.get_parent_id(curr)
            curr = str(parent) if parent else None

        chain.reverse()

        # Fallback path protection: if chain has <= 1 item and hierarchy_store has a fallback_path
        if pid_str in self.projects_by_id and self.hierarchy_store:
            fb = self.hierarchy_store.get_fallback_path(pid_str)
            if len(chain) <= 1 and fb:
                leaf_name = chain[0] if chain else self.projects_by_id[pid_str].get("name", "Unnamed")
                full = fb + [leaf_name]
                res = {
                    "top_level_project": full[0],
                    "project_path": "/".join(full[1:]),
                    "project_levels": full[1:],
                }
                self.cache[pid_str] = res
                return res

        if not chain:
            res = {
                "top_level_project": "Unknown",
                "project_path": "",
                "project_levels": [],
            }
        else:
            proj_data = self.projects_by_id.get(pid_str)
            is_archived = proj_data.get("is_archived", False) if proj_data else False
            has_parent = bool(proj_data.get("parent_id")) if proj_data else False
            if not has_parent and self.hierarchy_store:
                has_parent = bool(self.hierarchy_store.get_parent_id(pid_str))

            # Only group under 'archives' if the project has no parent (is archived)
            # and is not listed in hierarchy.json
            in_hierarchy_store = bool(self.hierarchy_store and pid_str in self.hierarchy_store.projects)

            if is_archived and not has_parent and not in_hierarchy_store:
                leaf_name = chain[0]
                if leaf_name.lower() in ("archives", "archived"):
                    res = {
                        "top_level_project": "archives",
                        "project_path": "",
                        "project_levels": [],
                    }
                else:
                    res = {
                        "top_level_project": "archives",
                        "project_path": leaf_name,
                        "project_levels": [leaf_name],
                    }
            else:
                top_level = chain[0]
                levels = chain[1:]
                path = "/".join(levels)
                res = {
                    "top_level_project": top_level,
                    "project_path": path,
                    "project_levels": levels,
                }

        self.cache[pid_str] = res
        return res


class SectionResolver:
    """
    Resolves section ID to section name using local preloaded/cached sections
    and on-demand API fallback.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        preloaded_sections: Optional[Union[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]] = None,
        cache: Optional[Any] = None,
    ):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.cache = cache
        self.section_cache: Dict[str, Dict[str, Any]] = {}
        if cache and hasattr(cache, "sections") and cache.sections:
            self.section_cache.update(cache.sections)
        if preloaded_sections:
            if isinstance(preloaded_sections, list):
                for s in preloaded_sections:
                    if s.get("id"):
                        self.section_cache[str(s["id"])] = s
            elif isinstance(preloaded_sections, dict):
                self.section_cache.update(preloaded_sections)

    def lookup_section(self, section_id: str) -> Optional[Dict[str, Any]]:
        """Lookup section dictionary by id, caching results."""
        sid = str(section_id)
        if sid in self.section_cache:
            return self.section_cache[sid]

        if not self.token:
            return None

        url = f"https://api.todoist.com/api/v1/sections/{sid}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    sec_info = {
                        "id": sid,
                        "project_id": str(data.get("project_id", "")),
                        "name": data.get("name", f"[Section {sid}]"),
                    }
                    self.section_cache[sid] = sec_info
                    if self.cache and hasattr(self.cache, "sections"):
                        self.cache.sections[sid] = sec_info
                    return sec_info
            elif resp.status_code == 404:
                fallback = {"id": sid, "project_id": "", "name": f"[Section {sid}]"}
                self.section_cache[sid] = fallback
                if self.cache and hasattr(self.cache, "sections"):
                    self.cache.sections[sid] = fallback
                return fallback
        except requests.exceptions.RequestException:
            pass

        return None

    def resolve(self, section_id: Optional[Any]) -> str:
        """
        Resolve section_id to section name.
        Returns empty string if section_id is None or empty.
        """
        if not section_id:
            return ""
        sid = str(section_id)
        sec = self.lookup_section(sid)
        if sec:
            return sec.get("name", f"[Section {sid}]")
        return f"[Section {sid}]"


class LabelResolver:
    """
    Resolves label identifiers or names using account labels cache.
    Formats label lists as clean [@label1, @label2] tags or plain comma list.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        preloaded_labels: Optional[Union[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]] = None,
        cache: Optional[Any] = None,
    ):
        self.token = token
        self.cache = cache
        self.labels_by_id: Dict[str, Dict[str, Any]] = {}
        self.labels_by_name: Dict[str, Dict[str, Any]] = {}

        if cache and hasattr(cache, "labels") and cache.labels:
            for lid, linfo in cache.labels.items():
                self.labels_by_id[str(lid)] = linfo
                if "name" in linfo:
                    self.labels_by_name[linfo["name"]] = linfo

        if preloaded_labels:
            if isinstance(preloaded_labels, dict):
                for k, v in preloaded_labels.items():
                    if isinstance(v, dict):
                        lid = str(v.get("id") or k)
                        lname = str(v.get("name") or "")
                        if lid:
                            self.labels_by_id[lid] = v
                        if lname:
                            self.labels_by_name[lname] = v
            elif isinstance(preloaded_labels, list):
                for l in preloaded_labels:
                    if isinstance(l, dict):
                        lid = str(l.get("id", ""))
                        lname = str(l.get("name", ""))
                        if lid:
                            self.labels_by_id[lid] = l
                        if lname:
                            self.labels_by_name[lname] = l

    def resolve_label(self, label_ref: Any) -> str:
        """Resolve a label ID or label name into its canonical label name."""
        ref_str = str(label_ref)
        if ref_str in self.labels_by_name:
            return self.labels_by_name[ref_str].get("name", ref_str)
        if ref_str in self.labels_by_id:
            return self.labels_by_id[ref_str].get("name", ref_str)
        return ref_str

    def resolve_labels(self, label_refs: Optional[List[Any]]) -> List[str]:
        """Resolve a list of label IDs or names into a sorted list of unique label names."""
        if not label_refs:
            return []
        resolved = []
        for r in label_refs:
            name = self.resolve_label(r)
            if name and name not in resolved:
                resolved.append(name)
        return resolved

    def format_tags(self, label_refs: Optional[List[Any]]) -> str:
        """Format resolved labels into '[@tag1, @tag2]' string."""
        names = self.resolve_labels(label_refs)
        if not names:
            return ""
        tags = [f"@{n.lstrip('@')}" for n in names]
        return f"[{', '.join(tags)}]"


def format_priority(priority_val: Optional[Any]) -> str:
    """
    Format Todoist priority integer (1-4) into standard p1-p4 code.
    In Todoist API:
      4 -> p1 (Urgent / Red)
      3 -> p2 (High / Orange)
      2 -> p3 (Medium / Blue)
      1 -> p4 (Normal / Default)
    Returns 'p4' if None or unparseable.
    """
    if priority_val is None:
        return "p4"
    try:
        val = int(priority_val)
        if val == 4:
            return "p1"
        elif val == 3:
            return "p2"
        elif val == 2:
            return "p3"
        elif val == 1:
            return "p4"
    except (ValueError, TypeError):
        pass
    return "p4"


def calculate_due_variance(
    due_date_str: Optional[str],
    completion_date_str: Optional[str],
    was_overdue: bool = False,
) -> Dict[str, Any]:
    """
    Calculate variance between original due date and completion date.
    Returns:
        {
            "due_date": "YYYY-MM-DD" or "",
            "days_variance": int (positive if completed after due date, negative if early, 0 if on time),
            "status": "on_time" | "overdue" | "early" | "undated",
            "variance_desc": "+1d overdue" | "on time" | "-2d early" | ""
        }
    """
    if not due_date_str:
        return {
            "due_date": "",
            "days_variance": 0,
            "status": "undated",
            "variance_desc": "",
        }

    clean_due = str(due_date_str)[:10]
    if not completion_date_str:
        return {
            "due_date": clean_due,
            "days_variance": 0,
            "status": "undated",
            "variance_desc": "",
        }

    try:
        d_due = datetime.strptime(clean_due, "%Y-%m-%d").date()
        d_done = datetime.strptime(str(completion_date_str)[:10], "%Y-%m-%d").date()
        diff_days = (d_done - d_due).days

        if diff_days > 0 or was_overdue:
            days = max(1, diff_days)
            return {
                "due_date": clean_due,
                "days_variance": days,
                "status": "overdue",
                "variance_desc": f"+{days}d overdue",
            }
        elif diff_days < 0:
            days = abs(diff_days)
            return {
                "due_date": clean_due,
                "days_variance": -days,
                "status": "early",
                "variance_desc": f"-{days}d early",
            }
        else:
            return {
                "due_date": clean_due,
                "days_variance": 0,
                "status": "on_time",
                "variance_desc": "on time",
            }
    except Exception:
        return {
            "due_date": clean_due,
            "days_variance": 0,
            "status": "undated",
            "variance_desc": "",
        }


class TaskHierarchyResolver:
    """
    Resolves multi-level task parent-child hierarchies from completed activity events.
    Traces parent tasks upward to build full relative task paths.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        preloaded_tasks: Optional[Dict[str, Dict[str, Any]]] = None,
        cache: Optional[Any] = None,
        tz: Optional[Union[str, tzinfo]] = None,
    ):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.cache = cache
        self.tz = resolve_timezone(tz)
        # Prioritize cache tasks, fallback to preloaded
        self.task_cache: Dict[str, Dict[str, Any]] = {}
        if cache and cache.tasks:
            self.task_cache.update(cache.tasks)
        if preloaded_tasks:
            self.task_cache.update(preloaded_tasks)

    def lookup_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Lookup task content and parent_id, caching results."""
        tid = str(task_id)
        if tid in self.task_cache:
            return self.task_cache[tid]

        if not self.token:
            return None

        url = f"https://api.todoist.com/api/v1/tasks/{tid}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                task_info = {
                    "content": data.get("content", f"[Task {tid}]"),
                    "parent_id": str(data["parent_id"]) if data.get("parent_id") else None,
                    "description": data.get("description", ""),
                    "priority": data.get("priority", 1),
                    "labels": data.get("labels", []),
                    "due": data.get("due"),
                }
                self.task_cache[tid] = task_info
                if self.cache:
                    self.cache.tasks[tid] = task_info
                return task_info
            elif resp.status_code == 404:
                fallback = {
                    "content": f"[Task {tid}]",
                    "parent_id": None,
                    "description": "",
                    "priority": 1,
                    "labels": [],
                    "due": None,
                }
                self.task_cache[tid] = fallback
                if self.cache:
                    self.cache.tasks[tid] = fallback
                return fallback
        except requests.exceptions.RequestException:
            pass

        return None

    def resolve(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve an activity event into formatted task hierarchy data and metadata.
        Returns:
            {
                "task_path": str,          # e.g. "Root / Subtask / Leaf"
                "task_levels": List[str],  # e.g. ["Root", "Subtask", "Leaf"]
                "parent_task_id": str,
                "project_id": str,
                "section_id": str,
                "event_id": str,
                "date": str,               # YYYY-MM-DD
                "time": str,               # HH:MM:SS
                "description": str,
                "priority": str,           # p1, p2, p3, p4
                "raw_priority": int,
                "labels": List[str],
                "due_date": str,           # YYYY-MM-DD
                "due_variance": str,       # e.g. "+1d overdue", "on time"
                "due_status": str,         # on_time, overdue, early, undated
                "was_overdue": bool,
            }
        """
        extra = event.get("extra_data", {})
        current_title = extra.get("content") or f"[Task {event.get('object_id', 'unknown')}]"
        raw_parent_id = extra.get("parent_id") or event.get("parent_item_id")
        parent_task_id = str(raw_parent_id) if raw_parent_id else ""
        raw_section_id = extra.get("section_id") or event.get("section_id")
        section_id = str(raw_section_id) if raw_section_id else ""

        event_date_str = str(event.get("event_date", ""))
        date_part, time_part = format_event_datetime(event_date_str, tz=self.tz)

        # Extended metadata: description, priority, labels, due date
        obj_id = str(event.get("object_id", ""))
        cached_task = self.task_cache.get(obj_id, {})

        description = extra.get("description")
        if description is None:
            description = cached_task.get("description", "")

        raw_priority = extra.get("priority")
        if raw_priority is None:
            raw_priority = cached_task.get("priority")
        priority_code = format_priority(raw_priority)

        raw_labels = extra.get("labels")
        if not raw_labels:
            raw_labels = cached_task.get("labels", [])

        due_date_str = extra.get("due_date") or extra.get("completed_due_date")
        if not due_date_str and isinstance(cached_task.get("due"), dict):
            due_date_str = cached_task["due"].get("date")

        was_overdue = bool(extra.get("was_overdue", False))
        due_info = calculate_due_variance(due_date_str, date_part, was_overdue=was_overdue)

        if not parent_task_id:
            return {
                "task_id": obj_id,
                "task_path": current_title,
                "task_levels": [current_title],
                "parent_task_id": "",
                "project_id": str(event.get("parent_project_id", "")),
                "section_id": section_id,
                "event_id": str(event.get("id", "")),
                "event_date": event_date_str,
                "date": date_part,
                "time": time_part,
                "description": description or "",
                "priority": priority_code,
                "raw_priority": raw_priority,
                "labels": list(raw_labels or []),
                "due_date": due_info["due_date"],
                "due_variance": due_info["variance_desc"],
                "due_status": due_info["status"],
                "was_overdue": was_overdue,
            }

        ancestors: List[str] = []
        curr_parent: Optional[str] = parent_task_id
        visited = {str(event.get("object_id", ""))}

        while curr_parent and curr_parent not in visited:
            visited.add(curr_parent)
            parent_info = self.lookup_task(curr_parent)
            if parent_info:
                ancestors.append(parent_info.get("content", f"[Task {curr_parent}]"))
                curr_parent = parent_info.get("parent_id")
            else:
                ancestors.append(f"[Task {curr_parent}]")
                break

        ancestors.reverse()
        full_levels = ancestors + [current_title]
        task_path = " / ".join(full_levels)

        return {
            "task_id": obj_id,
            "task_path": task_path,
            "task_levels": full_levels,
            "parent_task_id": parent_task_id,
            "project_id": str(event.get("parent_project_id", "")),
            "section_id": section_id,
            "event_id": str(event.get("id", "")),
            "event_date": event_date_str,
            "date": date_part,
            "time": time_part,
            "description": description or "",
            "priority": priority_code,
            "raw_priority": raw_priority,
            "labels": list(raw_labels or []),
            "due_date": due_info["due_date"],
            "due_variance": due_info["variance_desc"],
            "due_status": due_info["status"],
            "was_overdue": was_overdue,
        }


def build_trace_records(
    events: List[Dict[str, Any]],
    project_resolver: ProjectTreeResolver,
    task_resolver: TaskHierarchyResolver,
    section_resolver: Optional[SectionResolver] = None,
    label_resolver: Optional[LabelResolver] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> List[Dict[str, Any]]:
    """Combine activity events with project, task, section, and label resolvers into unified trace records."""
    records: List[Dict[str, Any]] = []
    total = len(events)
    for idx, ev in enumerate(events, 1):
        t_res = task_resolver.resolve(ev)
        p_res = project_resolver.resolve(t_res["project_id"])
        sec_name = section_resolver.resolve(t_res.get("section_id")) if section_resolver else ""
        raw_labels = t_res.get("labels", [])
        resolved_labels = label_resolver.resolve_labels(raw_labels) if label_resolver else raw_labels

        records.append({
            "event_id": t_res["event_id"],
            "event_date": t_res.get("event_date", str(ev.get("event_date", ""))),
            "task_id": t_res.get("task_id", str(ev.get("object_id", ""))),
            "top_level_project": p_res["top_level_project"],
            "project_path": p_res["project_path"],
            "project_levels": p_res["project_levels"],
            "section": sec_name,
            "section_id": t_res.get("section_id", ""),
            "date": t_res["date"],
            "time": t_res["time"],
            "task_path": t_res["task_path"],
            "task_levels": t_res["task_levels"],
            "parent_task_id": t_res["parent_task_id"],
            "project_id": t_res["project_id"],
            "description": t_res.get("description", ""),
            "priority": t_res.get("priority", "p4"),
            "raw_priority": t_res.get("raw_priority"),
            "labels": resolved_labels,
            "due_date": t_res.get("due_date", ""),
            "due_variance": t_res.get("due_variance", ""),
            "due_status": t_res.get("due_status", "undated"),
            "was_overdue": t_res.get("was_overdue", False),
        })
        if progress_cb and (idx % 20 == 0 or idx == total):
            progress_cb(idx, total)
    return records
