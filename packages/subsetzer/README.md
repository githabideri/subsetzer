# Subsetzer

Subsetzer is a stdlib-only subtitle translation toolkit that talks to an
Ollama-compatible LLM running on your LAN. Feed it `.srt`, `.vtt`, or `.tsv`
files, choose the target language, and it handles parsing, chunking, and
translation. The CLI stays faithful to the former `setzer` tool, but now ships
under a new name ready for PyPI.

## Features

- Translate SRT, VTT, and TSV subtitle files via Ollama-compatible APIs.
- Keep bracketed tags (like `[MUSIC]`) intact with `--no-translate-bracketed`.
- Chunk large transcripts with configurable `--max-chars` and `--cues-per-request`.
- Output SRT, VTT (with NOTE block including model + timestamp), or TSV files.
- Run with `pipx`, inside a virtual environment, or directly from source.

## Installation

```bash
pipx install subsetzer
# or
pip install subsetzer
```

Ensure you have an accessible Ollama server (default `http://127.0.0.1:11434`)
with a compatible model pulled (default `gemma3:12b`).

## CLI Usage

```bash
subsetzer --in input.srt --out ./out --target "German"
```

Useful flags (all mirrored from the previous CLI):

- `--outfmt {auto,srt,vtt,tsv}` to override the output format.
- `--outfile TEMPLATE` to customise the output path (placeholders: `{basename}`,
  `{dst}`, `{fmt}`, `{src}`, `{ts}`, `{model}`). The default template now adds
  the model slug so parallel runs stay separate.
- `--cues-per-request` / `--batch-per-chunk` to batch cues per LLM call.
- `--llm-mode {auto,chat,generate}` to force the Ollama API flavour.
- `--stream/--no-stream`, `--timeout`, `--no-llm`, `--debug` behave as before.

Run `subsetzer --help` for the full flag list.

## Environment Variables

Subsetzer understands both the new `SUBSETZER_*` variables and the legacy
`HOMEDOC_*` names. The new aliases take precedence when both are set.

| Variable | Description | Default |
| --- | --- | --- |
| `SUBSETZER_LLM_SERVER` / `HOMEDOC_LLM_SERVER` | Ollama server URL | `http://127.0.0.1:11434` |
| `SUBSETZER_LLM_MODEL` / `HOMEDOC_LLM_MODEL` | Model tag | `gemma3:12b` |
| `SUBSETZER_LLM_MODE` / `HOMEDOC_LLM_MODE` | `auto`, `chat`, or `generate` | `auto` |
| `SUBSETZER_STREAM` / `HOMEDOC_STREAM` | Enable streaming | `True` |
| `SUBSETZER_HTTP_TIMEOUT` / `HOMEDOC_HTTP_TIMEOUT` | Timeout in seconds | `60` |
| `SUBSETZER_CUES_PER_REQUEST` / `HOMEDOC_CUES_PER_REQUEST` | Batch size | `1` |
| `SUBSETZER_TZ` / `HOMEDOC_TZ` | Timezone for timestamped folders | local time |

## Development

Clone the repository and install in editable mode:

```bash
pip install -e packages/subsetzer
pytest packages/subsetzer/tests
```

Subsetzer ships with type hints (`py.typed`) and avoids third-party dependencies.

## License

GPL-3.0-or-later — see `LICENSE` for full details.
