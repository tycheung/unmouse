import sys

from unmouse.engine import run as run_engine
from unmouse.launcher.panel import run as run_launcher


def smoke_check() -> None:
    """Validate imports and version for CI / frozen exe smoke tests."""
    from unmouse import __version__
    from unmouse.launcher.panel import ui_index_path

    if not ui_index_path().is_file():
        msg = "control panel UI assets missing"
        raise SystemExit(msg)
    print(f"unmouse {__version__} smoke ok")


def main() -> None:
    if "--smoke" in sys.argv:
        smoke_check()
        return
    if "--engine" in sys.argv:
        run_engine()
    else:
        run_launcher()


if __name__ == "__main__":
    main()
