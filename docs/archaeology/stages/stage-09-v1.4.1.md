# Stage 9: v1.4.1

## Observed facts

- Commit `594f12f`, subject `Release v1.4.1`.
- Changes focused on CLI main, render, REPL, README, and tests.
- README/changelog describe topic display cleanup and simplified scan/topics workflows.

## Inferred purpose

- This appears to be a shell UX cleanup release that reduced command/display confusion.

## Main components

- CLI/shell layer: topic tree rendering, scan/topics command shape, completions.
- Tests: 56 passing pytest tests.
- Docs: interactive usage updated.

## Build/test status

- Command attempted: `py -m pytest --tb=short`.
- Result: passed, 56 tests.

## Notes

- Mostly interface-layer change.
- The lower-level export and reader architecture stayed stable.
