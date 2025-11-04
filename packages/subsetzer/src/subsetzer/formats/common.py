"""Shared helpers for subtitle formats."""
from __future__ import annotations

from typing import List, Tuple

from ..engine import TranscriptError

__all__ = ["clean_lines", "split_times"]


def clean_lines(text: str) -> List[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def split_times(time_line: str) -> Tuple[str, str]:
    parts = time_line.split("-->")
    if len(parts) < 2:
        raise TranscriptError(f"Unable to parse cue timing line: {time_line!r}")
    start = parts[0].strip()
    end_part = parts[1].strip().split()[0]
    return start, end_part

