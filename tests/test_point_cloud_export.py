from __future__ import annotations

import csv
import dataclasses
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ros2unbag.core.models import MessageRecord
from ros2unbag.core.point_cloud import point_cloud_declared_point_count, point_cloud_rows
from ros2unbag.core.session import _coverage_warnings
from ros2unbag.exporters.csv_exporter import export_topic_csv
from ros2unbag.exporters.npz_exporter import export_topic_npz
from ros2unbag.exporters.point_cloud_exporter import export_topic_point_clouds


@dataclasses.dataclass
class FakePointField:
    name: str
    offset: int
    datatype: int
    count: int = 1


@dataclasses.dataclass
class FakePointCloud2:
    width: int
    height: int
    fields: list[FakePointField]
    is_bigendian: bool
    point_step: int
    row_step: int
    data: bytes
    is_dense: bool = True


class FakeReader:
    def __init__(self, records: list[MessageRecord]) -> None:
        self.records = records

    def iter_messages(self, topics: list[str] | None = None) -> object:
        topic_filter = set(topics or [])
        for record in self.records:
            if not topic_filter or record.topic in topic_filter:
                yield record


class PointCloudExportTests(unittest.TestCase):
    def test_point_cloud_rows_decode_standard_fields(self) -> None:
        cloud = _fake_cloud()
        rows = point_cloud_rows(cloud)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["x"], 1.0)
        self.assertEqual(rows[0]["y"], 2.0)
        self.assertEqual(rows[1]["z"], 6.0)

    def test_point_cloud_rows_respect_row_step_padding(self) -> None:
        fields = [FakePointField("x", 0, 7)]
        data = (
            struct.pack("<f", 1.0)
            + b"PAD!"
            + struct.pack("<f", 2.0)
            + b"PAD!"
        )
        cloud = FakePointCloud2(
            width=1,
            height=2,
            fields=fields,
            is_bigendian=False,
            point_step=4,
            row_step=8,
            data=data,
        )

        rows = point_cloud_rows(cloud)

        self.assertEqual([row["x"] for row in rows], [1.0, 2.0])
        self.assertEqual([row["cloud_row"] for row in rows], [0, 1])

    def test_declared_point_count_uses_valid_width_height_metadata(self) -> None:
        self.assertEqual(point_cloud_declared_point_count(_fake_cloud()), 2)

    def test_declared_point_count_rejects_truncated_payload(self) -> None:
        cloud = _fake_cloud()
        cloud.data = cloud.data[:12]

        self.assertIsNone(point_cloud_declared_point_count(cloud))

    def test_point_cloud_field_does_not_read_across_point_boundary(self) -> None:
        fields = [FakePointField("bad", 10, 7)]
        data = struct.pack("<ffffff", 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
        cloud = FakePointCloud2(
            width=2,
            height=1,
            fields=fields,
            is_bigendian=False,
            point_step=12,
            row_step=24,
            data=data,
        )

        rows = point_cloud_rows(cloud)

        self.assertNotIn("bad", rows[0])

    def test_csv_export_expands_pointcloud_messages_to_point_rows(self) -> None:
        topic = "/points"
        record = MessageRecord(
            topic=topic,
            timestamp_ns=100,
            msgtype="sensor_msgs/msg/PointCloud2",
            raw=b"raw",
            decoded=_fake_cloud(),
        )
        reader = FakeReader([record])
        with tempfile.TemporaryDirectory() as temp_dir:
            result = export_topic_csv(reader, topic, Path(temp_dir), bag_start_timestamp_ns=50)
            with Path(result.output_path).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(result.message_count, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["point_index"], "0")
        self.assertEqual(rows[1]["x"], "4.0")
        self.assertIn("PointCloud2 CSV expands 1 source messages into 2 point rows.", result.warnings)

    def test_pcd_export_writes_point_cloud_sequence(self) -> None:
        topic = "/points"
        record = MessageRecord(
            topic=topic,
            timestamp_ns=100,
            msgtype="sensor_msgs/msg/PointCloud2",
            raw=b"raw",
            decoded=_fake_cloud(),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = export_topic_point_clouds(FakeReader([record]), topic, Path(temp_dir), point_format="pcd")
            output_dir = Path(result.output_path)
            pcd_text = (output_dir / "000000.pcd").read_text(encoding="ascii")
            timestamps_exists = (output_dir / "timestamps.csv").exists()

        self.assertEqual(result.message_count, 1)
        self.assertIn("FIELDS x y z", pcd_text)
        self.assertIn("POINTS 2", pcd_text)
        self.assertTrue(timestamps_exists)

    def test_ply_export_writes_point_cloud_sequence(self) -> None:
        topic = "/points"
        record = MessageRecord(
            topic=topic,
            timestamp_ns=100,
            msgtype="sensor_msgs/msg/PointCloud2",
            raw=b"raw",
            decoded=_fake_cloud(),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = export_topic_point_clouds(FakeReader([record]), topic, Path(temp_dir), point_format="ply")
            ply_text = (Path(result.output_path) / "000000.ply").read_text(encoding="ascii")

        self.assertIn("element vertex 2", ply_text)
        self.assertIn("property float x", ply_text)

    def test_npz_export_writes_point_cloud_frame_arrays(self) -> None:
        topic = "/points"
        record = MessageRecord(
            topic=topic,
            timestamp_ns=100,
            msgtype="sensor_msgs/msg/PointCloud2",
            raw=b"raw",
            decoded=_fake_cloud(),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = export_topic_npz(FakeReader([record]), topic, Path(temp_dir), bag_start_timestamp_ns=50)
            npz_path = Path(result.output_path) / "000000.npz"
            with np.load(npz_path) as data:
                x_values = data["x"].tolist()
                timestamp_ns = data["timestamp_ns"].item()

        self.assertEqual(result.message_count, 1)
        self.assertEqual(x_values, [1.0, 4.0])
        self.assertEqual(timestamp_ns, 100)

    def test_coverage_warning_explains_topic_range_vs_bag_range(self) -> None:
        warnings = _coverage_warnings(
            result=type(
                "Result",
                (),
                {
                    "first_timestamp_ns": 110,
                    "last_timestamp_ns": 190,
                },
            )(),
            bag_start_ns=100,
            bag_end_ns=200,
        )

        self.assertEqual(len(warnings), 1)
        self.assertIn("Topic coverage differs from bag coverage", warnings[0])


def _fake_cloud() -> FakePointCloud2:
    fields = [
        FakePointField("x", 0, 7),
        FakePointField("y", 4, 7),
        FakePointField("z", 8, 7),
    ]
    data = struct.pack("<ffffff", 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    return FakePointCloud2(
        width=2,
        height=1,
        fields=fields,
        is_bigendian=False,
        point_step=12,
        row_step=24,
        data=data,
    )


if __name__ == "__main__":
    unittest.main()
