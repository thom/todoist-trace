"""
Modern, dependency-free terminal progress reporting for todoist-trace.
Features ANSI styling, Unicode spinners, progress bars, day-based sync tracking,
speed calculation, and ETA countdowns.
"""

import math
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def supports_color(stream=sys.stdout, force_no_color: bool = False) -> bool:
    """Check if the given stream supports ANSI color escape sequences."""
    if force_no_color or os.environ.get("NO_COLOR"):
        return False
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return True


def is_interactive_terminal(stream=sys.stdout, force_plain: bool = False) -> bool:
    """
    Check if the stream is an interactive terminal that properly supports
    in-place row redrawing with carriage returns (\r).
    Disables in-place redrawing in Antigravity, CI, IDE logs, and non-ttys.
    """
    if force_plain:
        return False
    if os.environ.get("ANTIGRAVITY_AGENT"):
        return False
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return False
    if os.environ.get("INSIDE_EMACS") or os.environ.get("TERM") in ("dumb", "unknown", ""):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


class Style:
    """ANSI color and formatting codes with auto-disabling fallback."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def blue(self, text: str) -> str:
        return self._wrap("34", text)

    def magenta(self, text: str) -> str:
        return self._wrap("35", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)


def format_duration(seconds: float) -> str:
    """Format duration in seconds to MM:SS or HH:MM:SS."""
    sec = max(0, int(round(seconds)))
    if sec >= 3600:
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    m = sec // 60
    s = sec % 60
    return f"{m:02d}:{s:02d}"


def render_progress_bar(percentage: float, width: int = 20) -> str:
    """
    Render a clean unicode progress bar.
    Example: [██████████░░░░░░░░░░]
    """
    pct = max(0.0, min(100.0, percentage))
    if width <= 0:
        return ""
    filled_len = int(round(width * pct / 100.0))
    empty_len = width - filled_len
    return "█" * filled_len + "░" * empty_len


def parse_iso_timestamp(iso_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 timestamp string into datetime."""
    if not iso_str:
        return None
    cleaned = iso_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


class FancyProgressReporter:
    """
    High-performance, visual progress reporter for Todoist operations.
    Adapts automatically to TTY interactivity, terminal width, and quiet mode.
    """

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    CHECKMARK = "✔"
    CROSS = "✖"

    def __init__(
        self,
        quiet: bool = False,
        no_color: bool = False,
        plain: bool = False,
        stream=sys.stdout,
    ):
        self.quiet = quiet
        self.plain = plain
        self.stream = stream
        self.color_enabled = supports_color(stream, force_no_color=no_color)
        self.is_tty = is_interactive_terminal(stream, force_plain=plain) and not self.quiet
        self.style = Style(self.color_enabled)
        self.spinner_idx = 0
        self._last_line_len = 0
        self._last_update_time = 0.0

        # Sync state
        self._sync_start_time: Optional[float] = None
        self._sync_total_days: Optional[int] = None
        self._sync_dt_end: Optional[datetime] = None
        self._sync_dt_start: Optional[datetime] = None
        self._sync_total_seconds: Optional[float] = None
        self._last_milestone_events = 0
        self._last_proj_count = 0

    def _get_term_cols(self) -> int:
        return shutil.get_terminal_size((80, 24)).columns

    def _write_live_line(self, line: str) -> None:
        """Write an in-place updating line using carriage return in interactive TTY mode."""
        if self.quiet:
            return
        if self.is_tty:
            cols = self._get_term_cols()
            if len(line) > cols - 1:
                line = line[: cols - 4] + "..."
            self.stream.write(f"\r\033[K{line}")
            self.stream.flush()
        self._last_line_len = len(line)

    def _end_live_line(self, final_line: Optional[str] = None) -> None:
        """Finish an in-place line and advance to the next line."""
        if self.quiet:
            return
        if self.is_tty:
            if final_line is not None:
                self.stream.write(f"\r\033[K{final_line}\n")
            else:
                self.stream.write("\n")
            self.stream.flush()
        elif final_line is not None:
            self.stream.write(f"{final_line}\n")
            self.stream.flush()

    def print_text(self, text: str) -> None:
        """Print regular text if not quiet."""
        if not self.quiet:
            self.stream.write(f"{text}\n")
            self.stream.flush()

    # -------------------------------------------------------------------------
    # Banner
    # -------------------------------------------------------------------------
    def print_banner(
        self,
        date_range_desc: str,
        timezone_desc: str,
        cache_desc: str,
        category_desc: str = "all",
        format_desc: str = "csv",
    ) -> None:
        """Render a sleek boxed metadata header."""
        if self.quiet:
            return

        box_width = min(68, max(52, self._get_term_cols() - 2))
        inner_width = box_width - 4

        def row(label: str, val: str) -> str:
            label_styled = self.style.dim(f"{label:<10}: ")
            val_clean = val
            combined_raw = f"{label:<10}: {val_clean}"
            padding = " " * max(0, inner_width - len(combined_raw))
            return f"│ {label_styled}{self.style.bold(val_clean)}{padding} │"

        title = " todoist-trace "
        top_dash_len = box_width - len(title) - 3
        top = f"╭─{self.style.cyan(title)}{'─' * max(0, top_dash_len)}╮"
        bottom = f"╰{'─' * (box_width - 2)}╯"

        self.stream.write(f"\n{self.style.dim(top)}\n")
        self.stream.write(f"{row('Range', date_range_desc)}\n")
        self.stream.write(f"{row('Timezone', timezone_desc)}\n")
        self.stream.write(f"{row('Category', category_desc)}\n")
        self.stream.write(f"{row('Format', format_desc)}\n")
        self.stream.write(f"{row('Cache', cache_desc)}\n")
        self.stream.write(f"{self.style.dim(bottom)}\n\n")
        self.stream.flush()

    # -------------------------------------------------------------------------
    # Phase 1: Projects
    # -------------------------------------------------------------------------
    def start_projects(self, cached: bool = False, count: int = 0) -> None:
        if self.quiet:
            return
        if cached:
            msg = (
                f"{self.style.cyan('[1/4]')} {self.style.green(self.CHECKMARK)} "
                f"Projects: {self.style.bold(str(count))} cached projects loaded"
            )
            self.print_text(msg)
        elif self.is_tty:
            self._write_live_line(
                f"{self.style.cyan('[1/4]')} {self.style.yellow(self.SPINNER_FRAMES[0])} "
                "Connecting to Todoist API..."
            )
        else:
            self.print_text(f"{self.style.cyan('[1/4]')} Connecting to Todoist API...")

    def update_projects(self, active_count: int, archived_count: int = 0) -> None:
        if self.quiet:
            return
        if self.is_tty:
            self.spinner_idx = (self.spinner_idx + 1) % len(self.SPINNER_FRAMES)
            sp = self.style.yellow(self.SPINNER_FRAMES[self.spinner_idx])
            line = (
                f"{self.style.cyan('[1/4]')} {sp} Fetching projects... "
                f"{self.style.bold(str(active_count))} active"
                + (f", {self.style.bold(str(archived_count))} archived" if archived_count > 0 else "")
            )
            self._write_live_line(line)
        else:
            total = active_count + archived_count
            if total - self._last_proj_count >= 100:
                self._last_proj_count = total
                self.print_text(f"  → Fetched {active_count} active projects...")

    def finish_projects(self, active_count: int, archived_count: int) -> None:
        if self.quiet:
            return
        total = active_count + archived_count
        final = (
            f"{self.style.cyan('[1/4]')} {self.style.green(self.CHECKMARK)} "
            f"Projects: {self.style.bold(str(total))} retrieved "
            f"({active_count} active, {archived_count} archived)"
        )
        self._end_live_line(final)

    # -------------------------------------------------------------------------
    # Phase 2: Activity Sync
    # -------------------------------------------------------------------------
    def start_sync(
        self,
        start_iso: Optional[str],
        end_iso: Optional[str],
        total_cache_count: int = 0,
        fully_cached: bool = False,
    ) -> None:
        if self.quiet:
            return
        if fully_cached:
            final = (
                f"{self.style.cyan('[2/4]')} {self.style.green(self.CHECKMARK)} "
                f"Sync: Date range fully cached ({self.style.bold(str(total_cache_count))} events in SQLite). Zero API calls."
            )
            self.print_text(final)
            return

        self._sync_start_time = time.time()
        self._last_milestone_events = 0
        self._sync_dt_end = parse_iso_timestamp(end_iso) or datetime.now(timezone.utc)
        self._sync_dt_start = parse_iso_timestamp(start_iso)

        if self._sync_dt_start:
            self._sync_total_seconds = max(1.0, (self._sync_dt_end - self._sync_dt_start).total_seconds())
            self._sync_total_days = max(1, (self._sync_dt_end.date() - self._sync_dt_start.date()).days + 1)
        else:
            self._sync_total_seconds = None
            self._sync_total_days = None

        desc_s = start_iso[:10] if start_iso else "genesis"
        desc_e = end_iso[:10] if end_iso else "now"
        span_str = f" ({self._sync_total_days} days)" if self._sync_total_days else ""
        header = f"{self.style.cyan('[2/4]')} Syncing activities: {desc_s} → {desc_e}{span_str}"
        self.print_text(header)

    def update_sync(self, events_count: int, oldest_event_date: Optional[str] = None) -> None:
        if self.quiet:
            return

        self.spinner_idx = (self.spinner_idx + 1) % len(self.SPINNER_FRAMES)
        sp = self.style.yellow(self.SPINNER_FRAMES[self.spinner_idx])

        # Calculate time & speed
        now = time.time()
        elapsed = max(0.001, (now - self._sync_start_time) if self._sync_start_time else 0.001)
        speed = events_count / elapsed
        speed_str = f"{int(speed)} tasks/s"

        # Calculate day-based percentage & ETA
        pct: Optional[float] = None
        days_str = ""
        eta_str = ""

        if oldest_event_date and self._sync_dt_end:
            dt_curr = parse_iso_timestamp(oldest_event_date)
            if dt_curr:
                curr_date = dt_curr.date()
                if self._sync_dt_start and self._sync_total_seconds and self._sync_total_days:
                    elapsed_sec = max(0.0, (self._sync_dt_end - dt_curr).total_seconds())
                    pct = min(100.0, max(0.0, (elapsed_sec / self._sync_total_seconds) * 100.0))
                    days_done = max(1, min(self._sync_total_days, (self._sync_dt_end.date() - curr_date).days + 1))
                    days_str = f"Day {days_done}/{self._sync_total_days}"
                    if pct > 1.0:
                        est_total = elapsed / (pct / 100.0)
                        rem = max(0, est_total - elapsed)
                        eta_str = f"ETA {format_duration(rem)}"
                else:
                    days_done = max(1, (self._sync_dt_end.date() - curr_date).days + 1)
                    days_str = f"{days_done} days traversed"

        if self.is_tty:
            # Interactive fancy bar
            cols = self._get_term_cols()
            pct_val = pct if pct is not None else 0.0
            pct_text = f"{pct_val:5.1f}%" if pct is not None else "  ---%"
            tasks_text = f"{events_count:,} tasks"

            # Dynamic bar sizing
            info_parts = [p for p in [days_str, tasks_text, speed_str, eta_str] if p]
            info_suffix = " • ".join(info_parts)
            fixed_len = 16 + len(pct_text) + len(info_suffix)  # spinner, spacing, brackets
            avail_bar = max(0, min(24, cols - fixed_len))

            bar_str = f"[{self.style.cyan(render_progress_bar(pct_val, avail_bar))}] " if avail_bar >= 6 else ""
            line = f"      {sp} {bar_str}{self.style.bold(pct_text)} • {info_suffix}"
            self._write_live_line(line)
        else:
            # Clean milestone line per batch/page in non-interactive/Antigravity
            pct_display = f"{pct:.1f}% • " if pct is not None else ""
            day_display = f"{days_str} • " if days_str else ""
            eta_display = f" • {eta_str}" if eta_str else ""
            self.print_text(f"  → {events_count:,} activities synced ({pct_display}{day_display}{speed_str}{eta_display})")

    def finish_sync(
        self,
        new_events_count: int,
        total_cache_count: int,
        elapsed_sec: Optional[float] = None,
    ) -> None:
        if self.quiet:
            return
        dur = elapsed_sec if elapsed_sec is not None else (
            (time.time() - self._sync_start_time) if self._sync_start_time else 0.0
        )
        dur_str = format_duration(dur)
        speed = int(new_events_count / max(0.001, dur)) if dur > 0 else 0
        speed_str = f", {speed} tasks/s" if speed > 0 else ""

        final = (
            f"{self.style.cyan('[2/4]')} {self.style.green(self.CHECKMARK)} "
            f"Sync complete: {self.style.bold(f'{new_events_count:,}')} new activities synced "
            f"({total_cache_count:,} total in SQLite) in {dur_str}{speed_str}"
        )
        self._end_live_line(final)

    # -------------------------------------------------------------------------
    # Phase 3: Task & Project Hierarchies
    # -------------------------------------------------------------------------
    def start_resolve(self, total_records: int) -> None:
        if self.quiet:
            return
        self._resolve_start_time = time.time()
        self._resolve_total = total_records
        self._resolve_last_milestone = 0
        if total_records == 0:
            final = (
                f"{self.style.cyan('[3/4]')} {self.style.green(self.CHECKMARK)} "
                "Task hierarchies: 0 records to resolve."
            )
            self.print_text(final)
            return
        if self.is_tty:
            self._write_live_line(
                f"{self.style.cyan('[3/4]')} {self.style.yellow(self.SPINNER_FRAMES[0])} "
                f"Resolving task hierarchies (0 / {total_records:,})..."
            )
        else:
            self.print_text(f"{self.style.cyan('[3/4]')} Resolving task hierarchies ({total_records:,} records)...")

    def update_resolve(self, current: int, total: int) -> None:
        if self.quiet or total <= 0:
            return
        pct = (current / total) * 100.0
        self.spinner_idx = (self.spinner_idx + 1) % len(self.SPINNER_FRAMES)
        sp = self.style.yellow(self.SPINNER_FRAMES[self.spinner_idx])

        if self.is_tty:
            now = time.time()
            if now - self._last_update_time < 0.08 and current != total:
                return
            self._last_update_time = now
            cols = self._get_term_cols()
            pct_text = f"{pct:5.1f}%"
            counts_text = f"{current:,} / {total:,}"
            avail_bar = max(0, min(20, cols - 45))
            bar_str = f"[{self.style.cyan(render_progress_bar(pct, avail_bar))}] " if avail_bar >= 6 else ""
            line = f"      {sp} {bar_str}{self.style.bold(pct_text)} ({counts_text})"
            self._write_live_line(line)
        else:
            if current - self._resolve_last_milestone >= 1000:
                self._resolve_last_milestone = current
                self.print_text(f"  → Resolving hierarchies: {current:,} / {total:,} ({pct:.1f}%)...")

    def finish_resolve(self, total: int) -> None:
        if self.quiet or total == 0:
            return
        dur = max(0.001, time.time() - getattr(self, "_resolve_start_time", time.time()))
        dur_str = format_duration(dur)
        final = (
            f"{self.style.cyan('[3/4]')} {self.style.green(self.CHECKMARK)} "
            f"Task hierarchies: {self.style.bold(f'{total:,}')} records resolved in {dur_str}"
        )
        self._end_live_line(final)

    # -------------------------------------------------------------------------
    # Phase 4: Export Complete
    # -------------------------------------------------------------------------
    def finish_export(
        self,
        output_path: str,
        matched_count: int,
        total_count: int,
        out_fmt: str,
        style_desc: str = "",
    ) -> None:
        if self.quiet:
            return
        fmt_upper = out_fmt.upper()
        style_suffix = f" ({style_desc})" if style_desc else ""
        final = (
            f"{self.style.cyan('[4/4]')} {self.style.green(self.CHECKMARK)} "
            f"Export complete: {self.style.bold(output_path)} "
            f"({self.style.bold(f'{matched_count:,}')} of {total_count:,} records matched, {fmt_upper}{style_suffix})"
        )
        self.print_text(f"\n{final}")
