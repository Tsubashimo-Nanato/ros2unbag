from __future__ import annotations

from pathlib import Path

from ros2unbag.core.manifest import sanitize_topic_name
from ros2unbag.core.models import ExportResult
from ros2unbag.core.progress import ProgressCallback
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

