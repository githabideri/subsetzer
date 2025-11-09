# 2025-11-09 – Investigation: Subtitle data integrity & logging

## Context
- Repo: `subsetzer` at `main` (`ff15490`).
- Environment: Python 3.11, no network/LLM access unless noted.
- Goal: reproduce previously reported issues (VTT directives dropped, TSV metadata loss, `.csv` parsing mismatch, batch preamble fragility, raw payload logging) and capture concrete evidence before proposing fixes.

## Findings

### 1. VTT cue directives are discarded
**Expectation:** cue settings such as `line`, `position`, or `align` should persist when reading then writing a file.  
**Observation:** `split_times` truncates the timing line at the first whitespace after `-->`, so formatting directives vanish on write.

#### Repro
```bash
cat > /tmp/sample.vtt <<'EOF'
WEBVTT

00:00:01.000 --> 00:00:04.000 line:0% position:50% align:start
Hello world
EOF

python - <<'PY'
from subsetzer.io import read_transcript, build_output_as
tx = read_transcript("/tmp/sample.vtt")
print(build_output_as(tx, "vtt"))
PY
```

**Result:** output cue header becomes `00:00:01.000 --> 00:00:04.000` with no directives, confirming loss of author-intended positioning.

### 2. TSV round-trips wipe columns beyond start/end/text
**Expectation:** when a TSV has extra columns (speaker, cue id, etc.) they should survive serialization.  
**Observation:** `write_tsv` rebuilds each row with only three populated fields, so every additional column is blanked.

#### Repro
```bash
cat > /tmp/sample.tsv <<'EOF'
start	end	text	speaker
0	1	Hello	Alice
1	2	World	Bob
EOF

python - <<'PY'
from subsetzer.formats import parse_tsv, write_tsv
tx = parse_tsv(open("/tmp/sample.tsv").read())
print(write_tsv(tx))
PY
```

**Result:** rendered TSV contains empty `speaker` cells even though the header still lists the column, proving metadata loss.

### 3. `.csv` extension misdetected as TSV but parsed with tab delimiter
**Expectation:** a `.csv` file should either parse with commas or refuse detection.  
**Observation:** `detect_format` treats `.csv` as `tsv`, yet `parse_tsv` uses `delimiter="\t"`, so comma-separated values never split. All cue fields get populated with the entire row string, corrupting timestamps/text.

#### Repro
```bash
cat > /tmp/sample.csv <<'EOF'
start,end,text
0,1,Hello
1,2,World
EOF

python - <<'PY'
from subsetzer.io import read_transcript
tx = read_transcript("/tmp/sample.csv")
print(tx.fmt, tx.cues[0])
PY
```

**Result:** format is reported as TSV but `Cue.start/end/text` all contain the string `"0,1,Hello"`, demonstrating that commas were never split apart and the transcript contents became unusable.

### 4. Batch translation is brittle when LLM prepends text
**Expectation:** bulk translations should tolerate harmless preambles like “Sure:” before the first `ID|||` block.  
**Observation:** parser assumes the very first line already starts with `ID|||`. Any preamble hides the first cue, forcing single-cue retries (extra cost + latency).

#### Repro (simulated LLM)
```bash
python - <<'PY'
from unittest import mock
from subsetzer.engine import llm_translate_batch

response = "Sure, here you go: 1|||Hola\n2|||Mundo"
with mock.patch("subsetzer.engine._perform_llm_call", return_value=response):
    pairs = [("1", "Hello"), ("2", "World")]
    result = llm_translate_batch(
        pairs,
        source="en",
        target="es",
        model="demo",
        server="http://localhost",
        llm_mode="auto",
        stream=False,
        timeout=30,
        translate_bracketed=True,
        raw_handler=None,
    )
print(result)
PY
```

**Result:** tuple for cue 1 is `("1", "Hello")`—the untranslated source—because the parser captured `pid="Sure, here you go: 1"` and couldn’t match it back to cue `1`, forcing the retry path.

### 5. Raw LLM payload logging happens even without opting in
**Expectation:** sensitive inputs should only be written to disk when explicitly requested.  
**Observation:** CLI writes `llm_raw.txt` whenever `--stream` is true (default) even in `--no-llm` dry runs.

#### Repro
```bash
python - <<'PY'
from pathlib import Path
import tempfile, textwrap
from subsetzer.cli import main

tmp = Path(tempfile.mkdtemp())
infile = tmp / "input.srt"
infile.write_text(textwrap.dedent("""\
1
00:00:00,000 --> 00:00:01,000
Hello
"""))

outdir = tmp / "out"
main(["--in", str(infile), "--out", str(outdir), "--no-llm"])

job_dir = next(outdir.iterdir())
print(sorted(p.name for p in job_dir.iterdir()))
PY
```

**Result:** output directory contains both the translated SRT _and_ `llm_raw.txt` even though no network request occurred; by default every run leaves a payload file on disk.

## Next steps
1. Confirm whether each issue warrants automated regression tests.
2. Draft fixes (e.g., preserve VTT settings, respect TSV headers, stop auto-logging raw payloads) referencing this document.
3. Use a follow-up ADR/PR to propose and implement the remediation plan.
- Planned follow-up: add an opt-in `--capture-prompts` feature (see GitHub issue #1) to persist per-cue prompt/response transcripts for deeper debugging.

## Verification (after fixes)
- `source .venv/bin/activate && PYTHONPATH=packages/subsetzer/src python -m pytest packages/subsetzer/tests`
- `source .venv/bin/activate && PYTHONPATH=packages/subsetzer/src:packages/subsetzer-gui/src python -m pytest packages/subsetzer-gui/tests`
- End-to-end translations:
  - `SUBSETZER_LLM_MODEL=gemma3:12b PYTHONPATH=packages/subsetzer/src python -m subsetzer.cli --in outputs/attwenger.vtt --out results/ollama-tests/gemma12b --target "Croatian" --max-chars 2000 --cues-per-request 4 --flat --outfile "attwenger.{dst}.{model}.{fmt}" --capture-raw`
  - `SUBSETZER_LLM_MODEL=gemma3:4b PYTHONPATH=packages/subsetzer/src python -m subsetzer.cli --in outputs/attwenger.vtt --out results/ollama-tests/gemma4b --target "Croatian" --max-chars 2000 --cues-per-request 4 --flat --outfile "attwenger.{dst}.{model}.{fmt}" --capture-raw`
