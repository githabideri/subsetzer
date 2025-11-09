# Changelog

All notable changes to this project will be documented in this file. The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions adhere to semantic versioning.

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
