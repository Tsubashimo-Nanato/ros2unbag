from __future__ import annotations

import csv
from pathlib import Path

from ros2_unbag.core.manifest import sanitize_topic_name
from ros2_unbag.core.models import ExportResult
from ros2_unbag.exporters.tabular import collect_tabular_topic_data


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
    data = collect_tabular_topic_data(
        reader,
        topic,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
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


def _csv_warnings(warnings: list[str]) -> list[str]:
    return [
        warning.replace("tabular export", "CSV").replace("Tabular export", "CSV")
        for warning in warnings
    ]
