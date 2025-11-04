import unittest
from unittest import mock

import subsetzer.engine as engine_mod
from subsetzer.engine import (
    Cue,
    Chunk,
    Transcript,
    _apply_batch,
    translate_range,
)


class FakeStreamResponse:
    def __init__(self, lines):
        self._lines = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._lines)


class ApplyBatchTests(unittest.TestCase):
    def setUp(self):
        self.original_batch = [("1", "Hello"), ("2", "World"), ("3", "Foo"), ("4", "Bar")]
        self.cues = [
            Cue(index=1, start="0", end="1", text="Hello"),
            Cue(index=2, start="1", end="2", text="World"),
            Cue(index=3, start="2", end="3", text="Foo"),
            Cue(index=4, start="3", end="4", text="Bar"),
        ]

    def test_apply_batch_only_updates_present_ids(self):
        batches = iter(
            [
                [("1", "Hola"), ("2", "Mundo")],
                [("3", "Baz"), ("4", "Qux")],
            ]
        )

        def fake_batch(request_batch, **_):
            return next(batches)

        with mock.patch("subsetzer.engine.llm_translate_batch", side_effect=fake_batch):
            missing_first = _apply_batch(
                self.original_batch[:2],
                self.cues,
                "",
                "",
                "",
                "",
                "auto",
                False,
                30,
                True,
                None,
            )
            self.assertEqual(missing_first, [])
            self.assertEqual(self.cues[0].translated, "Hola")
            self.assertEqual(self.cues[1].translated, "Mundo")

            missing_second = _apply_batch(
                self.original_batch[2:],
                self.cues,
                "",
                "",
                "",
                "",
                "auto",
                False,
                30,
                True,
                None,
            )
            self.assertEqual(missing_second, [])
            self.assertEqual(self.cues[2].translated, "Baz")
            self.assertEqual(self.cues[3].translated, "Qux")

    def test_apply_batch_retries_missing_ids(self):
        def fake_batch(request_batch, **_):
            # Return only first translation; second gets dropped.
            return [(request_batch[0][0], "Hola")]

        with mock.patch("subsetzer.engine.llm_translate_batch", side_effect=fake_batch), mock.patch(
            "subsetzer.engine.llm_translate_single", return_value="Mundo"
        ) as single_mock:
            missing = _apply_batch(
                self.original_batch[:2],
                self.cues,
                "",
                "",
                "",
                "",
                "auto",
                False,
                30,
                True,
                None,
            )
        self.assertEqual(missing, [])
        self.assertEqual(self.cues[0].translated, "Hola")
        self.assertEqual(self.cues[1].translated, "Mundo")
        single_mock.assert_called_once()

    def test_apply_batch_marks_failures_after_retry(self):
        def fake_batch(request_batch, **_):
            return [
                (request_batch[0][0], "  Hola  "),
                (request_batch[1][0], "   "),
            ]

        with mock.patch("subsetzer.engine.llm_translate_batch", side_effect=fake_batch), mock.patch(
            "subsetzer.engine.llm_translate_single", return_value="   "
        ):
            missing = _apply_batch(
                self.original_batch[:2],
                self.cues,
                "",
                "",
                "",
                "",
                "auto",
                False,
                30,
                True,
                None,
            )
        self.assertEqual(missing, ["2"])
        self.assertEqual(self.cues[0].translated, "  Hola  ")
        self.assertEqual(self.cues[1].translated, "World")

    def test_apply_batch_retries_when_translation_equals_source(self):
        def fake_batch(request_batch, **_):
            return [
                (request_batch[0][0], "Hola"),
                (request_batch[1][0], "World"),  # identical to source
            ]

        with mock.patch("subsetzer.engine.llm_translate_batch", side_effect=fake_batch), mock.patch(
            "subsetzer.engine.llm_translate_single", return_value="Mundo"
        ) as single_mock:
            missing = _apply_batch(
                self.original_batch[:2],
                self.cues,
                "",
                "",
                "",
                "",
                "auto",
                False,
                30,
                True,
                None,
            )
        self.assertEqual(missing, [])
        self.assertEqual(self.cues[0].translated, "Hola")
        self.assertEqual(self.cues[1].translated, "Mundo")
        single_mock.assert_called_once()

    def test_llm_translate_batch_preserves_newlines(self):
        pairs = [("1", "Hello"), ("2", "World")]
        fake_response = "1|||Hola\nMundo\n2|||Buenos\ndias\n"

        with mock.patch("subsetzer.engine._perform_llm_call", return_value=fake_response):
            translated_pairs = engine_mod.llm_translate_batch(
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

        mapping = {pid: text for pid, text in translated_pairs}
        self.assertEqual(mapping["1"], "Hola\nMundo")
        self.assertEqual(mapping["2"], "Buenos\ndias")


class HttpJsonStreamTests(unittest.TestCase):
    def test_streaming_data_prefix_handling(self):
        lines = [
            'data: {"message": {"content": "Hel"}}',
            'data: {"message": {"content": "lo"}}',
            "data: [DONE]",
        ]
        fake_response = FakeStreamResponse(lines)
        collector = []

        def fake_urlopen(req, timeout):
            return fake_response

        with mock.patch("subsetzer.engine.urlopen", side_effect=fake_urlopen):
            result = engine_mod._http_json(  # type: ignore[attr-defined]
                "http://example/api/chat",
                {"a": 1},
                10,
                stream=True,
                raw_handler=collector.append,
            )

        self.assertEqual(result, "Hello")
        self.assertEqual(collector, lines)


class TranslationWhitespaceTests(unittest.TestCase):
    def test_translate_range_preserves_whitespace_on_empty(self):
        transcript = Transcript(fmt="srt", cues=[Cue(index=1, start="0", end="1", text="  Hello  \n")])
        chunk = Chunk(cid=1, start_idx=1, end_idx=1, charcount=5)

        with mock.patch("subsetzer.engine.llm_translate_single", return_value=""):
            translate_range(
                transcript,
                [chunk],
                server="http://localhost",
                model="demo",
                source="en",
                target="de",
                batch_n=1,
                translate_bracketed=True,
                llm_mode="auto",
                stream=False,
                timeout=10,
                no_llm=False,
            )

        self.assertEqual(transcript.cues[0].translated, "  Hello  \n")
