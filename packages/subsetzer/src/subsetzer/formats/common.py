"""Shared helpers for subtitle formats."""
from __future__ import annotations

from typing import List, Tuple

from ..engine import TranscriptError

__all__ = ["clean_lines", "split_times", "split_times_with_settings"]


def clean_lines(text: str) -> List[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def split_times(time_line: str) -> Tuple[str, str]:
    parts = time_line.split("-->")
    if len(parts) < 2:
        raise TranscriptError(f"Unable to parse cue timing line: {time_line!r}")
    start = parts[0].strip()
    end_part = parts[1].strip().split()[0]
    return start, end_part


def split_times_with_settings(time_line: str) -> Tuple[str, str, str]:
    parts = time_line.split("-->")
    if len(parts) < 2:
        raise TranscriptError(f"Unable to parse cue timing line: {time_line!r}")
    start = parts[0].strip()
    remainder = parts[1].strip()
    tokens = remainder.split(maxsplit=1)
    end = tokens[0]
    settings = tokens[1] if len(tokens) > 1 else ""
    return start, end, settings
