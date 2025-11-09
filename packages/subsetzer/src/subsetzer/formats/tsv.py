"""TSV subtitle parsing and serialisation."""
from __future__ import annotations

import csv
from typing import Iterable, List, Optional, Tuple

from ..engine import Cue, Transcript, TranscriptError
from .common import clean_lines

__all__ = ["parse_tsv", "write_tsv"]


def parse_tsv(text: str) -> Transcript:
    lines = clean_lines(text)
    sample = "\n".join(lines[:5])
    delimiter = "\t"
    if "\t" not in sample and sample.count(",") >= sample.count("\t"):
        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
            delimiter = dialect.delimiter
        except csv.Error:
            pass
    reader = csv.reader(lines, delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration as exc:  # pragma: no cover - defensive
        raise TranscriptError("TSV appears empty.") from exc

    header_lower = [h.lower() for h in header]
    start_idx, end_idx, text_idx = _infer_tsv_columns(header_lower)

    cues: List[Cue] = []
    stored_rows: List[List[str]] = []
    for idx, row in enumerate(reader, start=1):
        if not row:
            continue
        stored_rows.append(list(row))
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

    return Transcript(
        fmt="tsv",
        cues=cues,
        tsv_header=header,
        tsv_cols=(start_idx, end_idx, text_idx),
        tsv_rows=stored_rows,
        tsv_delimiter=delimiter,
    )


def write_tsv(transcript: Transcript) -> str:
    from io import StringIO

    buffer = StringIO()
    delimiter = transcript.tsv_delimiter if transcript.tsv_header else "\t"
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    header = transcript.tsv_header or ["start", "end", "text"]
    writer.writerow(header)
    start_idx, end_idx, text_idx = transcript.tsv_cols or (0, 1, 2)
    rows = transcript.tsv_rows if transcript.tsv_rows and len(transcript.tsv_rows) == len(transcript.cues) else None
    for idx, cue in enumerate(transcript.cues):
        if rows is not None:
            row = list(rows[idx])
            if len(row) < len(header):
                row.extend([""] * (len(header) - len(row)))
        else:
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
