from __future__ import annotations

import csv
from pathlib import Path

from ros2_unbag.core.decoder import ImageFrame, decode_compressed_image, decode_sensor_image
from ros2_unbag.core.manifest import sanitize_topic_name
from ros2_unbag.core.models import ExportResult


def export_topic_images(
    reader: object,
    topic: str,
    out_dir: str | Path,
    *,
    image_format: str,
    bag_start_timestamp_ns: int | None = None,
) -> ExportResult:
    """Export image messages as a PNG/JPG sequence with timestamps.csv."""
    fmt = image_format.lower()
    if fmt not in {"png", "jpg", "jpeg"}:
        raise ValueError(f"Unsupported image sequence format: {image_format}")
    suffix = "jpg" if fmt == "jpeg" else fmt
    output_dir = Path(out_dir) / "images" / sanitize_topic_name(topic)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamps_path = output_dir / "timestamps.csv"
    warnings: list[str] = []
    source_count = 0
    frame_count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None

    import cv2

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
                frame = _decode_record_frame(record)
            except Exception as exc:
                warnings.append(f"Skipped message at {record.timestamp_ns}: {exc}")
                continue
            warnings.extend(frame.warnings)
            filename = f"{frame_count:06d}.{suffix}"
            image = _image_for_still(frame, suffix)
            if not cv2.imwrite(str(output_dir / filename), image):
                warnings.append(f"cv2.imwrite failed for {filename}")
                continue
            writer.writerow(
                {
                    "frame_index": frame_count,
                    "timestamp_ns": record.timestamp_ns,
                    "timestamp_sec_from_start": _sec_from_start(
                        record.timestamp_ns, bag_start_timestamp_ns
                    ),
                    "filename": filename,
                    "width": frame.width,
                    "height": frame.height,
                    "encoding": frame.encoding,
                }
            )
            frame_count += 1

    if source_count and frame_count != source_count:
        warnings.append(f"Exported {frame_count} frames from {source_count} source messages.")

    return ExportResult(
        topic=topic,
        format=suffix,
        output_path=str(output_dir),
        message_count=frame_count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        warnings=sorted(set(warnings)),
    )


def _decode_record_frame(record: object) -> ImageFrame:
    decoded = getattr(record, "decoded", None)
    if decoded is None:
        raise ValueError("message was not decoded")
    msgtype = str(getattr(record, "msgtype", ""))
    if msgtype == "sensor_msgs/msg/Image":
        return decode_sensor_image(decoded)
    if msgtype == "sensor_msgs/msg/CompressedImage":
        return decode_compressed_image(decoded)
    raise ValueError(f"topic type {msgtype} is not an image type")


def _image_for_still(frame: ImageFrame, suffix: str) -> object:
    import cv2

    image = frame.array
    if suffix == "jpg" and getattr(image, "ndim", 0) == 3 and image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def _sec_from_start(timestamp_ns: int, bag_start_timestamp_ns: int | None) -> float | None:
    if bag_start_timestamp_ns is None:
        return None
    return (timestamp_ns - bag_start_timestamp_ns) / 1e9
