# Subsetzer Usage Guide

This document dives deeper into everyday workflows for both the CLI and GUI wrappers.

## CLI (`subsetzer`)

### Basic Invocation
```bash
subsetzer --in movie.vtt --out ./results --target "German"
```

- `--in` points to an `.srt`, `.vtt`, or `.tsv` file.
- `--out` is a directory; Subsetzer either writes directly there (`--flat`) or creates a timestamped job folder.
- `--target` selects the destination language (`--source` defaults to `auto`).

### Format Control
- Keep the input format with `--outfmt auto` (default), or force `srt`, `vtt`, or `tsv`.
- Use `--outfile` to customise file names. Placeholders: `{basename}`, `{src}`, `{dst}`, `{fmt}`, `{ts}`, `{model}`.

### Chunk Planning
- `--max-chars`: upper limit per chunk (default `4000`).
- `--cues-per-request`: number of cues sent per LLM call (default `SUBSETZER_CUES_PER_REQUEST` or `1`).
- Subsetzer automatically retries cues the bulk call could not translate or that come back identical to the input.

### Translation Options
- Disable bracketed translations (`[MUSIC]`, stage directions) with `--no-translate-bracketed`.
- Toggle streaming vs buffered responses via `--stream` / `--no-stream`.
- Use `--no-llm` to dry-run the pipeline and reuse source text.

### Environment Variables
All flags have environment counterparts:

| Variable | Meaning | Flag |
|----------|---------|------|
| `SUBSETZER_LLM_SERVER` | Ollama-compatible endpoint | `--server` |
| `SUBSETZER_LLM_MODEL` | Model identifier | `--model` |
| `SUBSETZER_LLM_MODE` | `auto`, `chat`, `generate` | `--llm-mode` |
| `SUBSETZER_STREAM` | `true` / `false` | `--stream` |
| `SUBSETZER_HTTP_TIMEOUT` | Seconds for HTTP timeout | `--timeout` |
| `SUBSETZER_CUES_PER_REQUEST` | Default batch size | `--cues-per-request` |

Legacy `HOMEDOC_*` names work too. Place the values in `.env` and `source` it before running.

### Examples
Translate using a remote host and force SRT output:

```bash
subsetzer \
  --in lectures/input.vtt \
  --out ./translations \
  --server http://lan-server:11434 \
  --model qwen3:14b \
  --target "English" \
  --outfmt srt \
  --cues-per-request 4 \
  --max-chars 6000
```

Create flat output with a custom template:

```bash
subsetzer \
  --in movie.srt \
  --out ./exports \
  --flat \
  --outfile "{basename}.{dst}.{model}.{fmt}" \
  --no-translate-bracketed
```

## GUI (`subsetzer-gui`)

### Launching
```bash
subsetzer-gui
```
or from the checkout:
```bash
PYTHONPATH=packages/subsetzer/src:packages/subsetzer-gui/src python -m subsetzer_gui.app
```

### Layout Overview
1. **Input/Output fields**: choose the subtitle file and target directory.
2. **Template & format**: the same placeholders available in the CLI.
3. **Server/model & chunk settings**: mirrors CLI flags; defaults can come from `.env`.
4. **Chunk list**: shows planned batches. Use *Build/Update chunks* before translating.
5. **Log console**: captures progress and any warnings/errors.
6. **CLI preview**: live command line equivalent for scripting reference.

![Subsetzer GUI](subsetzer-gui-1.png)

### Typical Workflow
1. Select the input subtitle file.
2. Choose or create an output directory.
3. Adjust language, server, and chunk settings if necessary.
4. Click **Build/Update chunks** to parse and plan the work.
5. Review the chunk list (optional).
6. Click **Translate ALL** or **Translate selected chunk**.
7. Monitor progress in the console; outputs land inside the chosen directory (timestamped unless *Flat output* is enabled).

### Abort & Retries
- **Abort** sets a flag checked between batches; the current LLM request must finish before the worker stops.
- Failed or identical translations will automatically fall back to per-cue retries using neighbouring context.

## Outputs
- **VTT** exports include a `NOTE translated-with model=<model> time=<iso8601>` header.
- Name collisions append `-N` suffixes automatically.
- A `llm_raw.txt` file is saved when streaming/debug logging is enabled for later inspection.

## Troubleshooting
- `HTTP error contacting LLM server`: verify the endpoint, model availability, and network access.
- `Tkinter is required…`: install the system Tk bindings (`sudo apt install python3-tk` on Debian/Ubuntu).
- Missing translations: increase `--max-chars` or reduce `--cues-per-request` to give the model more context.

For questions or ideas, open an issue or start a discussion on the GitHub repository.
