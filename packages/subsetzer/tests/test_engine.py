import unittest
from unittest import mock

import subsetzer.engine as engine_mod
from subsetzer.engine import (
    Cue,
    Chunk,
    Transcript,
    _apply_batch,
    _collapse_text,
    _remove_punctuation,
    translate_range,
)


def fake_backend(response: str):
    backend = mock.Mock()
    backend.chat.return_value = response
    return backend


class ApplyBatchTests(unittest.TestCase):
    def setUp(self):
        self.original_batch = [("1", "Hello"), ("2", "World"), ("3", "Foo"), ("4", "Bar")]
        self.cues = [
            Cue(index=1, start="0", end="1", text="Hello"),
            Cue(index=2, start="1", end="2", text="World"),
            Cue(index=3, start="2", end="3", text="Foo"),
            Cue(index=4, start="3", end="4", text="Bar"),
        ]
        self.backend = mock.Mock()

    def _apply(self, batch):
        return _apply_batch(
            batch,
            self.cues,
            source="",
            target="",
            model="demo",
            backend=self.backend,
        )

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
            missing_first = self._apply(self.original_batch[:2])
            self.assertEqual(missing_first, [])
            self.assertEqual(self.cues[0].translated, "Hola")
            self.assertEqual(self.cues[1].translated, "Mundo")

            missing_second = self._apply(self.original_batch[2:])
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
            missing = self._apply(self.original_batch[:2])
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
            missing = self._apply(self.original_batch[:2])
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
            missing = self._apply(self.original_batch[:2])
        self.assertEqual(missing, [])
        self.assertEqual(self.cues[0].translated, "Hola")
        self.assertEqual(self.cues[1].translated, "Mundo")
        single_mock.assert_called_once()

    def test_llm_translate_batch_preserves_newlines(self):
        pairs = [("1", "Hello"), ("2", "World")]
        fake_response = "1|||Hola\nMundo\n2|||Buenos\ndias\n"

        backend = fake_backend(fake_response)
        translated_pairs = engine_mod.llm_translate_batch(
            pairs,
            backend=backend,
            source="en",
            target="es",
            model="demo",
        )

        mapping = {pid: text for pid, text in translated_pairs}
        self.assertEqual(mapping["1"], "Hola\nMundo")
        self.assertEqual(mapping["2"], "Buenos\ndias")
        called = backend.chat.call_args
        self.assertEqual(called.kwargs["model"], "demo")
        self.assertEqual(len(called.kwargs["messages"]), 2)

    def test_llm_translate_batch_skips_preamble_text(self):
        pairs = [("1", "Hello"), ("2", "World")]
        fake_response = "Sure, here you go: 1|||Hola\n2|||Mundo\n"

        backend = fake_backend(fake_response)
        translated_pairs = engine_mod.llm_translate_batch(
            pairs,
            backend=backend,
            source="en",
            target="es",
            model="demo",
        )

        mapping = {pid: text for pid, text in translated_pairs}
        self.assertEqual(mapping["1"], "Hola")
        self.assertEqual(mapping["2"], "Mundo")

    def test_cleanup_translation_prefers_translation_tags(self):
        raw = (
            "Some chatter before\n"
            "<translation>\n"
            "First line||Second line\n"
            "Third line\n"
            "</translation>\n"
            "Ignore this."
        )
        result = engine_mod._cleanup_translation(raw)
        self.assertEqual(result, "First line\nSecond line\nThird line")

    def test_cleanup_translation_handles_markers_when_tags_missing(self):
        raw = "INPUT: keep original\nFirst line||Second line\nThird line"
        result = engine_mod._cleanup_translation(raw)
        self.assertEqual(result, "First line\nSecond line\nThird line")


class PostProcessingTests(unittest.TestCase):
    def test_collapse_text_joins_lines(self):
        self.assertEqual(_collapse_text("line one\nline two\nline three"), "line one line two line three")
        self.assertEqual(_collapse_text("  spaced   out  \n"), "spaced out")
        self.assertEqual(_collapse_text(""), "")

    def test_collapse_text_strips_speaker_dashes(self):
        self.assertEqual(_collapse_text("- Anna\n- Ben"), "Anna Ben")
        # Single dash line stays as-is (marker only stripped in all-dash runs)
        self.assertEqual(_collapse_text("- Anna"), "- Anna")

    def test_remove_punctuation_keeps_dashes_and_brackets(self):
        self.assertEqual(
            _remove_punctuation("Hello, world! How's it going?\u2014fine\u3002"),
            "Hello world How s it going fine",
        )
        self.assertEqual(_remove_punctuation("[MUSIC]"), "[MUSIC]")
        self.assertEqual(_remove_punctuation("a - b - c"), "a - b - c")

    def test_translate_range_no_punc_and_one_line(self):
        transcript = Transcript(
            fmt="srt",
            cues=[
                Cue(index=1, start="0", end="1", text="Hallo, wie geht's?"),
                Cue(index=2, start="1", end="2", text="Mir gut.\nDanke!"),
            ],
        )
        chunk = Chunk(cid=1, start_idx=1, end_idx=2, charcount=30)
        calls = []

        def fake_single(text, **kwargs):
            calls.append(text)
            return "Hola! Bien."

        with mock.patch("subsetzer.engine.llm_translate_single", side_effect=fake_single):
            translate_range(
                transcript,
                [chunk],
                backend=mock.Mock(),
                model="demo",
                source="en",
                target="de",
                batch_n=1,
                no_llm=False,
                no_punc=True,
                one_line=True,
            )

        self.assertEqual(calls, ["Hallo, wie geht's?", "Mir gut.\nDanke!"])
        self.assertEqual(transcript.cues[0].translated, "Hola Bien")
        self.assertEqual(transcript.cues[1].translated, "Hola Bien")

    def test_translate_range_no_punc_not_applied_in_no_llm(self):
        transcript = Transcript(fmt="srt", cues=[Cue(index=1, start="0", end="1", text="Keep: [TAG], ok!")])
        chunk = Chunk(cid=1, start_idx=1, end_idx=1, charcount=10)
        translate_range(
            transcript,
            [chunk],
            backend=mock.Mock(),
            model="demo",
            source="en",
            target="de",
            batch_n=1,
            no_llm=True,
            no_punc=True,
        )
        self.assertEqual(transcript.cues[0].translated, "Keep: [TAG], ok!")

    def test_translate_range_progress_hook(self):
        transcript = Transcript(
            fmt="srt",
            cues=[
                Cue(index=1, start="0", end="1", text="A"),
                Cue(index=2, start="1", end="2", text="B"),
                Cue(index=3, start="2", end="3", text="C"),
            ],
        )
        chunk = Chunk(cid=1, start_idx=1, end_idx=3, charcount=3)
        progress: list = []

        def fake_batch(request_batch, **_):
            return [(pid, f"tr-{pid}") for pid, _ in request_batch]

        with mock.patch("subsetzer.engine.llm_translate_batch", side_effect=fake_batch):
            translate_range(
                transcript,
                [chunk],
                backend=mock.Mock(),
                model="demo",
                source="en",
                target="de",
                batch_n=2,
                progress=lambda d, t: progress.append((d, t)),
            )
        # batch of 2, then batch of 1
        self.assertEqual(progress, [(2, 3), (3, 3)])
        self.assertEqual([c.translated for c in transcript.cues], ["tr-1", "tr-2", "tr-3"])


class TranslationWhitespaceTests(unittest.TestCase):
    def test_translate_range_preserves_whitespace_on_empty(self):
        transcript = Transcript(fmt="srt", cues=[Cue(index=1, start="0", end="1", text="  Hello  \n")])
        chunk = Chunk(cid=1, start_idx=1, end_idx=1, charcount=5)

        with mock.patch("subsetzer.engine.llm_translate_single", return_value=""):
            translate_range(
                transcript,
                [chunk],
                backend=mock.Mock(),
                model="demo",
                source="en",
                target="de",
                batch_n=1,
                no_llm=False,
            )

        self.assertEqual(transcript.cues[0].translated, "  Hello  \n")
