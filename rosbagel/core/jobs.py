from __future__ import annotations

from dataclasses import dataclass
from threading import Event


class CancelledError(RuntimeError):
    """Raised when a user-cancellable background operation is stopped."""


@dataclass(slots=True)
class CancellationToken:
    """Small cancellation primitive shared by GUI workers and core loops."""

    _event: Event

    @classmethod
    def create(cls) -> "CancellationToken":
        return cls(Event())

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise CancelledError("Operation was cancelled.")
