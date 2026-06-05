# Transition: v1.0.0 to v1.2.0

## Summary

Phase 4 tabular exports were implemented.

## Observed file changes

- File count summary: 13 files changed, 617 insertions, 101 deletions.
- Files added: `ros2_unbag/exporters/tabular.py`, `tests/test_phase4_exports.py`.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: CSV, Parquet, SQLite exporters, session export dispatch, README, changelog.

## Feature-level interpretation

Parquet and SQLite moved from planned formats to working flattened export paths.

## Architecture impact

CSV, Parquet, and SQLite began sharing tabular collection logic, reducing exporter duplication.

## Testing impact

Phase 4 export tests were added. Tagged test result increased from 29 to 32 passing tests.

## Risk notes

PointCloud2 row expansion and SQLite table shape became important compatibility surfaces.
