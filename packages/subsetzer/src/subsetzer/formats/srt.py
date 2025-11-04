"""SRT parsing and serialisation."""
from __future__ import annotations

from typing import List

from ..engine import Cue, Transcript, TranscriptError
from .common import clean_lines, split_times

__all__ = ["parse_srt", "write_srt"]


def parse_srt(text: str) -> Transcript:
    lines = clean_lines(text)
    cues: List[Cue] = []
    block: List[str] = []

    def flush(block_lines: List[str]) -> None:
        if not block_lines:
            return
        filtered = [line.replace("\ufeff", "") for line in block_lines]
        while filtered and not filtered[0].strip():
            filtered.pop(0)
        while filtered and not filtered[-1].strip():
            filtered.pop()
        if len(filtered) < 2:
            return
        first = filtered[0].strip()
        second = filtered[1] if len(filtered) > 1 else ""
        text_start = 2
        try:
            idx = int(first)
            time_line = second
        except ValueError:
            idx = len(cues) + 1
            if "-->" in filtered[0]:
                time_line = filtered[0]
                text_start = 1
            else:
                time_line = filtered[1]
        text_lines = filtered[text_start:]
        start, end = split_times(time_line)
        cues.append(Cue(index=idx, start=start, end=end, text="\n".join(text_lines)))

    for line in lines:
        if line.strip() == "":
            flush(block)
            block = []
        else:
            block.append(line)
    flush(block)

    if not cues:
        raise TranscriptError("No cues parsed from SRT file.")

    return Transcript(fmt="srt", cues=cues)


def write_srt(transcript: Transcript) -> str:
    segments = []
    for idx, cue in enumerate(transcript.cues, start=1):
        text = cue.translated if cue.translated is not None else cue.text
        segments.append(f"{idx}\n{cue.start} --> {cue.end}\n{text}")
    return "\n\n".join(segments) + "\n"
