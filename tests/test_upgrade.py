from __future__ import annotations

import sys
import unittest

from ros2unbag.cli.upgrade import (
    DEFAULT_GITHUB_REPOSITORY,
    build_upgrade_plan,
    format_command,
)


class UpgradeTests(unittest.TestCase):
    def test_github_upgrade_command_is_default(self) -> None:
        plan = build_upgrade_plan()

        self.assertEqual(plan.source, "github")
        self.assertEqual(plan.package_spec, f"git+{DEFAULT_GITHUB_REPOSITORY}")
        self.assertEqual(
            plan.command,
            (
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                f"git+{DEFAULT_GITHUB_REPOSITORY}",
            ),
        )

    def test_github_upgrade_ref_appends_revision(self) -> None:
        plan = build_upgrade_plan(ref="v1.4.3")

        self.assertEqual(plan.package_spec, f"git+{DEFAULT_GITHUB_REPOSITORY}@v1.4.3")

    def test_pypi_upgrade_ref_is_exact_version(self) -> None:
        plan = build_upgrade_plan(source="pypi", ref="1.4.3")

        self.assertEqual(plan.package_spec, "ros2unbag==1.4.3")

    def test_invalid_upgrade_source_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_upgrade_plan(source="local")

    def test_command_display_contains_package_spec(self) -> None:
        plan = build_upgrade_plan(ref="v1.4.3")

        self.assertIn("git+", format_command(plan.command))
        self.assertIn("@v1.4.3", plan.display_command)


if __name__ == "__main__":
    unittest.main()
