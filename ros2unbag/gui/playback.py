from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MAX_RENDERED_PLAYBACK_FRAMES = 300


@dataclass(slots=True)
class RenderedFrame:
    timestamp_ns: int
    pixmap: Any
    width: int
    height: int
    encoding: str
