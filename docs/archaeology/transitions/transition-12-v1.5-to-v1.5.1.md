# Transition: v1.5 to v1.5.1

## Summary

GUI appearance and dock behavior were polished.

## Observed file changes

- File count summary: 6 files changed, 519 insertions, 52 deletions.
- Files added: none observed.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: `ros2unbag/gui/timeline_viewer.py` and GUI tests.

## Feature-level interpretation

The GUI gained a theme switch, loading progress dialog, dock autosizing, and layout polish.

## Architecture impact

Most changes were concentrated in the GUI class, increasing the value of future GUI decomposition.

## Testing impact

Tests increased from 87 to 90 passing tests.

## Risk notes

UI layout and theme behavior are partly visual and may not be fully covered by headless tests.
