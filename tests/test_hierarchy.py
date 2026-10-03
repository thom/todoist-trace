"""
Unit tests for the Persistent Project Hierarchy Store and CLI integration.
Uses strictly synthetic test fixtures in compliance with AGENTS.md.
"""

from pathlib import Path
import json
import sqlite3
import pytest

from todoist_trace.hierarchy import HierarchyStore
from todoist_trace.resolvers import ProjectTreeResolver
from todoist_trace.cache import SQLiteTraceCache
from todoist_trace.progress import FancyProgressReporter
from todoist_trace.main import run_hierarchy, main


@pytest.fixture
def synthetic_hierarchy_store(tmp_path):
    store_file = tmp_path / "project_hierarchy.json"
    return HierarchyStore(file_path=store_file)


class TestHierarchyStoreCore:
    def test_record_and_resolve_active_hierarchy(self, synthetic_hierarchy_store):
        store = synthetic_hierarchy_store
        projects = [
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1", "is_archived": False},
            {"id": "syn_p3", "name": "auth-api", "parent_id": "syn_p2", "is_archived": False},
        ]
        store.record_batch(projects)

        assert store.get_parent_id("syn_p3") == "syn_p2"
        assert store.get_parent_id("syn_p2") == "syn_p1"
        assert store.get_parent_id("syn_p1") is None

        # Verify fallback path computation
        assert store.get_fallback_path("syn_p3") == ["core-platform", "services"]
        assert store.get_fallback_path("syn_p2") == ["core-platform"]
        assert store.get_fallback_path("syn_p1") == []

        top, path, levels = store.resolve_project_chain("syn_p3")
        assert top == "core-platform"
        assert path == "services/auth-api"
        assert levels == ["services", "auth-api"]

    def test_shield_rule_archived_project_null_parent(self, synthetic_hierarchy_store):
        store = synthetic_hierarchy_store
        # Initial active ingestion
        store.record_batch([
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1", "is_archived": False},
            {"id": "syn_p3", "name": "auth-api", "parent_id": "syn_p2", "is_archived": False},
        ])

        # API subsequently reports syn_p3 as archived with parent_id: null
        store.record_batch([
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1", "is_archived": False},
            {"id": "syn_p3", "name": "auth-api", "parent_id": None, "is_archived": True},
        ])

        # Shield Rule: parent_id must NOT be wiped
        assert store.get_parent_id("syn_p3") == "syn_p2"
        assert store.get_project("syn_p3")["is_archived"] is True

        top, path, levels = store.resolve_project_chain("syn_p3")
        assert top == "core-platform"
        assert levels == ["services", "auth-api"]

    def test_legitimate_move_active_project_to_root(self, synthetic_hierarchy_store):
        store = synthetic_hierarchy_store
        store.record_batch([
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1", "is_archived": False},
        ])
        assert store.get_parent_id("syn_p2") == "syn_p1"

        # User deliberately moves active project to root in Todoist
        store.record_project("syn_p2", "services", parent_id=None, is_archived=False)
        assert store.get_parent_id("syn_p2") is None

    def test_active_project_move_to_new_parent(self, synthetic_hierarchy_store):
        store = synthetic_hierarchy_store
        store.record_batch([
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1", "is_archived": False},
            {"id": "syn_p4", "name": "infra-ops", "parent_id": None, "is_archived": False},
        ])

        # Move syn_p2 under syn_p4
        store.record_project("syn_p2", "services", parent_id="syn_p4", is_archived=False)
        assert store.get_parent_id("syn_p2") == "syn_p4"

    def test_project_rename_propagation(self, synthetic_hierarchy_store):
        store = synthetic_hierarchy_store
        store.record_batch([
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1", "is_archived": False},
            {"id": "syn_p3", "name": "auth-api", "parent_id": "syn_p2", "is_archived": False},
        ])

        # Rename root project
        store.record_project("syn_p1", "enterprise-platform", parent_id=None, is_archived=False)

        top, path, levels = store.resolve_project_chain("syn_p3")
        assert top == "enterprise-platform"
        assert levels == ["services", "auth-api"]

    def test_deleted_ancestors_fallback_path(self, synthetic_hierarchy_store):
        store = synthetic_hierarchy_store
        store.record_batch([
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "legacy-services", "parent_id": "syn_p1", "is_archived": False},
            {"id": "syn_p3", "name": "billing-svc", "parent_id": "syn_p2", "is_archived": True},
        ])

        # Ancestors are completely deleted from active/cached live map
        live_projects_without_ancestors = {
            "syn_p3": {"id": "syn_p3", "name": "billing-svc", "parent_id": None, "is_archived": True}
        }

        # Simulate store where ancestors were pruned or missing from live map
        empty_live = {}
        top, path, levels = store.resolve_project_chain("syn_p3", live_projects_by_id=empty_live)
        assert top == "core-platform"
        assert levels == ["legacy-services", "billing-svc"]

    def test_circular_reference_prevention(self, synthetic_hierarchy_store):
        store = synthetic_hierarchy_store
        store.record_batch([
            {"id": "syn_p1", "name": "node-a", "parent_id": None},
            {"id": "syn_p2", "name": "node-b", "parent_id": "syn_p1"},
            {"id": "syn_p3", "name": "node-c", "parent_id": "syn_p2"},
        ])

        # Self parent: should fail
        assert store.set_parent("syn_p1", "syn_p1") is False

        # Attempt to make ancestor child of its own descendant (A -> C)
        assert store.set_parent("syn_p1", "syn_p3") is False

        # Verify integrity unchanged
        assert store.get_parent_id("syn_p1") is None
        assert store.get_parent_id("syn_p2") == "syn_p1"
        assert store.get_parent_id("syn_p3") == "syn_p2"

    def test_resolve_path_to_id_disambiguation(self, synthetic_hierarchy_store):
        store = synthetic_hierarchy_store
        # Two projects named 'database' under different parents
        store.record_batch([
            {"id": "syn_p10", "name": "platform-engineering", "parent_id": None},
            {"id": "syn_p11", "name": "database", "parent_id": "syn_p10"},
            {"id": "syn_p20", "name": "site-reliability", "parent_id": None},
            {"id": "syn_p21", "name": "database", "parent_id": "syn_p20"},
        ])

        # Bare name 'database' is ambiguous
        assert store.resolve_path_to_id("database") is None

        # Full paths disambiguate cleanly
        assert store.resolve_path_to_id("platform-engineering / database") == "syn_p11"
        assert store.resolve_path_to_id("site-reliability / database") == "syn_p21"
        assert store.resolve_path_to_id("site-reliability › database") == "syn_p21"

        # Unique root name resolves
        assert store.resolve_path_to_id("platform-engineering") == "syn_p10"

    def test_atomic_file_persistence(self, tmp_path):
        store_file = tmp_path / "project_hierarchy.json"
        store1 = HierarchyStore(file_path=store_file)
        store1.record_batch([
            {"id": "syn_p1", "name": "core-platform", "parent_id": None},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1"},
        ])

        assert store_file.is_file()

        # Load from fresh instance
        store2 = HierarchyStore(file_path=store_file)
        assert len(store2.projects) == 2
        assert store2.get_parent_id("syn_p2") == "syn_p1"
        assert store2.get_fallback_path("syn_p2") == ["core-platform"]


class TestCacheAndResolverIntegration:
    def test_project_tree_resolver_with_hierarchy_store(self, tmp_path):
        store = HierarchyStore(file_path=tmp_path / "hierarchy.json")
        store.record_batch([
            {"id": "syn_p1", "name": "core-platform", "parent_id": None},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1"},
        ])

        # API only returns archived project with parent_id: None
        api_projects = [
            {"id": "syn_p2", "name": "services", "parent_id": None, "is_archived": True}
        ]

        resolver = ProjectTreeResolver(api_projects, hierarchy_store=store)
        res = resolver.resolve("syn_p2")
        assert res["top_level_project"] == "core-platform"
        assert res["project_path"] == "services"
        assert res["project_levels"] == ["services"]

    def test_cache_wipe_resilience(self, tmp_path):
        db_file = tmp_path / "cache.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        # Ingest projects
        cache.projects = [
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1", "is_archived": False},
            {"id": "syn_p3", "name": "auth-api", "parent_id": "syn_p2", "is_archived": True},
        ]
        cache.save()

        # Wipe SQLite database completely
        db_file.unlink()
        assert not db_file.exists()

        # Reopen cache: HierarchyStore persists independently
        new_cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)
        assert new_cache.hierarchy_store is not None
        assert new_cache.hierarchy_store.get_parent_id("syn_p3") == "syn_p2"

        # Projects property loads from hierarchy store even when DB was empty
        assert len(new_cache.projects) >= 3

    def test_unassigned_archived_project_resolves_to_archived(self, tmp_path):
        store = HierarchyStore(file_path=tmp_path / "hierarchy_arch.json")
        projects = [
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p99", "name": "legacy-experiment", "parent_id": None, "is_archived": True},
        ]
        store.record_batch(projects)

        resolver = ProjectTreeResolver(projects, hierarchy_store=store)

        # Active project resolves normally to itself
        res_active = resolver.resolve("syn_p1")
        assert res_active["top_level_project"] == "core-platform"
        assert res_active["project_path"] == ""

        # Unassigned archived project resolves under "archived"
        res_arch = resolver.resolve("syn_p99")
        assert res_arch["top_level_project"] == "archived"
        assert res_arch["project_path"] == "legacy-experiment"
        assert res_arch["project_levels"] == ["legacy-experiment"]

        # In store resolve_project_chain (with live map) as well
        live_map = {p["id"]: p for p in projects}
        top, path, levels = store.resolve_project_chain("syn_p99", live_projects_by_id=live_map)
        assert top == "archived"
        assert path == "legacy-experiment"
        assert levels == ["legacy-experiment"]

        # If user explicitly records the archived project as root in project_hierarchy.json:
        store.set_parent("syn_p99", None, name="legacy-experiment")
        resolver_explicit = ProjectTreeResolver(projects, hierarchy_store=store)
        res_explicit = resolver_explicit.resolve("syn_p99")
        # Since it IS listed in project_hierarchy.json, it is not grouped under archived
        assert res_explicit["top_level_project"] == "legacy-experiment"
        assert res_explicit["project_path"] == ""

        # Once re-linked/assigned to a parent, it moves under that parent
        store.set_parent("syn_p99", "syn_p1")
        resolver_relinked = ProjectTreeResolver(projects, hierarchy_store=store)
        res_relinked = resolver_relinked.resolve("syn_p99")
        assert res_relinked["top_level_project"] == "core-platform"
        assert res_relinked["project_path"] == "legacy-experiment"

    def test_category_archived_filtering(self, tmp_path):
        from todoist_trace.filters import filter_records

        records = [
            {"top_level_project": "work", "task_path": "Task 1", "date": "2026-09-10"},
            {"top_level_project": "personal", "task_path": "Task 2", "date": "2026-09-10"},
            {"top_level_project": "archived", "task_path": "Task 3", "date": "2026-09-10"},
        ]

        # Filter work
        res_work = filter_records(records, category="work")
        assert len(res_work) == 1
        assert res_work[0]["task_path"] == "Task 1"

        # Filter archived
        res_arch = filter_records(records, category="archived")
        assert len(res_arch) == 1
        assert res_arch[0]["task_path"] == "Task 3"


class TestHierarchyCLICommands:
    def test_hierarchy_list_all_and_unassigned(self, tmp_path, capsys):
        db_file = tmp_path / "test_cli.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)
        cache.projects = [
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1", "is_archived": False},
            {"id": "syn_p3", "name": "auth-api", "parent_id": "syn_p2", "is_archived": True},
            {"id": "syn_p4", "name": "orphan-project", "parent_id": None, "is_archived": True},
        ]
        reporter = FancyProgressReporter(quiet=False)

        # 1. List unassigned
        settings_unassigned = {
            "hierarchy_action": "list",
            "hierarchy_unassigned": True,
            "hierarchy_all": False,
        }
        rc = run_hierarchy(settings_unassigned, reporter, cache)
        assert rc == 0
        captured = capsys.readouterr()
        assert "orphan-project" in captured.out
        assert "Unassigned" in captured.out

        # 2. List all
        settings_all = {
            "hierarchy_action": "list",
            "hierarchy_unassigned": False,
            "hierarchy_all": True,
        }
        rc = run_hierarchy(settings_all, reporter, cache)
        assert rc == 0
        captured = capsys.readouterr()
        assert "core-platform" in captured.out
        assert "services" in captured.out
        assert "auth-api" in captured.out

    def test_hierarchy_set_parent(self, tmp_path, capsys):
        db_file = tmp_path / "test_set.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)
        cache.projects = [
            {"id": "syn_p1", "name": "core-platform", "parent_id": None, "is_archived": False},
            {"id": "syn_p2", "name": "services", "parent_id": "syn_p1", "is_archived": False},
            {"id": "syn_p4", "name": "orphan-project", "parent_id": None, "is_archived": True},
        ]
        reporter = FancyProgressReporter(quiet=False)

        settings = {
            "hierarchy_action": "set",
            "hierarchy_project": "orphan-project",
            "hierarchy_parent": "core-platform / services",
        }
        rc = run_hierarchy(settings, reporter, cache)
        assert rc == 0
        captured = capsys.readouterr()
        assert "Successfully assigned" in captured.out

        # Verify parent is set in hierarchy store and cache
        assert cache.hierarchy_store.get_parent_id("syn_p4") == "syn_p2"
        cur = cache.conn.cursor()
        row = cur.execute("SELECT parent_id FROM projects WHERE id = 'syn_p4'").fetchone()
        assert row[0] == "syn_p2"
