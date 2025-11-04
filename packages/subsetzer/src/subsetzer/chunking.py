"""Chunk planning utilities."""
from __future__ import annotations

from typing import List

from .engine import Chunk, Cue

__all__ = ["make_chunks"]


def make_chunks(cues: List[Cue], max_chars: int) -> List[Chunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    chunks: List[Chunk] = []
    cid = 1
    char_total = 0
    start_pos = 0
    cue_total = 0
    max_cues_per_chunk = max(5, max_chars // 80)

    for pos, cue in enumerate(cues):
        text_len = len(cue.text) + cue.text.count("\n")
        text_len += len(str(cue.index)) + len(cue.start) + len(cue.end) + 5
        if not text_len:
            text_len = 1
        needs_split = False
        if char_total and char_total + text_len > max_chars:
            needs_split = True
        if cue_total and cue_total >= max_cues_per_chunk:
            needs_split = True
        if needs_split:
            chunks.append(
                Chunk(
                    cid=cid,
                    start_idx=start_pos + 1,
                    end_idx=pos,
                    charcount=char_total,
                )
            )
            cid += 1
            start_pos = pos
            char_total = 0
            cue_total = 0
        char_total += text_len
        cue_total += 1

    if cues:
        chunks.append(
            Chunk(
                cid=cid,
                start_idx=start_pos + 1,
                end_idx=len(cues),
                charcount=char_total,
            )
        )
    return chunks

