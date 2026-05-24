from __future__ import annotations

import csv
from pathlib import Path

from ros2unbag.core.manifest import sanitize_topic_name
from ros2unbag.core.models import ExportResult
from ros2unbag.core.point_cloud import iter_point_cloud_rows, point_cloud_field_names
from ros2unbag.core.progress import ProgressCallback
from ros2unbag.core.progress import advance_progress
from ros2unbag.exporters.tabular import collect_tabular_topic_data


def export_topic_csv(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ExportResult:
    if _topic_msgtype(reader, topic) == "sensor_msgs/msg/PointCloud2":
        return _export_point_cloud_csv_streaming(
            reader,
            topic,
            out_dir,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )

    output_dir = Path(out_dir) / "csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sanitize_topic_name(topic)}.csv"
    data = collect_tabular_topic_data(
        reader,
        topic,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=data.fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data.rows)

    return ExportResult(
        topic=topic,
        format="csv",
        output_path=str(output_path),
        message_count=data.source_message_count,
        first_timestamp_ns=data.first_timestamp_ns,
        last_timestamp_ns=data.last_timestamp_ns,
        warnings=_csv_warnings(data.warnings),
    )


def _export_point_cloud_csv_streaming(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    output_dir = Path(out_dir) / "csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sanitize_topic_name(topic)}.csv"
    fieldnames: list[str] | None = None
    writer: csv.DictWriter[str] | None = None
    source_count = 0
    point_row_count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    warnings: list[str] = []

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        for record in reader.iter_messages(topics=[topic]):
            source_count += 1
            first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
            last_timestamp = record.timestamp_ns
            if record.decoded is None:
                warnings.append("Message was not decoded; CSV contains decoded point rows only.")
                advance_progress(progress_callback)
                continue
            if fieldnames is None:
                fieldnames = [
                    "timestamp_ns",
                    "timestamp_sec_from_start",
                    "topic",
                    *point_cloud_field_names(record.decoded),
                ]
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
            base_row = {
                "timestamp_ns": record.timestamp_ns,
                "timestamp_sec_from_start": _sec_from_start(
                    record.timestamp_ns, bag_start_timestamp_ns
                ),
                "topic": record.topic,
            }
            for point_row in iter_point_cloud_rows(record.decoded):
                row = dict(base_row)
                row.update(point_row)
                writer.writerow(row)
                point_row_count += 1
            advance_progress(progress_callback)
        if fieldnames is None:
            writer = csv.DictWriter(
                handle,
                fieldnames=["timestamp_ns", "timestamp_sec_from_start", "topic"],
                extrasaction="ignore",
            )
            writer.writeheader()

    if source_count != point_row_count:
        warnings.append(
            f"PointCloud2 CSV expands {source_count} source messages into {point_row_count} point rows."
        )
    return ExportResult(
        topic=topic,
        format="csv",
        output_path=str(output_path),
        message_count=source_count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _topic_msgtype(reader: object, topic: str) -> str | None:
    get_topics = getattr(reader, "get_topics", None)
    if callable(get_topics):
        for info in get_topics():
            if getattr(info, "name", None) == topic:
                return str(getattr(info, "msgtype", ""))
    for record in reader.iter_messages(topics=[topic]):
        return str(record.msgtype)
    return None


def _sec_from_start(timestamp_ns: int, bag_start_timestamp_ns: int | None) -> float | None:
    if bag_start_timestamp_ns is None:
        return None
    return (timestamp_ns - bag_start_timestamp_ns) / 1e9


def _csv_warnings(warnings: list[str]) -> list[str]:
    return [
        warning.replace("tabular export", "CSV").replace("Tabular export", "CSV")
        for warning in warnings
    ]

