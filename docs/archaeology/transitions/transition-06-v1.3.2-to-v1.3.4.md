# Transition: v1.3.2 to v1.3.4

## Summary

Export compatibility checks were introduced.

## Observed file changes

- File count summary: 11 files changed, 191 insertions, 13 deletions.
- Files added: `tests/test_export_compatibility.py`.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: CLI main, REPL, session, type classifier.

## Feature-level interpretation

Incompatible media exports were rejected early while flexible data exports remained available.

## Architecture impact

Export compatibility policy was added but lived inside session/classifier code at this point.

## Testing impact

Tests increased from 45 to 50 passing tests.

## Risk notes

Compatibility rules are user-facing and should stay centralized as formats grow.
