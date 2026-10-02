"""
Unit tests for CSV and Markdown exporters, including bullet hierarchies.
"""

from todoist_trace.exporters import (
    export_csv,
    export_markdown,
    format_task_bullets,
    generate_csv,
    generate_markdown,
)


class TestExporters:
    """Test suite for CSV and Markdown exporters."""

    def test_generate_csv(self, sample_exporter_records):
        csv_out = generate_csv(sample_exporter_records)
        lines = csv_out.strip().split("\n")

        # Verify header
        expected_header = "top_level_project,project_path,date,time,task_path,parent_task_id,project_id,event_id"
        assert lines[0] == expected_header
        assert len(lines) == 4

        # Verify RFC 4180 escaping on quotes & commas
        assert '"Buy ""groceries"", apples & milk"' in lines[3]
        assert "work-areas,admin/email,2026-09-15,14:25:00,Reply to vendor requests,,proj_123,ev_002" in lines[1] or lines[2]

    def test_export_csv_file_creation(self, sample_exporter_records, tmp_path):
        out_file = tmp_path / "subdir" / "export.csv"
        export_csv(sample_exporter_records, str(out_file))

        assert out_file.is_file()
        content = out_file.read_text(encoding="utf-8")
        assert "top_level_project,project_path,date" in content
        assert "ev_001" in content

    def test_generate_markdown_nested_style(self, sample_exporter_records):
        md_out = generate_markdown(sample_exporter_records, style="nested")

        # Check date heading
        assert "## 2026-09-15" in md_out

        # Check progressive headings
        assert "### work-areas" in md_out
        assert "#### admin" in md_out
        assert "##### email" in md_out

        # Check task bullets
        assert "- Check inbox filters / triage / urgent" in md_out
        assert "- Reply to vendor requests" in md_out

        # Check direct task under root project
        assert "### personal" in md_out
        assert '- Buy "groceries", apples & milk' in md_out

    def test_generate_markdown_flat_style(self, sample_exporter_records):
        md_out = generate_markdown(sample_exporter_records, style="flat")

        # Check date heading
        assert "## 2026-09-15" in md_out

        # Check flat project path heading
        assert "### work-areas" in md_out
        assert "#### admin/email" in md_out
        assert "#### admin\n" not in md_out

        # Check task bullets
        assert "- Check inbox filters / triage / urgent" in md_out
        assert "- Reply to vendor requests" in md_out

        # Check root project without sub-heading
        assert "### personal" in md_out
        assert '- Buy "groceries", apples & milk' in md_out

    def test_export_markdown_file_creation(self, sample_exporter_records, tmp_path):
        out_file = tmp_path / "nested" / "export.md"
        export_markdown(sample_exporter_records, str(out_file), style="nested")

        assert out_file.is_file()
        content = out_file.read_text(encoding="utf-8")
        assert "## 2026-09-15" in content
        assert "### work-areas" in content

    def test_empty_records(self, tmp_path):
        assert generate_markdown([]) == ""
        csv_empty = generate_csv([])
        assert csv_empty.strip() == "top_level_project,project_path,date,time,task_path,parent_task_id,project_id,event_id"

    def test_generate_markdown_task_bullet_hierarchy(self):
        records = [
            {
                "top_level_project": "work",
                "project_path": "backend-api",
                "project_levels": ["backend-api"],
                "date": "2026-09-30",
                "time": "10:00:00",
                "task_path": "Sprint Deliverables / Services / Auth",
                "task_levels": ["Sprint Deliverables", "Services", "Auth"],
                "parent_task_id": "p2",
                "project_id": "p1",
                "event_id": "e1",
            },
            {
                "top_level_project": "work",
                "project_path": "backend-api",
                "project_levels": ["backend-api"],
                "date": "2026-09-30",
                "time": "10:05:00",
                "task_path": "Sprint Deliverables / Services / Database",
                "task_levels": ["Sprint Deliverables", "Services", "Database"],
                "parent_task_id": "p2",
                "project_id": "p1",
                "event_id": "e2",
            },
            {
                "top_level_project": "work",
                "project_path": "backend-api",
                "project_levels": ["backend-api"],
                "date": "2026-09-30",
                "time": "10:10:00",
                "task_path": "Sprint Deliverables / Client Portal",
                "task_levels": ["Sprint Deliverables", "Client Portal"],
                "parent_task_id": "p1",
                "project_id": "p1",
                "event_id": "e3",
            },
        ]
        # Nested task style
        md_nested = generate_markdown(records, style="nested", task_style="nested")
        assert "- Sprint Deliverables\n  - Client Portal\n  - Services\n    - Database\n    - Auth" in md_nested

        # Flat task style
        md_flat = generate_markdown(records, style="nested", task_style="flat")
        assert "- Sprint Deliverables / Services / Auth" in md_flat
        assert "- Sprint Deliverables / Services / Database" in md_flat
        assert "- Sprint Deliverables / Client Portal" in md_flat
