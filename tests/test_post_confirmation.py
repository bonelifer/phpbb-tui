"""Recognize phpBB's HTTP redirect after a successful post or edit."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from phpbb_tui.board import Board, Entwurf
from phpbb_tui.i18n import t


class PostConfirmationTests(unittest.TestCase):
    """Use synthetic response metadata, never a public forum submission."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Mock(headers={})
        with patch("phpbb_tui.board.requests.Session",
                   return_value=self.session):
            self.board = Board("https://example.invalid/forum",
                               Path(self.temp.name) / "cookies.txt")
        self.form = Entwurf({"creation_time": "1"}, "posting.php", {})
        self.page = '<div id="p101" class="post bg2">Stored post</div>'
        self.session.post.return_value = Mock(
            text=self.page, history=[Mock(status_code=302)],
            url="https://example.invalid/forum/viewtopic.php?t=42#p101")

    def test_http_redirect_confirms_without_diagnostic_dump(self) -> None:
        page = self.board.submit(self.form, "Subject", "Body")
        with patch.object(self.board, "dump", side_effect=AssertionError(
                "Successful redirect must not create a diagnostic dump")):
            self.assertEqual(self.board.submit_result(page),
                             (True, t("beitrag_da_nr", pid=101)))

    def test_wrong_origin_or_missing_post_does_not_confirm(self) -> None:
        for url in ("https://other.invalid/forum/viewtopic.php#p101",
                    "https://example.invalid/elsewhere/viewtopic.php#p101",
                    "https://example.invalid/forum/viewtopic.php#p999",
                    "https://example.invalid/forum/viewtopic.php"):
            with self.subTest(url=url):
                self.session.post.return_value.url = url
                page = self.board.submit(self.form, "Subject", "Body")
                self.assertEqual(self.board.submission_success(page),
                                 (False, ""))

    def test_topic_only_redirect_identifies_a_single_first_post(self) -> None:
        self.session.post.return_value.url = (
            "https://example.invalid/forum/viewtopic.php?t=42")
        page = self.board.submit(self.form, "Subject", "Body")
        self.assertEqual(self.board.submission_success(page),
                         (True, t("beitrag_da_nr", pid=101)))
        multiple = page + '<div id="p102" class="post bg1">Reply</div>'
        self.assertEqual(self.board.submission_success(multiple), (False, ""))

    def test_a_later_get_clears_redirect_confirmation(self) -> None:
        self.board.submit(self.form, "Subject", "Body")
        self.board.get("index.php")
        self.assertEqual(self.board.submission_success(self.page), (False, ""))

    def test_no_http_redirect_does_not_create_confirmation(self) -> None:
        self.session.post.return_value.history = []
        page = self.board.submit(self.form, "Subject", "Body")
        self.assertEqual(self.board.submission_success(page), (False, ""))
