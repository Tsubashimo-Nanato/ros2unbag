# Stage 8: v1.4.0

## Observed facts

- Commit `d550b66`, subject `Release v1.4.0`.
- Changes touched CLI main, render, REPL, progress, models, and session.
- README/changelog describe `export-select`, `inspect --dur`, Ctrl+C handling, and ETA progress.

## Inferred purpose

- This stage improved interactive export workflows and shell usability.

## Main components

- CLI/shell layer: selected export queue and confirmation flow.
- Core/domain logic: export selection model and session support.
- Tests: 55 passing pytest tests.

## Build/test status

- Command attempted: `py -m pytest --tb=short`.
- Result: passed, 55 tests.

## Notes

- User workflow complexity increased, making CLI/REPL separation more important.
- Selection behavior has test coverage through REPL/session tests.
