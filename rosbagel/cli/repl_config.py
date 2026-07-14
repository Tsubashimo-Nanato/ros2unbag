from __future__ import annotations

from rosbagel.cli.upgrade import UPGRADE_SOURCES


COMMANDS = [
    "open",
    "close",
    "scan",
    "topics",
    "export",
    "export-select",
    "export-all",
    "inspect",
    "dur",
    "gui",
    "upgrade",
    "help",
    "clear",
    "exit",
    "quit",
]

OPTIONS_BY_COMMAND = {
    "open": ["--backend"],
    "scan": ["--all", "-all", "--out", "-o"],
    "topics": ["-all", "--all", "-s", "--select"],
    "export": ["--topic", "-t", "--format", "-f", "--out", "-o", "--fps"],
    "export-select": ["--topic", "-t", "--format", "-f", "--out", "-o", "--fps"],
    "export-all": ["--out", "-o"],
    "inspect": ["--time", "--dur", "--absolute-ns"],
    "dur": [],
    "gui": [],
    "upgrade": ["--source", "--ref", "--yes", "-y", "--print-only"],
}

VIEW_CHOICES = ["table", "tree", "nav"]
BACKEND_CHOICES = ["auto", "rosbags", "sqlite"]
SOURCE_CHOICES = list(UPGRADE_SOURCES)

VALUE_OPTIONS = {
    "--backend",
    "--format",
    "-f",
    "--fps",
    "--out",
    "-o",
    "--time",
    "--dur",
    "--topic",
    "-t",
    "--view",
    "-v",
    "--source",
    "--ref",
}

FLAG_OPTIONS = {"--absolute-ns"}
FLAG_OPTIONS.update({"--all", "-all", "--select", "-s", "--yes", "-y", "--print-only"})
