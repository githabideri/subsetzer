"""Core translation engine.

Talks to OpenAI-compatible LLM servers through :mod:`subsetzer.backends`
(the default :class:`~subsetzer.backends.OpenAICompat` client covers vLLM,
llama.cpp, LM Studio, SGLang and Ollama's ``/v1`` API).
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .backends import LLMBackend, LLMError, OpenAICompat
from .langs import display_name as _prompt_lang

__all__ = [
    "Cue",
    "Transcript",
    "Chunk",
    "TranscriptError",
    "LLMError",
    "LLMBackend",
    "OpenAICompat",
    "llm_translate_single",
    "llm_translate_batch",
    "llm_translate_batch_structured",
    "translate_range",
    "_apply_batch",
    "_collapse_text",
    "_remove_punctuation",
]


@dataclass
class Cue:
    index: int
    start: str
    end: str
    text: str
    translated: Optional[str] = None
    settings: str = ""


@dataclass
class Transcript:
    fmt: str
    cues: List[Cue]
    header: str = ""
    tsv_header: Optional[List[str]] = None
    tsv_cols: Optional[Tuple[int, int, int]] = None
    tsv_rows: Optional[List[List[str]]] = None
    tsv_delimiter: str = "\t"


@dataclass
class Chunk:
    cid: int
    start_idx: int
    end_idx: int
    charcount: int
    status: str = "pending"
    err: Optional[str] = None


class TranscriptError(RuntimeError):
    """Raised for parsing and formatting problems."""


_TAG_RE = re.compile(r"</?[^>]+?>")
_BRACKET_RE = re.compile(r"\[[^\]]+\]")
_TIMECODE_LINE_RE = re.compile(r"^\d+\s*:\s*\d+:\d+", re.MULTILINE)
_INLINE_MARKER_RE = re.compile(
    r"^\s*(?:CUE|OUTPUT|TRANSLATION|TRANSLATED|RESPONSE|ANSWER|INPUT)\s*:\s*(.*)$",
    re.IGNORECASE,
)

# Punctuation stripped by --no-punc. CJK full-width forms and common Latin
# punctuation; dashes and ASCII brackets are preserved (brackets often mark
# tags such as [MUSIC] or [APPLAUSE]).
_PUNCT_CHARS = "！？。，、；：\u201c\u201d\u2018\u2019《》【】〖〗『』「」〈〉（）…—~·.,\'\"?!;:"
_PUNCT_RE = re.compile("[" + re.escape(_PUNCT_CHARS) + "]")
_DASH_SPEAKER_RE = re.compile(r"^\s*-\s")


def _remove_punctuation(text: str) -> str:
    """Strip punctuation from cue text, keeping dashes."""
    if not text:
        return text
    cleaned = _PUNCT_RE.sub(" ", text)
    cleaned = re.sub(r" +", " ", cleaned)
    return cleaned.strip()


def _collapse_text(text: str) -> str:
    """Fold a multi-line translation into a single line.

    If every line starts with ``- `` (dialogue/speaker style), the markers
    are removed before joining.
    """
    text = text.strip()
    if not text:
        return text

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return text

    if len(lines) > 1 and all(_DASH_SPEAKER_RE.match(line) for line in lines):
        lines = [re.sub(r"^\s*-\s*", "", line) for line in lines]

    return re.sub(r" +", " ", " ".join(lines)).strip()


def _protect_tags(text: str) -> Tuple[str, Dict[str, str]]:
    mapping: Dict[str, str] = {}
    counter = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal counter
        placeholder = f"__TAG{counter}__"
        mapping[placeholder] = match.group(0)
        counter += 1
        return placeholder

    protected = _TAG_RE.sub(repl, text)
    return protected, mapping


def _protect_brackets(text: str) -> Tuple[str, Dict[str, str]]:
    mapping: Dict[str, str] = {}
    counter = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal counter
        placeholder = f"__BR{counter}__"
        mapping[placeholder] = match.group(0)
        counter += 1
        return placeholder

    protected = _BRACKET_RE.sub(repl, text)
    return protected, mapping


def _restore_placeholders(text: str, mapping: Dict[str, str]) -> str:
    for placeholder, value in mapping.items():
        text = text.replace(placeholder, value)
    return text


def _cleanup_translation(text: str) -> str:
    if not text:
        return text

    cleaned = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    sentinel = re.search(r"<translation>(.*?)</translation>", cleaned, re.IGNORECASE | re.DOTALL)
    if sentinel:
        content = sentinel.group(1)
        content = re.sub(r"(?<!\|)\|\|(?!\|)", "\n", content)
        return content.strip()

    cleaned = re.sub(r"(?<!\|)\|\|(?!\|)", "\n", cleaned)
    lines = cleaned.split("\n")
    output: List[str] = []
    for line in lines:
        marker_match = _INLINE_MARKER_RE.match(line)
        if marker_match:
            output = []
            label = line.split(":", 1)[0].strip().lower()
            if label == "input":
                continue
            remainder = marker_match.group(1)
            if remainder:
                output.append(remainder)
            continue
        if _TIMECODE_LINE_RE.match(line.strip()):
            continue
        output.append(line)

    trailing_blank_lines = 0
    for line in reversed(output):
        if line.strip():
            break
        trailing_blank_lines += 1

    collapsed: List[str] = []
    blank_run = False
    for line in output:
        if line.strip():
            collapsed.append(line)
            blank_run = False
        else:
            if collapsed and not blank_run:
                collapsed.append("")
            blank_run = True

    output = collapsed
    while output and not output[0].strip():
        output.pop(0)
    while output and not output[-1].strip():
        output.pop()

    result = "\n".join(output)
    if trailing_blank_lines == 1 and cleaned.endswith(("\n", "\r")) and result:
        result += "\n"
    return result


def llm_translate_single(
    text: str,
    *,
    backend: LLMBackend,
    model: str,
    source: str,
    target: str,
    translate_bracketed: bool = True,
    stream: Optional[bool] = None,
    raw_handler: Optional[Callable[[str], None]] = None,
    context_before: str = "",
    context_after: str = "",
    previous_translation: str = "",
    next_translation: str = "",
    force_distinct: bool = False,
) -> str:
    prepared, tag_map = _protect_tags(text)
    bracket_map: Dict[str, str] = {}
    if not translate_bracketed:
        prepared, bracket_map = _protect_brackets(prepared)

    prompt = (
        "Translate the following subtitle cue from {src} to {dst}. "
        "Preserve placeholders, formatting, and whitespace exactly. "
        "Return only the translated cue wrapped between <translation> and </translation> tags; "
        "do not add commentary before or after the tags."
    ).format(src=_prompt_lang(source), dst=_prompt_lang(target))
    if context_before or context_after:
        prompt += (
            " Use the surrounding context to ensure the cue reads naturally within the full sentence, "
            "but limit the translation strictly to the current cue."
        )
    if force_distinct:
        prompt += (
            " Do not output the original wording or repeat neighbouring translations."
            " Produce a natural target-language fragment that fits the same display duration."
        )

    message_content = _build_single_prompt(
        prompt,
        prepared,
        context_before,
        context_after,
        previous_translation,
        next_translation,
    )

    raw_result = backend.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a professional subtitle translator. "
                    f"Always produce natural, idiomatic {_prompt_lang(target)}. "
                    "Never echo the source text. Output ONLY the translation."
                ),
            },
            {"role": "user", "content": message_content},
        ],
        stream=stream,
        raw_handler=raw_handler,
    )

    if not raw_result:
        return text
    cleaned = _cleanup_translation(raw_result)
    if not cleaned.strip():
        return text
    return _restore_placeholders(cleaned, {**tag_map, **bracket_map})


def _build_single_prompt(
    prompt: str,
    cue_text: str,
    context_before: str,
    context_after: str,
    previous_translation: str,
    next_translation: str,
) -> str:
    sections: List[str] = [prompt, ""]
    if context_before.strip():
        sections.append("PREVIOUS CUE:")
        sections.append(context_before.strip())
        sections.append("")
    sections.append("CURRENT CUE:")
    sections.append(cue_text)
    if context_after.strip():
        sections.append("")
        sections.append("NEXT CUE:")
        sections.append(context_after.strip())
    if previous_translation.strip():
        sections.append("")
        sections.append("PREVIOUS TRANSLATION:")
        sections.append(previous_translation.strip())
    if next_translation.strip():
        sections.append("")
        sections.append("NEXT TRANSLATION (if known):")
        sections.append(next_translation.strip())
    return "\n".join(sections)


def llm_translate_batch(
    pairs: List[Tuple[str, str]],
    *,
    backend: LLMBackend,
    model: str,
    source: str,
    target: str,
    translate_bracketed: bool = True,
    stream: Optional[bool] = None,
    raw_handler: Optional[Callable[[str], None]] = None,
) -> List[Tuple[str, str]]:
    protected_pairs: List[Tuple[str, str, Dict[str, str], Dict[str, str]]] = []
    inputs: List[str] = []
    for pid, text in pairs:
        prepared, tag_map = _protect_tags(text)
        bracket_map: Dict[str, str] = {}
        if not translate_bracketed:
            prepared, bracket_map = _protect_brackets(prepared)
        inputs.append(f"{pid}|||{prepared}")
        protected_pairs.append((pid, prepared, tag_map, bracket_map))

    instructions = (
        "Translate the following subtitle cues from {src} to {dst}. "
        "Cues form a continuous transcript and may contain partial sentences. "
        "Keep each translated cue natural and roughly similar in length to the source fragment so it fits the on-screen timing. "
        "For each cue, start a block with ID||| immediately followed by the translation. "
        "If a translation spans multiple subtitle lines, continue on subsequent lines until the next ID||| block begins. "
        "Do not merge cues together, do not skip any IDs, and never leave a cue empty."
    ).format(src=_prompt_lang(source), dst=_prompt_lang(target))

    joined = "\n".join(inputs)
    result = backend.chat(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You translate subtitles in bulk from {_prompt_lang(source)} to {_prompt_lang(target)}. "
                    f"Always produce natural, idiomatic {_prompt_lang(target)}. "
                    "Never echo the source text."
                ),
            },
            {"role": "user", "content": f"{instructions}\n\nINPUT:\n{joined}"},
        ],
        stream=stream,
        raw_handler=raw_handler,
    )

    mapping: Dict[str, str] = {}
    if result:
        lines = [line for line in result.strip().splitlines() if line.strip()]
        while lines and "|||" not in lines[0]:
            lines.pop(0)
        filtered = "\n".join(lines)
        blocks = re.split(r"\r?\n(?=\s*\S+\|\|\|)", filtered) if filtered else []
    else:
        blocks = []
    for block in blocks:
        if "|||" not in block:
            continue
        trimmed = block.strip("\r\n")
        if not trimmed:
            continue
        first_line, *rest_lines = trimmed.splitlines()
        marker_index = first_line.find("|||")
        if marker_index == -1:
            continue
        raw_pid = first_line[:marker_index].strip()
        pid_match = re.search(r"(\d+)$", raw_pid) if raw_pid else None
        pid = pid_match.group(1) if pid_match else raw_pid
        if not pid:
            continue
        translated_head = first_line[marker_index + 3 :]
        translated = translated_head
        if rest_lines:
            translated += "\n" + "\n".join(rest_lines)
        mapping[pid.strip()] = translated

    output: List[Tuple[str, str]] = []
    for pid, prepared, tag_map, bracket_map in protected_pairs:
        translated = mapping.get(pid)
        if translated is None:
            restored = _restore_placeholders(prepared, {**tag_map, **bracket_map})
        else:
            cleaned = _cleanup_translation(translated)
            if not cleaned.strip():
                restored = _restore_placeholders(prepared, {**tag_map, **bracket_map})
            else:
                restored = _restore_placeholders(cleaned, {**tag_map, **bracket_map})
        output.append((pid, restored))
    return output


def llm_translate_batch_structured(
    pairs: List[Tuple[str, str]],
    *,
    backend: LLMBackend,
    model: str,
    source: str,
    target: str,
    mode: str = "json",
    translate_bracketed: bool = True,
    stream: Optional[bool] = None,
    raw_handler: Optional[Callable[[str], None]] = None,
    repetition_detection: bool = False,
    seed: Optional[int] = None,
) -> Tuple[List[Tuple[str, str]], str]:
    """Batch translate with a *declared* response contract.

    ``mode`` is ``"json"`` (``response_format: json_schema`` — array of
    exactly ``len(pairs)`` strings) or ``"json_object"``
    (``{type: json_object}`` with a ``{"lines": [...]}`` wrapper prompt).
    Returns ``(pairs, status)`` where status is ``"ok"`` (all cues
    translated), ``"degenerate"`` (server loop detector stopped the run —
    vLLM ``finish_reason: "repetition"``) or ``"malformed"`` (response did
    not satisfy the contract).
    """
    chat_full = getattr(backend, "chat_full", None)
    if not isinstance(backend, OpenAICompat):
        # Duck-typed backends without structured support: sentinel fallback.
        return llm_translate_batch(
            pairs,
            backend=backend,
            model=model,
            source=source,
            target=target,
            translate_bracketed=translate_bracketed,
            stream=stream,
            raw_handler=raw_handler,
        ), "ok"

    protected: List[Tuple[str, str, Dict[str, str], Dict[str, str]]] = []
    lines: List[str] = []
    for pid, text in pairs:
        prepared, tag_map = _protect_tags(text)
        bracket_map: Dict[str, str] = {}
        if not translate_bracketed:
            prepared, bracket_map = _protect_brackets(prepared)
        lines.append(f"{len(lines) + 1}. {prepared}")
        protected.append((pid, prepared, tag_map, bracket_map))
    n = len(pairs)

    instructions = (
        "Translate the following subtitle cues from {src} to {dst}. "
        "Cues form a continuous transcript and may contain partial sentences. "
        "Keep each translated cue natural and roughly similar in length to the source fragment so it fits the on-screen timing. "
        "Do not merge cues together and never leave a translation empty. "
    ).format(src=_prompt_lang(source), dst=_prompt_lang(target))
    if mode == "json":
        instructions += (
            f"Reply with a JSON array of exactly {n} strings — one translation per cue, in the given order. Nothing else."
        )
        response_format: Optional[Dict[str, object]] = {
            "type": "json_schema",
            "json_schema": {
                "name": "lines",
                "strict": True,
                "schema": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": n,
                    "maxItems": n,
                },
            },
        }
    else:
        instructions += (
            f'Reply with a JSON object: {{"lines": [...]}} containing exactly {n} strings — one translation per cue, in the given order. Nothing else.'
        )
        response_format = {"type": "json_object"}

    result = chat_full(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    f"You translate subtitles in bulk from {_prompt_lang(source)} to {_prompt_lang(target)}. "
                    f"Always produce natural, idiomatic {_prompt_lang(target)}. "
                    "Never echo the source text."
                ),
            },
            {"role": "user", "content": f"{instructions}\n\n" + "\n".join(lines)},
        ],
        response_format=response_format,
        repetition_detection=(
            {"max_pattern_size": 8, "min_count": 3} if repetition_detection else None
        ),
        seed=seed,
    )
    content = result.get("content") or ""
    finish_reason = result.get("finish_reason")
    if finish_reason == "repetition":
        return [], "degenerate"
    from .backends import parse_string_array

    translations = parse_string_array(content, n=n)
    if translations is None:
        return [], "malformed"
    out: List[Tuple[str, str]] = []
    for (pid, prepared, tag_map, bracket_map), translated in zip(protected, translations):
        cleaned = _cleanup_translation(translated)
        if not cleaned.strip():
            cleaned = prepared
        out.append((pid, _restore_placeholders(cleaned, {**tag_map, **bracket_map})))
    return out, "ok"


def _new_seed() -> int:
    return random.randint(1, 2**31 - 1)


def _apply_batch(
    batch: List[Tuple[str, str]],
    cues_slice: List[Cue],
    *,
    source: str,
    target: str,
    model: str,
    backend: LLMBackend,
    translate_bracketed: bool = True,
    stream: Optional[bool] = None,
    raw_handler: Optional[Callable[[str], None]] = None,
    mode: str = "sentinel",
    caps: Optional[Dict[str, bool]] = None,
    logger: Optional[Callable[[str], None]] = None,
) -> List[str]:
    mapping: Dict[str, str] = {}
    status = "ok"
    if mode in ("json", "json_object") and isinstance(backend, OpenAICompat):
        rd = bool(caps and caps.get("repetition_detection"))
        for seed in (None, _new_seed()):
            pairs, status = llm_translate_batch_structured(
                batch,
                backend=backend,
                model=model,
                source=source,
                target=target,
                mode=mode,
                translate_bracketed=translate_bracketed,
                stream=stream,
                raw_handler=raw_handler,
                repetition_detection=rd,
                seed=seed,
            )
            mapping = {pid: text for pid, text in pairs}
            if status == "ok":
                break
            if status != "degenerate":
                break  # malformed: one seeded retry is not worth it; per-cue fallback below
        if status == "degenerate":
            cue_index = {str(cue.index): cue for cue in cues_slice}
            missing: List[str] = []
            for pid, _ in batch:
                cue = cue_index.get(pid)
                if cue is not None:
                    cue.translated = cue.text  # keep source: visible marker for a human
                missing.append(pid)
            if logger:
                for pid in missing:
                    logger(f"Flagged cue {pid}: model degenerated (repetition loop); left as source text")
            return missing
    else:
        translated_pairs = llm_translate_batch(
            batch,
            backend=backend,
            source=source,
            target=target,
            model=model,
            translate_bracketed=translate_bracketed,
            stream=stream,
            raw_handler=raw_handler,
        )
        mapping = {pid: text for pid, text in translated_pairs}

    cue_index = {str(cue.index): cue for cue in cues_slice}
    pending: List[Tuple[str, Optional[Cue]]] = []
    for pid, _ in batch:
        cue = cue_index.get(pid)
        if not cue:
            pending.append((pid, None))
            continue
        translated = mapping.get(pid)
        if translated is None or not translated.strip() or translated.strip() == cue.text.strip():
            pending.append((pid, cue))
        else:
            cue.translated = translated

    missing: List[str] = []
    if not pending:
        return missing

    for pid, cue in pending:
        if cue is None:
            missing.append(pid)
            continue
        idx = cues_slice.index(cue)
        context_before = ""
        previous_translation = ""
        if idx > 0:
            prev = cues_slice[idx - 1]
            context_before = prev.translated if prev.translated is not None else prev.text
            previous_translation = prev.translated or ""
        context_after = cues_slice[idx + 1].text if idx + 1 < len(cues_slice) else ""
        next_translation = (
            cues_slice[idx + 1].translated or ""
            if idx + 1 < len(cues_slice) and cues_slice[idx + 1].translated is not None
            else ""
        )
        retry = llm_translate_single(
            cue.text,
            backend=backend,
            model=model,
            source=source,
            target=target,
            translate_bracketed=translate_bracketed,
            stream=stream,
            raw_handler=raw_handler,
            context_before=context_before,
            context_after=context_after,
            previous_translation=previous_translation,
            next_translation=next_translation,
            force_distinct=True,
        )
        if retry and retry.strip():
            cue.translated = retry
        else:
            cue.translated = cue.text
            missing.append(pid)
    return missing


def translate_range(
    transcript: Transcript,
    chunks: List[Chunk],
    *,
    backend: LLMBackend,
    model: str,
    source: str,
    target: str,
    batch_n: int,
    translate_bracketed: bool = True,
    no_llm: bool = False,
    one_line: bool = False,
    no_punc: bool = False,
    stream: Optional[bool] = None,
    logger: Optional[Callable[[str], None]] = None,
    raw_handler: Optional[Callable[[str], None]] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    verbose: bool = False,
) -> None:
    """Translate cues of ``transcript`` within the given chunks in place.

    ``progress`` (if given) is called as ``progress(done, total)`` as cues
    complete. When not ``no_llm``, ``one_line``/``no_punc`` post-process
    every translated cue (fold multi-line cues to one line; strip
    punctuation, keeping dashes).
    """
    if batch_n <= 0:
        raise ValueError("batch_n must be positive")

    # Capability probe (once per server+model, cached on the backend):
    # picks the strongest response contract the server honors. Servers
    # without structured-output support (or any backend that lacks the
    # structured API) keep the sentinel protocol.
    mode = "sentinel"
    caps: Optional[Dict[str, bool]] = None
    if batch_n > 1 and isinstance(backend, OpenAICompat):
        try:
            caps = backend.probe_capabilities(model)
            if caps.get("json_schema"):
                mode = "json"
            elif caps.get("json_object"):
                mode = "json_object"
        except LLMError:
            mode = "sentinel"  # server unreachable etc.; the real call will surface it
        if logger:
            logger(f"Response contract: {mode}" + (" (repetition detection on)" if caps and caps.get("repetition_detection") else ""))

    total_cues = len(transcript.cues)
    cues_done = 0

    for chunk in chunks:
        if logger and verbose:
            logger(f"Processing chunk {chunk.cid} covering cues {chunk.start_idx}-{chunk.end_idx}")
        start = chunk.start_idx - 1
        end = chunk.end_idx
        cues_slice = transcript.cues[start:end]
        try:
            if no_llm:
                for cue in cues_slice:
                    cue.translated = cue.text
                cues_done += len(cues_slice)
                if progress:
                    progress(cues_done, total_cues)
                chunk.status = "done"
                continue
            if batch_n == 1:
                for cue in cues_slice:
                    translated = llm_translate_single(
                        cue.text,
                        backend=backend,
                        model=model,
                        source=source,
                        target=target,
                        translate_bracketed=translate_bracketed,
                        stream=stream,
                        raw_handler=raw_handler,
                    )
                    if translated:
                        cue.translated = translated
                    else:
                        cue.translated = cue.text
                        if logger:
                            logger(
                                f"Warning: empty translation for cue {cue.index}; reused original text"
                            )
                    cues_done += 1
                    if progress:
                        progress(cues_done, total_cues)
            else:
                batch: List[Tuple[str, str]] = []
                for cue in cues_slice:
                    batch.append((str(cue.index), cue.text))
                    if len(batch) == batch_n:
                        missing = _apply_batch(
                            batch,
                            cues_slice,
                            source=source,
                            target=target,
                            model=model,
                            backend=backend,
                            translate_bracketed=translate_bracketed,
                            stream=stream,
                            raw_handler=raw_handler,
                            mode=mode,
                            caps=caps,
                            logger=logger,
                        )
                        cues_done += len(batch)
                        if progress:
                            progress(cues_done, total_cues)
                        if missing and logger:
                            logger("Warning: missing translations for IDs " + ", ".join(missing))
                        batch = []
                if batch:
                    missing = _apply_batch(
                        batch,
                        cues_slice,
                        source=source,
                        target=target,
                        model=model,
                        backend=backend,
                        translate_bracketed=translate_bracketed,
                        stream=stream,
                        raw_handler=raw_handler,
                        mode=mode,
                        caps=caps,
                        logger=logger,
                    )
                    cues_done += len(batch)
                    if progress:
                        progress(cues_done, total_cues)
                    if missing and logger:
                        logger("Warning: missing translations for IDs " + ", ".join(missing))
            chunk.status = "done"
        except LLMError as exc:
            chunk.status = "error"
            chunk.err = str(exc)
            if logger:
                logger(f"Error processing chunk {chunk.cid}: {exc}")
            raise RuntimeError(f"Chunk {chunk.cid} failed: {exc}") from exc

    if not no_llm:
        for cue in transcript.cues:
            if cue.translated is None:
                continue
            if one_line:
                cue.translated = _collapse_text(cue.translated)
            if no_punc:
                cue.translated = _remove_punctuation(cue.translated)
