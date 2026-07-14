from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Iterator


POINT_FIELD_FORMATS: dict[int, tuple[str, int]] = {
    1: ("b", 1),   # INT8
    2: ("B", 1),   # UINT8
    3: ("h", 2),   # INT16
    4: ("H", 2),   # UINT16
    5: ("i", 4),   # INT32
    6: ("I", 4),   # UINT32
    7: ("f", 4),   # FLOAT32
    8: ("d", 8),   # FLOAT64
}

POINT_FIELD_TYPES: dict[int, str] = {
    1: "I",   # INT8
    2: "U",   # UINT8
    3: "I",   # INT16
    4: "U",   # UINT16
    5: "I",   # INT32
    6: "U",   # UINT32
    7: "F",   # FLOAT32
    8: "F",   # FLOAT64
}

PLY_FIELD_TYPES: dict[int, str] = {
    1: "char",
    2: "uchar",
    3: "short",
    4: "ushort",
    5: "int",
    6: "uint",
    7: "float",
    8: "double",
}


@dataclass(slots=True)
class PointCloudFieldSpec:
    name: str
    offset: int
    datatype: int
    count: int


def point_cloud_rows(message: object) -> list[dict[str, object]]:
    return list(iter_point_cloud_rows(message))


def iter_point_cloud_rows(message: object) -> Iterator[dict[str, object]]:
    fields = [_field_spec(field) for field in getattr(message, "fields", [])]
    fields = [field for field in fields if field.datatype in POINT_FIELD_FORMATS]
    data = _data_bytes(getattr(message, "data", b""))
    point_step = int(getattr(message, "point_step", 0) or 0)
    row_step = int(getattr(message, "row_step", 0) or 0)
    width = int(getattr(message, "width", 0) or 0)
    height = int(getattr(message, "height", 0) or 0)
    is_bigendian = bool(getattr(message, "is_bigendian", False))
    if point_step <= 0 or not data:
        return
    endian = ">" if is_bigendian else "<"

    if width > 0 and height > 0:
        row_stride = row_step if row_step >= width * point_step else width * point_step
        for cloud_row in range(height):
            for cloud_col in range(width):
                point_index = (cloud_row * width) + cloud_col
                base_offset = (cloud_row * row_stride) + (cloud_col * point_step)
                if base_offset + point_step > len(data):
                    continue
                row: dict[str, object] = {
                    "point_index": point_index,
                    "cloud_row": cloud_row,
                    "cloud_col": cloud_col,
                }
                for field in fields:
                    row.update(_read_field(data, base_offset, point_step, field, endian))
                yield row
        return

    point_count = len(data) // point_step
    for point_index in range(point_count):
        base_offset = point_index * point_step
        row = {"point_index": point_index}
        for field in fields:
            row.update(_read_field(data, base_offset, point_step, field, endian))
        yield row


def point_cloud_field_names(message: object) -> list[str]:
    names: list[str] = ["point_index", "cloud_row", "cloud_col"]
    for field in getattr(message, "fields", []):
        spec = _field_spec(field)
        if spec.datatype not in POINT_FIELD_FORMATS:
            continue
        if spec.count <= 1:
            names.append(spec.name)
        else:
            names.extend(f"{spec.name}.{index}" for index in range(spec.count))
    return names


def point_cloud_field_specs(message: object) -> list[PointCloudFieldSpec]:
    specs = [_field_spec(field) for field in getattr(message, "fields", [])]
    return [spec for spec in specs if spec.datatype in POINT_FIELD_FORMATS]


def point_cloud_point_count(message: object) -> int:
    declared_count = point_cloud_declared_point_count(message)
    if declared_count is not None:
        return declared_count
    return sum(1 for _row in iter_point_cloud_rows(message))


def point_cloud_declared_point_count(message: object) -> int | None:
    """Return a metadata-derived point count when the payload length supports it."""
    width = int(getattr(message, "width", 0) or 0)
    height = int(getattr(message, "height", 0) or 0)
    data = _data_bytes(getattr(message, "data", b""))
    point_step = int(getattr(message, "point_step", 0) or 0)
    if point_step <= 0:
        return 0 if not data else None
    if width > 0 and height > 0:
        row_step = int(getattr(message, "row_step", 0) or 0)
        row_stride = row_step if row_step >= width * point_step else width * point_step
        required_length = ((height - 1) * row_stride) + (width * point_step)
        return width * height if len(data) >= required_length else None
    return len(data) // point_step


def expanded_point_field_names(message: object) -> list[str]:
    names: list[str] = []
    for spec in point_cloud_field_specs(message):
        if spec.count <= 1:
            names.append(_safe_field_name(spec.name))
        else:
            names.extend(f"{_safe_field_name(spec.name)}_{index}" for index in range(spec.count))
    return names


def expanded_point_row(message: object, row: dict[str, object]) -> list[object]:
    values: list[object] = []
    for spec in point_cloud_field_specs(message):
        if spec.count <= 1:
            values.append(row.get(spec.name, 0))
        else:
            for index in range(spec.count):
                values.append(row.get(f"{spec.name}.{index}", 0))
    return values


def point_field_pcd_size(spec: PointCloudFieldSpec) -> int:
    return POINT_FIELD_FORMATS[spec.datatype][1]


def point_field_pcd_type(spec: PointCloudFieldSpec) -> str:
    return POINT_FIELD_TYPES[spec.datatype]


def point_field_ply_type(spec: PointCloudFieldSpec) -> str:
    return PLY_FIELD_TYPES[spec.datatype]


def _safe_field_name(name: str) -> str:
    safe = "".join(char if char.isalnum() or char == "_" else "_" for char in name.strip())
    return safe or "field"


def _field_spec(field: object) -> PointCloudFieldSpec:
    return PointCloudFieldSpec(
        name=str(getattr(field, "name", "")),
        offset=int(getattr(field, "offset", 0) or 0),
        datatype=int(getattr(field, "datatype", 0) or 0),
        count=max(1, int(getattr(field, "count", 1) or 1)),
    )


def _read_field(
    data: bytes, base_offset: int, point_step: int, field: PointCloudFieldSpec, endian: str
) -> dict[str, object]:
    fmt, size = POINT_FIELD_FORMATS[field.datatype]
    values: dict[str, object] = {}
    for index in range(field.count):
        offset = base_offset + field.offset + (index * size)
        if offset + size > len(data) or offset + size > base_offset + point_step:
            continue
        value = struct.unpack_from(endian + fmt, data, offset)[0]
        key = field.name if field.count == 1 else f"{field.name}.{index}"
        values[key] = value
    return values


def _data_bytes(data: Any) -> bytes:
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
