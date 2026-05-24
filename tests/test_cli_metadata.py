from __future__ import annotations

from pathlib import Path
import unittest

from ros2unbag.cli.main import UNINSTALL_PACKAGES


class CliMetadataTests(unittest.TestCase):
    def test_uninstall_packages_include_current_previous_and_dependencies(self) -> None:
        packages = set(UNINSTALL_PACKAGES)

        self.assertIn("ros2unbag", packages)
        self.assertIn("rosbag-inspector", packages)
        self.assertIn("rosbags", packages)
        self.assertIn("prompt-toolkit", packages)
        self.assertIn("rich", packages)
        self.assertIn("typer", packages)
        self.assertIn("vispy", packages)
        self.assertIn("PyOpenGL", packages)

    def test_windows_batch_helpers_are_present(self) -> None:
        root = Path(__file__).resolve().parents[1]

        self.assertTrue((root / "install.bat").exists())
        self.assertTrue((root / "uninstall.bat").exists())
        self.assertTrue((root / "ros2unbag.bat").exists())


if __name__ == "__main__":
    unittest.main()
