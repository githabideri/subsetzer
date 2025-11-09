---
title: subsetzer CLI Workflow Analysis
date: 2025-11-06
tags:
  - python
  - cli
  - subtitle
  - translation
  - command-line
  - automation
alias:
  - CLI Workflow Guide
status: done
type: technical-documentation
author: Qwen3 4B Instruct (38k)

---

# subsetzer CLI Workflow Documentation

## Overview
The subsetzer CLI provides a user-friendly interface for translating subtitle files (SRT, VTT, TSV) using a local LLM via an Ollama-compatible server. This document details the step-by-step workflow of the CLI process.

## 1. Command-Line Interface (Parser)

The CLI uses `argparse` to define configurable options with defaults and validation:

| Option | Default | Description |
|--------|---------|-------------|
| `--in` | Required | Input subtitle file (.srt/.vtt/.tsv) |
| `--out` | Required | Output directory for generated files |
| `--source` | "auto" | Source language (auto-detected) |
| `--target` | "English" | Target language |
| `--server` | `http://127.0.0.1:11434` | LLM server URL |
| `--model` | `gemma3:12b` | LLM model tag |
| `--cues-per-request` | `1` | Number of cues per LLM request |
| `--max-chars` | `4000` | Max characters per chunk |
| `--no-translate-bracketed` | `True` | Preserves bracketed tags like [MUSIC] |
| `--llm-mode` | `auto` | LLM mode (chat/generate) |
| `--stream` | `True` | Enable streaming responses |
| `--timeout` | `60` | HTTP timeout in seconds |
| `--no-llm` | False | Skip LLM calls and reuse original text |
| `--debug` | False | Enable verbose logging |

All options support environment variables (e.g., `SUBSETZER_SERVER`).

## 2. Input/Output Handling

- **Path validation**: Paths are resolved using `Path.expanduser()` to support `~` shortcuts.
- **Directory structure**: 
  - `--flat`: Outputs written directly to `--out`
  - Default: Timestamped subfolder (e.g., `YYYYMMDD-HHMMSS/`) within `--out`.

## 3. Workflow Execution

### Step 1: Load Transcript
```python
transcript = read_transcript(str(input_path))
```

Parses input subtitle file into a `Transcript` object with cues, formatting, and metadata.

### Step 2: Chunk Content
```python
chunks = make_chunks(transcript.cues, args.max_chars)
```

Splits cues into manageable segments to avoid overwhelming the LLM.

### Step 3: Translate Using Engine
```python
translate_range(
    transcript,
    chunks,
    server=args.server,
    model=args.model,
    source=args.source,
    target=args.target,
    batch_n=args.cues_per_request,
    translate_bracketed=args.translate_bracketed,
    llm_mode=args.llm_mode,
    stream=args.stream,
    timeout=args.timeout,
    no_llm=args.no_llm,
    logger=logger.log,
    raw_handler=raw_handler if (args.debug or args.stream) else None,
    verbose=args.debug,
)
```

- Translates cues in chunks with configurable batch size
- Preserves bracketed content when `--no-translate-bracketed` is disabled
- Falls back to original text if `--no-llm` is used

### Step 4: Output Generation

- Uses `build_output_as()` to render output in desired format (SRT/VTT/TSV)
- Adds timestamp and model metadata to VTT files
- Applies template `{basename}.{dst}.{model}.{fmt}`

### Step 5: Write Final File
```python
_write_file(output_path, result)
```

Saves the translated content to disk with UTF-8 encoding.

## 4. Error Handling & Debugging

- All operations are wrapped in try-except blocks with user-readable error messages.
- `--debug` enables:
  - Verbose logging to `homedoc.log`
  - Capture raw LLM responses to `llm_raw.txt` when `--capture-raw` (or `--debug`) is set

## 5. Example Usage
```bash
subsetzer --in input.srt --out ./output --source ru --target en --model gemma3:12b --batch-per-chunk 5
```

This translates a Russian SRT file to English using the gemma3:12b model, with 5 cues per request and detailed debug logs.

## Key Features
- Configurable batch size and chunk limits
- Environment variable support
- Timestamped output directories
- Raw LLM response capture for debugging
- Fail-safe behavior with fallbacks
- Clean, readable output formatting

## Known Limitations
- Does not support direct file-overwrite or in-place edits
- Output formatting is limited to supported formats (SRT/VTT/TSV)

---
Generated on 2025-11-06
