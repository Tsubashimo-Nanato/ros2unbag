from __future__ import annotations

from collections.abc import Callable

ProgressCallback = Callable[[int], None]


def advance_progress(progress_callback: ProgressCallback | None, amount: int = 1) -> None:
    if progress_callback is not None:
        progress_callback(amount)
