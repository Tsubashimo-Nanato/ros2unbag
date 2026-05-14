from __future__ import annotations

from dataclasses import dataclass

from .decoder import summarize_message
from .models import MessageRecord, TopicInfo
from .progress import ProgressCallback, advance_progress
from .topic_indexer import NearestMessage, build_timestamp_index


@dataclass(slots=True)
class InspectResult:
    topic: str
    msgtype: str
    nearest_timestamp_ns: int | None
    delta_ms: float | None
    before_timestamp_ns: int | None
    after_timestamp_ns: int | None
    summary: dict[str, object]


@dataclass(slots=True)
class _NearestRecord:
    nearest_record: MessageRecord | None = None
    nearest_delta_ns: int | None = None
    before_timestamp_ns: int | None = None
    after_timestamp_ns: int | None = None


def inspect_time(
    reader: object,
    *,
    relative_time_sec: float | None = None,
    absolute_timestamp_ns: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[int, list[InspectResult]]:
    return inspect_time_streaming(
        reader,
        relative_time_sec=relative_time_sec,
        absolute_timestamp_ns=absolute_timestamp_ns,
        progress_callback=progress_callback,
    )


def _inspect_time_indexed(
    reader: object,
    *,
    relative_time_sec: float | None = None,
    absolute_timestamp_ns: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[int, list[InspectResult]]:
    if absolute_timestamp_ns is None and relative_time_sec is None:
        raise ValueError("relative_time_sec or absolute_timestamp_ns is required")

    topics = {topic.name: topic for topic in reader.get_topics()}
    index = build_timestamp_index(reader, progress_callback=progress_callback)
    if absolute_timestamp_ns is None:
        if index.global_start_timestamp_ns is None:
            raise ValueError("Cannot inspect an empty bag")
        target_ns = index.global_start_timestamp_ns + int(relative_time_sec * 1_000_000_000)
    else:
        target_ns = absolute_timestamp_ns

    return _inspect_from_index(reader, topics, target_ns, index)


def inspect_time_streaming(
    reader: object,
    *,
    relative_time_sec: float | None = None,
    absolute_timestamp_ns: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[int, list[InspectResult]]:
    if absolute_timestamp_ns is None and relative_time_sec is None:
        raise ValueError("relative_time_sec or absolute_timestamp_ns is required")

    topics = {topic.name: topic for topic in reader.get_topics()}
    target_ns = absolute_timestamp_ns
    if target_ns is None:
        bag_start_ns = _reader_start_time(reader)
        if bag_start_ns is None:
            return _inspect_time_indexed(
                reader,
                relative_time_sec=relative_time_sec,
                progress_callback=progress_callback,
            )
        target_ns = bag_start_ns + int(relative_time_sec * 1_000_000_000)

    nearest_by_topic = _nearest_records_by_topic(
        reader,
        topics,
        target_ns,
        progress_callback=progress_callback,
    )
    results: list[InspectResult] = []
    for topic_name in sorted(topics):
        topic = topics[topic_name]
        nearest = nearest_by_topic.get(topic_name, _NearestRecord())
        record = nearest.nearest_record
        summary = summarize_message(record.decoded, record.raw) if record else {}
        delta_ms = (
            None if nearest.nearest_delta_ns is None else nearest.nearest_delta_ns / 1e6
        )
        results.append(
            InspectResult(
                topic=topic.name,
                msgtype=topic.msgtype,
                nearest_timestamp_ns=None if record is None else record.timestamp_ns,
                delta_ms=delta_ms,
                before_timestamp_ns=nearest.before_timestamp_ns,
                after_timestamp_ns=nearest.after_timestamp_ns,
                summary=summary,
            )
        )
    return target_ns, results


def _inspect_from_index(
    reader: object,
    topics: dict[str, TopicInfo],
    target_ns: int,
    index: object,
) -> tuple[int, list[InspectResult]]:
    nearest_by_topic: dict[str, NearestMessage] = {
        topic.name: index.find_nearest(topic.name, target_ns) for topic in topics.values()
    }
    wanted = {
        topic: nearest.nearest_timestamp_ns
        for topic, nearest in nearest_by_topic.items()
        if nearest.nearest_timestamp_ns is not None
    }
    records: dict[str, MessageRecord] = {}
    if wanted:
        for record in reader.iter_messages(topics=list(wanted)):
            if record.topic in records:
                continue
            if record.timestamp_ns == wanted.get(record.topic):
                records[record.topic] = record
            if len(records) == len(wanted):
                break

    results: list[InspectResult] = []
    for topic_name in sorted(topics):
        topic: TopicInfo = topics[topic_name]
        nearest = nearest_by_topic[topic_name]
        record = records.get(topic_name)
        summary = summarize_message(record.decoded, record.raw) if record else {}
        delta_ms = None if nearest.delta_ns is None else nearest.delta_ns / 1e6
        results.append(
            InspectResult(
                topic=topic.name,
                msgtype=topic.msgtype,
                nearest_timestamp_ns=nearest.nearest_timestamp_ns,
                delta_ms=delta_ms,
                before_timestamp_ns=nearest.before_timestamp_ns,
                after_timestamp_ns=nearest.after_timestamp_ns,
                summary=summary,
            )
        )
    return target_ns, results


def _nearest_records_by_topic(
    reader: object,
    topics: dict[str, TopicInfo],
    target_ns: int,
    *,
    progress_callback: ProgressCallback | None,
) -> dict[str, _NearestRecord]:
    nearest: dict[str, _NearestRecord] = {topic_name: _NearestRecord() for topic_name in topics}
    active_topics = {topic.name for topic in topics.values() if topic.message_count > 0}
    if not active_topics:
        active_topics = set(topics)
    after_topics: set[str] = set()

    for record in reader.iter_messages():
        state = nearest.setdefault(record.topic, _NearestRecord())
        delta_ns = record.timestamp_ns - target_ns
        abs_delta_ns = abs(delta_ns)
        if record.timestamp_ns < target_ns:
            state.before_timestamp_ns = record.timestamp_ns
        else:
            state.after_timestamp_ns = (
                record.timestamp_ns
                if state.after_timestamp_ns is None
                else state.after_timestamp_ns
            )
            after_topics.add(record.topic)

        if (
            state.nearest_delta_ns is None
            or abs_delta_ns < abs(state.nearest_delta_ns)
            or (
                abs_delta_ns == abs(state.nearest_delta_ns)
                and delta_ns < state.nearest_delta_ns
            )
        ):
            state.nearest_record = record
            state.nearest_delta_ns = delta_ns

        advance_progress(progress_callback)
        if active_topics <= after_topics:
            break
    return nearest


def _reader_start_time(reader: object) -> int | None:
    get_time_bounds = getattr(reader, "get_time_bounds", None)
    if not callable(get_time_bounds):
        return None
    try:
        start, _end = get_time_bounds()
    except Exception:
        return None
    return None if start is None else int(start)
