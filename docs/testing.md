# Testing

## Local Command

Run the full test suite with:

```powershell
py -m pytest
```

Current verification on `refactor/repository-organization`:

```text
100 passed
```

## Tagged Stage Results

Each tag was checked with:

```powershell
py -m pytest --tb=short
```

Results:

- `v1.0.0`: 29 passed
- `v1.2.0`: 32 passed
- `v1.2.2`: 38 passed
- `v1.3.0`: 39 passed
- `v1.3.1`: 40 passed
- `v1.3.2`: 45 passed
- `v1.3.4`: 50 passed
- `v1.4.0`: 55 passed
- `v1.4.1`: 56 passed
- `v1.4.2`: 59 passed
- `v1.4.3`: 68 passed
- `v1.5`: 87 passed
- `v1.5.1`: 90 passed
- `v1.5.2`: 96 passed

## Coverage Shape

- Core classification, decoding, topic tree, sync, progress, preview, update check, and bag-reader behavior have focused tests.
- Exporters have file-output tests for tabular, image/video, point-cloud, NPZ, and compatibility behavior.
- CLI/REPL behavior has parser, completion, and command-shape tests.
- GUI tests cover selected behavior without requiring real ROS bag playback.

## Follow-Up

- Add CI to run `py -m pytest` on supported Python versions.
- Add small fixture bags only if they are curated and kept out of large local `Bags/` data.
- Add smoke tests for installed command entry points after packaging changes.
