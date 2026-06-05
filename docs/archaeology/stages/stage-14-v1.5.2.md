# Stage 14: v1.5.2

## Observed facts

- Commit `9e14b2e`, subject `Release v1.5.2`.
- Current `main` and `origin/main` pointed here during inventory.
- Changes focused on GUI startup stability, GUI background update/upgrade work, bounded image playback rendering, and point-cloud performance.

## Inferred purpose

- This is the current stable release snapshot before the local archaeology/refactor branch.
- The release mainly hardens GUI behavior and large point-cloud workflows.

## Main components

- Core/domain logic: point-cloud count/performance improvements and preview behavior.
- Export layer: point-cloud exporter performance.
- GUI layer: startup, background update checks, playback memory behavior.
- Tests: 96 passing pytest tests.

## Build/test status

- Command attempted: `py -m pytest --tb=short`.
- Result: passed, 96 tests.

## Notes

- The project has a meaningful test suite and clear package structure.
- Main remaining architecture risk is the size and responsibility density of the GUI shell.
