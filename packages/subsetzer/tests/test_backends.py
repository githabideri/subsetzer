import json
import unittest
from unittest import mock
from urllib.error import HTTPError

from subsetzer.backends import LLMError, OpenAICompat


class FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._data

    def __iter__(self):
        for chunk in self._data.split(b"\n"):
            yield chunk + b"\n"


def make_server(handler):
    def fake_urlopen(req, timeout):
        return handler(req)

    return fake_urlopen


class OpenAICompatTests(unittest.TestCase):
    def test_empty_base_url_rejected(self):
        with self.assertRaises(ValueError):
            OpenAICompat("")

    def test_non_streaming_message_content(self):
        def handler(req):
            body = json.loads(req.data)
            self.assertEqual(body["model"], "m1")
            self.assertFalse(body["stream"])
            self.assertEqual(req.full_url, "http://127.0.0.1:8080/v1/chat/completions")
            self.assertEqual(req.headers.get("Authorization"), "Bearer secret")
            return FakeResponse(json.dumps(
                {"choices": [{"message": {"content": "Hallo"}}]}
            ).encode())

        backend = OpenAICompat("http://127.0.0.1:8080/v1", api_key="secret")
        with mock.patch("subsetzer.backends.urlopen", side_effect=make_server(handler)):
            result = backend.chat(model="m1", messages=[{"role": "user", "content": "x"}], stream=False)
        self.assertEqual(result, "Hallo")

    def test_streaming_deltas_until_done(self):
        payload = b"".join(
            line + b"\n"
            for line in (
                b'data: {"choices": [{"delta": {"content": "He"}}]}',
                b'data: {"choices": [{"delta": {"content": "llo"}}]}',
                b"data: [DONE]",
            )
        )
        seen = []

        def handler(req):
            body = json.loads(req.data)
            self.assertTrue(body["stream"])
            return FakeResponse(payload)

        backend = OpenAICompat("http://127.0.0.1:11434/v1")
        with mock.patch("subsetzer.backends.urlopen", side_effect=make_server(handler)):
            result = backend.chat(
                model="gemma3:12b",
                messages=[{"role": "user", "content": "x"}],
                stream=True,
                raw_handler=seen.append,
            )
        self.assertEqual(result, "Hello")
        self.assertEqual(len(seen), 3)

    def test_max_tokens_temperature_and_extra_body_merged(self):
        def handler(req):
            body = json.loads(req.data)
            self.assertEqual(body["max_tokens"], 4000)
            self.assertAlmostEqual(body["temperature"], 0.2)
            self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
            return FakeResponse(json.dumps(
                {"choices": [{"message": {"content": "ok"}}]}
            ).encode())

        backend = OpenAICompat(
            "http://127.0.0.1:8080/v1",
            max_tokens=4000,
            temperature=0.2,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        with mock.patch("subsetzer.backends.urlopen", side_effect=make_server(handler)):
            result = backend.chat(model="m", messages=[], stream=False)
        self.assertEqual(result, "ok")

    def test_http_error_includes_server_detail(self):
        def handler(req):
            raise HTTPError(
                "http://127.0.0.1:8080/v1/chat/completions",
                500,
                "Internal Server Error",
                {},
                __import__("io").BytesIO(b'{"error": {"message": "boom"}}'),
            )

        backend = OpenAICompat("http://127.0.0.1:8080/v1")
        with mock.patch("subsetzer.backends.urlopen", side_effect=make_server(handler)):
            with self.assertRaises(LLMError) as ctx:
                backend.chat(model="m", messages=[], stream=False)
        self.assertIn("500", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))

    def test_error_payload_raises(self):
        def handler(req):
            return FakeResponse(json.dumps(
                {"error": {"message": "model not found"}}
            ).encode())

        backend = OpenAICompat("http://127.0.0.1:8080/v1")
        with mock.patch("subsetzer.backends.urlopen", side_effect=make_server(handler)):
            with self.assertRaises(LLMError) as ctx:
                backend.chat(model="missing", messages=[], stream=False)
        self.assertIn("model not found", str(ctx.exception))

    def test_malformed_json_raises(self):
        def handler(req):
            return FakeResponse(b"not json at all")

        backend = OpenAICompat("http://127.0.0.1:8080/v1")
        with mock.patch("subsetzer.backends.urlopen", side_effect=make_server(handler)):
            with self.assertRaises(LLMError):
                backend.chat(model="m", messages=[], stream=False)
