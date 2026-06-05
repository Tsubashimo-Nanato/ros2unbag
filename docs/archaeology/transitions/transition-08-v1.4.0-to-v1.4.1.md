# Transition: v1.4.0 to v1.4.1

## Summary

Shell topic display and command shape were simplified.

## Observed file changes

- File count summary: 8 files changed, 133 insertions, 60 deletions.
- Files added: none observed.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: CLI main, render, REPL, REPL tests.

## Feature-level interpretation

Topic browsing variants moved under `topics`, and scan behavior became simpler.

## Architecture impact

The change stayed in interface and rendering layers.

## Testing impact

Tests increased from 55 to 56 passing tests.

## Risk notes

Command aliases and shortcuts should remain documented because users may rely on them.
