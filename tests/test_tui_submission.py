"""Final TUI writes distinguish rejection from an uncertain stored result."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from phpbb_tui import tui_submission
from phpbb_tui.board import Board, Entwurf
from phpbb_tui.i18n import t
from phpbb_tui.ui import Oberflaeche


class SubmissionTests(unittest.TestCase):
    """Exercise real Board POST handling and the surrounding compose loop."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Drafts must never land in the real state directory.
        drafts = patch("phpbb_tui.entwuerfe.ORDNER", Path(self.temp.name) / "drafts")
        drafts.start()
        self.addCleanup(drafts.stop)
        self.session = Mock(headers={})
        with patch("phpbb_tui.board.requests.Session",
                   return_value=self.session):
            self.board = Board("https://example.invalid/forum",
                               Path(self.temp.name) / "cookies.txt")
        self.form = Entwurf({"creation_time": "1"}, "posting.php", {})
        self.response = Mock(text="Unknown response", history=[])
        self.session.post.return_value = self.response
        self.board.dump = Mock(side_effect=AssertionError("Raw diagnostic"))

    def submit(self):
        return tui_submission.submit(self.board, self.form, "Subject", "Body")

    def test_lost_response_is_uncertain_and_sent_once(self):
        self.session.post.side_effect = requests.ReadTimeout("secret token")
        outcome, message = self.submit()
        self.assertEqual(outcome, "uncertain")
        self.assertNotIn("secret", message)
        self.session.post.assert_called_once()
        self.board.dump.assert_not_called()

    def test_unknown_response_and_server_error_are_uncertain(self):
        self.assertEqual(self.submit()[0], "uncertain")
        self.session.post.assert_called_once()
        self.session.post.reset_mock()
        self.response.raise_for_status.side_effect = requests.HTTPError(
            "secret", response=Mock(status_code=503))
        self.assertEqual(self.submit()[0], "uncertain")
        self.session.post.assert_called_once()

    def test_cookie_save_failure_after_write_is_uncertain(self):
        self.board._save = Mock(side_effect=OSError("private path"))
        self.assertEqual(self.submit()[0], "uncertain")
        self.session.post.assert_called_once()

    def test_known_connect_timeout_and_http_rejection(self):
        self.session.post.side_effect = requests.ConnectTimeout("secret")
        self.assertEqual(self.submit(),
                         ("rejected", t("senden_keine_verbindung")))
        self.session.post.side_effect = None
        self.response.raise_for_status.side_effect = requests.HTTPError(
            "secret", response=Mock(status_code=403, history=[]))
        self.assertEqual(self.submit(),
                         ("rejected", t("senden_abgelehnt")))

    def test_http_error_after_redirect_does_not_prove_rejection(self):
        self.response.raise_for_status.side_effect = requests.HTTPError(
            "Denied redirected GET", response=Mock(
                status_code=403, history=[Mock(status_code=302)]))
        self.assertEqual(self.submit()[0], "uncertain")
        self.session.post.assert_called_once()

    def test_content_errors_and_returned_forms_are_rejected(self):
        self.response.text = '<p class="error">Message too short</p>'
        self.assertEqual(self.submit(), ("rejected", "Message too short"))
        self.response.text = ('<form id="postform">successfully posted '
                              '</form>')
        self.assertEqual(self.submit()[0], "rejected")
        self.board.dump.assert_not_called()

    def test_redirected_post_and_pm_confirmations_succeed(self):
        self.response.text = '<div id="p101" class="post">Body</div>'
        self.response.history = [Mock(status_code=302)]
        self.response.url = 'https://example.invalid/forum/viewtopic.php#p101'
        self.assertEqual(self.submit()[0], "success")
        self.form.ziel = "ucp.php"
        self.response.history = []
        self.response.text = (
            '<div id="message">Stored</div><meta http-equiv="refresh" '
            'content="3; url=./ucp.php?i=pm&amp;mode=view&amp;p=42">')
        self.assertEqual(self.submit(), ("success", t("pm_gesendet_kurz")))

    def test_echoed_prose_and_parsing_failure_cannot_confirm(self):
        self.response.text = "Someone wrote: successfully posted"
        self.assertEqual(self.submit()[0], "uncertain")
        self.board.submission_success = Mock(side_effect=ValueError("secret"))
        self.assertEqual(self.submit()[0], "uncertain")

    def interface(self):
        ui = Oberflaeche(Mock(), self.board, Mock())
        ui.scr.getmaxyx.return_value = (24, 100)
        ui._editor = Mock(return_value=("Subject", "Body"))
        ui.warten = Mock()
        ui.bestaetigen = Mock(return_value=False)
        self.board.preview_text = Mock(return_value="Preview")
        return ui

    def test_compose_warns_without_edit_again_for_post_or_pm(self):
        for target in ("posting.php", "ucp.php"):
            with self.subTest(target=target):
                self.form.ziel = target
                ui = self.interface()
                self.board.submit = Mock(side_effect=[
                    "Preview page", OSError("Lost response")])
                ui.seite_zeigen = Mock(side_effect=["a", "q"])
                self.assertFalse(ui._verfassen(self.form))
                self.assertEqual(self.board.submit.call_count, 2)
                ui._editor.assert_called_once()
                ui.bestaetigen.assert_not_called()
                self.assertEqual(ui.seite_zeigen.call_args.args[0],
                                 t("senden_unklar_titel"))
                self.assertIn(t("senden_unklar"), ui.meldung)

    def test_rejection_keeps_edit_again_and_preview_failure_is_not_final(self):
        ui = self.interface()
        self.board.submit = Mock(side_effect=[
            OSError("Preview failed"), '<p class="error">Too short</p>'])
        ui.seite_zeigen = Mock(return_value="a")
        self.assertFalse(ui._verfassen(self.form))
        ui.bestaetigen.assert_called_once()
        self.assertEqual(ui.seite_zeigen.call_count, 1)
