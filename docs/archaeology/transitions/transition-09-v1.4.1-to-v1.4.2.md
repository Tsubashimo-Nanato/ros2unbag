# Transition: v1.4.1 to v1.4.2

## Summary

Progress rendering and streaming inspect behavior were optimized.

## Observed file changes

- File count summary: 9 files changed, 306 insertions, 16 deletions.
- Files added: `tests/test_progress.py`.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: CLI progress, session, sync, performance tests.

## Feature-level interpretation

Large scans and exports gained less noisy and more efficient progress output.

## Architecture impact

Progress behavior remained separated into CLI/core progress helpers.

## Testing impact

Tests increased from 56 to 59 passing tests.

## Risk notes

Progress rendering is platform-sensitive, especially on Windows terminals.
