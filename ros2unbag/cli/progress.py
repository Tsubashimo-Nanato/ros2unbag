from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
import shutil
import sys
from time import monotonic

from rich.progress import (
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.text import Text

from ros2unbag.cli.render import console
from ros2unbag.core.progress import ProgressCallback


class BlockBarColumn(ProgressColumn):
    """Render a fixed-width block progress bar instead of a dashed fallback."""

    def __init__(self, width: int = 28) -> None:
        super().__init__()
        self.width = width

    def render(self, task: object) -> Text:
        total = getattr(task, "total", None)
        completed = float(getattr(task, "completed", 0) or 0)
        if not total:
            filled = 0
        else:
            ratio = max(0.0, min(1.0, completed / float(total)))
            filled = int(round(ratio * self.width))
        bar = "\u2588" * filled + "\u2591" * (self.width - filled)
        return Text(bar, style="progress.bar.complete")


@contextmanager
def progress_task(description: str, total: int | None) -> Iterator[ProgressCallback]:
    """Render one transient progress task for long-running CLI operations."""
    if not console.is_terminal:
        yield _noop_progress
        return
    if _should_use_plain_progress():
        with _plain_progress_task(description, total) as advance:
            yield advance
        return

    normalized_total = total if total and total > 0 else None
    interrupted_snapshot: tuple[int, int | None] | None = None
    pending = 0
    last_update = monotonic()
    update_every = _update_batch_size(normalized_total)
    update_interval_sec = 0.05
    columns: tuple[object, ...]
    if normalized_total is None:
        columns = (
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        )
    else:
        columns = (
            TextColumn("[progress.description]{task.description}"),
            BlockBarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TextColumn("[dim]eta[/dim]"),
            TimeRemainingColumn(),
        )

    try:
        with Progress(
            *columns,
            console=console,
            transient=True,
            refresh_per_second=8,
        ) as progress:
            task_id = progress.add_task(description, total=normalized_total)

            def advance(amount: int = 1) -> None:
                nonlocal last_update, pending
                pending += amount
                now = monotonic()
                if pending >= update_every or now - last_update >= update_interval_sec:
                    progress.advance(task_id, pending)
                    pending = 0
                    last_update = now

            def flush_pending() -> None:
                nonlocal pending, last_update
                if pending:
                    progress.advance(task_id, pending)
                    pending = 0
                    last_update = monotonic()

            try:
                yield advance
            except KeyboardInterrupt:
                flush_pending()
                task = next(task for task in progress.tasks if task.id == task_id)
                interrupted_snapshot = (
                    int(task.completed),
                    int(task.total) if task.total is not None else None,
                )
                raise
            finally:
                flush_pending()
    except KeyboardInterrupt:
        if interrupted_snapshot is not None:
            completed, task_total = interrupted_snapshot
            if task_total is None:
                console.print(f"[yellow]Interrupted:[/yellow] {description} after {completed} steps.")
            else:
                console.print(
                    f"[yellow]Interrupted:[/yellow] {description} at {completed}/{task_total}."
                )
        raise


def _noop_progress(_amount: int = 1) -> None:
    return None


@contextmanager
def _plain_progress_task(description: str, total: int | None) -> Iterator[ProgressCallback]:
    """Single-line progress fallback for consoles where Rich Live floods output."""
    normalized_total = total if total and total > 0 else None
    completed = 0
    pending = 0
    last_update = monotonic()
    last_line_length = 0
    update_every = _update_batch_size(normalized_total)
    update_interval_sec = 0.20
    interrupted_snapshot: tuple[int, int | None] | None = None

    def render(force: bool = False) -> None:
        nonlocal last_line_length, last_update
        now = monotonic()
        if not force and now - last_update < update_interval_sec:
            return
        line = _plain_progress_line(
            description,
            completed,
            normalized_total,
            elapsed_sec=now - start_time,
            width=_terminal_width(),
        )
        padding = " " * max(0, last_line_length - len(line))
        sys.stderr.write("\r" + line + padding)
        sys.stderr.flush()
        last_line_length = len(line)
        last_update = now

    def flush_pending(force_render: bool = False) -> None:
        nonlocal completed, pending
        if pending:
            completed += pending
            pending = 0
        render(force=force_render)

    start_time = monotonic()
    try:
        render(force=True)

        def advance(amount: int = 1) -> None:
            nonlocal pending
            pending += amount
            if pending >= update_every:
                flush_pending()
            else:
                render()

        try:
            yield advance
        except KeyboardInterrupt:
            flush_pending(force_render=True)
            interrupted_snapshot = (completed, normalized_total)
            raise
        finally:
            flush_pending(force_render=True)
            sys.stderr.write("\r" + (" " * last_line_length) + "\r")
            sys.stderr.flush()
    except KeyboardInterrupt:
        if interrupted_snapshot is not None:
            completed_count, task_total = interrupted_snapshot
            if task_total is None:
                console.print(f"[yellow]Interrupted:[/yellow] {description} after {completed_count} steps.")
            else:
                console.print(
                    f"[yellow]Interrupted:[/yellow] {description} at {completed_count}/{task_total}."
                )
        raise


def _plain_progress_line(
    description: str,
    completed: int,
    total: int | None,
    *,
    elapsed_sec: float,
    width: int,
) -> str:
    width = max(20, width)
    elapsed = _format_duration(elapsed_sec)
    if total:
        ratio = max(0.0, min(1.0, completed / total))
        percent = f"{ratio * 100:5.1f}%"
        count = f"{completed}/{total}"
        eta = _format_duration((elapsed_sec / completed) * (total - completed)) if completed else "--:--"
        suffix = f" {percent} {count} elapsed {elapsed} eta {eta}"
    else:
        suffix = f" {completed} elapsed {elapsed}"

    max_bar_width = 24
    min_bar_width = 8
    max_description = max(8, width - max_bar_width - len(suffix) - 3)
    short_description = _middle_truncate(description, max_description)
    bar_width = max(min_bar_width, min(max_bar_width, width - len(short_description) - len(suffix) - 3))
    filled = 0 if not total else int(round(max(0.0, min(1.0, completed / total)) * bar_width))
    block = _safe_progress_char("\u2588", fallback="#")
    bar = block * filled + " " * (bar_width - filled)
    line = f"{short_description} {bar}{suffix}"
    if len(line) > width:
        line = _middle_truncate(line, width)
    return line


def _middle_truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    if max_length <= 3:
        return text[:max_length]
    head = max(1, (max_length - 3) // 2)
    tail = max_length - 3 - head
    if tail <= 0:
        return text[:head] + "..."
    return text[:head] + "..." + text[-tail:]


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _terminal_width() -> int:
    try:
        return shutil.get_terminal_size((80, 20)).columns
    except Exception:
        return 80


def _should_use_plain_progress() -> bool:
    if os.environ.get("ROS2UNBAG_PLAIN_PROGRESS"):
        return True
    return os.name == "nt" or bool(getattr(console, "legacy_windows", False))


def _safe_progress_char(char: str, *, fallback: str) -> str:
    encoding = getattr(sys.stderr, "encoding", None) or "utf-8"
    try:
        char.encode(encoding)
    except UnicodeEncodeError:
        return fallback
    return char


def _update_batch_size(total: int | None) -> int:
    if total is None:
        return 1_000
    if total < 5_000:
        return 1
    return max(10, total // 1_000)
