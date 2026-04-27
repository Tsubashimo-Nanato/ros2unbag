from __future__ import annotations

from dataclasses import dataclass

from .decoder import summarize_message
from .models import MessageRecord, TopicInfo
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


def inspect_time(
    reader: object,
    *,
    relative_time_sec: float | None = None,
    absolute_timestamp_ns: int | None = None,
) -> tuple[int, list[InspectResult]]:
    if absolute_timestamp_ns is None and relative_time_sec is None:
        raise ValueError("relative_time_sec or absolute_timestamp_ns is required")

    index = build_timestamp_index(reader)
    if absolute_timestamp_ns is None:
        if index.global_start_timestamp_ns is None:
            raise ValueError("Cannot inspect an empty bag")
        target_ns = index.global_start_timestamp_ns + int(relative_time_sec * 1_000_000_000)
    else:
        target_ns = absolute_timestamp_ns

    topics = {topic.name: topic for topic in reader.get_topics()}
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
