from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .bag_reader import BaseBagReader
from .models import ExportResult
from .progress import ProgressCallback
from ..exporters.csv_exporter import export_topic_csv
from ..exporters.image_exporter import export_topic_images
from ..exporters.jsonl_exporter import export_topic_jsonl
from ..exporters.npz_exporter import export_topic_npz
from ..exporters.parquet_exporter import export_topic_parquet
from ..exporters.point_cloud_exporter import export_topic_point_clouds
from ..exporters.raw_exporter import export_topic_raw
from ..exporters.sqlite_exporter import export_topic_sqlite
from ..exporters.video_exporter import export_topic_video


ExportHandler = Callable[
    [BaseBagReader, str, Path, int | None, float, ProgressCallback | None],
    ExportResult,
]


def run_export(
    reader: BaseBagReader,
    *,
    topic: str,
    fmt: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    fps: float = 30.0,
    progress_callback: ProgressCallback | None = None,
) -> ExportResult:
    handler = EXPORT_HANDLERS.get(fmt)
    if handler is None:
        raise ValueError(f"Unsupported implemented export format: {fmt}")
    return handler(reader, topic, out, bag_start_timestamp_ns, fps, progress_callback)


def _export_csv(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_csv(
        reader,
        topic,
        out,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_jsonl(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_jsonl(
        reader,
        topic,
        out,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_raw(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_raw(
        reader,
        topic,
        out,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_npz(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_npz(
        reader,
        topic,
        out,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_parquet(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_parquet(
        reader,
        topic,
        out,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_sqlite(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_sqlite(
        reader,
        topic,
        out,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_png(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_images(
        reader,
        topic,
        out,
        image_format="png",
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_jpg(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_images(
        reader,
        topic,
        out,
        image_format="jpg",
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_mp4(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_video(
        reader,
        topic,
        out,
        fps=fps,
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_pcd(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_point_clouds(
        reader,
        topic,
        out,
        point_format="pcd",
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


def _export_ply(
    reader: BaseBagReader,
    topic: str,
    out: Path,
    bag_start_timestamp_ns: int | None,
    _fps: float,
    progress_callback: ProgressCallback | None,
) -> ExportResult:
    return export_topic_point_clouds(
        reader,
        topic,
        out,
        point_format="ply",
        bag_start_timestamp_ns=bag_start_timestamp_ns,
        progress_callback=progress_callback,
    )


EXPORT_HANDLERS: dict[str, ExportHandler] = {
    "csv": _export_csv,
    "jpg": _export_jpg,
    "jsonl": _export_jsonl,
    "mp4": _export_mp4,
    "npz": _export_npz,
    "parquet": _export_parquet,
    "pcd": _export_pcd,
    "ply": _export_ply,
    "png": _export_png,
    "raw": _export_raw,
    "sqlite": _export_sqlite,
}
