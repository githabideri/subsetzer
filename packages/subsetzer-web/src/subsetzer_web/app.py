"""subsetzer-web — FastAPI server for subsetzer.

One command:

    subsetzer-web [--host 0.0.0.0] [--port 8787] [--api-only]

Uploads (SRT/VTT/TSV) are translated serially by a single worker thread
against any OpenAI-compatible LLM server. The default target is
configurable through the usual SUBSETZER_* environment variables
(``SUBSETZER_LLM_SERVER`` must be the ``/v1`` root).
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import uvicorn
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import HTMLResponse, StreamingResponse
from urllib.error import HTTPError, URLError
from urllib.request import Request as _UrlRequest
from urllib.request import urlopen

from subsetzer import (
    LLMError,
    OpenAICompat,
    TranscriptError,
    build_output_as,
    make_chunks,
    normalise_lang,
    read_transcript,
    translate_range,
)

__all__ = ["create_app", "main"]

__version__ = "0.2.0"

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_QUEUED_JOBS = 5
KEEP_JOBS = 20


class AbortRequested(Exception):
    """Raised inside the worker when the client asks to stop a job."""


@dataclass
class Job:
    id: str
    name: str
    status: str = "queued"  # queued | running | done | error | aborted
    done: int = 0
    total: int = 0
    error: str = ""
    out_file: str = ""
    model: str = ""
    source: str = ""
    target: str = ""
    cues_per_request: int = 1
    max_chars: int = 4000
    no_punc: bool = False
    one_line: bool = False
    created: float = field(default_factory=time.time)

    def to_dict(self, with_paths: bool = False) -> Dict[str, object]:
        d: Dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "done": self.done,
            "total": self.total,
            "model": self.model,
            "source": self.source,
            "target": self.target,
            "error": self.error,
        }
        if self.status == "done":
            d["download"] = f"/jobs/{self.id}/download"
        if with_paths:
            d["out_file"] = self.out_file
        return d


class ServerState:
    def __init__(self, data_dir: Path, api_only: bool) -> None:
        self.data_dir = data_dir
        self.api_only = api_only
        self.jobs: Dict[str, Job] = {}
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.abort: Dict[str, threading.Event] = {}
        self.worker: Optional[threading.Thread] = None

    # -- worker ---------------------------------------------------------

    def _prune(self) -> None:
        with self.lock:
            for job in sorted(self.jobs.values(), key=lambda j: j.created):
                if len(self.jobs) > KEEP_JOBS and job.status in {"done", "error", "aborted"}:
                    self.jobs.pop(job.id, None)
                    shutil.rmtree(self.data_dir / f"jobs-{job.id}", ignore_errors=True)

    def _worker(self) -> None:
        while not self.stop.is_set():
            try:
                job_id = self.queue.get(timeout=1.0)
            except queue.Empty:
                continue
            job = self.jobs.get(job_id)
            if job is None:
                continue
            if job.status == "aborted":
                continue
            self._run_job(job)
            self._prune()

    def _run_job(self, job: Job) -> None:
        job_dir = self.data_dir / f"jobs-{job.id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        input_path = job_dir / "input"
        try:
            transcript = read_transcript(str(input_path))
            chunks = make_chunks(transcript.cues, job.max_chars)
            job.total = len(transcript.cues)

            server = os.getenv("SUBSETZER_LLM_SERVER", "http://127.0.0.1:11434/v1")
            extra_body: Optional[Dict[str, object]] = None
            raw_extra = os.getenv("SUBSETZER_EXTRA_BODY", "")
            if raw_extra:
                parsed = json.loads(raw_extra)
                if isinstance(parsed, dict):
                    extra_body = parsed

            max_tokens_raw = os.getenv("SUBSETZER_MAX_TOKENS", "")
            temperature_raw = os.getenv("SUBSETZER_TEMPERATURE", "")
            backend = OpenAICompat(
                server,
                api_key=os.getenv("SUBSETZER_LLM_API_KEY") or None,
                max_tokens=int(max_tokens_raw) if max_tokens_raw else None,
                temperature=float(temperature_raw) if temperature_raw else None,
                extra_body=extra_body,
                stream=True,
                timeout=300.0,
            )

            abort_event = self.abort.get(job.id)

            def raw_handler(line: str) -> None:
                if abort_event is not None and abort_event.is_set():
                    raise AbortRequested()

            def progress(done: int, total: int) -> None:
                job.done = done
                job.total = total

            job.status = "running"
            translate_range(
                transcript,
                chunks,
                backend=backend,
                model=job.model,
                source=job.source,
                target=job.target,
                batch_n=job.cues_per_request,
                no_punc=job.no_punc,
                one_line=job.one_line,
                raw_handler=raw_handler,
                progress=progress,
            )

            result = build_output_as(transcript, transcript.fmt)
            out_path = job_dir / f"translated.{transcript.fmt}"
            out_path.write_text(result, encoding="utf-8")
            job.out_file = str(out_path)
            job.status = "done"
            job.done = job.total
        except AbortRequested:
            job.status = "aborted"
        except Exception as exc:  # noqa: BLE001 - report anything to the client
            job.status = "error"
            job.error = f"{type(exc).__name__}: {exc}"

    # -- helpers --------------------------------------------------------

    def new_job(self, job: Job) -> int:
        with self.lock:
            pending = sum(1 for j in self.jobs.values() if j.status in {"queued", "running"})
            if pending >= MAX_QUEUED_JOBS:
                raise HTTPException(status_code=503, detail="Server is busy; try again shortly.")
            self.jobs[job.id] = job
            self.abort[job.id] = threading.Event()
            self.queue.put(job.id)
            return pending


def _check_token(request: Request) -> None:
    expected = os.getenv("SUBSETZER_WEB_TOKEN", "")
    if not expected:
        return
    got = request.headers.get("x-subsetzer-token") or request.query_params.get("token", "")
    if got != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing token (SUBSETZER_WEB_TOKEN).")


def create_app(api_only: bool = False, data_dir: Optional[Path] = None) -> FastAPI:
    data_dir = data_dir or Path(os.getenv("SUBSETZER_WEB_DATA", "./subsetzer-web-data"))
    state = ServerState(data_dir=data_dir, api_only=api_only)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        data_dir.mkdir(parents=True, exist_ok=True)
        state.worker = threading.Thread(target=state._worker, daemon=True)
        state.worker.start()
        yield
        state.stop.set()

    app = FastAPI(title="subsetzer-web", version=__version__, lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> Dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/", dependencies=[Depends(_check_token)])
    def index() -> Response:
        if api_only:
            return JSONResponse(
                {
                    "name": "subsetzer-web",
                    "version": __version__,
                    "endpoints": [
                        "POST /translate",
                        "GET /jobs",
                        "GET /jobs/{id}",
                        "GET /jobs/{id}/events",
                        "GET /jobs/{id}/download",
                        "POST /jobs/{id}/abort",
                        "GET /models",
                    ],
                }
            )
        from .page import PAGE

        return HTMLResponse(PAGE)

    @app.get("/models", dependencies=[Depends(_check_token)])
    def models() -> Dict[str, object]:
        server = os.getenv("SUBSETZER_LLM_SERVER", "http://127.0.0.1:11434/v1")
        url = server.rstrip("/") + "/models"
        req = _UrlRequest(url)
        if os.getenv("SUBSETZER_LLM_API_KEY"):
            req.add_header("Authorization", f"Bearer {os.getenv('SUBSETZER_LLM_API_KEY')}")
        try:
            with urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=502, detail=f"Cannot reach LLM server at {url}: {exc}")
        data = payload.get("data") if isinstance(payload, dict) else None
        ids = [m.get("id", "") for m in data if isinstance(m, dict)] if isinstance(data, list) else []
        return {"data": [{"id": i} for i in ids], "server": server}

    @app.post("/translate", dependencies=[Depends(_check_token)])
    async def translate(
        file: UploadFile = File(...),
        source: str = Form("auto"),
        target: str = Form("English"),
        model: str = Form(""),
        cues_per_request: int = Form(1),
        max_chars: int = Form(4000),
        no_punc: bool = Form(False),
        one_line: bool = Form(False),
    ) -> Dict[str, object]:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 20 MB).")
        if not content.strip():
            raise HTTPException(status_code=400, detail="File is empty.")

        model = model or os.getenv("SUBSETZER_LLM_MODEL", "")
        if not model:
            raise HTTPException(status_code=400, detail="No model given and SUBSETZER_LLM_MODEL not set.")

        job = Job(
            id=uuid.uuid4().hex[:12],
            name=file.filename or "input.srt",
            model=model,
            source=source,
            target=target,
            cues_per_request=max(1, min(int(cues_per_request), 15)),
            max_chars=max(500, min(int(max_chars), 20000)),
            no_punc=bool(no_punc),
            one_line=bool(one_line),
        )
        job_dir = data_dir / f"jobs-{job.id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "input").write_bytes(content)
        try:
            read_transcript(str(job_dir / "input"))
        except TranscriptError as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"Cannot parse subtitle file: {exc}")

        try:
            position = state.new_job(job)
        except HTTPException:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise
        return {"job": job.id, "position": position + 1}

    @app.get("/jobs", dependencies=[Depends(_check_token)])
    def jobs() -> List[Dict[str, object]]:
        ordered = sorted(state.jobs.values(), key=lambda j: j.created, reverse=True)
        return [j.to_dict() for j in ordered[:20]]

    @app.get("/jobs/{job_id}", dependencies=[Depends(_check_token)])
    def job_status(job_id: str) -> Dict[str, object]:
        job = state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job.")
        return job.to_dict()

    @app.get("/jobs/{job_id}/events", dependencies=[Depends(_check_token)])
    def job_events(job_id: str) -> StreamingResponse:
        job = state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job.")

        def stream() -> Iterator[str]:
            while True:
                payload = job.to_dict()
                yield f"data: {json.dumps(payload)}\n\n"
                if job.status in {"done", "error", "aborted"}:
                    break
                time.sleep(0.4)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/jobs/{job_id}/download", dependencies=[Depends(_check_token)])
    def job_download(job_id: str) -> FileResponse:
        job = state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job.")
        if job.status != "done" or not job.out_file or not os.path.exists(job.out_file):
            raise HTTPException(status_code=409, detail="Job has no downloadable output yet.")
        fmt = os.path.splitext(job.out_file)[1].lstrip(".") or "srt"
        stem = os.path.splitext(job.name)[0]
        src_tok = "".join(c for c in normalise_lang(job.source).lower() if c.isalnum() or c in "-_") or "auto"
        dst_tok = "".join(c for c in normalise_lang(job.target).lower() if c.isalnum() or c in "-_") or "out"
        return FileResponse(
            job.out_file,
            media_type="application/octet-stream",
            filename=f"{stem}.{src_tok}.{dst_tok}.{fmt}",
        )

    @app.post("/jobs/{job_id}/abort", dependencies=[Depends(_check_token)])
    def job_abort(job_id: str) -> Dict[str, object]:
        job = state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job.")
        if job.status in {"done", "error", "aborted"}:
            return job.to_dict()
        state.abort.get(job_id, threading.Event()).set()
        job.status = "aborted"
        return job.to_dict()

    return app


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the subsetzer web/API server.")
    parser.add_argument("--host", default=os.getenv("SUBSETZER_WEB_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("SUBSETZER_WEB_PORT", "8787")))
    parser.add_argument(
        "--api-only",
        action="store_true",
        default=os.getenv("SUBSETZER_WEB_API_ONLY", "0") == "1",
        help="Serve the JSON API only (no web page)",
    )
    parser.add_argument(
        "--data-dir",
        default=os.getenv("SUBSETZER_WEB_DATA", "./subsetzer-web-data"),
        help="Directory for job inputs/outputs (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    app = create_app(api_only=args.api_only, data_dir=Path(args.data_dir))
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
