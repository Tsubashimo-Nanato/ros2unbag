from __future__ import annotations

import heapq
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from types import TracebackType
from typing import Iterator, Sequence

from .models import MessageRecord, TopicInfo


class BaseBagReader(ABC):
    def __init__(self) -> None:
        self.path: Path | None = None
        self.warnings: list[str] = []

    @abstractmethod
    def open(self, path: str | Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_topics(self) -> list[TopicInfo]:
        raise NotImplementedError

    @abstractmethod
    def iter_messages(self, topics: list[str] | None = None) -> Iterator[MessageRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_message_count(self, topic: str) -> int:
        raise NotImplementedError

    def get_time_bounds(self) -> tuple[int | None, int | None]:
        """Return bag start/end timestamps from metadata when available."""
        return time_bounds_from_topics(self.get_topics())

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> "BaseBagReader":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class RosbagsReader(BaseBagReader):
    """Preferred backend using rosbags.highlevel.AnyReader when available."""

    def __init__(self) -> None:
        super().__init__()
        self._reader: object | None = None
        self._connections: list[object] = []
        self._topics: dict[str, TopicInfo] = {}
        self._decode_warnings_seen: set[tuple[str, str]] = set()

    def open(self, path: str | Path) -> None:
        self.path = Path(path)
        try:
            from rosbags.highlevel import AnyReader
        except Exception as exc:  # pragma: no cover - exercised when optional dep missing.
            raise RuntimeError("rosbags is not installed") from exc

        reader = None
        last_error: Exception | None = None
        used_typestore = None
        for typestore_name, typestore in _typestore_candidates():
            candidate = AnyReader(
                [self.path],
                **({"default_typestore": typestore} if typestore is not None else {}),
            )
            try:
                candidate.open()
                reader = candidate
                used_typestore = typestore_name
                break
            except Exception as exc:
                last_error = exc
        if reader is None:
            raise RuntimeError(f"Could not open bag with rosbags: {last_error}") from last_error
        if used_typestore is not None:
            self.warnings.append(
                f"Bag did not provide complete type definitions; using rosbags typestore {used_typestore}."
            )
        self._reader = reader
        self._connections = list(getattr(reader, "connections", []))
        self._topics = {}
        for connection in self._connections:
            topic = str(getattr(connection, "topic"))
            msgtype = str(getattr(connection, "msgtype", ""))
            serialization_format = _connection_serialization_format(connection)
            count = int(getattr(connection, "msgcount", 0) or 0)
            self._topics[topic] = TopicInfo(
                name=topic,
                msgtype=msgtype,
                serialization_format=serialization_format,
                message_count=count,
            )

    def get_topics(self) -> list[TopicInfo]:
        return [self._topics[key] for key in sorted(self._topics)]

    def iter_messages(self, topics: list[str] | None = None) -> Iterator[MessageRecord]:
        if self._reader is None:
            raise RuntimeError("Reader is not open")
        topic_filter = set(topics) if topics else None
        connections = [
            connection
            for connection in self._connections
            if topic_filter is None or getattr(connection, "topic") in topic_filter
        ]
        for connection, timestamp, rawdata in self._reader.messages(connections=connections):
            raw = bytes(rawdata)
            msgtype = str(getattr(connection, "msgtype", ""))
            topic = str(getattr(connection, "topic"))
            decoded = None
            try:
                decoded = self._reader.deserialize(rawdata, msgtype)
            except Exception as exc:
                key = (topic, type(exc).__name__)
                if key not in self._decode_warnings_seen:
                    self.warnings.append(
                        f"Could not deserialize {topic} ({msgtype}); keeping raw bytes: {exc}"
                    )
                    self._decode_warnings_seen.add(key)
            yield MessageRecord(
                topic=topic,
                timestamp_ns=int(timestamp),
                msgtype=msgtype,
                raw=raw,
                decoded=decoded,
            )

    def get_message_count(self, topic: str) -> int:
        return self._topics.get(topic, TopicInfo(topic, "")).message_count

    def get_time_bounds(self) -> tuple[int | None, int | None]:
        if self._reader is None:
            raise RuntimeError("Reader is not open")
        start = _optional_int(getattr(self._reader, "start_time", None))
        end = _optional_int(getattr(self._reader, "end_time", None))
        if start is not None and end is not None:
            return start, end
        return super().get_time_bounds()

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
        self._reader = None
        self._connections = []


class SqliteRosbag2Reader(BaseBagReader):
    """Minimal ROS 2 sqlite3 fallback.

    This backend does not deserialize CDR payloads. It is intentionally useful for
    Phase 1 scans, timestamp indexes, and raw exports on machines without ROS or
    rosbags installed.
    """

    def __init__(self) -> None:
        super().__init__()
        self._db_paths: list[Path] = []
        self._connections: list[sqlite3.Connection] = []
        self._topics: dict[str, TopicInfo] = {}
        self._topic_maps: list[dict[int, tuple[str, str]]] = []

    def open(self, path: str | Path) -> None:
        self.path = Path(path)
        self._db_paths = _discover_sqlite_bags(self.path)
        if not self._db_paths:
            raise FileNotFoundError(f"No rosbag2 sqlite .db3 files found under {self.path}")
        self.warnings.append(
            "Using sqlite3 fallback backend; messages are not deserialized. "
            "Install rosbags for decoded CSV/JSONL exports."
        )
        self._connections = []
        self._topic_maps = []
        self._topics = {}
        for db_path in self._db_paths:
            connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            self._connections.append(connection)
            topic_map: dict[int, tuple[str, str]] = {}
            for row in connection.execute(
                "select id, name, type, serialization_format from topics order by name"
            ):
                topic_map[int(row["id"])] = (str(row["name"]), str(row["type"]))
                existing = self._topics.get(str(row["name"]))
                if existing is None:
                    self._topics[str(row["name"])] = TopicInfo(
                        name=str(row["name"]),
                        msgtype=str(row["type"]),
                        serialization_format=str(row["serialization_format"]),
                    )
            self._topic_maps.append(topic_map)
            self._load_counts(connection)

    def _load_counts(self, connection: sqlite3.Connection) -> None:
        query = """
            select
                t.name as topic,
                t.type as msgtype,
                t.serialization_format as serialization_format,
                count(m.id) as message_count,
                min(m.timestamp) as first_timestamp_ns,
                max(m.timestamp) as last_timestamp_ns
            from topics t
            left join messages m on m.topic_id = t.id
            group by t.id, t.name, t.type, t.serialization_format
            order by t.name
        """
        for row in connection.execute(query):
            topic = str(row["topic"])
            info = self._topics.setdefault(
                topic,
                TopicInfo(
                    name=topic,
                    msgtype=str(row["msgtype"]),
                    serialization_format=str(row["serialization_format"]),
                ),
            )
            count = int(row["message_count"] or 0)
            info.message_count += count
            first = row["first_timestamp_ns"]
            last = row["last_timestamp_ns"]
            if first is not None:
                first = int(first)
                if info.first_timestamp_ns is None or first < info.first_timestamp_ns:
                    info.first_timestamp_ns = first
            if last is not None:
                last = int(last)
                if info.last_timestamp_ns is None or last > info.last_timestamp_ns:
                    info.last_timestamp_ns = last
            if info.first_timestamp_ns is not None and info.last_timestamp_ns is not None:
                info.duration_sec = (info.last_timestamp_ns - info.first_timestamp_ns) / 1e9

    def get_topics(self) -> list[TopicInfo]:
        return [self._topics[key] for key in sorted(self._topics)]

    def iter_messages(self, topics: list[str] | None = None) -> Iterator[MessageRecord]:
        if not self._connections:
            raise RuntimeError("Reader is not open")
        topic_filter = set(topics) if topics else None
        heap: list[tuple[int, int, sqlite3.Row, Iterator[sqlite3.Row]]] = []
        for order, connection in enumerate(self._connections):
            iterator = self._iter_connection_rows(connection, topic_filter)
            try:
                row = next(iterator)
            except StopIteration:
                continue
            heapq.heappush(heap, (int(row["timestamp"]), order, row, iterator))
        while heap:
            _timestamp, order, row, iterator = heapq.heappop(heap)
            raw = bytes(row["data"])
            yield MessageRecord(
                topic=str(row["topic"]),
                timestamp_ns=int(row["timestamp"]),
                msgtype=str(row["msgtype"]),
                raw=raw,
                decoded=None,
            )
            try:
                next_row = next(iterator)
            except StopIteration:
                continue
            heapq.heappush(heap, (int(next_row["timestamp"]), order, next_row, iterator))

    def _iter_connection_rows(
        self, connection: sqlite3.Connection, topic_filter: set[str] | None
    ) -> Iterator[sqlite3.Row]:
        params: list[str] = []
        where = ""
        if topic_filter:
            placeholders = ",".join("?" for _ in topic_filter)
            where = f"where t.name in ({placeholders})"
            params = sorted(topic_filter)
        query = f"""
            select
                t.name as topic,
                t.type as msgtype,
                m.timestamp as timestamp,
                m.data as data
            from messages m
            join topics t on t.id = m.topic_id
            {where}
            order by m.timestamp, m.id
        """
        yield from connection.execute(query, params)

    def get_message_count(self, topic: str) -> int:
        return self._topics.get(topic, TopicInfo(topic, "")).message_count

    def close(self) -> None:
        for connection in self._connections:
            connection.close()
        self._connections = []
        self._topic_maps = []


def open_bag_reader(path: str | Path, backend: str = "auto") -> BaseBagReader:
    path = Path(path)
    if backend not in {"auto", "rosbags", "sqlite"}:
        raise ValueError("backend must be one of: auto, rosbags, sqlite")
    errors: list[str] = []
    if backend in {"auto", "rosbags"}:
        reader = RosbagsReader()
        try:
            reader.open(path)
            return reader
        except Exception as exc:
            errors.append(f"rosbags backend unavailable: {exc}")
            if backend == "rosbags":
                raise
    if backend in {"auto", "sqlite"}:
        reader = SqliteRosbag2Reader()
        try:
            reader.open(path)
            reader.warnings[:0] = errors
            return reader
        except Exception as exc:
            errors.append(f"sqlite backend unavailable: {exc}")
            if backend == "sqlite":
                raise
    raise RuntimeError("; ".join(errors) or f"Could not open bag at {path}")


def _discover_sqlite_bags(path: Path) -> list[Path]:
    if path.is_file() and path.suffix.lower() in {".db3", ".sqlite", ".sqlite3"}:
        return [path]
    if path.is_dir():
        return sorted(path.glob("*.db3")) + sorted(path.glob("*.sqlite")) + sorted(
            path.glob("*.sqlite3")
        )
    return []


def _connection_serialization_format(connection: object) -> str | None:
    for attr in ("serialization_format", "serialization"):
        value = getattr(connection, attr, None)
        if value:
            return str(value)
    ext = getattr(connection, "ext", None)
    if ext is not None:
        value = getattr(ext, "serialization_format", None)
        if value:
            return str(value)
    return None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def time_bounds_from_topics(topics: list[TopicInfo]) -> tuple[int | None, int | None]:
    for topic in topics:
        if topic.message_count > 0 and (
            topic.first_timestamp_ns is None or topic.last_timestamp_ns is None
        ):
            return None, None
    starts = [
        topic.first_timestamp_ns
        for topic in topics
        if topic.first_timestamp_ns is not None
    ]
    ends = [
        topic.last_timestamp_ns
        for topic in topics
        if topic.last_timestamp_ns is not None
    ]
    if not starts or not ends:
        return None, None
    return min(starts), max(ends)


def _typestore_candidates() -> Sequence[tuple[str | None, object | None]]:
    candidates: list[tuple[str | None, object | None]] = [(None, None)]
    try:
        from rosbags.typesys import Stores, get_typestore
    except Exception:
        return candidates

    preferred_names = [
        "LATEST",
        "ROS2_JAZZY",
        "ROS2_HUMBLE",
        "ROS2_IRON",
        "ROS2_GALACTIC",
        "ROS2_FOXY",
        "ROS1_NOETIC",
    ]
    for name in preferred_names:
        store = getattr(Stores, name, None)
        if store is None:
            continue
        try:
            candidates.append((name, get_typestore(store)))
        except Exception:
            continue
    return candidates
