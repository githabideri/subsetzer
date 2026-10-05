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
]


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
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if self.max_tokens is not None:
            body["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            body["temperature"] = self.temperature
        body.update(self.extra_body)
        return body

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
