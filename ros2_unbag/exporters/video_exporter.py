from __future__ import annotations

import csv
from pathlib import Path

from ros2_unbag.core.decoder import ImageFrame
from ros2_unbag.core.manifest import sanitize_topic_name
from ros2_unbag.core.models import ExportResult
from ros2_unbag.exporters.image_exporter import _decode_record_frame


def export_topic_video(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    fps: float = 30.0,
    bag_start_timestamp_ns: int | None = None,
    mode: str = "constant_fps",
) -> ExportResult:
    """Export image messages to MP4 with a true timestamp CSV sidecar."""
    if fps <= 0:
        raise ValueError("fps must be greater than zero")
    if mode != "constant_fps":
        raise ValueError("Only constant_fps video export is implemented")

    import cv2

    output_dir = Path(out_dir) / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_topic_name(topic)
    video_path = output_dir / f"{safe_name}.mp4"
    timestamps_path = output_dir / f"{safe_name}_timestamps.csv"
    warnings: list[str] = [
        "MP4 is written at constant FPS; timestamp sidecar contains true ROS timestamps."
    ]
    source_count = 0
    frame_count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    writer: object | None = None
    frame_size: tuple[int, int] | None = None

    with timestamps_path.open("w", newline="", encoding="utf-8") as handle:
        csv_writer = csv.DictWriter(
            handle,
            fieldnames=[
                "frame_index",
                "timestamp_ns",
                "timestamp_sec_from_start",
                "video_time_sec",
                "width",
                "height",
                "encoding",
            ],
        )
        csv_writer.writeheader()
        try:
            for record in reader.iter_messages(topics=[topic]):
                source_count += 1
                first_timestamp = record.timestamp_ns if first_timestamp is None else first_timestamp
                last_timestamp = record.timestamp_ns
                try:
                    frame = _decode_record_frame(record)
                    image = _image_for_video(frame)
                except Exception as exc:
                    warnings.append(f"Skipped message at {record.timestamp_ns}: {exc}")
                    continue
                warnings.extend(frame.warnings)
                current_size = (int(image.shape[1]), int(image.shape[0]))
                if writer is None:
                    frame_size = current_size
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(str(video_path), fourcc, fps, frame_size)
                    if not writer.isOpened():
                        raise ValueError(f"Could not open VideoWriter for {video_path}")
                elif current_size != frame_size:
                    warnings.append(
                        f"Skipped frame at {record.timestamp_ns}: size {current_size} != {frame_size}"
                    )
                    continue
                writer.write(image)
                csv_writer.writerow(
                    {
                        "frame_index": frame_count,
                        "timestamp_ns": record.timestamp_ns,
                        "timestamp_sec_from_start": _sec_from_start(
                            record.timestamp_ns, bag_start_timestamp_ns
                        ),
                        "video_time_sec": frame_count / fps,
                        "width": current_size[0],
                        "height": current_size[1],
                        "encoding": frame.encoding,
                    }
                )
                frame_count += 1
        finally:
            if writer is not None:
                writer.release()

    if source_count and frame_count != source_count:
        warnings.append(f"Exported {frame_count} video frames from {source_count} source messages.")
    if frame_count == 0:
        warnings.append("No video frames were written.")

    return ExportResult(
        topic=topic,
        format="mp4",
        output_path=str(video_path),
        message_count=frame_count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _image_for_video(frame: ImageFrame) -> object:
    import cv2

    image = frame.array
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    if image.ndim == 3 and image.shape[2] == 3:
        return image
    raise ValueError(f"Unsupported decoded image shape for video: {image.shape}")


def _sec_from_start(timestamp_ns: int, bag_start_timestamp_ns: int | None) -> float | None:
    if bag_start_timestamp_ns is None:
        return None
    return (timestamp_ns - bag_start_timestamp_ns) / 1e9
