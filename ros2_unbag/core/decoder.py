from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


SCALAR_TYPES = (str, int, float, bool, type(None))


@dataclass(slots=True)
class ImageFrame:
    array: Any
    width: int
    height: int
    encoding: str
    source_format: str
    warnings: list[str] = field(default_factory=list)


def is_scalar(value: Any) -> bool:
    return isinstance(value, SCALAR_TYPES)


def is_numeric_scalar(value: Any) -> bool:
    return isinstance(value, (int, float, bool))


def bytes_to_jsonable(value: bytes) -> dict[str, Any]:
    return {
        "__type__": "bytes",
        "encoding": "base64",
        "byte_length": len(value),
        "sha256": hashlib.sha256(value).hexdigest(),
        "data": base64.b64encode(value).decode("ascii"),
    }


def message_to_plain(value: Any) -> Any:
    """Convert dataclass/ROS-like/numpy values into JSON-friendly containers."""
    if is_scalar(value):
        return value
    if isinstance(value, bytes):
        return bytes_to_jsonable(value)
    if isinstance(value, bytearray):
        return bytes_to_jsonable(bytes(value))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: message_to_plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if not field.name.startswith("_")
        }
    if isinstance(value, Mapping):
        return {str(key): message_to_plain(item) for key, item in value.items()}
    if hasattr(value, "tolist") and callable(value.tolist):
        return message_to_plain(value.tolist())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [message_to_plain(item) for item in value]
    if hasattr(value, "_asdict") and callable(value._asdict):
        return {str(key): message_to_plain(item) for key, item in value._asdict().items()}
    if hasattr(value, "__slots__"):
        result: dict[str, Any] = {}
        for slot in value.__slots__:
            if slot.startswith("_"):
                continue
            if hasattr(value, slot):
                result[slot] = message_to_plain(getattr(value, slot))
        if result:
            return result
    if hasattr(value, "__dict__"):
        return {
            str(key): message_to_plain(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(message_to_plain(value), sort_keys=True, separators=(",", ":"))


def flatten_message(value: Any, *, array_expand_limit: int = 16) -> dict[str, Any]:
    plain = message_to_plain(value)
    flattened: dict[str, Any] = {}

    def visit(prefix: str, item: Any) -> None:
        if isinstance(item, Mapping):
            if not item:
                flattened[prefix or "value"] = "{}"
                return
            for key in sorted(item):
                child = f"{prefix}.{key}" if prefix else str(key)
                visit(child, item[key])
            return
        if isinstance(item, list):
            if not item:
                flattened[prefix or "value"] = "[]"
                return
            if len(item) <= array_expand_limit and all(is_scalar(entry) for entry in item):
                for index, entry in enumerate(item):
                    flattened[f"{prefix}.{index}"] = entry
            else:
                flattened[prefix] = _json_dumps(item)
            return
        if is_scalar(item):
            flattened[prefix] = item
            return
        flattened[prefix] = _json_dumps(item)

    if isinstance(plain, Mapping):
        for key in sorted(plain):
            visit(str(key), plain[key])
    else:
        visit("value", plain)
    return flattened


def summarize_message(decoded: object | None, raw: bytes | None = None) -> dict[str, Any]:
    if decoded is None:
        return {
            "decoded": False,
            "raw_byte_length": len(raw) if raw is not None else None,
            "summary": "raw serialized message",
        }

    image_summary = _image_summary_from_object(decoded)
    if image_summary is not None:
        return image_summary

    plain = message_to_plain(decoded)
    if isinstance(plain, Mapping):
        image_bits = _image_summary_from_mapping(plain)
        if image_bits is not None:
            return image_bits
        flattened = flatten_message(plain)
        preview = {
            key: value
            for key, value in list(flattened.items())[:10]
            if is_scalar(value) and key != "data.data"
        }
        return {
            "decoded": True,
            "decoded_type": type(decoded).__name__,
            "field_count": len(flattened),
            "preview": preview,
            "summary": ", ".join(f"{key}={value}" for key, value in preview.items())[:240]
            or type(decoded).__name__,
        }

    return {
        "decoded": True,
        "decoded_type": type(decoded).__name__,
        "value": plain,
        "summary": str(plain)[:240],
    }


def _image_summary_from_object(message: object) -> dict[str, Any] | None:
    if not hasattr(message, "width") or not hasattr(message, "height"):
        return None
    width = getattr(message, "width", None)
    height = getattr(message, "height", None)
    if not isinstance(width, int) or not isinstance(height, int):
        return None
    encoding = getattr(message, "encoding", None)
    return {
        "decoded": True,
        "kind": "image",
        "width": width,
        "height": height,
        "encoding": encoding,
        "step": getattr(message, "step", None),
        "summary": f"image {width}x{height} {encoding or ''}".strip(),
    }


def _image_summary_from_mapping(data: Mapping[str, Any]) -> dict[str, Any] | None:
    if not {"width", "height"}.issubset(data):
        return None
    encoding = data.get("encoding")
    width = data.get("width")
    height = data.get("height")
    if not isinstance(width, int) or not isinstance(height, int):
        return None
    return {
        "decoded": True,
        "kind": "image",
        "width": width,
        "height": height,
        "encoding": encoding,
        "step": data.get("step"),
        "summary": f"image {width}x{height} {encoding or ''}".strip(),
    }


def summarize_samples(records: list[Any]) -> dict[str, Any]:
    decoded_count = sum(1 for record in records if record.decoded is not None)
    raw_lengths = [len(record.raw) for record in records if record.raw is not None]
    first = records[0] if records else None
    summary = summarize_message(first.decoded, first.raw) if first else {}
    result = {
        "sample_count": len(records),
        "decoded_available": decoded_count > 0,
        "decoded_sample_count": decoded_count,
        "raw_byte_lengths": raw_lengths[:5],
        "first_sample": summary,
    }
    mask_detection = _mask_detection_summary(records)
    if mask_detection is not None:
        result["mask_detection"] = mask_detection
    return result


def _mask_detection_summary(records: list[Any]) -> dict[str, Any] | None:
    import numpy as np

    checked = 0
    binary_like = 0
    unique_values: list[int | float | str] = []
    evidence: list[str] = []
    decode_warnings: list[str] = []
    supported_grayscale_encodings = {"mono8", "8uc1"}

    for record in records:
        decoded = getattr(record, "decoded", None)
        if decoded is None:
            continue
        msgtype = str(getattr(record, "msgtype", ""))
        if msgtype not in {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}:
            continue
        try:
            if msgtype == "sensor_msgs/msg/Image":
                frame = decode_sensor_image(decoded)
                grayscale_encoding = frame.encoding.lower() in supported_grayscale_encodings
            else:
                frame = decode_compressed_image(decoded)
                grayscale_encoding = bool(getattr(frame.array, "ndim", 0) == 2)
        except Exception as exc:
            decode_warnings.append(str(exc))
            continue

        checked += 1
        array = frame.array
        if not grayscale_encoding or getattr(array, "ndim", 0) != 2:
            evidence.append(f"{frame.encoding} is not a supported single-channel mask encoding")
            continue

        values = np.unique(array)
        clipped_values = values[:16].tolist()
        if not unique_values:
            unique_values = [int(value) for value in clipped_values]
        binary_values = {0, 1, 255}
        value_set = {int(value) for value in values.tolist()}
        is_binary_like = len(value_set) <= 3 and value_set.issubset(binary_values)
        if is_binary_like:
            binary_like += 1
            evidence.append(f"{frame.encoding} unique values {sorted(value_set)}")
        else:
            evidence.append(f"{frame.encoding} has {len(value_set)} unique values")

    if checked == 0:
        if decode_warnings:
            return {
                "checked_frames": 0,
                "unique_values_mostly_binary": False,
                "confidence": 0.0,
                "evidence": decode_warnings[:3],
            }
        return None

    confidence = binary_like / checked
    return {
        "checked_frames": checked,
        "binary_like_frames": binary_like,
        "unique_values": unique_values,
        "unique_values_mostly_binary": confidence >= 0.66,
        "confidence": round(confidence, 3),
        "evidence": evidence[:5],
    }


def decode_sensor_image(_message: object) -> Any:
    """Decode common 8-bit sensor_msgs/Image encodings into OpenCV-compatible arrays.

    Color images are returned in OpenCV channel order so image/video exporters can
    write frames without guessing whether conversion has already happened.
    """
    import cv2
    import numpy as np

    height = int(getattr(_message, "height"))
    width = int(getattr(_message, "width"))
    encoding = str(getattr(_message, "encoding", "")).lower()
    step = int(getattr(_message, "step", 0) or 0)
    data = _raw_image_bytes(getattr(_message, "data", b""))
    warnings: list[str] = []

    channels_by_encoding = {
        "mono8": 1,
        "8uc1": 1,
        "rgb8": 3,
        "bgr8": 3,
        "rgba8": 4,
        "bgra8": 4,
    }
    channels = channels_by_encoding.get(encoding)
    if channels is None:
        raise ValueError(f"Unsupported sensor_msgs/Image encoding: {encoding!r}")

    bytes_per_pixel = channels
    expected_row_bytes = width * bytes_per_pixel
    if step == 0:
        step = expected_row_bytes
    if step < expected_row_bytes:
        raise ValueError(
            f"Image step {step} is smaller than expected row bytes {expected_row_bytes}"
        )
    required = step * height
    if len(data) < required:
        raise ValueError(f"Image data has {len(data)} bytes but {required} are required")
    if len(data) > required:
        warnings.append(f"Ignored {len(data) - required} trailing image data bytes.")

    flat = np.frombuffer(data[:required], dtype=np.uint8)
    rows = flat.reshape(height, step)
    packed = rows[:, :expected_row_bytes]
    if channels == 1:
        array = packed.reshape(height, width).copy()
    else:
        array = packed.reshape(height, width, channels).copy()

    if encoding == "rgb8":
        array = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    elif encoding == "rgba8":
        array = cv2.cvtColor(array, cv2.COLOR_RGBA2BGRA)

    return ImageFrame(
        array=array,
        width=width,
        height=height,
        encoding=encoding,
        source_format="sensor_msgs/msg/Image",
        warnings=warnings,
    )


def decode_compressed_image(_message: object) -> Any:
    """Decode sensor_msgs/msg/CompressedImage with cv2.imdecode."""
    import cv2
    import numpy as np

    data = _raw_image_bytes(getattr(_message, "data", b""))
    encoded = np.frombuffer(data, dtype=np.uint8)
    array = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if array is None:
        raise ValueError("cv2.imdecode could not decode compressed image data")
    height, width = array.shape[:2]
    encoding = str(getattr(_message, "format", "compressed") or "compressed")
    return ImageFrame(
        array=array,
        width=int(width),
        height=int(height),
        encoding=encoding,
        source_format="sensor_msgs/msg/CompressedImage",
    )


def _raw_image_bytes(data: Any) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, memoryview):
        return data.tobytes()
    if hasattr(data, "tobytes") and callable(data.tobytes):
        return data.tobytes()
    if isinstance(data, list):
        return bytes(data)
    return bytes(data)
