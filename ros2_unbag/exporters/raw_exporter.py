from __future__ import annotations

import csv
import json
from pathlib import Path

from ros2_unbag.core.decoder import message_to_plain
from ros2_unbag.core.manifest import sanitize_topic_name
from ros2_unbag.core.models import ExportResult


def export_topic_raw(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None = None,
) -> ExportResult:
    """Write message payloads to one binary stream plus a seekable CSV index."""
    output_dir = Path(out_dir) / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_topic_name(topic)
    bin_path = output_dir / f"{safe_name}.bin"
    index_path = output_dir / f"{safe_name}_index.csv"
    count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    byte_offset = 0
    warnings: list[str] = []

    with bin_path.open("wb") as binary, index_path.open(
        "w", newline="", encoding="utf-8"
    ) as index_handle:
        writer = csv.DictWriter(
            index_handle,
            fieldnames=[
                "message_index",
                "timestamp_ns",
                "timestamp_sec_from_start",
                "byte_offset",
                "byte_length",
                "msgtype",
            ],
        )
        writer.writeheader()
        for record in reader.iter_messages(topics=[topic]):
            payload = record.raw
            if payload is None:
                # Some fallback readers may expose decoded data but not original bytes.
                # Preserve the message content as deterministic JSON instead of dropping it.
                warnings.append(
                    "Record had no raw bytes; wrote JSON-serialized decoded payload instead."
                )
                payload = json.dumps(message_to_plain(record.decoded), sort_keys=True).encode(
                    "utf-8"
                )
            first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
            last_timestamp = record.timestamp_ns
            binary.write(payload)
            writer.writerow(
                {
                    "message_index": count,
                    "timestamp_ns": record.timestamp_ns,
                    "timestamp_sec_from_start": _sec_from_start(
                        record.timestamp_ns, bag_start_timestamp_ns
                    ),
                    "byte_offset": byte_offset,
                    "byte_length": len(payload),
                    "msgtype": record.msgtype,
                }
            )
            byte_offset += len(payload)
            count += 1

    return ExportResult(
        topic=topic,
        format="raw",
        output_path=str(bin_path),
        message_count=count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _sec_from_start(timestamp_ns: int, bag_start_timestamp_ns: int | None) -> float | None:
    if bag_start_timestamp_ns is None:
        return None
    return (timestamp_ns - bag_start_timestamp_ns) / 1e9
