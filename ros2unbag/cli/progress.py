from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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
    """Render one transient Rich progress task for long-running CLI operations."""
    if not console.is_terminal:
        yield _noop_progress
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


def _update_batch_size(total: int | None) -> int:
    if total is None:
        return 1_000
    if total < 5_000:
        return 1
    return max(10, total // 1_000)
