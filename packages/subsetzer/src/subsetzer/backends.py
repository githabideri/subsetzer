"""LLM backends for subsetzer.

The default backend, :class:`OpenAICompat`, speaks the OpenAI-compatible
``/v1/chat/completions`` API. That covers:

- vLLM:             ``http://host:8080/v1``
- llama.cpp (``llama-server``): ``http://host:8080/v1``
- LM Studio:        ``http://localhost:1234/v1``
- SGLang:           ``http://host:8000/v1``
- Ollama:           ``http://host:11434/v1``

Pass the ``/v1`` root as ``base_url``; the client appends
``/chat/completions`` itself.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Protocol

from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

__all__ = [
    "LLMError",
    "LLMBackend",
    "OpenAICompat",
    "parse_string_array",
]


def parse_string_array(content: Optional[str], *, n: int) -> Optional[List[str]]:
    return _parse_string_array(content, n=n)


class LLMError(RuntimeError):
    """Raised when the LLM could not be contacted or returned malformed data."""


class LLMBackend(Protocol):
    """Anything that can run a chat completion.

    Implementations must return the assistant text as a string (or ``""``
    when the server produced nothing usable).
    """

    def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        stream: Optional[bool] = None,
        timeout: Optional[float] = None,
        raw_handler: Optional[Callable[[str], None]] = None,
    ) -> str: ...


class OpenAICompat:
    """Client for OpenAI-compatible ``/v1/chat/completions`` endpoints.

    Uses only the standard library. ``max_tokens``, ``temperature`` and
    ``extra_body`` are optional knobs; anything in ``extra_body`` is merged
    verbatim into the JSON body (e.g. vLLM's
    ``{"chat_template_kwargs": {"enable_thinking": false}}``).
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        stream: bool = True,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        if not self.base_url:
            raise ValueError("base_url must be a non-empty OpenAI-compatible /v1 root")
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.extra_body: Dict[str, Any] = dict(extra_body or {})
        self.stream = stream
        self.timeout = timeout

    def _body(
        self,
        model: str,
        messages: List[Dict[str, str]],
        stream: bool,
        response_format: Optional[Dict[str, Any]] = None,
        repetition_detection: Optional[Dict[str, int]] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if response_format is not None:
            body["response_format"] = response_format
        if repetition_detection is not None:
            body["repetition_detection"] = repetition_detection
        if seed is not None:
            body["seed"] = seed
        body.update(self.extra_body)
        return body

    # -- structured (non-streaming) chat ---------------------------------

    def chat_full(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
        repetition_detection: Optional[Dict[str, int]] = None,
        seed: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Non-streaming chat completion.

        Returns ``{"content": str, "finish_reason": Optional[str]}``.
        ``repetition_detection`` is a vLLM extension (n-gram loop detector);
        servers that don't know it ignore it. ``finish_reason`` is
        ``"repetition"`` when vLLM's detector stopped a degenerate loop.
        """
        if timeout is not None:
            self.timeout = timeout
        url = self.base_url + "/chat/completions"
        body = self._body(
            model, messages, False, response_format, repetition_detection, seed
        )
        with self._open(url, body) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Malformed JSON response from server: {exc}") from exc
        content = self._message_from(parsed, delta=False)
        finish_reason: Optional[str] = None
        choices = parsed.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            fr = choices[0].get("finish_reason")
            if isinstance(fr, str):
                finish_reason = fr
        return {"content": content, "finish_reason": finish_reason}

    # -- capability probe ------------------------------------------------

    def probe_capabilities(
        self, model: str, *, timeout: float = 20.0
    ) -> Dict[str, bool]:
        """Cheaply probe which response-contract features this server honors.

        Sends one or two tiny requests (<=48 tokens) and validates the
        *shape of the response*, not just the HTTP status — some servers
        (notably llama.cpp) silently ignore ``json_schema`` and return free
        text. Returns ``{"json_schema", "json_object",
        "repetition_detection"}`` booleans; all ``False`` means the
        caller should fall back to the sentinel-tag protocol.
        Results are cached per (server, model).
        """
        key = (self.base_url, model)
        cached = getattr(self, "_caps_cache", None)
        if cached and key in cached:
            return cached[key]
        caps = {"json_schema": False, "json_object": False, "repetition_detection": False}
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "lines",
                "strict": True,
                "schema": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
        }
        messages = [
            {
                "role": "user",
                "content": (
                    "Translate the words 'house' and 'door' to German. "
                    "Reply with a JSON array of exactly two strings, in order."
                ),
            }
        ]
        for rd in ({"max_pattern_size": 8, "min_count": 3}, None):
            try:
                res = self.chat_full(
                    model=model,
                    messages=messages,
                    response_format=schema,
                    repetition_detection=rd,
                    timeout=timeout,
                )
            except LLMError:
                res = None
            if res is not None:
                parsed = _parse_string_array(res["content"], n=2)
                if parsed is not None:
                    caps["json_schema"] = True
                    if rd is not None:
                        caps["repetition_detection"] = True
                break  # request was accepted; no need to retry without rd
        if not caps["json_schema"]:
            obj_messages = [
                {
                    "role": "user",
                    "content": (
                        "Translate the words 'house' and 'door' to German. "
                        'Reply with a JSON object: {"lines": ["...", "..."]}'
                    ),
                }
            ]
            try:
                res = self.chat_full(
                    model=model,
                    messages=obj_messages,
                    response_format={"type": "json_object"},
                    timeout=timeout,
                )
                payload = json.loads(res["content"])
                lines = payload.get("lines") if isinstance(payload, dict) else None
                if isinstance(lines, list) and len(lines) == 2 and all(
                    isinstance(x, str) and x.strip() for x in lines
                ):
                    caps["json_object"] = True
            except (LLMError, json.JSONDecodeError, TypeError, ValueError):
                pass
        if cached is None:
            self._caps_cache = {}
            cached = self._caps_cache  # type: ignore[assignment]
        cached[key] = caps
        return caps

    def _open(
        self,
        url: str,
        body: Dict[str, Any],
    ) -> Any:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers)
        try:
            return urlopen(req, timeout=self.timeout)  # type: ignore[call-arg]
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:  # pragma: no cover - defensive
                detail = ""
            raise LLMError(
                f"LLM server returned HTTP {exc.code}: {detail or exc.reason}"
            ) from exc
        except URLError as exc:
            raise LLMError(f"Could not contact LLM server at {url}: {exc.reason}") from exc

    @staticmethod
    def _message_from(payload: Any, *, delta: bool) -> str:
        if not isinstance(payload, dict):
            raise LLMError("Unexpected payload type; expected JSON object.")
        if isinstance(payload.get("error"), (dict, str)):
            raise LLMError(f"LLM server error: {payload['error']}")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMError("LLM response contained no choices.")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise LLMError("Unexpected choice shape in LLM response.")
        if delta:
            piece = choice.get("delta")
            if isinstance(piece, dict):
                content = piece.get("content")
                if isinstance(content, str):
                    return content
            # Some servers emit final text instead of deltas.
            return str(choice.get("text") or "")
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content
        # Tolerate the completions-style shape.
        if "text" in choice:
            return str(choice.get("text") or "")
        raise LLMError("LLM response message had no string content.")

    def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        stream: Optional[bool] = None,
        timeout: Optional[float] = None,
        raw_handler: Optional[Callable[[str], None]] = None,
    ) -> str:
        stream = self.stream if stream is None else stream
        if timeout is not None:
            self.timeout = timeout
        url = self.base_url + "/chat/completions"
        body = self._body(model, messages, stream)
        with self._open(url, body) as resp:
            if not stream:
                text = resp.read().decode("utf-8", errors="replace")
                if raw_handler:
                    raw_handler(text)
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise LLMError(f"Malformed JSON response from server: {exc}") from exc
                return self._message_from(parsed, delta=False)

            pieces: List[str] = []
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if raw_handler:
                    raw_handler(line)
                if line.startswith("data:"):
                    line = line[len("data:") :].strip()
                    if line == "[DONE]":
                        break
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    piece = self._message_from(parsed, delta=True)
                except LLMError:
                    continue
                pieces.append(piece)
            return "".join(pieces)


def _parse_string_array(content: Optional[str], *, n: int) -> Optional[List[str]]:
    """Parse a JSON array (or ``{"lines": [...]}``) of exactly ``n`` non-empty strings."""
    if not content or not content.strip():
        return None
    try:
        payload = json.loads(content.strip())
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        payload = payload.get("lines")
    if not isinstance(payload, list) or len(payload) != n:
        return None
    if not all(isinstance(x, str) and x.strip() for x in payload):
        return None
    return [x.strip() for x in payload]
