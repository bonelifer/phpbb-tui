"""Protect management commands and existing interactive launch dispatch."""

import contextlib
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from phpbb_tui import __main__ as entry
from phpbb_tui import config


class MainTests(unittest.TestCase):
    """Mock UI, credentials, and HTTP while exercising the real dispatcher."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bc = config.BoardConfig("Example", "https://example.invalid",
                                     "Alice")
        self.cfg = config.Config([self.bc], self.root / "downloads", "browser")
        self.board = Mock()
        self.board.logged_in.return_value = True
        self.board.username = "Alice"
        self.board.name = self.bc.name
        self.board.base = self.bc.url
        self.start = Mock(return_value="done")
        fake_ui = types.ModuleType("phpbb_tui.ui")
        fake_ui.starten = self.start
        patches = [
            patch.object(entry.cfgmod, "laden", return_value=self.cfg),
            patch.object(entry.cfgmod, "STATE_DIR", self.root),
            patch.object(entry, "Board", return_value=self.board),
            patch.dict("sys.modules", {"phpbb_tui.ui": fake_ui}),
            patch("builtins.input", side_effect=AssertionError(
                "Unexpected input prompt")),
            patch.object(entry.getpass, "getpass", side_effect=AssertionError(
                "Unexpected password prompt")),
            contextlib.redirect_stdout(io.StringIO()),
        ]
        for manager in patches:
            manager.__enter__()
            self.addCleanup(manager.__exit__, None, None, None)

    def test_help_does_not_construct_board_or_start_ui(self) -> None:
        self.assertEqual(entry.main(["--help"]), 0)
        entry.Board.assert_not_called()
        self.start.assert_not_called()

    def test_list_does_not_construct_board(self) -> None:
        self.assertEqual(entry.main(["list"]), 0)
        entry.Board.assert_not_called()
        self.start.assert_not_called()

    def test_status_reports_session_state(self) -> None:
        for logged_in in (True, False):
            with self.subTest(logged_in=logged_in):
                self.board.logged_in.return_value = logged_in
                self.assertEqual(entry.main(["status", "Example"]),
                                 0 if logged_in else 1)
        self.start.assert_not_called()

    def test_logout_removes_only_selected_session(self) -> None:
        self.bc.cookie_path.write_text("synthetic", encoding="utf-8")
        other = self.root / "other.cookies.txt"
        other.write_text("synthetic", encoding="utf-8")
        self.assertEqual(entry.main(["logout", "Example"]), 0)
        self.assertFalse(self.bc.cookie_path.exists())
        self.assertTrue(other.exists())
        self.board.logged_in.assert_not_called()

    def test_login_uses_existing_interactive_flow(self) -> None:
        with patch("builtins.input", return_value=""), \
                patch.object(entry.getpass, "getpass", return_value="fixture"):
            self.assertEqual(entry.main(["login", "Example"]), 0)
        self.board.login.assert_called_once_with("Alice", "fixture")
        self.start.assert_not_called()

    def test_add_guest_registers_board_without_login(self) -> None:
        with patch.object(entry.cfgmod, "board_hinzufuegen",
                          return_value=self.bc) as add:
            self.assertEqual(entry.main(
                ["add", "https://example.invalid/", "Example", "--guest"]), 0)
        add.assert_called_once_with("Example", "https://example.invalid")
        self.board.get.assert_called_once_with("index.php")
        self.board.login.assert_not_called()
        self.start.assert_not_called()

    def test_no_arguments_and_named_board_start_tui(self) -> None:
        for argv in ([], ["Example"]):
            with self.subTest(argv=argv):
                self.start.reset_mock()
                self.assertEqual(entry.main(argv), 0)
                self.start.assert_called_once_with(self.board, self.cfg)

    def test_guest_aliases_skip_login_check(self) -> None:
        for flag in ("--guest", "--gast"):
            with self.subTest(flag=flag):
                self.assertEqual(entry.main(["Example", flag]), 0)
        self.board.logged_in.assert_not_called()

    def test_missing_session_enters_existing_login_flow(self) -> None:
        self.board.logged_in.return_value = False
        with patch.object(entry, "anmelden", return_value=True) as login:
            self.assertEqual(entry.main(["Example"]), 0)
        login.assert_called_once_with(self.board, "Alice")
        self.start.assert_called_once()

    def test_board_switch_returns_to_selection(self) -> None:
        self.start.side_effect = ["wechseln", "done"]
        with patch.object(entry, "auswahl", return_value=self.bc) as select:
            self.assertEqual(entry.main(["Example"]), 0)
        select.assert_called_once_with(self.cfg)
        self.assertEqual(self.start.call_count, 2)

    def test_unknown_board_and_empty_configuration_fail(self) -> None:
        self.assertEqual(entry.main(["missing"]), 1)
        self.cfg.boards.clear()
        self.assertEqual(entry.main([]), 1)
        self.start.assert_not_called()
