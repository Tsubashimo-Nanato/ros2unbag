from __future__ import annotations

from time import perf_counter
from typing import Any


class GuiProgressContext:
    def __init__(
        self,
        owner: Any,
        progress_dialog: Any,
        description: str,
        total: int | None,
    ) -> None:
        self.owner = owner
        self.progress_dialog = progress_dialog
        self.description = description
        self.total = total
        self.count = 0
        self._last_update = 0.0

    def __enter__(self) -> Any:
        self.owner._start_progress(self.description, self.total)
        if self.total is None or self.total <= 0:
            self.progress_dialog.setRange(0, 0)
        else:
            self.progress_dialog.setRange(0, self.total)
            self.progress_dialog.setValue(0)
        self.progress_dialog.setLabelText(self.description)
        return self._advance

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.owner._finish_progress()

    def _advance(self, amount: int) -> None:
        self.count += amount
        now = perf_counter()
        if not self._should_update(now):
            return

        self._last_update = now
        self.owner._set_progress(self.description, self.count, self.total)
        if self.total is None or self.total <= 0:
            self.progress_dialog.setRange(0, 0)
        else:
            self.progress_dialog.setRange(0, self.total)
            self.progress_dialog.setValue(min(self.count, self.total))
        self.progress_dialog.setLabelText(
            f"{self.description} ({self.count}"
            + (f"/{self.total})" if self.total else ")")
        )
        self.owner.QtWidgets.QApplication.processEvents()
        if self.progress_dialog.wasCanceled():
            raise RuntimeError("Operation cancelled")

    def _should_update(self, now: float) -> bool:
        return (
            self.count == 1
            or self.total is not None and self.count >= self.total
            or now - self._last_update >= 0.05
        )
