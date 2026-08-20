from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from prompt_toolkit.document import Document

from rosbagel.cli.parsing import parse_inspect_time
from rosbagel.cli.repl import (
    ExportSelectCompleter,
    BagelCompleter,
    _handle_manifest,
    _selection_from_args,
    dispatch_repl_line,
    split_repl_line,
)
from rosbagel.core.models import Manifest, TopicInfo
from rosbagel.core.session import Session


class ReplTests(unittest.TestCase):
    def test_split_repl_line_preserves_windows_paths(self) -> None:
        tokens = split_repl_line(r"open .\bag\demo --backend sqlite")
        self.assertEqual(tokens, ["open", r".\bag\demo", "--backend", "sqlite"])

    def test_absolute_inspect_time_preserves_nanosecond_integer(self) -> None:
        value = parse_inspect_time("1768890667673884124", absolute_ns=True)

        self.assertEqual(value, 1768890667673884124)
        self.assertIsInstance(value, int)

    def test_relative_inspect_time_remains_float_seconds(self) -> None:
        value = parse_inspect_time("1.25", absolute_ns=False)

        self.assertEqual(value, 1.25)
        self.assertIsInstance(value, float)

    def test_absolute_inspect_time_rejects_fractional_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "integer nanosecond timestamp"):
            parse_inspect_time("1.25", absolute_ns=True)

    def test_completes_format_values(self) -> None:
        completer = BagelCompleter(Session())
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
        completer = BagelCompleter(session)

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
        completer = BagelCompleter(session)
        completions = list(completer.get_completions(Document("export /c"), object()))
        self.assertEqual([item.text for item in completions], ["/camera/image_raw"])

    def test_completes_topics_for_duration_command(self) -> None:
        session = Session()
        session.topics = [
            TopicInfo(name="/camera/image_raw", msgtype="sensor_msgs/msg/Image"),
            TopicInfo(name="/imu", msgtype="sensor_msgs/msg/Imu"),
        ]
        completer = BagelCompleter(session)
        completions = list(completer.get_completions(Document("dur /i"), object()))
        self.assertEqual([item.text for item in completions], ["/imu"])

    def test_export_completion_advances_to_next_required_options(self) -> None:
        session = Session()
        session.topics = [
            TopicInfo(name="/camera/image_raw", msgtype="sensor_msgs/msg/Image"),
        ]
        completer = BagelCompleter(session)

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
        completer = BagelCompleter(session)

        completions = list(
            completer.get_completions(Document("export --topic /c"), object())
        )

        self.assertEqual([item.text for item in completions], ["/camera/image_raw"])

    def test_export_completion_offers_fps_after_mp4_output(self) -> None:
        completer = BagelCompleter(Session())

        completions = list(
            completer.get_completions(
                Document("export /camera/image_raw --format mp4 --out .\\export "),
                object(),
            )
        )

        self.assertEqual([item.text for item in completions], ["--fps "])

    def test_command_completion_suggests_next_required_option(self) -> None:
        completer = BagelCompleter(Session())

        export_all = list(completer.get_completions(Document("export-all "), object()))
        inspect = list(completer.get_completions(Document("inspect "), object()))

        self.assertEqual([item.text for item in export_all], ["--out "])
        self.assertIn("--time ", [item.text for item in inspect])
        self.assertIn("--dur ", [item.text for item in inspect])

    def test_topics_completion_prefers_all_and_selector_options(self) -> None:
        completer = BagelCompleter(Session())

        completions = list(completer.get_completions(Document("topics "), object()))

        self.assertEqual([item.text for item in completions], ["-all ", "-s "])

    def test_scan_completion_offers_all_and_out_when_bag_is_open(self) -> None:
        session = Session()
        session.reader = object()  # type: ignore[assignment]
        completer = BagelCompleter(session)

        completions = list(completer.get_completions(Document("scan "), object()))

        self.assertEqual([item.text for item in completions], ["--all ", "--out "])

    def test_scan_out_completes_output_paths(self) -> None:
        completer = BagelCompleter(Session())

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "scan_output"
            output_dir.mkdir()
            completions = list(
                completer.get_completions(
                    Document(f"scan --out {Path(temp_dir) / 'scan_'}"),
                    object(),
                )
            )

        self.assertEqual(len(completions), 1)
        self.assertIn("scan_output", completions[0].text)

    def test_manifest_completion_offers_command_out_and_paths(self) -> None:
        session = Session()
        session.reader = object()  # type: ignore[assignment]
        completer = BagelCompleter(session)

        command = list(completer.get_completions(Document("mani"), object()))
        out_option = list(completer.get_completions(Document("manifest "), object()))

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "manifests"
            output_dir.mkdir()
            paths = list(
                completer.get_completions(
                    Document(f"manifest --out {Path(temp_dir) / 'mani'}"),
                    object(),
                )
            )

        self.assertEqual([item.text for item in command], ["manifest"])
        self.assertEqual([item.text for item in out_option], ["--out "])
        self.assertEqual(len(paths), 1)
        self.assertIn("manifests", paths[0].text)

    def test_manifest_handler_writes_current_bag_manifest(self) -> None:
        session = Mock()
        session.scan.return_value = Manifest(source_bag_path="bag", created_at="now")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "reports" / "manifest.json"
            _handle_manifest(session, ["--out", str(output_path)])

            self.assertTrue(output_path.exists())

        session.scan.assert_called_once()

    def test_manifest_handler_requires_output_path(self) -> None:
        session = Mock()

        with self.assertRaisesRegex(ValueError, "Usage: manifest"):
            _handle_manifest(session, [])

    def test_malformed_command_reports_error_without_exiting_shell(self) -> None:
        with patch("rosbagel.cli.repl.console.print") as print_mock:
            should_exit = dispatch_repl_line(Session(), 'scan "')

        rendered = " ".join(str(call.args[0]) for call in print_mock.call_args_list)
        self.assertFalse(should_exit)
        self.assertIn("Could not parse input", rendered)

    def test_upgrade_completion_offers_source_values(self) -> None:
        completer = BagelCompleter(Session())

        option_completions = list(completer.get_completions(Document("upgrade "), object()))
        source_completions = list(
            completer.get_completions(Document("upgrade --source "), object())
        )

        self.assertIn("--source ", [item.text for item in option_completions])
        self.assertEqual([item.text for item in source_completions], ["github", "pypi"])

    def test_inspect_duration_option_completes_topics(self) -> None:
        session = Session()
        session.topics = [TopicInfo(name="/imu", msgtype="sensor_msgs/msg/Imu")]
        completer = BagelCompleter(session)

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
        completer = BagelCompleter(session)

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

    def test_gui_path_completion(self) -> None:
        completer = BagelCompleter(Session())

        with tempfile.TemporaryDirectory() as temp_dir:
            bag_dir = Path(temp_dir) / "bagdata"
            bag_dir.mkdir()
            completions = list(
                completer.get_completions(
                    Document(f"gui {Path(temp_dir) / 'ba'}"),
                    object(),
                )
            )

        self.assertEqual(len(completions), 1)
        self.assertIn("bagdata", completions[0].text)


if __name__ == "__main__":
    unittest.main()
