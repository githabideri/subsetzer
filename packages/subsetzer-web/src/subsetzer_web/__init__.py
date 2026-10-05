"""subsetzer-web: FastAPI web/API server for subsetzer."""
from __future__ import annotations

__all__ = ["create_app", "main", "__version__"]

__version__ = "0.2.0"


def __getattr__(name: str):
    # Lazy import: pulls in FastAPI only when the app is actually built.
    if name in ("create_app", "main"):
        from . import app

        return getattr(app, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
