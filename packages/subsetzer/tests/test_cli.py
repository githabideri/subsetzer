import os
import unittest
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

