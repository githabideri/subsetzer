---
title: subsetzer Engine Workflow Analysis
date: 2025-11-06
tags:
  - python
  - llm
  - subtitle
  - translation
  - chunking
  - engineering
alias:
  - Engine Workflow Guide
status: done
type: technical-documentation
author: Qwen3 4B Instruct (38k)

---

# subsetzer Engine Workflow Documentation

## Overview
The subsetzer engine implements a modular, chunked translation workflow for subtitle files using LLMs. This document details the step-by-step processing logic within the engine module.

## 1. Core Data Structures

### Cue
Represents a single subtitle cue with timing and text:
```python
@dataclass
class Cue:
    index: int
    start: str
    end: str
    text: str
    translated: Optional[str] = None
`\`

### Transcript
Container for a full subtitle file with cues and metadata:
```python
@dataclass
class Transcript:
    fmt: str
    cues: List[Cue]
    header: str = ""
    tsv_header: Optional[List[str]] = None
    tsv_cols: Optional[Tuple[int, int, int]] = None
`\`

### Chunk
Represents a processing segment of cues:
```python
@dataclass
class Chunk:
    cid: int
    start_idx: int
    end_idx: int
    charcount: int
    status: str = "pending"
    err: Optional[str] = None
`\`

## 2. Error Handling

- `TranscriptError`: Raised for parsing/formatting issues
- `LLMError`: Raised when LLM communication fails or returns malformed data

## 3. Translation Workflow

### Step 1: Single-Cue Translation
```python
def llm_translate_single(
    text: str,
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
`\`

- Uses structured prompt with contextual cues
- Preserves formatting with tag protection
- Returns translated content in `<translation>...</translation>` tags

### Step 2: Batch Translation
```python
def llm_translate_batch(
    pairs: List[Tuple[str, str]],
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
`\`

- Groups cues into batches of `batch_n` size
- Uses ID|||delimiter to maintain cue mapping
- Handles multi-line translations across cue blocks

### Step 3: Chunk Processing
```python
def translate_range(
    transcript: Transcript,
    chunks: List[Chunk],
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
`\`

- Processes each chunk sequentially
- Handles both single and batch translation modes
- Tracks chunk status and errors

## 4. Recovery Logic

### When Translation Fails
```python
except LLMError as exc:
    chunk.status = "error"
    chunk.err = str(exc)
    if logger:
        logger(f"Error processing chunk {chunk.cid}: {exc}")
    raise RuntimeError(f"Chunk {chunk.cid} failed: {exc}") from exc
`\`

- Sets chunk status to "error"
- Captures error message
- Logs error and propagates exception

### When Translation is Empty
```python
if not translated or not translated.strip() or translated.strip() == cue.text.strip():
    cue.translated = cue.text
    missing.append(pid)
`\`

- Falls back to original text
- Adds missing cue to error list
- Uses neighboring cues for context in retry

## 5. Contextual Prompt Assembly

### `_build_single_prompt`
```python
def _build_single_prompt(
    prompt: str,
    cue_text: str,
    context_before: str,
    context_after: str,
    previous_translation: str,
    next_translation: str,
) -> str:
`\`

- Constructs prompt with:
  - Source/target language instructions
  - Surrounding context (previous/next cues)
  - Previous/next translations
  - Force distinct output requirement

## 6. Tag & Bracket Handling

### `_protect_tags` and `_protect_brackets`
- Scans text for tags/brackets and replaces with placeholders
- Maintains mapping for restoration during final output
- Preserves original formatting while avoiding translation

## 7. Output Structure

After processing:
- All `Cue.translated` fields are populated
- Chunk `status` is updated to `done` or `error`
- Missing cues are logged and retained for retry

## Key Features
- Chunked processing to avoid memory/timeout issues
- Context-aware translation for better natural language output
- Error recovery with fallback to original text
- Flexible batch sizing
- Tag preservation for special content

## Limitations
- No native support for nested/complex formatting
- Translation quality depends on LLM model and prompt engineering

---
Generated on 2025-11-06