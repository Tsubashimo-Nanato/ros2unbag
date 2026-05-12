from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
