# Stage 3: v1.2.2

## Observed facts

- Commit `65491c9`, subject `Release v1.2.2`.
- Added `tests/test_bag_reader.py`.
- Changed backend validation, message flattening, point-cloud row handling, export suggestions, SQLite table/type behavior, and raw warning deduplication.

## Inferred purpose

- This appears to be a bugfix and robustness release after tabular exports landed.
- The focus was correctness around edge cases rather than feature expansion.

## Main components

- Core/domain logic: backend validation, flattening, point-cloud parsing.
- Export layer: SQLite and raw exporter robustness.
- Tests: 38 passing pytest tests.
- Docs: changelog clarified the historical 1.0.0 planned-export status.

## Build/test status

- Command attempted: `py -m pytest --tb=short`.
- Result: passed, 38 tests.

## Notes

- Tests captured several edge cases before they could regress.
- Session state preservation on failed open became explicit.
