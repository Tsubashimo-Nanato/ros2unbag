# Transition: v1.4.3 to v1.5

## Summary

The project expanded into GUI shell support and native point-cloud/NPZ exports.

## Observed file changes

- File count summary: 33 files changed, 3746 insertions, 60 deletions.
- Files added: `install.bat`, `uninstall.bat`, `ros2unbag.bat`, `jobs.py`, `preview.py`, `update_check.py`, `npz_exporter.py`, `point_cloud_exporter.py`, `gui/renderers.py`, and GUI/update/preview tests.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: GUI timeline viewer, session, type classifier, image/point-cloud exporters, README, changelog.

## Feature-level interpretation

The stage introduced a desktop inspection shell, GUI wiring, native point-cloud exports, NPZ exports, and Windows install helpers.

## Architecture impact

This was the largest interface expansion and increased GUI coupling risk.

## Testing impact

Tests increased from 68 to 87 passing tests.

## Risk notes

GUI behavior needs both automated tests and manual smoke testing. The tag/subject version mismatch should not be rewritten.
