# Transition: v1.4.2 to v1.4.3

## Summary

Upgrade commands and Windows progress fallback were added.

## Observed file changes

- File count summary: 11 files changed, 454 insertions, 12 deletions.
- Files added: `ros2unbag/cli/upgrade.py`, `tests/test_upgrade.py`.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: CLI main, CLI progress, REPL.

## Feature-level interpretation

The tool gained a local upgrade workflow from GitHub or PyPI with specific ref support.

## Architecture impact

Upgrade behavior was isolated in a CLI module, avoiding direct core bag-processing coupling.

## Testing impact

Tests increased from 59 to 68 passing tests.

## Risk notes

Live update behavior can affect installed environments; tests should avoid performing actual pip/network mutations.
