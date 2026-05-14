from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prompt_toolkit.document import Document

from ros2unbag.cli.repl import (
    ExportSelectCompleter,
    Ros2UnbagCompleter,
    _selection_from_args,
    split_repl_line,
)
from ros2unbag.core.models import TopicInfo
from ros2unbag.core.session import Session


class ReplTests(unittest.TestCase):
    def test_split_repl_line_preserves_windows_paths(self) -> None:
        tokens = split_repl_line(r"open .\bag\demo --backend sqlite")
        self.assertEqual(tokens, ["open", r".\bag\demo", "--backend", "sqlite"])

    def test_completes_format_values(self) -> None:
        completer = Ros2UnbagCompleter(Session())
        completions = list(
            completer.get_completions(Document("export /topic --format "), object())
        )
        values = {item.text for item in completions}
        self.assertIn("csv", values)
        self.assertIn("raw", values)

    def test_format_completion_filters_media_for_non_image_topic(self) -> None:
        session = Session()
        session.topics = [
            TopicInfo(
                name="/points",
                msgtype="sensor_msgs/msg/PointCloud2",
                category="point_cloud",
            )
        ]
        completer = Ros2UnbagCompleter(session)

        completions = list(
            completer.get_completions(Document("export /points --format "), object())
        )
        values = {item.text for item in completions}

        self.assertIn("csv", values)
        self.assertIn("raw", values)
        self.assertNotIn("mp4", values)

    def test_completes_open_topics(self) -> None:
        session = Session()
        session.topics = [
            TopicInfo(name="/camera/image_raw", msgtype="sensor_msgs/msg/Image"),
            TopicInfo(name="/imu", msgtype="sensor_msgs/msg/Imu"),
        ]
        completer = Ros2UnbagCompleter(session)
        completions = list(completer.get_completions(Document("export /c"), object()))
        self.assertEqual([item.text for item in completions], ["/camera/image_raw"])

    def test_completes_topics_for_duration_command(self) -> None:
        session = Session()
        session.topics = [
            TopicInfo(name="/camera/image_raw", msgtype="sensor_msgs/msg/Image"),
            TopicInfo(name="/imu", msgtype="sensor_msgs/msg/Imu"),
        ]
        completer = Ros2UnbagCompleter(session)
        completions = list(completer.get_completions(Document("dur /i"), object()))
        self.assertEqual([item.text for item in completions], ["/imu"])

    def test_export_completion_advances_to_next_required_options(self) -> None:
        session = Session()
        session.topics = [
            TopicInfo(name="/camera/image_raw", msgtype="sensor_msgs/msg/Image"),
        ]
        completer = Ros2UnbagCompleter(session)

        after_topic = list(
            completer.get_completions(Document("export /camera/image_raw "), object())
        )
        after_format = list(
            completer.get_completions(
                Document("export /camera/image_raw --format png "),
                object(),
            )
        )

        self.assertEqual([item.text for item in after_topic], ["--format "])
        self.assertEqual([item.text for item in after_format], ["--out "])

    def test_export_topic_option_completes_topic_names(self) -> None:
        session = Session()
        session.topics = [
            TopicInfo(name="/camera/image_raw", msgtype="sensor_msgs/msg/Image"),
        ]
        completer = Ros2UnbagCompleter(session)

        completions = list(
            completer.get_completions(Document("export --topic /c"), object())
        )

        self.assertEqual([item.text for item in completions], ["/camera/image_raw"])

    def test_export_completion_offers_fps_after_mp4_output(self) -> None:
        completer = Ros2UnbagCompleter(Session())

        completions = list(
            completer.get_completions(
                Document("export /camera/image_raw --format mp4 --out .\\export "),
                object(),
            )
        )

        self.assertEqual([item.text for item in completions], ["--fps "])

    def test_command_completion_suggests_next_required_option(self) -> None:
        completer = Ros2UnbagCompleter(Session())

        export_all = list(completer.get_completions(Document("export-all "), object()))
        inspect = list(completer.get_completions(Document("inspect "), object()))

        self.assertEqual([item.text for item in export_all], ["--out "])
        self.assertIn("--time ", [item.text for item in inspect])
        self.assertIn("--dur ", [item.text for item in inspect])

    def test_topics_completion_prefers_view_short_option(self) -> None:
        completer = Ros2UnbagCompleter(Session())

        completions = list(completer.get_completions(Document("topics "), object()))

        self.assertEqual([item.text for item in completions], ["-v "])

    def test_inspect_duration_option_completes_topics(self) -> None:
        session = Session()
        session.topics = [TopicInfo(name="/imu", msgtype="sensor_msgs/msg/Imu")]
        completer = Ros2UnbagCompleter(session)

        completions = list(
            completer.get_completions(Document("inspect --dur /i"), object())
        )

        self.assertEqual([item.text for item in completions], ["/imu"])

    def test_export_select_completer_reuses_export_arguments(self) -> None:
        session = Session()
        session.topics = [TopicInfo(name="/imu", msgtype="sensor_msgs/msg/Imu")]
        completer = ExportSelectCompleter(session)

        topic_completions = list(completer.get_completions(Document("/i"), object()))
        option_completions = list(completer.get_completions(Document("/imu "), object()))

        self.assertEqual([item.text for item in topic_completions], ["/imu"])
        self.assertEqual([item.text for item in option_completions], ["--format "])

    def test_selection_parser_accepts_export_style_arguments(self) -> None:
        session = Session()
        session.reader = object()  # type: ignore[assignment]
        session.topics = [TopicInfo(name="/imu", msgtype="sensor_msgs/msg/Imu")]

        selection = _selection_from_args(
            session,
            ["/imu", "--format", "csv", "--out", ".\\export"],
        )

        self.assertEqual(selection.topic, "/imu")
        self.assertEqual(selection.format, "csv")

    def test_scan_path_completion_still_works_after_opening_bag(self) -> None:
        session = Session()
        session.reader = object()  # type: ignore[assignment]
        completer = Ros2UnbagCompleter(session)

        with tempfile.TemporaryDirectory() as temp_dir:
            bag_dir = Path(temp_dir) / "bagdata"
            bag_dir.mkdir()
            completions = list(
                completer.get_completions(
                    Document(f"scan {Path(temp_dir) / 'ba'}"),
                    object(),
                )
            )

        self.assertEqual(len(completions), 1)
        self.assertIn("bagdata", completions[0].text)


if __name__ == "__main__":
    unittest.main()
