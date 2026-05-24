from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from ros2unbag.core.decoder import decode_compressed_image, decode_sensor_image, flatten_message
from ros2unbag.core.manifest import sanitize_topic_name
from ros2unbag.core.models import ExportResult
from ros2unbag.core.point_cloud import (
    expanded_point_field_names,
    expanded_point_row,
    iter_point_cloud_rows,
)
from ros2unbag.core.progress import ProgressCallback, advance_progress


IMAGE_TYPES = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}


def export_topic_npz(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ExportResult:
    first_record = _peek_first_record(reader, topic)
    if first_record is None:
        output_dir = Path(out_dir) / "npz"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{sanitize_topic_name(topic)}.npz"
        _save_npz(output_path, timestamp_ns=[], timestamp_sec_from_start=[])
        return ExportResult(topic=topic, format="npz", output_path=str(output_path))
    if first_record.msgtype == "sensor_msgs/msg/PointCloud2":
        return _export_point_cloud_npz(
            reader,
            topic,
            out_dir,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )
    if first_record.msgtype in IMAGE_TYPES:
        return _export_image_npz(
            reader,
            topic,
            out_dir,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )
    return _export_tabular_npz(
        reader,
        topic,
        out_dir,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _peek_first_record(reader: object, topic: str) -> object | None:
    for record in reader.iter_messages(topics=[topic]):
        return record
    return None


def _export_point_cloud_npz(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    import numpy as np

    output_dir = Path(out_dir) / "npz" / sanitize_topic_name(topic)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamps_path = output_dir / "timestamps.csv"
    warnings: list[str] = []
    source_count = 0
    written_count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None

    with timestamps_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "frame_index",
                "timestamp_ns",
                "timestamp_sec_from_start",
                "filename",
                "point_count",
                "field_names",
            ],
        )
        writer.writeheader()
        for record in reader.iter_messages(topics=[topic]):
            source_count += 1
            first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
            last_timestamp = record.timestamp_ns
            if record.decoded is None:
                warnings.append(f"Skipped message at {record.timestamp_ns}: message was not decoded")
                advance_progress(progress_callback)
                continue
            fields = expanded_point_field_names(record.decoded)
            columns: dict[str, list[float]] = {field: [] for field in fields}
            for row in iter_point_cloud_rows(record.decoded):
                for field, value in zip(fields, expanded_point_row(record.decoded, row)):
                    columns[field].append(float(value) if isinstance(value, (int, float)) else math.nan)
            filename = f"{written_count:06d}.npz"
            arrays = {
                field: np.asarray(values)
                for field, values in columns.items()
            }
            arrays["fields"] = np.asarray(fields)
            arrays["timestamp_ns"] = np.asarray(record.timestamp_ns, dtype=np.int64)
            sec = _sec_from_start(record.timestamp_ns, bag_start_timestamp_ns)
            arrays["timestamp_sec_from_start"] = np.asarray(
                math.nan if sec is None else sec,
                dtype=np.float64,
            )
            _save_npz(output_dir / filename, **arrays)
            writer.writerow(
                {
                    "frame_index": written_count,
                    "timestamp_ns": record.timestamp_ns,
                    "timestamp_sec_from_start": sec,
                    "filename": filename,
                    "point_count": len(next(iter(columns.values()), [])),
                    "field_names": " ".join(fields),
                }
            )
            written_count += 1
            advance_progress(progress_callback)

    if source_count and written_count != source_count:
        warnings.append(f"Exported {written_count} NPZ frames from {source_count} source messages.")
    return ExportResult(
        topic=topic,
        format="npz",
        output_path=str(output_dir),
        message_count=written_count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _export_image_npz(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    import numpy as np

    output_dir = Path(out_dir) / "npz" / sanitize_topic_name(topic)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamps_path = output_dir / "timestamps.csv"
    warnings: list[str] = []
    source_count = 0
    written_count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None

    with timestamps_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "frame_index",
                "timestamp_ns",
                "timestamp_sec_from_start",
                "filename",
                "width",
                "height",
                "encoding",
            ],
        )
        writer.writeheader()
        for record in reader.iter_messages(topics=[topic]):
            source_count += 1
            first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
            last_timestamp = record.timestamp_ns
            try:
                if record.decoded is None:
                    raise ValueError("message was not decoded")
                frame = (
                    decode_sensor_image(record.decoded)
                    if record.msgtype == "sensor_msgs/msg/Image"
                    else decode_compressed_image(record.decoded)
                )
            except Exception as exc:
                warnings.append(f"Skipped message at {record.timestamp_ns}: {exc}")
                advance_progress(progress_callback)
                continue
            filename = f"{written_count:06d}.npz"
            sec = _sec_from_start(record.timestamp_ns, bag_start_timestamp_ns)
            _save_npz(
                output_dir / filename,
                image=frame.array,
                timestamp_ns=np.asarray(record.timestamp_ns, dtype=np.int64),
                timestamp_sec_from_start=np.asarray(math.nan if sec is None else sec, dtype=np.float64),
                encoding=np.asarray(frame.encoding),
                width=np.asarray(frame.width, dtype=np.int64),
                height=np.asarray(frame.height, dtype=np.int64),
            )
            writer.writerow(
                {
                    "frame_index": written_count,
                    "timestamp_ns": record.timestamp_ns,
                    "timestamp_sec_from_start": sec,
                    "filename": filename,
                    "width": frame.width,
                    "height": frame.height,
                    "encoding": frame.encoding,
                }
            )
            written_count += 1
            advance_progress(progress_callback)

    if source_count and written_count != source_count:
        warnings.append(f"Exported {written_count} NPZ frames from {source_count} source messages.")
    return ExportResult(
        topic=topic,
        format="npz",
        output_path=str(output_dir),
        message_count=written_count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _export_tabular_npz(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    import numpy as np

    output_dir = Path(out_dir) / "npz"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sanitize_topic_name(topic)}.npz"
    timestamps: list[int] = []
    secs: list[float] = []
    values_by_field: dict[str, list[float]] = {}
    warnings: list[str] = []
    first_timestamp: int | None = None
    last_timestamp: int | None = None

    for record in reader.iter_messages(topics=[topic]):
        first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
        last_timestamp = record.timestamp_ns
        timestamps.append(record.timestamp_ns)
        sec = _sec_from_start(record.timestamp_ns, bag_start_timestamp_ns)
        secs.append(math.nan if sec is None else sec)
        row = flatten_message(record.decoded) if record.decoded is not None else {}
        for field in values_by_field:
            values_by_field[field].append(math.nan)
        for field, value in row.items():
            if not isinstance(value, (int, float, bool)):
                continue
            values_by_field.setdefault(field, [math.nan] * len(timestamps))
            values_by_field[field][-1] = float(value)
        if record.decoded is None:
            warnings.append("Message was not decoded; NPZ contains timestamps only for raw messages.")
        advance_progress(progress_callback)

    arrays: dict[str, Any] = {
        "timestamp_ns": np.asarray(timestamps, dtype=np.int64),
        "timestamp_sec_from_start": np.asarray(secs, dtype=np.float64),
        "fields": np.asarray(sorted(values_by_field)),
    }
    for field, values in values_by_field.items():
        arrays[_safe_npz_key(field)] = np.asarray(values, dtype=np.float64)
    _save_npz(output_path, **arrays)
    return ExportResult(
        topic=topic,
        format="npz",
        output_path=str(output_path),
        message_count=len(timestamps),
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _save_npz(path: Path, **arrays: object) -> None:
    import numpy as np

    np.savez_compressed(path, **arrays)


def _safe_npz_key(name: str) -> str:
    safe = "".join(char if char.isalnum() or char == "_" else "_" for char in name)
    return safe or "value"


def _sec_from_start(timestamp_ns: int, bag_start_timestamp_ns: int | None) -> float | None:
    if bag_start_timestamp_ns is None:
        return None
    return (timestamp_ns - bag_start_timestamp_ns) / 1e9
