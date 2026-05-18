from __future__ import annotations

from dataclasses import dataclass
import os
import shlex
import subprocess
import sys
from typing import Sequence


DEFAULT_GITHUB_REPOSITORY = "https://github.com/Tsubashimo-Nanato/ros2unbag.git"
UPGRADE_SOURCES = ("github", "pypi")


@dataclass(frozen=True)
class UpgradePlan:
    source: str
    ref: str | None
    package_spec: str
    command: tuple[str, ...]

    @property
    def display_command(self) -> str:
        display_executable = "py" if os.name == "nt" else self.command[0]
        return format_command((display_executable, *self.command[1:]))


def build_upgrade_plan(
    *,
    source: str = "github",
    ref: str | None = None,
) -> UpgradePlan:
    """Build the pip command used for self-upgrade without executing it."""
    normalized_source = source.lower()
    if normalized_source not in UPGRADE_SOURCES:
        choices = ", ".join(UPGRADE_SOURCES)
        raise ValueError(f"Unknown upgrade source '{source}'. Expected one of: {choices}.")

    if normalized_source == "github":
        repository = DEFAULT_GITHUB_REPOSITORY
        if ref:
            repository = f"{repository}@{ref}"
        package_spec = f"git+{repository}"
    elif ref:
        package_spec = f"ros2unbag=={ref}"
    else:
        package_spec = "ros2unbag"

    command = (sys.executable, "-m", "pip", "install", "--upgrade", package_spec)
    return UpgradePlan(
        source=normalized_source,
        ref=ref,
        package_spec=package_spec,
        command=command,
    )


def run_upgrade(plan: UpgradePlan) -> None:
    """Run the prepared upgrade command and raise when pip fails."""
    completed = subprocess.run(plan.command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Upgrade failed with exit code {completed.returncode}.")


def format_command(command: Sequence[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    return shlex.join(command)
