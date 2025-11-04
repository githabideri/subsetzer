"""Enable `python -m subsetzer`."""
from __future__ import annotations

from .cli import main


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    run()

