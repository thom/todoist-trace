"""
Persistent Project Hierarchy Store for todoist-trace.
Maintains historical project parent-child relationships across Todoist archiving,
deletions, renames, and local cache wipes.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .config import DEFAULT_HIERARCHY_PATH


class HierarchyStore:
    """
    Manages persistent project hierarchy records stored in a standalone JSON file.
    Immune to cache wipes and Todoist API null-parent archiving behavior.
    """

    def __init__(self, file_path: Optional[Union[str, Path]] = None):
        self.file_path = Path(file_path).expanduser() if file_path else DEFAULT_HIERARCHY_PATH
        self.projects: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Load stored project hierarchies from disk if file exists."""
        self.projects = {}
        if not self.file_path.is_file():
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_projects = data.get("projects", {}) if isinstance(data, dict) else {}
            for pid, pdata in raw_projects.items():
                if isinstance(pdata, dict):
                    pid_str = str(pid)
                    self.projects[pid_str] = {
                        "id": pid_str,
                        "name": str(pdata.get("name") or "Unnamed"),
                        "parent_id": str(pdata["parent_id"]) if pdata.get("parent_id") else None,
                        "is_archived": bool(pdata.get("is_archived", False)),
                        "is_deleted": bool(pdata.get("is_deleted", False)),
                        "fallback_path": list(pdata.get("fallback_path") or []),
                        "updated_at": pdata.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                    }
        except Exception:
            # If load fails due to read error, initialize empty to remain safe
            self.projects = {}

    def save(self) -> None:
        """Atomically save the hierarchy store to disk using a temporary file."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.file_path.with_suffix(".tmp")
            payload = {
                "version": 1,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "projects": self.projects,
            }
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.file_path)
        except Exception:
            # Non-blocking if running in read-only environment
            pass

    def get_project(self, project_id: Any) -> Optional[Dict[str, Any]]:
        """Return project dictionary by ID if known."""
        if not project_id:
            return None
        return self.projects.get(str(project_id))

    def get_parent_id(self, project_id: Any) -> Optional[str]:
        """Return preserved parent ID for a project, or None."""
        proj = self.get_project(project_id)
        return proj.get("parent_id") if proj else None

    def get_fallback_path(self, project_id: Any) -> List[str]:
        """Return fallback breadcrumb path list if known."""
        proj = self.get_project(project_id)
        return list(proj.get("fallback_path") or []) if proj else []

    def record_project(
        self,
        project_id: Any,
        name: str,
        parent_id: Optional[Any] = None,
        is_archived: bool = False,
        is_deleted: bool = False,
    ) -> None:
        """
        Record or update a project according to hierarchy retention rules:
        - If an archived project returns parent_id = None, do NOT overwrite an existing parent!
        - If an active project returns parent_id = None, legitimately update to root.
        - If an active project returns parent_id = <id>, update to the new parent.
        """
        if not project_id:
            return

        pid_str = str(project_id)
        parent_str = str(parent_id) if parent_id else None
        now_iso = datetime.now(timezone.utc).isoformat()

        if pid_str in self.projects:
            existing = self.projects[pid_str]
            # Shield Rule: If project is archived and API reports parent_id is None,
            # retain the existing known parent_id and fallback_path!
            if is_archived and not parent_str:
                existing_parent = existing.get("parent_id")
                existing["is_archived"] = True
                if name:
                    existing["name"] = name
                if is_deleted:
                    existing["is_deleted"] = True
                if existing_parent:
                    existing["parent_id"] = existing_parent
                existing["updated_at"] = now_iso
            else:
                # Active project, or legitimate move
                existing["name"] = name or existing.get("name", "Unnamed")
                existing["parent_id"] = parent_str
                existing["is_archived"] = is_archived
                existing["is_deleted"] = is_deleted
                existing["updated_at"] = now_iso
        else:
            # If project is not in store yet, record it if active or if it has a parent.
            # Do NOT automatically add unassigned archived projects to hierarchy.json.
            if is_archived and not parent_str:
                return

            self.projects[pid_str] = {
                "id": pid_str,
                "name": name or "Unnamed",
                "parent_id": parent_str,
                "is_archived": is_archived,
                "is_deleted": is_deleted,
                "fallback_path": [],
                "updated_at": now_iso,
            }

    def recompute_fallback_paths(self) -> None:
        """
        Recompute fallback ancestor paths for all projects in store.
        Cycle-safe using visited sets.
        """
        for pid_str, pdata in self.projects.items():
            chain: List[str] = []
            curr: Optional[str] = pdata.get("parent_id")
            visited: Set[str] = {pid_str}

            while curr and curr in self.projects and curr not in visited:
                visited.add(curr)
                parent_proj = self.projects[curr]
                chain.append(parent_proj.get("name", "Unnamed"))
                curr = parent_proj.get("parent_id")

            chain.reverse()
            pdata["fallback_path"] = chain

    def record_batch(self, projects: List[Dict[str, Any]], auto_save: bool = True) -> None:
        """
        Ingest a batch of projects. Ingests active projects first so parent nodes
        are established, then processes archived projects with parent preservation.
        """
        # Separate active and archived projects
        active_projs = [p for p in projects if not p.get("is_archived")]
        archived_projs = [p for p in projects if p.get("is_archived")]

        for p in active_projs:
            self.record_project(
                project_id=p.get("id"),
                name=p.get("name", ""),
                parent_id=p.get("parent_id"),
                is_archived=False,
                is_deleted=bool(p.get("is_deleted", False)),
            )

        for p in archived_projs:
            self.record_project(
                project_id=p.get("id"),
                name=p.get("name", ""),
                parent_id=p.get("parent_id"),
                is_archived=True,
                is_deleted=bool(p.get("is_deleted", False)),
            )

        self.recompute_fallback_paths()
        if auto_save:
            self.save()

    def set_parent(
        self,
        project_id: Any,
        parent_id: Optional[Any],
        name: Optional[str] = None,
        is_archived: bool = True,
    ) -> bool:
        """
        Explicitly assign a parent project ID to a target project.
        Returns True if successful, False if creates a circular reference.
        """
        pid_str = str(project_id)
        parent_str = str(parent_id) if parent_id else None

        # Check circular reference
        if parent_str:
            curr = parent_str
            visited = {pid_str}
            while curr and curr in self.projects:
                if curr in visited:
                    # Loop detected!
                    return False
                visited.add(curr)
                curr = self.projects[curr].get("parent_id")

        now_iso = datetime.now(timezone.utc).isoformat()
        if pid_str in self.projects:
            self.projects[pid_str]["parent_id"] = parent_str
            if name:
                self.projects[pid_str]["name"] = name
            self.projects[pid_str]["updated_at"] = now_iso
        else:
            self.projects[pid_str] = {
                "id": pid_str,
                "name": name or "Unnamed",
                "parent_id": parent_str,
                "is_archived": is_archived,
                "is_deleted": False,
                "fallback_path": [],
                "updated_at": now_iso,
            }

        self.recompute_fallback_paths()
        self.save()
        return True

    def find_projects_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Return all project records matching a given name (case-insensitive)."""
        name_clean = name.strip().lower()
        return [p for p in self.projects.values() if p.get("name", "").strip().lower() == name_clean]

    def resolve_path_to_id(self, path_str: str) -> Optional[str]:
        """
        Resolve a human-readable path string like 'operations / backend' or 'archive'
        to a specific target project ID.
        Returns None if not found or ambiguous.
        """
        clean_path = path_str.strip()
        if not clean_path:
            return None

        segments = [s.strip().lower() for s in clean_path.replace("›", "/").split("/") if s.strip()]
        if not segments:
            return None

        # Find candidates matching leaf segment name
        leaf_name = segments[-1]
        candidates = [p for p in self.projects.values() if p.get("name", "").strip().lower() == leaf_name]
        if not candidates:
            return None

        if len(segments) == 1:
            # If 1 segment, prefer root project (parent_id is None) if exists
            root_matches = [c for c in candidates if not c.get("parent_id")]
            if len(root_matches) == 1:
                return root_matches[0]["id"]
            if len(candidates) == 1:
                return candidates[0]["id"]
            return None

        # Multi-segment matching: verify ancestors match segments[:-1]
        expected_ancestors = segments[:-1]
        matching_ids: List[str] = []

        for cand in candidates:
            # Build ancestor name list
            cand_ancestors: List[str] = []
            curr = cand.get("parent_id")
            visited = {cand["id"]}
            while curr and curr in self.projects and curr not in visited:
                visited.add(curr)
                cand_ancestors.append(self.projects[curr].get("name", "").strip().lower())
                curr = self.projects[curr].get("parent_id")
            cand_ancestors.reverse()

            if cand_ancestors == expected_ancestors:
                matching_ids.append(cand["id"])

        if len(matching_ids) == 1:
            return matching_ids[0]

        return None

    def resolve_project_chain(
        self,
        project_id: Any,
        live_projects_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Tuple[str, str, List[str]]:
        """
        Recursively resolve project hierarchy.
        Uses live project names if available in live_projects_by_id, falls back to
        stored hierarchy nodes, and finally falls back to fallback_path.
        Returns (top_level_project, project_path, project_levels).
        """
        if not project_id:
            return ("Unknown", "", [])

        pid_str = str(project_id)
        chain: List[str] = []
        curr: Optional[str] = pid_str
        visited: Set[str] = set()

        live_map = live_projects_by_id or {}

        while curr and curr not in visited:
            visited.add(curr)
            # 1. Check live map
            if curr in live_map:
                proj = live_map[curr]
                chain.append(proj.get("name") or "Unnamed")
                parent = proj.get("parent_id")
                # If live says parent is None, verify if HierarchyStore preserved a parent!
                if not parent and curr in self.projects:
                    parent = self.projects[curr].get("parent_id")
                curr = str(parent) if parent else None
            # 2. Check HierarchyStore
            elif curr in self.projects:
                proj = self.projects[curr]
                chain.append(proj.get("name") or "Unnamed")
                parent = proj.get("parent_id")
                curr = str(parent) if parent else None
            else:
                break

        chain.reverse()

        # If chain could not reach root (e.g. parent deleted and not in store), check fallback_path
        if pid_str in self.projects and self.projects[pid_str].get("fallback_path"):
            fb = self.projects[pid_str]["fallback_path"]
            # If chain has fewer items than fallback + leaf, use fallback
            if len(chain) <= 1 and fb:
                leaf_name = chain[0] if chain else self.projects[pid_str].get("name", "Unnamed")
                full_levels = fb + [leaf_name]
                top_level = full_levels[0]
                levels = full_levels[1:]
                return (top_level, "/".join(levels), levels)

        if not chain:
            return ("Unknown", "", [])

        # Only group under 'archives' if project has no parent (is archived) and is NOT listed in hierarchy.json
        proj_meta = self.projects.get(pid_str)
        in_hierarchy_store = pid_str in self.projects
        is_archived = False
        has_parent = False

        if proj_meta:
            is_archived = proj_meta.get("is_archived", False)
            has_parent = bool(proj_meta.get("parent_id"))
        elif live_map and pid_str in live_map:
            is_archived = live_map[pid_str].get("is_archived", False)
            has_parent = bool(live_map[pid_str].get("parent_id"))

        if is_archived and not has_parent and not in_hierarchy_store:
            leaf_name = chain[0]
            if leaf_name.lower() in ("archives", "archived"):
                return ("archives", "", [])
            return ("archives", leaf_name, [leaf_name])

        top_level = chain[0]
        levels = chain[1:]
        path = "/".join(levels)
        return (top_level, path, levels)
