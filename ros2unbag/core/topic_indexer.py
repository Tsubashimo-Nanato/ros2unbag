from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Iterable

from .models import MessageRecord
from .progress import ProgressCallback, advance_progress


@dataclass(slots=True)
class NearestMessage:
    topic: str
    requested_timestamp_ns: int
    nearest_timestamp_ns: int | None
    delta_ns: int | None
    before_timestamp_ns: int | None
    after_timestamp_ns: int | None
    message_index: int | None


class TimestampIndex:
    def __init__(self) -> None:
        self.timestamps_by_topic: dict[str, list[int]] = {}
        self.global_start_timestamp_ns: int | None = None
        self.global_end_timestamp_ns: int | None = None

    def add(self, record: MessageRecord) -> None:
        timestamps = self.timestamps_by_topic.setdefault(record.topic, [])
        timestamps.append(record.timestamp_ns)
        if (
            self.global_start_timestamp_ns is None
            or record.timestamp_ns < self.global_start_timestamp_ns
        ):
            self.global_start_timestamp_ns = record.timestamp_ns
        if (
            self.global_end_timestamp_ns is None
            or record.timestamp_ns > self.global_end_timestamp_ns
        ):
            self.global_end_timestamp_ns = record.timestamp_ns

    def extend(self, records: Iterable[MessageRecord]) -> None:
        for record in records:
            self.add(record)
        self.finalize()

    def finalize(self) -> None:
        for timestamps in self.timestamps_by_topic.values():
            timestamps.sort()

    def topic_message_count(self, topic: str) -> int:
        return len(self.timestamps_by_topic.get(topic, []))

    def find_nearest(self, topic: str, timestamp_ns: int) -> NearestMessage:
        timestamps = self.timestamps_by_topic.get(topic, [])
        if not timestamps:
            return NearestMessage(topic, timestamp_ns, None, None, None, None, None)

        index = bisect_left(timestamps, timestamp_ns)
        before_index = index - 1 if index > 0 else None
        after_index = index if index < len(timestamps) else None
        before = timestamps[before_index] if before_index is not None else None
        after = timestamps[after_index] if after_index is not None else None

        if before is None:
            nearest_index = after_index
        elif after is None:
            nearest_index = before_index
        else:
            before_delta = abs(timestamp_ns - before)
            after_delta = abs(after - timestamp_ns)
            nearest_index = before_index if before_delta <= after_delta else after_index

        nearest = timestamps[nearest_index] if nearest_index is not None else None
        delta = None if nearest is None else nearest - timestamp_ns
        return NearestMessage(
            topic=topic,
            requested_timestamp_ns=timestamp_ns,
            nearest_timestamp_ns=nearest,
            delta_ns=delta,
            before_timestamp_ns=before,
            after_timestamp_ns=after,
            message_index=nearest_index,
        )


def build_timestamp_index(
    reader: object,
    topics: list[str] | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
) -> TimestampIndex:
    index = TimestampIndex()
    for record in reader.iter_messages(topics=topics):
        index.add(record)
        advance_progress(progress_callback)
    index.finalize()
    return index
