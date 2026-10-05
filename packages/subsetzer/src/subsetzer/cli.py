"""CLI entry point for subsetzer."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .backends import OpenAICompat
from .chunking import make_chunks
from .engine import translate_range
from .io import build_output_as, read_transcript, resolve_outfile
from .langs import normalise_lang
from .logging_utils import Logger
from .version import __version__

DEFAULT_OUTFILE_TEMPLATE = "{basename}.{dst}.{model}.{fmt}"


def _env_value(name: str, default: str) -> str:
    return os.getenv(f"SUBSETZER_{name}", default)


def _env_bool(name: str, default: bool) -> bool:
    raw = _env_value(name, "1" if default else "0")
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    raw = _env_value(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: Optional[float] = None) -> Optional[float]:
    raw = os.getenv(f"SUBSETZER_{name}", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return default


def _env_json(name: str) -> Optional[Dict[str, object]]:
    raw = os.getenv(f"SUBSETZER_{name}", "")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _build_parser() -> argparse.ArgumentParser:
    server_default = _env_value("LLM_SERVER", "http://127.0.0.1:11434/v1")
    model_default = _env_value("LLM_MODEL", "gemma3:12b")
    stream_default = _env_bool("STREAM", True)
    timeout_default = float(_env_value("HTTP_TIMEOUT", "60"))
    cues_default = _env_int("CUES_PER_REQUEST", 1)
    max_tokens_default = _env_int("MAX_TOKENS", 0) or None
    temperature_default = _env_float("TEMPERATURE")

    parser = argparse.ArgumentParser(
        description=(
            "Translate subtitle files with any OpenAI-compatible LLM server "
            "(vLLM, llama.cpp, LM Studio, SGLang, Ollama /v1)."
        ),
    )
    parser.add_argument("--in", dest="input_path", required=True, help="Input subtitle file (.srt/.vtt/.tsv)")
    parser.add_argument("--out", dest="output_dir", required=True, help="Output directory for generated files")
    parser.add_argument(
        "--flat",
        action="store_true",
        default=False,
        help="Write outputs directly into --out (default: %(default)s)",
    )
    parser.add_argument(
        "--no-flat",
        dest="flat",
        action="store_false",
        help="Write into timestamped folder within --out (default)",
    )
    parser.add_argument(
        "--source",
        default="auto",
        help="Source language: ISO code (de, zh-cn), English name (German), or 'auto' (default: %(default)s)",
    )
    parser.add_argument(
        "--target",
        default="English",
        help="Target language: ISO code (de, zh-cn) or English name (default: %(default)s)",
    )
    parser.add_argument(
        "--outfmt",
        choices=["auto", "srt", "vtt", "tsv"],
        default="auto",
        help="Output format (default: %(default)s matches input)",
    )
    parser.add_argument(
        "--outfile",
        help=(
            "Output file template. Supports placeholders {basename}, {src}, {dst}, {fmt}, {ts}, {model}."
        ),
    )
    parser.add_argument(
        "--cues-per-request",
        "--batch-per-chunk",
        dest="cues_per_request",
        type=int,
        default=cues_default,
        help="Number of subtitle cues to send per LLM request (default: %(default)s)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Maximum characters per chunk when planning (default: %(default)s)",
    )
    parser.add_argument(
        "--no-translate-bracketed",
        dest="translate_bracketed",
        action="store_false",
        default=True,
        help="Preserve bracketed tags like [MUSIC] without translation",
    )
    parser.add_argument(
        "--no-punc",
        action="store_true",
        default=_env_bool("NO_PUNC", False),
        help="Strip punctuation from translated cues (keeps dashes); useful for CJK display",
    )
    parser.add_argument(
        "--one-line",
        action="store_true",
        default=_env_bool("ONE_LINE", False),
        help="Fold multi-line translated cues into a single line",
    )
    parser.add_argument(
        "--server",
        default=server_default,
        help=(
            "OpenAI-compatible base URL, i.e. the /v1 root "
            f"(vLLM/llama.cpp: http://host:8080/v1, Ollama: http://host:11434/v1). "
            f"Default: {server_default}"
        ),
    )
    parser.add_argument(
        "--model",
        default=model_default,
        help=f"LLM model name as served by the server (default: {model_default})",
    )
    parser.add_argument(
        "--api-key",
        default=_env_value("LLM_API_KEY", ""),
        help="Optional API key sent as a Bearer token (default: SUBSETZER_LLM_API_KEY)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=max_tokens_default,
        help="Max completion tokens per request (default: unset)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=temperature_default,
        help="Sampling temperature (default: unset)",
    )
    parser.add_argument(
        "--extra-body",
        help=(
            "JSON object merged verbatim into each request body, "
            'e.g. \'{"chat_template_kwargs": {"enable_thinking": false}}\' for vLLM'
        ),
    )
    stream_group = parser.add_mutually_exclusive_group()
    stream_group.add_argument(
        "--stream",
        dest="stream",
        action="store_true",
        default=stream_default,
        help="Enable streaming responses",
    )
    stream_group.add_argument(
        "--no-stream",
        dest="stream",
        action="store_false",
        help="Disable streaming responses",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=timeout_default,
        help=f"HTTP timeout in seconds (default: {timeout_default})",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM calls and reuse original text",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose logging and capture raw LLM responses",
    )
    parser.add_argument(
        "--capture-raw",
        action="store_true",
        help="Persist raw LLM payloads to llm_raw.txt (default: disabled)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _resolve_output_directory(base: Path, flat: bool) -> Path:
    if flat:
        base.mkdir(parents=True, exist_ok=True)
        return base
    tz_name = os.getenv("SUBSETZER_TZ")
    now = dt.datetime.now()
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name)
            now = dt.datetime.now(tz)
        except Exception:
            pass
    folder_name = now.strftime("%Y%m%d-%H%M%S")
    target = base / folder_name
    target.mkdir(parents=True, exist_ok=True)
    return target


def _write_file(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Unable to write {path.name}: {exc}") from exc


def _language_token(label: str, fallback: str) -> str:
    cleaned = re.sub(r"[\s]+", "_", label.strip())
    cleaned = re.sub(r"[^0-9A-Za-z._-]", "-", cleaned)
    cleaned = re.sub(r"[-_]{2,}", "_", cleaned)
    result = cleaned.strip("_-.")
    return result.lower() or fallback


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input_path).expanduser()
    output_dir = Path(args.output_dir).expanduser()

    src_code = normalise_lang(args.source or "auto")
    dst_code = normalise_lang(args.target or "auto")

    extra_body: Optional[Dict[str, object]] = _env_json("EXTRA_BODY")
    if args.extra_body:
        try:
            parsed = json.loads(args.extra_body)
            if not isinstance(parsed, dict):
                raise ValueError("--extra-body must be a JSON object")
            extra_body = parsed
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"Error: invalid --extra-body: {exc}", file=sys.stderr)
            return 1

    try:
        backend = OpenAICompat(
            args.server,
            api_key=args.api_key or None,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            extra_body=extra_body,
            stream=args.stream,
            timeout=args.timeout,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        transcript = read_transcript(str(input_path))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        chunks = make_chunks(transcript.cues, args.max_chars)
    except Exception as exc:
        print(f"Error preparing chunks: {exc}", file=sys.stderr)
        return 1

    target_dir = _resolve_output_directory(output_dir, args.flat)
    log_path = target_dir / "subsetzer.log"
    logger = Logger(file_path=log_path, verbose=args.debug)
    raw_lines: List[str] = []
    collect_raw = bool(args.capture_raw or args.debug)

    logger.log(f"Loaded transcript with {len(transcript.cues)} cues in {transcript.fmt.upper()} format")
    logger.log(f"Planned {len(chunks)} chunk(s) with max {args.max_chars} characters")
    logger.log(
        f"Translate {src_code} -> {dst_code} via {args.server} model={args.model}"
    )

    def raw_handler(payload: str) -> None:
        if collect_raw:
            raw_lines.append(payload)

    try:
        translate_range(
            transcript,
            chunks,
            backend=backend,
            model=args.model,
            source=args.source,
            target=args.target,
            batch_n=args.cues_per_request,
            translate_bracketed=args.translate_bracketed,
            no_llm=args.no_llm,
            one_line=args.one_line,
            no_punc=args.no_punc,
            logger=logger.log,
            raw_handler=raw_handler if collect_raw else None,
            verbose=args.debug,
        )
    except Exception as exc:
        logger.log(f"Translation failed: {exc}")
        logger.close()
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    timestamp = dt.datetime.now(dt.timezone.utc).astimezone()
    vtt_note = f"translated-with model={args.model} time={timestamp.isoformat()}"
    target_fmt = args.outfmt if args.outfmt != "auto" else transcript.fmt
    try:
        result = build_output_as(
            transcript,
            target_fmt,
            vtt_note=vtt_note if target_fmt == "vtt" else None,
        )
    except Exception as exc:
        logger.log(f"Failed to render output: {exc}")
        logger.close()
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    outfile_template = args.outfile if args.outfile else DEFAULT_OUTFILE_TEMPLATE
    template_path: str
    if outfile_template.startswith("~") or Path(outfile_template).is_absolute():
        template_path = outfile_template
    else:
        template_path = str(target_dir / outfile_template)

    try:
        output_path = resolve_outfile(
            template_path,
            input_path,
            _language_token(src_code, "auto"),
            _language_token(dst_code, "unknown"),
            target_fmt,
            model=args.model,
        )
    except Exception as exc:
        logger.log(f"Failed to resolve output path: {exc}")
        logger.close()
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        _write_file(output_path, result)
    except Exception as exc:
        logger.log(str(exc))
        logger.close()
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    logger.log(f"Wrote {target_fmt.upper()} output to {output_path}")

    if collect_raw:
        raw_path = target_dir / "llm_raw.txt"
        try:
            raw_path.write_text("\n".join(raw_lines), encoding="utf-8")
            logger.log(f"Captured raw LLM payloads in {raw_path}")
        except OSError:
            logger.log("Unable to write llm_raw.txt")

    logger.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
