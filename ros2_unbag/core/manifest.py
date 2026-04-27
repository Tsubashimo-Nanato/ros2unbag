from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .decoder import summarize_samples
from .models import Manifest, MessageRecord, TopicInfo
from .type_classifier import classify_topic, suggested_exports_for_category


def sanitize_topic_name(topic_name: str) -> str:
    """Convert a ROS topic path into a deterministic filesystem-safe name."""
    cleaned = topic_name.strip().replace("\\", "/")
    parts = [part for part in cleaned.split("/") if part]
    base = "__".join(parts) if parts else "topic"
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", base)
    base = base.strip("._-") or "topic"
    if base[0].isdigit():
        base = f"topic_{base}"
    return base


def build_manifest(reader: object, *, sample_per_topic: int = 3) -> Manifest:
    """Scan all messages once to collect counts, timestamps, samples, and warnings."""
    topics = {topic.name: topic for topic in reader.get_topics()}
    counts: dict[str, int] = {topic_name: 0 for topic_name in topics}
    first_by_topic: dict[str, int] = {}
    last_by_topic: dict[str, int] = {}
    samples: dict[str, list[MessageRecord]] = {topic_name: [] for topic_name in topics}
    bag_start: int | None = None
    bag_end: int | None = None

    for record in reader.iter_messages():
        if record.topic not in topics:
            topics[record.topic] = TopicInfo(name=record.topic, msgtype=record.msgtype)
            counts[record.topic] = 0
            samples[record.topic] = []
        counts[record.topic] += 1
        first_by_topic.setdefault(record.topic, record.timestamp_ns)
        last_by_topic[record.topic] = record.timestamp_ns
        if len(samples[record.topic]) < sample_per_topic:
            samples[record.topic].append(record)
        if bag_start is None or record.timestamp_ns < bag_start:
            bag_start = record.timestamp_ns
        if bag_end is None or record.timestamp_ns > bag_end:
            bag_end = record.timestamp_ns

    for topic_name in sorted(topics):
        info = topics[topic_name]
        if counts.get(topic_name, 0) > 0:
            info.message_count = counts[topic_name]
        if topic_name in first_by_topic:
            info.first_timestamp_ns = first_by_topic[topic_name]
        if topic_name in last_by_topic:
            info.last_timestamp_ns = last_by_topic[topic_name]
        if info.first_timestamp_ns is not None and info.last_timestamp_ns is not None:
            info.duration_sec = (info.last_timestamp_ns - info.first_timestamp_ns) / 1e9
        info.sample_summary = summarize_samples(samples.get(topic_name, []))
        info.category = classify_topic(info, samples.get(topic_name, []))
        info.suggested_exports = suggested_exports_for_category(info.category)

    return Manifest(
        source_bag_path=str(getattr(reader, "path", "")),
        created_at=datetime.now(timezone.utc).isoformat(),
        bag_start_timestamp_ns=bag_start,
        bag_end_timestamp_ns=bag_end,
        topics=[topics[key] for key in sorted(topics)],
        warnings=list(getattr(reader, "warnings", [])),
    )


def write_manifest(manifest: Manifest, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def write_topics_csv(topics: list[TopicInfo], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "name",
        "msgtype",
        "serialization_format",
        "message_count",
        "first_timestamp_ns",
        "last_timestamp_ns",
        "duration_sec",
        "category",
        "suggested_exports",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for topic in topics:
            row = topic.to_dict()
            row["suggested_exports"] = ";".join(topic.suggested_exports)
            writer.writerow({field: row.get(field) for field in fields})
    return path
