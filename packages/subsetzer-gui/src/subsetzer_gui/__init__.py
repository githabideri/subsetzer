"""Subsetzer GUI package."""
from __future__ import annotations

__all__ = ["main"]


def main(*args, **kwargs):
    """Entry point proxy to avoid importing Tk code at module import time."""
    from .app import main as _main

    return _main(*args, **kwargs)
