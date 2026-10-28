"""Reject unsupported interpreters before importing Python 3.11 modules."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PythonVersionTests(unittest.TestCase):
    """Exercise the real module entry point in fresh subprocesses."""

    def run_entry(self, version=None):
        script = ("import runpy, sys; "
                  + (f"sys.version_info = {version!r}; " if version else "")
                  + "sys.argv = ['phpbb-tui', '--help']; "
                  "runpy.run_module('phpbb_tui', run_name='__main__')")
        return subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, capture_output=True,
            text=True, timeout=10, env={**os.environ, "PHPBB_TUI_LANG": "en"})

    def test_unsupported_versions_fail_without_an_import_traceback(self):
        for version in ((3, 9, 0), (3, 10, 0)):
            with self.subTest(version=version):
                result = self.run_entry(version)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr,
                                 "phpbb-tui requires Python 3.11 or newer.\n")

    def test_supported_interpreter_still_displays_help(self):
        result = self.run_entry()
        self.assertEqual(result.returncode, 0)
        self.assertIn("phpbb-tui", result.stdout)
        self.assertEqual(result.stderr, "")
