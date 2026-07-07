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
poetry run python scripts/check_epic_size.py
```

Before committing feature work, run `check_epic_size.py` to ensure the diff against `main`
stays within the **600-line epic budget** (additions + modifications; `poetry.lock` excluded).

## Run

```powershell
poetry run unmouse
```

*(Application entry point wired in upcoming releases.)*
