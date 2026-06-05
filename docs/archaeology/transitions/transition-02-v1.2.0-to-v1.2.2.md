# Transition: v1.2.0 to v1.2.2

## Summary

Bugfix release for backend validation, flattening, point-cloud row parsing, and SQLite export robustness.

## Observed file changes

- File count summary: 16 files changed, 172 insertions, 30 deletions.
- Files added: `tests/test_bag_reader.py`.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: `point_cloud.py`, `sqlite_exporter.py`, phase 4 tests, point-cloud tests.

## Feature-level interpretation

The release fixed edge cases introduced or exposed by richer tabular exports.

## Architecture impact

The structure stayed stable; changes were focused correctness fixes.

## Testing impact

Tests increased from 32 to 38 passing tests and added coverage for session state preservation and point-cloud boundaries.

## Risk notes

The point-cloud and SQLite fixes affect exported data shape and are high-value regression targets.
