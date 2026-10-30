"""Protect TUI downloads and exercise save-as selection with file writes."""

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from phpbb_tui.board import Anhang, Board, BoardError
from phpbb_tui.ui import Oberflaeche


class DownloadControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.board = Board.__new__(Board)
        self.board.base = 'https://example.invalid'
        self.board.s = Mock()
        self.board.s.get.side_effect = self.response
        self.ui = Oberflaeche(
            Mock(), self.board, SimpleNamespace(downloads=self.root))
        self.ui._download_ersetzen = Mock(return_value=False)
        self.ui.warten = Mock()
        self.ui.oeffnen = Mock()
        self.attachment = Anhang(7, 'display-name.txt')

    def response(self, *args, **kwargs):
        response = Mock(headers={
            'Content-Disposition': 'attachment; filename="server-name.txt"'})
        response.iter_content.return_value = iter([b'new contents'])
        return response

    def test_new_file_needs_no_confirmation(self):
        target = self.ui._anhang_speichern(self.attachment, self.root)
        self.assertEqual(target.read_bytes(), b'new contents')
        self.ui._download_ersetzen.assert_not_called()

    def test_refusal_preserves_file_and_uses_actual_server_filename(self):
        target = self.root / 'server-name.txt'
        target.write_bytes(b'keep')
        self.assertIsNone(self.ui._anhang_speichern(
            self.attachment, self.root))
        self.assertEqual(target.read_bytes(), b'keep')
        self.assertEqual(target, self.ui._download_ersetzen.call_args.args[0])
        self.board.s.get.assert_called_once()

    def test_confirmation_replaces_the_regular_file(self):
        target = self.root / 'server-name.txt'
        target.write_bytes(b'old')
        self.ui._download_ersetzen.return_value = True
        self.assertEqual(self.ui._anhang_speichern(self.attachment, self.root),
                         target)
        self.assertEqual(target.read_bytes(), b'new contents')
        self.assertEqual(self.board.s.get.call_count, 2)

    def test_symlink_and_directory_never_get_overwrite_prompt(self):
        outside = self.root / 'outside'
        outside.write_bytes(b'keep')
        target = self.root / 'server-name.txt'
        target.symlink_to(outside)
        with self.assertRaises(BoardError):
            self.ui._anhang_speichern(self.attachment, self.root)
        self.assertEqual(outside.read_bytes(), b'keep')
        target.unlink()
        target.mkdir()
        with self.assertRaises(BoardError):
            self.ui._anhang_speichern(self.attachment, self.root)
        self.ui._download_ersetzen.assert_not_called()

    def test_new_file_appearing_during_transfer_is_preserved(self):
        target = self.root / 'server-name.txt'
        original_link = os.link

        def race(source, destination):
            target.write_bytes(b'arrived during download')
            return original_link(source, destination)

        with patch('phpbb_tui.board.os.link', side_effect=race):
            self.assertIsNone(self.ui._anhang_speichern(
                self.attachment, self.root))
        self.assertEqual(target.read_bytes(), b'arrived during download')
        self.assertEqual(list(self.root.glob('.phpbb-tui-*')), [])
        self.assertEqual(target, self.ui._download_ersetzen.call_args.args[0])

    def test_interrupted_confirmed_replacement_preserves_existing_file(self):
        target = self.root / 'server-name.txt'
        target.write_bytes(b'keep')
        self.ui._download_ersetzen.return_value = True

        def chunks():
            yield b'partial'
            raise requests.ConnectionError('dropped response')

        def response(*args, **kwargs):
            result = self.response()
            result.iter_content.return_value = chunks()
            return result

        self.board.s.get.side_effect = response
        with self.assertRaises(requests.ConnectionError):
            self.ui._anhang_speichern(self.attachment, self.root)
        self.assertEqual(target.read_bytes(), b'keep')
        self.assertEqual(list(self.root.glob('.phpbb-tui-*')), [])

    def test_target_changed_to_symlink_after_confirmation_is_refused(self):
        target = self.root / 'server-name.txt'
        target.write_bytes(b'old')
        outside = self.root / 'outside'
        outside.write_bytes(b'keep')

        def confirm(path):
            path.unlink()
            path.symlink_to(outside)
            return True

        self.ui._download_ersetzen.side_effect = confirm
        with self.assertRaises(BoardError):
            self.ui._anhang_speichern(self.attachment, self.root)
        self.assertEqual(outside.read_bytes(), b'keep')

    def test_confirmation_wraps_full_path_and_accepts_only_yes(self):
        self.ui.scr.getmaxyx.return_value = (24, 44)
        path = self.root / ('long-name-' * 10 + '.txt')
        for key in ('y', 'j', 'n', 'q'):
            self.ui.seite_zeigen = Mock(return_value=key)
            self.assertEqual(Oberflaeche._download_ersetzen(self.ui, path),
                             key in ('y', 'j'))
            lines = self.ui.seite_zeigen.call_args.args[1]
            self.assertTrue(all(len(line) <= 40 for line in lines))
            self.assertIn(str(path), ''.join(lines))

    def test_save_as_file_and_directory_do_not_open_download(self):
        for directory in (False, True):
            with self.subTest(directory=directory):
                name = 'nested/' if directory else 'chosen'
                destination = self.root / name
                answer = str(destination) + ('/' if directory else '')
                self.ui.frage = Mock(return_value=answer)
                self.ui.liste = Mock(side_effect=[('S', 0), ('q', 0)])
                self.ui.anhaenge('Author', [self.attachment])
                target = (destination / 'server-name.txt'
                          if directory else destination)
                self.assertEqual(target.read_bytes(), b'new contents')
        self.ui.oeffnen.assert_not_called()

    def test_save_as_cancel_performs_no_network_request(self):
        self.ui.frage = Mock(return_value='')
        self.ui.liste = Mock(side_effect=[('S', 0), ('q', 0)])
        self.ui.anhaenge('Author', [self.attachment])
        self.board.s.get.assert_not_called()

    def test_enter_still_opens_and_lowercase_save_does_not(self):
        for key in ('\n', 's'):
            self.ui.liste = Mock(side_effect=[(key, 0), ('q', 0)])
            self.ui.anhaenge('Author', [self.attachment])
        self.ui.oeffnen.assert_called_once_with(
            str(self.root / 'server-name.txt'))
