from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from ros2unbag.cli.render import console
from ros2unbag.core.progress import ProgressCallback


@contextmanager
def progress_task(description: str, total: int | None) -> Iterator[ProgressCallback]:
    """Render one transient Rich progress task for long-running CLI operations."""
    if not console.is_terminal:
        yield _noop_progress
        return

    normalized_total = total if total and total > 0 else None
    interrupted_snapshot: tuple[int, int | None] | None = None
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
            BarColumn(),
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
                progress.advance(task_id, amount)

            try:
                yield advance
            except KeyboardInterrupt:
                task = next(task for task in progress.tasks if task.id == task_id)
                interrupted_snapshot = (
                    int(task.completed),
                    int(task.total) if task.total is not None else None,
                )
                raise
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
