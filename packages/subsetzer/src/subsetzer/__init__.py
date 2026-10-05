"""Subsetzer core package."""
from __future__ import annotations

from .version import __version__
from .backends import LLMBackend, LLMError, OpenAICompat
from .engine import (
    Cue,
    Chunk,
    LLMError,
    Transcript,
    TranscriptError,
    llm_translate_batch,
    llm_translate_single,
    translate_range,
)
from .chunking import make_chunks
from .langs import display_name, is_known_lang, normalise_lang
from .io import (
    build_output,
    build_output_as,
    detect_format,
    read_transcript,
    resolve_outfile,
)

__all__ = [
    "__version__",
    "Cue",
    "LLMBackend",
    "LLMError",
    "OpenAICompat",
    "display_name",
    "is_known_lang",
    "normalise_lang",
    "Chunk",
    "Transcript",
    "TranscriptError",
    "build_output",
    "build_output_as",
    "detect_format",
    "llm_translate_batch",
    "llm_translate_single",
    "make_chunks",
    "read_transcript",
    "resolve_outfile",
    "translate_range",
]

