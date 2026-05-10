from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .decoder import flatten_message, is_scalar, message_to_plain
from .models import MessageRecord, TopicInfo


NUMERIC_STD_MSGS = {
    "std_msgs/msg/Float32",
    "std_msgs/msg/Float64",
    "std_msgs/msg/Int32",
    "std_msgs/msg/Int64",
    "std_msgs/msg/UInt32",
    "std_msgs/msg/UInt64",
    "std_msgs/msg/Bool",
}

KNOWN_CATEGORIES = {
    **{msgtype: "scalar" for msgtype in NUMERIC_STD_MSGS},
    "std_msgs/msg/String": "text",
    "geometry_msgs/msg/Twist": "vector_struct",
    "geometry_msgs/msg/TwistStamped": "vector_struct",
    "geometry_msgs/msg/Vector3": "vector_struct",
    "geometry_msgs/msg/Vector3Stamped": "vector_struct",
    "geometry_msgs/msg/Point": "vector_struct",
    "geometry_msgs/msg/PointStamped": "vector_struct",
    "geometry_msgs/msg/Pose": "pose",
    "geometry_msgs/msg/PoseStamped": "pose",
    "geometry_msgs/msg/PoseWithCovariance": "pose",
    "geometry_msgs/msg/PoseWithCovarianceStamped": "pose",
    "nav_msgs/msg/Odometry": "odometry",
    "sensor_msgs/msg/Image": "image",
    "sensor_msgs/msg/CompressedImage": "compressed_image",
    "sensor_msgs/msg/PointCloud2": "point_cloud",
    "sensor_msgs/msg/Imu": "vector_struct",
    "sensor_msgs/msg/MagneticField": "vector_struct",
    "sensor_msgs/msg/NavSatFix": "vector_struct",
    "sensor_msgs/msg/Temperature": "scalar",
    "sensor_msgs/msg/CameraInfo": "matrix_like",
    "tf2_msgs/msg/TFMessage": "transform",
}

MASK_NAME_HINTS = ("mask", "seg", "segmentation", "lane", "binary")


def classify_topic(topic_info: TopicInfo, sample_messages: list[MessageRecord]) -> str:
    category = KNOWN_CATEGORIES.get(topic_info.msgtype)
    if category == "image" and _decoded_mask_evidence(topic_info, sample_messages):
        return "mask_candidate"
    if category is not None:
        return category

    decoded = [record.decoded for record in sample_messages if record.decoded is not None]
    if not decoded:
        return "unknown_raw"

    if _has_flat_numeric_fields(decoded[0]):
        return "vector_struct"
    if _has_nested_arrays(decoded[0]):
        return "matrix_like"
    return "custom_struct"


def suggested_exports_for_category(category: str) -> list[str]:
    if category in {"scalar", "text", "vector_struct", "pose", "odometry", "transform"}:
        return ["csv", "jsonl", "parquet", "sqlite"]
    if category in {"matrix_like", "custom_struct"}:
        return ["jsonl", "csv", "parquet", "sqlite"]
    if category in {"image", "compressed_image", "mask_candidate"}:
        return ["png", "jpg", "mp4", "raw"]
    if category == "point_cloud":
        return ["csv", "parquet", "sqlite", "raw"]
    return ["raw"]


def _decoded_mask_evidence(topic_info: TopicInfo, sample_messages: list[MessageRecord]) -> bool:
    has_name_hint = any(hint in topic_info.name.lower() for hint in MASK_NAME_HINTS)
    sample_summary = topic_info.sample_summary or {}
    evidence = sample_summary.get("mask_detection", {})
    confidence = float(evidence.get("confidence") or 0.0)
    is_binary_like = evidence.get("unique_values_mostly_binary") is True
    has_decoded_image = any(record.decoded is not None for record in sample_messages)
    return bool(has_decoded_image and is_binary_like and (confidence >= 0.75 or has_name_hint))


def _has_flat_numeric_fields(message: object) -> bool:
    flattened = flatten_message(message)
    values = [value for value in flattened.values() if is_scalar(value)]
    if not values:
        return False
    numeric = [value for value in values if isinstance(value, (int, float, bool))]
    return len(numeric) >= max(1, len(values) // 2)


def _has_nested_arrays(message: object) -> bool:
    plain = message_to_plain(message)
    return _contains_nested_sequence(plain)


def _contains_nested_sequence(value: Any, *, depth: int = 0) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_nested_sequence(item, depth=depth) for item in value.values())
    if isinstance(value, list):
        if depth > 0:
            return True
        return any(_contains_nested_sequence(item, depth=depth + 1) for item in value)
    return False
