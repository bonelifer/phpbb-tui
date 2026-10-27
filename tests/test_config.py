"""Protect existing configuration lookup and TOML loading behavior."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from phpbb_tui import config


class ConfigTests(unittest.TestCase):
    """Use temporary configuration paths, never the user's configuration."""

    def test_lookup_accepts_names_slugs_and_unique_substrings(self) -> None:
        first = config.BoardConfig("Support Board", "https://one.invalid")
        second = config.BoardConfig("Other Board", "https://two.invalid")
        cfg = config.Config([first, second], Path("downloads"), "xdg-open")
        for name in ("SUPPORT BOARD", "support-board", "support"):
            with self.subTest(name=name):
                self.assertIs(cfg.finde(name), first)
        self.assertIsNone(cfg.finde("board"))
        self.assertIsNone(cfg.finde("missing"))

    def test_load_preserves_settings_and_unicode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "boards.toml"
            downloads = root / "downloads"
            path.write_text(
                f'downloads = "{downloads.as_posix()}"\n'
                'browser = "fixture-browser"\n'
                '[[board]]\nname = "Café"\n'
                'url = "https://example.invalid/forum"\nuser = "Alice"\n',
                encoding="utf-8",
            )
            with patch.object(config, "CONFIG_FILE", path), \
                    patch.object(config, "STATE_DIR", root / "state"), \
                    patch.dict("os.environ", {}, clear=True):
                cfg = config.laden()
                self.assertEqual(cfg.downloads, downloads)
                self.assertEqual(cfg.browser, "fixture-browser")
                self.assertEqual(cfg.boards, [config.BoardConfig(
                    "Café", "https://example.invalid/forum", "Alice")])
                self.assertEqual(cfg.boards[0].cookie_path,
                                 root / "state" / "caf.cookies.txt")

    def test_missing_config_has_no_boards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(config, "CONFIG_FILE",
                              Path(directory) / "missing.toml"):
                self.assertEqual(config.laden().boards, [])
