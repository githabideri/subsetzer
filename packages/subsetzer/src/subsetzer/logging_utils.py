"""Logging helpers used by subsetzer CLI and GUI."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Optional

__all__ = ["Logger"]


class Logger:
    """Simple timestamped logger that mirrors output to stdout and a log file."""

    def __init__(self, *, file_path: Optional[Path], verbose: bool) -> None:
        self.file_path = file_path
        self.verbose = verbose
        self._handle = None
        if file_path is not None:
            try:
                self._handle = file_path.open("a", encoding="utf-8")
            except OSError:
                self._handle = None

    def log(self, message: str) -> None:
        timestamp = dt.datetime.now().isoformat(timespec="seconds")
        line = f"[{timestamp}] {message}"
        print(line)
        if self._handle is not None:
            try:
                self._handle.write(line + "\n")
                self._handle.flush()
            except OSError:
                self._handle = None

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            finally:
                self._handle = None

