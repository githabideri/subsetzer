"""File I/O helpers for subsetzer."""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Dict, Optional, Union

from .engine import Transcript, TranscriptError
from .formats import parse_srt, parse_tsv, parse_vtt, write_srt, write_tsv, write_vtt

__all__ = [
    "detect_format",
    "read_transcript",
    "build_output",
    "build_output_as",
    "resolve_outfile",
]

_FORMAT_GUESS_RE: Dict[str, re.Pattern[str]] = {
    "srt": re.compile(r"^\s*\d+\s*\n\s*\d\d:\d\d:\d\d[,\.]\d\d\d\s*-->", re.MULTILINE),
    "vtt": re.compile(r"^\s*WEBVTT", re.IGNORECASE),
    "tsv": re.compile(r"\t"),
}


def detect_format(text: str, filename: str = "") -> str:
    """Heuristic format detection based on extension and content."""
    ext = os.path.splitext(filename.lower())[1]
    if ext in {".srt"}:
        return "srt"
    if ext in {".vtt"}:
        return "vtt"
    if ext in {".tsv", ".csv"}:
        return "tsv"

    stripped = text.lstrip()
    if _FORMAT_GUESS_RE["vtt"].search(stripped):
        return "vtt"
    if _FORMAT_GUESS_RE["srt"].search(stripped):
        return "srt"
    if _FORMAT_GUESS_RE["tsv"].search(stripped):
        return "tsv"
    raise TranscriptError("Unable to detect subtitle format from input content.")


def read_transcript(path: str) -> Transcript:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = handle.read()
    except OSError as exc:
        raise TranscriptError(f"Unable to read input file: {exc}") from exc

    if not data.strip():
        raise TranscriptError("Input file is empty.")

    fmt = detect_format(data, filename=path)
    if fmt == "srt":
        return parse_srt(data)
    if fmt == "vtt":
        return parse_vtt(data)
    if fmt == "tsv":
        return parse_tsv(data)
    raise TranscriptError(f"Unsupported subtitle format: {fmt}")


def build_output_as(transcript: Transcript, fmt: str, vtt_note: Optional[str] = None) -> str:
    fmt = fmt.lower()
    if fmt == "srt":
        return write_srt(transcript)
    if fmt == "vtt":
        return write_vtt(transcript, note=vtt_note)
    if fmt == "tsv":
        return write_tsv(transcript)
    raise TranscriptError(f"Cannot build output for unknown format: {fmt}")


def build_output(transcript: Transcript, vtt_note: Optional[str] = None) -> str:
    note = vtt_note if transcript.fmt == "vtt" else None
    return build_output_as(transcript, transcript.fmt, vtt_note=note)


def resolve_outfile(
    template: Union[str, Path],
    input_path: Optional[Union[str, Path]],
    src: str,
    dst: str,
    fmt: str,
    model: Optional[str] = None,
) -> Path:
    path_template = Path(template) if isinstance(template, Path) else Path(str(template))

    input_base: Optional[Path] = None
    if input_path is not None and str(input_path):
        input_base = Path(str(input_path))

    basename = input_base.stem if input_base is not None else "output"
    tokens = {
        "basename": basename,
        "src": _slugify_token(src) or "src",
        "dst": _slugify_token(dst) or "dst",
        "fmt": fmt.lower(),
        "ts": dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
        "model": _slugify_token(model or "") or "model",
    }

    try:
        formatted = str(path_template).format(**tokens)
    except KeyError as exc:
        raise TranscriptError(f"Unknown placeholder in output template: {exc}") from exc

    candidate = Path(formatted).expanduser()
    candidate.parent.mkdir(parents=True, exist_ok=True)

    if not candidate.exists():
        return candidate

    suffix = "".join(candidate.suffixes)
    base_name = candidate.name
    if suffix:
        base_name = base_name[: -len(suffix)]
    counter = 1
    while True:
        new_name = f"{base_name}-{counter}{suffix}"
        new_path = candidate.with_name(new_name)
        if not new_path.exists():
            return new_path
        counter += 1


def _slugify_token(text: str) -> str:
    cleaned = re.sub(r"[\s]+", "_", str(text).strip())
    cleaned = re.sub(r"[^0-9A-Za-z._-]", "-", cleaned)
    cleaned = re.sub(r"[-_]{2,}", "_", cleaned)
    return cleaned.strip("_-.")
