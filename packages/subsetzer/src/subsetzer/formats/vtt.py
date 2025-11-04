"""WebVTT parsing and serialisation."""
from __future__ import annotations

from typing import List, Optional

from ..engine import Cue, Transcript, TranscriptError
from .common import clean_lines, split_times

__all__ = ["parse_vtt", "write_vtt", "split_times"]


def parse_vtt(text: str) -> Transcript:
    lines = clean_lines(text)
    header_lines: List[str] = []
    cues: List[Cue] = []
    block: List[str] = []
    seen_header = False

    for line in lines:
        if not seen_header:
            header_lines.append(line)
            if line.strip() == "":
                seen_header = True
            continue
        if line.strip() == "":
            if block:
                _flush_vtt_block(block, cues)
                block = []
        else:
            block.append(line)
    if block:
        _flush_vtt_block(block, cues)

    header = "\n".join(header_lines).strip("\n")
    if not header.upper().startswith("WEBVTT"):
        header = "WEBVTT" + ("\n" + header if header else "")

    if not cues:
        raise TranscriptError("No cues parsed from VTT file.")

    return Transcript(fmt="vtt", cues=cues, header=header)


def _flush_vtt_block(block: List[str], cues: List[Cue]) -> None:
    if not block:
        return
    time_line: Optional[str] = None
    text_start = 0
    if "-->" in block[0]:
        time_line = block[0]
        text_start = 1
    else:
        for idx, candidate in enumerate(block[1:], start=1):
            if "-->" in candidate:
                time_line = candidate
                text_start = idx + 1
                break
    if not time_line:
        return
    start, end = split_times(time_line)
    text = "\n".join(block[text_start:])
    index = len(cues) + 1
    cues.append(Cue(index=index, start=start, end=end, text=text))


def write_vtt(transcript: Transcript, note: Optional[str] = None) -> str:
    header = transcript.header or "WEBVTT"
    lines = [header.strip(), ""]
    if note:
        lines.append(f"NOTE {note}")
        lines.append("")
    for cue in transcript.cues:
        text = cue.translated if cue.translated is not None else cue.text
        lines.append(f"{cue.start} --> {cue.end}")
        lines.extend(text.split("\n"))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
