"""Use phpBB's localized confirmation value when deleting a PM."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from phpbb_tui.board import Board, BoardError


class PMDeleteConfirmationTests(unittest.TestCase):
    """The server compares posted confirmation to its translated YES."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Mock(headers={})
        with patch("phpbb_tui.board.requests.Session",
                   return_value=self.session):
            self.board = Board("https://example.invalid",
                               Path(self.temp.name) / "cookies.txt")

    def test_confirmation_uses_the_server_label(self) -> None:
        for label in ("Yes", "Ja", "Oui", "Sí", "Y&#101;s"):
            with self.subTest(label=label):
                self.session.post.reset_mock()
                self.session.get.return_value.text = (
                    '<form id="confirm" '
                    'action="./ucp.php?confirm_key=fixture">'
                    '<input type="hidden" name="p" value="7">'
                    '<input type="submit" value="' + label + '" '
                    'name="confirm"></form>')
                self.session.post.return_value.text = 'Message deleted'
                self.board.pm_loeschen(7)
                self.session.post.assert_called_once()
                self.assertEqual(
                    self.session.post.call_args.kwargs['data']['confirm'],
                    'Yes' if label == 'Y&#101;s' else label)

    def test_missing_confirmation_value_never_submits(self) -> None:
        self.session.get.return_value.text = (
            '<form id="confirm" action="./ucp.php">'
            '<input name="confirm" type="submit"></form>')
        with self.assertRaises(BoardError):
            self.board.pm_loeschen(7)
        self.session.post.assert_not_called()
