import sys

from unmouse.engine import run as run_engine
from unmouse.main import run as run_launcher


def main() -> None:
    if "--engine" in sys.argv:
        run_engine()
    else:
        run_launcher()


if __name__ == "__main__":
    main()
