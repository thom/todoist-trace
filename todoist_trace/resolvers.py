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

    def __init__(self, projects: List[Dict[str, Any]]):
        self.projects_by_id: Dict[str, Dict[str, Any]] = {
            str(p["id"]): p for p in projects if "id" in p
        }
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
            curr = str(parent) if parent else None

        chain.reverse()

        if not chain:
            res = {
                "top_level_project": "Unknown",
                "project_path": "",
                "project_levels": [],
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


class TaskHierarchyResolver:
    """
    Resolves multi-level task parent-child hierarchies from completed activity events.
    Traces parent tasks upward to build full relative task paths.
    """

    def __init__(
        self,
        token: str,
        preloaded_tasks: Optional[Dict[str, Dict[str, Any]]] = None,
        cache: Optional[Any] = None,
        tz: Optional[Union[str, tzinfo]] = None,
    ):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
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

        url = f"https://api.todoist.com/api/v1/tasks/{tid}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                task_info = {
                    "content": data.get("content", f"[Task {tid}]"),
                    "parent_id": str(data["parent_id"]) if data.get("parent_id") else None,
                    "labels": data.get("labels", []),
                }
                self.task_cache[tid] = task_info
                if self.cache:
                    self.cache.tasks[tid] = task_info
                return task_info
            elif resp.status_code == 404:
                fallback = {"content": f"[Task {tid}]", "parent_id": None, "labels": []}
                self.task_cache[tid] = fallback
                if self.cache:
                    self.cache.tasks[tid] = fallback
                return fallback
        except requests.exceptions.RequestException:
            pass

        return None

    def resolve(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve an activity event into formatted task hierarchy data.
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
                "labels": List[str],
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

        obj_id = str(event.get("object_id", ""))
        cached_task = self.task_cache.get(obj_id, {})
        raw_labels = extra.get("labels")
        if not raw_labels:
            raw_labels = cached_task.get("labels", [])

        if not parent_task_id:
            return {
                "task_path": current_title,
                "task_levels": [current_title],
                "parent_task_id": "",
                "project_id": str(event.get("parent_project_id", "")),
                "section_id": section_id,
                "event_id": str(event.get("id", "")),
                "date": date_part,
                "time": time_part,
                "labels": list(raw_labels or []),
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
            "task_path": task_path,
            "task_levels": full_levels,
            "parent_task_id": parent_task_id,
            "project_id": str(event.get("parent_project_id", "")),
            "section_id": section_id,
            "event_id": str(event.get("id", "")),
            "date": date_part,
            "time": time_part,
            "labels": list(raw_labels or []),
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
            "event_id": t_res["event_id"],
            "labels": resolved_labels,
        })
        if progress_cb and (idx % 20 == 0 or idx == total):
            progress_cb(idx, total)
    return records
