import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from subsetzer import cli


class CliTests(unittest.TestCase):
    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as ctx:
            cli.main(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_subsetzer_env_alias_takes_precedence(self):
        environ = {
            "SUBSETZER_LLM_MODEL": "alias-model",
            "HOMEDOC_LLM_MODEL": "legacy-model",
        }
        with mock.patch.dict(os.environ, environ, clear=True):
            parser = cli._build_parser()
            args = parser.parse_args(["--in", "input.srt", "--out", "out"])
            self.assertEqual(args.model, "alias-model")

    def _run_cli(self, extra_args=None):
        extra_args = extra_args or []
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            infile = tmp_path / "input.srt"
            infile.write_text(
                textwrap.dedent(
                    """\
                    1
                    00:00:00,000 --> 00:00:01,000
                    Hello
                    """
                )
            )
            outdir = tmp_path / "out"
            args = ["--in", str(infile), "--out", str(outdir), "--no-llm", "--flat"] + extra_args
            cli.main(args)
            outputs = list(outdir.glob("**/*"))
            return outdir, outputs

    def test_llm_raw_not_created_without_capture_flag(self):
        _, outputs = self._run_cli()
        self.assertFalse(any(p.name == "llm_raw.txt" for p in outputs))

    def test_llm_raw_created_when_capture_flag_set(self):
        _, outputs = self._run_cli(["--capture-raw"])
        self.assertTrue(any(p.name == "llm_raw.txt" for p in outputs))
