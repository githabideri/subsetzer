"""Core translation engine interacting with Ollama-compatible servers."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

__all__ = [
    "Cue",
    "Transcript",
    "Chunk",
    "TranscriptError",
    "LLMError",
    "llm_translate_single",
    "llm_translate_batch",
    "translate_range",
    "_apply_batch",
]


@dataclass
class Cue:
    index: int
    start: str
    end: str
    text: str
    translated: Optional[str] = None


@dataclass
class Transcript:
    fmt: str
    cues: List[Cue]
    header: str = ""
    tsv_header: Optional[List[str]] = None
    tsv_cols: Optional[Tuple[int, int, int]] = None


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


class LLMError(RuntimeError):
    """Raised when the LLM could not be contacted or returned malformed data."""


def _extract_message(payload: object) -> str:
    if not isinstance(payload, dict):
        raise LLMError("Unexpected payload type; expected JSON object.")
    # OpenAI compatibility: {"choices": [{"message": {"content": "..."}}, ...]}
    if "choices" in payload:
        try:
            return payload["choices"][0]["message"]["content"]
        except Exception as exc:  # pragma: no cover - defensive
            raise LLMError(f"Unable to extract chat message: {exc}") from exc
    if "response" in payload:
        return str(payload["response"])
    if "message" in payload and isinstance(payload["message"], dict):
        return str(payload["message"].get("content", ""))
    raise LLMError("LLM response did not include recognised content field.")


def _http_json(
    url: str,
    payload: Dict[str, object],
    timeout: float,
    *,
    stream: bool,
    raw_handler: Optional[Callable[[str], None]] = None,
) -> str:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # type: ignore[call-arg]
            if not stream:
                body = resp.read().decode("utf-8", errors="replace")
                if raw_handler:
                    raw_handler(body)
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError as exc:
                    raise LLMError(f"Malformed JSON response from server: {exc}") from exc
                return _extract_message(parsed)

            pieces: List[str] = []
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if raw_handler:
                    raw_handler(line)
                if line == "data: [DONE]":
                    break
                if line.startswith("data:"):
                    line = line[len("data:") :].strip()
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    piece = _extract_message(parsed)
                except LLMError:
                    continue
                pieces.append(piece)
            return "".join(pieces)
    except (HTTPError, URLError) as exc:
        raise LLMError(f"HTTP error contacting LLM server: {exc}") from exc


_TAG_RE = re.compile(r"</?[^>]+?>")
_BRACKET_RE = re.compile(r"\[[^\]]+\]")
_TIMECODE_LINE_RE = re.compile(r"^\d+\s*:\s*\d+:\d+", re.MULTILINE)
_INLINE_MARKER_RE = re.compile(
    r"^\s*(?:CUE|OUTPUT|TRANSLATION|TRANSLATED|RESPONSE|ANSWER)\s*:\s*(.*)$",
    re.IGNORECASE,
)


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
    lines = cleaned.split("\n")
    output: List[str] = []
    for line in lines:
        marker_match = _INLINE_MARKER_RE.match(line)
        if marker_match:
            output = []
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


def _perform_llm_call(
    *,
    server: str,
    mode: str,
    body: Dict[str, object],
    generate_prompt: str,
    stream: bool,
    timeout: float,
    raw_handler: Optional[Callable[[str], None]] = None,
) -> str:
    mode = (mode or "auto").lower()

    def request_chat() -> str:
        url = server.rstrip("/") + "/api/chat"
        return _http_json(url, body, timeout, stream=stream, raw_handler=raw_handler)

    def request_generate() -> str:
        payload = {
            "model": body.get("model"),
            "prompt": generate_prompt,
            "stream": stream,
        }
        url = server.rstrip("/") + "/api/generate"
        return _http_json(url, payload, timeout, stream=stream, raw_handler=raw_handler)

    if mode == "chat":
        return request_chat()
    if mode == "generate":
        return request_generate()
    try:
        return request_chat()
    except LLMError as exc:
        # Fallback to /generate if /chat fails
        return request_generate()


def llm_translate_single(
    text: str,
    *,
    source: str,
    target: str,
    model: str,
    server: str,
    translate_bracketed: bool,
    llm_mode: str,
    stream: bool,
    timeout: float,
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
        "Preserve placeholders, formatting, and whitespace exactly."
    ).format(src=source or "auto-detected language", dst=target)
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

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise subtitle translator."},
            {"role": "user", "content": message_content},
        ],
        "stream": stream,
    }

    raw_result = _perform_llm_call(
        server=server,
        mode=llm_mode,
        body=body,
        generate_prompt=message_content,
        stream=stream,
        timeout=timeout,
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
    source: str,
    target: str,
    model: str,
    server: str,
    llm_mode: str,
    stream: bool,
    timeout: float,
    translate_bracketed: bool,
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
    ).format(src=source or "auto-detected language", dst=target)

    joined = "\n".join(inputs)
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You translate subtitles in bulk."},
            {"role": "user", "content": f"{instructions}\n\nINPUT:\n{joined}"},
        ],
        "stream": stream,
    }

    result = _perform_llm_call(
        server=server,
        mode=llm_mode,
        body=body,
        generate_prompt=f"{instructions}\n\n{joined}",
        stream=stream,
        timeout=timeout,
        raw_handler=raw_handler,
    )

    mapping: Dict[str, str] = {}
    if result:
        blocks = re.split(r"\r?\n(?=\s*\S+\|\|\|)", result.strip())
    else:
        blocks = []
    for block in blocks:
        if "|||" not in block:
            continue
        trimmed = block.strip("\r\n")
        if not trimmed:
            continue
        first_line, *rest_lines = trimmed.splitlines()
        if "|||" not in first_line:
            continue
        pid, translated_head = first_line.split("|||", 1)
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


def _apply_batch(
    batch: List[Tuple[str, str]],
    cues_slice: List[Cue],
    source: str,
    target: str,
    model: str,
    server: str,
    llm_mode: str,
    stream: bool,
    timeout: float,
    translate_bracketed: bool,
    raw_handler: Optional[Callable[[str], None]],
) -> List[str]:
    translated_pairs = llm_translate_batch(
        batch,
        source=source,
        target=target,
        model=model,
        server=server,
        llm_mode=llm_mode,
        stream=stream,
        timeout=timeout,
        translate_bracketed=translate_bracketed,
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
            source=source,
            target=target,
            model=model,
            server=server,
            translate_bracketed=translate_bracketed,
            llm_mode=llm_mode,
            stream=stream,
            timeout=timeout,
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
    server: str,
    model: str,
    source: str,
    target: str,
    batch_n: int,
    translate_bracketed: bool,
    llm_mode: str,
    stream: bool,
    timeout: float,
    no_llm: bool,
    logger: Optional[Callable[[str], None]] = None,
    raw_handler: Optional[Callable[[str], None]] = None,
    verbose: bool = False,
) -> None:
    if batch_n <= 0:
        raise ValueError("batch_n must be positive")

    for chunk in chunks:
        if logger and verbose:
            logger(
                f"Processing chunk {chunk.cid} covering cues {chunk.start_idx}-{chunk.end_idx}"
            )
        start = chunk.start_idx - 1
        end = chunk.end_idx
        cues_slice = transcript.cues[start:end]
        try:
            if no_llm:
                for cue in cues_slice:
                    cue.translated = cue.text
                chunk.status = "done"
                continue
            if batch_n == 1:
                for cue in cues_slice:
                    translated = llm_translate_single(
                        cue.text,
                        source=source,
                        target=target,
                        model=model,
                        server=server,
                        translate_bracketed=translate_bracketed,
                        llm_mode=llm_mode,
                        stream=stream,
                        timeout=timeout,
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
            else:
                batch: List[Tuple[str, str]] = []
                for cue in cues_slice:
                    batch.append((str(cue.index), cue.text))
                    if len(batch) == batch_n:
                        missing = _apply_batch(
                            batch,
                            cues_slice,
                            source,
                            target,
                            model,
                            server,
                            llm_mode,
                            stream,
                            timeout,
                            translate_bracketed,
                            raw_handler,
                        )
                        if missing and logger:
                            logger("Warning: missing translations for IDs " + ", ".join(missing))
                        batch = []
                if batch:
                    missing = _apply_batch(
                        batch,
                        cues_slice,
                        source,
                        target,
                        model,
                        server,
                        llm_mode,
                        stream,
                        timeout,
                        translate_bracketed,
                        raw_handler,
                    )
                    if missing and logger:
                        logger("Warning: missing translations for IDs " + ", ".join(missing))
            chunk.status = "done"
        except LLMError as exc:
            chunk.status = "error"
            chunk.err = str(exc)
            if logger:
                logger(f"Error processing chunk {chunk.cid}: {exc}")
            raise RuntimeError(f"Chunk {chunk.cid} failed: {exc}") from exc
