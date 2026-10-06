"""Tests for the structured-output batch contract and the closed
retry/flag policy (json_schema / json_object / repetition detection).

A ``FakeBackend`` subclasses the real ``OpenAICompat`` so the engine's
``isinstance`` gate accepts it, while ``chat`` / ``chat_full`` /
``probe_capabilities`` are scripted — no network.
"""
import json
import unittest
from typing import Dict, List, Optional

from subsetzer.backends import OpenAICompat, parse_string_array
from subsetzer.engine import Cue, _apply_batch, llm_translate_batch_structured


class FakeBackend(OpenAICompat):
    def __init__(self) -> None:
        super().__init__("http://fake/v1")
        # (content, finish_reason) returned by chat_full; index advances.
        self.full_results: List[Dict[str, Optional[str]]] = []
        self._full_i = 0
        self.full_calls: List[Dict[str, object]] = []
        # scripted chat() return values for the sentinel / per-cue path.
        self.chat_results: List[str] = []
        self._chat_i = 0

    def chat_full(self, *, model, messages, response_format=None,
                  repetition_detection=None, seed=None, timeout=None):
        self.full_calls.append(
            {
                "response_format": response_format,
                "repetition_detection": repetition_detection,
                "seed": seed,
            }
        )
        if self._full_i < len(self.full_results):
            res = self.full_results[self._full_i]
            self._full_i += 1
        else:
            res = self.full_results[-1]
        return {"content": res["content"], "finish_reason": res["finish_reason"]}

    def chat(self, *, model, messages, stream=None, timeout=None, raw_handler=None):
        if self._chat_i < len(self.chat_results):
            out = self.chat_results[self._chat_i]
            self._chat_i += 1
        else:
            out = self.chat_results[-1]
        return out


def _cues(ids: List[int], texts: List[str]) -> List[Cue]:
    return [
        Cue(index=i, start="0", end="1", text=t)
        for i, t in zip(ids, texts)
    ]


class ParseStringArrayTests(unittest.TestCase):
    def test_plain_array(self):
        self.assertEqual(parse_string_array('["a", "b"]', n=2), ["a", "b"])

    def test_lines_wrapper(self):
        self.assertEqual(
            parse_string_array('{"lines": ["x", "y"]}', n=2), ["x", "y"]
        )

    def test_wrong_length(self):
        self.assertIsNone(parse_string_array('["a", "b", "c"]', n=2))

    def test_non_string_element(self):
        self.assertIsNone(parse_string_array('["a", 3]', n=2))

    def test_empty_element(self):
        self.assertIsNone(parse_string_array('["a", "  "]', n=2))

    def test_not_json(self):
        self.assertIsNone(parse_string_array("just prose, no json", n=2))

    def test_blank(self):
        self.assertIsNone(parse_string_array("   ", n=2))


class StructuredBatchTests(unittest.TestCase):
    def test_ok_returns_pairs_in_order(self):
        b = FakeBackend()
        b.full_results = [
            {"content": json.dumps(["du", "tür"]), "finish_reason": "stop"}
        ]
        pairs, status = llm_translate_batch_structured(
            [("1", "Haus"), ("2", "Tür")],
            backend=b,
            model="m",
            source="German",
            target="French",
            mode="json",
        )
        self.assertEqual(status, "ok")
        self.assertEqual(pairs, [("1", "du"), ("2", "tür")])
        # the json_schema contract was sent with min/maxItems = n
        rf = b.full_calls[0]["response_format"]
        self.assertEqual(rf["type"], "json_schema")
        self.assertEqual(rf["json_schema"]["schema"]["minItems"], 2)
        self.assertEqual(rf["json_schema"]["schema"]["maxItems"], 2)

    def test_json_object_mode_sends_json_object(self):
        b = FakeBackend()
        b.full_results = [
            {
                "content": json.dumps({"lines": ["a", "b"]}),
                "finish_reason": "stop",
            }
        ]
        _, status = llm_translate_batch_structured(
            [("1", "x"), ("2", "y")],
            backend=b,
            model="m",
            source="en",
            target="de",
            mode="json_object",
        )
        self.assertEqual(status, "ok")
        self.assertEqual(b.full_calls[0]["response_format"], {"type": "json_object"})

    def test_degenerate_on_repetition_finish(self):
        b = FakeBackend()
        b.full_results = [
            {"content": "Qo'pu' Qo'pu' Qo'pu'...", "finish_reason": "repetition"}
        ]
        pairs, status = llm_translate_batch_structured(
            [("1", "a"), ("2", "b")],
            backend=b,
            model="m",
            source="en",
            target="Klingon",
            mode="json",
        )
        self.assertEqual(status, "degenerate")
        self.assertEqual(pairs, [])

    def test_malformed_on_prose(self):
        b = FakeBackend()
        b.full_results = [
            {"content": "Sure, here is your translation:", "finish_reason": "stop"}
        ]
        _, status = llm_translate_batch_structured(
            [("1", "a"), ("2", "b")],
            backend=b,
            model="m",
            source="en",
            target="de",
            mode="json",
        )
        self.assertEqual(status, "malformed")

    def test_repetition_detection_passed_when_enabled(self):
        b = FakeBackend()
        b.full_results = [{"content": json.dumps(["a", "b"]), "finish_reason": "stop"}]
        llm_translate_batch_structured(
            [("1", "a"), ("2", "b")],
            backend=b,
            model="m",
            source="en",
            target="de",
            mode="json",
            repetition_detection=True,
        )
        self.assertEqual(
            b.full_calls[0]["repetition_detection"],
            {"max_pattern_size": 8, "min_count": 3},
        )

    def test_non_openai_compat_falls_back_to_sentinel(self):
        from unittest import mock

        b = mock.Mock()
        b.chat.return_value = "1|||translated one\n2|||translated two"
        pairs, status = llm_translate_batch_structured(
            [("1", "one"), ("2", "two")],
            backend=b,
            model="m",
            source="en",
            target="de",
            mode="json",
        )
        # a plain duck-typed backend is not OpenAICompat -> sentinel path
        self.assertEqual(status, "ok")
        self.assertEqual(pairs, [("1", "translated one"), ("2", "translated two")])


class ApplyBatchPolicyTests(unittest.TestCase):
    def test_degenerate_twice_flags_cues_as_source(self):
        b = FakeBackend()
        # both the initial and the seeded retry degenerate
        b.full_results = [
            {"content": "", "finish_reason": "repetition"},
            {"content": "", "finish_reason": "repetition"},
        ]
        cues = _cues([1, 2], ["alpha", "beta"])
        missing = _apply_batch(
            [("1", "alpha"), ("2", "beta")],
            cues,
            source="en",
            target="Klingon",
            model="m",
            backend=b,
            mode="json",
            caps={"repetition_detection": True},
            logger=lambda _msg: None,
        )
        self.assertEqual(missing, ["1", "2"])
        # flagged cues keep their source text (visible marker for a human)
        self.assertEqual(cues[0].translated, "alpha")
        self.assertEqual(cues[1].translated, "beta")
        # two structured attempts, second one seeded
        self.assertEqual(len(b.full_calls), 2)
        self.assertIsNone(b.full_calls[0]["seed"])
        self.assertIsNotNone(b.full_calls[1]["seed"])

    def test_ok_assigns_translations(self):
        b = FakeBackend()
        b.full_results = [
            {"content": json.dumps(["one-t", "two-t"]), "finish_reason": "stop"}
        ]
        cues = _cues([1, 2], ["one", "two"])
        missing = _apply_batch(
            [("1", "one"), ("2", "two")],
            cues,
            source="en",
            target="de",
            model="m",
            backend=b,
            mode="json",
            caps={"repetition_detection": False},
        )
        self.assertEqual(missing, [])
        self.assertEqual(cues[0].translated, "one-t")
        self.assertEqual(cues[1].translated, "two-t")
        self.assertEqual(len(b.full_calls), 1)  # no retry needed

    def test_malformed_falls_back_to_single_cue(self):
        b = FakeBackend()
        # structured call is malformed...
        b.full_results = [{"content": "nope", "finish_reason": "stop"}]
        # ...then the per-cue single-cue fallback (<translation> tags) supplies real translations
        b.chat_results = [
            "<translation>single one</translation>",
            "<translation>single two</translation>",
        ]
        cues = _cues([1, 2], ["one", "two"])
        missing = _apply_batch(
            [("1", "one"), ("2", "two")],
            cues,
            source="en",
            target="de",
            model="m",
            backend=b,
            mode="json",
            caps={"repetition_detection": False},
        )
        self.assertEqual(cues[0].translated, "single one")
        self.assertEqual(cues[1].translated, "single two")


class ProbeTests(unittest.TestCase):
    def test_probe_reports_json_schema_and_rd(self):
        b = FakeBackend()
        # probe sends a 2-item schema; answer with a valid 2-string array
        b.full_results = [
            {"content": json.dumps(["Haus", "Tür"]), "finish_reason": "stop"}
        ]
        caps = b.probe_capabilities("m")
        self.assertTrue(caps["json_schema"])
        self.assertTrue(caps["repetition_detection"])
        self.assertFalse(caps["json_object"])

    def test_probe_falls_back_to_json_object(self):
        b = FakeBackend()
        # schema request returns prose (silently ignored) -> not json_schema,
        # then the json_object probe returns a {"lines"} object -> honored
        b.full_results = [
            {"content": "Haus, Tür.", "finish_reason": "stop"},
            {
                "content": json.dumps({"lines": ["Haus", "Tür"]}),
                "finish_reason": "stop",
            },
        ]
        caps = b.probe_capabilities("m")
        self.assertFalse(caps["json_schema"])
        self.assertTrue(caps["json_object"])

    def test_probe_all_false_on_total_failure(self):
        b = FakeBackend()
        b.full_results = [
            {"content": "", "finish_reason": "stop"},
            {"content": "", "finish_reason": "stop"},
        ]
        caps = b.probe_capabilities("m")
        self.assertFalse(caps["json_schema"])
        self.assertFalse(caps["json_object"])
        self.assertFalse(caps["repetition_detection"])


if __name__ == "__main__":
    unittest.main()
