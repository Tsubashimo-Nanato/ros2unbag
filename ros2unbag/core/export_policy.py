from __future__ import annotations

from .models import TopicInfo


IMPLEMENTED_EXPORTS = {
    "csv",
    "jpg",
    "jsonl",
    "mp4",
    "npz",
    "parquet",
    "pcd",
    "ply",
    "png",
    "raw",
    "sqlite",
}
FUTURE_EXPORTS: dict[str, str] = {}
ALL_EXPORTS = IMPLEMENTED_EXPORTS | set(FUTURE_EXPORTS)

DATA_EXPORTS = ["csv", "jsonl", "npz", "parquet", "raw", "sqlite"]
IMAGE_EXPORTS = ["jpg", "mp4", "png"]
POINT_CLOUD_EXPORTS = ["pcd", "ply"]

IMAGE_MSGTYPES = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}
IMAGE_CATEGORIES = {"image", "compressed_image", "mask_candidate"}
POINT_CLOUD_MSGTYPES = {"sensor_msgs/msg/PointCloud2"}
POINT_CLOUD_CATEGORIES = {"point_cloud"}


def validate_export_format(fmt: str) -> str:
    normalized = fmt.lower()
    if normalized not in ALL_EXPORTS:
        allowed = ", ".join(sorted(ALL_EXPORTS))
        raise ValueError(f"Unsupported format {fmt!r}. Choose one of: {allowed}")
    return normalized


def compatible_export_formats(topic: TopicInfo) -> list[str]:
    formats = list(DATA_EXPORTS)
    if is_image_topic(topic):
        formats.extend(IMAGE_EXPORTS)
    if is_point_cloud_topic(topic):
        formats.extend(POINT_CLOUD_EXPORTS)
    return formats


def validate_topic_export_format(topic: TopicInfo, fmt: str) -> None:
    allowed_formats = compatible_export_formats(topic)
    if fmt in allowed_formats:
        return
    allowed = ", ".join(allowed_formats)
    raise ValueError(
        f"Format {fmt!r} is not compatible with topic {topic.name} "
        f"({topic.msgtype}, {topic.category}). Allowed formats: {allowed}"
    )


def default_export_formats(topic: TopicInfo) -> list[str]:
    decoded = bool(topic.sample_summary.get("decoded_available"))
    if topic.category in {"scalar", "text", "vector_struct", "pose", "odometry", "transform"}:
        return ["csv", "parquet", "jsonl", "sqlite"] if decoded else ["raw"]
    if topic.category in {"matrix_like", "custom_struct"}:
        return ["jsonl", "csv", "parquet", "sqlite"] if decoded else ["raw"]
    if topic.category in IMAGE_CATEGORIES:
        return ["png", "npz"] if decoded else ["raw"]
    if topic.category == "point_cloud":
        return ["pcd", "ply", "npz", "csv", "parquet", "sqlite", "jsonl"] if decoded else ["raw"]
    return ["raw"]


def suggested_exports_for_category(category: str) -> list[str]:
    if category in {"scalar", "text", "vector_struct", "pose", "odometry", "transform"}:
        return ["csv", "jsonl", "parquet", "sqlite"]
    if category in {"matrix_like", "custom_struct"}:
        return ["jsonl", "csv", "parquet", "sqlite"]
    if category in IMAGE_CATEGORIES:
        return ["png", "jpg", "mp4", "npz", "csv", "jsonl", "raw"]
    if category == "point_cloud":
        return ["pcd", "ply", "npz", "csv", "parquet", "sqlite", "jsonl", "raw"]
    return ["raw"]


def is_image_topic(topic: TopicInfo) -> bool:
    return topic.msgtype in IMAGE_MSGTYPES or topic.category in IMAGE_CATEGORIES


def is_point_cloud_topic(topic: TopicInfo) -> bool:
    return topic.msgtype in POINT_CLOUD_MSGTYPES or topic.category in POINT_CLOUD_CATEGORIES
