"""Protect attachment targets from failed downloads and unsafe filenames."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from phpbb_tui.board import Anhang, Board, BoardError


class AttachmentDownloadTests(unittest.TestCase):
    """Use temporary files and synthetic streaming responses."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.response = Mock(headers={"Content-Disposition":
                                      'attachment; filename="report.txt"'})
        self.response.iter_content.return_value = iter((b"complete", b" file"))
        self.session = Mock(headers={})
        self.session.get.return_value = self.response
        with patch("phpbb_tui.board.requests.Session",
                   return_value=self.session):
            self.board = Board("https://example.invalid",
                               self.root / "cookies")
        self.attachment = Anhang(7, "fallback.txt")

    @staticmethod
    def interrupted():
        yield b"partial"
        raise requests.ConnectionError("Interrupted stream")

    def test_interruption_preserves_existing_file(self) -> None:
        target = self.root / "report.txt"
        target.write_bytes(b"original")
        self.response.iter_content.return_value = self.interrupted()
        with self.assertRaises(requests.ConnectionError):
            self.board.anhang_laden(self.attachment, self.root)
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(list(self.root.glob('.phpbb-tui-*')), [])
        self.response.close.assert_called_once()

    def test_interruption_does_not_publish_a_partial_new_file(self) -> None:
        self.response.iter_content.return_value = self.interrupted()
        with self.assertRaises(requests.ConnectionError):
            self.board.anhang_laden(self.attachment, self.root)
        self.assertFalse((self.root / "report.txt").exists())

    def test_success_replaces_the_complete_file(self) -> None:
        target = self.root / "report.txt"
        target.write_bytes(b"original")
        self.assertEqual(self.board.anhang_laden(self.attachment, self.root),
                         target)
        self.assertEqual(target.read_bytes(), b"complete file")
        self.response.close.assert_called_once()

    def test_symlink_target_is_never_followed(self) -> None:
        outside = self.root / "outside.txt"
        outside.write_bytes(b"preserve")
        (self.root / "report.txt").symlink_to(outside)
        with self.assertRaises(BoardError):
            self.board.anhang_laden(self.attachment, self.root)
        self.assertEqual(outside.read_bytes(), b"preserve")
        self.response.iter_content.assert_not_called()

    def test_encoded_and_path_filenames_are_safely_resolved(self) -> None:
        for header, expected in (
            ("attachment; filename*=UTF-8''caf%C3%A9.txt", "café.txt"),
            ('attachment; filename="../report.txt"', ".._report.txt"),
            ('attachment; filename=".."', "anhang-7"),
        ):
            with self.subTest(header=header):
                self.response.headers["Content-Disposition"] = header
                self.response.iter_content.return_value = iter((b"fixture",))
                target = self.board.anhang_laden(self.attachment, self.root)
                self.assertEqual(target, self.root / expected)

    def test_html_error_page_is_not_saved_as_a_download(self) -> None:
        self.response.headers = {"Content-Type": "text/html; charset=UTF-8"}
        with self.assertRaises(BoardError):
            self.board.anhang_laden(self.attachment, self.root)
        self.assertFalse((self.root / "fallback.txt").exists())
        self.response.close.assert_called_once()
