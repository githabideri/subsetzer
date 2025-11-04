import datetime as dt
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from subsetzer.engine import Cue, Transcript, TranscriptError
from subsetzer.formats import parse_srt, parse_tsv, parse_vtt, write_srt, write_tsv, write_vtt
from subsetzer.io import build_output_as, resolve_outfile


SRT_SAMPLE = """1
00:00:01,000 --> 00:00:04,000
Hello world!

2
00:00:05,000 --> 00:00:07,000
How are you?
"""

VTT_SAMPLE = """WEBVTT

00:00:01.000 --> 00:00:04.000
Hello world!

00:00:05.000 --> 00:00:07.000
How are you?
"""

TSV_SAMPLE = "start\tend\ttext\n0\t1\tHello\n1\t2\tWorld\n"


class FormatTests(unittest.TestCase):
    def test_srt_round_trip(self):
        transcript = parse_srt(SRT_SAMPLE)
        self.assertEqual(transcript.fmt, "srt")
        rendered = write_srt(transcript)
        self.assertIn("Hello world!", rendered)
        self.assertIn("How are you?", rendered)

    def test_vtt_note_injection(self):
        transcript = parse_vtt(VTT_SAMPLE)
        note = "translated-with model=demo time=2024-01-01T00:00:00"
        rendered = write_vtt(transcript, note=note)
        self.assertTrue(rendered.startswith("WEBVTT"))
        self.assertIn(f"NOTE {note}", rendered)

    def test_tsv_round_trip(self):
        transcript = parse_tsv(TSV_SAMPLE)
        rendered = write_tsv(transcript)
        self.assertIn("Hello", rendered)
        self.assertIn("World", rendered)

    def test_build_output_as_respects_format(self):
        cues = [Cue(index=1, start="0", end="1", text="Hello", translated="Hola")]
        transcript = Transcript(fmt="vtt", cues=cues, header="WEBVTT")
        note = "translated-with model=demo time=" + dt.datetime.now().isoformat()
        vtt_content = build_output_as(transcript, "vtt", vtt_note=note)
        self.assertIn("Hola", vtt_content)
        self.assertIn(note, vtt_content)

    def test_resolve_outfile_handles_collisions(self):
        with mock.patch("pathlib.Path.exists", side_effect=[True, False]):
            path = resolve_outfile(
                "{basename}.{dst}.{fmt}",
                Path("input.srt"),
                "auto",
                "German",
                "srt",
            )
        self.assertEqual(path.name, "input-1.German.srt")

    def test_resolve_outfile_unknown_placeholder(self):
        with self.assertRaises(TranscriptError):
            resolve_outfile(
                "{missing}.srt",
                Path("input.srt"),
                "src",
                "dst",
                "srt",
            )

    def test_resolve_outfile_includes_model_placeholder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template = Path(tmpdir) / "{basename}.{dst}.{model}.{fmt}"
            path = resolve_outfile(
                str(template),
                Path("movie.srt"),
                "de",
                "hr",
                "srt",
                model="qwen3:14b",
            )
            self.assertIn("qwen3-14b", path.name)
            self.assertTrue(path.parent.exists())
