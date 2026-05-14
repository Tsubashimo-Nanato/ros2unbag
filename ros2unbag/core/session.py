from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

from .bag_reader import BaseBagReader, open_bag_reader, time_bounds_from_topics
from .manifest import build_manifest, write_manifest, write_topics_csv
from .models import ExportResult, Manifest, TopicDuration, TopicInfo
from .progress import ProgressCallback
from .sync import InspectResult, inspect_time as inspect_time_core
from .topic_indexer import build_timestamp_index
from .type_classifier import classify_topic, suggested_exports_for_category
from ..exporters.csv_exporter import export_topic_csv
from ..exporters.image_exporter import export_topic_images
from ..exporters.jsonl_exporter import export_topic_jsonl
from ..exporters.parquet_exporter import export_topic_parquet
from ..exporters.raw_exporter import export_topic_raw
from ..exporters.sqlite_exporter import export_topic_sqlite
from ..exporters.video_exporter import export_topic_video


IMPLEMENTED_EXPORTS = {"csv", "jpg", "jsonl", "mp4", "parquet", "png", "raw", "sqlite"}
FUTURE_EXPORTS: dict[str, str] = {}
ALL_EXPORTS = IMPLEMENTED_EXPORTS | set(FUTURE_EXPORTS)
ProgressFactory = Callable[[str, int | None], AbstractContextManager[ProgressCallback]]
DATA_EXPORTS = ["csv", "jsonl", "parquet", "raw", "sqlite"]
IMAGE_EXPORTS = ["jpg", "mp4", "png"]
IMAGE_MSGTYPES = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}
IMAGE_CATEGORIES = {"image", "compressed_image", "mask_candidate"}


class Session:
    def __init__(self, *, backend: str = "auto") -> None:
        self.backend = backend
        self.bag_path: Path | None = None
        self.topics: list[TopicInfo] = []
        self.manifest: Manifest | None = None
        self.reader: BaseBagReader | None = None
        self._bag_time_bounds_cache: tuple[int | None, int | None] | None = None

    def open_bag(self, path: str | Path, *, backend: str | None = None) -> list[TopicInfo]:
        self.close()
        selected_backend = backend or self.backend
        bag_path = Path(path)
        reader = open_bag_reader(bag_path, backend=selected_backend)
        self.backend = selected_backend
        self.bag_path = bag_path
        self.reader = reader
        self.topics = self.reader.get_topics()
        for topic in self.topics:
            topic.category = classify_topic(topic, [])
            topic.suggested_exports = suggested_exports_for_category(topic.category)
        self.manifest = None
        return self.topics

    def close(self) -> None:
        if self.reader is not None:
            self.reader.close()
        self.reader = None
        self.bag_path = None
        self.topics = []
        self.manifest = None
        self._bag_time_bounds_cache = None

    def scan(self, *, progress_factory: ProgressFactory | None = None) -> Manifest:
        reader = self._require_reader()
        if progress_factory is None:
            self.manifest = build_manifest(reader)
        else:
            with progress_factory("Scanning bag messages", _total_message_count(self.topics)) as advance:
                self.manifest = build_manifest(reader, progress_callback=advance)
        self.topics = self.manifest.topics
        self._bag_time_bounds_cache = (
            self.manifest.bag_start_timestamp_ns,
            self.manifest.bag_end_timestamp_ns,
        )
        return self.manifest

    def list_topics(self) -> list[TopicInfo]:
        self._require_reader()
        if self.manifest is not None:
            return self.manifest.topics
        return self.topics

    def inspect_time(
        self,
        seconds: float,
        *,
        absolute_ns: bool = False,
        progress_factory: ProgressFactory | None = None,
    ) -> tuple[int, list[InspectResult], list[str]]:
        reader = self._require_reader()
        if progress_factory is None:
            target_ns, results = inspect_time_core(
                reader,
                absolute_timestamp_ns=int(seconds) if absolute_ns else None,
                relative_time_sec=None if absolute_ns else seconds,
            )
        else:
            with progress_factory("Indexing timestamps", _total_message_count(self.topics)) as advance:
                target_ns, results = inspect_time_core(
                    reader,
                    absolute_timestamp_ns=int(seconds) if absolute_ns else None,
                    relative_time_sec=None if absolute_ns else seconds,
                    progress_callback=advance,
                )
        warnings = list(getattr(reader, "warnings", []))
        return target_ns, results, warnings

    def export_topic(
        self,
        topic: str,
        fmt: str,
        out_dir: str | Path,
        *,
        fps: float = 30.0,
        progress_factory: ProgressFactory | None = None,
    ) -> ExportResult:
        reader = self._require_reader()
        fmt = validate_export_format(fmt)
        if fmt in FUTURE_EXPORTS:
            raise ValueError(FUTURE_EXPORTS[fmt])
        topics_by_name = {item.name: item for item in self.list_topics()}
        topic_info = topics_by_name.get(topic)
        if topic_info is None:
            raise ValueError(f"Topic not found: {topic}")
        validate_topic_export_format(topic_info, fmt)
        bag_start_ns, bag_end_ns = self._bag_time_bounds(progress_factory=progress_factory)
        result = self._run_export_with_progress(
            reader,
            topic=topic,
            fmt=fmt,
            out=Path(out_dir),
            bag_start_timestamp_ns=bag_start_ns,
            fps=fps,
            progress_factory=progress_factory,
        )
        result.warnings.extend(_coverage_warnings(result, bag_start_ns, bag_end_ns))
        result.warnings = sorted(set(result.warnings))
        return result

    def export_all(
        self,
        out_dir: str | Path,
        *,
        progress_factory: ProgressFactory | None = None,
    ) -> tuple[Manifest, list[ExportResult]]:
        reader = self._require_reader()
        manifest = self.manifest if self.manifest is not None else self.scan(
            progress_factory=progress_factory
        )
        results: list[ExportResult] = []
        for topic in manifest.topics:
            if topic.message_count == 0:
                continue
            for fmt in default_export_formats(topic):
                try:
                    result = self._run_export_with_progress(
                        reader,
                        topic=topic.name,
                        fmt=fmt,
                        out=Path(out_dir),
                        bag_start_timestamp_ns=manifest.bag_start_timestamp_ns,
                        progress_factory=progress_factory,
                    )
                    result.warnings.extend(
                        _coverage_warnings(
                            result,
                            manifest.bag_start_timestamp_ns,
                            manifest.bag_end_timestamp_ns,
                        )
                    )
                    result.warnings = sorted(set(result.warnings))
                    results.append(result)
                except Exception as exc:
                    results.append(
                        ExportResult(
                            topic=topic.name,
                            format=fmt,
                            output_path="",
                            warnings=[f"Export failed: {exc}"],
                        )
                    )
        manifest.exports = results
        write_manifest(manifest, Path(out_dir) / "manifest.json")
        write_topics_csv(manifest.topics, Path(out_dir) / "topics.csv")
        return manifest, results

    def topic_duration(
        self,
        topic: str,
        *,
        progress_factory: ProgressFactory | None = None,
    ) -> TopicDuration:
        resolved_topic = self._resolve_topic_name(topic)
        topic_info = next(item for item in self.list_topics() if item.name == resolved_topic)
        bag_start_ns, bag_end_ns = self._bag_time_bounds(progress_factory=progress_factory)

        first_ns = topic_info.first_timestamp_ns
        last_ns = topic_info.last_timestamp_ns
        count = topic_info.message_count
        if first_ns is None or last_ns is None or count == 0:
            if progress_factory is None:
                topic_index = build_timestamp_index(self._require_reader(), topics=[resolved_topic])
            else:
                with progress_factory(
                    f"Indexing {resolved_topic}",
                    self._message_count(resolved_topic),
                ) as advance:
                    topic_index = build_timestamp_index(
                        self._require_reader(),
                        topics=[resolved_topic],
                        progress_callback=advance,
                    )
            timestamps = topic_index.timestamps_by_topic.get(resolved_topic, [])
            count = len(timestamps)
            if timestamps:
                first_ns = timestamps[0]
                last_ns = timestamps[-1]

        return TopicDuration(
            topic=resolved_topic,
            msgtype=topic_info.msgtype,
            message_count=count,
            first_timestamp_ns=first_ns,
            last_timestamp_ns=last_ns,
            topic_duration_sec=_span_sec(first_ns, last_ns),
            bag_start_timestamp_ns=bag_start_ns,
            bag_end_timestamp_ns=bag_end_ns,
            bag_duration_sec=_span_sec(bag_start_ns, bag_end_ns),
            start_offset_sec=_offset_sec(first_ns, bag_start_ns),
            end_gap_sec=_offset_sec(bag_end_ns, last_ns),
        )

    def _resolve_topic_name(self, topic: str) -> str:
        topic_names = [item.name for item in self.list_topics()]
        if topic in topic_names:
            return topic
        leaf_matches = [name for name in topic_names if name.rsplit("/", 1)[-1] == topic]
        if len(leaf_matches) == 1:
            return leaf_matches[0]
        if len(leaf_matches) > 1:
            choices = ", ".join(leaf_matches[:8])
            raise ValueError(f"Ambiguous topic leaf {topic!r}. Use a full topic path. Matches: {choices}")
        raise ValueError(f"Topic not found: {topic}")

    def _bag_time_bounds(
        self,
        *,
        progress_factory: ProgressFactory | None = None,
    ) -> tuple[int | None, int | None]:
        if self.manifest is not None:
            return self.manifest.bag_start_timestamp_ns, self.manifest.bag_end_timestamp_ns
        if self._bag_time_bounds_cache is not None:
            return self._bag_time_bounds_cache
        reader = self._require_reader()
        metadata_bounds = _reader_time_bounds(reader, self.topics)
        if metadata_bounds[0] is not None and metadata_bounds[1] is not None:
            self._bag_time_bounds_cache = metadata_bounds
            return metadata_bounds
        if progress_factory is None:
            index = build_timestamp_index(reader)
        else:
            with progress_factory("Indexing bag time bounds", _total_message_count(self.topics)) as advance:
                index = build_timestamp_index(reader, progress_callback=advance)
        self._bag_time_bounds_cache = (
            index.global_start_timestamp_ns,
            index.global_end_timestamp_ns,
        )
        return self._bag_time_bounds_cache

    def _run_export_with_progress(
        self,
        reader: BaseBagReader,
        *,
        topic: str,
        fmt: str,
        out: Path,
        bag_start_timestamp_ns: int | None,
        fps: float = 30.0,
        progress_factory: ProgressFactory | None = None,
    ) -> ExportResult:
        if progress_factory is None:
            return run_export(
                reader,
                topic=topic,
                fmt=fmt,
                out=out,
                bag_start_timestamp_ns=bag_start_timestamp_ns,
                fps=fps,
            )
        with progress_factory(
            f"Exporting {topic} as {fmt}",
            self._message_count(topic),
        ) as advance:
            return run_export(
                reader,
                topic=topic,
                fmt=fmt,
                out=out,
                bag_start_timestamp_ns=bag_start_timestamp_ns,
                fps=fps,
                progress_callback=advance,
            )

    def _message_count(self, topic: str) -> int | None:
        try:
            count = self._require_reader().get_message_count(topic)
        except Exception:
            return None
        return count if count > 0 else None

    def _require_reader(self) -> BaseBagReader:
        if self.reader is None:
            raise RuntimeError("No bag is open. Run open BAG_PATH first.")
        return self.reader


def validate_export_format(fmt: str) -> str:
    normalized = fmt.lower()
    if normalized not in ALL_EXPORTS:
        allowed = ", ".join(sorted(ALL_EXPORTS))
        raise ValueError(f"Unsupported format {fmt!r}. Choose one of: {allowed}")
    return normalized


def compatible_export_formats(topic: TopicInfo) -> list[str]:
    formats = list(DATA_EXPORTS)
    if _is_image_topic(topic):
        formats.extend(IMAGE_EXPORTS)
    return formats


def validate_topic_export_format(topic: TopicInfo, fmt: str) -> None:
    if fmt in compatible_export_formats(topic):
        return
    allowed = ", ".join(compatible_export_formats(topic))
    raise ValueError(
        f"Format {fmt!r} is not compatible with topic {topic.name} "
        f"({topic.msgtype}, {topic.category}). Allowed formats: {allowed}"
    )


def _is_image_topic(topic: TopicInfo) -> bool:
    return topic.msgtype in IMAGE_MSGTYPES or topic.category in IMAGE_CATEGORIES


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
    if fmt == "csv":
        return export_topic_csv(
            reader,
            topic,
            out,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )
    if fmt == "jsonl":
        return export_topic_jsonl(
            reader,
            topic,
            out,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )
    if fmt == "raw":
        return export_topic_raw(
            reader,
            topic,
            out,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )
    if fmt == "parquet":
        return export_topic_parquet(
            reader,
            topic,
            out,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )
    if fmt == "sqlite":
        return export_topic_sqlite(
            reader,
            topic,
            out,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )
    if fmt in {"png", "jpg"}:
        return export_topic_images(
            reader,
            topic,
            out,
            image_format=fmt,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )
    if fmt == "mp4":
        return export_topic_video(
            reader,
            topic,
            out,
            fps=fps,
            bag_start_timestamp_ns=bag_start_timestamp_ns,
            progress_callback=progress_callback,
        )
    raise ValueError(f"Unsupported implemented export format: {fmt}")


def default_export_formats(topic: TopicInfo) -> list[str]:
    decoded = bool(topic.sample_summary.get("decoded_available"))
    if topic.category in {"scalar", "text", "vector_struct", "pose", "odometry", "transform"}:
        return ["csv", "parquet", "jsonl", "sqlite"] if decoded else ["raw"]
    if topic.category in {"matrix_like", "custom_struct"}:
        return ["jsonl", "csv", "parquet", "sqlite"] if decoded else ["raw"]
    if topic.category in {"image", "compressed_image", "mask_candidate"}:
        return ["png"] if decoded else ["raw"]
    return ["raw"]


def _span_sec(start_ns: int | None, end_ns: int | None) -> float | None:
    if start_ns is None or end_ns is None:
        return None
    return (end_ns - start_ns) / 1e9


def _offset_sec(end_ns: int | None, start_ns: int | None) -> float | None:
    if start_ns is None or end_ns is None:
        return None
    return (end_ns - start_ns) / 1e9


def _total_message_count(topics: list[TopicInfo]) -> int | None:
    total = sum(topic.message_count for topic in topics if topic.message_count > 0)
    return total if total > 0 else None


def _reader_time_bounds(
    reader: object,
    topics: list[TopicInfo],
) -> tuple[int | None, int | None]:
    get_time_bounds = getattr(reader, "get_time_bounds", None)
    if callable(get_time_bounds):
        try:
            start, end = get_time_bounds()
        except Exception:
            start, end = None, None
        if start is not None and end is not None:
            return int(start), int(end)
    return time_bounds_from_topics(topics)


def _coverage_warnings(
    result: ExportResult, bag_start_ns: int | None, bag_end_ns: int | None
) -> list[str]:
    if (
        bag_start_ns is None
        or bag_end_ns is None
        or result.first_timestamp_ns is None
        or result.last_timestamp_ns is None
    ):
        return []
    starts_late = result.first_timestamp_ns > bag_start_ns
    ends_early = result.last_timestamp_ns < bag_end_ns
    if not starts_late and not ends_early:
        return []
    topic_span = (result.last_timestamp_ns - result.first_timestamp_ns) / 1e9
    bag_span = (bag_end_ns - bag_start_ns) / 1e9
    return [
        "Topic coverage differs from bag coverage: "
        f"topic {result.first_timestamp_ns}..{result.last_timestamp_ns} "
        f"({topic_span:.3f}s), bag {bag_start_ns}..{bag_end_ns} ({bag_span:.3f}s). "
        "No messages for this topic exist outside the topic timestamp range in the bag index."
    ]
