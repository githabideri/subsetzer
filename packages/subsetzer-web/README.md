# subsetzer-web

A FastAPI web/API server around the subsetzer translation engine.

Upload a subtitle file (SRT/VTT/TSV), pick a model, get a translated file
back. One command, one serial worker, LAN-friendly.

## Install

```bash
pipx install subsetzer-web
# or in a venv:
pip install subsetzer-web
```

## Run

```bash
export SUBSETZER_LLM_SERVER=http://127.0.0.1:8000/v1   # any OpenAI-compatible /v1 root
export SUBSETZER_LLM_MODEL=my-llm-model               # default model for the UI select
subsetzer-web --port 8787
```

Then open `http://<host>:8787` (or `--api-only` for a headless JSON API).

### Environment

| Variable | Purpose |
|---|---|
| `SUBSETZER_LLM_SERVER` | OpenAI-compatible `/v1` root (vLLM, llama.cpp, LM Studio, SGLang, Ollama) |
| `SUBSETZER_LLM_MODEL` | Default model (the UI select can override per request) |
| `SUBSETZER_LLM_API_KEY` | Optional Bearer token for the LLM server |
| `SUBSETZER_MAX_TOKENS` | Max completion tokens per request |
| `SUBSETZER_TEMPERATURE` | Sampling temperature |
| `SUBSETZER_EXTRA_BODY` | JSON object merged into every request body, e.g. `'{"chat_template_kwargs":{"enable_thinking":false}}'` for vLLM |
| `SUBSETZER_WEB_HOST` / `SUBSETZER_WEB_PORT` | Bind address (default `0.0.0.0:8787`) |
| `SUBSETZER_WEB_DATA` | Job storage directory (default `./subsetzer-web-data`) |
| `SUBSETZER_WEB_TOKEN` | Optional access token: when set, all routes except `/healthz` require `X-Subsetzer-Token` header or `?token=` |
| `SUBSETZER_WEB_API_ONLY` | `1` = headless JSON mode (same as `--api-only`) |

## API (also usable with curl)

```bash
# list models from the LLM server
curl http://localhost:8787/models

# start a translation job
curl -F "file=@episode.srt" -F "source=Serbian" -F "target=German" \
     -F "model=my-llm-model" -F "cues_per_request=4" \
     http://localhost:8787/translate
# -> {"job":"ab12cd34ef56","position":1}

# poll / stream progress
curl http://localhost:8787/jobs/ab12cd34ef56
curl -N http://localhost:8787/jobs/ab12cd34ef56/events   # SSE

# download the result, abort, list jobs
curl -OJ http://localhost:8787/jobs/ab12cd34ef56/download
curl -X POST http://localhost:8787/jobs/ab12cd34ef56/abort
curl http://localhost:8787/jobs
```

Jobs run serially (modest models do not like concurrency); a small queue
absorbs bursts. Inputs and outputs live under the data directory and are
pruned after 20 finished jobs.
