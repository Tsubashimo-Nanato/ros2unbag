# Contributing

Thanks for considering a contribution. This project is an initial public release maintained by an amateur developer, so small, focused improvements are especially welcome.

## How to Contribute

1. Open an issue describing the bug, limitation, or feature idea.
2. Keep pull requests focused on one behavior or cleanup at a time.
3. Add or update tests when changing behavior.
4. Update `README.md` when commands, dependencies, installation steps, behavior, or limitations change.
5. Run the test suite before submitting:

```powershell
py -m unittest discover -s tests
```

## Development Setup

```powershell
py -m pip install -e .[dev]
```

For GUI experiments, install the optional GUI extra:

```powershell
py -m pip install -e .[gui]
```

Please do not commit local ROS bags, exported data, command history, or generated cache files.
