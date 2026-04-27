from __future__ import annotations

import base64
import csv
import hashlib
from pathlib import Path
from typing import Any

from ros2_unbag.core.decoder import flatten_message
from ros2_unbag.core.manifest import sanitize_topic_name
from ros2_unbag.core.models import ExportResult
from ros2_unbag.core.point_cloud import point_cloud_field_names, point_cloud_rows


def export_topic_csv(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None = None,
) -> ExportResult:
    output_dir = Path(out_dir) / "csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sanitize_topic_name(topic)}.csv"
    rows: list[dict[str, Any]] = []
    fieldnames: set[str] = {"timestamp_ns", "timestamp_sec_from_start", "topic"}
    warnings: list[str] = []
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    source_message_count = 0

    for record in reader.iter_messages(topics=[topic]):
        source_message_count += 1
        first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
        last_timestamp = record.timestamp_ns
        base_row: dict[str, Any] = {
            "timestamp_ns": record.timestamp_ns,
            "timestamp_sec_from_start": _sec_from_start(
                record.timestamp_ns, bag_start_timestamp_ns
            ),
            "topic": record.topic,
        }
        if record.msgtype == "sensor_msgs/msg/PointCloud2" and record.decoded is not None:
            point_rows = point_cloud_rows(record.decoded)
            fieldnames.update(point_cloud_field_names(record.decoded))
            for point_row in point_rows:
                row = dict(base_row)
                row.update(point_row)
                rows.append(row)
                fieldnames.update(row)
            continue
        if record.decoded is not None:
            row = dict(base_row)
            row.update(flatten_message(record.decoded))
        else:
            warnings.append(
                "Message was not decoded; CSV contains raw metadata. Use raw export to preserve bytes."
            )
            row = dict(base_row)
            row.update(_raw_csv_fields(record.raw))
        rows.append(row)
        fieldnames.update(row)

    if rows and source_message_count != len(rows):
        warnings.append(
            f"PointCloud2 CSV expands {source_message_count} source messages into {len(rows)} point rows."
        )

    ordered_fields = ["timestamp_ns", "timestamp_sec_from_start", "topic"] + sorted(
        fieldnames - {"timestamp_ns", "timestamp_sec_from_start", "topic"}
    )
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return ExportResult(
        topic=topic,
        format="csv",
        output_path=str(output_path),
        message_count=source_message_count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _sec_from_start(timestamp_ns: int, bag_start_timestamp_ns: int | None) -> float | None:
    if bag_start_timestamp_ns is None:
        return None
    return (timestamp_ns - bag_start_timestamp_ns) / 1e9


def _raw_csv_fields(raw: bytes | None) -> dict[str, Any]:
    if raw is None:
        return {"decoded": False, "raw_byte_length": None}
    fields: dict[str, Any] = {
        "decoded": False,
        "raw_byte_length": len(raw),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
    }
    if len(raw) <= 4096:
        fields["raw_base64"] = base64.b64encode(raw).decode("ascii")
    return fields
