from __future__ import annotations

from pathlib import Path

from ros2unbag.core.manifest import sanitize_topic_name
from ros2unbag.core.models import ExportResult
from ros2unbag.core.point_cloud import iter_point_cloud_rows, point_cloud_field_names
from ros2unbag.core.progress import ProgressCallback
from ros2unbag.core.progress import advance_progress
from ros2unbag.exporters.csv_exporter import _topic_msgtype
from ros2unbag.exporters.tabular import collect_tabular_topic_data


def export_topic_parquet(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ExportResult:
    """Export one topic as flattened Parquet rows using pandas + pyarrow."""
    if _topic_msgtype(reader, topic) == "sensor_msgs/msg/PointCloud2":
        return _export_point_cloud_parquet_streaming(
            reader,
            topic,
            out_dir,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )

    import pandas as pd

    output_dir = Path(out_dir) / "parquet"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sanitize_topic_name(topic)}.parquet"
    data = collect_tabular_topic_data(
        reader,
        topic,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )
    frame = pd.DataFrame(data.rows, columns=data.fieldnames)
    frame.to_parquet(output_path, engine="pyarrow", index=False)

    return ExportResult(
        topic=topic,
        format="parquet",
        output_path=str(output_path),
        message_count=data.source_message_count,
        first_timestamp_ns=data.first_timestamp_ns,
        last_timestamp_ns=data.last_timestamp_ns,
        warnings=data.warnings,
    )


def _export_point_cloud_parquet_streaming(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    bag_start_timestamp_ns: int | None,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    import pyarrow as pa
    import pyarrow.parquet as pq

    output_dir = Path(out_dir) / "parquet"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{sanitize_topic_name(topic)}.parquet"
    source_count = 0
    point_row_count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    warnings: list[str] = []
    rows: list[dict[str, object]] = []
    writer: pq.ParquetWriter | None = None
    fieldnames: list[str] | None = None
    batch_size = 50_000

    def flush() -> None:
        nonlocal writer, rows
        if not rows:
            return
        table = pa.Table.from_pylist(rows)
        if writer is None:
            writer = pq.ParquetWriter(output_path, table.schema)
        writer.write_table(table)
        rows = []

    try:
        for record in reader.iter_messages(topics=[topic]):
            source_count += 1
            first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
            last_timestamp = record.timestamp_ns
            if record.decoded is None:
                warnings.append("Message was not decoded; Parquet contains decoded point rows only.")
                advance_progress(progress_callback)
                continue
            if fieldnames is None:
                fieldnames = [
                    "timestamp_ns",
                    "timestamp_sec_from_start",
                    "topic",
                    *point_cloud_field_names(record.decoded),
                ]
            base_row = {
                "timestamp_ns": record.timestamp_ns,
                "timestamp_sec_from_start": _sec_from_start(
                    record.timestamp_ns, bag_start_timestamp_ns
                ),
                "topic": record.topic,
            }
            for point_row in iter_point_cloud_rows(record.decoded):
                row = {field: None for field in fieldnames}
                row.update(base_row)
                row.update(point_row)
                rows.append(row)
                point_row_count += 1
                if len(rows) >= batch_size:
                    flush()
            advance_progress(progress_callback)
        flush()
    finally:
        if writer is not None:
            writer.close()

    if writer is None:
        import pandas as pd

        pd.DataFrame(columns=fieldnames or ["timestamp_ns", "timestamp_sec_from_start", "topic"]).to_parquet(
            output_path,
            engine="pyarrow",
            index=False,
        )
    if source_count != point_row_count:
        warnings.append(
            f"PointCloud2 Parquet expands {source_count} source messages into {point_row_count} point rows."
        )
    return ExportResult(
        topic=topic,
        format="parquet",
        output_path=str(output_path),
        message_count=source_count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _sec_from_start(timestamp_ns: int, bag_start_timestamp_ns: int | None) -> float | None:
    if bag_start_timestamp_ns is None:
        return None
    return (timestamp_ns - bag_start_timestamp_ns) / 1e9

