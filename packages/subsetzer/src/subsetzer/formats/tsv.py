"""TSV subtitle parsing and serialisation."""
from __future__ import annotations

import csv
from typing import Iterable, List, Optional, Tuple

from ..engine import Cue, Transcript, TranscriptError
from .common import clean_lines

__all__ = ["parse_tsv", "write_tsv"]


def parse_tsv(text: str) -> Transcript:
    reader = csv.reader(clean_lines(text), delimiter="\t")
    try:
        header = next(reader)
    except StopIteration as exc:  # pragma: no cover - defensive
        raise TranscriptError("TSV appears empty.") from exc

    header_lower = [h.lower() for h in header]
    start_idx, end_idx, text_idx = _infer_tsv_columns(header_lower)

    cues: List[Cue] = []
    for idx, row in enumerate(reader, start=1):
        if not row:
            continue
        try:
            start = row[start_idx]
            end = row[end_idx]
            text_val = row[text_idx]
        except IndexError as exc:
            raise TranscriptError(
                f"Row {idx} does not contain required columns (expected at least {text_idx + 1} columns)."
            ) from exc
        cues.append(Cue(index=idx, start=start, end=end, text=text_val))

    if not cues:
        raise TranscriptError("No cues parsed from TSV file.")

    return Transcript(fmt="tsv", cues=cues, tsv_header=header, tsv_cols=(start_idx, end_idx, text_idx))


def write_tsv(transcript: Transcript) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    header = transcript.tsv_header or ["start", "end", "text"]
    writer.writerow(header)
    start_idx, end_idx, text_idx = transcript.tsv_cols or (0, 1, 2)
    for cue in transcript.cues:
        row = [""] * max(len(header), text_idx + 1)
        row[start_idx] = cue.start
        row[end_idx] = cue.end
        row[text_idx] = cue.translated if cue.translated is not None else cue.text
        writer.writerow(row)
    return buffer.getvalue()


def _infer_tsv_columns(header_lower: List[str]) -> Tuple[int, int, int]:
    start_idx = _first_with_keywords(header_lower, ["start", "begin"])
    end_idx = _first_with_keywords(header_lower, ["end", "finish"])
    text_idx = _first_with_keywords(header_lower, ["text", "subtitle", "caption", "transcript"])

    if start_idx is None or end_idx is None or text_idx is None:
        if len(header_lower) < 3:
            raise TranscriptError("TSV header must contain at least three columns.")
        return 0, 1, 2
    return start_idx, end_idx, text_idx


def _first_with_keywords(header: List[str], keywords: Iterable[str]) -> Optional[int]:
    for idx, value in enumerate(header):
        for key in keywords:
            if key in value:
                return idx
    return None
