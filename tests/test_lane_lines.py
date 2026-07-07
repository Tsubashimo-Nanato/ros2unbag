from __future__ import annotations

import dataclasses
import math
import struct
import unittest

from ros2unbag.core.lane_lines import (
    LANE_ROLES,
    LaneFrame,
    LanePoint,
    LaneSeries,
    build_lane_overlay_data,
    extract_lane_points,
    lane_bounds,
    lane_role_for_topic,
    lane_topics,
)
from ros2unbag.core.models import MessageRecord, TopicInfo


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


class FakeReader:
    def __init__(self, records: list[MessageRecord]) -> None:
        self.records = records
        self.iter_starts = 0
        self.last_topics: list[str] | None = None

    def iter_messages(self, topics: list[str] | None = None) -> object:
        self.iter_starts += 1
        self.last_topics = topics
        topic_filter = set(topics or [])
        for record in self.records:
            if not topic_filter or record.topic in topic_filter:
                yield record


class LaneLineTests(unittest.TestCase):
    def test_lane_topic_detector_accepts_lane_point_cloud_topics(self) -> None:
        topics = [
            _lane_topic("center"),
            _lane_topic("left"),
            _lane_topic("right"),
        ]

        self.assertEqual(lane_role_for_topic(topics[0]), "center")
        self.assertEqual(list(lane_topics(topics)), list(LANE_ROLES))

    def test_lane_topic_detector_rejects_other_point_clouds(self) -> None:
        wrong_type = TopicInfo(
            name="/aiformula_perception/lane_line_publisher/lane_lines/center",
            msgtype="std_msgs/msg/String",
        )
        wrong_path = TopicInfo(
            name="/aiformula_perception/lane_line_publisher/lane_lines/centerline",
            msgtype="sensor_msgs/msg/PointCloud2",
        )

        self.assertIsNone(lane_role_for_topic(wrong_type))
        self.assertIsNone(lane_role_for_topic(wrong_path))

    def test_extract_lane_points_reads_xy_and_filters_non_finite_values(self) -> None:
        cloud = _cloud([
            (1.0, 2.0, 0.0),
            (math.nan, 3.0, 0.0),
            (4.0, math.inf, 0.0),
            (5.0, 6.0, 7.0),
        ])

        points = extract_lane_points(cloud)

        self.assertEqual(points, (LanePoint(1.0, 2.0), LanePoint(5.0, 6.0)))

    def test_extract_lane_points_ignores_points_without_xy_fields(self) -> None:
        cloud = FakePointCloud2(
            width=1,
            height=1,
            fields=[FakePointField("x", 0, 7)],
            is_bigendian=False,
            point_step=4,
            row_step=4,
            data=struct.pack("<f", 1.0),
        )

        self.assertEqual(extract_lane_points(cloud), ())

    def test_nearest_frame_uses_closest_timestamp(self) -> None:
        series = LaneSeries(
            role="center",
            topic="/center",
            frames=[
                LaneFrame(timestamp_ns=100, points=()),
                LaneFrame(timestamp_ns=200, points=()),
                LaneFrame(timestamp_ns=350, points=()),
            ],
        )

        self.assertEqual(series.nearest_frame(80).timestamp_ns, 100)
        self.assertEqual(series.nearest_frame(275).timestamp_ns, 200)
        self.assertEqual(series.nearest_frame(310).timestamp_ns, 350)

    def test_lane_bounds_adds_margin_and_handles_zero_span(self) -> None:
        bounds = lane_bounds([LanePoint(2.0, 4.0), LanePoint(12.0, 8.0)])

        self.assertIsNotNone(bounds)
        self.assertAlmostEqual(bounds.min_x, 1.5)
        self.assertAlmostEqual(bounds.max_x, 12.5)
        self.assertAlmostEqual(bounds.min_y, 3.8)
        self.assertAlmostEqual(bounds.max_y, 8.2)

        flat = lane_bounds([LanePoint(2.0, 4.0)])
        self.assertEqual(flat.min_x, 1.0)
        self.assertEqual(flat.max_x, 3.0)
        self.assertEqual(flat.min_y, 3.0)
        self.assertEqual(flat.max_y, 5.0)

    def test_build_lane_overlay_data_reads_lane_topics_in_one_pass(self) -> None:
        center_topic = _lane_topic("center")
        left_topic = _lane_topic("left")
        right_topic = _lane_topic("right")
        reader = FakeReader([
            MessageRecord(center_topic.name, 100, center_topic.msgtype, decoded=_cloud([(1.0, 2.0, 0.0)])),
            MessageRecord(left_topic.name, 120, left_topic.msgtype, decoded=_cloud([(3.0, 4.0, 0.0)])),
            MessageRecord("/not_lane", 130, "sensor_msgs/msg/PointCloud2", decoded=_cloud([(5.0, 6.0, 0.0)])),
            MessageRecord(right_topic.name, 140, right_topic.msgtype, decoded=_cloud([(7.0, 8.0, 0.0)])),
        ])

        data = build_lane_overlay_data(reader, [center_topic, left_topic, right_topic])

        self.assertEqual(reader.iter_starts, 1)
        self.assertEqual(set(reader.last_topics or []), {center_topic.name, left_topic.name, right_topic.name})
        self.assertEqual([series.role for series in data.ordered_series()], list(LANE_ROLES))
        self.assertEqual(data.series_by_role["center"].frames[0].points, (LanePoint(1.0, 2.0),))
        self.assertEqual(data.series_by_role["left"].frames[0].timestamp_ns, 120)
        self.assertEqual(data.series_by_role["right"].frames[0].points, (LanePoint(7.0, 8.0),))


def _lane_topic(role: str) -> TopicInfo:
    return TopicInfo(
        name=f"/aiformula_perception/lane_line_publisher/lane_lines/{role}",
        msgtype="sensor_msgs/msg/PointCloud2",
        category="point_cloud",
    )


def _cloud(points: list[tuple[float, float, float]]) -> FakePointCloud2:
    return FakePointCloud2(
        width=len(points),
        height=1,
        fields=[
            FakePointField("x", 0, 7),
            FakePointField("y", 4, 7),
            FakePointField("z", 8, 7),
        ],
        is_bigendian=False,
        point_step=12,
        row_step=12 * len(points),
        data=struct.pack("<" + ("fff" * len(points)), *(value for point in points for value in point)),
    )


if __name__ == "__main__":
    unittest.main()
