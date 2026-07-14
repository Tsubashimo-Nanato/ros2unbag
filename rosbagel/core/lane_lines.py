from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from math import isfinite
from typing import Iterable

from .jobs import CancellationToken
from .models import TopicInfo
from .point_cloud import iter_point_cloud_rows
from .progress import ProgressCallback, advance_progress


LANE_ROLES = ("center", "left", "right")
LANE_TOPIC_ROOT = "/lane_line_publisher/lane_lines/"


@dataclass(frozen=True, slots=True)
class LanePoint:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class LaneFrame:
    timestamp_ns: int
    points: tuple[LanePoint, ...]


@dataclass(frozen=True, slots=True)
class LaneBounds:
    min_x: float
    max_x: float
    min_y: float
    max_y: float


@dataclass(slots=True)
class LaneSeries:
    role: str
    topic: str
    frames: list[LaneFrame]
    _timestamps_ns: list[int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._timestamps_ns = [frame.timestamp_ns for frame in self.frames]

    def nearest_frame(self, timestamp_ns: int) -> LaneFrame | None:
        if not self.frames:
            return None
        index = bisect_left(self._timestamps_ns, timestamp_ns)
        if index <= 0:
            return self.frames[0]
        if index >= len(self.frames):
            return self.frames[-1]
        before = self.frames[index - 1]
        after = self.frames[index]
        before_delta = abs(before.timestamp_ns - timestamp_ns)
        after_delta = abs(after.timestamp_ns - timestamp_ns)
        return before if before_delta <= after_delta else after


@dataclass(slots=True)
class LaneOverlayData:
    series_by_role: dict[str, LaneSeries]

    def ordered_series(self, roles: Iterable[str] = LANE_ROLES) -> list[LaneSeries]:
        return [
            self.series_by_role[role]
            for role in roles
            if role in self.series_by_role
        ]

    def bounds_for_roles(self, roles: Iterable[str]) -> LaneBounds | None:
        points: list[LanePoint] = []
        for series in self.ordered_series(roles):
            for frame in series.frames:
                points.extend(frame.points)
        return lane_bounds(points)


def lane_role_for_topic(topic: TopicInfo) -> str | None:
    if topic.msgtype != "sensor_msgs/msg/PointCloud2":
        return None
    for role in LANE_ROLES:
        if topic.name.endswith(f"{LANE_TOPIC_ROOT}{role}"):
            return role
    return None


def lane_topics(topics: Iterable[TopicInfo]) -> dict[str, TopicInfo]:
    found: dict[str, TopicInfo] = {}
    for topic in topics:
        role = lane_role_for_topic(topic)
        if role is not None:
            found[role] = topic
    return {role: found[role] for role in LANE_ROLES if role in found}


def extract_lane_points(message: object) -> tuple[LanePoint, ...]:
    points: list[LanePoint] = []
    for row in iter_point_cloud_rows(message):
        x = _finite_float(row.get("x"))
        y = _finite_float(row.get("y"))
        if x is None or y is None:
            continue
        points.append(LanePoint(x=x, y=y))
    return tuple(points)


def build_lane_series(
    reader: object,
    topic: TopicInfo,
    role: str,
    *,
    cancellation_token: CancellationToken | None = None,
    progress_callback: ProgressCallback | None = None,
) -> LaneSeries:
    frames: list[LaneFrame] = []
    for record in reader.iter_messages(topics=[topic.name]):
        if cancellation_token is not None:
            cancellation_token.throw_if_cancelled()
        if record.decoded is None:
            advance_progress(progress_callback)
            continue
        points = extract_lane_points(record.decoded)
        frames.append(LaneFrame(timestamp_ns=record.timestamp_ns, points=points))
        advance_progress(progress_callback)
    return LaneSeries(role=role, topic=topic.name, frames=frames)


def build_lane_overlay_data(
    reader: object,
    topics: Iterable[TopicInfo],
    *,
    cancellation_token: CancellationToken | None = None,
    progress_callback: ProgressCallback | None = None,
) -> LaneOverlayData:
    topics_by_role = lane_topics(topics)
    topic_to_role = {topic.name: role for role, topic in topics_by_role.items()}
    frames_by_role: dict[str, list[LaneFrame]] = {role: [] for role in topics_by_role}
    if not topic_to_role:
        return LaneOverlayData(series_by_role={})

    for record in reader.iter_messages(topics=list(topic_to_role)):
        if cancellation_token is not None:
            cancellation_token.throw_if_cancelled()
        role = topic_to_role.get(record.topic)
        if role is None:
            advance_progress(progress_callback)
            continue
        if record.decoded is not None:
            frames_by_role[role].append(
                LaneFrame(
                    timestamp_ns=record.timestamp_ns,
                    points=extract_lane_points(record.decoded),
                )
            )
        advance_progress(progress_callback)

    series_by_role: dict[str, LaneSeries] = {}
    for role, topic in topics_by_role.items():
        series_by_role[role] = LaneSeries(
            role=role,
            topic=topic.name,
            frames=frames_by_role[role],
        )
    return LaneOverlayData(series_by_role=series_by_role)


def lane_bounds(points: Iterable[LanePoint]) -> LaneBounds | None:
    values = list(points)
    if not values:
        return None
    min_x = min(point.x for point in values)
    max_x = max(point.x for point in values)
    min_y = min(point.y for point in values)
    max_y = max(point.y for point in values)
    x_span = max_x - min_x
    y_span = max_y - min_y
    x_margin = (x_span * 0.05) if x_span > 0 else 1.0
    y_margin = (y_span * 0.05) if y_span > 0 else 1.0
    return LaneBounds(
        min_x=min_x - x_margin,
        max_x=max_x + x_margin,
        min_y=min_y - y_margin,
        max_y=max_y + y_margin,
    )


def _finite_float(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None
