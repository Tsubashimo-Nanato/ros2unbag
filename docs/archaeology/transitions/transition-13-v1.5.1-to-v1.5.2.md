# Transition: v1.5.1 to v1.5.2

## Summary

GUI stability and point-cloud performance were improved.

## Observed file changes

- File count summary: 11 files changed, 382 insertions, 83 deletions.
- Files added: none observed.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: GUI timeline viewer, point-cloud core/exporter, preview tests.

## Feature-level interpretation

The release hardened GUI startup/update behavior and reduced point-cloud preview/export overhead.

## Architecture impact

Background work moved away from the Qt UI thread, which improves GUI responsiveness.

## Testing impact

Tests increased from 90 to 96 passing tests.

## Risk notes

Threaded GUI work and point-cloud performance optimizations should remain regression-tested.
