from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any


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


@dataclass(slots=True)
class PointCloudFieldSpec:
    name: str
    offset: int
    datatype: int
    count: int


def point_cloud_rows(message: object) -> list[dict[str, object]]:
    fields = [_field_spec(field) for field in getattr(message, "fields", [])]
    fields = [field for field in fields if field.datatype in POINT_FIELD_FORMATS]
    data = _data_bytes(getattr(message, "data", b""))
    point_step = int(getattr(message, "point_step", 0) or 0)
    row_step = int(getattr(message, "row_step", 0) or 0)
    width = int(getattr(message, "width", 0) or 0)
    height = int(getattr(message, "height", 0) or 0)
    is_bigendian = bool(getattr(message, "is_bigendian", False))
    if point_step <= 0 or not data:
        return []
    endian = ">" if is_bigendian else "<"

    rows: list[dict[str, object]] = []
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
                rows.append(row)
        return rows

    point_count = len(data) // point_step
    for point_index in range(point_count):
        base_offset = point_index * point_step
        row = {"point_index": point_index}
        for field in fields:
            row.update(_read_field(data, base_offset, point_step, field, endian))
        rows.append(row)
    return rows


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
