# Changelog

All notable changes to this project will be documented in this file. The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions adhere to semantic versioning.

# [Unreleased]
### Fixed
- Guard GUI cues-per-request / max-char inputs so clearing the entry doesn’t throw `_tkinter.TclError` when updating the CLI preview (see [issue #2](https://github.com/githabideri/subsetzer/issues/2); commit 8e4cceb). Shipping with 0.1.5.

## [0.2.0] - 2026-10-05
### Added
- Structured batch contract: at session start the engine probes the server and uses the strongest response format it *verifiably* honors — `response_format: json_schema` (JSON array of exactly N strings), then `json_object`, then the classic `ID|||` sentinel protocol. The probe validates the *shape of the answer*, because some servers (notably llama.cpp) silently ignore `json_schema` and return free text.
- vLLM `repetition_detection` n-gram loop backstop: degenerate generation is terminated by the server with a typed `finish_reason: "repetition"` instead of burning the full `max_tokens` budget (the old `Qo'pu'` ×400 failure mode). Closed policy per batch: degenerate → one re-sampled retry (`seed`) → flagged cues keep their source text; malformed → per-cue single-cue fallback. Servers without the extension simply ignore the field; sentinel servers are untouched.
- `subsetzer-web`: multi-server registry (`SUBSETZER_LLM_SERVERS`, a JSON list of `{name, url, api_key?}` mirroring the llm-hub config); `/models` unions every registered server's live `/v1/models` list (grouped by server in the UI, unreachable servers reported); jobs route automatically to the server that serves the selected model. Single-server setups via `SUBSETZER_LLM_SERVER` behave exactly as before.
- `subsetzer-web`: new FastAPI package — upload SRT/VTT/TSV, serial job queue, SSE progress, download, abort; env-driven LLM config, optional access token, `--api-only` mode, embedded web UI.
- `backends.py`: OpenAI-compatible `/v1` client covering vLLM, llama.cpp, LM Studio, SGLang, and Ollama; `--extra-body` passthrough for server-specific knobs (e.g. vLLM `chat_template_kwargs`).
- `--no-punc` (punctuation-free translation, for dubbing scripts) and `--one-line` (fold multi-line cues) post-processing options in CLI, GUI, and web.
- `langs.py`: language-name normalisation (display names, ISO codes, common aliases).
- CLI: `--api-key`, `--max-tokens`, `--temperature`, `--extra-body`.

### Changed
- Engine is backend-driven; the `--server` flag now takes the `/v1` root (Ollama users: `http://127.0.0.1:11434/v1`). `--llm-mode` is gone (the fork’s generate/chat split no longer applies).
- VTT output timestamps now use `.` instead of `,` (spec-compliant, player-friendly).
- GUI: OpenAI-compatible server field, new option checkboxes, CLI preview follows the new flags.

## [0.1.4] - 2025-11-09
### Added
- Investigation documentation capturing VTT/TSV/CSV/data-loss issues plus real-world Ollama test results.
- Opt-in `--capture-raw` flag and CLI tests covering raw payload capture, VTT directives, TSV metadata, CSV parsing, and batch preambles.
- README/USAGE guidance about model behavior (gemma3:12b vs gemma3:4b) to set expectations.

### Fixed
- Preserve VTT cue directives, TSV metadata/delimiters, and CSV parsing fidelity; warn when models echo source text.
- Harden `llm_translate_batch` against preamble chatter and keep chunk planning aware of directive lengths.

## [0.1.3] - 2025-11-05
### Added
- Enforce `<translation>` sentinel tags for LLM fallback responses, ensuring CLI and GUI discard any prompt scaffolding or chatter.

### Fixed
- Cleaned multi-line cue handling for fallback translations without regex-based heuristics.

## [0.1.2] - 2025-11-04
### Added
- Initial packaging split into `subsetzer` (CLI) and `subsetzer-gui` (Tk GUI) with Ollama-compatible translation engine.
- PyPI release automation and documentation updates.
