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
            TimeRemainingColumn(),
        )

    with Progress(
        *columns,
        console=console,
        transient=True,
        refresh_per_second=8,
    ) as progress:
        task_id = progress.add_task(description, total=normalized_total)

        def advance(amount: int = 1) -> None:
            progress.advance(task_id, amount)

        yield advance


def _noop_progress(_amount: int = 1) -> None:
    return None
