from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from rosbagel.cli.main import app


class CliCommandTests(unittest.TestCase):
    def test_missing_bag_path_is_reported_without_traceback(self) -> None:
        missing_path = Path("missing-rosbag-for-cli-test")

        result = CliRunner().invoke(app, ["scan", str(missing_path)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(f"Bag path does not exist: {missing_path}", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_reader_failure_is_reported_without_traceback(self) -> None:
        bag_path = Path(__file__).resolve().parent
        with patch(
            "rosbagel.cli.main.Session.open_bag",
            side_effect=RuntimeError("broken bag index"),
        ):
            result = CliRunner().invoke(app, ["topics", str(bag_path)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Could not open bag", result.output)
        self.assertIn(str(bag_path), result.output)
        self.assertIn("broken", result.output)
        self.assertIn("bag index", result.output)
        self.assertNotIn("Traceback", result.output)


if __name__ == "__main__":
    unittest.main()
