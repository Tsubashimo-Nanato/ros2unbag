from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TopicInfo:
    name: str
    msgtype: str
    serialization_format: str | None = None
    message_count: int = 0
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    duration_sec: float | None = None
    category: str = "unknown_raw"
    suggested_exports: list[str] = field(default_factory=list)
    sample_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TopicInfo":
        return cls(**data)


@dataclass(slots=True)
class MessageRecord:
    topic: str
    timestamp_ns: int
    msgtype: str
    raw: bytes | None = None
    decoded: object | None = None


@dataclass(slots=True)
class ExportResult:
    topic: str
    format: str
    output_path: str
    message_count: int = 0
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExportResult":
        return cls(**data)


@dataclass(slots=True)
class Manifest:
    source_bag_path: str
    created_at: str
    bag_start_timestamp_ns: int | None = None
    bag_end_timestamp_ns: int | None = None
    topics: list[TopicInfo] = field(default_factory=list)
    exports: list[ExportResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["topics"] = [topic.to_dict() for topic in self.topics]
        data["exports"] = [export.to_dict() for export in self.exports]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Manifest":
        copied = dict(data)
        copied["topics"] = [TopicInfo.from_dict(item) for item in copied.get("topics", [])]
        copied["exports"] = [
            ExportResult.from_dict(item) for item in copied.get("exports", [])
        ]
        return cls(**copied)


@dataclass(slots=True)
class TopicDuration:
    topic: str
    msgtype: str
    message_count: int
    first_timestamp_ns: int | None
    last_timestamp_ns: int | None
    topic_duration_sec: float | None
    bag_start_timestamp_ns: int | None
    bag_end_timestamp_ns: int | None
    bag_duration_sec: float | None
    start_offset_sec: float | None
    end_gap_sec: float | None
