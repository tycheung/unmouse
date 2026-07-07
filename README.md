# unmouse

OS-level eye tracking and hand-gesture control for Windows using a standard webcam.

## Requirements

- Python 3.10+
- [Poetry](https://python-poetry.org/)

## Setup

```powershell
poetry install
```

## Development

```powershell
poetry run pytest
poetry run ruff check src tests
poetry run mypy src
```

## Run

```powershell
poetry run unmouse
```

*(Application entry point wired in upcoming releases.)*
