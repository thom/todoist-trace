"""
Interactive HTML dashboard exporter for todoist-trace records.
Generates a standalone, self-contained single-page application with:
- Stats KPI cards (total tasks, active days, on-time rates, velocity)
- Dynamic interactive SVG charts (daily activity timeline, hourly distribution, project share)
- Instant client-side search and multi-dimensional filters (project, section, priority, due status, labels)
- Multiple view modes: Timeline (daily collapsible tree), Projects hierarchy, and Sortable Data Table
- Light and Dark mode with auto-detection and persistence
- Zero external dependencies: 100% offline-ready and self-contained
"""

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import normalize_categories


def generate_html(
    records: List[Dict[str, Any]],
    include_labels: bool = True,
    include_descriptions: bool = True,
    include_priorities: bool = True,
    include_due_dates: bool = True,
    title: str = "Todoist Trace - Activity Dashboard",
    categories_config: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a self-contained, interactive HTML dashboard."""
    # Sanitize JSON payload for embedding inside <script>
    json_data = json.dumps(records).replace("</", "<\\/")

    # Normalize category configuration and serialize for JS
    norm_categories = normalize_categories(categories_config)
    categories_json = json.dumps(norm_categories)

    # Build dynamic category checkbox options
    category_options = [
        '<label class="multiselect-option"><input type="checkbox" value="work" onchange="onCategoryChange()"><span class="multiselect-opt-text">Work</span></label>',
        '<label class="multiselect-option"><input type="checkbox" value="personal" onchange="onCategoryChange()"><span class="multiselect-opt-text">Personal</span></label>',
    ]
    for cat_key in norm_categories:
        if cat_key not in ("work", "personal"):
            category_options.append(
                f'<label class="multiselect-option"><input type="checkbox" value="{html.escape(cat_key)}" onchange="onCategoryChange()"><span class="multiselect-opt-text">{html.escape(cat_key.capitalize())}</span></label>'
            )
    category_options.append(
        '<label class="multiselect-option"><input type="checkbox" value="others" onchange="onCategoryChange()"><span class="multiselect-opt-text">Others (Unassigned)</span></label>'
    )
    category_options_html = "\n              ".join(category_options)

    # Pre-calculate initial summary stats for SSR fallback
    total_records = len(records)
    unique_dates = len({r.get("date") for r in records if r.get("date")})
    unique_projects = len({r.get("top_level_project") for r in records if r.get("top_level_project")})

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    /* CSS Reset & Semantic Variables */
    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    :root[data-theme="dark"] {{
      --bg: #090d16;
      --bg-card: #111827;
      --bg-card-subtle: #162032;
      --bg-hover: #1e293b;
      --border: #1f293d;
      --border-subtle: #1b2436;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --accent-light: rgba(99, 102, 241, 0.15);
      --p1-bg: rgba(239, 68, 68, 0.15);
      --p1-border: rgba(239, 68, 68, 0.4);
      --p1-text: #f87171;
      --p2-bg: rgba(249, 115, 22, 0.15);
      --p2-border: rgba(249, 115, 22, 0.4);
      --p2-text: #fb923c;
      --p3-bg: rgba(59, 130, 246, 0.15);
      --p3-border: rgba(59, 130, 246, 0.4);
      --p3-text: #60a5fa;
      --p4-bg: rgba(148, 163, 184, 0.1);
      --p4-border: rgba(148, 163, 184, 0.25);
      --p4-text: #94a3b8;
      --status-overdue-bg: rgba(239, 68, 68, 0.15);
      --status-overdue-text: #f87171;
      --status-ontime-bg: rgba(34, 197, 94, 0.15);
      --status-ontime-text: #4ade80;
      --status-early-bg: rgba(20, 184, 166, 0.15);
      --status-early-text: #2dd4bf;
      --shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.5);
    }}

    :root[data-theme="light"] {{
      --bg: #f8fafc;
      --bg-card: #ffffff;
      --bg-card-subtle: #f1f5f9;
      --bg-hover: #e2e8f0;
      --border: #e2e8f0;
      --border-subtle: #cbd5e1;
      --text: #0f172a;
      --text-muted: #475569;
      --text-dim: #94a3b8;
      --accent: #4f46e5;
      --accent-hover: #4338ca;
      --accent-light: rgba(79, 70, 229, 0.1);
      --p1-bg: #fee2e2;
      --p1-border: #fca5a5;
      --p1-text: #b91c1c;
      --p2-bg: #ffedd5;
      --p2-border: #fdba74;
      --p2-text: #c2410c;
      --p3-bg: #dbeafe;
      --p3-border: #93c5fd;
      --p3-text: #1d4ed8;
      --p4-bg: #f1f5f9;
      --p4-border: #cbd5e1;
      --p4-text: #475569;
      --status-overdue-bg: #fee2e2;
      --status-overdue-text: #b91c1c;
      --status-ontime-bg: #dcfce7;
      --status-ontime-text: #15803d;
      --status-early-bg: #ccfbf1;
      --status-early-text: #0f766e;
      --shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.08);
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      transition: background-color 0.2s ease, color 0.2s ease;
      min-height: 100vh;
      padding-bottom: 60px;
    }}

    /* Container */
    .container {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 0 20px;
    }}

    /* Top Navigation Header */
    header.topbar {{
      position: sticky;
      top: 0;
      z-index: 50;
      background-color: var(--bg);
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(12px);
      padding: 14px 0;
      margin-bottom: 24px;
    }}

    .topbar-content {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .brand-icon {{
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: linear-gradient(135deg, var(--accent), #ec4899);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      font-weight: 700;
      font-size: 16px;
      box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4);
    }}

    .brand-title {{
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}

    .brand-badge {{
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 600;
      letter-spacing: 0.05em;
      padding: 2px 8px;
      border-radius: 20px;
      background-color: var(--accent-light);
      color: var(--accent);
      border: 1px solid var(--accent);
    }}

    .topbar-actions {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    /* Buttons */
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 6px 14px;
      font-size: 13px;
      font-weight: 500;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s ease;
      border: 1px solid var(--border);
      background-color: var(--bg-card);
      color: var(--text);
    }}

    .btn:hover {{
      background-color: var(--bg-hover);
    }}

    .btn-primary {{
      background-color: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
    }}

    .btn-primary:hover {{
      background-color: var(--accent-hover);
    }}

    .btn-icon {{
      padding: 6px 10px;
    }}

    .btn-sm {{
      padding: 4px 10px;
      font-size: 12px;
      border-radius: 6px;
    }}

    /* KPI Summary Cards Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}

    .kpi-card {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      box-shadow: var(--shadow);
      transition: transform 0.15s ease;
    }}

    .kpi-card:hover {{
      transform: translateY(-2px);
    }}

    .kpi-label {{
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-muted);
      margin-bottom: 6px;
    }}

    .kpi-value {{
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--text);
    }}

    .kpi-subtext {{
      font-size: 12px;
      color: var(--text-dim);
      margin-top: 4px;
    }}

    /* Visualizations Section */
    .charts-grid {{
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }}

    @media (max-width: 900px) {{
      .charts-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    .chart-card {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: var(--shadow);
    }}

    .chart-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }}

    .chart-title {{
      font-size: 14px;
      font-weight: 600;
      color: var(--text);
    }}

    .chart-subtitle {{
      font-size: 12px;
      color: var(--text-muted);
    }}

    .chart-container {{
      width: 100%;
      height: 180px;
      position: relative;
    }}

    /* Search & Filter Controls */
    .filter-bar {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 24px;
      box-shadow: var(--shadow);
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}

    .filter-row {{
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }}

    .search-input-wrap {{
      position: relative;
      flex: 1;
      min-width: 240px;
    }}

    .search-input {{
      width: 100%;
      padding: 8px 12px 8px 36px;
      font-size: 14px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text);
      outline: none;
      transition: border-color 0.15s ease;
    }}

    .search-input:focus {{
      border-color: var(--accent);
    }}

    .search-icon {{
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-dim);
      font-size: 14px;
    }}

    /* Multiselect Dropdown Component */
    .multiselect {{
      position: relative;
      display: inline-block;
      user-select: none;
    }}

    .multiselect-btn {{
      display: inline-flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 7px 12px;
      font-size: 13px;
      font-weight: 500;
      border-radius: 8px;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text);
      outline: none;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s ease;
      min-width: 140px;
      max-width: 220px;
    }}

    .multiselect-btn:hover {{
      background-color: var(--bg-hover);
      border-color: var(--text-dim);
    }}

    .multiselect.open .multiselect-btn {{
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-light);
    }}

    .multiselect-label {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      text-align: left;
      flex: 1;
    }}

    .multiselect-arrow {{
      font-size: 10px;
      color: var(--text-dim);
      transition: transform 0.2s ease;
      flex-shrink: 0;
    }}

    .multiselect.open .multiselect-arrow {{
      transform: rotate(180deg);
      color: var(--accent);
    }}

    .multiselect-menu {{
      display: none;
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      min-width: 220px;
      max-width: 320px;
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 10px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.3);
      z-index: 100;
      padding: 8px;
      flex-direction: column;
      gap: 6px;
    }}

    :root[data-theme="light"] .multiselect-menu {{
      box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.15), 0 8px 10px -6px rgba(15, 23, 42, 0.1);
    }}

    .multiselect.open .multiselect-menu {{
      display: flex;
    }}

    .multiselect-actions {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border-subtle);
    }}

    .multiselect-action-btn {{
      background: transparent;
      border: none;
      color: var(--accent);
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      padding: 3px 6px;
      border-radius: 4px;
      transition: background-color 0.15s ease;
    }}

    .multiselect-action-btn:hover {{
      background-color: var(--accent-light);
    }}

    .multiselect-search-wrap {{
      position: relative;
      margin: 2px 0;
    }}

    .multiselect-search {{
      width: 100%;
      padding: 5px 8px;
      font-size: 12px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text);
      outline: none;
    }}

    .multiselect-search:focus {{
      border-color: var(--accent);
    }}

    .multiselect-options {{
      max-height: 220px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding-right: 2px;
    }}

    .multiselect-options::-webkit-scrollbar {{
      width: 4px;
    }}

    .multiselect-options::-webkit-scrollbar-thumb {{
      background-color: var(--border);
      border-radius: 4px;
    }}

    .multiselect-option {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 8px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 12px;
      color: var(--text);
      transition: background-color 0.12s ease;
      user-select: none;
    }}

    .multiselect-option:hover {{
      background-color: var(--bg-hover);
    }}

    .multiselect-option input[type="checkbox"] {{
      cursor: pointer;
      width: 14px;
      height: 14px;
      accent-color: var(--accent);
      flex-shrink: 0;
    }}

    .multiselect-opt-text {{
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .multiselect-empty {{
      padding: 10px 8px;
      font-size: 12px;
      color: var(--text-dim);
      text-align: center;
    }}

    .filter-pills {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }}

    .pill {{
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 500;
      border-radius: 16px;
      cursor: pointer;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text-muted);
      transition: all 0.15s ease;
      user-select: none;
    }}

    .pill:hover {{
      background-color: var(--bg-hover);
      color: var(--text);
    }}

    .pill.active {{
      background-color: var(--accent);
      border-color: var(--accent);
      color: #ffffff;
    }}

    /* Date Range Filter Row */
    .date-filter-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      padding-top: 2px;
    }}

    .date-label {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      user-select: none;
    }}

    /* Date Range Dropdown */
    .date-range-dropdown {{
      position: relative;
      display: inline-block;
    }}

    .date-range-btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 500;
      border-radius: 8px;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text);
      outline: none;
      cursor: pointer;
      transition: all 0.15s ease;
      white-space: nowrap;
    }}

    .date-range-btn:hover {{
      background-color: var(--bg-hover);
      border-color: var(--text-dim);
    }}

    .date-range-dropdown.open .date-range-btn {{
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-light);
    }}

    .date-range-btn.has-value {{
      border-color: var(--accent);
      background-color: var(--accent-light);
      color: var(--accent);
      font-weight: 600;
    }}

    .date-range-menu {{
      width: 530px;
      max-width: 530px;
      padding: 12px 14px;
      gap: 10px;
      left: 0;
      right: auto;
    }}

    @media (max-width: 600px) {{
      .date-range-menu {{
        width: calc(100vw - 32px);
        min-width: 280px;
        max-width: 530px;
      }}
    }}

    .date-range-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border);
    }}

    .date-range-title {{
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-dim);
    }}

    .date-range-selected-preview {{
      font-size: 11px;
      font-weight: 600;
      color: var(--accent);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .cal-nav-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
      padding: 2px 0;
    }}

    .cal-nav-btn {{
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      border-radius: 6px;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text);
      cursor: pointer;
      transition: all 0.15s ease;
      line-height: 1;
    }}

    .cal-nav-btn:hover {{
      background-color: var(--bg-hover);
      border-color: var(--text-dim);
    }}

    .cal-dual-container {{
      display: flex;
      gap: 16px;
      justify-content: space-between;
    }}

    @media (max-width: 600px) {{
      .cal-dual-container {{
        flex-direction: column;
        gap: 12px;
      }}
    }}

    .cal-pane {{
      flex: 1 1 230px;
      min-width: 220px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}

    .cal-pane-title {{
      font-size: 12px;
      font-weight: 700;
      text-align: center;
      color: var(--text);
      padding: 2px 0 4px 0;
    }}

    .cal-weekdays {{
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      text-align: center;
      font-size: 10px;
      font-weight: 700;
      color: var(--text-dim);
      padding-bottom: 2px;
    }}

    .cal-grid {{
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      row-gap: 2px;
      column-gap: 0;
    }}

    .cal-day-cell {{
      height: 28px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      cursor: pointer;
      user-select: none;
      color: var(--text);
      border-radius: 0;
      transition: background-color 0.1s ease;
    }}

    .cal-day-empty {{
      height: 28px;
      cursor: default;
    }}

    .cal-day-cell:hover:not(.cal-day-empty) {{
      background-color: var(--bg-hover);
      border-radius: 4px;
    }}

    .cal-day-cell.cal-start {{
      background-color: var(--accent) !important;
      color: #ffffff !important;
      font-weight: 700;
      border-top-left-radius: 6px;
      border-bottom-left-radius: 6px;
    }}

    .cal-day-cell.cal-end {{
      background-color: var(--accent) !important;
      color: #ffffff !important;
      font-weight: 700;
      border-top-right-radius: 6px;
      border-bottom-right-radius: 6px;
    }}

    .cal-day-cell.cal-single {{
      border-radius: 6px !important;
    }}

    .cal-day-cell.cal-in-range {{
      background-color: var(--accent-light);
      color: var(--text);
      border-radius: 0;
    }}

    .cal-day-cell.cal-preview {{
      background-color: var(--accent-light);
      opacity: 0.85;
      border-radius: 0;
    }}

    .cal-day-cell.cal-today:not(.cal-start):not(.cal-end) {{
      box-shadow: inset 0 0 0 1px var(--accent);
      border-radius: 4px;
    }}

    .date-range-footer {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding-top: 8px;
      border-top: 1px solid var(--border);
      flex-wrap: wrap;
    }}

    .date-range-inputs {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .date-input-inline {{
      display: flex;
      align-items: center;
      gap: 4px;
    }}

    .date-input-inline label {{
      font-size: 11px;
      font-weight: 600;
      color: var(--text-muted);
    }}

    .filter-date-input-sm {{
      padding: 4px 6px;
      font-size: 11px;
      font-family: inherit;
      border: 1px solid var(--border);
      border-radius: 4px;
      background-color: var(--bg-card);
      color: var(--text);
      outline: none;
      cursor: pointer;
      color-scheme: dark;
      width: 120px;
    }}

    :root[data-theme="light"] .filter-date-input-sm {{
      color-scheme: light;
      background-color: #ffffff;
    }}

    .filter-date-input-sm:focus {{
      border-color: var(--accent);
    }}

    .date-range-actions {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
    }}

    .btn-toggle-days {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      font-size: 12px;
      font-weight: 600;
      border-radius: 6px;
      cursor: pointer;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text);
      transition: all 0.15s ease;
      user-select: none;
    }}

    .btn-toggle-days:hover {{
      background-color: var(--bg-hover);
      border-color: var(--accent);
      color: var(--accent);
    }}

    /* View Switcher Tabs */
    .view-switcher {{
      display: inline-flex;
      border-radius: 8px;
      background-color: var(--bg-card-subtle);
      border: 1px solid var(--border);
      padding: 2px;
    }}

    .view-tab {{
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 600;
      border-radius: 6px;
      cursor: pointer;
      color: var(--text-muted);
      background: transparent;
      border: none;
      transition: all 0.15s ease;
    }}

    .view-tab.active {{
      background-color: var(--bg-card);
      color: var(--text);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }}

    /* Filter Counter Banner */
    .filter-status {{
      font-size: 13px;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    /* View Content Containers */
    .view-section {{
      display: none;
    }}

    .view-section.active {{
      display: block;
    }}

    /* Day / Timeline View Accordions */
    .day-group {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-bottom: 16px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .day-header {{
      padding: 14px 20px;
      background-color: var(--bg-card-subtle);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      user-select: none;
    }}

    .day-title {{
      font-size: 15px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .day-count-badge {{
      font-size: 12px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 12px;
      background-color: var(--accent-light);
      color: var(--accent);
    }}

    .day-toggle-icon {{
      font-size: 12px;
      color: var(--text-dim);
      transition: transform 0.2s ease;
    }}

    .day-group.collapsed .day-toggle-icon {{
      transform: rotate(-90deg);
    }}

    .day-group.collapsed .day-content {{
      display: none;
    }}

    .day-content {{
      padding: 16px 20px;
    }}

    /* Top-Level Project Group */
    .top-project-group {{
      margin-bottom: 16px;
      background-color: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 14px 16px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }}

    .top-project-group:last-child {{
      margin-bottom: 0;
    }}

    .top-project-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border-subtle);
    }}

    .top-project-icon {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
      margin-right: 4px;
      color: var(--accent);
    }}

    .top-project-title {{
      font-size: 14px;
      font-weight: 700;
      color: var(--text);
      letter-spacing: -0.01em;
    }}

    .top-project-count-badge {{
      font-size: 11px;
      font-weight: 600;
      color: var(--text-dim);
      background-color: var(--bg-hover);
      padding: 2px 8px;
      border-radius: 10px;
      border: 1px solid var(--border-subtle);
    }}

    .top-project-content {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}

    /* Sub-Project Group */
    .subproject-group {{
      margin-top: 4px;
      margin-bottom: 6px;
      padding-left: 12px;
      border-left: 2px solid var(--accent);
    }}

    .subproject-group.depth-1 {{
      margin-left: 14px;
      border-left: 2px dashed var(--accent-light);
    }}

    .subproject-group.depth-2 {{
      margin-left: 14px;
      border-left: 2px dotted var(--text-dim);
    }}

    .subproject-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }}

    .subproject-icon {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
      margin-right: 4px;
      color: var(--accent);
      opacity: 0.9;
    }}

    .subproject-title {{
      font-size: 13px;
      font-weight: 600;
      color: var(--accent);
    }}

    .subproject-count-badge {{
      font-size: 10px;
      font-weight: 500;
      color: var(--text-dim);
      background-color: var(--bg-hover);
      padding: 1px 6px;
      border-radius: 8px;
    }}

    .subproject-content {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    /* Section Group inside Project */
    .project-section-group {{
      margin-top: 10px;
      margin-bottom: 6px;
      padding-left: 10px;
      border-left: 2px solid var(--accent-light);
    }}

    .project-section-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 6px;
      padding-bottom: 4px;
      border-bottom: 1px solid var(--border-subtle);
    }}

    .project-section-title-wrap {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .section-icon {{
      font-size: 11px;
      color: var(--accent);
      opacity: 0.9;
    }}

    .section-name {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
    }}

    .section-count-badge {{
      font-size: 10px;
      font-weight: 500;
      padding: 1px 6px;
      border-radius: 10px;
      background-color: var(--bg-hover);
      color: var(--text-dim);
    }}

    .section-tag {{
      font-size: 11px;
      font-weight: 500;
      padding: 1px 6px;
      border-radius: 4px;
      background-color: var(--bg-hover);
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
    }}

    /* Hierarchical Task Tree */
    .task-tree {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .task-tree-node {{
      position: relative;
    }}

    .task-children {{
      margin-left: 20px;
      padding-left: 14px;
      border-left: 2px dashed var(--border);
      margin-top: 6px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .task-item.is-parent-context {{
      background-color: var(--bg-card-subtle);
      border-left: 2px dashed var(--accent);
    }}

    .badge-parent {{
      background-color: var(--bg-hover);
      color: var(--text-dim);
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 4px;
    }}

    .task-item.is-subtask {{
      border-left: 2px solid var(--accent-light);
    }}

    /* Task Item Row */
    .task-item {{
      padding: 8px 12px;
      border-radius: 8px;
      margin-bottom: 2px;
      background-color: var(--bg-card);
      border: 1px solid var(--border-subtle);
      transition: background-color 0.15s ease;
    }}

    .task-item:hover {{
      background-color: var(--bg-card-subtle);
    }}

    .task-main-row {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }}

    .task-title-group {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      flex: 1;
    }}

    .task-bullet {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      margin-top: 1px;
      flex-shrink: 0;
    }}

    .subtask-branch {{
      color: var(--text-dim);
      font-size: 13px;
      font-weight: 700;
      line-height: 1;
      margin-right: 1px;
    }}

    /* SVG Vector Icons */
    .icon {{
      display: inline-flex;
      vertical-align: middle;
      flex-shrink: 0;
    }}

    .icon-layers {{
      color: var(--accent);
    }}

    .icon-hash {{
      color: var(--accent);
      opacity: 0.9;
    }}

    .icon-section {{
      color: var(--accent);
      vertical-align: -2px;
    }}

    .icon-check-square {{
      color: var(--accent);
    }}

    .icon-minus-square {{
      color: var(--text-dim);
    }}

    .task-content {{
      font-size: 14px;
      font-weight: 500;
      color: var(--text);
    }}

    .task-meta-group {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}

    .task-time {{
      font-size: 12px;
      font-family: monospace;
      color: var(--text-dim);
    }}

    /* Badges */
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid transparent;
    }}

    .badge-p1 {{ background-color: var(--p1-bg); border-color: var(--p1-border); color: var(--p1-text); }}
    .badge-p2 {{ background-color: var(--p2-bg); border-color: var(--p2-border); color: var(--p2-text); }}
    .badge-p3 {{ background-color: var(--p3-bg); border-color: var(--p3-border); color: var(--p3-text); }}
    .badge-p4 {{ background-color: var(--p4-bg); border-color: var(--p4-border); color: var(--p4-text); }}

    .badge-overdue {{ background-color: var(--status-overdue-bg); color: var(--status-overdue-text); }}
    .badge-ontime {{ background-color: var(--status-ontime-bg); color: var(--status-ontime-text); }}
    .badge-early {{ background-color: var(--status-early-bg); color: var(--status-early-text); }}

    .badge-label {{
      background-color: var(--bg-hover);
      color: var(--text-muted);
      cursor: pointer;
    }}
    .badge-label:hover {{
      color: var(--accent);
    }}

    .badge-date {{
      font-size: 11px;
      font-family: monospace;
      font-weight: 600;
      color: var(--text-muted);
      background-color: var(--bg-card-subtle);
      border: 1px solid var(--border);
      padding: 1px 6px;
      border-radius: 4px;
      white-space: nowrap;
    }}

    .projects-view-toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }}

    .task-desc {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 6px;
      margin-left: 20px;
      padding-left: 10px;
      border-left: 2px solid var(--border);
      line-height: 1.5;
    }}
    .task-desc a,
    .task-content a,
    .task-parent-title a,
    .data-table td a {{
      color: var(--accent);
      text-decoration: underline;
      text-underline-offset: 2px;
      word-break: break-word;
    }}
    .task-desc a:hover,
    .task-content a:hover,
    .task-parent-title a:hover,
    .data-table td a:hover {{
      text-decoration: none;
      filter: brightness(1.2);
    }}
    .task-desc code,
    .task-content code,
    .data-table td code {{
      background-color: var(--bg-hover);
      color: var(--text);
      padding: 1px 5px;
      border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.9em;
      border: 1px solid var(--border);
    }}
    .task-desc ul, .task-desc ol {{
      margin: 4px 0 4px 18px;
      padding-left: 0;
    }}
    .task-desc li {{
      margin-bottom: 2px;
    }}

    /* Table View */
    .table-container {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow-x: auto;
      box-shadow: var(--shadow);
    }}

    table.data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }}

    table.data-table th {{
      background-color: var(--bg-card-subtle);
      padding: 12px 14px;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }}

    table.data-table th:hover {{
      color: var(--text);
    }}

    table.data-table td {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-subtle);
      vertical-align: top;
    }}

    table.data-table tr:hover td {{
      background-color: var(--bg-card-subtle);
    }}

    /* Tooltip */
    .chart-tooltip {{
      position: fixed;
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 12px;
      box-shadow: var(--shadow);
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.15s ease;
      z-index: 1000;
      transform: translate(-50%, -100%);
      margin-top: -10px;
      white-space: nowrap;
    }}

    /* Empty state */
    .empty-state {{
      text-align: center;
      padding: 48px 20px;
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: var(--text-muted);
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="container topbar-content">
      <div class="brand">
        <div class="brand-icon">✓</div>
        <div class="brand-title">todoist-trace</div>
        <div class="brand-badge">Activity Dashboard</div>
      </div>
      <div class="topbar-actions">
        <div class="view-switcher">
          <button class="view-tab active" data-view="timeline" onclick="switchView('timeline')">Timeline</button>
          <button class="view-tab" data-view="projects" onclick="switchView('projects')">Projects</button>
          <button class="view-tab" data-view="table" onclick="switchView('table')">Table</button>
        </div>
        <button class="btn btn-icon" id="theme-toggle" onclick="toggleTheme()" title="Toggle Dark / Light Mode">
          <span id="theme-icon">☀️</span>
        </button>
      </div>
    </div>
  </header>

  <main class="container">
    <!-- KPI Header Cards -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Completed Tasks</div>
        <div class="kpi-value" id="kpi-total-tasks">{total_records:,}</div>
        <div class="kpi-subtext" id="kpi-sub-tasks">Across all synced records</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Active Days</div>
        <div class="kpi-value" id="kpi-active-days">{unique_dates}</div>
        <div class="kpi-subtext" id="kpi-velocity">- tasks / active day</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">On-Time Rate</div>
        <div class="kpi-value" id="kpi-ontime-rate">-%</div>
        <div class="kpi-subtext" id="kpi-ontime-sub">Based on due dates</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Top Project</div>
        <div class="kpi-value" id="kpi-top-project">-</div>
        <div class="kpi-subtext" id="kpi-top-proj-sub">- tasks</div>
      </div>
    </div>

    <!-- Charts Row -->
    <div class="charts-grid">
      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">Daily Activity Velocity</div>
            <div class="chart-subtitle">Tasks completed per day (click bar to filter day)</div>
          </div>
        </div>
        <div class="chart-container" id="timeline-chart-wrap">
          <svg id="timeline-chart" width="100%" height="100%"></svg>
          <div class="chart-tooltip" id="chart-tooltip"></div>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">Project Share</div>
            <div class="chart-subtitle">Top projects distribution</div>
          </div>
        </div>
        <div class="chart-container" id="project-chart-wrap" style="height: 180px; overflow-y: auto;">
          <div id="project-bars" style="display: flex; flex-direction: column; gap: 8px;"></div>
        </div>
      </div>
    </div>

    <!-- Filter & Search Controls -->
    <div class="filter-bar">
      <div class="filter-row">
        <div class="search-input-wrap">
          <span class="search-icon">🔍</span>
          <input type="text" id="search-box" class="search-input" placeholder="Search tasks, descriptions, projects, or @tags..." oninput="onSearchChange()">
        </div>
        <div class="multiselect" id="category-filter" data-name="Categories" data-default="All Categories">
          <button type="button" class="multiselect-btn" onclick="toggleDropdown('category-filter')">
            <span class="multiselect-label">All Categories</span>
            <span class="multiselect-arrow">▾</span>
          </button>
          <div class="multiselect-menu">
            <div class="multiselect-actions">
              <button type="button" class="multiselect-action-btn" onclick="selectAllOptions('category-filter')">All</button>
              <button type="button" class="multiselect-action-btn" onclick="clearAllOptions('category-filter')">Clear</button>
            </div>
            <div class="multiselect-options">
              {category_options_html}
            </div>
          </div>
        </div>

        <div class="multiselect" id="parent-project-filter" data-name="Parent Projects" data-default="All Parent Projects">
          <button type="button" class="multiselect-btn" onclick="toggleDropdown('parent-project-filter')">
            <span class="multiselect-label">All Parent Projects</span>
            <span class="multiselect-arrow">▾</span>
          </button>
          <div class="multiselect-menu">
            <div class="multiselect-actions">
              <button type="button" class="multiselect-action-btn" onclick="selectAllOptions('parent-project-filter')">All</button>
              <button type="button" class="multiselect-action-btn" onclick="clearAllOptions('parent-project-filter')">Clear</button>
            </div>
            <div class="multiselect-search-wrap">
              <input type="text" class="multiselect-search" placeholder="Search parent projects..." oninput="filterDropdownOptions('parent-project-filter', this.value)">
            </div>
            <div class="multiselect-options" id="parent-project-options"></div>
          </div>
        </div>

        <div class="multiselect" id="project-filter" data-name="Projects" data-default="All Projects">
          <button type="button" class="multiselect-btn" onclick="toggleDropdown('project-filter')">
            <span class="multiselect-label">All Projects</span>
            <span class="multiselect-arrow">▾</span>
          </button>
          <div class="multiselect-menu">
            <div class="multiselect-actions">
              <button type="button" class="multiselect-action-btn" onclick="selectAllOptions('project-filter')">All</button>
              <button type="button" class="multiselect-action-btn" onclick="clearAllOptions('project-filter')">Clear</button>
            </div>
            <div class="multiselect-search-wrap">
              <input type="text" class="multiselect-search" placeholder="Search projects..." oninput="filterDropdownOptions('project-filter', this.value)">
            </div>
            <div class="multiselect-options" id="project-options"></div>
          </div>
        </div>

        <div class="multiselect" id="priority-filter" data-name="Priorities" data-default="All Priorities">
          <button type="button" class="multiselect-btn" onclick="toggleDropdown('priority-filter')">
            <span class="multiselect-label">All Priorities</span>
            <span class="multiselect-arrow">▾</span>
          </button>
          <div class="multiselect-menu">
            <div class="multiselect-actions">
              <button type="button" class="multiselect-action-btn" onclick="selectAllOptions('priority-filter')">All</button>
              <button type="button" class="multiselect-action-btn" onclick="clearAllOptions('priority-filter')">Clear</button>
            </div>
            <div class="multiselect-options">
              <label class="multiselect-option"><input type="checkbox" value="p1" onchange="onPriorityChange()"><span class="multiselect-opt-text">P1 (Urgent)</span></label>
              <label class="multiselect-option"><input type="checkbox" value="p2" onchange="onPriorityChange()"><span class="multiselect-opt-text">P2 (High)</span></label>
              <label class="multiselect-option"><input type="checkbox" value="p3" onchange="onPriorityChange()"><span class="multiselect-opt-text">P3 (Medium)</span></label>
              <label class="multiselect-option"><input type="checkbox" value="p4" onchange="onPriorityChange()"><span class="multiselect-opt-text">P4 (Normal)</span></label>
            </div>
          </div>
        </div>

        <div class="multiselect" id="due-filter" data-name="Due Statuses" data-default="All Due Statuses">
          <button type="button" class="multiselect-btn" onclick="toggleDropdown('due-filter')">
            <span class="multiselect-label">All Due Statuses</span>
            <span class="multiselect-arrow">▾</span>
          </button>
          <div class="multiselect-menu">
            <div class="multiselect-actions">
              <button type="button" class="multiselect-action-btn" onclick="selectAllOptions('due-filter')">All</button>
              <button type="button" class="multiselect-action-btn" onclick="clearAllOptions('due-filter')">Clear</button>
            </div>
            <div class="multiselect-options">
              <label class="multiselect-option"><input type="checkbox" value="overdue" onchange="onDueChange()"><span class="multiselect-opt-text">Overdue</span></label>
              <label class="multiselect-option"><input type="checkbox" value="on_time" onchange="onDueChange()"><span class="multiselect-opt-text">On Time</span></label>
              <label class="multiselect-option"><input type="checkbox" value="early" onchange="onDueChange()"><span class="multiselect-opt-text">Early</span></label>
              <label class="multiselect-option"><input type="checkbox" value="undated" onchange="onDueChange()"><span class="multiselect-opt-text">Undated</span></label>
            </div>
          </div>
        </div>
        <button class="btn" onclick="resetFilters()">Reset Filters</button>
      </div>

      <div class="filter-row date-filter-row">
        <span class="date-label">Period:</span>
        <div class="filter-pills" id="date-presets">
          <span class="pill active" data-preset="all" onclick="setDatePreset('all')">All Time</span>
          <span class="pill" data-preset="cur_week" onclick="setDatePreset('cur_week')">Current Week</span>
          <span class="pill" data-preset="prev_week" onclick="setDatePreset('prev_week')">Previous Week</span>
          <span class="pill" data-preset="cur_month" onclick="setDatePreset('cur_month')">This Month</span>
          <span class="pill" data-preset="last_month" onclick="setDatePreset('last_month')">Last Month</span>
          <span class="pill" data-preset="cur_quarter" onclick="setDatePreset('cur_quarter')">Current Quarter</span>
          <span class="pill" data-preset="last_quarter" onclick="setDatePreset('last_quarter')">Last Quarter</span>
          <span class="pill" data-preset="cur_year" onclick="setDatePreset('cur_year')">Current Year</span>
          <span class="pill" data-preset="prev_year" onclick="setDatePreset('prev_year')">Previous Year</span>
        </div>
        <div class="multiselect date-range-dropdown" id="date-range-dropdown">
          <button type="button" class="date-range-btn" id="date-range-btn" onclick="toggleDropdown('date-range-dropdown')">
            <span>📅</span>
            <span class="date-range-label" id="date-range-label">Custom Range</span>
            <span class="multiselect-arrow">▾</span>
          </button>
          <div class="multiselect-menu date-range-menu" onclick="event.stopPropagation()">
            <div class="date-range-header">
              <div class="date-range-title">Custom Date Range</div>
              <div class="date-range-selected-preview" id="date-range-preview">Click start date, then end date</div>
            </div>
            <div class="cal-nav-bar">
              <div style="display: flex; gap: 4px;">
                <button type="button" class="cal-nav-btn" onclick="changeCalMonth(-12, event)" title="Previous Year">«</button>
                <button type="button" class="cal-nav-btn" onclick="changeCalMonth(-1, event)" title="Previous Month">‹</button>
              </div>
              <span style="font-size: 11px; font-weight: 600; color: var(--text-dim);">Pick Start &amp; End Dates</span>
              <div style="display: flex; gap: 4px;">
                <button type="button" class="cal-nav-btn" onclick="changeCalMonth(1, event)" title="Next Month">›</button>
                <button type="button" class="cal-nav-btn" onclick="changeCalMonth(12, event)" title="Next Year">»</button>
              </div>
            </div>
            <div class="cal-dual-container" id="cal-dual-container"></div>
            <div class="date-range-footer">
              <div class="date-range-inputs">
                <div class="date-input-inline">
                  <label for="date-from">From</label>
                  <input type="date" id="date-from" class="filter-date-input-sm" onchange="onManualDateInputChange()" onkeydown="if(event.key==='Enter') applyCustomDateRange()">
                </div>
                <div class="date-input-inline">
                  <label for="date-to">To</label>
                  <input type="date" id="date-to" class="filter-date-input-sm" onchange="onManualDateInputChange()" onkeydown="if(event.key==='Enter') applyCustomDateRange()">
                </div>
              </div>
              <div class="date-range-actions">
                <button type="button" class="btn btn-sm" id="btn-clear-date" onclick="clearDateRange()">Clear</button>
                <button type="button" class="btn btn-sm btn-primary" onclick="applyCustomDateRange(true)">Done</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="filter-status">
        <span id="filter-counter">Showing {total_records} of {total_records} tasks</span>
        <div style="display: flex; align-items: center; gap: 8px;">
          <button class="btn-toggle-days" id="btn-toggle-accordions" onclick="toggleAllDays()" title="Toggle expand or collapse for all displayed days">
            <span id="toggle-days-icon" style="font-size: 13px;">⊟</span>
            <span id="toggle-days-text">Collapse All Days</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Timeline View Container -->
    <div id="view-timeline" class="view-section active">
      <div id="timeline-container"></div>
    </div>

    <!-- Projects View Container -->
    <div id="view-projects" class="view-section">
      <div class="projects-view-toolbar">
        <div style="display: inline-flex; align-items: center; gap: 8px;">
          <span style="font-size: 12px; font-weight: 600; color: var(--text-muted);">Grouping:</span>
          <div class="view-switcher" id="projects-grouping-switcher">
            <button class="view-tab active" id="btn-group-project" onclick="setProjectsGrouping('project')" title="Flat list of specific projects with parent breadcrumb">By Project</button>
            <button class="view-tab" id="btn-group-hierarchy" onclick="setProjectsGrouping('hierarchy')" title="Nested 3-tier hierarchy: Category › Parent Project › Subprojects">By Hierarchy</button>
          </div>
        </div>
        <div id="projects-meta-summary" style="font-size: 12px; color: var(--text-dim);"></div>
      </div>
      <div id="projects-container"></div>
    </div>

    <!-- Data Table View Container -->
    <div id="view-table" class="view-section">
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th onclick="sortTable('date')">Date & Time ⬍</th>
              <th onclick="sortTable('top_level_project')">Parent Project ⬍</th>
              <th onclick="sortTable('project_path')">Project / Section ⬍</th>
              <th onclick="sortTable('task_path')">Task Hierarchy ⬍</th>
              <th onclick="sortTable('priority')">Priority ⬍</th>
              <th>Labels</th>
              <th onclick="sortTable('due_date')">Due Date ⬍</th>
            </tr>
          </thead>
          <tbody id="table-body"></tbody>
        </table>
      </div>
    </div>
  </main>

  <!-- Embedded JSON Payload -->
  <script type="application/json" id="trace-data">{json_data}</script>

  <!-- Client-Side Dashboard Engine -->
  <script>
    // SVG Vector Icon Suite
    const ICONS = {{
      layers: '<svg class="icon icon-layers" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
      hash: '<svg class="icon icon-hash" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/></svg>',
      section: '<svg class="icon icon-section" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M12 3v18"/></svg>',
      checkSquare: '<svg class="icon icon-check-square" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="4" fill="var(--accent-light)"/><path d="m9 12 2 2 4-4" stroke="var(--accent)" stroke-width="2.5"/></svg>',
      minusSquare: '<svg class="icon icon-minus-square" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="4"/><line x1="8" y1="12" x2="16" y2="12" stroke-width="2.5"/></svg>'
    }};

    let rawRecords = [];
    try {{
      rawRecords = JSON.parse(document.getElementById('trace-data').textContent);
    }} catch (e) {{
      console.error('Failed to parse trace records JSON', e);
    }}

    let filteredRecords = [...rawRecords];
    let currentSortColumn = 'date';
    let currentSortAsc = false;
    let activeDayFilter = null;
    let isAllDaysCollapsed = false;

    // Theme Management
    function initTheme() {{
      const saved = localStorage.getItem('todoist-trace-theme');
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const theme = saved || (prefersDark ? 'dark' : 'light');
      setTheme(theme);
    }}

    function setTheme(theme) {{
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('todoist-trace-theme', theme);
      const icon = document.getElementById('theme-icon');
      if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
      renderTimelineChart();
    }}

    function toggleTheme() {{
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      setTheme(current === 'dark' ? 'light' : 'dark');
    }}

    // Toggle expand or collapse all displayed days / groups
    function toggleAllDays() {{
      const activeSection = document.querySelector('.view-section.active');
      if (!activeSection) return;
      const groups = activeSection.querySelectorAll('.day-group');
      if (!groups.length) return;

      const hasExpanded = Array.from(groups).some(g => !g.classList.contains('collapsed'));
      const shouldCollapse = hasExpanded;
      isAllDaysCollapsed = shouldCollapse;

      groups.forEach(g => {{
        g.classList.toggle('collapsed', shouldCollapse);
      }});

      updateDayToggleButton();
    }}

    function toggleAllAccordions() {{
      toggleAllDays();
    }}

    function updateDayToggleButton() {{
      const btn = document.getElementById('btn-toggle-accordions') || document.getElementById('btn-toggle-days');
      if (!btn) return;
      const activeSection = document.querySelector('.view-section.active');
      if (!activeSection || activeSection.id === 'view-table') {{
        btn.style.display = 'none';
        return;
      }}
      const groups = activeSection.querySelectorAll('.day-group');
      if (!groups.length) {{
        btn.style.display = 'none';
        return;
      }}
      btn.style.display = 'inline-flex';

      const hasExpanded = Array.from(groups).some(g => !g.classList.contains('collapsed'));
      isAllDaysCollapsed = !hasExpanded;

      const entity = activeSection.id === 'view-timeline' ? 'Days' : 'Projects';
      const icon = document.getElementById('toggle-days-icon');
      const text = document.getElementById('toggle-days-text');

      if (icon) icon.textContent = hasExpanded ? '⊟' : '⊞';
      if (text) text.textContent = hasExpanded ? `Collapse All ${{entity}}` : `Expand All ${{entity}}`;
    }}

    // View Switching
    function switchView(viewName) {{
      document.querySelectorAll('.view-tab').forEach(t => {{
        t.classList.toggle('active', t.getAttribute('data-view') === viewName);
      }});
      document.querySelectorAll('.view-section').forEach(s => {{
        s.classList.toggle('active', s.id === `view-${{viewName}}`);
      }});
      updateDayToggleButton();
    }}

    // Date Range Helpers & Presets
    function getRecordDateRange() {{
      const dates = rawRecords.map(r => r.date).filter(Boolean).sort();
      if (!dates.length) return {{ min: '', max: '' }};
      return {{ min: dates[0], max: dates[dates.length - 1] }};
    }}

    function formatDateIso(d) {{
      const year = d.getFullYear();
      const month = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${{year}}-${{month}}-${{day}}`;
    }}

    function getReferenceDate() {{
      const bounds = getRecordDateRange();
      const now = new Date();
      if (!bounds.max) return now;
      const maxDate = new Date(bounds.max + 'T23:59:59');
      // If dataset is from >30 days ago, anchor presets to the dataset's max date
      if ((now.getTime() - maxDate.getTime()) > (30 * 86400000)) {{
        return maxDate;
      }}
      return now;
    }}

    // Calendar Range Picker State & Helpers
    let calViewYear = null;
    let calViewMonth = null;
    let calStart = null;
    let calEnd = null;
    let calHover = null;

    const MONTH_NAMES = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ];
    const WEEKDAY_NAMES = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

    function padZero(n) {{
      return String(n).padStart(2, '0');
    }}

    function initCalendarState() {{
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');
      calStart = (dateFrom && dateFrom.value) ? dateFrom.value : null;
      calEnd = (dateTo && dateTo.value) ? dateTo.value : null;
      calHover = null;

      if (calStart) {{
        const parts = calStart.split('-');
        calViewYear = parseInt(parts[0], 10);
        calViewMonth = parseInt(parts[1], 10) - 1;
      }} else {{
        const ref = getReferenceDate();
        calViewYear = ref.getFullYear();
        calViewMonth = ref.getMonth() > 0 ? ref.getMonth() - 1 : 0;
      }}
    }}

    function syncCalendarFromInputs() {{
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');
      calStart = (dateFrom && dateFrom.value) ? dateFrom.value : null;
      calEnd = (dateTo && dateTo.value) ? dateTo.value : null;
      calHover = null;
      if (calStart) {{
        const parts = calStart.split('-');
        calViewYear = parseInt(parts[0], 10);
        calViewMonth = parseInt(parts[1], 10) - 1;
      }}
      renderCalendar();
    }}

    function changeCalMonth(delta, event) {{
      if (event && event.stopPropagation) event.stopPropagation();
      if (calViewYear === null || calViewMonth === null) initCalendarState();
      calViewMonth += delta;
      while (calViewMonth < 0) {{
        calViewMonth += 12;
        calViewYear -= 1;
      }}
      while (calViewMonth > 11) {{
        calViewMonth -= 12;
        calViewYear += 1;
      }}
      renderCalendar();
    }}

    function renderCalendar() {{
      const container = document.getElementById('cal-dual-container');
      if (!container) return;
      if (calViewYear === null || calViewMonth === null) initCalendarState();

      const todayStr = formatDateIso(new Date());

      const leftY = calViewYear;
      const leftM = calViewMonth;

      let rightY = leftY;
      let rightM = leftM + 1;
      if (rightM > 11) {{
        rightM = 0;
        rightY += 1;
      }}

      function buildPaneHtml(year, month) {{
        const title = `${{MONTH_NAMES[month]}} ${{year}}`;
        const firstDayObj = new Date(year, month, 1);
        const dayOfWeek = firstDayObj.getDay();
        const startBlank = (dayOfWeek === 0 ? 6 : dayOfWeek - 1);
        const daysInMonth = new Date(year, month + 1, 0).getDate();

        let cellsHtml = '';
        for (let b = 0; b < startBlank; b++) {{
          cellsHtml += '<div class="cal-day-empty"></div>';
        }}

        for (let d = 1; d <= daysInMonth; d++) {{
          const dateStr = `${{year}}-${{padZero(month + 1)}}-${{padZero(d)}}`;
          let classes = ['cal-day-cell'];

          const isStart = (dateStr === calStart);
          const isEnd = (dateStr === calEnd);
          const isSingle = (isStart && isEnd);

          if (isSingle) {{
            classes.push('cal-start', 'cal-end', 'cal-single');
          }} else if (isStart) {{
            classes.push('cal-start');
            if (!calEnd && !calHover) classes.push('cal-single');
          }} else if (isEnd) {{
            classes.push('cal-end');
          }} else if (calStart && calEnd && dateStr > calStart && dateStr < calEnd) {{
            classes.push('cal-in-range');
          }} else if (calStart && !calEnd && calHover && dateStr > calStart && dateStr <= calHover) {{
            classes.push('cal-preview');
            if (dateStr === calHover) classes.push('cal-end');
          }}

          if (dateStr === todayStr) {{
            classes.push('cal-today');
          }}

          cellsHtml += `<div class="${{classes.join(' ')}}" data-date="${{dateStr}}" onclick="onCalDayClick('${{dateStr}}', event)" onmouseenter="onCalDayHover('${{dateStr}}')" title="${{dateStr}}">${{d}}</div>`;
        }}

        const weekdaysHtml = WEEKDAY_NAMES.map(w => `<div>${{w}}</div>`).join('');

        return `
          <div class="cal-pane">
            <div class="cal-pane-title">${{title}}</div>
            <div class="cal-weekdays">${{weekdaysHtml}}</div>
            <div class="cal-grid" onmouseleave="onCalMouseLeave()">${{cellsHtml}}</div>
          </div>
        `;
      }}

      container.innerHTML = buildPaneHtml(leftY, leftM) + buildPaneHtml(rightY, rightM);
      updateCalPreviewText();
    }}

    function onCalDayClick(dateStr, event) {{
      if (event && event.stopPropagation) event.stopPropagation();
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');

      if (!calStart || (calStart && calEnd)) {{
        calStart = dateStr;
        calEnd = null;
        calHover = null;
        if (dateFrom) dateFrom.value = calStart;
        if (dateTo) dateTo.value = '';
        renderCalendar();
      }} else if (calStart && !calEnd) {{
        if (dateStr < calStart) {{
          calStart = dateStr;
          calEnd = null;
          calHover = null;
          if (dateFrom) dateFrom.value = calStart;
          if (dateTo) dateTo.value = '';
          renderCalendar();
        }} else {{
          calEnd = dateStr;
          calHover = null;
          if (dateTo) dateTo.value = calEnd;
          renderCalendar();
          applyCustomDateRange(false);
        }}
      }}
    }}

    function onCalDayHover(dateStr) {{
      if (calStart && !calEnd) {{
        if (dateStr >= calStart) {{
          calHover = dateStr;
          const cells = document.querySelectorAll('.cal-day-cell[data-date]');
          cells.forEach(cell => {{
            const d = cell.getAttribute('data-date');
            if (d > calStart && d < dateStr) {{
              cell.classList.add('cal-preview');
              cell.classList.remove('cal-end');
            }} else if (d === dateStr && d !== calStart) {{
              cell.classList.add('cal-preview', 'cal-end');
            }} else if (d !== calStart) {{
              cell.classList.remove('cal-preview', 'cal-end');
            }}
          }});
          updateCalPreviewText();
        }} else {{
          calHover = null;
          const cells = document.querySelectorAll('.cal-day-cell[data-date]');
          cells.forEach(cell => {{
            if (cell.getAttribute('data-date') !== calStart) {{
              cell.classList.remove('cal-preview', 'cal-end');
            }}
          }});
          updateCalPreviewText();
        }}
      }}
    }}

    function onCalMouseLeave() {{
      if (calStart && !calEnd) {{
        calHover = null;
        const cells = document.querySelectorAll('.cal-day-cell[data-date]');
        cells.forEach(cell => {{
          if (cell.getAttribute('data-date') !== calStart) {{
            cell.classList.remove('cal-preview', 'cal-end');
          }}
        }});
        updateCalPreviewText();
      }}
    }}

    function updateCalPreviewText() {{
      const preview = document.getElementById('date-range-preview');
      if (!preview) return;

      if (calStart && calEnd) {{
        preview.textContent = `${{calStart}} → ${{calEnd}} (Applied)`;
      }} else if (calStart && calHover && calHover >= calStart) {{
        preview.textContent = `${{calStart}} → ${{calHover}} (click to set)`;
      }} else if (calStart) {{
        preview.textContent = `Start: ${{calStart}} (click end date)`;
      }} else {{
        preview.textContent = 'Click start date, then end date';
      }}
    }}

    function onManualDateInputChange() {{
      syncCalendarFromInputs();
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');
      if (dateFrom && dateFrom.value && dateTo && dateTo.value) {{
        applyCustomDateRange(false);
      }}
    }}

    function initDatePickers() {{
      const bounds = getRecordDateRange();
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');
      if (dateFrom && bounds.min) dateFrom.min = bounds.min;
      if (dateTo && bounds.min) dateTo.min = bounds.min;
      initCalendarState();
      renderCalendar();
    }}

    function updatePresetPills(activePreset) {{
      document.querySelectorAll('#date-presets .pill').forEach(p => {{
        p.classList.toggle('active', p.getAttribute('data-preset') === activePreset);
      }});
    }}

    function setDatePreset(preset) {{
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');
      const rangeLabel = document.getElementById('date-range-label');
      const rangeBtn = document.getElementById('date-range-btn');
      if (!dateFrom || !dateTo) return;

      activeDayFilter = null;

      const ref = getReferenceDate();
      const year = ref.getFullYear();
      const month = ref.getMonth(); // 0 to 11
      const day = ref.getDate();
      const dayOfWeek = ref.getDay(); // 0 = Sun, 1 = Mon, ..., 6 = Sat

      if (preset === 'all') {{
        dateFrom.value = '';
        dateTo.value = '';
      }} else if (preset === 'cur_week') {{
        // Current week (Mon - Sun)
        const distToMon = (dayOfWeek === 0 ? 6 : dayOfWeek - 1);
        const mon = new Date(year, month, day - distToMon);
        const sun = new Date(year, month, day - distToMon + 6);
        dateFrom.value = formatDateIso(mon);
        dateTo.value = formatDateIso(sun);
      }} else if (preset === 'prev_week') {{
        // Previous week (Mon - Sun)
        const distToMon = (dayOfWeek === 0 ? 6 : dayOfWeek - 1);
        const prevMon = new Date(year, month, day - distToMon - 7);
        const prevSun = new Date(year, month, day - distToMon - 1);
        dateFrom.value = formatDateIso(prevMon);
        dateTo.value = formatDateIso(prevSun);
      }} else if (preset === 'cur_month') {{
        const start = new Date(year, month, 1);
        const end = new Date(year, month + 1, 0);
        dateFrom.value = formatDateIso(start);
        dateTo.value = formatDateIso(end);
      }} else if (preset === 'last_month') {{
        const start = new Date(year, month - 1, 1);
        const end = new Date(year, month, 0);
        dateFrom.value = formatDateIso(start);
        dateTo.value = formatDateIso(end);
      }} else if (preset === 'cur_quarter') {{
        // Quarters: Jan-Mar, Apr-Jun, Jul-Sep, Oct-Dec
        const qIndex = Math.floor(month / 3);
        const start = new Date(year, qIndex * 3, 1);
        const end = new Date(year, (qIndex + 1) * 3, 0);
        dateFrom.value = formatDateIso(start);
        dateTo.value = formatDateIso(end);
      }} else if (preset === 'last_quarter') {{
        const qIndex = Math.floor(month / 3);
        const start = new Date(year, (qIndex - 1) * 3, 1);
        const end = new Date(year, qIndex * 3, 0);
        dateFrom.value = formatDateIso(start);
        dateTo.value = formatDateIso(end);
      }} else if (preset === 'cur_year') {{
        const start = new Date(year, 0, 1);
        const end = new Date(year, 11, 31);
        dateFrom.value = formatDateIso(start);
        dateTo.value = formatDateIso(end);
      }} else if (preset === 'prev_year') {{
        const start = new Date(year - 1, 0, 1);
        const end = new Date(year - 1, 11, 31);
        dateFrom.value = formatDateIso(start);
        dateTo.value = formatDateIso(end);
      }}

      if (rangeLabel) rangeLabel.textContent = 'Custom Range';
      if (rangeBtn) rangeBtn.classList.remove('has-value');

      syncCalendarFromInputs();
      updatePresetPills(preset);
      applyFilters();
    }}

    function applyCustomDateRange(shouldClose = true) {{
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');
      const rangeLabel = document.getElementById('date-range-label');
      const rangeBtn = document.getElementById('date-range-btn');
      if (!dateFrom || !dateTo) return;

      let fromVal = dateFrom.value;
      let toVal = dateTo.value;

      if (fromVal && toVal && fromVal > toVal) {{
        const tmp = fromVal;
        fromVal = toVal;
        toVal = tmp;
        dateFrom.value = fromVal;
        dateTo.value = toVal;
      }}

      activeDayFilter = null;

      if (fromVal || toVal) {{
        updatePresetPills(null);
        if (rangeBtn) rangeBtn.classList.add('has-value');
        if (rangeLabel) {{
          if (fromVal && toVal) {{
            rangeLabel.textContent = `${{fromVal}} → ${{toVal}}`;
          }} else if (fromVal) {{
            rangeLabel.textContent = `From ${{fromVal}}`;
          }} else {{
            rangeLabel.textContent = `Until ${{toVal}}`;
          }}
        }}
      }} else {{
        updatePresetPills('all');
        if (rangeBtn) rangeBtn.classList.remove('has-value');
        if (rangeLabel) rangeLabel.textContent = 'Custom Range';
      }}

      syncCalendarFromInputs();
      if (shouldClose) {{
        closeAllDropdowns();
      }}
      applyFilters();
    }}

    function clearDateRange() {{
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');
      const rangeLabel = document.getElementById('date-range-label');
      const rangeBtn = document.getElementById('date-range-btn');
      if (dateFrom) dateFrom.value = '';
      if (dateTo) dateTo.value = '';
      calStart = null;
      calEnd = null;
      calHover = null;
      renderCalendar();
      if (rangeBtn) rangeBtn.classList.remove('has-value');
      if (rangeLabel) rangeLabel.textContent = 'Custom Range';
      activeDayFilter = null;
      updatePresetPills('all');
      applyFilters();
    }}

    // Helper to extract the actual specific project name for a task
    function getRecordProject(r) {{
      if (r.project_levels && r.project_levels.length > 0) {{
        return r.project_levels.join(' › ');
      }}
      return r.top_level_project || 'Uncategorized';
    }}

    const CATEGORY_MAP = {categories_json};

    // Helper to determine category for a record
    function getRecordCategory(r) {{
      const tp = (r.top_level_project || '').toLowerCase().trim();
      if (!tp || tp === 'archives' || tp === 'archived') return 'others';

      for (const [catName, patterns] of Object.entries(CATEGORY_MAP)) {{
        for (const p of patterns) {{
          const pClean = p.toLowerCase().trim();
          if (pClean.endsWith('*')) {{
            const prefix = pClean.slice(0, -1);
            if (tp.startsWith(prefix)) return catName.toLowerCase();
          }} else if (
            tp === pClean ||
            tp.startsWith(pClean + '-') ||
            tp.startsWith(pClean + '_') ||
            tp.startsWith(pClean + ' ') ||
            tp.startsWith(pClean + '/')
          ) {{
            return catName.toLowerCase();
          }}
        }}
      }}
      return 'others';
    }}

    // Multiselect Dropdown Controller
    let openDropdownId = null;

    function toggleDropdown(id) {{
      if (openDropdownId === id) {{
        closeAllDropdowns();
      }} else {{
        closeAllDropdowns();
        const el = document.getElementById(id);
        if (el) {{
          el.classList.add('open');
          openDropdownId = id;
          if (id === 'date-range-dropdown') {{
            syncCalendarFromInputs();
          }}
          const menu = el.querySelector('.multiselect-menu');
          if (menu) {{
            const rect = menu.getBoundingClientRect();
            if (rect.right > window.innerWidth - 10) {{
              menu.style.left = 'auto';
              menu.style.right = '0';
            }} else {{
              menu.style.left = '0';
              menu.style.right = 'auto';
            }}
          }}
          const searchInput = el.querySelector('.multiselect-search');
          if (searchInput) {{
            searchInput.value = '';
            filterDropdownOptions(id, '');
            setTimeout(() => searchInput.focus(), 50);
          }}
        }}
      }}
    }}

    function closeAllDropdowns() {{
      document.querySelectorAll('.multiselect.open').forEach(el => {{
        el.classList.remove('open');
      }});
      openDropdownId = null;
    }}

    document.addEventListener('click', (e) => {{
      if (!e.target || !document.body.contains(e.target)) return;
      if (!e.target.closest || !e.target.closest('.multiselect')) {{
        closeAllDropdowns();
      }}
    }});
    document.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape') {{
        closeAllDropdowns();
      }}
    }});

    function getSelectedValues(id) {{
      const container = document.getElementById(id);
      if (!container) return [];
      const checked = container.querySelectorAll('.multiselect-options input[type="checkbox"]:checked');
      return Array.from(checked).map(cb => cb.value);
    }}

    function updateMultiselectButton(id) {{
      const container = document.getElementById(id);
      if (!container) return;
      const labelEl = container.querySelector('.multiselect-label');
      const btn = container.querySelector('.multiselect-btn');
      if (!labelEl) return;
      const defaultLabel = container.getAttribute('data-default') || 'All';
      const name = container.getAttribute('data-name') || 'Items';
      const allCbs = Array.from(container.querySelectorAll('.multiselect-options input[type="checkbox"]'));
      const checkedCbs = allCbs.filter(cb => cb.checked);

      let displayText = defaultLabel;
      if (checkedCbs.length === 0 || (allCbs.length > 0 && checkedCbs.length === allCbs.length)) {{
        displayText = defaultLabel;
      }} else if (checkedCbs.length === 1) {{
        const textSpan = checkedCbs[0].closest('.multiselect-option').querySelector('.multiselect-opt-text');
        displayText = textSpan ? textSpan.textContent.trim() : checkedCbs[0].value;
      }} else {{
        displayText = `${{name}} (${{checkedCbs.length}})`;
      }}
      labelEl.textContent = displayText;
      if (btn) btn.title = displayText;
    }}

    function selectAllOptions(id) {{
      const container = document.getElementById(id);
      if (!container) return;
      const searchInput = container.querySelector('.multiselect-search');
      const hasSearch = searchInput && searchInput.value.trim().length > 0;
      const options = container.querySelectorAll('.multiselect-options .multiselect-option');
      options.forEach(opt => {{
        if (!hasSearch || opt.style.display !== 'none') {{
          const cb = opt.querySelector('input[type="checkbox"]');
          if (cb) cb.checked = true;
        }}
      }});
      updateMultiselectButton(id);
      handleMultiselectChange(id);
    }}

    function clearAllOptions(id) {{
      const container = document.getElementById(id);
      if (!container) return;
      const options = container.querySelectorAll('.multiselect-options .multiselect-option');
      options.forEach(opt => {{
        const cb = opt.querySelector('input[type="checkbox"]');
        if (cb) cb.checked = false;
      }});
      updateMultiselectButton(id);
      handleMultiselectChange(id);
    }}

    function filterDropdownOptions(id, query) {{
      const container = document.getElementById(id);
      if (!container) return;
      const q = (query || '').toLowerCase().trim();
      const options = container.querySelectorAll('.multiselect-options .multiselect-option');
      let visibleCount = 0;
      options.forEach(opt => {{
        const textSpan = opt.querySelector('.multiselect-opt-text');
        const text = (textSpan ? textSpan.textContent : '').toLowerCase();
        if (!q || text.includes(q)) {{
          opt.style.display = 'flex';
          visibleCount++;
        }} else {{
          opt.style.display = 'none';
        }}
      }});
      let emptyEl = container.querySelector('.multiselect-search-empty');
      if (visibleCount === 0 && options.length > 0) {{
        if (!emptyEl) {{
          emptyEl = document.createElement('div');
          emptyEl.className = 'multiselect-empty multiselect-search-empty';
          emptyEl.textContent = 'No matching items';
          container.querySelector('.multiselect-options').appendChild(emptyEl);
        }}
        emptyEl.style.display = 'block';
      }} else if (emptyEl) {{
        emptyEl.style.display = 'none';
      }}
    }}

    function handleMultiselectChange(id) {{
      if (id === 'category-filter') {{
        onCategoryChange();
      }} else if (id === 'parent-project-filter') {{
        onParentProjectChange();
      }} else if (id === 'project-filter') {{
        onProjectChange();
      }} else if (id === 'priority-filter') {{
        onPriorityChange();
      }} else if (id === 'due-filter') {{
        onDueChange();
      }}
    }}

    // Cascading Multiselect Dropdowns Synchronization
    function updateProjectDropdowns(onlyProjects = false) {{
      const selectedCats = getSelectedValues('category-filter');
      const allCatCbs = document.querySelectorAll('#category-filter .multiselect-options input[type="checkbox"]');
      const isAllCats = (selectedCats.length === 0 || selectedCats.length === allCatCbs.length);

      // 1. Records matching current category selection
      const catRecords = rawRecords.filter(r => {{
        if (isAllCats) return true;
        const recCat = getRecordCategory(r);
        return selectedCats.includes(recCat);
      }});

      if (!onlyProjects) {{
        // 2. Unique parent projects for this category selection
        const parentProjects = [...new Set(catRecords.map(r => r.top_level_project).filter(Boolean))].sort();
        const prevCheckedParents = new Set(getSelectedValues('parent-project-filter'));
        const parentOptsContainer = document.getElementById('parent-project-options');

        if (parentOptsContainer) {{
          if (parentProjects.length === 0) {{
            parentOptsContainer.innerHTML = '<div class="multiselect-empty">No parent projects</div>';
          }} else {{
            let parentHtml = '';
            parentProjects.forEach(p => {{
              const isChecked = prevCheckedParents.has(p) ? 'checked' : '';
              parentHtml += `<label class="multiselect-option"><input type="checkbox" value="${{escapeHtml(p)}}" ${{isChecked}} onchange="onParentProjectChange()"><span class="multiselect-opt-text">${{escapeHtml(p)}}</span></label>`;
            }});
            parentOptsContainer.innerHTML = parentHtml;
          }}
          updateMultiselectButton('parent-project-filter');
        }}
      }}

      // 3. Filter for active parent projects if selected
      const selectedParents = getSelectedValues('parent-project-filter');
      const allParentCbs = document.querySelectorAll('#parent-project-filter .multiselect-options input[type="checkbox"]');
      const isAllParents = (selectedParents.length === 0 || selectedParents.length === allParentCbs.length);

      const parentFiltered = catRecords.filter(r => {{
        if (isAllParents) return true;
        return selectedParents.includes(r.top_level_project);
      }});

      // 4. Unique specific projects
      const specificProjects = [...new Set(parentFiltered.map(r => getRecordProject(r)).filter(Boolean))].sort();
      const prevCheckedProjects = new Set(getSelectedValues('project-filter'));
      const projOptsContainer = document.getElementById('project-options');

      if (projOptsContainer) {{
        if (specificProjects.length === 0) {{
          projOptsContainer.innerHTML = '<div class="multiselect-empty">No projects</div>';
        }} else {{
          let projHtml = '';
          specificProjects.forEach(p => {{
            const isChecked = prevCheckedProjects.has(p) ? 'checked' : '';
            projHtml += `<label class="multiselect-option"><input type="checkbox" value="${{escapeHtml(p)}}" ${{isChecked}} onchange="onProjectChange()"><span class="multiselect-opt-text">${{escapeHtml(p)}}</span></label>`;
          }});
          projOptsContainer.innerHTML = projHtml;
        }}
        updateMultiselectButton('project-filter');
      }}
    }}

    function initFilterDropdowns() {{
      updateProjectDropdowns();
      ['category-filter', 'parent-project-filter', 'project-filter', 'priority-filter', 'due-filter'].forEach(id => {{
        updateMultiselectButton(id);
      }});
    }}

    function onCategoryChange() {{
      updateMultiselectButton('category-filter');
      updateProjectDropdowns();
      applyFilters();
    }}

    function onParentProjectChange() {{
      updateMultiselectButton('parent-project-filter');
      updateProjectDropdowns(true);
      applyFilters();
    }}

    function onProjectChange() {{
      updateMultiselectButton('project-filter');
      applyFilters();
    }}

    function onPriorityChange() {{
      updateMultiselectButton('priority-filter');
      applyFilters();
    }}

    function onDueChange() {{
      updateMultiselectButton('due-filter');
      applyFilters();
    }}

    // Apply Active Filters
    function applyFilters() {{
      const query = (document.getElementById('search-box').value || '').toLowerCase().trim();
      const selectedCats = getSelectedValues('category-filter');
      const selectedParents = getSelectedValues('parent-project-filter');
      const selectedProjs = getSelectedValues('project-filter');
      const selectedPrios = getSelectedValues('priority-filter');
      const selectedDues = getSelectedValues('due-filter');
      const dateFrom = document.getElementById('date-from') ? document.getElementById('date-from').value : '';
      const dateTo = document.getElementById('date-to') ? document.getElementById('date-to').value : '';

      const allCatCbs = document.querySelectorAll('#category-filter .multiselect-options input[type="checkbox"]');
      const isAllCats = (selectedCats.length === 0 || selectedCats.length === allCatCbs.length);

      const allParentCbs = document.querySelectorAll('#parent-project-filter .multiselect-options input[type="checkbox"]');
      const isAllParents = (selectedParents.length === 0 || selectedParents.length === allParentCbs.length);

      const allProjCbs = document.querySelectorAll('#project-filter .multiselect-options input[type="checkbox"]');
      const isAllProjs = (selectedProjs.length === 0 || selectedProjs.length === allProjCbs.length);

      const allPrioCbs = document.querySelectorAll('#priority-filter .multiselect-options input[type="checkbox"]');
      const isAllPrios = (selectedPrios.length === 0 || selectedPrios.length === allPrioCbs.length);

      const allDueCbs = document.querySelectorAll('#due-filter .multiselect-options input[type="checkbox"]');
      const isAllDues = (selectedDues.length === 0 || selectedDues.length === allDueCbs.length);

      const catSet = new Set(selectedCats.map(c => c.toLowerCase()));
      const parentSet = new Set(selectedParents);
      const projSet = new Set(selectedProjs);
      const prioSet = new Set(selectedPrios.map(p => p.toLowerCase()));
      const dueSet = new Set(selectedDues.map(d => d.toLowerCase()));

      filteredRecords = rawRecords.filter(r => {{
        // Category check
        if (!isAllCats) {{
          const recCat = getRecordCategory(r);
          if (!catSet.has(recCat)) return false;
        }}

        // Parent Project check
        if (!isAllParents) {{
          if (!parentSet.has(r.top_level_project)) return false;
        }}

        // Specific Project check
        if (!isAllProjs) {{
          const p = getRecordProject(r);
          if (!projSet.has(p)) return false;
        }}

        // Priority check
        if (!isAllPrios) {{
          const prio = (r.priority || '').toLowerCase();
          if (!prioSet.has(prio)) return false;
        }}

        // Due check
        if (!isAllDues) {{
          const due = (r.due_status || 'undated').toLowerCase();
          if (!dueSet.has(due)) return false;
        }}

        // Day click check
        if (activeDayFilter && r.date !== activeDayFilter) return false;

        // Date range filter
        if (dateFrom && r.date && r.date < dateFrom) return false;
        if (dateTo && r.date && r.date > dateTo) return false;
        if ((dateFrom || dateTo) && !r.date) return false;

        if (query) {{
          const haystack = [
            r.task_path,
            r.description,
            r.top_level_project,
            r.project_path,
            r.section,
            (r.labels || []).join(' '),
          ].filter(Boolean).join(' ').toLowerCase();
          if (!haystack.includes(query)) return false;
        }}
        return true;
      }});

      updateKPIs();
      renderTimelineView();
      renderProjectsView();
      renderTableView();
      renderTimelineChart();
      renderProjectBars();

      const counter = document.getElementById('filter-counter');
      if (counter) {{
        let periodStr = '';
        if (dateFrom && dateTo) {{
          periodStr = ` (${{dateFrom}} to ${{dateTo}})`;
        }} else if (dateFrom) {{
          periodStr = ` (from ${{dateFrom}})`;
        }} else if (dateTo) {{
          periodStr = ` (up to ${{dateTo}})`;
        }}
        counter.textContent = `Showing ${{filteredRecords.length.toLocaleString()}} of ${{rawRecords.length.toLocaleString()}} tasks${{periodStr}}${{activeDayFilter ? ` [Filtered to ${{activeDayFilter}}]` : ''}}`;
      }}
    }}

    function onSearchChange() {{
      applyFilters();
    }}

    function resetFilters() {{
      document.getElementById('search-box').value = '';
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');
      if (dateFrom) dateFrom.value = '';
      if (dateTo) dateTo.value = '';
      const rangeLabel = document.getElementById('date-range-label');
      const rangeBtn = document.getElementById('date-range-btn');
      if (rangeBtn) rangeBtn.classList.remove('has-value');
      if (rangeLabel) rangeLabel.textContent = 'Custom Range';
      updatePresetPills('all');
      activeDayFilter = null;

      ['category-filter', 'parent-project-filter', 'project-filter', 'priority-filter', 'due-filter'].forEach(id => {{
        const container = document.getElementById(id);
        if (container) {{
          container.querySelectorAll('.multiselect-options input[type="checkbox"]').forEach(cb => {{
            cb.checked = false;
          }});
          updateMultiselectButton(id);
        }}
      }});

      updateProjectDropdowns();
      applyFilters();
    }}

    // Update KPI Header Cards
    function updateKPIs() {{
      const total = filteredRecords.length;
      document.getElementById('kpi-total-tasks').textContent = total.toLocaleString();

      const dates = [...new Set(filteredRecords.map(r => r.date).filter(Boolean))];
      const activeDays = dates.length;
      document.getElementById('kpi-active-days').textContent = activeDays;
      const avg = activeDays ? (total / activeDays).toFixed(1) : '0';
      document.getElementById('kpi-velocity').textContent = `${{avg}} tasks / active day`;

      // On-time percentage
      const datedTasks = filteredRecords.filter(r => r.due_status && r.due_status !== 'undated');
      if (datedTasks.length > 0) {{
        const onTimeOrEarly = datedTasks.filter(r => r.due_status === 'on_time' || r.due_status === 'early').length;
        const pct = Math.round((onTimeOrEarly / datedTasks.length) * 100);
        document.getElementById('kpi-ontime-rate').textContent = `${{pct}}%`;
        document.getElementById('kpi-ontime-sub').textContent = `${{onTimeOrEarly}} of ${{datedTasks.length}} dated tasks on time`;
      }} else {{
        document.getElementById('kpi-ontime-rate').textContent = 'N/A';
        document.getElementById('kpi-ontime-sub').textContent = 'No dated tasks';
      }}

      // Top Project KPI (Actual specific project)
      const projCounts = {{}};
      filteredRecords.forEach(r => {{
        const p = getRecordProject(r);
        projCounts[p] = (projCounts[p] || 0) + 1;
      }});
      let topProj = '-';
      let topCount = 0;
      for (const [p, c] of Object.entries(projCounts)) {{
        // Exclude generic buckets from the Top Project KPI if other projects exist
        const pLow = p.toLowerCase();
        if ((pLow === 'archives' || pLow === 'archived' || pLow === 'uncategorized') && Object.keys(projCounts).length > 1) continue;
        if (c > topCount) {{
          topProj = p;
          topCount = c;
        }}
      }}
      document.getElementById('kpi-top-project').textContent = topProj;
      document.getElementById('kpi-top-proj-sub').textContent = topCount ? `${{topCount.toLocaleString()}} tasks (${{Math.round(topCount / total * 100)}}%)` : '-';
    }}

    // Render Timeline View (Grouped by Date)
    function renderTimelineView() {{
      const container = document.getElementById('timeline-container');
      if (!container) return;

      if (filteredRecords.length === 0) {{
        container.innerHTML = '<div class="empty-state">No matching tasks found. Adjust search or filters.</div>';
        return;
      }}

      // Group by date
      const byDate = {{}};
      filteredRecords.forEach(r => {{
        const d = r.date || 'Undated';
        if (!byDate[d]) byDate[d] = [];
        byDate[d].push(r);
      }});

      const sortedDates = Object.keys(byDate).sort().reverse();
      let html = '';

      sortedDates.forEach(dateStr => {{
        const dayRecords = byDate[dateStr];
        const collapsedCls = isAllDaysCollapsed ? ' collapsed' : '';
        html += `
          <div class="day-group${{collapsedCls}}" data-date="${{dateStr}}">
            <div class="day-header" onclick="toggleDayAccordion(this)">
              <div class="day-title">
                <span>${{dateStr}}</span>
                <span class="day-count-badge">${{dayRecords.length}} tasks</span>
              </div>
              <span class="day-toggle-icon">▼</span>
            </div>
            <div class="day-content">
        `;

        // Split by top-level project first
        const byTopProj = {{}};
        dayRecords.forEach(r => {{
          const tp = r.top_level_project || 'Uncategorized';
          if (!byTopProj[tp]) byTopProj[tp] = [];
          byTopProj[tp].push(r);
        }});

        const sortedTopProjs = Object.keys(byTopProj).sort();
        sortedTopProjs.forEach(topProj => {{
          const topRecords = byTopProj[topProj];

          html += `
            <div class="top-project-group">
              <div class="top-project-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="top-project-icon">${{ICONS.layers}}</span>
                  <span class="top-project-title">${{escapeHtml(topProj)}}</span>
                </div>
                <span class="top-project-count-badge">${{topRecords.length}} task${{topRecords.length === 1 ? '' : 's'}}</span>
              </div>
              <div class="top-project-content">
                ${{renderSubprojectHierarchy(topRecords)}}
              </div>
            </div>
          `;
        }});

        html += `
            </div>
          </div>
        `;
      }});

      container.innerHTML = html;
      updateDayToggleButton();
    }}

    function toggleDayAccordion(el) {{
      const group = el.closest('.day-group');
      if (group) group.classList.toggle('collapsed');
      updateDayToggleButton();
    }}

    // Hierarchical Task Tree Resolution
    function buildTaskTree(records) {{
      const root = {{}};

      records.forEach(r => {{
        let levels = r.task_levels;
        if (!levels || levels.length === 0) {{
          if (r.task_path) {{
            levels = r.task_path.split(' / ').map(s => s.trim()).filter(Boolean);
          }}
          if (!levels || levels.length === 0) {{
            levels = ['Unnamed Task'];
          }}
        }}

        let curr = root;
        for (let i = 0; i < levels.length - 1; i++) {{
          const lvl = levels[i];
          if (!curr[lvl]) {{
            curr[lvl] = {{
              title: lvl,
              records: [],
              children: {{}}
            }};
          }}
          curr = curr[lvl].children;
        }}

        const leafTitle = levels[levels.length - 1];
        if (!curr[leafTitle]) {{
          curr[leafTitle] = {{
            title: leafTitle,
            records: [r],
            children: {{}}
          }};
        }} else {{
          curr[leafTitle].records.push(r);
        }}
      }});

      return root;
    }}

    function countTotalLeaves(node) {{
      let count = (node.records || []).length;
      for (const child of Object.values(node.children || {{}})) {{
        count += countTotalLeaves(child);
      }}
      return count;
    }}

    function renderTaskItemCard(title, t, isSubtask = false, showDate = false) {{
      let prioBadge = '';
      if (t.priority && t.priority.toLowerCase() !== 'p4') {{
        prioBadge = `<span class="badge badge-${{t.priority.toLowerCase()}}">${{t.priority.toUpperCase()}}</span>`;
      }}

      let dueBadge = '';
      if (t.due_status && t.due_status !== 'undated') {{
        dueBadge = `<span class="badge badge-${{t.due_status}}">${{escapeHtml(t.due_variance || t.due_status)}}</span>`;
      }}

      let labelsBadges = '';
      if (t.labels && t.labels.length > 0) {{
        labelsBadges = t.labels.map(l => `<span class="badge badge-label" onclick="filterByTag('${{escapeHtml(l)}}')">@${{escapeHtml(l.replace(/^@/, ''))}}</span>`).join(' ');
      }}

      let dateBadge = '';
      if (showDate && t.date) {{
        dateBadge = `<span class="badge badge-date" title="Completed on ${{escapeHtml(t.date)}}">${{escapeHtml(t.date)}}</span>`;
      }}

      let descHtml = '';
      if (t.description) {{
        descHtml = `<div class="task-desc">${{renderMarkdown(t.description)}}</div>`;
      }}

      const bullet = isSubtask
        ? `<span class="task-bullet is-subtask"><span class="subtask-branch">↳</span>${{ICONS.checkSquare}}</span>`
        : `<span class="task-bullet">${{ICONS.checkSquare}}</span>`;

      return `
        <div class="task-item ${{isSubtask ? 'is-subtask' : ''}}">
          <div class="task-main-row">
            <div class="task-title-group">
              ${{bullet}}
              <span class="task-content" style="${{isSubtask ? 'font-size: 13px;' : ''}}">${{renderMarkdown(title, true)}}</span>
            </div>
            <div class="task-meta-group">
              ${{prioBadge}}
              ${{dueBadge}}
              ${{labelsBadges}}
              ${{dateBadge}}
              <span class="task-time">${{escapeHtml(t.time || '')}}</span>
            </div>
          </div>
          ${{descHtml}}
        </div>
      `;
    }}

    function renderTaskTree(nodes, depth = 0, showDate = false) {{
      let html = '<div class="task-tree">';
      for (const node of Object.values(nodes)) {{
        const hasChildren = Object.keys(node.children).length > 0;
        const hasRecords = node.records && node.records.length > 0;

        html += '<div class="task-tree-node">';

        if (hasRecords) {{
          node.records.forEach(r => {{
            html += renderTaskItemCard(node.title, r, depth > 0, showDate);
          }});
        }} else {{
          const subtaskCount = countTotalLeaves(node);
          html += `
            <div class="task-item is-parent-context">
              <div class="task-main-row">
                <div class="task-title-group">
                  <span class="task-bullet is-parent">${{ICONS.minusSquare}}</span>
                  <span class="task-content" style="color: var(--text-muted); font-weight: 500;">${{renderMarkdown(node.title, true)}}</span>
                </div>
                <div class="task-meta-group">
                  <span class="badge-parent">${{subtaskCount}} subtask${{subtaskCount === 1 ? '' : 's'}}</span>
                </div>
              </div>
            </div>
          `;
        }}

        if (hasChildren) {{
          html += `
            <div class="task-children">
              ${{renderTaskTree(node.children, depth + 1, showDate)}}
            </div>
          `;
        }}

        html += '</div>';
      }}
      html += '</div>';
      return html;
    }}

    // Hierarchical Project Tree Resolution
    function buildProjectTree(records) {{
      const root = {{
        name: '',
        records: [],
        children: {{}}
      }};

      records.forEach(r => {{
        let levels = r.project_levels;
        if (!levels || levels.length === 0) {{
          if (r.project_path) {{
            levels = r.project_path.split('/').map(s => s.trim()).filter(Boolean);
          }}
        }}

        if (!levels || levels.length === 0) {{
          root.records.push(r);
          return;
        }}

        let curr = root;
        for (let i = 0; i < levels.length; i++) {{
          const lvl = levels[i];
          if (!curr.children[lvl]) {{
            curr.children[lvl] = {{
              name: lvl,
              records: [],
              children: {{}}
            }};
          }}
          curr = curr.children[lvl];
        }}
        curr.records.push(r);
      }});

      return root;
    }}

    function countTotalProjectTasks(node) {{
      let count = (node.records || []).length;
      for (const child of Object.values(node.children || {{}})) {{
        count += countTotalProjectTasks(child);
      }}
      return count;
    }}

    function renderTasksWithSections(records, showDate = false) {{
      if (!records || records.length === 0) return '';

      const hasSections = records.some(r => Boolean(r.section));
      if (!hasSections) {{
        const tree = buildTaskTree(records);
        return renderTaskTree(tree, 0, showDate);
      }}

      // Group by section: empty/unsectioned first
      const sectionMap = {{}};
      records.forEach(r => {{
        const sec = r.section || '';
        if (!sectionMap[sec]) sectionMap[sec] = [];
        sectionMap[sec].push(r);
      }});

      let html = '';
      if (sectionMap['']) {{
        const tree = buildTaskTree(sectionMap['']);
        html += renderTaskTree(tree, 0, showDate);
      }}

      for (const [sec, recs] of Object.entries(sectionMap)) {{
        if (sec === '') continue;
        html += `
          <div class="project-section-group">
            <div class="project-section-header">
              <div class="project-section-title-wrap">
                <span class="section-icon">${{ICONS.section}}</span>
                <span class="section-name">${{renderMarkdown(sec, true)}}</span>
              </div>
              <span class="section-count-badge">${{recs.length}} task${{recs.length === 1 ? '' : 's'}}</span>
            </div>
            ${{renderTaskTree(buildTaskTree(recs), 0, showDate)}}
          </div>
        `;
      }}

      return html;
    }}

    function renderProjectNode(node, depth = 0, showDate = false) {{
      let html = '';

      // Render direct tasks under this node
      if (node.records && node.records.length > 0) {{
        if (depth === 0 && Object.keys(node.children).length > 0) {{
          html += `
            <div style="font-size: 11px; font-weight: 600; color: var(--text-dim); margin-bottom: 4px;">
              (Direct Tasks)
            </div>
          `;
        }}
        html += renderTasksWithSections(node.records, showDate);
      }}

      // Render child subprojects
      const sortedChildNames = Object.keys(node.children).sort();
      for (const childName of sortedChildNames) {{
        const child = node.children[childName];
        const totalChildTasks = countTotalProjectTasks(child);

        html += `
          <div class="subproject-group depth-${{depth}}">
            <div class="subproject-header">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span class="subproject-icon">${{ICONS.hash}}</span>
                <span class="subproject-title">${{escapeHtml(child.name)}}</span>
              </div>
              <span class="subproject-count-badge">${{totalChildTasks}} task${{totalChildTasks === 1 ? '' : 's'}}</span>
            </div>
            <div class="subproject-content">
              ${{renderProjectNode(child, depth + 1, showDate)}}
            </div>
          </div>
        `;
      }}

      return html;
    }}

    function renderSubprojectHierarchy(topRecords, showDate = false) {{
      const projectTree = buildProjectTree(topRecords);
      return renderProjectNode(projectTree, 0, showDate);
    }}

    function filterByTag(tag) {{
      document.getElementById('search-box').value = `@${{tag.replace(/^@/, '')}}`;
      applyFilters();
    }}

    let projectsGrouping = 'project';

    function setProjectsGrouping(mode) {{
      projectsGrouping = mode;
      const btnProject = document.getElementById('btn-group-project');
      const btnHierarchy = document.getElementById('btn-group-hierarchy');
      if (btnProject) btnProject.classList.toggle('active', mode === 'project');
      if (btnHierarchy) btnHierarchy.classList.toggle('active', mode === 'hierarchy');
      renderProjectsView();
    }}

    // Render Projects View
    function renderProjectsView() {{
      const container = document.getElementById('projects-container');
      if (!container) return;

      const summaryEl = document.getElementById('projects-meta-summary');

      if (filteredRecords.length === 0) {{
        container.innerHTML = '<div class="empty-state">No matching tasks found.</div>';
        if (summaryEl) summaryEl.textContent = '';
        updateDayToggleButton();
        return;
      }}

      // Mode 1: By Specific Project (Flat Cards with parent breadcrumb)
      if (projectsGrouping === 'project') {{
        const byProject = {{}};
        filteredRecords.forEach(r => {{
          const specific = getRecordProject(r);
          const parent = r.top_level_project || '';
          let key = specific;
          if (parent && parent !== specific) {{
            key = `${{parent}} › ${{specific}}`;
          }}
          if (!byProject[key]) {{
            byProject[key] = {{
              key: key,
              parentName: parent,
              specificName: specific,
              category: getRecordCategory(r),
              records: [],
            }};
          }}
          byProject[key].records.push(r);
        }});

        const sortedKeys = Object.keys(byProject).sort((a, b) => {{
          const diff = byProject[b].records.length - byProject[a].records.length;
          if (diff !== 0) return diff;
          return a.localeCompare(b);
        }});

        if (summaryEl) {{
          summaryEl.textContent = `Showing ${{sortedKeys.length}} projects (${{filteredRecords.length}} tasks)`;
        }}

        let html = '';
        for (const key of sortedKeys) {{
          const item = byProject[key];
          const tasks = [...item.records].sort((a, b) => {{
            const dtA = (a.date || '') + ' ' + (a.time || '');
            const dtB = (b.date || '') + ' ' + (b.time || '');
            return dtB.localeCompare(dtA);
          }});
          const collapsedCls = isAllDaysCollapsed ? ' collapsed' : '';

          let titleHtml = '';
          if (item.parentName && item.parentName !== item.specificName) {{
            titleHtml = `<span style="font-size: 12px; color: var(--text-dim); margin-right: 4px;">${{escapeHtml(item.parentName)}} ›</span><span style="font-weight: 700; font-size: 14px;">${{escapeHtml(item.specificName)}}</span>`;
          }} else {{
            titleHtml = `<span style="font-weight: 700; font-size: 14px;">${{escapeHtml(item.specificName)}}</span>`;
          }}

          html += `
            <div class="day-group${{collapsedCls}}">
              <div class="day-header" onclick="toggleDayAccordion(this)">
                <div class="day-title">
                  <span class="subproject-icon" style="margin-right: 4px;">${{ICONS.hash}}</span>
                  ${{titleHtml}}
                  <span class="day-count-badge">${{tasks.length}} task${{tasks.length === 1 ? '' : 's'}}</span>
                </div>
                <span class="day-toggle-icon">▼</span>
              </div>
              <div class="day-content" style="padding: 10px 14px;">
                ${{renderTasksWithSections(tasks, true)}}
              </div>
            </div>
          `;
        }}
        container.innerHTML = html;
        updateDayToggleButton();
        return;
      }}

      // Mode 2: By Hierarchy (Category › Parent Project › Subprojects)
      const byCategory = {{}};
      filteredRecords.forEach(r => {{
        const cat = getRecordCategory(r);
        const topProj = r.top_level_project || 'Uncategorized';
        if (!byCategory[cat]) byCategory[cat] = {{}};
        if (!byCategory[cat][topProj]) byCategory[cat][topProj] = [];
        byCategory[cat][topProj].push(r);
      }});

      const catOrder = ['work', 'personal', 'others'];
      const extraCats = Object.keys(byCategory).filter(c => !catOrder.includes(c)).sort();
      const allCats = [...catOrder.filter(c => byCategory[c]), ...extraCats];

      let totalParents = 0;
      allCats.forEach(c => {{ totalParents += Object.keys(byCategory[c]).length; }});

      if (summaryEl) {{
        summaryEl.textContent = `Showing ${{allCats.length}} categories · ${{totalParents}} parent projects (${{filteredRecords.length}} tasks)`;
      }}

      let html = '';
      for (const cat of allCats) {{
        const catTitle = cat === 'work' ? '💼 Work' : cat === 'personal' ? '👤 Personal' : cat === 'others' ? '📦 Others / Unassigned' : cat.toUpperCase();
        const parentMap = byCategory[cat];
        let catTaskCount = 0;
        Object.values(parentMap).forEach(list => {{ catTaskCount += list.length; }});

        html += `
          <div class="category-block" style="margin-bottom: 20px;">
            <div class="category-block-header" style="display: flex; align-items: center; justify-content: space-between; padding: 6px 4px; margin-bottom: 8px; border-bottom: 2px solid var(--border);">
              <span style="font-size: 13px; font-weight: 700; color: var(--accent); letter-spacing: 0.3px;">${{escapeHtml(catTitle)}}</span>
              <span class="badge" style="background-color: var(--bg-card-subtle); color: var(--text-dim); font-size: 11px;">${{catTaskCount}} task${{catTaskCount === 1 ? '' : 's'}}</span>
            </div>
        `;

        const sortedParents = Object.keys(parentMap).sort((a, b) => {{
          const diff = parentMap[b].length - parentMap[a].length;
          if (diff !== 0) return diff;
          return a.localeCompare(b);
        }});

        for (const proj of sortedParents) {{
          const tasks = parentMap[proj];
          const collapsedCls = isAllDaysCollapsed ? ' collapsed' : '';

          html += `
            <div class="day-group${{collapsedCls}}">
              <div class="day-header" onclick="toggleDayAccordion(this)">
                <div class="day-title">
                  <span class="top-project-icon" style="margin-right: 4px;">${{ICONS.layers}}</span>
                  <span style="font-weight: 700;">${{escapeHtml(proj)}}</span>
                  <span class="day-count-badge">${{tasks.length}} task${{tasks.length === 1 ? '' : 's'}}</span>
                </div>
                <span class="day-toggle-icon">▼</span>
              </div>
              <div class="day-content" style="padding: 10px 14px;">
                ${{renderSubprojectHierarchy(tasks, true)}}
              </div>
            </div>
          `;
        }}

        html += '</div>';
      }}
      container.innerHTML = html;
      updateDayToggleButton();
    }}

    // Render Table View
    function renderTableView() {{
      const tbody = document.getElementById('table-body');
      if (!tbody) return;

      if (filteredRecords.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No records found</td></tr>';
        return;
      }}

      // Apply current sort
      const sorted = [...filteredRecords].sort((a, b) => {{
        const valA = (a[currentSortColumn] || '').toString();
        const valB = (b[currentSortColumn] || '').toString();
        return currentSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }});

      let rows = '';
      sorted.slice(0, 250).forEach(r => {{
        const tags = (r.labels || []).map(l => `@${{l.replace(/^@/, '')}}`).join(', ');

        let taskCellContent = '';
        if (r.task_levels && r.task_levels.length > 1) {{
          const ancestors = r.task_levels.slice(0, -1).map(l => renderMarkdown(l, true)).join(' › ');
          const leaf = renderMarkdown(r.task_levels[r.task_levels.length - 1], true);
          taskCellContent = `
            <div style="font-size: 11px; color: var(--text-dim); margin-bottom: 2px;">${{ancestors}}</div>
            <strong>${{leaf}}</strong>
          `;
        }} else {{
          taskCellContent = `<strong>${{renderMarkdown(r.task_path || '-', true)}}</strong>`;
        }}

        const projDisplay = (r.project_levels && r.project_levels.length > 0)
          ? r.project_levels.join(' › ')
          : (r.project_path || '-');

        rows += `
          <tr>
            <td style="font-family: monospace;">${{escapeHtml(r.date)}} ${{escapeHtml(r.time || '')}}</td>
            <td><span class="badge" style="background:var(--bg-hover);">${{escapeHtml(r.top_level_project || '-')}}</span></td>
            <td>${{escapeHtml(projDisplay)}}${{r.section ? ` <span class="section-tag">${{ICONS.section}} ${{renderMarkdown(r.section, true)}}</span>` : ''}}</td>
            <td>
              ${{taskCellContent}}
              ${{r.description ? `<div style="font-size:11px; color:var(--text-muted); margin-top:3px;">${{renderMarkdown(r.description)}}</div>` : ''}}
            </td>
            <td>${{r.priority && r.priority.toLowerCase() !== 'p4' ? `<span class="badge badge-${{r.priority.toLowerCase()}}">${{r.priority.toUpperCase()}}</span>` : '-'}}</td>
            <td>${{escapeHtml(tags || '-')}}</td>
            <td>${{r.due_status && r.due_status !== 'undated' ? `<span class="badge badge-${{r.due_status}}">${{escapeHtml(r.due_variance || r.due_date)}}</span>` : '-'}}</td>
          </tr>
        `;
      }});

      tbody.innerHTML = rows;
    }}

    function sortTable(column) {{
      if (currentSortColumn === column) {{
        currentSortAsc = !currentSortAsc;
      }} else {{
        currentSortColumn = column;
        currentSortAsc = false;
      }}
      renderTableView();
    }}

    // Interactive SVG Velocity Chart
    function renderTimelineChart() {{
      const svg = document.getElementById('timeline-chart');
      const tooltip = document.getElementById('chart-tooltip');
      if (!svg) return;

      const dateFrom = document.getElementById('date-from') ? document.getElementById('date-from').value : '';
      const dateTo = document.getElementById('date-to') ? document.getElementById('date-to').value : '';

      const chartPool = rawRecords.filter(r => {{
        if (dateFrom && r.date && r.date < dateFrom) return false;
        if (dateTo && r.date && r.date > dateTo) return false;
        if ((dateFrom || dateTo) && !r.date) return false;
        return true;
      }});

      const dateCounts = {{}};
      chartPool.forEach(r => {{
        if (r.date) dateCounts[r.date] = (dateCounts[r.date] || 0) + 1;
      }});

      const dates = Object.keys(dateCounts).sort();
      if (dates.length === 0) {{
        svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="var(--text-muted)" font-size="12">No activity data</text>';
        return;
      }}

      const maxVal = Math.max(...Object.values(dateCounts), 1);
      const width = svg.clientWidth || 600;
      const height = svg.clientHeight || 180;
      const padLeft = 30;
      const padBottom = 25;
      const padTop = 15;
      const padRight = 15;
      const chartW = width - padLeft - padRight;
      const chartH = height - padTop - padBottom;

      const barWidth = Math.max(3, (chartW / dates.length) - 2);

      let svgContent = '';
      // Grid line
      svgContent += `<line x1="${{padLeft}}" y1="${{height - padBottom}}" x2="${{width - padRight}}" y2="${{height - padBottom}}" stroke="var(--border)" stroke-width="1" />`;

      dates.forEach((d, idx) => {{
        const count = dateCounts[d];
        const h = (count / maxVal) * chartH;
        const x = padLeft + (idx * (chartW / dates.length));
        const y = height - padBottom - h;
        const isSelected = activeDayFilter === d;

        svgContent += `
          <rect x="${{x}}" y="${{y}}" width="${{barWidth}}" height="${{h}}"
                rx="2"
                fill="${{isSelected ? '#ec4899' : 'var(--accent)'}}"
                opacity="${{isSelected ? '1' : '0.85'}}"
                style="cursor: pointer; transition: opacity 0.15s ease;"
                onmouseover="showChartTooltip(event, '${{d}}', ${{count}})"
                onmousemove="moveChartTooltip(event)"
                onmouseout="hideChartTooltip()"
                onclick="filterByDay('${{d}}')" />
        `;
      }});

      svg.innerHTML = svgContent;
    }}

    function showChartTooltip(evt, date, count) {{
      const tooltip = document.getElementById('chart-tooltip');
      if (!tooltip) return;
      tooltip.innerHTML = `<strong>${{date}}</strong>: ${{count}} task${{count === 1 ? '' : 's'}}`;
      tooltip.style.left = `${{evt.clientX}}px`;
      tooltip.style.top = `${{evt.clientY}}px`;
      tooltip.style.opacity = '1';
    }}

    function moveChartTooltip(evt) {{
      const tooltip = document.getElementById('chart-tooltip');
      if (!tooltip) return;
      tooltip.style.left = `${{evt.clientX}}px`;
      tooltip.style.top = `${{evt.clientY}}px`;
    }}

    function hideChartTooltip() {{
      const tooltip = document.getElementById('chart-tooltip');
      if (tooltip) tooltip.style.opacity = '0';
    }}

    function filterByDay(date) {{
      if (activeDayFilter === date) {{
        activeDayFilter = null;
      }} else {{
        activeDayFilter = date;
      }}
      applyFilters();
    }}

    // Project Share Bars
    function renderProjectBars() {{
      const container = document.getElementById('project-bars');
      if (!container) return;

      const projCounts = {{}};
      filteredRecords.forEach(r => {{
        const p = getRecordProject(r);
        projCounts[p] = (projCounts[p] || 0) + 1;
      }});

      const total = filteredRecords.length || 1;
      const sorted = Object.entries(projCounts).sort((a, b) => b[1] - a[1]);

      let html = '';
      sorted.slice(0, 8).forEach(([proj, count]) => {{
        const pct = Math.round((count / total) * 100);
        html += `
          <div>
            <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 2px;">
              <span style="font-weight: 600; cursor: pointer; color: var(--accent);" onclick="filterByProject('${{escapeHtml(proj)}}')">${{escapeHtml(proj)}}</span>
              <span style="color: var(--text-muted);">${{count}} (${{pct}}%)</span>
            </div>
            <div style="width: 100%; height: 6px; background-color: var(--bg-hover); border-radius: 3px; overflow: hidden;">
              <div style="width: ${{pct}}%; height: 100%; background: linear-gradient(90deg, var(--accent), #a855f7); border-radius: 3px;"></div>
            </div>
          </div>
        `;
      }});

      container.innerHTML = html || '<div class="empty-state" style="padding: 20px;">No projects</div>';
    }}

    function filterByProject(proj) {{
      ['category-filter', 'parent-project-filter'].forEach(id => {{
        const container = document.getElementById(id);
        if (container) {{
          container.querySelectorAll('.multiselect-options input[type="checkbox"]').forEach(cb => {{
            cb.checked = false;
          }});
          updateMultiselectButton(id);
        }}
      }});
      updateProjectDropdowns();

      const projContainer = document.getElementById('project-filter');
      if (projContainer) {{
        projContainer.querySelectorAll('.multiselect-options input[type="checkbox"]').forEach(cb => {{
          cb.checked = (cb.value === proj);
        }});
        updateMultiselectButton('project-filter');
      }}
      applyFilters();
    }}

    function escapeHtml(str) {{
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }}

    function renderMarkdown(str, inlineOnly = false) {{
      if (!str) return '';
      let text = String(str);

      // 1. Escape HTML entities
      text = escapeHtml(text);

      // 2. Protect inline code `...` using non-markdown sentinel tokens
      const tokens = [];
      text = text.replace(/`([^`]+)`/g, (match, code) => {{
        tokens.push(`<code>${{code}}</code>`);
        return `@@@MD_TOKEN_${{tokens.length - 1}}@@@`;
      }});

      // 3. Markdown links: [text](url)
      text = text.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, (match, linkText, url) => {{
        const trimmedUrl = url.trim();
        if (!/^(https?:|mailto:|#|\\/)/i.test(trimmedUrl)) {{
          return linkText;
        }}
        tokens.push(`<a href="${{trimmedUrl}}" target="_blank" rel="noopener noreferrer">${{linkText}}</a>`);
        return `@@@MD_TOKEN_${{tokens.length - 1}}@@@`;
      }});

      // 4. Autolink bare URLs: https://... or http://...
      text = text.replace(/(^|[\\s(])(https?:\\/\\/[^\\s)<>"]+)/g, (match, prefix, rawUrl) => {{
        let url = rawUrl;
        let trailingPunct = '';
        const punctMatch = url.match(/[.,;:!?]+$/);
        if (punctMatch) {{
          trailingPunct = punctMatch[0];
          url = url.slice(0, -trailingPunct.length);
        }}
        tokens.push(`<a href="${{url}}" target="_blank" rel="noopener noreferrer">${{url}}</a>`);
        return `${{prefix}}@@@MD_TOKEN_${{tokens.length - 1}}@@@${{trailingPunct}}`;
      }});

      // 5. Bold, Italic & Strikethrough (restricted to non-newline matches and non-space boundaries)
      text = text.replace(/\\*\\*(?!\\s)([^\\*\\n]+?)(?<!\\s)\\*\\*/g, '<strong>$1</strong>');
      text = text.replace(/__(?!\\s)([^_\\n]+?)(?<!\\s)__/g, '<strong>$1</strong>');
      text = text.replace(/(^|[^\\*])\\*(?!\\s)([^\\*\\n]+?)(?<!\\s)\\*/g, '$1<em>$2</em>');
      text = text.replace(/(^|[^\\w])_(?!\\s)([^_\\n]+?)(?<!\\s)_(?![\\w])/g, '$1<em>$2</em>');
      text = text.replace(/~~(?!\\s)([^~\\n]+?)(?<!\\s)~~/g, '<del>$1</del>');

      // 6. Restore protected tokens
      text = text.replace(/@@@MD_TOKEN_(\\d+)@@@/g, (match, index) => {{
        return tokens[parseInt(index, 10)] || match;
      }});

      const NL = String.fromCharCode(10);
      const CR = String.fromCharCode(13);
      const reAllNewlines = new RegExp('[' + CR + NL + ']+', 'g');
      const reNewline = new RegExp(CR + '?' + NL);

      if (inlineOnly) {{
        return text.replace(reAllNewlines, ' ');
      }}

      // 7. Multiline block rendering for descriptions (lists, paragraphs, line breaks)
      const lines = text.split(reNewline);
      const outBlocks = [];
      let inList = false;
      let listType = '';

      for (let i = 0; i < lines.length; i++) {{
        const line = lines[i];
        const ulMatch = line.match(/^\\s*[*-]\\s+(.+)$/);
        const olMatch = line.match(/^\\s*\\d+\\.\\s+(.+)$/);

        if (ulMatch) {{
          if (!inList || listType !== 'ul') {{
            if (inList) outBlocks.push(`</${{listType}}>`);
            outBlocks.push('<ul>');
            inList = true;
            listType = 'ul';
          }}
          outBlocks.push(`<li>${{ulMatch[1]}}</li>`);
        }} else if (olMatch) {{
          if (!inList || listType !== 'ol') {{
            if (inList) outBlocks.push(`</${{listType}}>`);
            outBlocks.push('<ol>');
            inList = true;
            listType = 'ol';
          }}
          outBlocks.push(`<li>${{olMatch[1]}}</li>`);
        }} else {{
          if (inList) {{
            outBlocks.push(`</${{listType}}>`);
            inList = false;
            listType = '';
          }}
          if (line.trim() === '') {{
            outBlocks.push('<div style="height: 4px;"></div>');
          }} else {{
            outBlocks.push(`<div>${{line}}</div>`);
          }}
        }}
      }}
      if (inList) {{
        outBlocks.push(`</${{listType}}>`);
      }}
      return outBlocks.join('');
    }}

    // Window Init
    window.addEventListener('DOMContentLoaded', () => {{
      initTheme();
      initFilterDropdowns();
      initDatePickers();
      applyFilters();
    }});

    window.addEventListener('resize', () => {{
      renderTimelineChart();
    }});
  </script>
</body>
</html>
"""


def export_html(
    records: List[Dict[str, Any]],
    output_path: str,
    include_labels: bool = True,
    include_descriptions: bool = True,
    include_priorities: bool = True,
    include_due_dates: bool = True,
    title: str = "Todoist Trace - Activity Dashboard",
    categories_config: Optional[Dict[str, Any]] = None,
) -> None:
    """Generate and write interactive HTML dashboard to disk."""
    html_content = generate_html(
        records,
        include_labels=include_labels,
        include_descriptions=include_descriptions,
        include_priorities=include_priorities,
        include_due_dates=include_due_dates,
        title=title,
        categories_config=categories_config,
    )
    dest = Path(output_path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html_content, encoding="utf-8")
