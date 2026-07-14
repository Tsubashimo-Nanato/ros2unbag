from __future__ import annotations

from io import StringIO
import unittest

from rich.console import Console

from rosbagel.cli.welcome import LOGO, show_welcome


class WelcomeTests(unittest.TestCase):
    def test_welcome_renders_logo_and_defaults_to_shell(self) -> None:
        output = StringIO()
        console = Console(file=output, force_terminal=False, color_system=None)
        captured: dict[str, object] = {}

        def confirm(prompt: str, **kwargs: object) -> bool:
            captured["prompt"] = prompt
            captured.update(kwargs)
            return False

        requested_gui = show_welcome(console, confirm=confirm, animated=False)

        rendered = output.getvalue()
        self.assertFalse(requested_gui)
        self.assertIn(LOGO[0], rendered)
        self.assertIn("Keep the source untouched", rendered)
        self.assertIn("GUI", str(captured["prompt"]))
        self.assertFalse(captured["default"])

    def test_welcome_returns_gui_selection(self) -> None:
        console = Console(file=StringIO(), force_terminal=False, color_system=None)

        requested_gui = show_welcome(
            console,
            confirm=lambda *_args, **_kwargs: True,
            animated=False,
        )

        self.assertTrue(requested_gui)


if __name__ == "__main__":
    unittest.main()
