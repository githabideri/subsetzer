"""Smoke tests for the subsetzer-web FastAPI app (no LLM server needed)."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from subsetzer_web.app import create_app  # noqa: E402

SRT = """1
00:00:21,890 --> 00:00:24,746
U svom dobu spavao je napolju u snegu.
"""


def _client(tmp_path: Path, **kwargs) -> TestClient:
    # __enter__ runs the app lifespan, which starts the job worker thread.
    tc = TestClient(create_app(data_dir=tmp_path, **kwargs))
    tc.__enter__()
    return tc


def test_healthz(tmp_path: Path) -> None:
    client = _client(tmp_path)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_index_page_and_api_only(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/")
    assert resp.status_code == 200
    assert "<!doctype html>" in resp.text

    resp = _client(tmp_path, api_only=True).get("/")
    assert resp.status_code == 200
    assert "endpoints" in resp.json()


def test_upload_validation(tmp_path: Path) -> None:
    client = _client(tmp_path)

    # garbage file
    resp = client.post(
        "/translate",
        files={"file": ("bad.srt", b"not a subtitle at all", "text/plain")},
        data={"source": "Serbian", "target": "German", "model": "x"},
    )
    assert resp.status_code == 400

    # no model
    resp = client.post(
        "/translate",
        files={"file": ("ok.srt", SRT.encode(), "text/plain")},
        data={"source": "auto", "target": "English", "model": ""},
    )
    assert resp.status_code == 400

    # empty file
    resp = client.post(
        "/translate",
        files={"file": ("empty.srt", b"", "text/plain")},
        data={"model": "x"},
    )
    assert resp.status_code == 400


def test_token_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SUBSETZER_WEB_TOKEN", "sekret")
    client = _client(tmp_path)
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers={"X-Subsetzer-Token": "sekret"}).status_code == 200
    assert client.get("/jobs", params={"token": "sekret"}).status_code == 200
    # healthz stays open
    assert client.get("/healthz").status_code == 200


def test_job_lifecycle_with_fake_llm(tmp_path: Path, monkeypatch) -> None:
    """Feed a stub LLM through the real worker: job goes queued -> done."""
    from subsetzer_web import app as app_module

    class StubBackend:
        stream = False

        def chat(self, model: str | None = None, messages=None, **kw: object) -> str:
            prompt = messages[-1]["content"]  # the cue block is the last user message
            lines = prompt.splitlines()
            # Batch mode: one line per "Cue N:" header, prefixed with XX.
            out = []
            for i, line in enumerate(lines):
                if re.match(r"^Cue \d+:$", line):
                    j = i + 1
                    block = []
                    while j < len(lines) and lines[j].strip():
                        block.append(lines[j])
                        j += 1
                    out.append("XX " + " / ".join(block))
            if out:
                return "\n".join(out)
            # Single mode: "CURRENT CUE:" section, answered in <translation> tags.
            if "CURRENT CUE:" in prompt:
                tail = prompt.split("CURRENT CUE:", 1)[1].strip().splitlines()
                return "<translation>XX " + " / ".join(tail) + "</translation>"
            return "XX " + prompt.strip()

    monkeypatch.setattr(app_module, "OpenAICompat", lambda *a, **k: StubBackend())

    client = _client(tmp_path)
    resp = client.post(
        "/translate",
        files={"file": ("movie.srt", SRT.encode(), "text/plain")},
        data={"source": "Serbian", "target": "German", "model": "stub", "cues_per_request": "1"},
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job"]

    # wait for the worker (poll the API, as a client would)
    final = None
    for _ in range(50):
        time.sleep(0.1)
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] in {"done", "error", "aborted"}:
            final = status
            break
    assert final is not None, "job did not finish"
    assert final["status"] == "done", final
    assert final["done"] == 1

    download = client.get(f"/jobs/{job_id}/download")
    assert download.status_code == 200
    body = download.text
    assert "XX U svom dobu" in body
    assert "00:00:21,890 --> 00:00:24,746" in body
    assert "sr" in download.headers.get("content-disposition", "")


def test_models_proxy_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SUBSETZER_LLM_SERVER", "http://127.0.0.1:1/v1")  # nothing listens
    client = _client(tmp_path)
    resp = client.get("/models")
    assert resp.status_code == 502
