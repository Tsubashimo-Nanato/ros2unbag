# Transition: v1.2.2 to v1.3.0

## Summary

The import package was renamed from `ros2_unbag` to `ros2unbag`, and shared progress plumbing was introduced.

## Observed file changes

- File count summary: 45 files changed, 444 insertions, 128 deletions.
- Files added: `ros2unbag/cli/progress.py`, `ros2unbag/core/progress.py`.
- Files deleted: none observed as plain deletes.
- Files renamed: the package tree moved from `ros2_unbag/` to `ros2unbag/`.
- Heavily modified: `session.py`, CLI main, REPL, exporters, tests.

## Feature-level interpretation

The project aligned distribution, command, and import names while adding progress callbacks for long-running operations.

## Architecture impact

The package rename was structural. Progress abstractions created a cleaner boundary between core work and terminal rendering.

## Testing impact

Tests increased from 38 to 39 passing tests and all imports were updated to the new package name.

## Risk notes

Package renames can break downstream imports; preserving clear release notes was important.
