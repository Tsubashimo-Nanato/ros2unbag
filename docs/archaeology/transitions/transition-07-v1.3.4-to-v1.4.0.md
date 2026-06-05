# Transition: v1.3.4 to v1.4.0

## Summary

Selected export workflow and shell UX improvements were added.

## Observed file changes

- File count summary: 12 files changed, 512 insertions, 79 deletions.
- Files added: none observed.
- Files deleted: none observed.
- Files renamed: none observed.
- Heavily modified: CLI main, REPL, render, session, models.

## Feature-level interpretation

Users could queue export selections, review them, and export selected topics in one workflow.

## Architecture impact

Session gained more orchestration responsibility for selected exports.

## Testing impact

Tests increased from 50 to 55 passing tests.

## Risk notes

Interactive queue behavior can couple terminal UI and session logic if not kept explicit.
