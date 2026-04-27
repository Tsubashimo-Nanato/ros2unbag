from __future__ import annotations

import json
from pathlib import Path

from ros2_unbag.core.decoder import message_to_plain
from ros2_unbag.core.manifest import sanitize_topic_name
from ros2_unbag.core.models import ExportResult


def export_topic_jsonl(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None = None,
) -> ExportResult:
    output_dir = Path(out_dir) / "jsonl"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sanitize_topic_name(topic)}.jsonl"
    count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    warnings: list[str] = []

    with output_path.open("w", encoding="utf-8") as handle:
        for record in reader.iter_messages(topics=[topic]):
            first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
            last_timestamp = record.timestamp_ns
            data = (
                message_to_plain(record.decoded)
                if record.decoded is not None
                else {"raw": message_to_plain(record.raw or b"")}
            )
            if record.decoded is None:
                warnings.append(
                    "Message was not decoded; JSONL includes base64 raw bytes."
                )
            payload = {
                "timestamp_ns": record.timestamp_ns,
                "timestamp_sec_from_start": _sec_from_start(
                    record.timestamp_ns, bag_start_timestamp_ns
                ),
                "topic": record.topic,
                "type": record.msgtype,
                "data": data,
            }
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
            count += 1

    return ExportResult(
        topic=topic,
        format="jsonl",
        output_path=str(output_path),
        message_count=count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _sec_from_start(timestamp_ns: int, bag_start_timestamp_ns: int | None) -> float | None:
    if bag_start_timestamp_ns is None:
        return None
    return (timestamp_ns - bag_start_timestamp_ns) / 1e9
