from __future__ import annotations

import csv
import dataclasses
import tempfile
import unittest
from pathlib import Path

from ros2_unbag.core.models import MessageRecord
from ros2_unbag.exporters.image_exporter import export_topic_images
from ros2_unbag.exporters.video_exporter import export_topic_video


@dataclasses.dataclass
class FakeImage:
    height: int
    width: int
    encoding: str
    step: int
    data: bytes


class FakeReader:
    def __init__(self, records: list[MessageRecord]) -> None:
        self.records = records

    def iter_messages(self, topics: list[str] | None = None) -> object:
        topic_filter = set(topics or [])
        for record in self.records:
            if not topic_filter or record.topic in topic_filter:
                yield record


class ImageExportTests(unittest.TestCase):
    def test_png_export_writes_frames_and_timestamp_csv(self) -> None:
        topic = "/camera/mask"
        records = [
            _record(topic, 100, width=2, height=2),
            _record(topic, 200, width=2, height=2),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            result = export_topic_images(
                FakeReader(records),
                topic,
                Path(temp_dir),
                image_format="png",
                bag_start_timestamp_ns=50,
            )
            output_dir = Path(result.output_path)
            with (output_dir / "timestamps.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(result.message_count, 2)
            self.assertTrue((output_dir / "000000.png").exists())
            self.assertEqual(rows[0]["timestamp_ns"], "100")
            self.assertEqual(rows[0]["timestamp_sec_from_start"], "5e-08")
            self.assertEqual(rows[1]["filename"], "000001.png")

    def test_mp4_export_writes_video_and_timestamp_csv(self) -> None:
        topic = "/camera/image_raw"
        records = [
            _record(topic, 100, width=16, height=16),
            _record(topic, 200, width=16, height=16),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                result = export_topic_video(
                    FakeReader(records),
                    topic,
                    Path(temp_dir),
                    fps=10.0,
                    bag_start_timestamp_ns=0,
                )
            except ValueError as exc:
                if "Could not open VideoWriter" in str(exc):
                    self.skipTest(str(exc))
                raise

            video_path = Path(result.output_path)
            timestamps_path = video_path.with_name(f"{video_path.stem}_timestamps.csv")
            with timestamps_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(result.message_count, 2)
            self.assertTrue(video_path.exists())
            self.assertEqual(rows[1]["video_time_sec"], "0.1")
            self.assertIn("constant FPS", " ".join(result.warnings))


def _record(topic: str, timestamp_ns: int, *, width: int, height: int) -> MessageRecord:
    row = bytes([0, 255] * (width // 2))
    data = row * height
    image = FakeImage(height=height, width=width, encoding="mono8", step=width, data=data)
    return MessageRecord(
        topic=topic,
        timestamp_ns=timestamp_ns,
        msgtype="sensor_msgs/msg/Image",
        raw=b"raw",
        decoded=image,
    )


if __name__ == "__main__":
    unittest.main()
