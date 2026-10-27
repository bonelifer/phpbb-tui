"""Recognize phpBB PM confirmations without relying on translated prose."""

import unittest
from pathlib import Path
from unittest.mock import patch

from phpbb_tui.board import Board
from phpbb_tui.i18n import t


class PMConfirmationTests(unittest.TestCase):
    """Use synthetic same-board confirmation and rejection pages."""

    def setUp(self) -> None:
        self.board = Board.__new__(Board)
        self.board.base = "https://example.invalid/forum"

    @staticmethod
    def confirmation(url: str) -> str:
        return ('<div id="message">Message stored.</div>'
                '<meta http-equiv="refresh" content="3; url=' + url + '">')

    def test_pm_confirmation_is_success_without_a_dump(self) -> None:
        page = self.confirmation(
            './ucp.php?i=pm&amp;mode=view&amp;f=-2&amp;p=42')
        with patch.object(self.board, "dump",
                          side_effect=AssertionError("Dump")):
            self.assertEqual(self.board.submit_result(page),
                             (True, t("pm_gesendet_kurz")))
        self.assertEqual(self.board.pm_submission_id(page), 42)

    def test_rejection_or_unrelated_urls_are_not_success(self) -> None:
        for url in ('https://other.invalid/ucp.php?i=pm&mode=view&p=42',
                    '/other/ucp.php?i=pm&mode=view&p=42',
                    './ucp.php?i=pm&mode=compose&p=42',
                    './ucp.php?i=pm&mode=view&p=0',
                    './ucp.php?i=pm&mode=view&p=42&p=43'):
            with self.subTest(url=url):
                self.assertIsNone(self.board.pm_submission_id(
                    self.confirmation(url)))

    def test_echoed_meta_cannot_confirm_a_send(self) -> None:
        page = self.confirmation('./ucp.php?i=pm&mode=view&p=42')
        self.assertIsNone(self.board.pm_submission_id(
            '<form id="postform">' + page + '</form>'))

    def test_unknown_response_retains_existing_failure_behavior(self) -> None:
        with patch.object(self.board, 'dump',
                          return_value=Path('fixture.html')):
            self.assertFalse(self.board.submit_result('Unknown response')[0])
