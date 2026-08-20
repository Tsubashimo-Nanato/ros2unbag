from __future__ import annotations

from collections.abc import Callable
import time

from rich.console import Console
from rich.prompt import Confirm

from rosbagel import __version__


LOGO = (
    " ____   ___  ____  ____                  _",
    "|  _ \\ / _ \\/ ___|| __ )  __ _  __ _  ___| |",
    "| |_) | | | \\___ \\|  _ \\ / _` |/ _` |/ _ \\ |",
    "|  _ <| |_| |___) | |_) | (_| | (_| |  __/ |",
    "|_| \\_\\___/|____/|____/ \\__,_|\\__, |\\___|_|",
    "                                  |___/",
)
DESCRIPTION = "Offline ROS 1/2 bag inspection, export, and visualization on Windows."
AUTHOR = "Owen ZI-WEN ZHOU, also known online as Nanato."
LICENSE = "AGPL-3.0-or-later"
REPOSITORY = "github.com/Tsubashimo-Nanato/ROSBagel"


def show_welcome(
    console: Console,
    *,
    confirm: Callable[..., bool] = Confirm.ask,
    sleep: Callable[[float], None] = time.sleep,
    animated: bool = True,
) -> bool:
    """Render the shell greeting and return whether the GUI was requested."""
    delay = 0.035 if animated else 0.0
    for index, line in enumerate(LOGO):
        style = "bold #f59e0b" if index in {0, len(LOGO) - 1} else "bold #d4d4d4"
        console.print(line, style=style, soft_wrap=False)
        if delay:
            sleep(delay)

    console.print(f"ROSBagel v{__version__}", style="bold #f59e0b")
    console.print()
    console.print(DESCRIPTION, style="#d4d4d4")
    console.print(f"Author: {AUTHOR}", style="dim")
    console.print(f"License: {LICENSE}", style="dim")
    console.print(f"Repository: {REPOSITORY}", style="dim")
    console.print()
    return confirm(
        "Open the GUI [dim](in development)[/dim]?",
        default=False,
        console=console,
    )
